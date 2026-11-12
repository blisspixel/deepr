"""Regression checks for the public GitHub Releases install channel."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.release_notes import changelog_section, fallback_summary, release_notes_text
from scripts.release_notes import main as release_notes_main
from scripts.write_release_checksums import checksum_lines
from scripts.write_release_checksums import main as write_checksums_main

ROOT = Path(__file__).parents[2]


def _installer_shell(family: str) -> str:
    if family == "powershell":
        executable = shutil.which("powershell") or shutil.which("pwsh")
    elif sys.platform == "win32":
        git_bash = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
        executable = str(git_bash) if git_bash.is_file() else None
    else:
        executable = shutil.which("bash")
    if executable is None:
        pytest.skip(f"{family} is not installed on this platform")
    return executable


@pytest.mark.parametrize("family", ["powershell", "bash"])
@pytest.mark.parametrize("behavior", ["works", "repair_works", "stays_broken"])
def test_installer_exit_status_reflects_cli_after_repair(tmp_path: Path, family: str, behavior: str) -> None:
    """Run the real installer with local command doubles, without network or installs."""
    shell = _installer_shell(family)
    release = {
        "tag_name": "v2.50.18",
        "assets": [
            {
                "name": "deepr_research-2.50.18-py3-none-any.whl",
                "browser_download_url": (
                    "https://github.com/blisspixel/deepr/releases/download/"
                    "v2.50.18/deepr_research-2.50.18-py3-none-any.whl"
                ),
            }
        ],
    }
    env = {
        **os.environ,
        "DEEPR_INSTALL_TEST_BEHAVIOR": behavior,
        "DEEPR_INSTALL_TEST_RELEASE": json.dumps(release),
        "DEEPR_INSTALL_TEST_PYTHON": Path(sys.executable).as_posix(),
        "DEEPR_INSTALL_TEST_OPERATIONS": (tmp_path / "operations.txt").as_posix(),
        "DEEPR_INSTALL_TEST_SCRIPT": (
            ROOT / "scripts" / f"install.{'ps1' if family == 'powershell' else 'sh'}"
        ).as_posix(),
    }
    if family == "powershell":
        wrapper = tmp_path / "installer-test.ps1"
        wrapper.write_text(
            """$global:installCount = 0
function python {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq '-c') { & $env:DEEPR_INSTALL_TEST_PYTHON @args; return }
    if ($args[2] -eq '--version') { '1.17.2'; return }
    if ($args[2] -eq 'list') { 'deepr-research'; return }
    if ($args[2] -eq 'install') { $global:installCount += 1 }
    Add-Content -LiteralPath $env:DEEPR_INSTALL_TEST_OPERATIONS -Value $args[2]
}
function pipx {
    if ($args[0] -eq 'environment') {
        $global:LASTEXITCODE = 0
        if ($args[2] -eq 'PIPX_LOCAL_VENVS') { '/owned' } else { '/shim/bin' }
        return
    }
    python -m pipx @args
}
Set-Alias -Name (Join-Path '/owned' 'deepr-research/Scripts/python.exe') -Value python
function Get-Command {
    param($Name, $ErrorAction)
    if ($Name -eq 'deepr') { return [pscustomobject]@{ Source = '/shim/bin/deepr.exe' } }
    Microsoft.PowerShell.Core\\Get-Command -Name $Name -ErrorAction SilentlyContinue
}
function uv { $global:LASTEXITCODE = 0; if ($args[0] -ne 'tool' -or $args[1] -ne 'list') { throw 'unexpected uv mutation' } }
function deepr {
    if ($env:DEEPR_INSTALL_TEST_BEHAVIOR -eq 'stays_broken' -or
        ($env:DEEPR_INSTALL_TEST_BEHAVIOR -eq 'repair_works' -and $global:installCount -lt 2)) {
        $global:LASTEXITCODE = 7
        return
    }
    $global:LASTEXITCODE = 0
    'deepr, version 2.50.18'
}
function Invoke-RestMethod { $env:DEEPR_INSTALL_TEST_RELEASE | ConvertFrom-Json }
Invoke-Expression (Get-Content -LiteralPath $env:DEEPR_INSTALL_TEST_SCRIPT -Raw)
""",
            encoding="utf-8",
        )
        command = [shell, "-NoProfile", "-NonInteractive", "-File", str(wrapper)]
    else:
        wrapper = tmp_path / "installer-test.sh"
        wrapper.write_text(
            """install_count=0
