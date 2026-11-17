"""Reject MCP tool calls that cannot run before asking for confirmation.

Lookup and the existing argument checks happen first. Confirmation is asked
only after the tool is registered and those checks pass (#349).
"""

from __future__ import annotations

import json
from typing import Any

from deepr.mcp.metered_contract import MeteredMCPContractError, require_metered_api_contract
from deepr.mcp.runtime_registry import create_runtime_registry
from deepr.mcp.tool_errors import make_tool_error

_JOB_ID_TOOLS = frozenset({"deepr_cancel_job", "deepr_check_status", "deepr_get_result"})
_REPORT_ID_TOOLS = frozenset({"deepr_reflect", "deepr_expert_absorb"})
_METERED_CONTRACT_TOOLS = frozenset({"deepr_research", "deepr_expert_validate", "deepr_expert_absorb"})


def known_tool_names() -> frozenset[str]:
    """Return the registered tool names the stdio dispatcher can run."""
    return frozenset(tool.name for tool in create_runtime_registry().all_tools())


def unknown_tool_response(name: str) -> dict[str, Any] | None:
    """Return TOOL_NOT_FOUND when the name is not a registered tool."""
    if name in known_tool_names():
        return None
    error = make_tool_error("TOOL_NOT_FOUND", f"Unknown tool: {name}")
    return _error_result(error, structured=True)


def invalid_argument_response(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Return a validation error for a call that cannot run.

    A contract-valid metered call returns None so the confirmation gate still
    runs before the handler. An invalid contract returns the same error the
    handler would return, without asking for approval.
    """
    if name in _JOB_ID_TOOLS and not arguments.get("job_id"):
        error = make_tool_error("INVALID_PARAMS", "job_id is required and must not be empty")
        return _error_result(error, structured=False)
    # An empty report id used to reach a prefix lookup and match an arbitrary report.
    if name in _REPORT_ID_TOOLS and not str(arguments.get("report_id") or "").strip():
        error = make_tool_error("INVALID_PARAMS", "report_id is required and must not be empty")
        return _error_result(error, structured=True)
    contract_error = _metered_contract_error(name, arguments)
    if contract_error is not None:
        return _error_result(contract_error, structured=True)
    return None


def _metered_contract_error(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    if name not in _METERED_CONTRACT_TOOLS:
        return None
    try:
        require_metered_api_contract(
            budget=arguments.get("budget"),
            allow_metered_api=arguments.get("allow_metered_api", False),
            confirm_metered_cost=arguments.get("confirm_metered_cost", False),
        )
    except MeteredMCPContractError as exc:
        return make_tool_error(exc.code, str(exc))
    return None


def _error_result(error: dict[str, Any], *, structured: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": json.dumps(error)}],
        "isError": True,
    }
    if structured:
        result["structuredContent"] = error
    return result
