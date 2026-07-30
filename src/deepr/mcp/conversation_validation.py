"""Live HTTP acceptance checks for durable expert conversations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from deepr.mcp.http_client_policy import (
    is_exact_zero_cost,
    validated_mcp_http_timeout,
    validated_remote_mcp_url,
)

MCP_CONVERSATION_VALIDATION_SCHEMA_VERSION = "deepr-mcp-conversation-validation-v1"
MCP_CONVERSATION_VALIDATION_KIND = "deepr.mcp.conversation_validation"

ValidationMode = Literal["http", "managed_loopback"]

DEFAULT_START_MESSAGE = (
    "Using the frozen expert state, recommend the single highest-value reliability gate for releasing a durable "
    "local expert-conversation service. Explain the main uncertainty. Do not ask a clarification question."
)
DEFAULT_CONTINUE_MESSAGE = (
    "Challenge the prior recommendation. Identify the strongest failure mode the first answer underweighted and "
    "revise the release gate if needed. Use the prior answer as conversation context."
)


class ConversationValidationFailure(RuntimeError):
    """Safe validation failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class MCPConversationValidationCheck:
    """One observable acceptance condition."""

    name: str
    status: Literal["passed", "failed"]
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class MCPConversationValidationReport:
    """Secret-free, versioned live validation report."""

    mode: ValidationMode
    endpoint: str | None
    checks: tuple[MCPConversationValidationCheck, ...]
    conversation_id: str | None = None
    expert_names: tuple[str, ...] = ()
    local_model: str | None = None
    error: dict[str, str] | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def ok(self) -> bool:
        return bool(self.checks) and not self.error and all(check.status == "passed" for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        remote_mode = self.mode == "http"
        verified_managed = self.mode == "managed_loopback" and self.ok
        return {
            "schema_version": MCP_CONVERSATION_VALIDATION_SCHEMA_VERSION,
            "kind": MCP_CONVERSATION_VALIDATION_KIND,
            "mode": self.mode,
            "endpoint": self.endpoint,
            "ok": self.ok,
            "cost_usd": 0.0,
            "cost_scope": "validation_client_only" if remote_mode else "managed_loopback_harness",
            "capacity_source": "local_owned" if verified_managed else "unverified",
            "fallback_policy": "none" if verified_managed else "unverified",
            "live_metered_fallback": False if verified_managed else None,
            "remote_tool_call_attempted": False,
            "remote_tool_cost_status": "not_submitted",
            "remote_tool_calls_metered_api": None,
            "conversation_id": self.conversation_id,
            "expert_names": list(self.expert_names),
            "local_model": self.local_model,
            "checks": [check.to_dict() for check in self.checks],
            "error": self.error,
            "generated_at": self.generated_at.isoformat(),
        }


def _failed(name: str, detail: str) -> MCPConversationValidationCheck:
    return MCPConversationValidationCheck(name=name, status="failed", detail=detail)


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ConversationValidationFailure(code, message)


def _validate_local_contract(conversation: dict[str, Any], turn: dict[str, Any]) -> None:
    backend = conversation.get("backend")
    bounds = conversation.get("bounds")
    usage = conversation.get("usage")
    if not isinstance(backend, dict):
        raise ConversationValidationFailure("INVALID_BACKEND", "conversation omitted backend metadata")
    _require(
        backend.get("capacity_source") == "local_owned" and backend.get("backend_class") == "local",
        "NONLOCAL_BACKEND",
        "conversation did not use owned local capacity",
    )
    _require(
        backend.get("fallback_policy") == "none" and backend.get("live_metered_fallback") is False,
        "METERED_FALLBACK_ENABLED",
        "conversation allowed a fallback backend",
    )
    _require(
        isinstance(bounds, dict) and is_exact_zero_cost(bounds.get("max_cost_usd")),
        "NONZERO_COST_CEILING",
        "conversation cost ceiling was not zero",
    )
    _require(
        isinstance(usage, dict) and is_exact_zero_cost(usage.get("cost_usd")),
        "NONZERO_RECORDED_COST",
        "conversation recorded nonzero Deepr cost",
    )
    turn_state = str(turn.get("state") or "unknown")
    if turn_state != "completed" or turn.get("artifact_available") is not True:
        stop = turn.get("stop")
        stop_reason = str(stop.get("reason") or turn_state) if isinstance(stop, dict) else turn_state
        code_by_state = {
            "budget_exhausted": "LOCAL_CONVERSATION_BUDGET_EXHAUSTED",
            "failed": "LOCAL_EXECUTOR_FAILED",
            "verifier_failed": "LOCAL_ARTIFACT_VERIFIER_FAILED",
            "waiting_capacity": "LOCAL_CAPACITY_UNAVAILABLE",
        }
        raise ConversationValidationFailure(
            code_by_state.get(turn_state, "TURN_NOT_COMPLETED"),
            f"local model turn ended in {turn_state} with stop reason {stop_reason}",
        )
    artifact = turn.get("artifact")
    if not isinstance(artifact, dict):
        raise ConversationValidationFailure("INVALID_ARTIFACT", "turn artifact was not an object")
    _require(
        isinstance(artifact.get("direct_answer"), str) and bool(artifact["direct_answer"].strip()),
        "EMPTY_ANSWER",
        "turn artifact did not contain a direct answer",
    )


def assert_secret_redaction(observed: list[str], forbidden_values: tuple[str, ...]) -> None:
    for forbidden in forbidden_values:
        if forbidden and any(forbidden in value for value in observed):
            raise ConversationValidationFailure("SECRET_ECHOED", "a response echoed authentication material")


async def run_http_conversation_validation(
    url: str,
    *,
    auth_token: str | None = None,
    expert: str | None = None,
    local_model: str | None = None,
    start_message: str = DEFAULT_START_MESSAGE,
    continue_message: str = DEFAULT_CONTINUE_MESSAGE,
    timeout_seconds: float = 180.0,
) -> MCPConversationValidationReport:
    """Fail closed before remote conversation work until cost authority is attestable."""
    try:
        endpoint = validated_remote_mcp_url(url)
        validated_mcp_http_timeout(timeout_seconds)
    except ValueError as exc:
        detail = str(exc)
        return MCPConversationValidationReport(
            mode="http",
            endpoint=None,
            checks=(_failed("http_preflight", detail),),
            local_model=local_model,
            error={"error_code": "INVALID_HTTP_PREFLIGHT", "message": detail},
        )

    del auth_token, expert, start_message, continue_message
    detail = (
        "Remote MCP conversation validation is blocked until Deepr can verify an independently "
        "enforced cost authority before tools/call. Bearer authentication and returned local, "
        "zero-cost metadata are self-reported and cannot prove that a remote endpoint avoided "
        "metered side effects. Use direct offline validation instead."
    )
    return MCPConversationValidationReport(
        mode="http",
        endpoint=endpoint,
        checks=(_failed("http_tool_cost_authority", detail),),
        local_model=local_model,
        error={"error_code": "MCP_HTTP_CONVERSATION_VALIDATION_BLOCKED", "message": detail},
    )


__all__ = [
    "DEFAULT_CONTINUE_MESSAGE",
    "DEFAULT_START_MESSAGE",
    "ConversationValidationFailure",
    "MCPConversationValidationCheck",
    "MCPConversationValidationReport",
    "assert_secret_redaction",
    "run_http_conversation_validation",
]