python3() {
    if [ "$1" = '-c' ]; then "$DEEPR_INSTALL_TEST_PYTHON" "$@"; return; fi
    case "$3" in
        --version) printf '1.17.2\\n' ;;
        list) printf 'deepr-research\\n' ;;
        install) install_count=$((install_count + 1)); printf 'install\\n' >> "$DEEPR_INSTALL_TEST_OPERATIONS" ;;
        uninstall) printf 'uninstall\\n' >> "$DEEPR_INSTALL_TEST_OPERATIONS" ;;
        *) return 90 ;;
    esac
}
pipx() {
    if [ "$1" = environment ]; then
        if [ "$3" = PIPX_LOCAL_VENVS ]; then printf '/owned\\n'; else printf '/shim/bin\\n'; fi
    else python3 -m pipx "$@"; fi
}
/owned/deepr-research/bin/python() { python3 "$@"; }
command() { if [ "$1" = -v ] && [ "$2" = deepr ]; then printf '/shim/bin/deepr\\n'; else builtin command "$@"; fi; }
uv() { [ "$1" = tool ] && [ "$2" = list ]; }
curl() { printf '%s' "$DEEPR_INSTALL_TEST_RELEASE"; }
deepr() {
    if [ "$DEEPR_INSTALL_TEST_BEHAVIOR" = stays_broken ] ||
       { [ "$DEEPR_INSTALL_TEST_BEHAVIOR" = repair_works ] && [ "$install_count" -lt 2 ]; }; then
        return 7
    fi
    printf 'deepr, version 2.50.18\\n'
}
source "$DEEPR_INSTALL_TEST_SCRIPT"
""",
            encoding="utf-8",
            newline="\n",
        )
        command = [shell, str(wrapper)]
    result = subprocess.run(command, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    output = result.stdout + result.stderr
    operations = (tmp_path / "operations.txt").read_text(encoding="utf-8-sig").splitlines()
    assert operations.count("install") == (1 if behavior == "works" else 2), output
    assert operations.count("uninstall") == (0 if behavior == "works" else 1), output
    if behavior == "stays_broken":
        assert result.returncode != 0, output
        assert "still does not run" in output
        assert "==> Done." not in output
        assert "Next steps:" not in output
    else:
        assert result.returncode == 0, output
        assert "==> Done." in output
        assert "deepr, version 2.50.18" in output


@pytest.mark.parametrize("relative_path", ["scripts/install.sh", "scripts/install.ps1"])
def test_installers_resolve_a_repository_release_wheel(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "https://api.github.com/repos/blisspixel/deepr/releases/latest" in text
    assert "https://github.com/blisspixel/deepr/releases/download/" in text
    assert "deepr_research-" in text
    assert "--force" in text
    assert "-m pipx --version" in text
    assert "pypi.org" not in text.lower()
    assert "cd deepr/deepr" not in text
    assert "Configure owned-local Ollama or a safety-eligible plan CLI" in text
    assert "budget set 5" in text
    assert "Add at least one API key" not in text


def test_windows_installer_does_not_bootstrap_into_user_or_venv_python() -> None:
    text = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")

    assert "function Test-PipxAvailable($PythonCommand)" in text
    assert "& $PythonCommand -m pipx --version *> $null" in text
    assert "catch {" in text
    assert "return $false" in text
    assert "pip install --user" not in text
    assert "official instructions" in text
    assert "--managed-python" in text


def test_makefile_exposes_only_explicit_manual_pypi_publication() -> None:
    text = (ROOT / "scripts/Makefile").read_text(encoding="utf-8")

    assert "publish-pypi-manual:" in text
    assert "\npublish:" not in text
    assert "GitHub Releases is the current release channel" in text


@pytest.mark.parametrize("family", ["powershell", "bash"])
def test_installer_missing_release_assets_fails_clearly(tmp_path: Path, family: str) -> None:
    """A release with no wheel exits before any install and names the missing asset."""
    shell = _installer_shell(family)
    release = {"tag_name": "v2.51.7", "assets": []}
    operations = tmp_path / "operations.txt"
    env = {
        **os.environ,
        "DEEPR_INSTALL_TEST_RELEASE": json.dumps(release),
        "DEEPR_INSTALL_TEST_PYTHON": Path(sys.executable).as_posix(),
        "DEEPR_INSTALL_TEST_OPERATIONS": operations.as_posix(),
        "DEEPR_INSTALL_TEST_SCRIPT": (
            ROOT / "scripts" / f"install.{'ps1' if family == 'powershell' else 'sh'}"
        ).as_posix(),
    }
    if family == "powershell":
        wrapper = tmp_path / "missing-assets.ps1"
        wrapper.write_text(
            r"""
