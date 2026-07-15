"""Tests for the durable consult lifecycle journal."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock

from deepr.experts import consult_lifecycle as lifecycle_module
from deepr.experts import consult_lifecycle_storage as lifecycle_storage_module
from deepr.experts.consult_lifecycle import (
    CONSULT_LIFECYCLE_KIND,
    CONSULT_LIFECYCLE_SCHEMA_VERSION,
    TERMINAL_STATES,
    ConsultLifecycle,
    ConsultLifecycleElapsedLimitError,
    ConsultLifecycleJournalError,
    ConsultLifecycleLockTimeoutError,
    ConsultLifecycleTransitionError,
    LifecycleState,
    load_consult_lifecycle_events,
)


def _capacity(*, admission: str = "admitted", provider: str = "ollama", model: str = "qwen3.6") -> dict[str, object]:
    return {
        "source": "local_owned",
        "backend": "local",
        "provider": provider,
        "model": model,
        "admission": admission,
        "live_metered_fallback": False,
    }


def _bounds() -> dict[str, object]:
    return {
        "dispatch_scope": "council_work_item",
        "max_cost_usd": 2.0,
        "max_dispatches": 4,
        "max_output_tokens": 4096,
        "max_context_bytes": 65_536,
    }


def _minimal_bounds() -> dict[str, object]:
    return {
        "dispatch_scope": "council_work_item",
        "max_cost_usd": 2.0,
        "max_dispatches": 4,
    }


def _lineage() -> dict[str, object]:
    return {
        "operation": "one_shot",
        "question_hash": "a" * 64,
        "roster_hash": "b" * 64,
        "snapshot_set_hash": "c" * 64,
    }


def _progress(dispatches: int, tokens: int = 0, context_bytes: int = 0, cost_usd: float = 0.0) -> dict[str, object]:
    return {
        "cost_usd_observed": cost_usd,
        "dispatches_completed": dispatches,
        "output_tokens_observed": tokens,
        "context_bytes_observed": context_bytes,
    }


def _start(path: Path, *, trace_id: str | None = None) -> ConsultLifecycle:
    return ConsultLifecycle.start(
        trace_id=trace_id,
        path=path,
        max_elapsed_seconds=300,
        capacity=_capacity(),
        bounds=_bounds(),
        lineage=_lineage(),
    )


def _assert_no_content_fields(value: Any) -> None:
    if isinstance(value, dict):
        assert "answer" not in value
        assert "private_reasoning" not in value
        assert "reasoning" not in value
        for child in value.values():
            _assert_no_content_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_content_fields(child)


def test_loading_missing_journal_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "consult_lifecycle_events.jsonl"

    assert load_consult_lifecycle_events(path=path) == []
    assert not path.parent.exists()


def test_start_heartbeat_and_finish_append_bounded_events(tmp_path: Path) -> None:
    path = tmp_path / "consult_lifecycle_events.jsonl"
    lifecycle = _start(path)

    heartbeat = lifecycle.heartbeat(
        phase="perspectives",
        progress=_progress(2, tokens=800, context_bytes=1024),
    )
    terminal = lifecycle.finish(
        LifecycleState.COMPLETED,
        reason_code="trace_finalized",
        progress=_progress(4, tokens=1200, context_bytes=2048, cost_usd=0.75),
    )
    events = load_consult_lifecycle_events(trace_id=lifecycle.trace_id, path=path)

    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert [event["event_type"] for event in events] == ["started", "heartbeat", "state_transition"]
    assert events[0]["state"] == "running"
    assert events[0]["previous_state"] is None
    assert heartbeat["remaining"]["dispatches"] == 2
    assert terminal["state"] == "completed"
    assert terminal["remaining"]["dispatches"] == 0
    assert terminal["remaining"]["cost_usd"] == 1.25
    assert terminal["contract"] == {
        "append_only": True,
        "trace_writes_only": True,
        "writes_expert_state": False,
        "writes_graph": False,
        "writes_routing_state": False,
        "answer_text_allowed": False,
        "private_reasoning_allowed": False,
    }
    assert all(event["schema_version"] == CONSULT_LIFECYCLE_SCHEMA_VERSION for event in events)
    assert all(event["kind"] == CONSULT_LIFECYCLE_KIND for event in events)
    _assert_no_content_fields(events)


def test_token_and_context_counters_are_optional_but_enforced_when_supplied(tmp_path: Path) -> None:
    minimal = ConsultLifecycle.start(
        path=tmp_path / "minimal.jsonl",
        max_elapsed_seconds=300,
        capacity=_capacity(),
        bounds=_minimal_bounds(),
        lineage=_lineage(),
    )
    minimal_event = load_consult_lifecycle_events(path=minimal.path)[0]
    assert minimal_event["bounds"] == _minimal_bounds()
    assert minimal_event["progress"] == {
        "cost_usd_observed": 0.0,
        "dispatches_completed": 0,
    }
    assert minimal_event["remaining"] == {
        "cost_usd": 2.0,
        "dispatches": 4,
        "elapsed_ms": 300_000,
    }
    with pytest.raises(ValueError, match=r"requires bounds\.max_output_tokens"):
        minimal.heartbeat(
            phase="perspectives",
            progress={
                "cost_usd_observed": 0.0,
                "dispatches_completed": 1,
                "output_tokens_observed": 1,
            },
        )

    bounded = _start(tmp_path / "optional_counters.jsonl")
    event = bounded.heartbeat(
        phase="perspectives",
        progress=_progress(1, tokens=4096, context_bytes=65_536),
    )
    assert event["remaining"]["output_tokens"] == 0
    assert event["remaining"]["context_bytes"] == 0

    with pytest.raises(ValueError, match="output_tokens_observed exceeds"):
        bounded.heartbeat(phase="perspectives", progress=_progress(1, tokens=4097, context_bytes=65_536))
    with pytest.raises(ValueError, match="context_bytes_observed exceeds"):
        bounded.heartbeat(phase="perspectives", progress=_progress(1, tokens=4096, context_bytes=65_537))


def test_waiting_run_resumes_with_same_trace_and_new_attempt(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.jsonl"
    lifecycle = _start(path, trace_id="consult_resume_case")
    waiting = lifecycle.transition(
        "waiting_capacity",
        phase="preflight",
        reason_code="local_capacity_busy",
        capacity=_capacity(admission="waiting"),
    )

    resumed = ConsultLifecycle.resume(
        trace_id=lifecycle.trace_id,
        path=path,
        capacity=_capacity(admission="admitted"),
    )
    resumed.heartbeat(phase="perspectives", progress=_progress(1, tokens=200))
    resumed.finish("cancelled", reason_code="cancelled_by_host")
    events = load_consult_lifecycle_events(trace_id=lifecycle.trace_id, path=path)

    assert waiting["state"] == "waiting_capacity"
    assert events[2]["event_type"] == "started"
    assert events[2]["previous_state"] == "waiting_capacity"
    assert events[2]["reason_code"] == "resumed"
    assert resumed.trace_id == lifecycle.trace_id
    assert resumed.attempt_id != lifecycle.attempt_id
    assert [event["sequence"] for event in events] == [1, 2, 3, 4, 5]
    assert events[-1]["state"] == "cancelled"


def test_interrupted_run_can_resume_but_stale_attempt_loses_ownership(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.jsonl"
    lifecycle = _start(path)
    lifecycle.transition("interrupted", phase="synthesis", reason_code="stale_heartbeat")
    resumed = ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path)

    with pytest.raises(ConsultLifecycleTransitionError, match="no longer owns"):
        lifecycle.heartbeat(phase="synthesis")

    resumed.finish("failed", reason_code="provider_error")


def test_terminal_state_is_immutable_and_not_resumable(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.jsonl"
    lifecycle = _start(path)
    lifecycle.finish("completed", reason_code="trace_finalized")

    with pytest.raises(ConsultLifecycleTransitionError, match="terminal"):
        lifecycle.heartbeat(phase="trace_finalize")
    with pytest.raises(ConsultLifecycleTransitionError, match="cannot resume"):
        ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path)

    assert len(load_consult_lifecycle_events(trace_id=lifecycle.trace_id, path=path)) == 2


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), 31_536_001])
def test_elapsed_ceiling_must_be_finite_positive_and_bounded(tmp_path: Path, value: float) -> None:
    with pytest.raises(ValueError, match="max_elapsed_seconds"):
        ConsultLifecycle.start(
            path=tmp_path / "lifecycle.jsonl",
            max_elapsed_seconds=value,
            capacity=_capacity(),
            bounds=_bounds(),
            lineage=_lineage(),
        )


def test_bounds_progress_and_capacity_identity_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.jsonl"
    lifecycle = _start(path)

    with pytest.raises(ValueError, match="exceeds"):
        lifecycle.heartbeat(phase="perspectives", progress=_progress(5))
    lifecycle.heartbeat(phase="perspectives", progress=_progress(2))
    with pytest.raises(ConsultLifecycleTransitionError, match="cannot decrease"):
        lifecycle.heartbeat(phase="perspectives", progress=_progress(1))
    with pytest.raises(ConsultLifecycleTransitionError, match="model cannot change"):
        lifecycle.heartbeat(phase="perspectives", capacity=_capacity(model="other-model"))
    with pytest.raises(ValueError, match="reason_code"):
        lifecycle.transition("failed", phase="synthesis", reason_code="Provider failed: secret")
    with pytest.raises(ConsultLifecycleTransitionError, match="finish requires"):
        lifecycle.finish("interrupted", reason_code="host_interrupted")


def test_explicit_empty_progress_and_capacity_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty_fields.jsonl"
    lifecycle = _start(path)

    with pytest.raises(ValueError, match="progress must contain exactly"):
        lifecycle.heartbeat(phase="perspectives", progress={})
    with pytest.raises(ValueError, match="capacity must contain exactly"):
        lifecycle.heartbeat(phase="perspectives", capacity={})

    lifecycle.transition("waiting_capacity", phase="preflight", reason_code="local_capacity_busy")
    with pytest.raises(ValueError, match="progress must contain exactly"):
        ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path, progress={})
    with pytest.raises(ValueError, match="capacity must contain exactly"):
        ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path, capacity={})


@pytest.mark.parametrize("value", [-1.0, float("inf"), float("nan")])
def test_cost_ceiling_must_be_finite_and_non_negative(tmp_path: Path, value: float) -> None:
    bounds = _bounds()
    bounds["max_cost_usd"] = value
    with pytest.raises(ValueError, match="max_cost_usd"):
        ConsultLifecycle.start(
            path=tmp_path / "invalid_cost.jsonl",
            max_elapsed_seconds=300,
            capacity=_capacity(),
            bounds=bounds,
            lineage=_lineage(),
        )


@pytest.mark.parametrize("value", [-0.01, float("inf"), float("nan")])
def test_observed_cost_rejects_invalid_values(tmp_path: Path, value: float) -> None:
    lifecycle = _start(tmp_path / f"invalid_observed_{value!r}.jsonl")
    with pytest.raises(ValueError, match="cost_usd_observed"):
        lifecycle.heartbeat(phase="perspectives", progress=_progress(1, cost_usd=value))


def test_observed_overspend_transitions_to_typed_terminal_state(tmp_path: Path) -> None:
    lifecycle = _start(tmp_path / "observed_overspend.jsonl")

    event = lifecycle.heartbeat(phase="perspectives", progress=_progress(1, cost_usd=2.01))

    assert event["state"] == "failed"
    assert event["reason_code"] == "cost_bound_exceeded"
    assert event["progress"]["cost_usd_observed"] == 2.01
    assert event["remaining"]["cost_usd"] == 0.0


def test_observed_cost_is_monotonic_and_decimal_remaining_is_exact(tmp_path: Path) -> None:
    lifecycle = _start(tmp_path / "cost_progress.jsonl")
    event = lifecycle.heartbeat(phase="perspectives", progress=_progress(1, cost_usd=0.3))
    assert event["remaining"]["cost_usd"] == 1.7

    with pytest.raises(ConsultLifecycleTransitionError, match="cost_usd_observed cannot decrease"):
        lifecycle.heartbeat(phase="perspectives", progress=_progress(1, cost_usd=0.29))


def test_capacity_can_resolve_once_but_cannot_switch_or_clear(tmp_path: Path) -> None:
    path = tmp_path / "capacity_resolution.jsonl"
    lifecycle = ConsultLifecycle.start(
        path=path,
        max_elapsed_seconds=300,
        capacity=_capacity(admission="unknown", provider="", model=""),
        bounds=_bounds(),
        lineage=_lineage(),
    )
    resolved = _capacity(admission="admitted")
    event = lifecycle.heartbeat(phase="preflight", capacity=resolved)
    assert event["capacity"] == resolved

    lifecycle.heartbeat(phase="perspectives", capacity=_capacity(admission="waiting"))
    with pytest.raises(ConsultLifecycleTransitionError, match="model cannot change"):
        lifecycle.heartbeat(phase="perspectives", capacity=_capacity(model="different-model"))
    with pytest.raises(ConsultLifecycleTransitionError, match="provider cannot change"):
        lifecycle.heartbeat(phase="perspectives", capacity=_capacity(provider="", model="qwen3.6"))


def test_resume_enriches_capacity_from_latest_event_only(tmp_path: Path) -> None:
    path = tmp_path / "resume_capacity.jsonl"
    lifecycle = ConsultLifecycle.start(
        path=path,
        max_elapsed_seconds=300,
        capacity=_capacity(admission="unknown", provider="", model=""),
        bounds=_bounds(),
        lineage=_lineage(),
    )
    lifecycle.transition(
        "waiting_capacity",
        phase="preflight",
        reason_code="local_capacity_busy",
        capacity=_capacity(admission="waiting", provider="", model=""),
    )
    resumed = ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path, capacity=_capacity())
    assert load_consult_lifecycle_events(path=path)[-1]["capacity"] == _capacity()

    resumed.transition("interrupted", phase="preflight", reason_code="host_interrupted")
    with pytest.raises(ConsultLifecycleTransitionError, match="model cannot change"):
        ConsultLifecycle.resume(
            trace_id=lifecycle.trace_id,
            path=path,
            capacity=_capacity(model="different-model"),
        )


def test_dispatch_scope_distinguishes_work_items_from_provider_calls(tmp_path: Path) -> None:
    provider_bounds = _bounds()
    provider_bounds["dispatch_scope"] = "provider_call"
    lifecycle = ConsultLifecycle.start(
        path=tmp_path / "provider_calls.jsonl",
        max_elapsed_seconds=300,
        capacity=_capacity(),
        bounds=provider_bounds,
        lineage={**_lineage(), "operation": "deliberation"},
    )
    assert load_consult_lifecycle_events(path=lifecycle.path)[0]["bounds"]["dispatch_scope"] == "provider_call"

    invalid_bounds = _bounds()
    invalid_bounds["dispatch_scope"] = "logical_dispatch"
    with pytest.raises(ValueError, match="dispatch_scope"):
        ConsultLifecycle.start(
            path=tmp_path / "invalid_scope.jsonl",
            max_elapsed_seconds=300,
            capacity=_capacity(),
            bounds=invalid_bounds,
            lineage=_lineage(),
        )


def test_duplicate_trace_id_is_rejected_under_same_journal(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.jsonl"
    _start(path, trace_id="consult_duplicate")

    with pytest.raises(ConsultLifecycleTransitionError, match="already exists"):
        _start(path, trace_id="consult_duplicate")


def test_corrupt_or_gapped_journal_fails_closed(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_text('{"trace_id":', encoding="utf-8")
    with pytest.raises(ConsultLifecycleJournalError, match="not valid JSON"):
        load_consult_lifecycle_events(path=corrupt)

    path = tmp_path / "gapped.jsonl"
    lifecycle = _start(path, trace_id="consult_gapped")
    event = load_consult_lifecycle_events(path=path)[0]
    event["sequence"] = 3
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(ConsultLifecycleJournalError, match="expected 1"):
        load_consult_lifecycle_events(path=path)
    assert lifecycle.trace_id == "consult_gapped"


def test_tampered_content_and_terminal_history_fail_closed(tmp_path: Path) -> None:
    content_path = tmp_path / "content.jsonl"
    _start(content_path)
    content_event = load_consult_lifecycle_events(path=content_path)[0]
    content_event["answer"] = "This field is forbidden"
    content_path.write_text(json.dumps(content_event) + "\n", encoding="utf-8")
    with pytest.raises(ConsultLifecycleJournalError, match="must contain exactly"):
        load_consult_lifecycle_events(path=content_path)

    terminal_path = tmp_path / "terminal.jsonl"
    lifecycle = _start(terminal_path)
    lifecycle.finish("completed", reason_code="trace_finalized")
    events = load_consult_lifecycle_events(path=terminal_path)
    invalid_followup = dict(events[-1])
    invalid_followup.update(
        {
            "sequence": 3,
            "event_type": "heartbeat",
            "state": "running",
            "previous_state": "completed",
            "reason_code": None,
        }
    )
    terminal_path.write_text(
        "".join(f"{json.dumps(event)}\n" for event in [*events, invalid_followup]),
        encoding="utf-8",
    )
    with pytest.raises(ConsultLifecycleJournalError, match="no event may follow terminal state"):
        load_consult_lifecycle_events(path=terminal_path)


def test_tampered_cost_remaining_and_resolved_capacity_fail_closed(tmp_path: Path) -> None:
    cost_path = tmp_path / "tampered_cost.jsonl"
    _start(cost_path)
    cost_event = load_consult_lifecycle_events(path=cost_path)[0]
    cost_event["remaining"]["cost_usd"] = 0.01
    cost_path.write_text(json.dumps(cost_event) + "\n", encoding="utf-8")
    with pytest.raises(ConsultLifecycleJournalError, match="remaining counters"):
        load_consult_lifecycle_events(path=cost_path)

    capacity_path = tmp_path / "tampered_capacity.jsonl"
    lifecycle = ConsultLifecycle.start(
        path=capacity_path,
        max_elapsed_seconds=300,
        capacity=_capacity(admission="unknown", provider="", model=""),
        bounds=_bounds(),
        lineage=_lineage(),
    )
    lifecycle.heartbeat(phase="preflight", capacity=_capacity())
    lifecycle.heartbeat(phase="perspectives", capacity=_capacity())
    capacity_events = load_consult_lifecycle_events(path=capacity_path)
    capacity_events[-1]["capacity"]["model"] = "switched-model"
    capacity_path.write_text(
        "".join(f"{json.dumps(event)}\n" for event in capacity_events),
        encoding="utf-8",
    )
    with pytest.raises(ConsultLifecycleJournalError, match="model cannot change"):
        load_consult_lifecycle_events(path=capacity_path)


def test_concurrent_heartbeats_keep_one_monotonic_sequence(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.jsonl"
    lifecycle = _start(path)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: lifecycle.heartbeat(phase="perspectives"), range(12)))

    events = load_consult_lifecycle_events(trace_id=lifecycle.trace_id, path=path)
    assert [event["sequence"] for event in events] == list(range(1, 14))
    assert len({(event["trace_id"], event["sequence"]) for event in events}) == 13


def test_trace_path_environment_keeps_lifecycle_journal_as_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = tmp_path / "isolated" / "consult_traces.jsonl"
    monkeypatch.delenv("DEEPR_CONSULT_LIFECYCLE_PATH", raising=False)
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(trace_path))
    lifecycle = ConsultLifecycle.start(
        max_elapsed_seconds=300,
        capacity=_capacity(),
        bounds=_bounds(),
        lineage=_lineage(),
    )

    expected = trace_path.parent / "consult_lifecycle_events.jsonl"
    assert lifecycle.path == expected
    assert expected.exists()
    assert not trace_path.exists()


def test_start_persistence_counts_against_active_elapsed_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = {"now": 0.0}
    original_append = lifecycle_storage_module.append_jsonl_durable
    monkeypatch.setattr(lifecycle_module.time, "monotonic", lambda: clock["now"])

    def delayed_append(*args: Any, **kwargs: Any) -> None:
        clock["now"] = 0.4
        original_append(*args, **kwargs)

    monkeypatch.setattr(lifecycle_storage_module, "append_jsonl_durable", delayed_append)
    lifecycle = ConsultLifecycle.start(
        path=tmp_path / "start_elapsed.jsonl",
        max_elapsed_seconds=1.0,
        capacity=_capacity(),
        bounds=_bounds(),
        lineage=_lineage(),
    )

    assert lifecycle.remaining_elapsed_seconds() == pytest.approx(0.6)


def test_heartbeat_at_elapsed_ceiling_writes_one_typed_terminal_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr(lifecycle_module.time, "monotonic", lambda: clock["now"])
    path = tmp_path / "elapsed.jsonl"
    lifecycle = ConsultLifecycle.start(
        path=path,
        max_elapsed_seconds=0.1,
        capacity=_capacity(),
        bounds=_bounds(),
        lineage=_lineage(),
    )
    clock["now"] = 0.1

    with pytest.raises(ConsultLifecycleElapsedLimitError) as raised:
        lifecycle.heartbeat(phase="perspectives")

    assert raised.value.event["reason_code"] == "elapsed_limit"
    assert lifecycle.stop_elapsed_limit(phase="perspectives")["sequence"] == 2
    events = load_consult_lifecycle_events(path=path)
    assert [(event["state"], event["reason_code"]) for event in events] == [
        ("running", None),
        ("failed", "elapsed_limit"),
    ]


def test_resumed_attempt_near_expiry_stops_at_cumulative_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr(lifecycle_module.time, "monotonic", lambda: clock["now"])
    path = tmp_path / "resume_expiry.jsonl"
    lifecycle = ConsultLifecycle.start(
        path=path,
        max_elapsed_seconds=0.1,
        capacity=_capacity(),
        bounds=_bounds(),
        lineage=_lineage(),
    )
    clock["now"] = 0.09
    lifecycle.transition("interrupted", phase="synthesis", reason_code="host_interrupted")
    resumed = ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path)
    clock["now"] = 0.101

    with pytest.raises(ConsultLifecycleElapsedLimitError):
        resumed.heartbeat(phase="synthesis")

    events = load_consult_lifecycle_events(path=path)
    assert events[-1]["state"] == "failed"
    assert events[-1]["reason_code"] == "elapsed_limit"
    assert len([event for event in events if event["state"] in {state.value for state in TERMINAL_STATES}]) == 1


def test_persisted_nonterminal_event_at_elapsed_ceiling_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "tampered_elapsed.jsonl"
    ConsultLifecycle.start(
        path=path,
        max_elapsed_seconds=0.1,
        capacity=_capacity(),
        bounds=_bounds(),
        lineage=_lineage(),
    )
    event = json.loads(path.read_text(encoding="utf-8"))
    event["elapsed_ms"] = 100
    event["remaining"]["elapsed_ms"] = 0
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(ConsultLifecycleJournalError, match="nonterminal event cannot reach"):
        load_consult_lifecycle_events(path=path)


def test_lifecycle_process_and_file_lock_waits_are_bounded_without_late_write(tmp_path: Path) -> None:
    for name, lock_factory in (
        ("process", lambda path: lifecycle_module._shared_path_lock(path)),
        ("file", lambda path: FileLock(str(lifecycle_module._lock_path(path)))),
    ):
        path = tmp_path / f"{name}.jsonl"
        held_lock = lock_factory(path)
        held_lock.acquire()
        try:
            with pytest.raises(ConsultLifecycleLockTimeoutError):
                ConsultLifecycle.start(
                    path=path,
                    max_elapsed_seconds=0.01,
                    capacity=_capacity(),
                    bounds=_bounds(),
                    lineage=_lineage(),
                )
        finally:
            held_lock.release()
        assert not path.exists()


def test_lifecycle_load_resume_and_append_use_bounded_process_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lifecycle_module, "_DEFAULT_LOCK_TIMEOUT_SECONDS", 0.01)
    path = tmp_path / "bounded_operations.jsonl"
    lifecycle = _start(path)
    lifecycle.transition("interrupted", phase="synthesis", reason_code="host_interrupted")
    held_lock = lifecycle_module._shared_path_lock(path)

    held_lock.acquire()
    try:
        with pytest.raises(ConsultLifecycleLockTimeoutError):
            load_consult_lifecycle_events(path=path)
        with pytest.raises(ConsultLifecycleLockTimeoutError):
            ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path)
    finally:
        held_lock.release()
    assert len(load_consult_lifecycle_events(path=path)) == 2

    resumed = ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path)
    held_lock.acquire()
    try:
        with pytest.raises(ConsultLifecycleLockTimeoutError):
            resumed.heartbeat(phase="synthesis")
    finally:
        held_lock.release()
    assert len(load_consult_lifecycle_events(path=path)) == 3
