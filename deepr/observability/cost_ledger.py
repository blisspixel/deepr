"""Canonical append-only cost ledger for Deepr."""

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def default_cost_data_dir() -> Path:
    """Resolve the cost-data directory.

    Honors DEEPR_COST_DATA_DIR so deployments can relocate cost state and -
    critically - so the test suite can isolate itself: the default is
    CWD-relative, and unit tests running from the repo root were appending
    fabricated cost events to the user's real canonical ledger.
    """
    base = os.environ.get("DEEPR_COST_DATA_DIR", "").strip()
    return Path(base) if base else Path("data/costs")


@dataclass
class CostLedgerEvent:
    """Single immutable cost event in the canonical ledger."""

    operation: str
    provider: str
    cost_usd: float
    timestamp: datetime = field(default_factory=_utc_now)
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    task_id: str = ""
    session_id: str = ""
    request_id: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    agent_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "timestamp": self.timestamp.isoformat(),
            "operation": self.operation,
            "provider": self.provider,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "source": self.source,
            "metadata": self.metadata,
            "idempotency_key": self.idempotency_key,
        }
        if self.agent_id:
            d["agent_id"] = self.agent_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostLedgerEvent":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else _utc_now(),
            operation=data.get("operation", ""),
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            cost_usd=float(data.get("cost_usd", 0.0)),
            tokens_input=int(data.get("tokens_input", 0)),
            tokens_output=int(data.get("tokens_output", 0)),
            task_id=data.get("task_id", ""),
            session_id=data.get("session_id", ""),
            request_id=data.get("request_id", ""),
            source=data.get("source", ""),
            metadata=data.get("metadata", {}) or {},
            idempotency_key=data.get("idempotency_key", ""),
            agent_id=data.get("agent_id", ""),
        )


class CostLedger:
    """Append-only cost ledger with idempotency support."""

    def __init__(self, ledger_path: Path | None = None):
        self.ledger_path = ledger_path or default_cost_data_dir() / "cost_ledger.jsonl"
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._idempotency_keys: set[str] = set()
        self._load_idempotency_index()

    def _load_idempotency_index(self) -> None:
        if not self.ledger_path.exists():
            return
        try:
            with open(self.ledger_path, encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        key = data.get("idempotency_key")
                        if key:
                            self._idempotency_keys.add(key)
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        # Surface ledger corruption — the previous silent
                        # ``continue`` let partial-write lines drop out of
                        # the idempotency index, which then allowed the
                        # same operation to be billed twice on retry.
                        logger.error(
                            "Corrupted cost ledger line %d at %s: %s",
                            line_no,
                            self.ledger_path,
                            exc,
                        )
                        continue
        except OSError as e:
            logger.warning("Failed loading cost ledger index: %s", e)

    def record_event(
        self,
        operation: str,
        provider: str,
        cost_usd: float,
        model: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        task_id: str = "",
        session_id: str = "",
        request_id: str = "",
        source: str = "",
        metadata: dict[str, Any] | None = None,
        idempotency_key: str = "",
        agent_id: str = "",
    ) -> tuple[CostLedgerEvent, bool]:
        if cost_usd < 0:
            logger.warning("Negative cost_usd=%s for %s/%s, clamping to 0", cost_usd, operation, provider)
            cost_usd = 0.0

        event = CostLedgerEvent(
            operation=operation,
            provider=provider,
            cost_usd=cost_usd,
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            task_id=task_id,
            session_id=session_id,
            request_id=request_id,
            source=source,
            metadata=metadata or {},
            idempotency_key=idempotency_key,
            agent_id=agent_id,
        )

        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency_keys:
                return event, False

            # Durable append: flush + fsync before releasing the lock so
            # a crash between write() and process exit can't truncate the
            # last record of the canonical cost ledger.
            line = json.dumps(event.to_dict(), ensure_ascii=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    # fsync is unavailable on some filesystems / network
                    # mounts. We've already buffered the line; downgrade
                    # silently rather than failing the API call.
                    pass

            if idempotency_key:
                self._idempotency_keys.add(idempotency_key)

        return event, True

    def get_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        source: str | None = None,
    ) -> list[CostLedgerEvent]:
        events: list[CostLedgerEvent] = []
        if not self.ledger_path.exists():
            return events

        with open(self.ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = CostLedgerEvent.from_dict(data)
                except (json.JSONDecodeError, TypeError, ValueError):
                    # Intent: one corrupted cost ledger line must not prevent loading the rest of the billing history; partial results still allow usage queries and caps.
                    continue

                if source and event.source != source:
                    continue
                if start_date and event.timestamp < start_date:
                    continue
                if end_date and event.timestamp > end_date:
                    continue
                events.append(event)

        return events

    def get_total_cost(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        source: str | None = None,
    ) -> float:
        return sum(e.cost_usd for e in self.get_events(start_date=start_date, end_date=end_date, source=source))

    def get_health(self) -> dict[str, Any]:
        writable = False
        error = ""
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8"):
                pass
            writable = True
        except OSError as e:
            error = str(e)

        events = self.get_events()
        return {
            "path": str(self.ledger_path),
            "exists": self.ledger_path.exists(),
            "writable": writable,
            "event_count": len(events),
            "total_cost_usd": sum(e.cost_usd for e in events),
            "latest_timestamp": events[-1].timestamp.isoformat() if events else None,
            "idempotency_keys_loaded": len(self._idempotency_keys),
            "error": error,
        }
