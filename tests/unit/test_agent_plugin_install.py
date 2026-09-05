"""Regressions for manifest-driven installed Agent Plugin launches."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location(
        "agent_plugin_install_check", ROOT / "scripts/check_agent_plugin_install.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def installation(tmp_path):
    package = tmp_path / "installed plugin"
    shutil.copytree(ROOT / "packages/deepr-agent-plugin", package)
    data = tmp_path / "persistent plugin data"
    data.mkdir()
    executable = tmp_path / "runtime with spaces" / ("deepr-mcp.exe" if os.name == "nt" else "deepr-mcp")
    executable.parent.mkdir()
    executable.write_bytes(b"fixture executable is resolved but never run\n")
    executable.chmod(0o755)
    return package, data, executable


def test_launch_uses_declared_cwd_and_preserves_argument_tokens(checker, installation):
    package, data, executable = installation
    working = data / "declared working directory"
    working.mkdir()
    manifest_path = package / "mcp.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    server = manifest["mcpServers"]["deepr"]
    server["cwd"] = "${PLUGIN_DATA}/declared working directory"
    server["args"] = ["--data", "${PLUGIN_DATA}/two words", "literal argument"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    command, cwd, environment = checker._plugin_launch(package, data, executable)

    assert Path(command[0]) == executable
    assert command[1:] == ["--data", f"{data}/two words", "literal argument"]
    assert cwd == working
    assert Path(environment["PATH"].split(os.pathsep)[0]) == executable.parent


def test_launch_sets_client_owned_variables_and_omits_credentials(checker, installation, monkeypatch):
    package, data, executable = installation
    monkeypatch.setenv("OPENROUTER_API_KEY", "inherited-secret-must-not-reach-child")
    monkeypatch.setenv("PLUGIN_ROOT", "wrong inherited root")
    monkeypatch.setenv("PLUGIN_DATA", "wrong inherited data")

    _, _, environment = checker._plugin_launch(package, data, executable)

    assert environment["PLUGIN_ROOT"] == str(package)
    assert environment["PLUGIN_DATA"] == str(data)
    assert "OPENROUTER_API_KEY" not in environment
    assert Path(environment["DEEPR_EXPERTS_PATH"]) == data / "deepr/experts"


def test_launch_does_not_bypass_an_unresolvable_manifest_command(checker, installation):
    package, data, executable = installation
    manifest_path = package / "mcp.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mcpServers"]["deepr"]["command"] = "missing-deepr-plugin-executable-73281"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="manifest command did not resolve"):
        checker._plugin_launch(package, data, executable)


def test_launch_refuses_a_different_runtime_on_the_search_path(checker, installation):
    package, data, executable = installation
    other = executable.with_name("other-runtime.exe" if os.name == "nt" else "other-runtime")
    other.write_bytes(b"wrong runtime\n")
    other.chmod(0o755)
    manifest_path = package / "mcp.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mcpServers"]["deepr"]["command"] = other.name
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="manifest command did not resolve"):
        checker._plugin_launch(package, data, executable)
