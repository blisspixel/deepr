"""Orchestrate the four-arm rehearsal and blind its answers without model calls."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from deepr.evals import expert_value_rehearsal as rehearsal_module
from deepr.evals.expert_value_blinding import bind_review_labels, build_blind_assignment, load_cells, reviewer_criteria
from deepr.evals.expert_value_rehearsal import (
    PLAN_SCHEMA,
    RehearsalPlan,
    RehearsalPolicy,
    RehearsalRun,
    plan_from_blueprint,
    tree_digest,
    worker_environment,
)
from tests.unit.test_eval.test_expert_value_sources import Bundle

ARMS = {"fresh_research", "static_history", "compiled_expert", "maintained_expert"}


def make_policy(**overrides: Any) -> RehearsalPolicy:
    payload = {
        "schema_version": "deepr-expert-value-rehearsal-policy-v1",
        "status": "unreviewed_operational_rehearsal",
        "model": "fixture:14b",
        "model_digest": "a" * 64,
        "ollama_base_url": "http://127.0.0.1:11434",
        "num_ctx": 8192,
        "max_output_tokens": 512,
        "temperature": 0.0,
        "seed": 1,
        "think": False,
        "lenses": ["synopsis", "change"],
        "study_max_corpus_chars": 20000,
        "study_chunk_chars": 20000,
        "memory_prefix_max_chars": 4000,
        "max_calls_per_phase": 6,
        "call_timeout_seconds": 60,
        "worker_timeout_seconds": 60,
        **overrides,
    }
    return RehearsalPolicy.model_validate(payload)


def make_plan() -> RehearsalPlan:
    return RehearsalPlan.model_validate(
        {
            "schema_version": PLAN_SCHEMA,
            "cases": [
                {"case_id": "c1", "source_world_id": "world-1", "question": "First question?"},
                {"case_id": "c2", "source_world_id": "world-2", "question": "Second question?"},
            ],
        }
    )


class FakeLauncher:
    """Simulates worker outputs; ``behavior`` can fail or misbehave by worker id."""

    def __init__(self, behavior: Callable[[dict[str, Any], Path], str | None] | None = None) -> None:
        self.specs: list[dict[str, Any]] = []
        self.envs: list[dict[str, str]] = []
        self.behavior = behavior

    def __call__(self, spec_path: Path, env: dict[str, str], cwd: Path, timeout: float) -> int:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        self.specs.append(spec)
        self.envs.append(env)
        out = Path(spec["output_dir"])
        action = self.behavior(spec, cwd) if self.behavior else None
        if action == "timeout":
            return -1
        if action == "crash":
            return 3
        with open(out / "calls.jsonl", "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "request_id": f"x:{spec['worker_id']}:1",
                        "status": "returned",
                        "raw_response": {"prompt_eval_count": 5, "eval_count": 2},
                    }
                )
                + "\n"
            )
        costs = cwd / "costs"
        costs.mkdir(exist_ok=True)
        (costs / "cost_ledger.jsonl").write_text('{"cost_usd": 0}\n', encoding="utf-8")
        status = "failed" if action == "fail" else "completed"
        if status == "completed" and spec["phase"] == "answer":
            (out / "answer.md").write_text(f"Answer to {spec['question']}", encoding="utf-8")
            if action == "touch-memory":
                (Path(spec["prior_checkpoint"]) / "brief.md").write_text("changed", encoding="utf-8")
        elif status == "completed":
            checkpoint = out / "checkpoint"
            checkpoint.mkdir()
            (checkpoint / "brief.md").write_text(f"memory from {spec['worker_id']}", encoding="utf-8")
        package = str(Path(rehearsal_module.__file__).resolve().parents[1])
        (out / "result.json").write_text(
            json.dumps({"status": status, "error_type": "Fake" if action else None, "deepr_package": package})
        )
        return 0 if status == "completed" else 1


def run(tmp_path: Path, launcher: FakeLauncher, **policy: Any) -> tuple[RehearsalRun, dict[str, Any]]:
    bundle = Bundle(tmp_path / "organizer")
    rehearsal = RehearsalRun(
        policy=make_policy(**policy),
        plan=make_plan(),
        index_path=bundle.index_path,
        artifact_root=bundle.root,
        run_root=tmp_path / "run",
        launcher=launcher,
    )
    return rehearsal, rehearsal.execute()


def cell(rehearsal: RehearsalRun, case: str, arm: str) -> dict[str, Any]:
    return next(c for c in rehearsal.cells if c["acceptance_case_id"] == case and c["arm"] == arm)


def test_all_cells_terminal_with_arm_policy_and_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak")
    launcher = FakeLauncher()
    rehearsal, summary = run(tmp_path, launcher)
    assert summary["status"] == "operationally_complete"
    assert summary["terminal_cells"] == summary["planned_cells"] == summary["answered"] == 8
    assert summary["equal_source_inventory_per_world"] is True
    assert summary["consultation_memory_unchanged"] is True
    assert summary["worker_code_matches_orchestrator"] is True
    assert summary["frozen_checkpoints_unchanged"] is True
    assert summary["ledger_reconciled"] is True
    assert summary["canonical_ledger_events"] == summary["model_calls"]
    assert summary["semantic_review_performed"] is False and summary["value_claim"] is None
    assert set(summary["resources_by_phase"]) == {"construct", "maintain", "answer"}
    # Only answer workers see questions; every worker gets its own new input copy.
    for spec in launcher.specs:
        assert ("question" in spec) == (spec["phase"] == "answer")
    assert len({spec["input_copy"] for spec in launcher.specs}) == len(launcher.specs)
    for env in launcher.envs:
        assert "OPENROUTER_API_KEY" not in env
        assert env["PYTHON_DOTENV_DISABLED"] == "1"
    assert cell(rehearsal, "c1", "static_history")["memory_checkpoint"] is None
    assert cell(rehearsal, "c1", "compiled_expert")["memory_checkpoint"] == "compiled-w1"
    assert cell(rehearsal, "c2", "compiled_expert")["memory_checkpoint"] == "compiled-w1"
    assert cell(rehearsal, "c2", "maintained_expert")["memory_checkpoint"] == "maintained-world-2"
    assert cell(rehearsal, "c2", "maintained_expert")["maintenance_status"] == "completed"
    assert cell(rehearsal, "c2", "fresh_research")["memory_checkpoint"] == "fresh-c2"
    phases = [spec["worker_id"] for spec in launcher.specs if spec["phase"] != "answer"]
    assert phases[0] == "construct-compiled" and phases.index("maintain-world-2") > phases.index("construct-fresh-c1")
    events = [json.loads(line)["event"] for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines()]
    assert events[0] == "run_started" and events[-1] == "run_finished"
    assert json.loads((tmp_path / "run" / "run.json").read_text())["application"]["module_sha256"]


def test_failed_maintenance_keeps_last_checkpoint_and_says_so(tmp_path: Path) -> None:
    launcher = FakeLauncher(lambda spec, _cwd: "fail" if spec["worker_id"] == "maintain-world-2" else None)
    rehearsal, summary = run(tmp_path, launcher)
    maintained = cell(rehearsal, "c2", "maintained_expert")
    assert maintained["status"] == "answered"
    assert maintained["memory_checkpoint"] == "compiled-w1"
    assert maintained["maintenance_status"] == "failed_kept_last_checkpoint"
    assert summary["status"] == "operationally_complete"


def test_failed_compiled_construction_blocks_dependent_arms(tmp_path: Path) -> None:
    launcher = FakeLauncher(lambda spec, _cwd: "fail" if spec["worker_id"] == "construct-compiled" else None)
    rehearsal, summary = run(tmp_path, launcher)
    for case in ("c1", "c2"):
        for arm in ("compiled_expert", "maintained_expert"):
            assert cell(rehearsal, case, arm)["status"] == "blocked"
    assert summary["blocked"] == 4 and summary["answered"] == 4
    assert summary["terminal_cells"] == 8


def test_fresh_construction_failure_timeout_and_crash_are_terminal(tmp_path: Path) -> None:
    def behavior(spec: dict[str, Any], _cwd: Path) -> str | None:
        return {
            "construct-fresh-c1": "fail",
            "answer-c2-static_history": "timeout",
            "answer-c2-compiled_expert": "crash",
        }.get(spec["worker_id"])

    rehearsal, summary = run(tmp_path, FakeLauncher(behavior))
    assert cell(rehearsal, "c1", "fresh_research") | {"status": "blocked"} == cell(rehearsal, "c1", "fresh_research")
    assert cell(rehearsal, "c2", "static_history")["reason"] == "WorkerTimeout"
    assert cell(rehearsal, "c2", "compiled_expert")["reason"] == "WorkerExited"
    assert summary["failed"] == 2 and summary["blocked"] == 1 and summary["terminal_cells"] == 8


def test_consultation_write_to_memory_copy_is_detected(tmp_path: Path) -> None:
    launcher = FakeLauncher(
        lambda spec, _cwd: "touch-memory" if spec["worker_id"] == "answer-c1-compiled_expert" else None
    )
    rehearsal, summary = run(tmp_path, launcher)
    assert cell(rehearsal, "c1", "compiled_expert")["memory_unchanged"] is False
    assert summary["consultation_memory_unchanged"] is False
    # The frozen checkpoint itself was never exposed to the worker.
    assert summary["frozen_checkpoints_unchanged"] is True


def test_run_root_and_plan_guards(tmp_path: Path) -> None:
    bundle = Bundle(tmp_path / "organizer")
    (tmp_path / "exists").mkdir()
    with pytest.raises(FileExistsError):
        RehearsalRun(
            policy=make_policy(),
            plan=make_plan(),
            index_path=bundle.index_path,
            artifact_root=bundle.root,
            run_root=tmp_path / "exists",
        )
    with pytest.raises(ValueError, match="outside"):
        RehearsalRun(
            policy=make_policy(),
            plan=make_plan(),
            index_path=bundle.index_path,
            artifact_root=bundle.root,
            run_root=bundle.root / "run",
        )
    bad = RehearsalPlan.model_validate(
        {"schema_version": PLAN_SCHEMA, "cases": [{"case_id": "c", "source_world_id": "world-9", "question": "q"}]}
    )
    with pytest.raises(ValueError, match="outside the preparation index"):
        RehearsalRun(
            policy=make_policy(),
            plan=bad,
            index_path=bundle.index_path,
            artifact_root=bundle.root,
            run_root=tmp_path / "r2",
        )
    dup = RehearsalPlan.model_validate(
        {"schema_version": PLAN_SCHEMA, "cases": [{"case_id": "c", "source_world_id": "world-1", "question": "q"}] * 2}
    )
    with pytest.raises(ValueError, match="unique"):
        RehearsalRun(
            policy=make_policy(),
            plan=dup,
            index_path=bundle.index_path,
            artifact_root=bundle.root,
            run_root=tmp_path / "r3",
        )


def test_policy_refuses_reviewed_status_and_unknown_fields() -> None:
    with pytest.raises(ValueError):
        make_policy(status="reviewed")
    with pytest.raises(ValueError):
        make_policy(paid_fallback=True)


def test_worker_environment_is_allowlisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("DEEPR_DATA_DIR", "C:/real/data")
    env = worker_environment(tmp_path, make_policy())
    assert "GITHUB_TOKEN" not in env
    assert env["DEEPR_DATA_DIR"] == str(tmp_path / "data")
    assert env["OLLAMA_HOST"] == "http://127.0.0.1:11434"


def test_plan_from_blueprint_copies_questions_only() -> None:
    blueprint = {"acceptance_cases": [{"id": "c1", "question": "Q?", "success_criteria": ["secret criterion"]}]}
    placement = {
        "cases": [{"acceptance_case_id": "c1", "source_world_id": "world-1", "evaluation_role_draft": "update"}]
    }
    plan = plan_from_blueprint(blueprint, placement)
    assert "secret criterion" not in plan.model_dump_json() and "update" not in plan.model_dump_json()


def test_tree_digest_changes_with_bytes_and_names(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x")
    first = tree_digest(tmp_path)
    (tmp_path / "a.txt").write_text("y")
    assert tree_digest(tmp_path) != first


# -- blinding ----------------------------------------------------------------


def blinded(tmp_path: Path, launcher: FakeLauncher | None = None) -> tuple[Path, bytes, bytes]:
    run(tmp_path, launcher or FakeLauncher())
    criteria = reviewer_criteria(
        {
            "acceptance_cases": [
                {"id": c, "question": f"{c}?", "success_criteria": ["s"], "failure_conditions": ["f"]}
                for c in ("c1", "c2")
            ]
        },
        {
            "cases": [
                {"acceptance_case_id": "c1", "source_world_id": "world-1"},
                {"acceptance_case_id": "c2", "source_world_id": "world-2"},
            ]
        },
        {"world-1": "2026-01-20T00:00:00Z", "world-2": "2026-02-20T00:00:00Z"},
    )
    packet, key = build_blind_assignment(tmp_path / "run", criteria, rubric={"scale": [0, 1, 2]})
    return tmp_path / "run", packet, key


def test_packet_hides_arms_and_key_maps_every_answer_once(tmp_path: Path) -> None:
    _root, packet, key = blinded(tmp_path)
    text = packet.decode("utf-8")
    for arm in ARMS:
        assert arm not in text
    for forbidden in ("memory_checkpoint", "wall_seconds", "workers/", "compiled-w1"):
        assert forbidden not in text
    parsed_key = json.loads(key)
    assert parsed_key["reviewable_cells"] == 8 == len({e["opaque_id"] for e in parsed_key["entries"]})
    assert {(e["acceptance_case_id"], e["arm"]) for e in parsed_key["entries"]} == {
        (c, a) for c in ("c1", "c2") for a in ARMS
    }
    ids_in_packet = [a["opaque_id"] for case in json.loads(packet)["cases"] for a in case["answers"]]
    assert sorted(ids_in_packet) == sorted(e["opaque_id"] for e in parsed_key["entries"])


def test_non_answered_cells_stay_in_the_key_denominator(tmp_path: Path) -> None:
    launcher = FakeLauncher(lambda spec, _cwd: "fail" if spec["worker_id"] == "answer-c1-static_history" else None)
    _, _packet, key = blinded(tmp_path, launcher)
    parsed = json.loads(key)
    assert parsed["terminal_cells"] == 8 and parsed["reviewable_cells"] == 7
    assert parsed["non_reviewable"][0]["arm"] == "static_history"


def _labels(key: bytes, **override: Any) -> bytes:
    entries = json.loads(key)["entries"]
    labels = [{"opaque_id": e["opaque_id"], "answer_sha256": e["answer_sha256"], "score": 1} for e in entries]
    return json.dumps({"reviewer": {"id": "reviewer-1"}, "labels": labels, **override}).encode()


def test_labels_bind_one_to_one_and_refuse_every_mismatch(tmp_path: Path) -> None:
    root, packet, key = blinded(tmp_path)
    binding = bind_review_labels(root, key, packet, _labels(key))
    assert binding["status"] == "labels_bound" and len(binding["bound"]) == 8
    assert binding["reviewer"]["identity_verified"] is False
    assert binding["semantic_scores_validated"] is False
    labels = json.loads(_labels(key))
    with pytest.raises(ValueError, match="different reviewer packet"):
        bind_review_labels(root, key, packet + b" ", _labels(key))
    with pytest.raises(ValueError, match="no label"):
        bind_review_labels(root, key, packet, json.dumps({**labels, "labels": labels["labels"][1:]}).encode())
    with pytest.raises(ValueError, match="more than one"):
        bind_review_labels(
            root, key, packet, json.dumps({**labels, "labels": labels["labels"] + labels["labels"][:1]}).encode()
        )
    with pytest.raises(ValueError, match="unknown answer id"):
        bind_review_labels(
            root, key, packet, json.dumps({**labels, "labels": [*labels["labels"], {"opaque_id": "zz"}]}).encode()
        )
    stale = [dict(item) for item in labels["labels"]]
    stale[0]["answer_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="different answer bytes"):
        bind_review_labels(root, key, packet, json.dumps({**labels, "labels": stale}).encode())
    with pytest.raises(ValueError, match="reviewer id"):
        bind_review_labels(root, key, packet, json.dumps({**labels, "reviewer": {}}).encode())
    with pytest.raises(ValueError, match="not an assignment key"):
        bind_review_labels(root, packet, packet, _labels(key))
    first = json.loads(key)["entries"][0]
    (root / first["answer_ref"]).write_text("replaced answer", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after assignment"):
        bind_review_labels(root, key, packet, _labels(key))


def test_answer_changed_before_blinding_is_refused(tmp_path: Path) -> None:
    run(tmp_path, FakeLauncher())
    first = load_cells(tmp_path / "run")[0]
    answered = next(c for c in load_cells(tmp_path / "run") if c["status"] == "answered")
    (tmp_path / "run" / answered["answer_ref"]).write_text("edited", encoding="utf-8")
    assert first["schema_version"].endswith("-v1")
    with pytest.raises(ValueError, match="answer bytes changed"):
        build_blind_assignment(tmp_path / "run", {c: {} for c in ("c1", "c2")})


def test_missing_criteria_and_empty_run_are_refused(tmp_path: Path) -> None:
    run(tmp_path, FakeLauncher())
    with pytest.raises(ValueError, match="no reviewer criteria"):
        build_blind_assignment(tmp_path / "run", {})
    (tmp_path / "empty" / "cells").mkdir(parents=True)
    with pytest.raises(ValueError, match="no terminal cells"):
        load_cells(tmp_path / "empty")


def test_arm_identifier_in_answer_text_blocks_the_packet(tmp_path: Path) -> None:
    run(tmp_path, FakeLauncher())
    answered = next(c for c in load_cells(tmp_path / "run") if c["status"] == "answered")
    path = tmp_path / "run" / answered["answer_ref"]
    path.write_text("I am the maintained_expert", encoding="utf-8")
    import hashlib

    cell_path = (
        tmp_path
        / "run"
        / "cells"
        / answered["source_world_id"]
        / answered["acceptance_case_id"]
        / f"{answered['arm']}.json"
    )
    answered["answer_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    cell_path.write_text(json.dumps(answered), encoding="utf-8")
    with pytest.raises(ValueError, match="arm identifiers"):
        build_blind_assignment(tmp_path / "run", {c: {"question": c} for c in ("c1", "c2")})
