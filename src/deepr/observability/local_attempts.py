"""Content-free, durable lifecycle receipts for native owned-local generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from deepr.observability.cost_ledger import CostLedger

SOURCE = "local.native_ollama"
SCHEMA = "native-local-attempt-v1"


class LocalAttemptAccountingError(RuntimeError):
    """The native attempt could not be durably recorded."""


class LocalGenerationAttempt:
    """One invocation, including refusal before transport and uncertain interruption."""

    def __init__(self, model: str, *, correlation_id: str = "") -> None:
        self.attempt_id = uuid4().hex
        self.request_id = correlation_id or self.attempt_id
        self.model = model
        self.digest = ""
        self.dispatched = False
        try:
            self.ledger = CostLedger(lock_timeout_seconds=5.0)
        except Exception as error:
            raise LocalAttemptAccountingError(
                "Local attempt ledger is unavailable; no generation was dispatched."
            ) from error
        self._record("requested")

    def dispatch(self, digest: str) -> None:
        self.digest = digest
        self._record("dispatching")
        self.dispatched = True

    def finish(self, status: str, *, tokens_input: int = 0, tokens_output: int = 0, error_type: str = "") -> None:
        self._record(status, tokens_input=tokens_input, tokens_output=tokens_output, error_type=error_type)

    def _record(self, status: str, *, tokens_input: int = 0, tokens_output: int = 0, error_type: str = "") -> None:
        phase = status if status in {"requested", "dispatching"} else "terminal"
        metadata: dict[str, Any] = {
            "schema": SCHEMA,
            "observed_at": datetime.now(UTC).isoformat(),
            "attempt_id": self.attempt_id,
            "status": status,
            "model_digest": self.digest,
            "transport_may_have_started": self.dispatched or status == "dispatching",
        }
        if error_type:
            metadata["error_type"] = error_type
        try:
            self.ledger.record_event(
                operation=f"native_local_{phase}",
                provider="local",
                model=self.model,
                cost_usd=0.0,
                request_id=self.request_id,
                source=SOURCE,
                idempotency_key=f"native-local:{self.attempt_id}:{phase}",
                metadata=metadata,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                lock_timeout_seconds=5.0,
                require_fsync=True,
            )
        except Exception as error:
            raise LocalAttemptAccountingError(f"Local attempt {phase} could not be durably recorded.") from error


def mirror_native_attempt_event(ledger: CostLedger, event: dict[str, Any]) -> bool:
    """Mirror an isolated worker receipt once; leave legacy records to their reader."""
    if (event.get("metadata") or {}).get("schema") != SCHEMA:
        return False
    ledger.record_event(
        operation=event["operation"],
        provider=event["provider"],
        cost_usd=event["cost_usd"],
        model=event["model"],
        tokens_input=event["tokens_input"],
        tokens_output=event["tokens_output"],
        request_id=event["request_id"],
        source=event["source"],
        idempotency_key=event["idempotency_key"],
        metadata=event["metadata"],
        lock_timeout_seconds=5.0,
        require_fsync=True,
    )
    return True


def count_local_attempts(events: list[dict[str, Any]]) -> int:
    """Count native identities and retained legacy single-event attempts separately."""
    native: set[str] = set()
    legacy = 0
    for event in events:
        metadata = event.get("metadata") or {}
        if metadata.get("schema") == SCHEMA:
            identity = metadata.get("attempt_id")
            if not isinstance(identity, str) or not identity:
                raise ValueError("native local receipt is missing its attempt identity")
            native.add(identity)
        else:
            legacy += 1
    return len(native) + legacy
