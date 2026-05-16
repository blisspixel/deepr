"""Test that the MCP confirmation gate strips ``_approved`` from arguments
before dispatching, so handlers without that kwarg don't crash with
``TypeError``.

Regression coverage for the v2.10.2 confirmation-gate fix.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_approved_kwarg_is_stripped_before_handler_dispatch():
    """The dispatch table uses ``**args``; passing ``_approved=True``
    through would raise ``TypeError`` because handlers like
    ``deepr_research`` don't declare ``_approved`` in their signature."""
    from deepr.mcp import server as server_module

    # Build a minimal server stub with the methods the dispatch table
    # references. Track the kwargs each handler receives so we can assert
    # ``_approved`` did not leak.
    handler_calls: dict[str, dict] = {}

    async def fake_deepr_research(**kwargs):
        handler_calls["deepr_research"] = kwargs
        return {"result": "ok"}

    fake_server = MagicMock()
    fake_server.deepr_research = AsyncMock(side_effect=fake_deepr_research)
    fake_server.deepr_status = AsyncMock(return_value={})
    fake_server.deepr_check_status = AsyncMock(return_value={})
    fake_server.deepr_get_result = AsyncMock(return_value={})
    fake_server.deepr_agentic_research = AsyncMock(return_value={})
    fake_server.list_experts = AsyncMock(return_value=[])
    fake_server.query_expert = AsyncMock(return_value={})
    fake_server.get_expert_info = AsyncMock(return_value={})
    fake_server.expert_manifest = AsyncMock(return_value={})
    fake_server.rank_gaps = AsyncMock(return_value={})
    fake_server.deepr_cancel_job = AsyncMock(return_value={})
    fake_server.deepr_tool_search = AsyncMock(return_value={})
    fake_server.deepr_get_task_progress = AsyncMock(return_value={})
    fake_server.deepr_list_recoverable_tasks = AsyncMock(return_value={})
    fake_server.deepr_resume_task = AsyncMock(return_value={})
    fake_server.deepr_pause_task = AsyncMock(return_value={})
    # Instruction signer (required by gate path)
    fake_server.instruction_signer = MagicMock()
    fake_server.instruction_signer.sign = MagicMock(return_value=MagicMock(nonce="test-nonce"))

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "deepr_research",
            "arguments": {
                "prompt": "test prompt",
                "model": "gpt-5",
                "budget": 5.0,
                "_approved": True,  # The token the gate checks
            },
        },
    }

    # Force UNRESTRICTED mode so the confirmation gate path isn't taken,
    # OR auto-approve so _approved IS the relevant arg-stripping path.
    with patch.dict("os.environ", {"DEEPR_MCP_AUTO_APPROVE": "1"}):
        response = await server_module._handle_tools_call(fake_server, request["params"])

    # The handler was called and ``_approved`` was NOT passed through.
    assert "deepr_research" in handler_calls
    assert "_approved" not in handler_calls["deepr_research"]
    assert handler_calls["deepr_research"]["prompt"] == "test prompt"

    # The response is not an error.
    assert response.get("isError") is not True
