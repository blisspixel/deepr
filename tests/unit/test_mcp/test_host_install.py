"""Unit tests for local coding-host MCP install helpers."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from deepr.cli.commands.mcp import mcp
from deepr.mcp.host_install import (
    HOST_BRIEF_SCHEMA,
    HOST_INSTALL_SCHEMA,
    build_host_brief,
    build_mcp_json_document,
    build_server_spec,
    plan_host_install,
    probe_project_mcp_json,
    write_mcp_json,
)


def test_build_server_spec_sets_data_dir_and_serve_args(tmp_path: Path) -> None:
    data = tmp_path / "deepr-home"
    data.mkdir()
    deepr_bin = tmp_path / "deepr.exe"
    deepr_bin.write_text("", encoding="utf-8")
    spec = build_server_spec(
        deepr_command=str(deepr_bin),
        data_dir=str(data),
        use_python_module=False,
    )
    assert spec.args == ["mcp", "serve"]
    assert spec.env["DEEPR_DATA_DIR"] == str(data.resolve())
    assert "DEEPR_LOG_LEVEL" in spec.env
    add_argv = spec.as_claude_mcp_add_argv()
    assert add_argv[:4] == ["mcp", "add", "deepr", "-s"]
    assert "local" in add_argv
    assert "--" in add_argv
    assert str(deepr_bin.resolve()) in add_argv


def test_write_mcp_json_merges_existing_servers(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    existing = project / ".mcp.json"
    existing.write_text(
        json.dumps({"mcpServers": {"other": {"command": "echo", "args": []}}}),
        encoding="utf-8",
    )
    plan = plan_host_install(
        project_dir=project,
        deepr_command=str(tmp_path / "deepr"),
        data_dir=str(tmp_path / "data"),
        use_python_module=False,
    )
    # ensure parent of command exists for resolve
    Path(plan.deepr_command).write_text("", encoding="utf-8")
    plan = plan_host_install(
        project_dir=project,
        deepr_command=str(tmp_path / "deepr"),
        data_dir=str(tmp_path / "data"),
        use_python_module=False,
    )
    write_mcp_json(plan, merge=True)
    doc = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
    assert "other" in doc["mcpServers"]
    assert "deepr" in doc["mcpServers"]
    assert doc["mcpServers"]["deepr"]["args"] == ["mcp", "serve"]


def test_build_host_brief_includes_restart_and_local_rules() -> None:
    text = build_host_brief(
        experts=["Meshtastic LoRa Mesh Automation"],
        data_dir="C:/Users/nicks/.deepr",
    )
    assert HOST_BRIEF_SCHEMA in text or "deepr-mcp-host-brief-v1" in text
    assert "Restart" in text or "restart" in text
    assert 'synthesis_backend="local"' in text
    assert "budget=0" in text
    assert "Meshtastic LoRa Mesh Automation" in text
    assert "CLI fallback" in text
    assert "deepr mcp install-host" in text


def test_probe_project_mcp_json_missing(tmp_path: Path) -> None:
    probe = probe_project_mcp_json(tmp_path)
    assert probe["present"] is False
    assert probe["has_server"] is False
    assert probe["cost_usd"] == 0.0


def test_install_host_dry_run_cli(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    deepr_bin = tmp_path / "deepr"
    deepr_bin.write_text("", encoding="utf-8")
    result = CliRunner().invoke(
        mcp,
        [
            "install-host",
            "--project",
            str(project),
            "--deepr-command",
            str(deepr_bin),
            "--data-dir",
            str(tmp_path / "home"),
            "--dry-run",
            "--skip-claude-cli",
            "--no-brief",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == HOST_INSTALL_SCHEMA
    assert payload["dry_run"] is True
    assert payload["wrote_mcp_json"] is False
    assert payload["cost_usd"] == 0.0
    assert not (project / ".mcp.json").exists()


def test_install_host_writes_mcp_json(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    deepr_bin = tmp_path / "deepr"
    deepr_bin.write_text("", encoding="utf-8")
    data = tmp_path / "home"
    data.mkdir()
    result = CliRunner().invoke(
        mcp,
        [
            "install-host",
            "--project",
            str(project),
            "--deepr-command",
            str(deepr_bin),
            "--data-dir",
            str(data),
            "--skip-claude-cli",
            "--no-brief",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Restart the host session" in result.output
    doc = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
    assert "deepr" in doc["mcpServers"]
    assert doc["mcpServers"]["deepr"]["env"]["DEEPR_DATA_DIR"] == str(data.resolve())


def test_host_brief_cli_json() -> None:
    result = CliRunner().invoke(
        mcp,
        ["host-brief", "--expert", "NephMesh Hybrid Resilient Comms", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == HOST_BRIEF_SCHEMA
    assert payload["cost_usd"] == 0.0
    assert "NephMesh Hybrid Resilient Comms" in payload["brief"]


def test_build_mcp_json_document_shape() -> None:
    spec = build_server_spec(
        deepr_command="C:/tools/deepr.exe",
        data_dir="C:/data/deepr",
        use_python_module=False,
    )
    doc = build_mcp_json_document(spec)
    assert set(doc.keys()) == {"mcpServers"}
    assert "deepr" in doc["mcpServers"]
