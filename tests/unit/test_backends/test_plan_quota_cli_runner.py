"""Tests for deepr.backends.plan_quota.cli_runner.

Uses real hermetic subprocesses via ``sys.executable`` (cross-platform, fast, no
vendor CLI needed) so the runner's launch/timeout/exit-code handling is exercised
for real rather than mocked.
"""

from __future__ import annotations

import json
import os
import sys

from deepr.backends.plan_quota.cli_runner import _clean_argv, run_cli


class TestRunCli:
    async def test_captures_stdout(self):
        result = await run_cli([sys.executable, "-c", "import sys; sys.stdout.write('hello')"])
        assert result.ok
        assert result.stdout == "hello"
        assert result.returncode == 0
        assert result.duration_ms >= 0

    async def test_feeds_stdin(self):
        result = await run_cli(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
            stdin="piped-prompt",
        )
        assert result.ok
        assert result.stdout == "piped-prompt"

    async def test_separates_stderr(self):
        result = await run_cli(
            [sys.executable, "-c", "import sys; sys.stderr.write('progress'); sys.stdout.write('answer')"]
        )
        assert result.stdout == "answer"
        assert "progress" in result.stderr

    async def test_nonzero_exit_is_not_ok(self):
        result = await run_cli([sys.executable, "-c", "import sys; sys.exit(3)"])
        assert not result.ok
        assert result.returncode == 3
        assert not result.timed_out
        assert not result.launch_error

    async def test_timeout_kills_and_flags(self):
        result = await run_cli([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
        assert not result.ok
        assert result.timed_out
        assert result.returncode is None

    async def test_launch_failure_is_reported_not_raised(self):
        result = await run_cli(["deepr-no-such-binary-xyz-123"])
        assert not result.ok
        assert result.launch_error
        assert result.returncode is None

    async def test_null_bytes_in_prompt_argument_are_normalized(self):
        result = await run_cli([sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", "fresh\x00context"])
        assert result.ok
        assert result.stdout == "fresh context"

    def test_executable_is_resolved_with_pathext(self, monkeypatch):
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.shutil.which",
            lambda exe: "C:/bin/codex.cmd" if exe == "codex" else None,
        )

        assert _clean_argv(["codex", "exec"]) == ["C:/bin/codex.cmd", "exec"]

    async def test_invalid_environment_entries_are_omitted(self):
        env: dict[str, object] = dict(os.environ)
        env["DEEPR_BAD"] = "x\x00y"
        env["DEEPR_NONE"] = None
        result = await run_cli(
            [
                sys.executable,
                "-c",
                (
                    "import json, os; "
                    "print(json.dumps({'bad': os.environ.get('DEEPR_BAD'), "
                    "'none': os.environ.get('DEEPR_NONE')}, sort_keys=True))"
                ),
            ],
            env=env,
        )
        assert result.ok
        assert json.loads(result.stdout) == {"bad": None, "none": None}
