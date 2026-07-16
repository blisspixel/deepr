"""Managed loopback acceptance harness for expert conversations."""

from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from deepr.experts.conversation.local_executor import LocalOllamaConversationExecutor
from deepr.experts.conversation.service import (
    ExpertConversationService,
    ExpertConversationTurnExecutor,
)
from deepr.experts.conversation.store import ExpertConversationStore
from deepr.mcp.conversation_validation import (
    DEFAULT_CONTINUE_MESSAGE,
    DEFAULT_START_MESSAGE,
    ConversationCheckpoint,
    ConversationValidationFailure,
    HTTPConversationProbe,
    MCPConversationValidationCheck,
    MCPConversationValidationReport,
    _failed,
    _passed,
    _require,
    assert_secret_redaction,
)
from deepr.mcp.expert_conversation import MCPExpertConversationTools
from deepr.mcp.http_server import _make_http_message_handler
from deepr.mcp.security.scoped_keys import RemoteMCPAuditLog, ScopedMCPKeyStore
from deepr.mcp.security.tool_allowlist import ResearchMode
from deepr.mcp.server import DeeprMCPServer
from deepr.mcp.transport.http import StreamingHttpTransport

ExecutorFactory = Callable[[], ExpertConversationTurnExecutor]


class _ValidationClock:
    def __init__(self) -> None:
        self.value = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, days: float) -> None:
        self.value += timedelta(days=days)


@dataclass
class _ManagedRuntime:
    transport: StreamingHttpTransport

    @property
    def endpoint(self) -> str:
        return self.transport.url

    async def stop(self) -> None:
        await self.transport.stop()


