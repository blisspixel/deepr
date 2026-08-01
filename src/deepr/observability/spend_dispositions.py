"""Append-only dispositions for settled spend without surviving report artifacts.

The cost ledger is immutable. When paid events cannot be joined to a report
directory, operators record a durable disposition so ``costs doctor`` can
distinguish expected non-report work (and other closed cases) from still-
unexplained orphans.

Disposition kinds match ROADMAP P0:

- ``failed_or_cancelled`` - work settled conservatively after failure/cancel
- ``expected_non_report`` - intentional non-report surfaces (chat, portraits, ...)
- ``lost_artifact`` - settlement with job identity but missing report artifact
- ``unresolved_provider_evidence`` - needs external receipt before close-out

Only the absence of a disposition keeps spend in the unexplained bucket.
``unresolved_provider_evidence`` is a recorded disposition (not unexplained)
so forensic inventory can be complete while still flagging weak evidence for
review in reports.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.utils.atomic_io import append_jsonl_durable

DISPOSITION_SCHEMA_VERSION = "deepr-spend-disposition-v1"
DISPOSITION_KIND = "deepr.costs.spend_disposition"

DISPOSITION_FAILED_OR_CANCELLED = "failed_or_cancelled"
DISPOSITION_EXPECTED_NON_REPORT = "expected_non_report"
DISPOSITION_LOST_ARTIFACT = "lost_artifact"
DISPOSITION_UNRESOLVED_PROVIDER = "unresolved_provider_evidence"

DISPOSITION_KINDS = frozenset(
    {
        DISPOSITION_FAILED_OR_CANCELLED,
        DISPOSITION_EXPECTED_NON_REPORT,
        DISPOSITION_LOST_ARTIFACT,
        DISPOSITION_UNRESOLVED_PROVIDER,
    }
)

# Operations that never emit research report directories by design.
_EXPECTED_NON_REPORT_OPERATIONS = frozenset(
    {
        "portrait_generation",
        "expert_chat",
        "standard_research_fallback",
        "council_synthesis_backfill",
    }
)


def spend_disposition_log_path(path: Path | None = None) -> Path:
    """Return the append-only disposition log path (cost data dir by default)."""
    if path is not None:
        return path
    from deepr.observability.cost_authority import default_cost_data_dir

    return default_cost_data_dir() / "spend_dispositions.jsonl"


def event_identity_key(
    *,
    timestamp: str,
    operation: str,
    provider: str,
    model: str,
    cost_usd: float,
    task_id: str,
    request_id: str = "",
    source: str = "",
    idempotency_key: str = "",
) -> str:
    """Stable identity for one ledger event without mutating the ledger.

    Prefer a non-empty ledger ``idempotency_key``. Otherwise hash a canonical
    field set so re-imports of the same event map to the same disposition.
    """
    key = str(idempotency_key or "").strip()
    if key:
        return f"idem:{key}"
    payload = "|".join(
        [
            str(timestamp or ""),
            str(operation or ""),
            str(provider or ""),
            str(model or ""),
            f"{float(cost_usd):.6f}",
            str(task_id or ""),
            str(request_id or ""),
            str(source or ""),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"hash:{digest}"


def event_identity_key_from_ledger_event(event: Any) -> str:
    """Build an identity key from a ``CostLedgerEvent`` or mapping-like object."""
    if isinstance(event, Mapping):
        timestamp = str(event.get("timestamp") or "")
        cost = float(event.get("cost_usd") or 0.0)
        return event_identity_key(
            timestamp=timestamp,
            operation=str(event.get("operation") or ""),
            provider=str(event.get("provider") or ""),
            model=str(event.get("model") or ""),
            cost_usd=cost,
            task_id=str(event.get("task_id") or ""),
            request_id=str(event.get("request_id") or ""),
            source=str(event.get("source") or ""),
            idempotency_key=str(event.get("idempotency_key") or ""),
        )
    stamp = getattr(event, "timestamp", "")
    if hasattr(stamp, "isoformat"):
        timestamp = stamp.isoformat()
    else:
        timestamp = str(stamp or "")
    return event_identity_key(
        timestamp=timestamp,
        operation=str(getattr(event, "operation", "") or ""),
        provider=str(getattr(event, "provider", "") or ""),
        model=str(getattr(event, "model", "") or ""),
        cost_usd=float(getattr(event, "cost_usd", 0.0) or 0.0),
        task_id=str(getattr(event, "task_id", "") or ""),
        request_id=str(getattr(event, "request_id", "") or ""),
        source=str(getattr(event, "source", "") or ""),
        idempotency_key=str(getattr(event, "idempotency_key", "") or ""),
    )


@dataclass(frozen=True)
class SpendDispositionRecord:
    """One durable disposition for a settled ledger event."""

    event_key: str
    disposition: str
    cost_usd: float
    task_id: str
    operation: str
    provider: str
    model: str
    event_timestamp: str
    rationale: str
    request_id: str = ""
    job_id: str = ""
    provider_receipt_id: str = ""
    evidence: dict[str, Any] | None = None
    recorded_at: datetime | None = None
    recorded_by: str = "operator"

    def to_dict(self) -> dict[str, Any]:
        if self.disposition not in DISPOSITION_KINDS:
            raise ValueError(f"unknown disposition kind: {self.disposition!r}")
        recorded = self.recorded_at or datetime.now(UTC)
        return {
            "schema_version": DISPOSITION_SCHEMA_VERSION,
            "kind": DISPOSITION_KIND,
            "event_key": self.event_key,
            "disposition": self.disposition,
            "cost_usd": round(float(self.cost_usd), 6),
            "task_id": str(self.task_id or ""),
            "operation": str(self.operation or ""),
            "provider": str(self.provider or ""),
            "model": str(self.model or ""),
            "event_timestamp": str(self.event_timestamp or "")[:32],
            "request_id": str(self.request_id or ""),
            "job_id": str(self.job_id or ""),
            "provider_receipt_id": str(self.provider_receipt_id or ""),
            "rationale": str(self.rationale or ""),
            "evidence": dict(self.evidence or {}),
            "recorded_at": recorded.isoformat(),
            "recorded_by": str(self.recorded_by or "operator"),
        }


def record_spend_disposition(
    *,
    event_key: str,
    disposition: str,
    cost_usd: float,
    task_id: str,
    operation: str,
    provider: str,
    model: str,
    event_timestamp: str,
    rationale: str,
    request_id: str = "",
    job_id: str = "",
    provider_receipt_id: str = "",
    evidence: dict[str, Any] | None = None,
    recorded_by: str = "operator",
    path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append one disposition and return the stored record."""
    if disposition not in DISPOSITION_KINDS:
        raise ValueError(f"unknown disposition kind: {disposition!r}")
    if not str(event_key or "").strip():
        raise ValueError("event_key is required")
    if not str(rationale or "").strip():
        raise ValueError("rationale is required")
    record = SpendDispositionRecord(
        event_key=str(event_key).strip(),
        disposition=disposition,
        cost_usd=float(cost_usd),
        task_id=task_id,
        operation=operation,
        provider=provider,
        model=model,
        event_timestamp=event_timestamp,
        rationale=rationale.strip(),
        request_id=request_id,
        job_id=job_id,
        provider_receipt_id=provider_receipt_id,
        evidence=evidence,
        recorded_at=now or datetime.now(UTC),
        recorded_by=recorded_by,
    ).to_dict()
    append_jsonl_durable(spend_disposition_log_path(path), record, fsync=True)
    return record


