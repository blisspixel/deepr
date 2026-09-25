"""Orchestrate the four-arm rehearsal and blind its answers without model calls."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
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

QUESTIONS = {"c1": "First question?", "c2": "Second question?"}
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
        if action == "launcher-error":
            raise RuntimeError("launcher broke")
        if action == "interrupt":
            (cwd / "costs").mkdir(exist_ok=True)
            (cwd / "costs" / "cost_ledger.jsonl").write_text(
                json.dumps({"request_id": f"x:{spec['worker_id']}:{spec['attempt_id']}:1", "metadata": {}}) + "\n",
                encoding="utf-8",
            )
            raise KeyboardInterrupt
        if action == "corrupt-result":
            (out / "result.json").write_text("{not json", encoding="utf-8")
            return 0
        with open(out / "calls.jsonl", "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "request_id": f"x:{spec['worker_id']}:{spec['attempt_id']}:1",
                        "status": "returned",
                        "raw_response": {"prompt_eval_count": 5, "eval_count": 2},
                    }
                )
                + "\n"
            )
        costs = cwd / "costs"
        costs.mkdir(exist_ok=True)
        attempts = [
            {
                "request_id": f"x:{spec['worker_id']}:{spec['attempt_id']}:1",
                "cost_usd": 0,
                "metadata": {"prompt_sha256": "p"},
            }
        ]
        if action == "killed-mid-call":
            attempts.append(
                {"request_id": f"x:{spec['worker_id']}:{spec['attempt_id']}:2", "cost_usd": 0, "metadata": {}}
            )
        (costs / "cost_ledger.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in attempts), encoding="utf-8"
        )
        status = "failed" if action == "fail" else "completed"
        if status == "completed" and spec["phase"] == "answer":
            (out / "answer.md").write_text(f"Answer to {spec['question']}", encoding="utf-8")
            if action == "touch-memory":
                (Path(spec["prior_checkpoint"]) / "brief.md").write_text("changed", encoding="utf-8")
        elif status == "completed":
            checkpoint = out / "checkpoint"
            checkpoint.mkdir()
            (checkpoint / "brief.md").write_text(f"memory from {spec['worker_id']}", encoding="utf-8")
        result: dict[str, Any] = {
            "status": status,
            "error_type": "Fake" if action == "fail" else None,
            "module_sha256": {"x": "y"} if action == "other-code" else rehearsal_module.module_hashes(),
            "finished_at": datetime.now(UTC).isoformat(),
        }
        if status == "completed" and spec["phase"] == "answer":
            manifest = json.loads((Path(spec["input_copy"]) / "manifest.json").read_text(encoding="utf-8"))
            question = "a different question" if action == "wrong-question" else spec["question"]
            result.update(
                question_sha256=hashlib.sha256(question.encode("utf-8")).hexdigest(),
                source_digests=[source["sha256"] for source in manifest["sources"]],
                stop_reason="length" if action == "truncated" else "stop",
                answer_truncated=action == "truncated",
            )
        (out / "result.json").write_text(json.dumps(result))
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
    assert cell(rehearsal, "c2", "compiled_expert")["reason"] == "WorkerResultMissing"
    assert summary["failed"] == 2 and summary["blocked"] == 1 and summary["terminal_cells"] == 8
    # Workers that never reported code (timeout, crash) are not counted as a code mismatch.
    assert summary["worker_code_matches_orchestrator"] is True and summary["status"] == "operationally_complete"


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
                {"id": c, "question": QUESTIONS[c], "success_criteria": ["s"], "failure_conditions": ["f"]}
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
        build_blind_assignment(tmp_path / "run", {c: {"question": q} for c, q in QUESTIONS.items()})


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
        build_blind_assignment(tmp_path / "run", {c: {"question": q} for c, q in QUESTIONS.items()})


def test_attempt_killed_mid_call_still_reaches_the_canonical_ledger(tmp_path: Path) -> None:
    from deepr.observability.cost_ledger import CostLedger

    launcher = FakeLauncher(lambda spec, _cwd: "killed-mid-call" if spec["worker_id"] == "construct-compiled" else None)
    _, summary = run(tmp_path, launcher)
    assert summary["attempts_without_completion_record"] == 1
    assert summary["worker_ledger_events"] == summary["canonical_ledger_events"] == summary["model_calls"] + 1
    assert summary["ledger_reconciled"] is True
    events = CostLedger().ledger_path.read_text(encoding="utf-8")
    assert re.search(r"x:construct-compiled:[0-9a-f]{8}:2", events) and "no_completion_record" in events


# -- hardening regressions -----------------------------------------------------


def test_launcher_error_and_corrupt_result_become_failed_cells_and_the_run_continues(tmp_path: Path) -> None:
    def behavior(spec: dict[str, Any], _cwd: Path) -> str | None:
        return {"answer-c1-static_history": "launcher-error", "answer-c2-static_history": "corrupt-result"}.get(
            spec["worker_id"]
        )

    rehearsal, summary = run(tmp_path, FakeLauncher(behavior))
    assert cell(rehearsal, "c1", "static_history")["reason"] == "RuntimeError"
    assert cell(rehearsal, "c2", "static_history")["reason"] == "WorkerResultMissing"
    assert summary["terminal_cells"] == 8 and summary["failed"] == 2
    record = json.loads((tmp_path / "run" / "workers" / "answer-c1-static_history" / "orchestrator.json").read_text())
    assert record["status"] == "failed" and record["error"] == "launcher broke"


def test_question_mismatch_and_truncation_are_recorded(tmp_path: Path) -> None:
    def behavior(spec: dict[str, Any], _cwd: Path) -> str | None:
        return {"answer-c1-compiled_expert": "wrong-question", "answer-c2-compiled_expert": "truncated"}.get(
            spec["worker_id"]
        )

    rehearsal, summary = run(tmp_path, FakeLauncher(behavior))
    assert cell(rehearsal, "c1", "compiled_expert")["reason"] == "QuestionMismatch"
    truncated = cell(rehearsal, "c2", "compiled_expert")
    assert truncated["status"] == "answered" and truncated["answer_truncated"] is True
    assert summary["truncated_answers"] == 1


def test_interrupt_still_mirrors_the_attempt_and_writes_a_summary(tmp_path: Path) -> None:
    from deepr.observability.cost_ledger import CostLedger

    launcher = FakeLauncher(lambda spec, _cwd: "interrupt" if spec["worker_id"] == "answer-c1-static_history" else None)
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, launcher)
    summary = json.loads((tmp_path / "run" / "summary.json").read_text())
    assert summary["status"] == "incomplete" and summary["terminal_cells"] < 8
    assert re.search(r"x:answer-c1-static_history:[0-9a-f]{8}:1", CostLedger().ledger_path.read_text(encoding="utf-8"))
    assert (tmp_path / "run" / "workers" / "answer-c1-static_history" / "orchestrator.json").is_file()


def test_unreconciled_ledger_or_foreign_code_makes_the_run_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = RehearsalRun._mirror_ledger

    def flaky(self: RehearsalRun, worker_dir: Path) -> int:
        if worker_dir.name == "answer-c1-static_history":
            raise OSError("ledger locked")
        return original(self, worker_dir)

    monkeypatch.setattr(RehearsalRun, "_mirror_ledger", flaky)
    _, summary = run(tmp_path / "a", FakeLauncher())
    assert summary["ledger_reconciled"] is False and summary["status"] == "incomplete"
    assert "ledger_reconciled" in summary["failed_checks"]
    monkeypatch.setattr(RehearsalRun, "_mirror_ledger", original)
    launcher = FakeLauncher(lambda spec, _cwd: "other-code" if spec["worker_id"] == "construct-compiled" else None)
    _, summary = run(tmp_path / "b", launcher)
    assert summary["worker_code_matches_orchestrator"] is False and summary["status"] == "incomplete"


def test_canonical_expert_writes_during_the_run_are_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    experts = tmp_path / "experts"
    (experts / "someone").mkdir(parents=True)
    (experts / "someone" / "profile.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(experts))

    def behavior(spec: dict[str, Any], _cwd: Path) -> str | None:
        if spec["worker_id"] == "answer-c2-static_history":
            (experts / "someone" / "profile.json").write_text('{"changed": true}', encoding="utf-8")
        return None

    _, summary = run(tmp_path, FakeLauncher(behavior))
    assert summary["canonical_experts_unchanged"] is False
    assert summary["status"] == "incomplete"


def test_checks_without_evidence_are_none_not_vacuous_passes(tmp_path: Path) -> None:
    _, summary = run(tmp_path, FakeLauncher(lambda spec, _cwd: "fail"))
    assert summary["answered"] == 0
    assert summary["consultation_memory_unchanged"] is None
    assert summary["equal_source_inventory_per_world"] is None
    assert summary["frozen_checkpoints_unchanged"] is None
    assert summary["status"] == "operationally_complete"  # every cell terminal and no check failed
    assert summary["failed"] + summary["blocked"] == 8


def test_case_ids_differing_only_by_letter_case_are_refused(tmp_path: Path) -> None:
    bundle = Bundle(tmp_path / "organizer")
    plan = RehearsalPlan.model_validate(
        {
            "schema_version": PLAN_SCHEMA,
            "cases": [
                {"case_id": "Case", "source_world_id": "world-1", "question": "q"},
                {"case_id": "case", "source_world_id": "world-1", "question": "q"},
            ],
        }
    )
    with pytest.raises(ValueError, match="letter case"):
        RehearsalRun(
            policy=make_policy(),
            plan=plan,
            index_path=bundle.index_path,
            artifact_root=bundle.root,
            run_root=tmp_path / "r",
        )


def test_blind_requires_a_finished_run_and_lists_missing_cells(tmp_path: Path) -> None:
    run(tmp_path, FakeLauncher())
    summary = tmp_path / "run" / "summary.json"
    criteria = {c: {"question": q} for c, q in QUESTIONS.items()}
    removed = next((tmp_path / "run" / "cells").rglob("static_history.json"))
    removed.unlink()
    _, key = build_blind_assignment(tmp_path / "run", criteria)
    parsed = json.loads(key)
    assert parsed["planned_cells"] == 8 and parsed["terminal_cells"] == 7
    assert [e["status"] for e in parsed["non_reviewable"]] == ["missing"]
    summary.unlink()
    with pytest.raises(ValueError, match="no summary"):
        build_blind_assignment(tmp_path / "run", criteria)


def test_harness_markers_are_masked_with_both_digests_in_the_key(tmp_path: Path) -> None:
    run(tmp_path, FakeLauncher())
    answered = next(c for c in load_cells(tmp_path / "run") if c["status"] == "answered")
    path = tmp_path / "run" / answered["answer_ref"]
    path.write_text("Per the Prior Notes (synopsis-0123456789abcdef), yes.", encoding="utf-8")
    answered["answer_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    cell_path = (
        tmp_path
        / "run"
        / "cells"
        / answered["source_world_id"]
        / answered["acceptance_case_id"]
        / f"{answered['arm']}.json"
    )
    cell_path.write_text(json.dumps(answered), encoding="utf-8")
    packet, key = build_blind_assignment(tmp_path / "run", {c: {"question": q} for c, q in QUESTIONS.items()})
    text = packet.decode("utf-8")
    assert "synopsis-0123456789abcdef" not in text and "Prior Notes" not in text
    assert "[harness marker removed]" in text
    entry = next(e for e in json.loads(key)["entries"] if e["answer_sha256"] == answered["answer_sha256"])
    assert entry["masked_markers"] == 2 and entry["display_sha256"] != entry["answer_sha256"]
    assert json.loads(key)["answers_with_masked_markers"] == 1
    assert answered["answer_sha256"] not in text


# -- verified resume -----------------------------------------------------------


def _resumable(tmp_path: Path, launcher: FakeLauncher, **overrides: Any) -> tuple[Bundle, RehearsalRun]:
    bundle = Bundle(tmp_path / "organizer")
    first = RehearsalRun(
        policy=make_policy(),
        plan=make_plan(),
        index_path=bundle.index_path,
        artifact_root=bundle.root,
        run_root=tmp_path / "run",
        launcher=launcher,
    )
    return bundle, first


def _resume(bundle: Bundle, tmp_path: Path, launcher: FakeLauncher, **overrides: Any) -> RehearsalRun:
    return RehearsalRun(
        policy=overrides.get("policy", make_policy()),
        plan=overrides.get("plan", make_plan()),
        index_path=bundle.index_path,
        artifact_root=bundle.root,
        run_root=tmp_path / "run",
        launcher=launcher,
        resume=True,
    )


def test_resume_continues_without_rerunning_finished_phases(tmp_path: Path) -> None:
    from deepr.observability.cost_ledger import CostLedger

    interrupted = FakeLauncher(lambda spec, _cwd: "interrupt" if spec["worker_id"] == "construct-fresh-c2" else None)
    bundle, first = _resumable(tmp_path, interrupted)
    with pytest.raises(KeyboardInterrupt):
        first.execute()
    done_before = {(c["acceptance_case_id"], c["arm"]) for c in first.cells}
    order_before = json.loads(
        next(
            line
            for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines()
            if '"c2"' in line and "case_arm_order" in line
        )
    )["order"]

    fresh = FakeLauncher()
    resumed = _resume(bundle, tmp_path, fresh)
    summary = resumed.execute()
    assert summary["status"] == "operationally_complete" and summary["terminal_cells"] == 8, summary["failed_checks"]
    launched = {spec["worker_id"] for spec in fresh.specs}
    assert "construct-compiled" not in launched and "maintain-world-2" not in launched
    assert "construct-fresh-c2" in launched
    assert not any(f"answer-{case}-{arm}" in launched for case, arm in done_before)
    assert (tmp_path / "run" / "workers" / "construct-fresh-c2.abandoned-1").is_dir()
    ledger_text = CostLedger().ledger_path.read_text(encoding="utf-8")
    assert len(set(re.findall(r"x:construct-fresh-c2:[0-9a-f]{8}:1", ledger_text))) == 2
    events = [json.loads(line) for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events].count("run_started") == 1
    assert any(e["event"] == "run_resumed" for e in events)
    assert any(e["event"] == "worker_abandoned" for e in events)
    assert [e["order"] for e in events if e["event"] == "case_arm_order" and e["case"] == "c2"] == [order_before]
    assert summary["ledger_reconciled"] is True


def test_resume_reuses_a_finished_answer_whose_cell_was_not_written(tmp_path: Path) -> None:
    interrupted = FakeLauncher(lambda spec, _cwd: "interrupt" if spec["worker_id"] == "construct-fresh-c2" else None)
    bundle, first = _resumable(tmp_path, interrupted)
    with pytest.raises(KeyboardInterrupt):
        first.execute()
    lost = next((tmp_path / "run" / "cells").rglob("static_history.json"))
    lost.unlink()
    fresh = FakeLauncher()
    summary = _resume(bundle, tmp_path, fresh).execute()
    assert summary["terminal_cells"] == 8
    assert "answer-c1-static_history" not in {spec["worker_id"] for spec in fresh.specs}
    assert lost.is_file()


@pytest.mark.parametrize("tamper", ["policy", "plan", "code", "answer", "checkpoint", "missing"])
def test_resume_refuses_anything_it_cannot_verify(tmp_path: Path, tamper: str, monkeypatch: pytest.MonkeyPatch) -> None:
    interrupted = FakeLauncher(lambda spec, _cwd: "interrupt" if spec["worker_id"] == "construct-fresh-c2" else None)
    bundle, first = _resumable(tmp_path, interrupted)
    with pytest.raises(KeyboardInterrupt):
        first.execute()
    overrides: dict[str, Any] = {}
    if tamper == "policy":
        overrides["policy"] = make_policy(seed=2)
    elif tamper == "plan":
        overrides["plan"] = RehearsalPlan.model_validate(
            {
                "schema_version": PLAN_SCHEMA,
                "cases": [{"case_id": "c1", "source_world_id": "world-1", "question": "Other?"}],
            }
        )
    elif tamper == "code":
        monkeypatch.setattr(rehearsal_module, "module_hashes", lambda: {"changed": "x"})
    elif tamper == "answer":
        answered = next(c for c in first.cells if c["status"] == "answered")
        (tmp_path / "run" / answered["answer_ref"]).write_text("edited", encoding="utf-8")
    elif tamper == "checkpoint":
        (tmp_path / "run" / "checkpoints" / "compiled-w1" / "brief.md").write_text("edited", encoding="utf-8")
    else:
        import shutil

        shutil.rmtree(tmp_path / "run")
    with pytest.raises(ValueError):
        _resume(bundle, tmp_path, FakeLauncher(), **overrides)


def test_resume_refuses_a_finished_run(tmp_path: Path) -> None:
    bundle, first = _resumable(tmp_path, FakeLauncher())
    first.execute()
    with pytest.raises(ValueError, match="already finished"):
        _resume(bundle, tmp_path, FakeLauncher())


def test_a_second_writer_is_refused_while_a_run_holds_its_root(tmp_path: Path) -> None:
    interrupted = FakeLauncher(lambda spec, _cwd: "interrupt" if spec["worker_id"] == "construct-fresh-c2" else None)
    bundle, first = _resumable(tmp_path, interrupted)
    with pytest.raises(ValueError, match="another process"):
        _resume(bundle, tmp_path, FakeLauncher())
    with pytest.raises(KeyboardInterrupt):
        first.execute()
    # The interrupted run released the root, so a verified resume may now take it.
    assert _resume(bundle, tmp_path, FakeLauncher()).execute()["status"] == "operationally_complete"
