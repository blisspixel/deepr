"""Tests for deepr.backends.quota_ledger - observed plan quota state.

All tests use explicit temp paths and fixed timestamps. No vendor CLI, network,
or provider API is touched.
"""

from __future__ import annotations

import json
import multiprocessing
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread

import pytest

from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerDurabilityError,
    QuotaLedgerEvent,
    QuotaLedgerIdempotencyConflict,
    QuotaLedgerLockTimeout,
    QuotaLedgerReadError,
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

    @pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
    def test_rejects_invalid_quota_numeric_values(self, tmp_path, value):
        with pytest.raises((TypeError, ValueError), match="units_remaining"):
            record_quota_event(
                replace(_event(), units_remaining=value),
                path=tmp_path / "quota.jsonl",
            )

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

    def test_idempotency_key_prevents_duplicate_append(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        event = replace(_event(), idempotency_key="plan-attempt-1")

        first = QuotaLedger(path).record_event(event)
        second = QuotaLedger(path).record_event(event)

        assert first == second
        assert QuotaLedger(path).get_events() == [event]

    def test_idempotency_key_rejects_conflicting_observation(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        first = replace(_event("codex"), idempotency_key="plan-attempt-1")
        conflicting = replace(
            _event("claude", QuotaEventType.EXHAUSTED, remaining=0.0),
            idempotency_key="plan-attempt-1",
        )
        ledger = QuotaLedger(path)
        ledger.record_event(first)

        with pytest.raises(QuotaLedgerIdempotencyConflict, match="conflicts"):
            ledger.record_event(conflicting)

        assert ledger.get_events() == [first]

    def test_idempotency_replay_detects_later_historical_conflict(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        first = replace(_event("codex"), idempotency_key="plan-attempt-1")
        conflicting = replace(_event("claude"), idempotency_key="plan-attempt-1")
        ledger = QuotaLedger(path)
        ledger.record_event(first)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(conflicting.to_dict()) + "\n")

        with pytest.raises(QuotaLedgerIdempotencyConflict, match="conflicts"):
            ledger.record_event(first)

    def test_append_fails_closed_on_torn_json_but_read_only_view_remains_tolerant(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        first = replace(_event(), idempotency_key="plan-attempt-1")
        ledger = QuotaLedger(path)
        ledger.record_event(first)
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"backend_id": "codex"')

        assert ledger.get_events() == [first]
        with pytest.raises(QuotaLedgerReadError, match="invalid record at line 2"):
            ledger.record_event(replace(_event(), idempotency_key="plan-attempt-2"))

        assert path.read_text(encoding="utf-8").count("\n") == 1

    def test_append_fails_closed_on_malformed_matching_record(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        path.write_text(
            json.dumps({"idempotency_key": "plan-attempt-1", "metadata": []}) + "\n",
            encoding="utf-8",
        )

        with pytest.raises(QuotaLedgerReadError, match="invalid record"):
            QuotaLedger(path).record_event(replace(_event(), idempotency_key="plan-attempt-1"))

        assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    def test_append_fails_closed_on_partial_object_without_idempotency_key(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        path.write_text(
            json.dumps(
                {
                    "timestamp": T0.isoformat(),
                    "backend_id": "codex",
                    "event_type": "usage_observed",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with pytest.raises(QuotaLedgerReadError, match="invalid record"):
            QuotaLedger(path).record_event(replace(_event(), idempotency_key="plan-attempt-2"))

        assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    @pytest.mark.parametrize(
        ("field_name", "malformed_value"),
        [
            ("units_used", "2.0"),
            ("overage_enabled", "false"),
            ("metadata", ["not", "an", "object"]),
        ],
    )
    def test_append_fails_closed_instead_of_coercing_malformed_canonical_fields(
        self,
        tmp_path,
        field_name,
        malformed_value,
    ):
        path = tmp_path / "quota.jsonl"
        data = _event().to_dict()
        data.pop("idempotency_key")
        data[field_name] = malformed_value
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")

        with pytest.raises(QuotaLedgerReadError, match="invalid record"):
            QuotaLedger(path).record_event(replace(_event(), idempotency_key="plan-attempt-2"))

    def test_append_fails_closed_on_nonstandard_json_constant_in_nested_metadata(
        self,
        tmp_path,
    ):
        path = tmp_path / "quota.jsonl"
        data = _event().to_dict()
        data.pop("idempotency_key")
        data["metadata"] = {"nested": {"invalid": float("nan")}}
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")

        with pytest.raises(QuotaLedgerReadError, match="invalid record"):
            QuotaLedger(path).record_event(replace(_event(), idempotency_key="plan-attempt-2"))

    def test_required_fsync_failure_replays_without_duplicate_after_resync(
        self,
        monkeypatch,
        tmp_path,
    ):
        path = tmp_path / "quota.jsonl"
        event = replace(_event(), idempotency_key="plan-attempt-1")
        real_fsync = os.fsync
        calls = 0

        def fail_once(fd: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("fixture durability failure")
            real_fsync(fd)

        monkeypatch.setattr("deepr.backends.quota_ledger.os.fsync", fail_once)
        ledger = QuotaLedger(path)
        with pytest.raises(QuotaLedgerDurabilityError, match="durability barrier"):
            ledger.record_event(event, require_fsync=True)

        assert len(path.read_text(encoding="utf-8").splitlines()) == 1
        assert ledger.record_event(event, require_fsync=True) == event
        assert calls == 2
        assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    def test_required_fsync_replay_keeps_failing_closed_until_durable(
        self,
        monkeypatch,
        tmp_path,
    ):
        path = tmp_path / "quota.jsonl"
        event = replace(_event(), idempotency_key="plan-attempt-1")

        def fail_fsync(_fd: int) -> None:
            raise OSError("fixture durability failure")

        monkeypatch.setattr("deepr.backends.quota_ledger.os.fsync", fail_fsync)
        ledger = QuotaLedger(path)
        with pytest.raises(QuotaLedgerDurabilityError):
            ledger.record_event(event, require_fsync=True)
        with pytest.raises(QuotaLedgerDurabilityError):
            ledger.record_event(event, require_fsync=True)

        assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    def test_bounded_lock_timeout_does_not_wait_indefinitely(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        holder = QuotaLedger(path)
        entered = Event()
        release = Event()

        def hold_lock() -> None:
            with holder._locked():
                entered.set()
                assert release.wait(timeout=5)

        thread = Thread(target=hold_lock)
        thread.start()
        assert entered.wait(timeout=5)
        try:
            bounded = QuotaLedger(path, lock_timeout_seconds=0.05)
            with pytest.raises(QuotaLedgerLockTimeout, match="configured timeout"):
                bounded.record_event(_event())
        finally:
            release.set()
            thread.join(timeout=5)
        assert not thread.is_alive()


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
