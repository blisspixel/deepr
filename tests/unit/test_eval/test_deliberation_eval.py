"""Tests for the zero-cost bounded deliberation fixture evaluator."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from deepr.evals.deliberation import (
    DELIBERATION_EVAL_KIND,
    DELIBERATION_EVAL_SCHEMA_VERSION,
    FROZEN_ONE_SHOT_BASELINE,
    FROZEN_STRUCTURED_DELIBERATION,
    maximum_dispatch_count,
    run_deliberation_eval,
    write_deliberation_eval_report,
)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _isolate_all_runtime_roots(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = root / "runtime"
    monkeypatch.setenv("DEEPR_DATA_DIR", str(runtime))
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(runtime / "experts"))
    monkeypatch.setenv("DEEPR_REPORTS_PATH", str(runtime / "reports"))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(runtime / "costs"))
    monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(runtime / "capacity"))
    monkeypatch.setenv("DEEPR_QUEUE_DB_PATH", str(runtime / "queue" / "research_queue.db"))
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(runtime / "traces" / "consult.jsonl"))
    monkeypatch.setenv("DEEPR_CONSULT_LIFECYCLE_PATH", str(runtime / "traces" / "lifecycle.jsonl"))
    monkeypatch.setenv("DEEPR_JSONL_PATH", str(runtime / "logs" / "jobs.jsonl"))
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("USERPROFILE", str(root / "home"))


@pytest.mark.parametrize(
    ("participant_count", "mode", "expected"),
    [(1, "default", 3), (3, "default", 7), (1, "deep", 5), (3, "deep", 11)],
)
def test_maximum_dispatch_count(participant_count: int, mode: str, expected: int) -> None:
    assert maximum_dispatch_count(participant_count, mode) == expected


@pytest.mark.parametrize(
    ("participant_count", "mode"),
    [(0, "default"), (-1, "default"), (True, "default"), (1.5, "default"), (1, "wide")],
)
def test_maximum_dispatch_count_rejects_invalid_inputs(participant_count: object, mode: str) -> None:
    with pytest.raises(ValueError):
        maximum_dispatch_count(participant_count, mode)  # type: ignore[arg-type]


def test_deliberation_eval_builtin_structural_cases_pass() -> None:
    report = run_deliberation_eval()
    data = report.to_dict()

    assert data["schema_version"] == DELIBERATION_EVAL_SCHEMA_VERSION
    assert data["kind"] == DELIBERATION_EVAL_KIND
    assert data["cost_usd"] == 0.0
    assert data["semantic_review_status"] == "unreviewed"
    assert data["contract"]["provider_calls"] == 0
    assert data["contract"]["backend_calls"] == 0
    assert data["contract"]["expert_store_reads"] == 0
    assert data["contract"]["live_metered_fallback"] is False
    assert data["contract"]["authority"] == "proposal_only"
    assert data["contract"]["accepted"] is False
    assert data["contract"]["review_required"] is True
    assert "writes_state" not in data["contract"]
    assert data["contract"]["report_write_requires_opt_in"] is True
    assert report.total_cases == 11
    assert report.failed_cases == 0
    assert report.score == 1.0
    assert {outcome.case_id for outcome in report.outcomes} == {
        "frozen_baseline_contract",
        "round_one_independence",
        "exact_turn_lineage",
        "targeted_challenge_cardinality",
        "position_and_dissent_reference_preservation",
        "typed_stop_states",
        "local_only_no_fallback",
        "finite_resource_bounds",
        "proposal_only_review_gate",
        "adversarial_text_is_inert",
        "semantic_review_boundary",
    }
    assert all(outcome.to_dict()["semantic_verdict"] is False for outcome in report.outcomes)


def test_default_fixture_ends_with_skeptic_and_reserves_synthesis_for_deep_mode() -> None:
    assert FROZEN_ONE_SHOT_BASELINE.turns[-1].role == "proposal_synthesis"
    assert FROZEN_STRUCTURED_DELIBERATION.mode == "default"
    assert FROZEN_STRUCTURED_DELIBERATION.turns[-1].role == "evidence_seeking_skeptic"
    assert all(turn.role != "proposal_synthesis" for turn in FROZEN_STRUCTURED_DELIBERATION.turns)
    fixture_outcome = next(
        outcome for outcome in run_deliberation_eval().outcomes if outcome.case_id == "frozen_baseline_contract"
    )
    assert fixture_outcome.detail["deep_final_role"] == "proposal_synthesis"


def test_deliberation_eval_does_not_write_files_or_open_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _isolate_all_runtime_roots(tmp_path, monkeypatch)
    runtime_root = tmp_path / "runtime"
    expert_root = runtime_root / "experts" / "sentinel"
    expert_root.mkdir(parents=True)
    (expert_root / "beliefs.json").write_text('{"sentinel": true}', encoding="utf-8")
    marker = tmp_path / "existing.txt"
    marker.write_text("preserve", encoding="utf-8")
    before = _snapshot(tmp_path)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("frozen evaluator must not open network connections")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    run_deliberation_eval()

    assert _snapshot(tmp_path) == before


def test_deliberation_report_write_is_confined_to_requested_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _isolate_all_runtime_roots(tmp_path, monkeypatch)
    marker = tmp_path / "existing.txt"
    marker.write_text("preserve", encoding="utf-8")
    output_dir = tmp_path / "allowed" / "benchmarks"
    report = run_deliberation_eval()
    before = _snapshot(tmp_path)

    path = write_deliberation_eval_report(report, output_dir=output_dir)
    files = _snapshot(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert set(files) - set(before) == {path.relative_to(tmp_path).as_posix()}
    assert all(files[name] == content for name, content in before.items())
    assert path.parent == output_dir
    assert path.name.startswith("deliberation_eval_")
    assert data["schema_version"] == DELIBERATION_EVAL_SCHEMA_VERSION
    assert data["kind"] == DELIBERATION_EVAL_KIND
    assert data["semantic_review_status"] == "unreviewed"
