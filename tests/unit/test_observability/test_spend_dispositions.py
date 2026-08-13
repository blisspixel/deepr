"""Unit tests for durable spend dispositions (ROADMAP P0 orphan reconciliation)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from deepr.observability.cost_ledger import CostLedger, CostLedgerEvent
from deepr.observability.spend_dispositions import (
    DISPOSITION_EXPECTED_NON_REPORT,
    DISPOSITION_LOST_ARTIFACT,
    apply_suggested_dispositions,
    classify_paid_events,
    event_identity_key,
    event_identity_key_from_ledger_event,
    latest_dispositions_by_event_key,
    record_spend_disposition,
    suggest_disposition_for_orphan,
)


def test_event_identity_prefers_idempotency_key() -> None:
    key = event_identity_key(
        timestamp="2026-07-01T00:00:00+00:00",
        operation="research_job",
        provider="openai",
        model="o3",
        cost_usd=1.0,
        task_id="abc",
        idempotency_key="queue:update_results:abc:1.000000",
    )
    assert key == "idem:queue:update_results:abc:1.000000"


def test_event_identity_hashes_when_no_idempotency_key() -> None:
    a = event_identity_key(
        timestamp="2026-07-01T00:00:00+00:00",
        operation="portrait_generation",
        provider="auto",
        model="",
        cost_usd=0.04,
        task_id="portrait_X",
    )
    b = event_identity_key(
        timestamp="2026-07-01T00:00:00+00:00",
        operation="portrait_generation",
        provider="auto",
        model="",
        cost_usd=0.04,
        task_id="portrait_X",
    )
    c = event_identity_key(
        timestamp="2026-07-01T00:00:00+00:00",
        operation="portrait_generation",
        provider="auto",
        model="",
        cost_usd=0.04,
        task_id="portrait_Y",
    )
    assert a.startswith("hash:")
    assert a == b
    assert a != c


def test_classify_separates_matched_disposed_unexplained(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    (reports / "2026-07-25_topic_a7ae5c65").mkdir(parents=True)
    ledger_path = tmp_path / "cost_ledger.jsonl"
    ledger = CostLedger(ledger_path=ledger_path)
    ledger.record_event(
        operation="research_completion",
        provider="xai",
        cost_usd=0.03,
        model="grok-4-5",
        task_id="research_research-a7ae5c653d8c",
        idempotency_key="matched-1",
    )
    ledger.record_event(
        operation="portrait_generation",
        provider="auto",
        cost_usd=0.04,
        task_id="portrait_Demo",
        idempotency_key="portrait-1",
    )
    ledger.record_event(
        operation="research_job",
        provider="openai",
        cost_usd=1.85,
        model="o3-deep-research",
        task_id="deadbeef-uuid",
        idempotency_key="orphan-1",
    )
    events = ledger.with_locked_accounting_events(list)
    portrait_key = event_identity_key_from_ledger_event(next(e for e in events if e.task_id == "portrait_Demo"))
    record_spend_disposition(
        event_key=portrait_key,
        disposition=DISPOSITION_EXPECTED_NON_REPORT,
        cost_usd=0.04,
        task_id="portrait_Demo",
        operation="portrait_generation",
        provider="auto",
        model="",
        event_timestamp="2026-07-25T00:00:00",
        rationale="portraits do not create report dirs",
        path=tmp_path / "spend_dispositions.jsonl",
    )
    cutoff = datetime.now(UTC) - timedelta(days=45)
    matched, disposed, unexplained = classify_paid_events(
        events,
        [d.name for d in reports.iterdir()],
        cutoff,
        dispositions_by_key=latest_dispositions_by_event_key(tmp_path / "spend_dispositions.jsonl"),
    )
    assert len(matched) == 1
    assert matched[0]["cost_usd"] == 0.03
    assert len(disposed) == 1
    assert disposed[0]["disposition"] == DISPOSITION_EXPECTED_NON_REPORT
    assert len(unexplained) == 1
    assert unexplained[0]["cost_usd"] == 1.85


def test_classify_closes_exact_expert_absorb_settlement_without_report_dir() -> None:
    event = CostLedgerEvent(
        operation="research_completion",
        provider="openai",
        cost_usd=0.010712,
        model="gpt-5-mini",
        task_id="research_expert-absorb-extraction-66f70a3933254459b86da27c2321d829",
        request_id="req_b2e7a5526a954845a360568a35f72469",
        source="expert_absorb.extraction",
        idempotency_key="job:expert-absorb-extraction-66f70a3933254459b86da27c2321d829:completion",
        timestamp=datetime.now(UTC),
    )

    matched, disposed, unexplained = classify_paid_events(
        [event],
        [],
        datetime.now(UTC) - timedelta(days=1),
    )

    assert matched == []
    assert unexplained == []
    assert len(disposed) == 1
    assert disposed[0]["disposition"] == DISPOSITION_EXPECTED_NON_REPORT
    assert disposed[0]["provider_receipt_id"] == event.request_id
    assert "persists expert state" in disposed[0]["rationale"]


def test_expert_absorb_intrinsic_disposition_requires_source_and_task_identity() -> None:
    base = {
        "event_key": "idem:absorb",
        "cost_usd": 0.01,
        "task_id": "research_expert-absorb-extraction-abc",
        "operation": "research_completion",
        "provider": "openai",
        "model": "gpt-5-mini",
        "timestamp": "2026-08-12T23:18:40+00:00",
        "request_id": "req-1",
        "source": "expert_absorb.extraction",
    }

    kind, _rationale, _evidence = suggest_disposition_for_orphan(base)
    assert kind == DISPOSITION_EXPECTED_NON_REPORT

    mismatched = {**base, "task_id": "research_unrelated"}
    mismatched_kind, _mismatched_rationale, _mismatched_evidence = suggest_disposition_for_orphan(mismatched)
    assert mismatched_kind == DISPOSITION_LOST_ARTIFACT


def test_suggest_and_apply_closes_unexplained(tmp_path: Path) -> None:
    entry = {
        "event_key": "idem:portrait-x",
        "cost_usd": 0.04,
        "task_id": "portrait_Coffee",
        "operation": "portrait_generation",
        "provider": "auto",
        "model": "",
        "timestamp": "2026-07-01T00:00:00",
        "request_id": "",
        "source": "experts.portraits",
    }
    kind, rationale, evidence = suggest_disposition_for_orphan(entry)
    assert kind == DISPOSITION_EXPECTED_NON_REPORT
    assert "non-report" in rationale
    assert evidence["operation"] == "portrait_generation"

    research = {
        "event_key": "idem:rj-1",
        "cost_usd": 0.52,
        "task_id": "682b02bf-15ed-4b70-8175-5ec9fd9ea5f0",
        "operation": "research_job",
        "provider": "openai",
        "model": "o3-deep-research",
        "timestamp": "2026-07-01T00:22:22",
        "request_id": "",
        "source": "queue.update_results",
    }
    kind2, _rationale2, evidence2 = suggest_disposition_for_orphan(research)
    assert kind2 == DISPOSITION_LOST_ARTIFACT
    assert evidence2["job_id"] == research["task_id"]

    path = tmp_path / "spend_dispositions.jsonl"
    written = apply_suggested_dispositions([entry, research], path=path)
    assert len(written) == 2
    latest = latest_dispositions_by_event_key(path)
    assert latest["idem:portrait-x"]["disposition"] == DISPOSITION_EXPECTED_NON_REPORT
    assert latest["idem:rj-1"]["disposition"] == DISPOSITION_LOST_ARTIFACT
    assert latest["idem:rj-1"]["job_id"] == research["task_id"]


def test_ledger_event_identity_roundtrip() -> None:
    event = CostLedgerEvent(
        operation="expert_chat",
        provider="openai",
        cost_usd=0.01,
        model="gpt-5.2",
        task_id="chat_Demo_abc",
        idempotency_key="chat-key-1",
        timestamp=datetime(2026, 7, 1, tzinfo=UTC),
    )
    assert event_identity_key_from_ledger_event(event) == "idem:chat-key-1"
