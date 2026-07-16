"""MCP adapter for durable, local-only expert conversations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol, cast

from deepr.experts.conversation.local_executor import LocalOllamaConversationExecutor
from deepr.experts.conversation.models import (
    BackendSelection,
    ConsultationMode,
    ConversationBounds,
    ConversationContinueRequest,
    ConversationError,
    ConversationOperationResult,
    ConversationStartRequest,
    ErrorCode,
)
from deepr.experts.conversation.service import ExpertConversationService
from deepr.experts.conversation.snapshots import compile_conversation_snapshots
from deepr.experts.conversation.store import ExpertConversationStore
from deepr.mcp.request_context import MCPRequestIdentity, current_mcp_request_identity
from deepr.mcp.search.registry import ToolSchema

OPERATION_SCHEMA_VERSION = "deepr-expert-conversation-operation-v1"
OPERATION_KIND = "deepr.expert.conversation_operation"

ModelResolver = Callable[[], Awaitable[str | None]]


class ExpertStoreLike(Protocol):
    def list_all(self) -> list[Any]:
        """Return available expert profiles."""


def _bounds_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "max_turns": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            "max_model_calls": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 40},
            "max_input_tokens": {"type": "integer", "minimum": 1, "maximum": 1_000_000_000},
            "max_output_tokens": {"type": "integer", "minimum": 1, "maximum": 1_000_000_000},
            "max_context_bytes": {"type": "integer", "minimum": 1024, "maximum": 1_048_576},
            "max_elapsed_seconds": {"type": "integer", "minimum": 1, "maximum": 86_400},
            "max_cost_usd": {"type": "number", "const": 0.0, "default": 0.0},
        },
    }


START_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "message": {"type": "string", "minLength": 1, "maxLength": 131_072},
        "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128},
        "experts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "max_experts": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
        "mode": {"type": "string", "enum": ["focused", "council"], "default": "focused"},
        "decision_brief": {"type": "string", "minLength": 1, "maxLength": 65_536},
        "local_model": {"type": "string", "minLength": 1, "maxLength": 256},
        "bounds": _bounds_schema(),
        "retention_days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30},
    },
    "required": ["message", "idempotency_key"],
}

CONTINUE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "conversation_id": {"type": "string", "pattern": "^conv_[A-Za-z0-9_-]{22,64}$"},
        "expected_version": {"type": "integer", "minimum": 1},
        "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128},
        "message": {"type": "string", "minLength": 1, "maxLength": 131_072},
        "input_request_id": {
            "type": "string",
            "pattern": "^input_[A-Za-z0-9_-]{16,64}$",
        },
    },
    "required": ["conversation_id", "expected_version", "idempotency_key", "message"],
}

GET_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "conversation_id": {"type": "string", "pattern": "^conv_[A-Za-z0-9_-]{22,64}$"},
        "turn_id": {"type": "string", "pattern": "^turn_[A-Za-z0-9_-]{16,64}$"},
    },
    "required": ["conversation_id"],
}

CLOSE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "conversation_id": {"type": "string", "pattern": "^conv_[A-Za-z0-9_-]{22,64}$"},
        "expected_version": {"type": "integer", "minimum": 1},
        "delete_content": {
            "type": "boolean",
            "default": False,
            "description": "Purge transcript and artifact content after recording the close event.",
        },
    },
    "required": ["conversation_id", "expected_version"],
}

OPERATION_OUTPUT_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "kind",
                "operation",
                "conversation",
                "turn",
                "replayed",
                "dispatch_status",
            ],
            "properties": {
                "schema_version": {"const": OPERATION_SCHEMA_VERSION},
                "kind": {"const": OPERATION_KIND},
                "operation": {"enum": ["start", "continue", "get", "close"]},
                "conversation": {"type": "object"},
                "turn": {"oneOf": [{"type": "object"}, {"type": "null"}]},
                "replayed": {"type": "boolean"},
                "dispatch_status": {"type": "string"},
            },
        },
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "kind", "error"],
            "properties": {
                "schema_version": {"const": "deepr-expert-conversation-error-v1"},
                "kind": {"const": "deepr.expert.conversation_error"},
                "error": {"type": "object"},
            },
        },
    ]
}


CONVERSATION_TOOL_SCHEMAS = (
    ToolSchema(
        name="deepr_start_expert_conversation",
        description=(
            "Start a durable local-only conversation with one frozen expert roster. Returns an opaque conversation "
            "handle for later turns. Uses Ollama at $0, disables metered fallback, and never writes expert memory."
        ),
        input_schema=START_INPUT_SCHEMA,
        output_schema=OPERATION_OUTPUT_SCHEMA,
        category="experts",
        cost_tier="free",
    ),
    ToolSchema(
        name="deepr_continue_expert_conversation",
        description=(
            "Continue an owned expert conversation using its opaque handle, expected version, and a unique "
            "idempotency key. The pinned roster, model, snapshot, and capacity ceilings cannot widen."
        ),
        input_schema=CONTINUE_INPUT_SCHEMA,
        output_schema=OPERATION_OUTPUT_SCHEMA,
        category="experts",
        cost_tier="free",
    ),
    ToolSchema(
        name="deepr_get_expert_conversation",
        description=(
            "Inspect an owned durable expert conversation and its latest or selected turn. Cross-owner ids return "
            "not found, and deleted or expired content is not reconstructed."
        ),
        input_schema=GET_INPUT_SCHEMA,
        output_schema=OPERATION_OUTPUT_SCHEMA,
        category="experts",
        cost_tier="free",
    ),
    ToolSchema(
        name="deepr_close_expert_conversation",
        description=(
            "Close an owned expert conversation using optimistic concurrency. Optionally purge transcript and "
            "artifact content while retaining the minimal append-only audit skeleton."
        ),
        input_schema=CLOSE_INPUT_SCHEMA,
        output_schema=OPERATION_OUTPUT_SCHEMA,
        category="experts",
        cost_tier="free",
    ),
)


async def _default_model_resolver() -> str | None:
    from deepr.backends.local import default_local_model_async

    return await default_local_model_async()


def _error(
    code: ErrorCode, message: str, *, retryable: bool = False, field_name: str | None = None
) -> ConversationError:
    return ConversationError(code, message, retryable=retryable, field_name=field_name)


def _identity() -> MCPRequestIdentity:
    identity = current_mcp_request_identity() or MCPRequestIdentity.local_stdio()
    if identity.transport == "http" and not identity.authenticated:
        raise _error(ErrorCode.OWNERSHIP_DENIED, "Authenticated HTTP access is required.")
    if identity.transport == "http" and not identity.peer_is_loopback and identity.authentication != "scoped_key":
        raise _error(ErrorCode.OWNERSHIP_DENIED, "A scoped MCP key is required for LAN conversations.")
    return identity


def _mode(value: str) -> ConsultationMode:
    try:
        resolved = ConsultationMode(value)
    except (TypeError, ValueError) as exc:
        raise _error(ErrorCode.INVALID_REQUEST, "mode must be focused or council.", field_name="mode") from exc
    if resolved not in {ConsultationMode.FOCUSED, ConsultationMode.COUNCIL}:
        raise _error(ErrorCode.INVALID_REQUEST, "mode must be focused or council.", field_name="mode")
    return resolved


def _bounds(value: dict[str, Any] | None) -> ConversationBounds:
    if value is None:
        return ConversationBounds()
    if not isinstance(value, dict):
        raise _error(ErrorCode.INVALID_REQUEST, "bounds must be an object.", field_name="bounds")
    try:
        return ConversationBounds.from_dict(value)
    except ConversationError:
        raise


def _operation(operation: str, result: ConversationOperationResult) -> dict[str, Any]:
    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "kind": OPERATION_KIND,
        "operation": operation,
        **result.to_dict(),
    }


def _scope_allows(identity: MCPRequestIdentity, expert_names: Sequence[str]) -> None:
    if identity.expert_allowlist and not set(expert_names).issubset(identity.expert_allowlist):
        raise _error(ErrorCode.OWNERSHIP_DENIED, "Conversation access is outside the current expert scope.")


class MCPExpertConversationTools:
    """Translate MCP requests into the shared durable conversation service."""

    def __init__(
        self,
        expert_store: ExpertStoreLike,
        *,
        service: ExpertConversationService | None = None,
        model_resolver: ModelResolver | None = None,
    ) -> None:
        self.expert_store = expert_store
        self.service = service or ExpertConversationService(
            ExpertConversationStore(),
            LocalOllamaConversationExecutor,
        )
        self._model_resolver = model_resolver or _default_model_resolver
        self._recovery_lock = asyncio.Lock()
        self._recovery_complete = False

    @staticmethod
    def _safe_error(exc: ConversationError) -> dict[str, Any]:
        return exc.to_envelope()

    async def _ensure_recovered(self) -> None:
        if self._recovery_complete:
            return
        async with self._recovery_lock:
            if self._recovery_complete:
                return
            await self.service.recover()
            await self.service.expire_due()
            self._recovery_complete = True

    async def start(
        self,
        *,
        message: str,
        idempotency_key: str,
        experts: list[str] | None = None,
        max_experts: int = 1,
        mode: str = "focused",
        decision_brief: str | None = None,
        local_model: str | None = None,
        bounds: dict[str, Any] | None = None,
        retention_days: int = 30,
    ) -> dict[str, Any]:
        try:
            identity = _identity()
            await self._ensure_recovered()
            resolved_mode = _mode(mode)
            if local_model is not None and (not isinstance(local_model, str) or not local_model.strip()):
                raise _error(ErrorCode.INVALID_REQUEST, "local_model must be non-empty text.", field_name="local_model")
            model = local_model.strip() if isinstance(local_model, str) else await self._model_resolver()
            if not model:
                raise _error(
                    ErrorCode.WAITING_CAPACITY,
                    "No local Ollama model is currently available.",
                    retryable=True,
                    field_name="local_model",
                )
            snapshots = await asyncio.to_thread(
                compile_conversation_snapshots,
                self.expert_store,
                message=message,
                requested_experts=experts,
                max_experts=max_experts,
                mode=resolved_mode,
            )
            _scope_allows(identity, [snapshot.expert_name for snapshot in snapshots])
            request = ConversationStartRequest(
                owner_id=identity.owner_id,
                idempotency_key=idempotency_key,
                message=message,
                expert_snapshots=snapshots,
                backend=BackendSelection.local(model),
                bounds=_bounds(bounds),
                mode=resolved_mode,
                decision_brief=decision_brief,
                retention_days=retention_days,
            )
            return _operation("start", await self.service.start(request))
        except ConversationError as exc:
            return self._safe_error(exc)
        except (OSError, RuntimeError):
            return self._safe_error(_error(ErrorCode.STORAGE_FAILED, "Conversation start failed safely."))

    async def _owned_current(
        self,
        identity: MCPRequestIdentity,
        conversation_id: str,
        *,
        turn_id: str | None = None,
    ) -> ConversationOperationResult:
        current = await self.service.get(
            owner_id=identity.owner_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )
        names = current.conversation.get("expert_names", [])
        if not isinstance(names, list):
            raise _error(ErrorCode.STORAGE_FAILED, "Stored conversation roster is invalid.")
        _scope_allows(identity, [str(name) for name in names])
        return current

    async def continue_conversation(
        self,
        *,
        conversation_id: str,
        expected_version: int,
        idempotency_key: str,
        message: str,
        input_request_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            identity = _identity()
            await self._ensure_recovered()
            await self._owned_current(identity, conversation_id)
            request = ConversationContinueRequest(
                owner_id=identity.owner_id,
                conversation_id=conversation_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                message=message,
                input_request_id=input_request_id,
            )
            return _operation("continue", await self.service.continue_conversation(request))
        except ConversationError as exc:
            return self._safe_error(exc)
        except (OSError, RuntimeError):
            return self._safe_error(_error(ErrorCode.STORAGE_FAILED, "Conversation continuation failed safely."))

    async def get(self, *, conversation_id: str, turn_id: str | None = None) -> dict[str, Any]:
        try:
            identity = _identity()
            await self._ensure_recovered()
            current = await self._owned_current(identity, conversation_id, turn_id=turn_id)
            return _operation("get", current)
        except ConversationError as exc:
            return self._safe_error(exc)
        except (OSError, RuntimeError):
            return self._safe_error(_error(ErrorCode.STORAGE_FAILED, "Conversation inspection failed safely."))

    async def close(
        self,
        *,
        conversation_id: str,
        expected_version: int,
        delete_content: bool = False,
    ) -> dict[str, Any]:
        try:
            identity = _identity()
            await self._ensure_recovered()
            await self._owned_current(identity, conversation_id)
            result = await self.service.close(
                owner_id=identity.owner_id,
                conversation_id=conversation_id,
                expected_version=expected_version,
            )
            if delete_content:
                result = await self.service.delete_content(
                    owner_id=identity.owner_id,
                    conversation_id=conversation_id,
                    expected_version=int(result.conversation["version"]),
                )
            return _operation("close", result)
        except ConversationError as exc:
            return self._safe_error(exc)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError):
            return self._safe_error(_error(ErrorCode.STORAGE_FAILED, "Conversation close failed safely."))


def register_conversation_tools(registry: Any) -> None:
    """Register the four durable conversation tools on a ToolRegistry."""
    for schema in CONVERSATION_TOOL_SCHEMAS:
        registry.register(schema)


def bind_conversation_tools(server: Any) -> MCPExpertConversationTools:
    """Lazily attach MCP conversation tools to a DeeprMCPServer-like host."""
    tools = getattr(server, "_expert_conversation_tools", None)
    if tools is None:
        tools = MCPExpertConversationTools(server.store)
        server._expert_conversation_tools = tools
    return cast(MCPExpertConversationTools, tools)


def conversation_tool_dispatch(
    server: Any,
) -> dict[str, Callable[[dict[str, Any]], Awaitable[Any]]]:
    """Build tool-name dispatch entries for durable expert conversations."""

    def _tools() -> MCPExpertConversationTools:
        return bind_conversation_tools(server)

    return {
        "deepr_start_expert_conversation": lambda args: _tools().start(**args),
        "deepr_continue_expert_conversation": lambda args: _tools().continue_conversation(**args),
        "deepr_get_expert_conversation": lambda args: _tools().get(**args),
        "deepr_close_expert_conversation": lambda args: _tools().close(**args),
    }


__all__ = [
    "CONVERSATION_TOOL_SCHEMAS",
    "OPERATION_KIND",
    "OPERATION_SCHEMA_VERSION",
    "MCPExpertConversationTools",
    "bind_conversation_tools",
    "conversation_tool_dispatch",
    "register_conversation_tools",
]
