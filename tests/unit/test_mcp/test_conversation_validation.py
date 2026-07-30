"""Acceptance-harness tests for durable MCP expert conversations."""

from __future__ import annotations

import socket
from typing import Any

import aiohttp
import pytest

from deepr.mcp import conversation_validation
from deepr.mcp.conversation_validation import (
    MCPConversationValidationCheck,
    MCPConversationValidationReport,
    _validate_local_contract,
    assert_secret_redaction,
    run_http_conversation_validation,
)
from deepr.mcp.conversation_validation_managed import (
    run_managed_loopback_conversation_validation,
)


def _operation(
    operation: str,
    *,
    version: int,
    ordinal: int,
    replayed: bool = False,
    closed: bool = False,
    purged: bool = False,
) -> dict[str, Any]:
    prior_ids = ["turn_first"] if ordinal == 2 else []
    turn_id = "turn_first" if ordinal == 1 else "turn_second"
    return {
        "schema_version": "deepr-expert-conversation-operation-v1",
        "kind": "deepr.expert.conversation_operation",
        "operation": operation,
        "conversation": {
            "conversation_id": "conv_AAAAAAAAAAAAAAAAAAAAAA",
            "state": "closed" if closed else "open",
            "version": version,
            "expert_names": ["Reliability Engineering"],
            "backend": {
                "capacity_source": "local_owned",
                "backend_class": "local",
                "model": "fixture-local-model",
                "fallback_policy": "none",
                "live_metered_fallback": False,
            },
            "bounds": {"max_cost_usd": 0.0},
            "usage": {"cost_usd": 0.0},
            "retention": {"content_deleted": purged},
        },
        "turn": {
            "turn_id": turn_id,
            "ordinal": ordinal,
            "state": "completed",
            "request": {"content_available": not purged},
            "context": {"recent_turn_ids": prior_ids},
            "artifact_available": not purged,
            "artifact": None if purged else {"direct_answer": "A verified answer."},
            "artifact_sha256": ("a" if ordinal == 1 else "b") * 64,
        },
        "replayed": replayed,
        "dispatch_status": "completed",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/mcp/", "https://mcp.example.com/mcp"])
async def test_http_conversation_validation_blocks_before_client_construction(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda *args, **kwargs: pytest.fail("remote client must not be constructed"),
    )

    report = await run_http_conversation_validation(
        url,
        auth_token="secret-token",
        expert="Reliability Engineering",
        local_model="fixture-local-model",
        timeout_seconds=2.0,
    )

    payload = report.to_dict()
    assert report.ok is False
    assert report.error["error_code"] == "MCP_HTTP_CONVERSATION_VALIDATION_BLOCKED"
    assert payload["capacity_source"] == "unverified"
    assert payload["fallback_policy"] == "unverified"
    assert payload["live_metered_fallback"] is None
    assert payload["remote_tool_call_attempted"] is False
    assert payload["remote_tool_calls_metered_api"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0.0, -1.0, 301.0])
async def test_http_conversation_validation_rejects_timeout_before_client(
    timeout: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda *args, **kwargs: pytest.fail("remote client must not be constructed"),
    )

    report = await run_http_conversation_validation(
        "https://mcp.example.com/mcp",
        timeout_seconds=timeout,
    )

    assert report.ok is False
    assert report.error["error_code"] == "INVALID_HTTP_PREFLIGHT"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, "0", None, True])
@pytest.mark.parametrize("location", ["bounds", "usage"])
def test_conversation_validation_rejects_invalid_zero_cost_fields(location: str, value: Any) -> None:
    payload = _operation("start", version=2, ordinal=1)
    conversation = payload["conversation"]
    turn = payload["turn"]
    if location == "bounds":
        conversation["bounds"]["max_cost_usd"] = value
    else:
        conversation["usage"]["cost_usd"] = value

    with pytest.raises(conversation_validation.ConversationValidationFailure) as exc_info:
        _validate_local_contract(conversation, turn)

    assert exc_info.value.code in {"NONZERO_COST_CEILING", "NONZERO_RECORDED_COST"}


def test_secret_redaction_rejects_echo() -> None:
    with pytest.raises(conversation_validation.ConversationValidationFailure, match="echoed"):
        assert_secret_redaction(["response has private-token"], ("private-token",))


def test_failed_check_marks_conversation_report_failed() -> None:
    report = MCPConversationValidationReport(
        mode="http",
        endpoint="http://localhost/mcp",
        checks=(MCPConversationValidationCheck("x", "failed", "bad"),),
    )

    assert report.ok is False
    assert report.to_dict()["ok"] is False


@pytest.mark.asyncio
async def test_managed_loopback_validation_blocks_before_server_or_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "socket",
        lambda *_args, **_kwargs: pytest.fail("managed server socket must not be constructed"),
    )
    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda *_args, **_kwargs: pytest.fail("managed HTTP client must not be constructed"),
    )

    def fail_executor() -> Any:
        pytest.fail("managed executor must not be constructed")

    report = await run_managed_loopback_conversation_validation(
        expert="reliability_engineering",
        local_model="fixture-local-model",
        timeout_seconds=10.0,
        executor_factory=fail_executor,
    )

    payload = report.to_dict()
    assert report.ok is False
    assert report.endpoint is None
    assert report.error["error_code"] == "MCP_MANAGED_CONVERSATION_VALIDATION_BLOCKED"
    assert payload["capacity_source"] == "unverified"
    assert payload["fallback_policy"] == "unverified"
    assert payload["live_metered_fallback"] is None
    assert payload["remote_tool_call_attempted"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0.0, -1.0, 301.0])
async def test_managed_loopback_rejects_timeout_before_server_start(
    timeout: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        socket,
        "socket",
        lambda *_args, **_kwargs: pytest.fail("managed server socket must not be constructed"),
    )
    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda *_args, **_kwargs: pytest.fail("managed HTTP client must not be constructed"),
    )

    report = await run_managed_loopback_conversation_validation(timeout_seconds=timeout)

    assert report.ok is False
    assert report.error["error_code"] == "INVALID_TIMEOUT"
