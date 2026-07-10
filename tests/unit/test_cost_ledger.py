"""Unit tests for canonical cost ledger."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

from deepr.observability.cost_ledger import CostLedger


def test_record_and_total(tmp_path: Path):
    ledger = CostLedger(ledger_path=tmp_path / "cost_ledger.jsonl")
    ledger.record_event(operation="research", provider="openai", cost_usd=1.25, source="test")
    ledger.record_event(operation="chat", provider="xai", cost_usd=0.75, source="test")

    assert ledger.get_total_cost() == 2.0
    assert len(ledger.get_events()) == 2


def test_idempotency_key_deduplicates(tmp_path: Path):
    ledger = CostLedger(ledger_path=tmp_path / "cost_ledger.jsonl")
    _event, created = ledger.record_event(
        operation="research",
        provider="openai",
        cost_usd=1.0,
        source="test",
        idempotency_key="abc-123",
    )
    assert created is True

    _event2, created2 = ledger.record_event(
        operation="research",
        provider="openai",
        cost_usd=1.0,
        source="test",
        idempotency_key="abc-123",
    )
    assert created2 is False
    assert len(ledger.get_events()) == 1


def test_idempotency_key_deduplicates_preinitialized_instances(tmp_path: Path):
    ledger_path = tmp_path / "cost_ledger.jsonl"
    ledgers = (CostLedger(ledger_path=ledger_path), CostLedger(ledger_path=ledger_path))
    barrier = Barrier(2)

    def record(ledger: CostLedger) -> bool:
        barrier.wait()
        _event, created = ledger.record_event(
            operation="research",
            provider="openai",
            cost_usd=1.0,
            source="test",
            idempotency_key="shared-completion",
        )
        return created

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(executor.map(record, ledgers))

    assert sorted(created) == [False, True]
    assert len(ledgers[0].get_events()) == 1


def test_locked_snapshot_blocks_concurrent_writer_until_operation_commits(tmp_path: Path):
    ledger_path = tmp_path / "cost_ledger.jsonl"
    snapshot_ledger = CostLedger(ledger_path=ledger_path)
    writer_ledger = CostLedger(ledger_path=ledger_path)
    snapshot_entered = Event()
    release_snapshot = Event()
    writer_finished = Event()

    def hold_snapshot() -> None:
        def operation(_events):
            snapshot_entered.set()
            assert release_snapshot.wait(timeout=5)

        snapshot_ledger.with_locked_events(operation)

    def write() -> None:
        assert snapshot_entered.wait(timeout=5)
        writer_ledger.record_event("research", "openai", 0.8, idempotency_key="writer")
        writer_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshot_future = executor.submit(hold_snapshot)
        writer_future = executor.submit(write)
        assert snapshot_entered.wait(timeout=5)
        assert writer_finished.wait(timeout=0.1) is False
        release_snapshot.set()
        snapshot_future.result(timeout=5)
        writer_future.result(timeout=5)

    assert writer_finished.is_set()


def test_health_reports_file_and_counts(tmp_path: Path):
    ledger_path = tmp_path / "cost_ledger.jsonl"
    ledger = CostLedger(ledger_path=ledger_path)
    ledger.record_event(operation="research", provider="openai", cost_usd=0.5, source="test")

    health = ledger.get_health()

    assert health["exists"] is True
    assert health["writable"] is True
    assert health["event_count"] == 1
    assert health["total_cost_usd"] == 0.5
