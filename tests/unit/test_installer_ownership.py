"""Real shell entrypoints with all manager/network mutations replaced by shims."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.test_release_installers import _installer_shell

ROOT = Path(os.getenv("DEEPR_INSTALLER_TEST_SOURCE_ROOT", Path(__file__).parents[2]))
RELEASE = {
    "tag_name": "v9.9.9",
    "assets": [
        {
            "name": "deepr_research-9.9.9-py3-none-any.whl",
            "browser_download_url": "https://github.com/blisspixel/deepr/releases/download/v9.9.9/deepr_research-9.9.9-py3-none-any.whl",
        }
    ],
}

BASH = r"""
install_count=0
command() {
    if [ "$1" = -v ]; then
        case "$2" in
            uv|pipx) [ "$DEEPR_SHIM_OWNER" != missing ] || return 1; [ "$2:$DEEPR_SHIM_OWNER" != uv:fresh-pipx ] || return 1; [ "$2:$DEEPR_SHIM_OWNER" != pipx:pipx-module ] || return 1; printf '%s\n' "$2"; return ;;
            deepr) case "$DEEPR_SHIM_OWNER" in fresh-uv|fresh-pipx|missing) [ "$install_count" -gt 0 ] || return 1 ;; esac; if [ "$DEEPR_SHIM_OWNER" = shadow ]; then printf '/other/deepr\n'; else printf '%s/deepr\n' "$DEEPR_SHIM_BIN"; fi; return ;;
            python*) [ "$DEEPR_SHIM_OWNER" != uv-no-python ] || return 1; [ "$2" = python3 ] || return 1; printf 'python3\n'; return ;;
        esac
    fi
    builtin command "$@"
}
python3() {
    if [ "$1" = -m ]; then
        if [ "$2" = pipx ] && [ "$DEEPR_SHIM_OWNER" != missing ]; then shift 2; pipx "$@"; return; fi
        if [ "$2" = pip ]; then printf 'forbidden pip bootstrap\n' >> "$DEEPR_SHIM_LOG"; fi
        return 1
    fi
    case "$2" in
        *sys.version_info*) "$DEEPR_SHIM_PYTHON" -c '
import sys
from collections import namedtuple
from types import SimpleNamespace
version = namedtuple("Version", "major minor micro releaselevel serial")
host = sys.argv[2]
fake_sys = SimpleNamespace(executable="python", _base_executable="python", implementation=SimpleNamespace(name="cpython"), version_info=version(3, int(host) if host.isdigit() else 13, 0, "candidate" if host == "prerelease" else "final", 0))
exec(sys.argv[1].replace("import sys;", "", 1).replace("import sys", "", 1).strip(), {"sys": fake_sys})
' "$2" "$DEEPR_SHIM_HOST_PYTHON" ;;
        *_base_executable*) printf 'python3\n' ;;
        *) "$DEEPR_SHIM_PYTHON" "$@" ;;
    esac
}
uv() {
    if [ "$1 $2" = 'tool list' ]; then
        case "$DEEPR_SHIM_OWNER" in uv|uv-no-python|both) printf 'deepr-research v9.9.8\n';; esac
        return 0
    fi
    if [ "$1 $2" = 'tool dir' ]; then printf '%s\n' "$DEEPR_SHIM_BIN"; return; fi
    printf 'uv %s\n' "$*" >> "$DEEPR_SHIM_LOG"
    if [ "$1 $2" = 'python find' ]; then printf 'python3\n'; fi
    if [ "$1 $2" = 'tool install' ]; then install_count=$((install_count+1)); fi
}
pipx() {
    if [ "$1" = --version ]; then printf '1.17.2\n'; return 0; fi
    if [ "$1" = list ]; then
        case "$DEEPR_SHIM_OWNER" in pipx|pipx-module|py-only|shadow|both|unsupported|prerelease) printf 'package deepr-research 9.9.8\n';; esac
        return 0
    fi
    if [ "$1" = environment ]; then
        if [ "$3" = PIPX_LOCAL_VENVS ]; then
            [ "$DEEPR_SHIM_OWNED_PYTHON" != unreadable-root ] || return 2
            printf '/owned\n'
        else printf '%s\n' "$DEEPR_SHIM_BIN"; fi
        return
    fi
    printf 'pipx %s\n' "$*" >> "$DEEPR_SHIM_LOG"
    if [ "$1" = install ]; then install_count=$((install_count+1)); fi
}
/owned/deepr-research/bin/python() {
    [ "$DEEPR_SHIM_OWNED_PYTHON" != missing ] || return 127
    case "$2" in *sys.version_info*) ;; *) "$DEEPR_SHIM_PYTHON" "$@"; return ;; esac
    "$DEEPR_SHIM_PYTHON" -c '