def load_spend_dispositions(path: Path | None = None) -> list[dict[str, Any]]:
    """Load all disposition records in append order."""
    resolved = spend_disposition_log_path(path)
    if not resolved.exists():
        return []
    records: list[dict[str, Any]] = []
    with resolved.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("spend disposition line must be a JSON object")
            records.append(payload)
    return records


def latest_dispositions_by_event_key(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return the latest disposition per event key (append-order last wins)."""
    latest: dict[str, dict[str, Any]] = {}
    for record in load_spend_dispositions(path):
        key = str(record.get("event_key") or "").strip()
        if not key:
            continue
        kind = str(record.get("disposition") or "")
        if kind not in DISPOSITION_KINDS:
            continue
        latest[key] = record
    return latest


def classify_paid_events(
    events: Iterable[Any],
    dir_names: list[str],
    cutoff: datetime,
    dispositions_by_key: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split paid events into matched, disposed, and unexplained buckets.

    Matched: report directory fragment join succeeds.
    Disposed: no report match, but a durable disposition exists.
    Unexplained: no report match and no disposition (doctor fails on this sum).
    """
    from datetime import datetime as dt

    dispositions = dispositions_by_key or {}
    matched: list[dict[str, Any]] = []
    disposed: list[dict[str, Any]] = []
    unexplained: list[dict[str, Any]] = []

    for event in events:
        cost = float(getattr(event, "cost_usd", 0.0) or 0.0)
        if cost <= 0:
            continue
        stamp = getattr(event, "timestamp", None)
        if isinstance(stamp, str):
            try:
                stamp = dt.fromisoformat(stamp)
            except ValueError:
                stamp = None
        if stamp is not None and getattr(stamp, "tzinfo", None) is None:
            stamp = stamp.replace(tzinfo=UTC)
        if stamp is not None and stamp < cutoff:
            continue

        task = str(getattr(event, "task_id", "") or "")
        fragment = task.split("research-", 1)[1][:8] if "research-" in task else ""
        request_id = str(getattr(event, "request_id", "") or "")
        operation = str(getattr(event, "operation", "") or "")
        provider = str(getattr(event, "provider", "") or "")
        model = str(getattr(event, "model", "") or "")
        source = str(getattr(event, "source", "") or "")
        event_key = event_identity_key_from_ledger_event(event)
        entry: dict[str, Any] = {
            "timestamp": str(getattr(event, "timestamp", ""))[:19],
            "provider": provider,
            "model": model,
            "cost_usd": round(cost, 6),
            "task_id": task,
            "operation": operation,
            "request_id": request_id,
            "source": source,
            "event_key": event_key,
        }
        if fragment and any(fragment in name for name in dir_names):
            entry["status"] = "matched"
            matched.append(entry)
            continue

        disposition = dispositions.get(event_key)
        if disposition is not None:
            entry["status"] = "disposed"
            entry["disposition"] = str(disposition.get("disposition") or "")
            entry["rationale"] = str(disposition.get("rationale") or "")
            entry["job_id"] = str(disposition.get("job_id") or "")
            entry["provider_receipt_id"] = str(disposition.get("provider_receipt_id") or "")
            disposed.append(entry)
            continue

        entry["status"] = "unexplained"
        unexplained.append(entry)

    return matched, disposed, unexplained


def suggest_disposition_for_orphan(entry: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Return a deterministic (kind, rationale, evidence) for a doctor orphan entry.

    Used by forensic apply helpers and tests. Never contacts a provider.
    """
    operation = str(entry.get("operation") or "")
    task_id = str(entry.get("task_id") or "")
    source = str(entry.get("source") or "")
    evidence: dict[str, Any] = {
        "operation": operation,
        "task_id": task_id,
        "source": source,
    }

    if operation in _EXPECTED_NON_REPORT_OPERATIONS or task_id.startswith("portrait_"):
        return (
            DISPOSITION_EXPECTED_NON_REPORT,
            (
                f"Operation {operation or 'unknown'} is a non-report surface; "
                "settled cost is not expected to map to a research report directory."
            ),
            evidence,
        )

    if task_id.startswith("chat_") or source in {"experts.chat", "web.browser_chat.failure"}:
        return (
            DISPOSITION_EXPECTED_NON_REPORT,
            "Expert chat / chat-path settlement does not emit a research report directory.",
            evidence,
        )

    if operation in {"research_job", "research_completion"}:
        job_id = task_id
        evidence["job_id"] = job_id
        evidence["queue_row"] = "absent_or_unjoined"
        return (
            DISPOSITION_LOST_ARTIFACT,
            (
                "Research settlement has a job identity but no surviving report directory "
                "and no joinable queue row; classified as lost artifact, not rewritten."
            ),
            evidence,
        )

    return (
        DISPOSITION_UNRESOLVED_PROVIDER,
        "No deterministic local rule matched; requires provider receipt or manual review.",
        evidence,
    )


def apply_suggested_dispositions(
    unexplained: Iterable[Mapping[str, Any]],
    *,
    path: Path | None = None,
    recorded_by: str = "forensic-auto",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Record suggested dispositions for each unexplained entry; return records."""
    written: list[dict[str, Any]] = []
    for entry in unexplained:
        kind, rationale, evidence = suggest_disposition_for_orphan(entry)
        job_id = str(evidence.get("job_id") or entry.get("task_id") or "")
        record = record_spend_disposition(
            event_key=str(entry.get("event_key") or ""),
            disposition=kind,
            cost_usd=float(entry.get("cost_usd") or 0.0),
            task_id=str(entry.get("task_id") or ""),
            operation=str(entry.get("operation") or ""),
            provider=str(entry.get("provider") or ""),
            model=str(entry.get("model") or ""),
            event_timestamp=str(entry.get("timestamp") or ""),
            rationale=rationale,
            request_id=str(entry.get("request_id") or ""),
            job_id=job_id if kind == DISPOSITION_LOST_ARTIFACT else "",
            evidence=evidence,
            recorded_by=recorded_by,
            path=path,
            now=now,
        )
        written.append(record)
    return written
