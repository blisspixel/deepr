"""Tests for deepr.backends.plan_quota.cli_runner.

Uses real hermetic subprocesses via ``sys.executable`` (cross-platform, fast, no
vendor CLI needed) so the runner's launch/timeout/exit-code handling is exercised
for real rather than mocked.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

from deepr.backends.plan_quota.cli_runner import _clean_argv, _kill_process_tree, run_cli


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

    async def test_communicate_error_uses_bounded_cleanup_and_preserves_error(
        self,
        monkeypatch,
    ):
        communicate_error = RuntimeError("fixture communicate failure")

        class ErrorThenHungProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 222
                self.communicate_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    raise communicate_error
                await asyncio.Future()

            async def wait(self):
                await asyncio.Future()

        process = ErrorThenHungProcess()
        killed = []

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            killed.append(active_process)
            active_process.returncode = -9

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._PROCESS_CLEANUP_TIMEOUT_S",
            0.01,
        )

        result = await asyncio.wait_for(run_cli(["fake-plan-cli"]), timeout=0.2)

        assert result.runtime_error == "runner failed (RuntimeError)"
        assert result.runtime_exception is communicate_error
        assert killed == [process]
        assert process.communicate_calls == 2

    async def test_timeout_kills_and_flags(self):
        result = await run_cli([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
        assert not result.ok
        assert result.timed_out
        assert result.returncode is None

    async def test_cancellation_kills_started_process_and_propagates(self, monkeypatch):
        communicate_started = asyncio.Event()

        class BlockingProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 123
                self.communicate_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    communicate_started.set()
                    await asyncio.Future()
                return b"", b""

        process = BlockingProcess()
        killed = []

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            killed.append(active_process)
            active_process.returncode = -9

        monkeypatch.setattr("deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec", create_process)
        monkeypatch.setattr("deepr.backends.plan_quota.cli_runner._kill_process_tree", kill_process_tree)
        task = asyncio.create_task(run_cli(["fake-plan-cli"]), name="cancel-plan-cli")
        await communicate_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert killed == [process]
        assert process.communicate_calls == 2

    async def test_cancellation_during_launch_cleans_up_late_process_and_propagates(
        self,
        monkeypatch,
    ):
        launch_started = asyncio.Event()
        finish_launch = asyncio.Event()

        class LateProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 456
                self.communicate_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                return b"", b""

        process = LateProcess()
        killed = []

        async def delayed_create(*args, **kwargs):
            launch_started.set()
            await finish_launch.wait()
            return process

        async def kill_process_tree(active_process):
            killed.append(active_process)
            active_process.returncode = -9

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            delayed_create,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        task = asyncio.create_task(run_cli(["fake-plan-cli"]), name="cancel-launch")
        await launch_started.wait()

        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish_launch.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert killed == [process]
        assert process.communicate_calls == 1

    async def test_hung_launch_cancellation_is_bounded_and_keeps_cleanup_owner(
        self,
        monkeypatch,
    ):
        from deepr.backends.plan_quota import cli_runner

        launch_started = asyncio.Event()
        finish_launch = asyncio.Event()
        cleanup_finished = asyncio.Event()

        class VeryLateProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 654
                self.communicate_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                return b"", b""

        process = VeryLateProcess()

        async def hung_create(*args, **kwargs):
            launch_started.set()
            await finish_launch.wait()
            return process

        async def kill_process_tree(active_process):
            active_process.returncode = -9
            cleanup_finished.set()

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            hung_create,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._LAUNCH_CLEANUP_GRACE_S",
            0.01,
        )
        task = asyncio.create_task(run_cli(["fake-plan-cli"]), name="cancel-hung-launch")
        await launch_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.2)

        assert len(cli_runner._BACKGROUND_CLEANUPS) == 1
        finish_launch.set()
        await asyncio.wait_for(cleanup_finished.wait(), timeout=0.2)
        for _ in range(10):
            if not cli_runner._BACKGROUND_CLEANUPS:
                break
            await asyncio.sleep(0)

        assert cli_runner._BACKGROUND_CLEANUPS == set()
        assert process.communicate_calls == 1

    async def test_cancellation_cleanup_reap_is_bounded(self, monkeypatch):
        communicate_started = asyncio.Event()

        class HungReapProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 789
                self.communicate_calls = 0
                self.kill_calls = 0

            async def communicate(self, input_bytes=None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    communicate_started.set()
                await asyncio.Future()

            def kill(self):
                self.kill_calls += 1
                self.returncode = -9

        process = HungReapProcess()

        async def create_process(*args, **kwargs):
            return process

        async def kill_process_tree(active_process):
            active_process.kill()

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._kill_process_tree",
            kill_process_tree,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._PROCESS_CLEANUP_TIMEOUT_S",
            0.01,
        )
        task = asyncio.create_task(run_cli(["fake-plan-cli"]), name="cancel-hung-reap")
        await communicate_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.2)

        assert process.kill_calls == 1
        assert process.communicate_calls == 2

    async def test_windows_taskkill_wait_is_bounded(self, monkeypatch):
        class HungTaskkill:
            def __init__(self):
                self.returncode = None
                self.kill_calls = 0

            async def wait(self):
                await asyncio.Future()

            def kill(self):
                self.kill_calls += 1
                self.returncode = -9

        class ActiveProcess:
            def __init__(self):
                self.returncode = None
                self.pid = 321
                self.kill_calls = 0

            def kill(self):
                self.kill_calls += 1
                self.returncode = -9

        killer = HungTaskkill()
        process = ActiveProcess()

        async def create_taskkill(*args, **kwargs):
            return killer

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.subprocess.CREATE_NEW_PROCESS_GROUP",
            1,
            raising=False,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_taskkill,
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._PROCESS_CLEANUP_TIMEOUT_S",
            0.01,
        )

        await asyncio.wait_for(_kill_process_tree(process), timeout=0.2)

        assert killer.kill_calls == 1
        assert process.kill_calls == 1

    async def test_launch_failure_is_reported_not_raised(self):
        result = await run_cli(["deepr-no-such-binary-xyz-123"])
        assert not result.ok
        assert result.launch_error
        assert result.returncode is None

    async def test_launch_failure_hides_resolved_path_and_retains_raw_exception(
        self,
        monkeypatch,
    ):
        launch_exception = FileNotFoundError(
            2,
            "private operating system detail",
            "C:/Users/private-account/bin/codex.exe",
        )

        async def fail_launch(*args, **kwargs):
            raise launch_exception

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.shutil.which",
            lambda _exe: "C:/Users/private-account/bin/codex.exe",
        )
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            fail_launch,
        )

        result = await run_cli(["codex"])

        assert "C:/Users" not in result.launch_error
        assert "private-account" not in result.launch_error
        assert "private operating system detail" not in result.launch_error
        assert result.launch_error == "failed to launch 'codex.exe' (FileNotFoundError, errno=2)"
        assert result.launch_exception is launch_exception
        assert "private-account" not in repr(result)

    @pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf"), "1"])
    async def test_invalid_timeout_is_rejected_before_launch(self, monkeypatch, timeout):
        launch_calls = []

        async def create_process(*args, **kwargs):
            launch_calls.append(args)
            raise AssertionError("must not launch")

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )

        with pytest.raises(ValueError, match="finite positive"):
            await run_cli(["fake-plan-cli"], timeout=timeout)

        assert launch_calls == []

    async def test_scratch_failure_is_structured_and_path_safe_before_launch(self, monkeypatch):
        launch_calls = []
        scratch_error = PermissionError("C:/Users/private-account/scratch")

        async def create_process(*args, **kwargs):
            launch_calls.append(args)
            raise AssertionError("must not launch")

        def fail_scratch():
            raise scratch_error

        monkeypatch.setattr("deepr.backends.plan_quota.cli_runner._scratch_dir", fail_scratch)
        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )

        result = await run_cli(["fake-plan-cli"])

        assert result.launch_error == "failed to launch 'fake-plan-cli' (PermissionError)"
        assert "private-account" not in result.launch_error
        assert result.launch_exception is scratch_error
        assert launch_calls == []

    async def test_invalid_stdin_is_rejected_before_process_launch(self, monkeypatch):
        launch_calls = []

        async def create_process(*args, **kwargs):
            launch_calls.append(args)
            raise AssertionError("must not launch")

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner.asyncio.create_subprocess_exec",
            create_process,
        )

        result = await run_cli(["fake-plan-cli"], stdin="unpaired-\ud800")

        assert "UnicodeEncodeError" in result.launch_error
        assert result.returncode is None
        assert launch_calls == []

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
