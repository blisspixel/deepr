"""Unit tests for canonical cost ledger."""

from pathlib import Path

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


def test_health_reports_file_and_counts(tmp_path: Path):
    ledger_path = tmp_path / "cost_ledger.jsonl"
    ledger = CostLedger(ledger_path=ledger_path)
    ledger.record_event(operation="research", provider="openai", cost_usd=0.5, source="test")

    health = ledger.get_health()

    assert health["exists"] is True
    assert health["writable"] is True
    assert health["event_count"] == 1
    assert health["total_cost_usd"] == 0.5
