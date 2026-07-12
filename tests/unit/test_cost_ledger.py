"""Unit tests for canonical cost ledger."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest

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


def _record_live_attribution_shape(ledger: CostLedger) -> None:
    task_id = "research_browser-chat-turn-55b09a61d7a54739837586f76d888e3d"
    target_key = "job:browser-chat-turn-55b09a61d7a54739837586f76d888e3d:completion"
    ledger.record_event(
        operation="research_completion",
        provider="openai",
        model="qwen2.5-coder:32b",
        cost_usd=0.2,
        task_id=task_id,
        session_id=task_id,
        source="web.browser_chat.failure",
        metadata={"estimated_cost_usd": 0.2, "actual_cost_reported": True},
        idempotency_key=target_key,
    )
    ledger.record_event(
        operation="cost_accounting_reconciliation",
        provider="openai",
        model="gpt-5.2",
        cost_usd=0.0,
        task_id=task_id,
        session_id=task_id,
        source="live_validation.reconciliation",
        metadata={
            "supersedes_idempotency_key": target_key,
            "correction_type": "attribution_metadata",
            "observed_outcome": "http_429_no_usage_response",
            "conservative_ceiling_charge_usd": 0.2,
            "actual_cost_reported": False,
            "settlement_basis": "conservative_unaccounted_ceiling",
            "original_model_attribution": "qwen2.5-coder:32b",
            "routed_model_attribution": "gpt-5.2",
            "total_adjustment_usd": 0.0,
        },
        idempotency_key="reconcile:browser-chat-turn-55b09a61d7a54739837586f76d888e3d:attribution-v1",
    )


def test_attributed_events_reconcile_live_browser_chat_shape_without_mutating_raw_ledger(tmp_path: Path):
    ledger = CostLedger(ledger_path=tmp_path / "cost_ledger.jsonl")
    _record_live_attribution_shape(ledger)

    raw = ledger.get_events()
    attributed = ledger.get_attributed_events()

    assert [(event.model, event.cost_usd) for event in raw] == [
        ("qwen2.5-coder:32b", 0.2),
        ("gpt-5.2", 0.0),
    ]
    assert [(event.provider, event.model, event.cost_usd) for event in attributed] == [("openai", "gpt-5.2", 0.2)]
    assert ledger.get_total_cost() == pytest.approx(0.2)
    assert sum(event.cost_usd for event in attributed) == pytest.approx(ledger.get_total_cost())


def test_attribution_reconciliation_applies_after_spend_period_filter(tmp_path: Path):
    ledger = CostLedger(ledger_path=tmp_path / "cost_ledger.jsonl")
    _record_live_attribution_shape(ledger)
    raw = ledger.get_events()
    raw[0].timestamp = datetime.now(UTC) - timedelta(days=10)
    raw[1].timestamp = datetime.now(UTC)
    ledger.ledger_path.write_text(
        "\n".join(json.dumps(event.to_dict()) for event in raw) + "\n",
        encoding="utf-8",
    )

    attributed = ledger.get_attributed_events(
        start_date=datetime.now(UTC) - timedelta(days=11),
        end_date=datetime.now(UTC) - timedelta(days=9),
    )

    assert [(event.model, event.cost_usd) for event in attributed] == [("gpt-5.2", 0.2)]


@pytest.mark.parametrize(
    ("metadata_update", "event_update"),
    [
        ({"schema_version": "unknown"}, {}),
        ({"actual_cost_reported": True}, {}),
        ({"total_adjustment_usd": 0.01}, {}),
        ({"conservative_ceiling_charge_usd": 0.19}, {}),
        ({"original_model_attribution": "other-model"}, {}),
        ({"routed_model_attribution": "other-model"}, {}),
        ({}, {"cost_usd": 0.01}),
    ],
)
def test_malformed_attribution_reconciliation_fails_closed(
    tmp_path: Path,
    metadata_update: dict[str, object],
    event_update: dict[str, object],
) -> None:
    ledger = CostLedger(ledger_path=tmp_path / "cost_ledger.jsonl")
    _record_live_attribution_shape(ledger)
    events = ledger.get_events()
    correction = events[1].to_dict()
    correction["metadata"].update(metadata_update)
    correction.update(event_update)
    ledger.ledger_path.write_text(
        json.dumps(events[0].to_dict()) + "\n" + json.dumps(correction) + "\n",
        encoding="utf-8",
    )

    attributed = ledger.get_attributed_events()

    assert attributed[0].model == "qwen2.5-coder:32b"
    assert sum(event.cost_usd for event in attributed) == pytest.approx(ledger.get_total_cost())


@pytest.mark.parametrize(
    ("provider_metadata", "expected_provider"),
    [
        (
            {
                "original_provider_attribution": "wrong-provider",
                "routed_provider_attribution": "openai",
            },
            "openai",
        ),
        ({}, "wrong-provider"),
    ],
)
def test_provider_reattribution_requires_explicit_v1_provider_fields(
    tmp_path: Path,
    provider_metadata: dict[str, str],
    expected_provider: str,
) -> None:
    ledger = CostLedger(ledger_path=tmp_path / "cost_ledger.jsonl")
    task_id = "provider-fix"
    ledger.record_event(
        "research_completion",
        "wrong-provider",
        0.4,
        model="gpt-5.2",
        task_id=task_id,
        session_id=task_id,
        idempotency_key="provider-target",
    )
    ledger.record_event(
        "cost_accounting_reconciliation",
        "openai",
        0.0,
        model="gpt-5.2",
        task_id=task_id,
        session_id=task_id,
        idempotency_key="provider-correction",
        metadata={
            "schema_version": "deepr-cost-attribution-reconciliation-v1",
            "supersedes_idempotency_key": "provider-target",
            "correction_type": "attribution_metadata",
            "observed_outcome": "provider_attribution_audit",
            "conservative_ceiling_charge_usd": 0.4,
            "actual_cost_reported": False,
            "settlement_basis": "conservative_unaccounted_ceiling",
            "original_model_attribution": "gpt-5.2",
            "routed_model_attribution": "gpt-5.2",
            "total_adjustment_usd": 0.0,
            **provider_metadata,
        },
    )

    assert [(event.provider, event.cost_usd) for event in ledger.get_attributed_events()] == [(expected_provider, 0.4)]


def test_multiple_valid_corrections_for_one_target_are_ambiguous_and_fail_closed(tmp_path: Path):
    ledger = CostLedger(ledger_path=tmp_path / "cost_ledger.jsonl")
    _record_live_attribution_shape(ledger)
    first = ledger.get_events()[1]
    ledger.record_event(
        first.operation,
        first.provider,
        first.cost_usd,
        model="gpt-5.3",
        task_id=first.task_id,
        session_id=first.session_id,
        idempotency_key="second-valid-correction",
        metadata={**first.metadata, "routed_model_attribution": "gpt-5.3"},
    )

    attributed = ledger.get_attributed_events()

    assert [(event.model, event.cost_usd) for event in attributed] == [("qwen2.5-coder:32b", 0.2)]
