"""Live HTTP acceptance checks for durable expert conversations."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from deepr.mcp.expert_conversation import OPERATION_KIND, OPERATION_SCHEMA_VERSION
from deepr.mcp.transport.http import HttpClient, HttpMessage

MCP_CONVERSATION_VALIDATION_SCHEMA_VERSION = "deepr-mcp-conversation-validation-v1"
MCP_CONVERSATION_VALIDATION_KIND = "deepr.mcp.conversation_validation"

ValidationMode = Literal["http", "managed_loopback"]

CONVERSATION_TOOL_NAMES = (
    "deepr_start_expert_conversation",
    "deepr_continue_expert_conversation",
    "deepr_get_expert_conversation",
    "deepr_close_expert_conversation",
)

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
class ConversationCheckpoint:
    """Opaque state needed to continue validation after transport restart."""

    conversation_id: str
    version: int
    turn_id: str
    artifact_sha256: str
    expert_names: tuple[str, ...]
    model: str


@dataclass(frozen=True)
class MCPConversationValidationReport:
    """Secret-free, versioned live validation report."""

    mode: ValidationMode
    endpoint: str
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
        return {
            "schema_version": MCP_CONVERSATION_VALIDATION_SCHEMA_VERSION,
            "kind": MCP_CONVERSATION_VALIDATION_KIND,
            "mode": self.mode,
            "endpoint": self.endpoint,
            "ok": self.ok,
            "cost_usd": 0.0,
            "capacity_source": "local_owned",
            "fallback_policy": "none",
            "live_metered_fallback": False,
            "conversation_id": self.conversation_id,
            "expert_names": list(self.expert_names),
            "local_model": self.local_model,
            "checks": [check.to_dict() for check in self.checks],
            "error": self.error,
            "generated_at": self.generated_at.isoformat(),
        }


def _passed(name: str, detail: str) -> MCPConversationValidationCheck:
    return MCPConversationValidationCheck(name=name, status="passed", detail=detail)


def _failed(name: str, detail: str) -> MCPConversationValidationCheck:
    return MCPConversationValidationCheck(name=name, status="failed", detail=detail)


def _parse_tool_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ConversationValidationFailure("INVALID_MCP_RESULT", "tools/call result was not an object")
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise ConversationValidationFailure("INVALID_MCP_RESULT", "tools/call returned no content")
    first = content[0]
    if not isinstance(first, dict) or not isinstance(first.get("text"), str):
        raise ConversationValidationFailure("INVALID_MCP_RESULT", "tools/call content did not contain text JSON")
    try:
        payload = json.loads(first["text"])
    except json.JSONDecodeError as exc:
        raise ConversationValidationFailure("INVALID_MCP_RESULT", "tools/call text was not JSON") from exc
    if not isinstance(payload, dict):
        raise ConversationValidationFailure("INVALID_MCP_RESULT", "tools/call JSON was not an object")
    return payload


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ConversationValidationFailure(code, message)


def _operation_payload(payload: dict[str, Any], operation: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if payload.get("kind") == "deepr.expert.conversation_error":
        error = payload.get("error")
        code = str(error.get("code") or "CONVERSATION_ERROR") if isinstance(error, dict) else "CONVERSATION_ERROR"
        message = (
            str(error.get("safe_message") or "Conversation operation failed")
            if isinstance(error, dict)
            else "Conversation operation failed"
        )
        raise ConversationValidationFailure(code, message)
    _require(
        payload.get("schema_version") == OPERATION_SCHEMA_VERSION,
        "INVALID_OPERATION_SCHEMA",
        "conversation operation schema version was not recognized",
    )
    _require(
        payload.get("kind") == OPERATION_KIND and payload.get("operation") == operation,
        "INVALID_OPERATION_KIND",
        f"conversation operation was not {operation}",
    )
    conversation = payload.get("conversation")
    turn = payload.get("turn")
    if not isinstance(conversation, dict):
        raise ConversationValidationFailure("INVALID_CONVERSATION", "operation omitted conversation state")
    if not isinstance(turn, dict):
        raise ConversationValidationFailure("INVALID_TURN", "operation omitted turn state")
    return conversation, turn


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
        isinstance(bounds, dict) and float(bounds.get("max_cost_usd", -1)) == 0.0,
        "NONZERO_COST_CEILING",
        "conversation cost ceiling was not zero",
    )
    _require(
        isinstance(usage, dict) and float(usage.get("cost_usd", -1)) == 0.0,
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


def _checkpoint(conversation: dict[str, Any], turn: dict[str, Any]) -> ConversationCheckpoint:
    backend = conversation["backend"]
    names = conversation.get("expert_names")
    if not isinstance(backend, dict):
        raise ConversationValidationFailure("INVALID_BACKEND", "conversation backend was not an object")
    if not isinstance(names, list) or not names:
        raise ConversationValidationFailure("INVALID_ROSTER", "conversation roster was empty")
    return ConversationCheckpoint(
        conversation_id=str(conversation["conversation_id"]),
        version=int(conversation["version"]),
        turn_id=str(turn["turn_id"]),
        artifact_sha256=str(turn["artifact_sha256"]),
        expert_names=tuple(str(name) for name in names),
        model=str(backend["model"]),
    )


class HTTPConversationProbe:
    """Stateful MCP client used by remote and managed acceptance flows."""

    def __init__(
        self,
        endpoint: str,
        *,
        auth_token: str,
        timeout_seconds: float,
        checks: list[MCPConversationValidationCheck],
        observed_responses: list[str],
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = HttpClient(self.endpoint, timeout=timeout_seconds, auth_token=auth_token)
        self.checks = checks
        self.observed_responses = observed_responses
        self._request_index = 0

    async def connect(self) -> None:
        await self.client.connect()

    async def disconnect(self) -> None:
        await self.client.disconnect()

    async def _send(self, method: str, params: dict[str, Any]) -> HttpMessage:
        self._request_index += 1
        response = await self.client.send(
            HttpMessage(
                id=f"conversation-validation-{self._request_index}",
                method=method,
                params=params,
            )
        )
        if response is None:
            raise ConversationValidationFailure("NO_MCP_RESPONSE", f"{method} returned no response")
        self.observed_responses.append(json.dumps(response.to_dict(), sort_keys=True, default=str))
        if response.error:
            data = response.error.get("data")
            code = str(data.get("error_code") or "MCP_ERROR") if isinstance(data, dict) else "MCP_ERROR"
            raise ConversationValidationFailure(code, str(response.error.get("message") or f"{method} failed"))
        return response

    async def initialize_and_discover(self, *, check_prefix: str = "") -> None:
        await self._send("initialize", {})
        self.checks.append(_passed(f"{check_prefix}mcp_initialize", "endpoint accepted initialize"))
        response = await self._send("tools/list", {"_fullList": True})
        result = response.result
        tools = result.get("tools") if isinstance(result, dict) else None
        names = (
            {str(tool.get("name")) for tool in tools if isinstance(tool, dict) and isinstance(tool.get("name"), str)}
            if isinstance(tools, list)
            else set()
        )
        missing = sorted(set(CONVERSATION_TOOL_NAMES) - names)
        _require(not missing, "TOOLS_NOT_REGISTERED", f"conversation tools missing from tools/list: {missing}")
        self.checks.append(
            _passed(f"{check_prefix}conversation_tool_discovery", "all four conversation tools were advertised")
        )

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = await self._send(
            "tools/call",
            {
                "name": tool_name,
                "arguments": {**arguments, "_approved": True},
            },
        )
        result = response.result
        payload = _parse_tool_result(result)
        if isinstance(result, dict) and result.get("isError") is True:
            _operation_payload(payload, "error")
        return payload

    async def start_and_replay(
        self,
        *,
        message: str,
        expert: str | None,
        local_model: str | None,
        retention_days: int = 30,
        check_prefix: str = "",
    ) -> ConversationCheckpoint:
        arguments: dict[str, Any] = {
            "message": message,
            "idempotency_key": f"validation-start-{secrets.token_hex(12)}",
            "mode": "focused",
            "max_experts": 1,
            "retention_days": retention_days,
            "bounds": {
                "max_turns": 2,
                "max_model_calls": 2,
                "max_input_tokens": 100_000,
                "max_output_tokens": 50_000,
                "max_context_bytes": 65_536,
                "max_elapsed_seconds": min(max(int(self.timeout_seconds * 2), 600), 86_400),
                "max_cost_usd": 0.0,
            },
        }
        if expert:
            arguments["experts"] = [expert]
        if local_model:
            arguments["local_model"] = local_model
        first = await self.call("deepr_start_expert_conversation", arguments)
        conversation, turn = _operation_payload(first, "start")
        _validate_local_contract(conversation, turn)
        first_checkpoint = _checkpoint(conversation, turn)
        self.checks.append(
            _passed(f"{check_prefix}start_local_conversation", "start returned a verified local-only turn")
        )

        replay = await self.call("deepr_start_expert_conversation", arguments)
        replay_conversation, replay_turn = _operation_payload(replay, "start")
        _require(replay.get("replayed") is True, "START_NOT_REPLAYED", "duplicate start was not replayed")
        replay_checkpoint = _checkpoint(replay_conversation, replay_turn)
        _require(
            replay_checkpoint == first_checkpoint,
            "START_REPLAY_DRIFT",
            "duplicate start changed the handle, version, turn, artifact, roster, or model",
        )
        self.checks.append(
            _passed(
                f"{check_prefix}duplicate_start_replay",
                "duplicate start returned the identical durable result",
            )
        )
        return first_checkpoint

    async def get_and_verify(
        self,
        checkpoint: ConversationCheckpoint,
        *,
        check_name: str,
    ) -> ConversationCheckpoint:
        payload = await self.call(
            "deepr_get_expert_conversation",
            {"conversation_id": checkpoint.conversation_id},
        )
        conversation, turn = _operation_payload(payload, "get")
        _validate_local_contract(conversation, turn)
        current = _checkpoint(conversation, turn)
        _require(current == checkpoint, "GET_STATE_DRIFT", "get did not return the expected durable checkpoint")
        self.checks.append(_passed(check_name, "durable checkpoint was recovered exactly"))
        return current

    async def continue_and_replay(
        self,
        checkpoint: ConversationCheckpoint,
        *,
        message: str,
    ) -> ConversationCheckpoint:
        arguments = {
            "conversation_id": checkpoint.conversation_id,
            "expected_version": checkpoint.version,
            "idempotency_key": f"validation-continue-{secrets.token_hex(12)}",
            "message": message,
        }
        first = await self.call("deepr_continue_expert_conversation", arguments)
        conversation, turn = _operation_payload(first, "continue")
        _validate_local_contract(conversation, turn)
        current = _checkpoint(conversation, turn)
        _require(current.conversation_id == checkpoint.conversation_id, "HANDLE_CHANGED", "continue changed the handle")
        _require(current.version > checkpoint.version, "VERSION_NOT_ADVANCED", "continue did not advance the version")
        context = turn.get("context")
        recent_ids = context.get("recent_turn_ids") if isinstance(context, dict) else None
        _require(
            isinstance(recent_ids, list) and checkpoint.turn_id in recent_ids,
            "PRIOR_TURN_NOT_VISIBLE",
            "continuation context did not include the prior turn",
        )
        self.checks.append(_passed("continue_with_prior_context", "follow-up used the pinned prior turn"))

        replay = await self.call("deepr_continue_expert_conversation", arguments)
        replay_conversation, replay_turn = _operation_payload(replay, "continue")
        _require(replay.get("replayed") is True, "CONTINUE_NOT_REPLAYED", "duplicate continuation was not replayed")
        replay_checkpoint = _checkpoint(replay_conversation, replay_turn)
        _require(
            replay_checkpoint == current,
            "CONTINUE_REPLAY_DRIFT",
            "duplicate continuation changed the durable result",
        )
        self.checks.append(
            _passed("duplicate_continue_replay", "duplicate continuation returned the identical durable result")
        )
        return current

    async def close_and_purge(self, checkpoint: ConversationCheckpoint) -> None:
        payload = await self.call(
            "deepr_close_expert_conversation",
            {
                "conversation_id": checkpoint.conversation_id,
                "expected_version": checkpoint.version,
                "delete_content": True,
            },
        )
        conversation, turn = _operation_payload(payload, "close")
        retention = conversation.get("retention")
        request = turn.get("request")
        _require(conversation.get("state") == "closed", "CLOSE_FAILED", "conversation did not close")
        _require(
            isinstance(retention, dict) and retention.get("content_deleted") is True,
            "PURGE_FAILED",
            "close did not purge retained content",
        )
        _require(
            isinstance(request, dict)
            and request.get("content_available") is False
            and turn.get("artifact_available") is False,
            "CONTENT_RETAINED",
            "purged turn content remained readable",
        )
        self.checks.append(_passed("close_and_purge", "close retained only the audit skeleton"))

    async def get_expired_and_verify(self, conversation_id: str) -> None:
        payload = await self.call(
            "deepr_get_expert_conversation",
            {"conversation_id": conversation_id},
        )
        conversation, turn = _operation_payload(payload, "get")
        retention = conversation.get("retention")
        request = turn.get("request")
        _require(conversation.get("state") == "expired", "EXPIRY_FAILED", "conversation did not expire")
        _require(
            isinstance(retention, dict) and retention.get("content_deleted") is True,
            "EXPIRY_CONTENT_RETAINED",
            "expired conversation retained content",
        )
        _require(
            isinstance(request, dict)
            and request.get("content_available") is False
            and turn.get("artifact_available") is False,
            "EXPIRY_CONTENT_READABLE",
            "expired turn content remained readable",
        )
        self.checks.append(_passed("retention_expiry", "simulated retention expiry purged logical content"))


def assert_secret_redaction(observed: list[str], forbidden_values: tuple[str, ...]) -> None:
    for forbidden in forbidden_values:
        if forbidden and any(forbidden in value for value in observed):
            raise ConversationValidationFailure("SECRET_ECHOED", "a response echoed authentication material")


async def run_http_conversation_validation(
    url: str,
    *,
    auth_token: str,
    expert: str | None = None,
    local_model: str | None = None,
    start_message: str = DEFAULT_START_MESSAGE,
    continue_message: str = DEFAULT_CONTINUE_MESSAGE,
    timeout_seconds: float = 180.0,
) -> MCPConversationValidationReport:
    """Validate a running authenticated MCP endpoint without paid capacity."""
    endpoint = url.rstrip("/")
    checks: list[MCPConversationValidationCheck] = []
    observed: list[str] = []
    checkpoint: ConversationCheckpoint | None = None
    error: dict[str, str] | None = None
    probe = HTTPConversationProbe(
        endpoint,
        auth_token=auth_token,
        timeout_seconds=timeout_seconds,
        checks=checks,
        observed_responses=observed,
    )
    try:
        await probe.connect()
        await probe.initialize_and_discover()
        checkpoint = await probe.start_and_replay(
            message=start_message,
            expert=expert,
            local_model=local_model,
        )
        await probe.get_and_verify(checkpoint, check_name="same_process_get")
        checkpoint = await probe.continue_and_replay(checkpoint, message=continue_message)
        await probe.close_and_purge(checkpoint)
        assert_secret_redaction(observed, (auth_token,))
        checks.append(_passed("authentication_material_redacted", "responses did not echo the bearer secret"))
    except ConversationValidationFailure as exc:
        checks.append(_failed("conversation_validation", exc.safe_message))
        error = {"error_code": exc.code, "message": exc.safe_message}
    except (OSError, RuntimeError, ValueError) as exc:
        safe_message = f"conversation validation failed: {type(exc).__name__}"
        checks.append(_failed("conversation_validation", safe_message))
        error = {"error_code": "MCP_CONVERSATION_VALIDATION_FAILED", "message": safe_message}
    finally:
        await probe.disconnect()

    return MCPConversationValidationReport(
        mode="http",
        endpoint=endpoint,
        checks=tuple(checks),
        conversation_id=checkpoint.conversation_id if checkpoint else None,
        expert_names=checkpoint.expert_names if checkpoint else (),
        local_model=checkpoint.model if checkpoint else local_model,
        error=error,
    )


__all__ = [
    "CONVERSATION_TOOL_NAMES",
    "DEFAULT_CONTINUE_MESSAGE",
    "DEFAULT_START_MESSAGE",
    "ConversationCheckpoint",
    "ConversationValidationFailure",
    "HTTPConversationProbe",
    "MCPConversationValidationCheck",
    "MCPConversationValidationReport",
    "assert_secret_redaction",
    "run_http_conversation_validation",
]
