"""Tests for `deepr init` - guided first-run setup.

Assertions key off the deterministic .env file state (and exit codes) rather
than Rich-rendered console text. CliRunner.isolated_filesystem keeps every
write inside a temp dir, so no real .env is touched.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from deepr.cli.commands.init import _key_is_set, _read_env_file, _upsert_env, init


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Determinism: no provider/budget vars leak in from the host machine."""
    for var in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "XAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPR_MAX_COST_PER_JOB",
        "DEEPR_MAX_COST_PER_DAY",
        "DEEPR_MAX_COST_PER_MONTH",
    ):
        monkeypatch.delenv(var, raising=False)


class TestKeyDetection:
    def test_blank_and_placeholder_are_unset(self):
        assert not _key_is_set(None)
        assert not _key_is_set("")
        assert not _key_is_set("   ")
        assert not _key_is_set("your-openai-api-key")

    def test_real_key_is_set(self):
        assert _key_is_set("sk-abc123realkey")


class TestEnvFileHelpers:
    def test_upsert_creates_and_preserves(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("# header\nKEEP=yes\nGEMINI_API_KEY=old\n", encoding="utf-8")
        _upsert_env(path, {"GEMINI_API_KEY": "new", "NEW_VAR": "1"})
        parsed = _read_env_file(path)
        assert parsed["GEMINI_API_KEY"] == "new"  # updated in place
        assert parsed["KEEP"] == "yes"  # preserved
        assert parsed["NEW_VAR"] == "1"  # appended
        assert "# header" in path.read_text(encoding="utf-8")  # comment kept


class TestInitYes:
    def test_creates_env_and_default_budget_when_missing(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(init, ["--yes"])
            assert result.exit_code == 0
            env = _read_env_file(__import__("pathlib").Path(".env"))
            assert env["DEEPR_MAX_COST_PER_JOB"] == "5.0"
            assert env["DEEPR_MAX_COST_PER_DAY"] == "25.0"
            assert env["DEEPR_MAX_COST_PER_MONTH"] == "200.0"

    def test_detects_key_already_in_environment(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key-123")
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(init, ["--yes"])
            assert result.exit_code == 0
            assert "Gemini" in result.output

    def test_budget_option_sets_per_job_ceiling(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(init, ["--yes", "--budget", "2.5"])
            assert result.exit_code == 0
            env = _read_env_file(__import__("pathlib").Path(".env"))
            assert env["DEEPR_MAX_COST_PER_JOB"] == "2.5"

    def test_existing_budget_not_clobbered(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            from pathlib import Path

            Path(".env").write_text("DEEPR_MAX_COST_PER_JOB=7.0\n", encoding="utf-8")
            result = runner.invoke(init, ["--yes"])
            assert result.exit_code == 0
            assert _read_env_file(Path(".env"))["DEEPR_MAX_COST_PER_JOB"] == "7.0"

    def test_existing_env_key_preserved(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            from pathlib import Path

            Path(".env").write_text("MY_OTHER_VAR=keepme\nGEMINI_API_KEY=real-key-abc\n", encoding="utf-8")
            result = runner.invoke(init, ["--yes"])
            assert result.exit_code == 0
            env = _read_env_file(Path(".env"))
            assert env["MY_OTHER_VAR"] == "keepme"
            assert env["GEMINI_API_KEY"] == "real-key-abc"

    def test_data_dir_sets_portable_paths(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            from pathlib import Path

            result = runner.invoke(init, ["--yes", "--data-dir", "/synced/deepr"])
            assert result.exit_code == 0
            env = _read_env_file(Path(".env"))
            assert env["DEEPR_DATA_DIR"] == "/synced/deepr"
            assert env["DEEPR_EXPERTS_PATH"] == "/synced/deepr/experts"
            assert env["DEEPR_REPORTS_PATH"] == "/synced/deepr/reports"


class TestInitInteractive:
    def test_adds_one_key_and_sets_budget(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            from pathlib import Path

            # Gemini: yes + key; decline OpenAI/Grok/Anthropic; budget 4; default data dir.
            result = runner.invoke(init, [], input="y\nreal-gemini-xyz\nn\nn\nn\n4\n\n")
            assert result.exit_code == 0
            env = _read_env_file(Path(".env"))
            assert env["GEMINI_API_KEY"] == "real-gemini-xyz"
            assert env["DEEPR_MAX_COST_PER_JOB"] == "4.0"

    def test_decline_all_keys_still_writes_budget(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            from pathlib import Path

            result = runner.invoke(init, [], input="n\nn\nn\nn\n5\n\n")
            assert result.exit_code == 0
            env = _read_env_file(Path(".env"))
            assert "GEMINI_API_KEY" not in env
            assert env["DEEPR_MAX_COST_PER_JOB"] == "5.0"
