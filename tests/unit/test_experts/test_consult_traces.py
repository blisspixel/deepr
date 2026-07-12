"""Tests for replayable consult trace records."""

from __future__ import annotations

import json
import multiprocessing
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from filelock import FileLock

from deepr.experts import consult_traces as consult_traces_module
from deepr.experts.consult_traces import (
    CONSULT_QUALITY_EVAL_CASE_KIND,
    CONSULT_QUALITY_EVAL_CASE_SCHEMA_VERSION,
    CONSULT_TRACE_CANDIDATES_KIND,
    CONSULT_TRACE_CANDIDATES_SCHEMA_VERSION,
    CONSULT_TRACE_KIND,
    CONSULT_TRACE_SCHEMA_VERSION,
    RECALL_EVAL_CASE_CANDIDATE_KIND,
    RECALL_EVAL_CASE_CANDIDATE_SCHEMA_VERSION,
    ConsultTraceLockTimeoutError,
    _trace_path,
    build_consult_trace,
    build_consult_trace_candidates,
    load_consult_traces,
    record_consult_trace,
    review_consult_traces,
)


def _record_consult_traces_in_process(path: str, worker_id: int, count: int) -> None:
    """Append deterministic traces from a spawned process."""
    for index in range(count):
        record_consult_trace(
            path=Path(path),
            question=f"worker {worker_id} question {index}",
            requested_experts=[f"expert-{worker_id}"],
            max_experts=1,
            budget=0.0,
            payload={
                **_payload(),
                "answer": f"worker-{worker_id}-trace-{index}-" + ("x" * 65_536),
            },
            result={"perspectives": [{}], "synthesis_status": "completed"},
            trace_id=f"consult_worker_{worker_id}_{index}",
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


def _record_with_timeout(path: Path, timeout: float) -> None:
    record_consult_trace(
        path=path,
        lock_timeout_seconds=timeout,
        question="lock contention",
        requested_experts=["A"],
        max_experts=1,
        budget=0.0,
        payload=_payload(),
        result={"perspectives": [{}], "synthesis_status": "completed"},
        trace_id="consult_lock_test",
    )


def test_trace_process_and_file_lock_waits_are_bounded_without_late_write(tmp_path: Path) -> None:
    for name, lock_factory in (
        ("process", lambda path: consult_traces_module._shared_trace_path_lock(path)),
        ("file", lambda path: FileLock(str(path.resolve().with_name(f"{path.name}.lock")))),
    ):
        path = tmp_path / f"{name}.jsonl"
        held_lock = lock_factory(path)
        held_lock.acquire()
        try:
            with pytest.raises(ConsultTraceLockTimeoutError) as raised:
                _record_with_timeout(path, 0.01)
        finally:
            held_lock.release()
        assert raised.value.trace_id == "consult_lock_test"
        assert not path.exists()


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


def test_build_consult_trace_records_effective_explicit_roster_size():
    record = build_consult_trace(
        question="How should four experts collaborate?",
        requested_experts=["A", "B", "C", "D"],
        max_experts=3,
        budget=0.0,
        payload={**_payload(), "experts_consulted": ["A", "B", "C", "D"]},
        result={"perspectives": [{}, {}, {}, {}], "synthesis_status": "completed"},
        trace_id="consult_abcdef123456",
    )

    assert record["input"]["selection_mode"] == "explicit"
    assert record["input"]["requested_max_experts"] == 3
    assert record["input"]["max_experts"] == 4


def test_build_consult_trace_records_selected_order_context_position_metadata():
    payload = _payload()
    payload["perspectives"] = [
        {
            "expert": "A",
            "confidence": 0.9,
            "response": "alpha",
            "context": {"source": "belief_store", "selection": "first"},
        },
        {
            "expert": "B",
            "confidence": 0.8,
            "response": "beta",
            "context": {"source": "belief_store", "selection": "middle"},
        },
        {
            "expert": "C",
            "confidence": 0.7,
            "response": "gamma",
            "context": {"source": "belief_store", "selection": "last"},
        },
    ]

    record = build_consult_trace(
        question="How should long context be checked?",
        requested_experts=["A", "B", "C"],
        max_experts=3,
        budget=0.0,
        payload=payload,
        result={"perspectives": [{}, {}, {}], "synthesis_status": "completed"},
        trace_id="consult_abcdef123456",
        recorded_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )

    positions = [item["context_position"] for item in record["context_packet"]["selected"]]
    assert [item["selected_order_zone"] for item in positions] == ["start", "middle", "end"]
    assert [item["selected_index"] for item in positions] == [0, 1, 2]
    assert {item["selected_count"] for item in positions} == {3}
    assert positions[1]["relative_position"] == 0.5
    assert {item["token_offsets_available"] for item in positions} == {False}
    assert {item["semantic_verdict"] for item in positions} == {False}


def test_build_consult_trace_candidates_routes_middle_context_for_review():
    payload = _payload()
    payload["perspectives"] = [
        {
            "expert": "A",
            "confidence": 0.9,
            "response": "start",
            "context": {"source": "belief_store", "selection": "start", "belief_ids": ["belief_start"]},
        },
        {
            "expert": "B",
            "confidence": 0.8,
            "response": "private middle packet content",
            "context": {"source": "belief_store", "selection": "middle", "belief_ids": ["belief_middle"]},
        },
        {
            "expert": "C",
            "confidence": 0.7,
            "response": "end",
            "context": {"source": "belief_store", "selection": "end", "belief_ids": ["belief_end"]},
        },
    ]
    trace = build_consult_trace(
        question="How should a consult preserve middle evidence?",
        requested_experts=["A", "B", "C"],
        max_experts=3,
        budget=0.0,
        payload=payload,
        result={"perspectives": [{}, {}, {}], "synthesis_status": "completed"},
        trace_id="consult_middlectx",
        recorded_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )

    candidates = build_consult_trace_candidates([trace])

    assert candidates["candidate_count"] == 1
    assert candidates["middle_context_review_count"] == 1
    assert candidates["recall_case_candidate_count"] == 1
    candidate = candidates["candidates"][0]
    assert candidate["reason"] == "middle_context_review"
    assert candidate["severity"] == 2
    assert candidate["middle_context_slot_count"] == 1
    assert candidate["eval_case"]["acceptance_check"] == (
        "future reviewed consult should preserve relevant middle-context evidence when available"
    )
    semantic_case = candidate["semantic_eval_case"]
    assert semantic_case["contract"]["semantic_verdict"] is False
    assert semantic_case["input"]["context_position_zones"] == ["start", "middle", "end"]
    assert semantic_case["input"]["middle_context_slot_count"] == 1
    risk_checks = {item["risk_label"]: item for item in semantic_case["hallucination_risk_checks"]}
    assert risk_checks["long_context_middle_loss"]["requires_semantic_judgment"] is True
    assert "long_context_middle_loss" in semantic_case["failure_labels"]
    recall_candidate = candidate["recall_case_candidate"]
    assert recall_candidate["schema_version"] == RECALL_EVAL_CASE_CANDIDATE_SCHEMA_VERSION
    assert recall_candidate["kind"] == RECALL_EVAL_CASE_CANDIDATE_KIND
    assert recall_candidate["contract"]["requires_operator_relevance_review"] is True
    assert recall_candidate["contract"]["semantic_verdict"] is False
    assert recall_candidate["input"]["candidate_belief_ids"] == ["belief_start", "belief_middle", "belief_end"]
    assert "query" not in recall_candidate["input"]
    assert "private middle packet content" not in json.dumps(candidate)


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
    assert record["status"] == "failed"


def test_build_consult_trace_marks_output_limit_incomplete():
    record = build_consult_trace(
        question="q",
        requested_experts=["A"],
        max_experts=1,
        budget=0.0,
        payload={**_payload(), "synthesis_status": "truncated", "synthesis_stop_reason": "length"},
        result={
            "perspectives": [{}],
            "synthesis_status": "truncated",
            "synthesis_error_type": "OutputLimit",
            "synthesis_stop_reason": "length",
        },
        trace_id="consult_abcdef123456",
        recorded_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    assert record["status"] == "failed"
    event = next(event for event in record["events"] if event["name"] == "synthesis_incomplete")
    assert event["attributes"]["stop_reason"] == "length"
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


def test_record_consult_trace_serializes_same_path_thread_appends(tmp_path, monkeypatch):
    path = tmp_path / "consult_traces.jsonl"
    worker_count = 8
    start = threading.Barrier(worker_count)
    counter_lock = threading.Lock()
    active = 0
    peak_active = 0

    def observed_append(*args, **kwargs):
        nonlocal active, peak_active
        with counter_lock:
            active += 1
            peak_active = max(peak_active, active)
        time.sleep(0.01)
        with counter_lock:
            active -= 1

    monkeypatch.setattr("deepr.experts.consult_traces.append_jsonl_durable", observed_append)

    def record(index):
        start.wait(timeout=5)
        return record_consult_trace(
            path=path,
            question=f"thread question {index}",
            requested_experts=[],
            max_experts=1,
            budget=0.0,
            trace_id=f"consult_thread_{index}",
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        refs = list(executor.map(record, range(worker_count)))

    assert peak_active == 1
    assert {ref["trace_id"] for ref in refs} == {f"consult_thread_{index}" for index in range(worker_count)}


def test_spawned_consult_trace_writers_preserve_every_jsonl_record(tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_record_consult_traces_in_process, args=(str(path), worker_id, 8))
        for worker_id in range(3)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    records = load_consult_traces(path=path, limit=100)
    assert len(records) == 24
    assert {record["trace_id"] for record in records} == {
        f"consult_worker_{worker_id}_{index}" for worker_id in range(3) for index in range(8)
    }
    assert len(path.read_text(encoding="utf-8").splitlines()) == 24


def test_default_trace_path_uses_runtime_data_root(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("DEEPR_DATA_DIR", str(runtime_root))
    monkeypatch.delenv("DEEPR_CONSULT_TRACE_PATH", raising=False)

    record_consult_trace(
        question="isolated trace",
        requested_experts=[],
        max_experts=3,
        budget=0.0,
        trace_id="consult_runtime_root",
    )

    expected = runtime_root / "consult_traces" / "consult_traces.jsonl"
    loaded = load_consult_traces()
    assert expected.exists()
    assert [record["trace_id"] for record in loaded] == ["consult_runtime_root"]


def test_default_trace_path_preserves_per_user_compatibility_without_runtime_override(monkeypatch):
    monkeypatch.delenv("DEEPR_DATA_DIR", raising=False)
    monkeypatch.delenv("DEEPR_CONSULT_TRACE_PATH", raising=False)

    with patch("deepr.experts.consult_traces.default_data_dir", return_value=Path("operator-home")):
        assert _trace_path() == Path("operator-home/consult_traces/consult_traces.jsonl")


def test_load_consult_traces_returns_newest_valid_records(tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    first = build_consult_trace(question="first", requested_experts=[], max_experts=3, budget=0.0)
    second = build_consult_trace(question="second", requested_experts=[], max_experts=3, budget=0.0)
    path.write_text(
        "\n".join([json.dumps(first), "{not-json", json.dumps(second)]) + "\n",
        encoding="utf-8",
    )

    loaded = load_consult_traces(path=path, limit=1)

    assert [record["input"]["question"] for record in loaded] == ["second"]


def test_build_consult_trace_candidates_flags_failed_and_low_context_traces():
    failed = build_consult_trace(
        question="How should consult recover from a synthesis outage?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id="consult_aaaaaaaaaaaa",
        recorded_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    )
    low_context = build_consult_trace(
        question="Where is Deepr weak on current MCP guidance?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        payload={**_payload(), "perspectives": [{"expert": "A", "confidence": 0.2, "response": "thin"}]},
        result={"perspectives": [{}], "synthesis_status": "completed"},
        trace_id="consult_bbbbbbbbbbbb",
        recorded_at=datetime(2026, 6, 26, 12, 1, tzinfo=UTC),
    )

    payload = build_consult_trace_candidates([failed, low_context])

    assert payload["schema_version"] == CONSULT_TRACE_CANDIDATES_SCHEMA_VERSION
    assert payload["kind"] == CONSULT_TRACE_CANDIDATES_KIND
    assert payload["candidate_count"] == 2
    assert payload["failed_trace_count"] == 1
    assert payload["low_context_trace_count"] == 1
    assert payload["semantic_eval_case_count"] == 2
    assert [candidate["reason"] for candidate in payload["candidates"]] == ["failed_consult", "low_context"]
    assert payload["candidates"][0]["gap"]["priority"] == 5
    assert payload["candidates"][0]["eval_case"]["source_trace_id"] == "consult_aaaaaaaaaaaa"
    semantic_case = payload["candidates"][0]["semantic_eval_case"]
    assert semantic_case["schema_version"] == CONSULT_QUALITY_EVAL_CASE_SCHEMA_VERSION
    assert semantic_case["kind"] == CONSULT_QUALITY_EVAL_CASE_KIND
    assert semantic_case["contract"]["semantic_verdict"] is False
    assert semantic_case["contract"]["lexical_verdict_allowed"] is False
    assert semantic_case["contract"]["writes_state"] is False
    assert semantic_case["acceptance_policy"]["never_commits_beliefs"] is True
    assert "output" not in payload["candidates"][0]
    assert "failure" not in payload["candidates"][0]


def test_review_consult_traces_omits_local_path_from_payload(tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    record_consult_trace(
        path=path,
        question="q",
        requested_experts=[],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id="consult_abcdef123456",
    )

    payload = review_consult_traces(path=path)

    assert payload["contract"]["path_exposed"] is False
    assert str(path) not in json.dumps(payload)