function python {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq '-c') { & $env:DEEPR_INSTALL_TEST_PYTHON @args; return }
    Add-Content -LiteralPath $env:DEEPR_INSTALL_TEST_OPERATIONS -Value ($args -join ' ')
}
function uv {
    $global:LASTEXITCODE = 0
    Add-Content -LiteralPath $env:DEEPR_INSTALL_TEST_OPERATIONS -Value ("uv " + ($args -join ' '))
    if ($args[0] -eq '--version') { 'uv 0.13.7'; return }
    if ($args[0] -eq 'tool' -and $args[1] -eq 'list') { return }
}
function Get-Command {
    param($Name, $ErrorAction)
    if ($Name -in @('uv', 'python')) { return [pscustomobject]@{ Source = "$Name.exe" } }
    return $null
}
function Invoke-RestMethod { $env:DEEPR_INSTALL_TEST_RELEASE | ConvertFrom-Json }
Invoke-Expression (Get-Content -LiteralPath $env:DEEPR_INSTALL_TEST_SCRIPT -Raw)
""",
            encoding="utf-8",
        )
        command = [shell, "-NoProfile", "-NonInteractive", "-File", str(wrapper)]
    else:
        wrapper = tmp_path / "missing-assets.sh"
        wrapper.write_text(
            """python3() {
    if [ "$1" = '-c' ] && [[ "$2" == *sys.implementation.name* ]]; then return 0; fi
    if [ "$1" = '-c' ]; then "$DEEPR_INSTALL_TEST_PYTHON" "$@"; return; fi
    printf '%s\\n' "$*" >> "$DEEPR_INSTALL_TEST_OPERATIONS"
}
command() {
    if [ "$1" = -v ]; then
        case "$2" in
            uv|python3|curl|grep) return 0 ;;
            *) return 1 ;;
        esac
    fi
    builtin command "$@"
}
uv() {
    printf 'uv %s\\n' "$*" >> "$DEEPR_INSTALL_TEST_OPERATIONS"
    if [ "$1" = --version ]; then printf 'uv 0.13.7\\n'; fi
    return 0
}
curl() { printf '%s' "$DEEPR_INSTALL_TEST_RELEASE"; }
source "$DEEPR_INSTALL_TEST_SCRIPT"
""",
            encoding="utf-8",
            newline="\n",
        )
        command = [shell, str(wrapper)]
    result = subprocess.run(command, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    output = result.stdout + result.stderr
    recorded = operations.read_text(encoding="utf-8") if operations.exists() else ""
    assert result.returncode != 0, output
    assert "Traceback" not in output
    assert "the latest GitHub release has no supported Deepr wheel asset." in output
    assert "No installation changes were made" in output or "No Deepr installation changes were made" in output
    assert "==> Done." not in output
    assert "tool install" not in recorded
    assert "python install" not in recorded


def test_release_checksums_use_gnu_format_and_skip_themselves(tmp_path: Path) -> None:
    wheel = tmp_path / "deepr_research-2.51.7-py3-none-any.whl"
    plugin = tmp_path / "deepr-agent-plugin-2.51.7.tar.gz"
    wheel.write_bytes(b"wheel-bytes")
    plugin.write_bytes(b"plugin-bytes")
    (tmp_path / "SHA256SUMS").write_text("stale\n", encoding="ascii")

    assert write_checksums_main([str(tmp_path)]) == 0
    text = (tmp_path / "SHA256SUMS").read_text(encoding="ascii")
    expected = [
        f"{hashlib.sha256(plugin.read_bytes()).hexdigest()}  {plugin.name}",
        f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}",
    ]
    assert text == "\n".join(expected) + "\n"
    assert checksum_lines(tmp_path) == expected
    assert "stale" not in text
    assert "SHA256SUMS" not in text


def test_release_checksums_reject_an_empty_directory(tmp_path: Path) -> None:
    assert write_checksums_main([str(tmp_path)]) == 1


def test_release_workflow_publishes_tag_assets_without_cancelling() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "release.yml"
    text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    steps = workflow["jobs"]["publish"]["steps"]
    uses = [step["uses"].split("@", 1)[0] for step in steps if "uses" in step]
    runs = "\n".join(step.get("run", "") for step in steps)

    trigger = workflow.get("on", workflow.get(True))
    assert trigger["push"]["tags"] == ["v*"]
    assert workflow["permissions"]["contents"] == "write"
    assert "concurrency" not in workflow
    assert "cancel-in-progress" not in text
    assert workflow["jobs"]["publish"]["timeout-minutes"] == 30
    assert uses == ["actions/checkout", "astral-sh/setup-uv"]
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in text
    assert "astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884" in text
    publish = steps[-1]["run"]
    assert "uv run python -m build" in runs
    assert "scripts/build_agent_plugin.py" in runs
    assert "scripts/write_release_checksums.py dist" in runs
    assert 'uv run python scripts/release_notes.py "$version" docs/CHANGELOG.md' in publish
    assert "gh release create" in publish
    assert "--notes-file" in publish
    assert "gh release upload" not in text
    assert "--clobber" not in text
    assert "GitHub immutable releases cannot take new assets." in publish
    assert "Push a new patch tag instead of uploading to ${tag}." in publish
    assert "SHA256SUMS" in runs
    assert "pypi.org" not in text.lower()
    assert "softprops/action-gh-release" not in text


def test_release_notes_use_the_version_section_and_stop_at_the_next_heading() -> None:
    changelog = (ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = release_notes_text(changelog, "2.51.9")

    assert notes.startswith("## [2.51.9]")
    assert "SHA256SUMS" in notes
    assert "README installer works again" in notes
    assert "v2.51.8 shipped without assets" in notes
    assert "\n## [2.51.8]" not in notes
    assert changelog_section(changelog, "v2.51.8") == release_notes_text(changelog, "2.51.8")
    older = release_notes_text(changelog, "2.51.8")
    assert older.startswith("## [2.51.8]")
    assert "\n## [2.51.7]" not in older


def test_release_notes_fall_back_when_the_section_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changelog = "## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n\nShipped.\n\n## [0.9.0] - 2025-01-01\n"
    assert changelog_section(changelog, "1.0.0") == "## [1.0.0] - 2026-01-01\n\nShipped.\n"
    assert changelog_section(changelog, "9.9.9") is None
    assert release_notes_text(changelog, "9.9.9") == fallback_summary("9.9.9")
    assert release_notes_text("no headings\n", "v1.2.3") == "Deepr 1.2.3. See docs/CHANGELOG.md.\n"

    missing = tmp_path / "missing.md"
    assert release_notes_main(["2.51.9", str(missing)]) == 0
    captured = capsys.readouterr()
    assert captured.out == fallback_summary("2.51.9")
    assert "Changelog not found" in captured.err

    present = tmp_path / "CHANGELOG.md"
    present.write_text(changelog, encoding="utf-8")
    assert release_notes_main(["9.9.9", str(present)]) == 0
    captured = capsys.readouterr()
    assert captured.out == fallback_summary("9.9.9")
    assert "using a short summary" in captured.err
    assert release_notes_main([]) == 2


def test_scripts_readme_uses_real_make_targets_from_repository_root() -> None:
    text = (ROOT / "scripts/README.md").read_text(encoding="utf-8")

    assert "make -f scripts/Makefile test" in text
    assert "make -f scripts/Makefile build" in text
    assert "make format" not in text
    assert "make typecheck" not in text
