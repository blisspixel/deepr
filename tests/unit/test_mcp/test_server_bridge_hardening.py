"""Focused regressions for the policy-aware MCP stdio bridge."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from deepr.mcp.security.tool_allowlist import ResearchMode
from deepr.mcp.server import DeeprMCPServer, _handle_tools_call, _handle_tools_list


@pytest.fixture
def read_only_server(monkeypatch: pytest.MonkeyPatch) -> DeeprMCPServer:
    monkeypatch.setenv("DEEPR_RESEARCH_MODE", "read_only")
    with (
        patch("deepr.mcp.server.ExpertStore") as expert_store,
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler") as resource_handler,
        patch("deepr.mcp.server.TaskDurabilityManager"),
        patch("deepr.mcp.server.OutputVerifier"),
    ):
        resource_handler.return_value.jobs.list_jobs.return_value = []
        server = DeeprMCPServer()
    expert_store.return_value.list_all.return_value = []
    return server


def test_console_script_targets_stdout_clean_server_main() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    project = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["scripts"]["deepr-mcp"] == "deepr.mcp.server:main"


@pytest.mark.parametrize("value", ["", "READ_ONLY", " read_only", "read_only ", "unknown"])
def test_explicit_invalid_mode_fails_before_state_initialization(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("DEEPR_RESEARCH_MODE", value)
    with (
        patch("deepr.mcp.server.ExpertStore") as expert_store,
        patch("deepr.mcp.server.load_config") as load_config,
        pytest.raises(ValueError, match="DEEPR_RESEARCH_MODE must be one of"),
    ):
        DeeprMCPServer()

    expert_store.assert_not_called()
    load_config.assert_not_called()


def test_unset_mode_preserves_standard_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_RESEARCH_MODE", raising=False)
    with (
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler"),
        patch("deepr.mcp.server.TaskDurabilityManager"),
        patch("deepr.mcp.server.OutputVerifier"),
    ):
        server = DeeprMCPServer()

    assert server.tool_allowlist.mode is ResearchMode.STANDARD


@pytest.mark.asyncio
async def test_read_only_discovery_uses_effective_registered_surface(
    read_only_server: DeeprMCPServer,
) -> None:
    registered = {tool.name for tool in read_only_server.registry.all_tools()}
    available = read_only_server.available_tool_names()

    assert len(registered) == 36
    assert {
        "deepr_get_task_progress",
        "deepr_list_recoverable_tasks",
        "deepr_pause_task",
        "deepr_resume_task",
    } <= registered
    assert available <= registered
    assert len(available) == 10
    assert "deepr_research" not in available
    assert {"deepr_pause_task", "deepr_resume_task"}.isdisjoint(available)

    full_list = await _handle_tools_list(read_only_server, {"_fullList": True})
    assert {tool["name"] for tool in full_list["tools"]} == available

    search = await read_only_server.deepr_tool_search("autonomous agentic research", limit=10)
    assert {tool["name"] for tool in search["tools"]} <= available
    assert search["total_available"] == len(available)

    capabilities = await read_only_server.deepr_capabilities()
    assert {tool["tool"] for tool in capabilities["tools"]} <= available

    with patch(
        "deepr.mcp.server.current_cost_status",
        return_value=("healthy", {"accounting_status": "known"}),
    ):
        status = await read_only_server.deepr_status()

    assert status["capabilities"]["tools"] == len(available)
    assert status["security"]["allowed_tools"] == len(available)
    assert status["security"]["blocked_tools"] == len(registered - available)
    assert status["security"]["tools_requiring_confirmation"] == 0


@pytest.mark.asyncio
async def test_read_only_block_precedes_caller_and_environment_approval(
    monkeypatch: pytest.MonkeyPatch,
    read_only_server: DeeprMCPServer,
) -> None:
    monkeypatch.setenv("DEEPR_MCP_AUTO_APPROVE", "1")
    read_only_server.deepr_research = AsyncMock()

    result = await _handle_tools_call(
        read_only_server,
        {
            "name": "deepr_research",
            "arguments": {
                "prompt": "must remain blocked",
                "budget": 1.0,
                "allow_metered_api": True,
                "confirm_metered_cost": True,
                "_approved": True,
            },
        },
    )

    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"])["error_code"] == "TOOL_BLOCKED"
    read_only_server.deepr_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_approve_zero_does_not_approve_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    read_only_server: DeeprMCPServer,
) -> None:
    monkeypatch.setenv("DEEPR_MCP_AUTO_APPROVE", "0")
    read_only_server.tool_allowlist.mode = ResearchMode.STANDARD
    read_only_server.deepr_research = AsyncMock()

    result = await _handle_tools_call(
        read_only_server,
        {
            "name": "deepr_research",
            "arguments": {
                "prompt": "must require confirmation",
                "budget": 1.0,
                "allow_metered_api": True,
                "confirm_metered_cost": True,
            },
        },
    )

    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"])["error_code"] == "CONFIRMATION_REQUIRED"
    read_only_server.deepr_research.assert_not_awaited()


def _subprocess_environment(data_root: Path, *, mode: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DEEPR_RESEARCH_MODE": mode,
            "DEEPR_MCP_AUTO_APPROVE": "1",
            "DEEPR_LOG_LEVEL": "WARNING",
            "DEEPR_DATA_DIR": str(data_root),
            "DEEPR_EXPERTS_PATH": str(data_root / "experts"),
            "DEEPR_REPORTS_PATH": str(data_root / "reports"),
            "DEEPR_COST_DATA_DIR": str(data_root / "costs"),
            "DEEPR_BUDGET_FILE": str(data_root / "budget.json"),
            "DEEPR_MAX_COST_PER_JOB": "0",
            "DEEPR_MAX_COST_PER_DAY": "0",
            "DEEPR_MAX_COST_PER_WEEK": "0",
            "DEEPR_MAX_COST_PER_MONTH": "0",
        }
    )
    return environment


def test_stdio_entrypoint_emits_only_json_and_blocks_approved_write(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "bridge-test", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_fullList": True}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "deepr_research",
                "arguments": {
                    "prompt": "must remain blocked",
                    "budget": 1.0,
                    "allow_metered_api": True,
                    "confirm_metered_cost": True,
                    "_approved": True,
                },
            },
        },
    ]
    completed = subprocess.run(
        [sys.executable, "-c", "from deepr.mcp.server import main; main()"],
        input="".join(f"{json.dumps(request)}\n" for request in requests),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=_subprocess_environment(data_root, mode="read_only"),
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line]
    assert [response["id"] for response in responses] == [1, 2, 3]
    advertised = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert "deepr_research" not in advertised
    blocked = json.loads(responses[2]["result"]["content"][0]["text"])
    assert blocked["error_code"] == "TOOL_BLOCKED"


def test_invalid_mode_subprocess_creates_no_server_state(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    completed = subprocess.run(
        [sys.executable, "-c", "from deepr.mcp.server import main; main()"],
        input="",
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=_subprocess_environment(data_root, mode="READ_ONLY"),
        timeout=30,
        check=False,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "DEEPR_RESEARCH_MODE must be one of" in completed.stderr
    assert not data_root.exists()


def test_stdio_module_import_does_not_require_optional_document_or_cloud_extras(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    code = (
        "import sys; "
        "sys.modules['docx'] = None; "
        "sys.modules['azure'] = None; "
        "import deepr.mcp.server; "
        "print('imported')"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=_subprocess_environment(data_root, mode="read_only"),
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "imported\n"
