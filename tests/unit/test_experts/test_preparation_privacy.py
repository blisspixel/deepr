"""Prepared global projections retain identities without retaining private text."""

import hashlib
import json

import pytest

from deepr.experts import preparation_privacy as privacy
from deepr.experts.consult_traces import (
    _semantic_eval_case_for_trace,
    build_consult_trace_candidates,
    load_consult_traces,
    load_consult_traces_by_id,
    record_consult_trace,
)

PRIVATE = "PRIVATE_QUESTION_ANSWER_PERSPECTIVE_ERROR"


def test_capacity_is_a_fixed_shape_with_idempotent_identity_hashes():
    projected = privacy.safe_prepared_capacity(
        {"source": "local", "backend": "local", "model": PRIVATE, "provider": PRIVATE, "admission": "admitted"}
    )
    assert set(projected) == {"source", "backend", "provider", "model", "admission", "live_metered_fallback"}
    assert PRIVATE not in json.dumps(projected)
    assert projected["model"] == "sha256:" + hashlib.sha256(PRIVATE.encode()).hexdigest()
    assert privacy.safe_prepared_capacity(projected) == projected


@pytest.mark.parametrize("field,value", [("source", PRIVATE), ("admission", PRIVATE), ("live_metered_fallback", PRIVATE)])
def test_capacity_refuses_noncode_metadata(field, value):
    with pytest.raises(ValueError):
        privacy.safe_prepared_capacity({field: value})


@pytest.mark.parametrize("failed", [False, True])
def test_prepared_trace_never_calls_legacy_builder_or_copies_nested_private_text(tmp_path, monkeypatch, failed):
    from deepr.experts import consult_traces

    def forbidden(**kwargs):
        raise AssertionError("legacy trace builder received private preparation")

    monkeypatch.setattr(consult_traces, "build_consult_trace", forbidden)
    path = tmp_path / "global.jsonl"
    trace_id = "consult_0123456789ab"
    reference = record_consult_trace(
        path=path,
        protected_preparation=True,
        preparation_reference={"operation_id": "op_" + "b" * 32, "owner_sha256": "a" * 64, "private": PRIVATE},
        question=PRIVATE,
        requested_experts=[PRIVATE],
        max_experts=1,
        budget=0.0,
        payload={"answer": PRIVATE, "perspectives": [{"context": {"prompt": PRIVATE}}], "cost_usd": 0.0},
        result={"synthesis_status": "failed" if failed else "completed", "synthesis": PRIVATE},
        capacity={"synthesis_backend": "local", "provider": PRIVATE, "model": PRIVATE},
        failure={"stage": PRIVATE, "message": PRIVATE, "error_type": PRIVATE} if failed else None,
        trace_id=trace_id,
    )
    assert reference["protected_preparation"] is True
    assert reference["content_availability"] == "protected"
    assert PRIVATE not in path.read_text()
    record = load_consult_traces(path=path)[0]
    assert record["input"]["question_hash"] == hashlib.sha256(PRIVATE.encode()).hexdigest()
    assert record["status"] == ("failed" if failed else "completed")
    assert record["output"]["content_availability"] == "protected"
    assert "answer" not in record["output"] and "question" not in record["input"]
    assert load_consult_traces_by_id({trace_id}, path=path) == [record]
    candidates = build_consult_trace_candidates([record])
    assert candidates["candidate_count"] == 0 and candidates["unavailable_trace_count"] == 1
    with pytest.raises(ValueError, match="unavailable"):
        _semantic_eval_case_for_trace(record, "failed_consult")


def test_preclaim_failure_trace_explicitly_has_no_private_content_reference():
    trace = privacy.build_prepared_consult_trace(
        question=PRIVATE, requested_experts=[PRIVATE], max_experts=1, budget=0.0,
        failure={"message": PRIVATE},
    )
    assert trace["content_availability"] == "unavailable"
    assert trace["preparation"] == {} and PRIVATE not in json.dumps(trace)


def test_operation_reference_requires_owner_binding():
    assert privacy.safe_preparation_reference({"operation_id": "op_" + "b" * 32}) == {}
    assert privacy.safe_preparation_reference({"operation_id": "op_" + "b" * 32, "owner_sha256": "a" * 64}) == {
        "operation_id": "op_" + "b" * 32, "owner_sha256": "a" * 64,
    }


def test_cli_scope_ignores_username_environment_and_stdio_is_process_scoped(monkeypatch):
    monkeypatch.setattr(privacy, "current_os_principal", lambda: "actual-token-user")
    first = privacy.preparation_cli_scope()
    monkeypatch.setenv("USERNAME", "forged-user")
    monkeypatch.setenv("USER", "another-forged-user")
    assert privacy.preparation_cli_scope() == first
    stdio = privacy.preparation_stdio_scope()
    assert privacy.preparation_stdio_scope() == stdio
    assert stdio != first
    monkeypatch.setattr(privacy, "_STDIO_PROCESS_NONCE", "new-process-nonce")
    assert privacy.preparation_stdio_scope() != stdio


def test_actual_os_principal_is_stable_when_environment_names_change(monkeypatch):
    principal = privacy.current_os_principal()
    monkeypatch.setenv("USERNAME", PRIVATE)
    monkeypatch.setenv("USER", PRIVATE)
    monkeypatch.setenv("LOGNAME", PRIVATE)
    assert privacy.current_os_principal() == principal
    assert PRIVATE not in principal
