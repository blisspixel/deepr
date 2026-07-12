"""Tests for the `deepr upgrade` self-update command."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.commands import upgrade as upgrade_mod
from deepr.cli.commands.upgrade import upgrade

WHEEL_URL = "https://github.com/blisspixel/deepr/releases/download/v9.9.9/deepr_research-9.9.9-py3-none-any.whl"


def _release(version: str = "9.9.9", wheel_url: str | None = WHEEL_URL) -> upgrade_mod.ReleaseInfo:
    return upgrade_mod.ReleaseInfo(version=version, tag=f"v{version}", wheel_url=wheel_url)


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


def test_detect_origin_recognizes_editable_direct_url(monkeypatch):
    distribution = SimpleNamespace(read_text=lambda _name: '{"dir_info": {"editable": true}}')
    monkeypatch.setattr(upgrade_mod.importlib_metadata, "distribution", lambda _name: distribution)

    assert upgrade_mod._detect_origin() == "editable"


class TestUpgradeCheck:
    def test_check_reports_newer_available(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "__version__", "2.14.0")
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: _release("2.15.0"))

        result = CliRunner().invoke(upgrade, ["--check"])

        assert result.exit_code == 0
        assert "2.15.0" in result.output
        assert "newer version is available" in result.output

    def test_check_reports_up_to_date(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "__version__", "2.15.0")
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: _release("2.15.0"))

        result = CliRunner().invoke(upgrade, ["--check"])

        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    def test_check_handles_offline(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: None)

        result = CliRunner().invoke(upgrade, ["--check"])

        assert result.exit_code == 0
        assert "could not read the latest github release" in result.output.lower()

    def test_check_never_invokes_subprocess(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: _release())

        def _boom(*a, **k):  # pragma: no cover - must not be called
            raise AssertionError("subprocess.run must not run under --check")

        monkeypatch.setattr(subprocess, "run", _boom)
        result = CliRunner().invoke(upgrade, ["--check"])
        assert result.exit_code == 0

    def test_check_reports_missing_wheel(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: _release(wheel_url=None))

        result = CliRunner().invoke(upgrade, ["--check"])

        assert result.exit_code == 0
        assert "does not include a supported deepr wheel" in result.output.lower()


class TestReleasePayload:
    def test_selects_supported_wheel(self):
        payload = {
            "tag_name": "v9.9.9",
            "assets": [
                {"name": "notes.txt", "browser_download_url": f"{WHEEL_URL}.txt"},
                {
                    "name": "deepr_research-9.9.9-py3-none-any.whl",
                    "browser_download_url": WHEEL_URL,
                },
            ],
        }

        assert upgrade_mod._release_from_payload(payload) == _release()

    def test_rejects_wheel_url_outside_repository(self):
        payload = {
            "tag_name": "v9.9.9",
            "assets": [
                {
                    "name": "deepr_research-9.9.9-py3-none-any.whl",
                    "browser_download_url": "https://example.com/deepr_research-9.9.9-py3-none-any.whl",
                },
            ],
        }

        assert upgrade_mod._release_from_payload(payload) == _release(wheel_url=None)

    def test_rejects_wheel_from_a_different_version(self):
        payload = {
            "tag_name": "v9.9.8",
            "assets": [
                {
                    "name": "deepr_research-9.9.9-py3-none-any.whl",
                    "browser_download_url": WHEEL_URL,
                },
            ],
        }

        assert upgrade_mod._release_from_payload(payload) == _release("9.9.8", wheel_url=None)

    def test_rejects_payload_without_tag(self):
        assert upgrade_mod._release_from_payload({"assets": []}) is None


class TestUpgradeRun:
    def test_editable_prints_git_guidance_no_subprocess(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: _release())
        monkeypatch.setattr(upgrade_mod, "_detect_origin", lambda: "editable")

        def _boom(*a, **k):  # pragma: no cover
            raise AssertionError("editable installs must not auto-run an upgrade")

        monkeypatch.setattr(subprocess, "run", _boom)
        result = CliRunner().invoke(upgrade, [])

        assert result.exit_code == 0
        assert "git" in result.output.lower()
        assert "pip install -e ." in result.output

    def test_pipx_installs_release_wheel(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: _release())
        monkeypatch.setattr(upgrade_mod, "_detect_origin", lambda: "pipx")
        calls: list[list[str]] = []

        def _fake_run(cmd, check=False):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(subprocess, "run", _fake_run)
        result = CliRunner().invoke(upgrade, [])

        assert result.exit_code == 0
        assert calls == [["pipx", "install", "--force", WHEEL_URL]]
        assert "complete" in result.output.lower()

    def test_pip_failure_propagates_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: _release())
        monkeypatch.setattr(upgrade_mod, "_detect_origin", lambda: "pip")

        def _fake_run(cmd, check=False):
            return subprocess.CompletedProcess(cmd, 1)

        monkeypatch.setattr(subprocess, "run", _fake_run)
        result = CliRunner().invoke(upgrade, [])

        assert result.exit_code == 1

    def test_offline_upgrade_exits_without_subprocess(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: None)

        def _boom(*a, **k):  # pragma: no cover
            raise AssertionError("offline upgrade must not invoke a subprocess")

        monkeypatch.setattr(subprocess, "run", _boom)
        result = CliRunner().invoke(upgrade, [])

        assert result.exit_code == 1
        assert "no changes were made" in result.output.lower()

    def test_missing_wheel_exits_without_subprocess(self, monkeypatch):
        monkeypatch.setattr(upgrade_mod, "_fetch_latest_release", lambda: _release(wheel_url=None))
        monkeypatch.setattr(upgrade_mod, "_detect_origin", lambda: "pipx")

        def _boom(*a, **k):  # pragma: no cover
            raise AssertionError("missing wheel must not invoke a subprocess")

        monkeypatch.setattr(subprocess, "run", _boom)
        result = CliRunner().invoke(upgrade, [])

        assert result.exit_code == 1
        assert "no supported deepr wheel asset" in result.output.lower()
