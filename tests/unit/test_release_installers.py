"""Regression checks for the public GitHub Releases install channel."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
        "tag_name": "v2.50.12",
        "assets": [
            {
                "name": "deepr_research-2.50.12-py3-none-any.whl",
                "browser_download_url": (
                    "https://github.com/blisspixel/deepr/releases/download/"
                    "v2.50.12/deepr_research-2.50.12-py3-none-any.whl"
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
function deepr {
    if ($env:DEEPR_INSTALL_TEST_BEHAVIOR -eq 'stays_broken' -or
        ($env:DEEPR_INSTALL_TEST_BEHAVIOR -eq 'repair_works' -and $global:installCount -lt 2)) {
        $global:LASTEXITCODE = 7
        return
    }
    $global:LASTEXITCODE = 0
    'deepr, version 2.50.12'
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
curl() { printf '%s' "$DEEPR_INSTALL_TEST_RELEASE"; }
deepr() {
    if [ "$DEEPR_INSTALL_TEST_BEHAVIOR" = stays_broken ] ||
       { [ "$DEEPR_INSTALL_TEST_BEHAVIOR" = repair_works ] && [ "$install_count" -lt 2 ]; }; then
        return 7
    fi
    printf 'deepr, version 2.50.12\\n'
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
        assert "deepr, version 2.50.12" in output


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


def test_windows_installer_bootstraps_when_pipx_probe_raises() -> None:
    text = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")

    assert "function Test-PipxAvailable($PythonCommand)" in text
    assert "& $PythonCommand -m pipx --version *> $null" in text
    assert "catch {" in text
    assert "return $false" in text
    assert "if (-not (Test-PipxAvailable $python))" in text


def test_makefile_exposes_only_explicit_manual_pypi_publication() -> None:
    text = (ROOT / "scripts/Makefile").read_text(encoding="utf-8")

    assert "publish-pypi-manual:" in text
    assert "\npublish:" not in text
    assert "GitHub Releases is the current release channel" in text


def test_scripts_readme_uses_real_make_targets_from_repository_root() -> None:
    text = (ROOT / "scripts/README.md").read_text(encoding="utf-8")

    assert "make -f scripts/Makefile test" in text
    assert "make -f scripts/Makefile build" in text
    assert "make format" not in text
    assert "make typecheck" not in text
