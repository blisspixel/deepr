"""Tests for replayable consult trace records."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from deepr.experts.consult_traces import (
    CONSULT_TRACE_KIND,
    CONSULT_TRACE_SCHEMA_VERSION,
    build_consult_trace,
    record_consult_trace,
)


def _payload() -> dict:
    return {
        "schema_version": "deepr-consult-v1",
        "kind": "deepr.expert.consult",
        "question": "q",
        "answer": "synthesized",
        "experts_consulted": ["A"],
        "perspectives": [
            {
                "expert": "A",
                "domain": "alpha",
                "confidence": 0.9,
                "response": "answer",
                "context": {"source": "belief_store", "selection": "query_overlap"},
            }
        ],
        "agreements": [],
        "disagreements": [],
        "cost_usd": 0.0,
    }


def test_build_consult_trace_records_replay_context():
    record = build_consult_trace(
        question="How should consult improve?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        payload=_payload(),
        result={"perspectives": [{}], "synthesis_status": "completed"},
        capacity={
            "synthesis_backend": "local",
            "provider": "local",
            "model": "qwen",
            "live_metered_fallback": False,
        },
        trace_id="consult_abcdef123456",
        recorded_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    )

    assert record["schema_version"] == CONSULT_TRACE_SCHEMA_VERSION
    assert record["kind"] == CONSULT_TRACE_KIND
    assert record["trace_id"] == "consult_abcdef123456"
    assert record["input"]["question_hash"]
    assert record["capacity"]["live_metered_fallback"] is False
    assert record["context_packet"]["selected"][0]["context"]["source"] == "belief_store"
    assert {check["name"] for check in record["checks"]} >= {
        "consult_payload_contract",
        "owned_capacity_no_metered_fallback",
        "synthesis_status",
    }


def test_build_consult_trace_makes_synthesis_failure_first_class():
    record = build_consult_trace(
        question="q",
        requested_experts=[],
        max_experts=3,
        budget=0.0,
        payload={**_payload(), "answer": "Synthesis unavailable."},
        result={"perspectives": [{}], "synthesis_status": "failed", "synthesis_error_type": "RuntimeError"},
        trace_id="consult_abcdef123456",
        recorded_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    )

    assert any(event["name"] == "synthesis_failed" for event in record["events"])
    assert next(check for check in record["checks"] if check["name"] == "synthesis_status")["status"] == "failed"


def test_record_consult_trace_appends_jsonl_and_returns_public_ref(tmp_path):
    path = tmp_path / "consult_traces.jsonl"

    ref = record_consult_trace(
        path=path,
        question="q",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        payload=_payload(),
        result={"perspectives": [{}], "synthesis_status": "completed"},
        trace_id="consult_abcdef123456",
    )

    data = json.loads(path.read_text(encoding="utf-8").strip())
    assert data["trace_id"] == "consult_abcdef123456"
    assert ref == {
        "schema_version": CONSULT_TRACE_SCHEMA_VERSION,
        "kind": CONSULT_TRACE_KIND,
        "trace_id": "consult_abcdef123456",
        "status": "completed",
        "recorded": True,
        "checks_ran": [check["name"] for check in data["checks"]],
    }
