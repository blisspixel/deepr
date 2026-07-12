"""Tests for deepr.backends.quota_ledger - observed plan quota state.

All tests use explicit temp paths and fixed timestamps. No vendor CLI, network,
or provider API is touched.
"""

from __future__ import annotations

import multiprocessing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerEvent,
    QuotaWindowKind,
    latest_quota_by_backend,
    load_quota_events,
    quota_ledger_path,
    record_quota_event,
    summarize_quota_state,
)

T0 = datetime(2026, 6, 17, tzinfo=UTC)


def _record_events_in_process(path: str, worker_id: int, count: int) -> None:
    """Append deterministic events from a spawned process."""
    for index in range(count):
        record_quota_event(
            _event(
                backend_id=f"worker-{worker_id}",
                timestamp=T0 + timedelta(microseconds=index),
                remaining=float(index),
            ),
            path=Path(path),
        )


def _event(
    backend_id: str = "codex",
    event_type: QuotaEventType = QuotaEventType.USAGE_OBSERVED,
    *,
    timestamp: datetime = T0,
    account_id: str = "",
    remaining: float | None = 12.5,
) -> QuotaLedgerEvent:
    return QuotaLedgerEvent(
        backend_id=backend_id,
        account_id=account_id,
        event_type=event_type,
        timestamp=timestamp,
        cost_model=CostModel.ROLLING_WINDOW,
        window_kind=QuotaWindowKind.ROLLING_5H,
        units_used=2.0,
        units_remaining=remaining,
        unit_name="compute_units",
        remaining_confidence=QuotaConfidence.OBSERVED,
        reset_at=timestamp + timedelta(hours=3),
        detail="fixture",
    )


class TestQuotaLedger:
    def test_records_and_reads_event(self, tmp_path):
        p = tmp_path / "quota.jsonl"
        event = _event()
        assert record_quota_event(event, path=p) == event

        loaded = load_quota_events(p)
        assert loaded == [event]
        assert p.read_text(encoding="utf-8").endswith("\n")

    def test_missing_file_is_empty(self, tmp_path):
        assert load_quota_events(tmp_path / "missing.jsonl") == []

    def test_corrupt_line_skipped_not_fatal(self, tmp_path):
        p = tmp_path / "quota.jsonl"
        record_quota_event(_event(), path=p)
        with p.open("a", encoding="utf-8") as f:
            f.write("{ not json\n")

        assert load_quota_events(p) == [_event()]

    def test_requires_backend_id(self, tmp_path):
        with pytest.raises(ValueError, match="backend_id"):
            record_quota_event(_event(backend_id=" "), path=tmp_path / "quota.jsonl")

    def test_instances_share_one_process_local_path_lock(self, tmp_path):
        path = tmp_path / "quota.jsonl"

        assert QuotaLedger(path)._lock is QuotaLedger(path)._lock

    def test_spawned_writers_preserve_every_jsonl_event(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        context = multiprocessing.get_context("spawn")
        processes = [
            context.Process(target=_record_events_in_process, args=(str(path), worker_id, 12)) for worker_id in range(3)
        ]

        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=20)
            assert process.exitcode == 0

        events = load_quota_events(path)
        assert len(events) == 36
        assert {event.backend_id for event in events} == {"worker-0", "worker-1", "worker-2"}
        assert len(path.read_text(encoding="utf-8").splitlines()) == 36


class TestSummary:
    def test_latest_by_backend_uses_timestamp_not_append_order(self, tmp_path):
        p = tmp_path / "quota.jsonl"
        newer = _event(timestamp=T0 + timedelta(hours=1), remaining=4.0)
        older = _event(timestamp=T0, event_type=QuotaEventType.EXHAUSTED, remaining=0.0)
        record_quota_event(newer, path=p)
        record_quota_event(older, path=p)

        latest = latest_quota_by_backend(p)
        assert latest[("codex", "")] == newer

    def test_summary_marks_exhausted_and_quarantined(self, tmp_path):
        p = tmp_path / "quota.jsonl"
        record_quota_event(_event("codex", QuotaEventType.EXHAUSTED, remaining=0.0), path=p)
        record_quota_event(_event("kiro-cli", QuotaEventType.QUARANTINED, remaining=None), path=p)

        summaries = {s.backend_id: s for s in summarize_quota_state(p)}
        assert summaries["codex"].exhausted
        assert not summaries["codex"].quarantined
        assert summaries["kiro-cli"].quarantined
        assert summaries["kiro-cli"].to_dict()["event_type"] == "quarantined"

    def test_account_id_keeps_accounts_independent(self, tmp_path):
        p = tmp_path / "quota.jsonl"
        record_quota_event(_event("agy", account_id="personal", remaining=1), path=p)
        record_quota_event(_event("agy", account_id="work", remaining=5), path=p)

        keys = [state.key for state in summarize_quota_state(p)]
        assert keys == ["agy:personal", "agy:work"]


class TestDataDir:
    def test_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path / "cap"))
        assert quota_ledger_path() == tmp_path / "cap" / "quota_ledger.jsonl"


class TestEventShape:
    def test_event_to_from_dict(self):
        event = _event()
        assert QuotaLedgerEvent.from_dict(event.to_dict()) == event

    def test_unknown_enum_values_fall_back(self):
        data = _event().to_dict()
        data["event_type"] = "future_event"
        data["window_kind"] = "future_window"
        data["remaining_confidence"] = "future_confidence"
        event = QuotaLedgerEvent.from_dict(data)
        assert event.event_type == QuotaEventType.USAGE_OBSERVED
        assert event.window_kind == QuotaWindowKind.UNKNOWN
        assert event.remaining_confidence == QuotaConfidence.UNKNOWN

    def test_legacy_string_bool_and_bad_metadata_parse_safely(self):
        data = _event().to_dict()
        data["overage_enabled"] = "false"
        data["metadata"] = ["not", "a", "dict"]
        event = QuotaLedgerEvent.from_dict(data)
        assert event.overage_enabled is False
        assert event.metadata == {}

    def test_class_api_matches_function_api(self, tmp_path):
        p = tmp_path / "quota.jsonl"
        ledger = QuotaLedger(p)
        event = ledger.record_event(_event())
        assert ledger.get_events() == [event]