def _loopback_port() -> int:
    """Choose a currently free loopback port for the short-lived harness."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


async def _start_runtime(
    *,
    port: int,
    database_path: Path,
    clock: _ValidationClock,
    key_store: ScopedMCPKeyStore,
    audit_log: RemoteMCPAuditLog,
    executor_factory: ExecutorFactory,
) -> _ManagedRuntime:
    server = DeeprMCPServer()
    service = ExpertConversationService(
        ExpertConversationStore(database_path, clock=clock),
        executor_factory,
    )
    server._expert_conversation_tools = MCPExpertConversationTools(
        server.store,
        service=service,
    )
    transport = StreamingHttpTransport(
        host="127.0.0.1",
        port=port,
        path="/mcp",
        scoped_key_store=key_store,
        audit_log=audit_log,
    )
    transport.on_message(_make_http_message_handler(server))
    await transport.start()
    return _ManagedRuntime(transport=transport)


def _scan_secret_from_files(root: Path, forbidden_values: tuple[str, ...]) -> None:
    encoded = tuple(value.encode("utf-8") for value in forbidden_values if value)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if any(secret in raw for secret in encoded):
            raise ConversationValidationFailure(
                "SECRET_PERSISTED",
                "the managed validation directory persisted authentication material",
            )


def _audit_is_zero_cost(audit_log: RemoteMCPAuditLog) -> bool:
    conversation_tools = {
        "deepr_start_expert_conversation",
        "deepr_continue_expert_conversation",
        "deepr_get_expert_conversation",
        "deepr_close_expert_conversation",
    }
    events = [event for event in audit_log.read_recent(limit=10_000) if event.tool in conversation_tools]
    return bool(events) and all(event.cost_usd in {None, 0.0} for event in events)


async def _disconnect_and_stop(
    probe: HTTPConversationProbe | None,
    runtime: _ManagedRuntime | None,
) -> None:
    if probe is not None:
        await probe.disconnect()
    if runtime is not None:
        await runtime.stop()


async def run_managed_loopback_conversation_validation(
    *,
    expert: str | None = None,
    local_model: str | None = None,
    start_message: str = DEFAULT_START_MESSAGE,
    continue_message: str = DEFAULT_CONTINUE_MESSAGE,
    timeout_seconds: float = 180.0,
    executor_factory: ExecutorFactory | None = None,
) -> MCPConversationValidationReport:
    """Start, restart, expire, and revoke a temporary authenticated service."""
    checks: list[MCPConversationValidationCheck] = []
    observed: list[str] = []
    checkpoint: ConversationCheckpoint | None = None
    endpoint = "http://127.0.0.1:0/mcp"
    error: dict[str, str] | None = None
    resolved_executor_factory = executor_factory or LocalOllamaConversationExecutor

    try:
        with TemporaryDirectory(prefix="deepr-conversation-validation-") as temporary:
            root = Path(temporary)
            clock = _ValidationClock()
            key_store = ScopedMCPKeyStore(root / "keys.json")
            audit_log = RemoteMCPAuditLog(root / "audit.jsonl")
            secret, record = key_store.create_key(
                "managed-conversation-validator",
                mode=ResearchMode.STANDARD,
                budget_limit_usd=0.0,
            )
            other_secret, _other_record = key_store.create_key(
                "managed-conversation-isolation-probe",
                mode=ResearchMode.STANDARD,
                budget_limit_usd=0.0,
            )
            port = _loopback_port()
            database_path = root / "conversations.db"

            runtime = await _start_runtime(
                port=port,
                database_path=database_path,
                clock=clock,
                key_store=key_store,
                audit_log=audit_log,
                executor_factory=resolved_executor_factory,
            )
            endpoint = runtime.endpoint
            probe = HTTPConversationProbe(
                endpoint,
                auth_token=secret,
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
            finally:
                await _disconnect_and_stop(probe, runtime)

            runtime = await _start_runtime(
                port=port,
                database_path=database_path,
                clock=clock,
                key_store=key_store,
                audit_log=audit_log,
                executor_factory=resolved_executor_factory,
            )
            probe = HTTPConversationProbe(
                runtime.endpoint,
                auth_token=secret,
                timeout_seconds=timeout_seconds,
                checks=checks,
                observed_responses=observed,
            )
            try:
                await probe.connect()
                await probe.initialize_and_discover(check_prefix="restart_")
                await probe.get_and_verify(checkpoint, check_name="restart_recovery")

                isolation_probe = HTTPConversationProbe(
                    runtime.endpoint,
                    auth_token=other_secret,
                    timeout_seconds=timeout_seconds,
                    checks=checks,
                    observed_responses=observed,
                )
                try:
                    await isolation_probe.connect()
                    try:
                        await isolation_probe.call(
                            "deepr_get_expert_conversation",
                            {"conversation_id": checkpoint.conversation_id},
                        )
                    except ConversationValidationFailure as exc:
                        _require(
                            exc.code == "not_found",
                            "OWNER_ISOLATION_FAILED",
                            "a second scoped key received a distinguishable or readable result",
                        )
                    else:
                        raise ConversationValidationFailure(
                            "OWNER_ISOLATION_FAILED",
                            "a second scoped key read the conversation",
                        )
                    checks.append(_passed("cross_key_isolation", "a second key received only not found"))
                finally:
                    await isolation_probe.disconnect()

                await probe.close_and_purge(checkpoint)
                expiry_checkpoint = await probe.start_and_replay(
                    message="State the most important retention risk for this local service.",
                    expert=expert,
                    local_model=local_model,
                    retention_days=1,
                    check_prefix="expiry_",
                )
            finally:
                await _disconnect_and_stop(probe, runtime)

            clock.advance(days=2)
            runtime = await _start_runtime(
                port=port,
                database_path=database_path,
                clock=clock,
                key_store=key_store,
                audit_log=audit_log,
                executor_factory=resolved_executor_factory,
            )
            probe = HTTPConversationProbe(
                runtime.endpoint,
                auth_token=secret,
                timeout_seconds=timeout_seconds,
                checks=checks,
                observed_responses=observed,
            )
            try:
                await probe.connect()
                await probe.initialize_and_discover(check_prefix="expiry_restart_")
                await probe.get_expired_and_verify(expiry_checkpoint.conversation_id)
                _require(key_store.revoke(record.key_id), "KEY_REVOCATION_FAILED", "scoped key was not revoked")
                try:
                    await probe.call(
                        "deepr_get_expert_conversation",
                        {"conversation_id": checkpoint.conversation_id},
                    )
                except ConversationValidationFailure as exc:
                    _require(
                        exc.safe_message == "Unauthorized",
                        "KEY_REVOCATION_FAILED",
                        "revoked key did not receive an unauthorized response",
                    )
                else:
                    raise ConversationValidationFailure(
                        "KEY_REVOCATION_FAILED",
                        "revoked key retained conversation access",
                    )
                checks.append(_passed("scoped_key_revocation", "revoked key was rejected on the next request"))
            finally:
                await _disconnect_and_stop(probe, runtime)

            assert_secret_redaction(observed, (secret, other_secret))
            _scan_secret_from_files(root, (secret, other_secret))
            checks.append(
                _passed(
                    "authentication_material_redacted",
                    "responses and temporary durable files did not contain bearer secrets",
                )
            )
            _require(_audit_is_zero_cost(audit_log), "AUDIT_COST_INVALID", "remote audit did not preserve $0 posture")
            checks.append(_passed("remote_audit_zero_cost", "authenticated conversation calls recorded no spend"))
    except ConversationValidationFailure as exc:
        checks.append(_failed("managed_conversation_validation", exc.safe_message))
        error = {"error_code": exc.code, "message": exc.safe_message}
    except (OSError, RuntimeError, ValueError) as exc:
        safe_message = f"managed conversation validation failed: {type(exc).__name__}"
        checks.append(_failed("managed_conversation_validation", safe_message))
        error = {"error_code": "MANAGED_CONVERSATION_VALIDATION_FAILED", "message": safe_message}

    return MCPConversationValidationReport(
        mode="managed_loopback",
        endpoint=endpoint,
        checks=tuple(checks),
        conversation_id=checkpoint.conversation_id if checkpoint else None,
        expert_names=checkpoint.expert_names if checkpoint else (),
        local_model=checkpoint.model if checkpoint else local_model,
        error=error,
    )


__all__ = ["run_managed_loopback_conversation_validation"]
