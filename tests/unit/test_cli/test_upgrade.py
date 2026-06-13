"""Tests for the `deepr upgrade` self-update command."""

from __future__ import annotations

import subprocess

from click.testing import CliRunner

from deepr.cli.commands import upgrade as upgrade_mod
from deepr.cli.commands.upgrade import upgrade


class TestVersionTuple:
    def test_basic(self):
        assert upgrade_mod._version_tuple("2.14.0") == (2, 14, 0)

    def test_prerelease_suffix_is_tolerated(self):
        assert upgrade_mod._version_tuple("2.15.0rc1") == (2, 15, 0)

    def test_ordering(self):
        assert upgrade_mod._version_tuple("2.14.0") < upgrade_mod._version_tuple("2.15.0")
        assert upgrade_mod._version_tuple("2.14.0") < upgrade_mod._version_tuple("2.14.1")

    def test_garbage_is_zero_not_an_error(self):
        assert upgrade_mod._version_tuple("garbage") == (0,)


class TestUpgradeCheck:
    def test_check_reports_newer_available(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "__version__", "2.14.0")
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_version", lambda: "2.15.0")

        result = CliRunner().invoke(upgrade, ["--check"])

        assert result.exit_code == 0
        assert "2.15.0" in result.output
        assert "newer version is available" in result.output

    def test_check_reports_up_to_date(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "__version__", "2.15.0")
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_version", lambda: "2.15.0")

        result = CliRunner().invoke(upgrade, ["--check"])

        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    def test_check_handles_offline(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_version", lambda: None)

        result = CliRunner().invoke(upgrade, ["--check"])

        assert result.exit_code == 0
        assert "could not reach pypi" in result.output.lower()

    def test_check_never_invokes_subprocess(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_version", lambda: "9.9.9")

        def _boom(*a, **k):  # pragma: no cover - must not be called
            raise AssertionError("subprocess.run must not run under --check")

        monkeypatch.setattr(subprocess, "run", _boom)
        result = CliRunner().invoke(upgrade, ["--check"])
        assert result.exit_code == 0


class TestUpgradeRun:
    def test_editable_prints_git_guidance_no_subprocess(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_version", lambda: "9.9.9")
        monkeypatch.setattr(upgrade_mod, "_detect_origin", lambda: "editable")

        def _boom(*a, **k):  # pragma: no cover
            raise AssertionError("editable installs must not auto-run an upgrade")

        monkeypatch.setattr(subprocess, "run", _boom)
        result = CliRunner().invoke(upgrade, [])

        assert result.exit_code == 0
        assert "git" in result.output.lower()
        assert "pip install -e ." in result.output

    def test_pipx_runs_pipx_upgrade(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_version", lambda: "9.9.9")
        monkeypatch.setattr(upgrade_mod, "_detect_origin", lambda: "pipx")
        calls: list[list[str]] = []

        def _fake_run(cmd, check=False):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(subprocess, "run", _fake_run)
        result = CliRunner().invoke(upgrade, [])

        assert result.exit_code == 0
        assert calls == [["pipx", "upgrade", "deepr-research"]]
        assert "complete" in result.output.lower()

    def test_pip_failure_propagates_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_version", lambda: "9.9.9")
        monkeypatch.setattr(upgrade_mod, "_detect_origin", lambda: "pip")

        def _fake_run(cmd, check=False):
            return subprocess.CompletedProcess(cmd, 1)

        monkeypatch.setattr(subprocess, "run", _fake_run)
        result = CliRunner().invoke(upgrade, [])

        assert result.exit_code == 1