import sys
from collections import namedtuple
from types import SimpleNamespace
version = namedtuple("Version", "major minor micro releaselevel serial")
owned = sys.argv[2]
fake_sys = SimpleNamespace(executable="/owned/python", _base_executable="owned-base-python", implementation=SimpleNamespace(name="pypy" if owned == "pypy" else "cpython"), version_info=version(3, int(owned) if owned.isdigit() else 13, 0, "candidate" if owned == "prerelease" else "final", 0))
exec(sys.argv[1].replace("import sys;", "", 1).replace("import sys", "", 1).strip(), {"sys": fake_sys})
' "$2" "$DEEPR_SHIM_OWNED_PYTHON"
}
curl() { printf 'release\n' >> "$DEEPR_SHIM_REQUEST_LOG"; printf '%s' "$DEEPR_SHIM_RELEASE"; }
deepr() {
    if [ "$DEEPR_SHIM_REPAIR" = true ] && [ "$install_count" -lt 2 ]; then return 7; fi
    printf 'deepr, version 9.9.9\n'
}
if [ "$DEEPR_SHIM_UNINSTALL" = true ]; then set -- --uninstall; else set --; fi
source "$DEEPR_SHIM_SCRIPT"
"""

POWERSHELL = r"""
$global:installCount = 0
function Get-Command {
    param($Name, $ErrorAction)
    if ($Name -in @('uv', 'pipx') -and $env:DEEPR_SHIM_OWNER -eq 'missing') { return $null }
    if ($Name -eq 'pipx' -and $env:DEEPR_SHIM_OWNER -eq 'pipx-module') { return $null }
    if ($Name -eq 'uv' -and $env:DEEPR_SHIM_OWNER -eq 'fresh-pipx') { return $null }
    if ($Name -eq 'deepr' -and $env:DEEPR_SHIM_OWNER -in @('fresh-uv', 'fresh-pipx', 'missing') -and $global:installCount -eq 0) { return $null }
    if ($Name -like 'python*' -and ($Name -ne 'python' -or $env:DEEPR_SHIM_OWNER -in @('uv-no-python', 'py-only'))) { return $null }
    if ($Name -eq 'py' -and $env:DEEPR_SHIM_OWNER -ne 'py-only') { return $null }
    if ($Name -eq 'deepr') {
        $source = if ($env:DEEPR_SHIM_OWNER -eq 'shadow') { '/other/deepr.exe' } else { Join-Path $env:DEEPR_SHIM_BIN 'deepr.exe' }
        return [pscustomobject]@{ Source = $source }
    }
    Microsoft.PowerShell.Core\Get-Command -Name $Name -ErrorAction SilentlyContinue
}
function python {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq '-m') {
        if ($args[1] -eq 'pipx' -and $env:DEEPR_SHIM_OWNER -ne 'missing') { $pipxArgs = @($args | Select-Object -Skip 2); pipx @pipxArgs; return }
        if ($args[1] -eq 'pip') { Add-Content -LiteralPath $env:DEEPR_SHIM_LOG -Value 'forbidden pip bootstrap' }
        $global:LASTEXITCODE = 1; return
    }
    if ($args[1] -like '*sys.version_info*') {
        $probe = @'
import sys
from collections import namedtuple
from types import SimpleNamespace
version = namedtuple('Version', 'major minor micro releaselevel serial')
host = sys.argv[2]
fake_sys = SimpleNamespace(executable='python', _base_executable='python', implementation=SimpleNamespace(name='cpython'), version_info=version(3, int(host) if host.isdigit() else 13, 0, 'candidate' if host == 'prerelease' else 'final', 0))
exec(sys.argv[1].replace('import sys;', '', 1).replace('import sys', '', 1).strip(), {'sys': fake_sys})
'@
        & $env:DEEPR_SHIM_PYTHON -c $probe $args[1] $env:DEEPR_SHIM_HOST_PYTHON
        return
    }
    if ($args[1] -like '*_base_executable*') { 'python'; return }
    & $env:DEEPR_SHIM_PYTHON @args
}
function py {
    if ($args[0] -ne '-3.15') { $global:LASTEXITCODE = 1; return }
    $probeArgs = @($args | Select-Object -Skip 1)
    python @probeArgs
}
function uv {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'tool' -and $args[1] -eq 'list') {
        if ($env:DEEPR_SHIM_OWNER -in @('uv', 'uv-no-python', 'both')) { 'deepr-research v9.9.8' }
        return
    }
    if ($args[0] -eq 'tool' -and $args[1] -eq 'dir') { $env:DEEPR_SHIM_BIN; return }
    Add-Content -LiteralPath $env:DEEPR_SHIM_LOG -Value ('uv ' + ($args -join ' '))
    if ($args[0] -eq 'tool' -and $args[1] -eq 'install') { $global:installCount += 1 }
}
function pipx {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq '--version') { '1.17.2'; return }
    if ($args[0] -eq 'list') {
        if ($env:DEEPR_SHIM_OWNER -in @('pipx', 'pipx-module', 'py-only', 'shadow', 'both', 'unsupported', 'prerelease')) { 'package deepr-research 9.9.8' }
        return
    }
    if ($args[0] -eq 'environment') {
        if ($args[2] -eq 'PIPX_LOCAL_VENVS') {
            if ($env:DEEPR_SHIM_OWNED_PYTHON -eq 'unreadable-root') { $global:LASTEXITCODE = 2; return }
            '/owned'
        } else { $env:DEEPR_SHIM_BIN }
        return
    }
    Add-Content -LiteralPath $env:DEEPR_SHIM_LOG -Value ('pipx ' + ($args -join ' '))
    if ($args[0] -eq 'install') { $global:installCount += 1 }
}
function OwnedPython {
    if ($env:DEEPR_SHIM_OWNED_PYTHON -eq 'missing') { $global:LASTEXITCODE = 127; return }
    $probe = @'
import sys
from collections import namedtuple
from types import SimpleNamespace
version = namedtuple('Version', 'major minor micro releaselevel serial')
owned = sys.argv[2]
fake_sys = SimpleNamespace(executable='/owned/python', _base_executable='owned-base-python', implementation=SimpleNamespace(name='pypy' if owned == 'pypy' else 'cpython'), version_info=version(3, int(owned) if owned.isdigit() else 13, 0, 'candidate' if owned == 'prerelease' else 'final', 0))
exec(sys.argv[1].replace('import sys;', '', 1).replace('import sys', '', 1).strip(), {'sys': fake_sys})
'@
    & $env:DEEPR_SHIM_PYTHON -c $probe $args[1] $env:DEEPR_SHIM_OWNED_PYTHON
}
Set-Alias -Name (Join-Path '/owned' 'deepr-research/Scripts/python.exe') -Value OwnedPython
function deepr {
    $global:LASTEXITCODE = 0
    if ($env:DEEPR_SHIM_REPAIR -eq 'true' -and $global:installCount -lt 2) { $global:LASTEXITCODE = 7; return }
    'deepr, version 9.9.9'
}
function Invoke-RestMethod { Add-Content -LiteralPath $env:DEEPR_SHIM_REQUEST_LOG -Value 'release'; $env:DEEPR_SHIM_RELEASE | ConvertFrom-Json }
$scriptText = Get-Content -LiteralPath $env:DEEPR_SHIM_SCRIPT -Raw
if ($env:DEEPR_SHIM_UNINSTALL -eq 'true') { & ([scriptblock]::Create($scriptText)) -Uninstall }
else { Invoke-Expression $scriptText }
"""


def run_installer(
    tmp_path,
    family,
    owner,
    *,
    repair=False,
    uninstall=False,
    release=RELEASE,
    script_root=ROOT,
    owned_python="13",
    host_python="13",
):
    suffix = "ps1" if family == "powershell" else "sh"
    wrapper = tmp_path / f"run.{suffix}"
    wrapper.write_text(POWERSHELL if family == "powershell" else BASH)
    log = tmp_path / "operations.txt"
    env = {
        **os.environ,
        "DEEPR_SHIM_OWNER": owner,
        "DEEPR_SHIM_OWNED_PYTHON": owned_python,
        "DEEPR_SHIM_HOST_PYTHON": host_python,
        "DEEPR_SHIM_BIN": str(tmp_path / "bin"),
        "DEEPR_SHIM_REPAIR": str(repair).lower(),
        "DEEPR_SHIM_UNINSTALL": str(uninstall).lower(),
        "DEEPR_SHIM_RELEASE": json.dumps(release),
        "DEEPR_SHIM_SCRIPT": str(script_root / "scripts" / f"install.{suffix}"),
        "DEEPR_SHIM_LOG": str(log),
        "DEEPR_SHIM_REQUEST_LOG": str(tmp_path / "release-requests.txt"),
        "DEEPR_SHIM_PYTHON": sys.executable,
    }
    shell = _installer_shell(family)
    args = (
        [shell, "-NoProfile", "-NonInteractive", "-File", str(wrapper)]
        if family == "powershell"
        else [shell, str(wrapper)]
    )
    result = subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False)
    return result, log.read_text(encoding="utf-8-sig").splitlines() if log.exists() else []


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize(
    "owner,expected",
    [
        ("uv", "uv"),
        ("uv-no-python", "uv"),
        ("pipx", "pipx"),
        ("pipx-module", "pipx"),
        ("py-only", "pipx"),
        ("fresh-uv", "uv"),
        ("fresh-pipx", "pipx"),
    ],
)
@pytest.mark.parametrize("repair", [False, True])
def test_installer_preserves_owner_and_pins_interpreter(tmp_path, family, owner, expected, repair):
    result, operations = run_installer(tmp_path, family, owner, repair=repair)
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [
        op for op in operations if " install " in op and ("tool install" in op or op.startswith("pipx install"))
    ]
    assert len(installs) == (2 if repair else 1), operations
    assert "--force" in installs[0].split(), installs
    if repair:
        assert "--force" not in installs[1].split(), installs
    assert all(op.startswith(expected) and "--python " in op for op in installs)
    if expected == "uv":
        assert all("--python 3.15 --managed-python" in op for op in installs)
    assert all(not op.startswith("pip ") for op in operations)
    assert all(op.startswith(expected) for op in operations)


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize("owner", ["both", "unknown", "shadow", "missing"])
def test_ambiguous_unmanaged_missing_manager_or_unsupported_python_refuses_without_mutation(tmp_path, family, owner):
    result, operations = run_installer(tmp_path, family, owner)
    assert result.returncode != 0, result.stdout + result.stderr
    assert operations == []
    assert "Done." not in result.stdout


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize("owner", ["uv", "pipx"])
def test_uninstall_uses_existing_owner_without_release_request_or_install(tmp_path, family, owner):
    result, operations = run_installer(tmp_path, family, owner, uninstall=True, release={})
    assert result.returncode == 0, result.stdout + result.stderr
    assert operations == [f"{owner} " + ("tool " if owner == "uv" else "") + "uninstall deepr-research"]


@pytest.mark.parametrize("family", ["bash", "powershell"])
def test_untrusted_wheel_refuses_before_tool_mutation(tmp_path, family):
    release = {
        "tag_name": "v9.9.9",
        "assets": [
            {
                "name": "deepr_research-9.9.9-py3-none-any.whl",
                "browser_download_url": "https://untrusted.example/wheel.whl",
            }
        ],
    }
    result, operations = run_installer(tmp_path, family, "uv", release=release)
    assert result.returncode != 0
    assert operations == []


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize("owned_python", ["10", "16", "prerelease", "pypy", "missing", "unreadable-root"])
def test_owned_pipx_runtime_refuses_before_mutation_despite_supported_path_python(tmp_path, family, owned_python):
    result, operations = run_installer(tmp_path, family, "pipx", owned_python=owned_python)
    assert result.returncode != 0, result.stdout + result.stderr
    assert operations == []
    assert "reinstall deepr-research --python" in result.stdout + result.stderr
    assert "rerun" in (result.stdout + result.stderr).lower()
    assert "Done." not in result.stdout
    assert not (tmp_path / "release-requests.txt").exists()


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize("owner", ["pipx", "pipx-module"])
def test_owned_pipx_refusal_guidance_uses_the_detected_manager_entrypoint(tmp_path, family, owner):
    result, operations = run_installer(tmp_path, family, owner, owned_python="16")
    assert result.returncode != 0
    assert operations == []
    output = result.stdout + result.stderr
    if family == "powershell":
        prefix = "& 'python' -m pipx" if owner == "pipx-module" else "pipx"
        expected = f"{prefix} reinstall deepr-research --python 'python'"
    else:
        prefix = "python3 -m pipx" if owner == "pipx-module" else "pipx"
        expected = f"{prefix} reinstall deepr-research --python python"
    assert expected in [line.strip() for line in output.splitlines()]


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize("owned_python", ["11", "12", "13", "14", "15"])
@pytest.mark.parametrize("repair", [False, True])
def test_supported_owned_pipx_runtime_keeps_its_base_interpreter(tmp_path, family, owned_python, repair):
    result, operations = run_installer(tmp_path, family, "pipx", owned_python=owned_python, repair=repair)
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [op for op in operations if op.startswith("pipx install ")]
    assert len(installs) == (2 if repair else 1)
    assert all("--python owned-base-python" in op for op in installs)


@pytest.mark.parametrize("family", ["bash", "powershell"])
def test_owned_pipx_uninstall_does_not_require_supported_runtime(tmp_path, family):
    result, operations = run_installer(tmp_path, family, "pipx", owned_python="missing", uninstall=True, release={})
    assert result.returncode == 0, result.stdout + result.stderr
    assert operations == ["pipx uninstall deepr-research"]


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize("owner", ["pipx", "pipx-module"])
@pytest.mark.parametrize("owned_python", ["11", "12", "13", "14", "15"])
@pytest.mark.parametrize("host_python", ["10", "16", "prerelease"])
@pytest.mark.parametrize("repair", [False, True])
def test_supported_owned_pipx_runtime_works_without_a_supported_path_python(
    tmp_path, family, owner, owned_python, host_python, repair
):
    result, operations = run_installer(
        tmp_path, family, owner, owned_python=owned_python, host_python=host_python, repair=repair
    )
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [op for op in operations if op.startswith("pipx install ")]
    assert len(installs) == (2 if repair else 1)
    assert all("--python owned-base-python" in op for op in installs)


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize("owner", ["pipx", "pipx-module"])
@pytest.mark.parametrize("owned_python", ["10", "16", "missing", "unreadable-root"])
@pytest.mark.parametrize("host_python", ["10", "16", "prerelease"])
def test_unsupported_owned_and_path_python_refuses_with_explicit_repair_guidance(
    tmp_path, family, owner, owned_python, host_python
):
    result, operations = run_installer(tmp_path, family, owner, owned_python=owned_python, host_python=host_python)
    assert result.returncode != 0, result.stdout + result.stderr
    assert operations == []
    assert not (tmp_path / "release-requests.txt").exists()
    output = result.stdout + result.stderr
    assert "reinstall deepr-research --python" in output
    assert "3.11, 3.12, 3.13, 3.14 or 3.15" in output
    assert "rerun" in output.lower()
    assert "Done." not in output


@pytest.mark.parametrize("family", ["bash", "powershell"])
@pytest.mark.parametrize("host_python", ["10", "16", "prerelease"])
def test_fresh_pipx_requires_a_supported_path_python(tmp_path, family, host_python):
    result, operations = run_installer(tmp_path, family, "fresh-pipx", host_python=host_python)
    assert result.returncode != 0, result.stdout + result.stderr
    assert operations == []
    assert not (tmp_path / "release-requests.txt").exists()
