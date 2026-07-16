"""Acceptance-harness tests for durable MCP expert conversations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from deepr.mcp import conversation_validation
from deepr.mcp.conversation_validation import (
    CONVERSATION_TOOL_NAMES,
    MCPConversationValidationCheck,
    MCPConversationValidationReport,
    assert_secret_redaction,
    run_http_conversation_validation,
)
from deepr.mcp.conversation_validation_managed import (
    run_managed_loopback_conversation_validation,
)
from deepr.mcp.transport.http import HttpMessage
from tests.unit.conversation_fixtures import CompletingExecutor, expert_snapshot


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


class _FakeConversationHttpClient:
    instances: list[_FakeConversationHttpClient] = []

    def __init__(self, base_url: str, timeout: float = 30.0, auth_token: str | None = None) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.auth_token = auth_token
        self.sent: list[HttpMessage] = []
        self.disconnected = False
        self.start_calls = 0
        self.continue_calls = 0
        _FakeConversationHttpClient.instances.append(self)

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        self.disconnected = True

    async def send(self, message: HttpMessage) -> HttpMessage:
        self.sent.append(message)
        if message.method == "initialize":
            return HttpMessage(id=message.id, result={"serverInfo": {"name": "deepr"}})
        if message.method == "tools/list":
            return HttpMessage(
                id=message.id,
                result={"tools": [{"name": name} for name in CONVERSATION_TOOL_NAMES]},
            )
        assert message.method == "tools/call"
        assert isinstance(message.params, dict)
        name = message.params["name"]
        if name == "deepr_start_expert_conversation":
            self.start_calls += 1
            payload = _operation("start", version=2, ordinal=1, replayed=self.start_calls == 2)
        elif name == "deepr_get_expert_conversation":
            payload = _operation("get", version=2, ordinal=1)
        elif name == "deepr_continue_expert_conversation":
            self.continue_calls += 1
            payload = _operation("continue", version=4, ordinal=2, replayed=self.continue_calls == 2)
        elif name == "deepr_close_expert_conversation":
            payload = _operation("close", version=6, ordinal=2, closed=True, purged=True)
        else:
            raise AssertionError(f"unexpected tool {name}")
        return HttpMessage(
            id=message.id,
            result={
                "content": [{"type": "text", "text": json.dumps(payload)}],
                "structuredContent": payload,
                "isError": False,
            },
        )


@pytest.mark.asyncio
async def test_http_conversation_validation_runs_full_remote_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeConversationHttpClient.instances = []
    monkeypatch.setattr(conversation_validation, "HttpClient", _FakeConversationHttpClient)

    report = await run_http_conversation_validation(
        "http://127.0.0.1:8765/mcp/",
        auth_token="secret-token",
        expert="Reliability Engineering",
        local_model="fixture-local-model",
        timeout_seconds=2.0,
    )

    assert report.ok is True
    assert report.endpoint == "http://127.0.0.1:8765/mcp"
    assert report.conversation_id == "conv_AAAAAAAAAAAAAAAAAAAAAA"
    assert report.to_dict()["cost_usd"] == 0.0
    client = _FakeConversationHttpClient.instances[0]
    assert client.disconnected is True
    assert [message.method for message in client.sent] == [
        "initialize",
        "tools/list",
        "tools/call",
        "tools/call",
        "tools/call",
        "tools/call",
        "tools/call",
        "tools/call",
    ]
    for message in client.sent[2:]:
        assert message.params["arguments"]["_approved"] is True
    assert "secret-token" not in json.dumps(report.to_dict())


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
async def test_managed_loopback_validation_covers_restart_expiry_and_revocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del tmp_path
    monkeypatch.setattr(
        "deepr.mcp.expert_conversation.compile_conversation_snapshots",
        lambda *_args, **_kwargs: (expert_snapshot(),),
    )
    executor = CompletingExecutor()

    report = await run_managed_loopback_conversation_validation(
        expert="reliability_engineering",
        local_model="fixture-local-model",
        timeout_seconds=10.0,
        executor_factory=lambda: executor,
    )

    assert report.ok is True, report.to_dict()
    passed = {check.name for check in report.checks if check.status == "passed"}
    assert {
        "restart_recovery",
        "cross_key_isolation",
        "retention_expiry",
        "scoped_key_revocation",
        "authentication_material_redacted",
        "remote_audit_zero_cost",
    }.issubset(passed)
    assert len(executor.contexts) == 3
