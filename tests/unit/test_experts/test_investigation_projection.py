from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from deepr.experts.investigation.inputs import compile_input_bundle
from deepr.experts.investigation.models import (
    PLAN_KIND,
    PLAN_SCHEMA_VERSION,
    InvestigationBounds,
    InvestigationContractError,
    LearningMode,
    Phase,
    ProtocolMode,
    RunState,
    sha256_json,
    validate_plan,
)
from deepr.experts.investigation.projection import (
    ARTIFACT_PAGE_KIND,
    EVENT_PAGE_KIND,
    FOLLOW_UP_KIND,
    FORK_LINEAGE_KIND,
    STATUS_PROJECTION_KIND,
    preview_follow_up,
    preview_fork,
    project_artifacts,
    project_events,
    project_status,
)
from deepr.experts.investigation.store import (
    InvestigationNotFoundError,
    InvestigationStorageError,
    InvestigationStore,
)

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"
NOW = "2026-07-17T00:00:00+00:00"


def _plan(tmp_path: Path, *, run_id: str = "inv_proj_test") -> dict[str, Any]:
    snapshot = {"expert": {"name": "Fixture Expert"}, "summary": {"claim_count": 0}}
    bundle = compile_input_bundle(input_root=tmp_path, created_at=NOW)
    bounds = InvestigationBounds.for_plan(
        expert_count=1,
        protocol=ProtocolMode.INDEPENDENT,
        learning=LearningMode.OFF,
    )
    material: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "run_id": run_id,
        "created_at": NOW,
        "question": "Fixture question",
        "experts": [
            {
                "name": "Fixture Expert",
                "domain": "fixtures",
                "snapshot_sha256": sha256_json(snapshot),
                "snapshot_source_position": "fixture",
                "snapshot": snapshot,
                "readiness": {},
            }
        ],
        "protocol": "independent",
        "learning": "off",
        "input_bundle": bundle,
        "capacity": {"class": "local", "model": "fixture", "fallback": "none"},
        "retrieval": {"max_queries_per_expert": 4, "max_pages_per_expert": 8},
        "bounds": bounds.to_dict(),
        "learning_contract": {
            "mode": "off",
            "source_pack_evidence_only": True,
            "factual_belief_source_pack_evidence_only": True,
            "dialogue_is_evidence": False,
            "perspective_proposals_from_expert_positions": False,
            "perspective_proposals_are_factual_beliefs": False,
            "perspective_truth_or_novelty_verified": False,
            "domain_relevance_required": False,
            "domain_relevance_judgment": "not_applicable",
            "writes_expert_state": False,
            "writes_beliefs": False,
            "writes_graph": False,
            "human_reviewed": False,
        },
    }
    material["plan_sha256"] = sha256_json(material)
    return validate_plan(material)


def _validate(name: str, payload: dict[str, Any]) -> None:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def _snapshot_run(store: InvestigationStore, run_id: str) -> dict[str, str]:
    root = store.run_dir(run_id)
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.endswith(".lock")
    }


def test_status_projection_is_read_only_content_free_and_schema_valid(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path))
    before = _snapshot_run(store, "inv_proj_test")

    payload = project_status(store, "inv_proj_test")

    assert payload["kind"] == STATUS_PROJECTION_KIND
    assert payload["projection_only"] is True
    assert payload["semantic_acceptance"] is False
    assert payload["mutates_run"] is False
    assert payload["cost_usd"] == 0.0
    encoded = json.dumps(payload)
    assert "run_dir" not in encoded
    assert str(store.run_dir("inv_proj_test")) not in encoded
    assert payload["capability_snapshot"]["creates_authority"] is False
    assert payload["control_evidence"]["canonical_store"] is False
    _validate("investigation-status-projection-v1.json", payload)
    _validate("investigation-capability-snapshot-v1.json", payload["capability_snapshot"])
    _validate("investigation-control-evidence-v1.json", payload["control_evidence"])
    assert _snapshot_run(store, "inv_proj_test") == before


def test_event_page_redacts_paths_and_replays_from_sequence_zero(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path))
    store.append_event(
        "inv_proj_test",
        event_type="artifact_committed",
        phase=Phase.CHARTERS,
        status=RunState.RUNNING,
        detail={
            "logical_key": "charter:fixture",
            "path": "artifacts/charters/fixture.json",
            "prompt": "secret prompt text",
            "sha256": "a" * 64,
        },
    )
    store.append_event(
        "inv_proj_test",
        event_type="phase_entered",
        phase=Phase.RESEARCH,
        status=RunState.RUNNING,
        detail={},
    )

    first = project_events(store, "inv_proj_test", after_sequence=0, limit=1)
    rest = project_events(store, "inv_proj_test", after_sequence=first["next_sequence"], limit=20)
    replay = project_events(store, "inv_proj_test", after_sequence=0, limit=50)

    assert first["kind"] == EVENT_PAGE_KIND
    assert first["count"] == 1
    assert first["complete"] is False
    assert rest["complete"] is True
    assert [event["sequence"] for event in replay["events"]] == [1, 2, 3]
    leaked = json.dumps(replay)
    assert "artifacts/charters/fixture.json" not in leaked
    assert "secret prompt text" not in leaked
    assert "path" not in replay["events"][1]["detail"]
    assert replay["events"][1]["detail"]["logical_key"] == "charter:fixture"
    _validate("investigation-event-page-v1.json", first)
    _validate("investigation-event-page-v1.json", replay)


def test_artifact_page_omits_bodies_and_local_paths(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path))
    reference = store.write_artifact(
        "inv_proj_test",
        phase=Phase.CHARTERS,
        key="fixture",
        payload={"schema_version": "fixture-v1", "kind": "fixture", "secret": "body-text"},
        max_disk_bytes=1_000_000,
    )
    state = store.load_state("inv_proj_test")
    artifacts = dict(state.get("artifacts") or {})
    artifacts["charter:fixture"] = reference
    state["artifacts"] = artifacts
    store.save_state("inv_proj_test", state, expected_version=int(state["version"]))

    payload = project_artifacts(store, "inv_proj_test")
    encoded = json.dumps(payload)

    assert payload["kind"] == ARTIFACT_PAGE_KIND
    assert payload["read_content"] is False
    assert payload["count"] == 1
    assert payload["artifacts"][0]["name"] == "charter:fixture"
    assert payload["artifacts"][0]["sha256"] == reference["sha256"]
    assert "body-text" not in encoded
    assert reference["path"] not in encoded
    assert "path" not in payload["artifacts"][0]
    _validate("investigation-artifact-page-v1.json", payload)


def test_projection_denies_cross_run_access_and_unknown_runs(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path, run_id="inv_alpha"))
    store.create(_plan(tmp_path, run_id="inv_beta"))
    store.append_event(
        "inv_beta",
        event_type="phase_entered",
        phase=Phase.RESEARCH,
        status=RunState.RUNNING,
        detail={"logical_key": "only-beta"},
    )

    alpha = project_events(store, "inv_alpha")
    beta = project_events(store, "inv_beta")

    assert all(event["run_id"] == "inv_alpha" for event in alpha["events"])
    assert "only-beta" not in json.dumps(alpha)
    assert any(event["detail"].get("logical_key") == "only-beta" for event in beta["events"])
    with pytest.raises(InvestigationNotFoundError, match="not found"):
        project_status(store, "inv_missing")
    with pytest.raises(InvestigationStorageError, match="invalid investigation run id"):
        project_status(store, "../inv_alpha")


def test_follow_up_and_fork_are_preview_only(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    created = store.create(_plan(tmp_path))

    with pytest.raises(InvestigationStorageError, match="terminal parent"):
        preview_follow_up(store, "inv_proj_test")

    terminal = dict(created)
    terminal["state"] = RunState.COMPLETED.value
    terminal["phase"] = Phase.COMPLETE.value
    store.save_state("inv_proj_test", terminal, expected_version=int(created["version"]))
    before = _snapshot_run(store, "inv_proj_test")

    follow = preview_follow_up(store, "inv_proj_test")
    fork = preview_fork(store, "inv_proj_test", phase="research")

    assert follow["kind"] == FOLLOW_UP_KIND
    assert fork["kind"] == FORK_LINEAGE_KIND
    assert follow["implemented"] is False
    assert fork["creates_run"] is False
    assert follow["mutates_parent"] is False
    assert fork["mutates_parent"] is False
    _validate("investigation-follow-up-v1.json", follow)
    _validate("investigation-fork-lineage-v1.json", fork)
    with pytest.raises(InvestigationContractError, match="published investigation phase"):
        preview_fork(store, "inv_proj_test", phase="not-a-phase")
    assert _snapshot_run(store, "inv_proj_test") == before
    assert not (store.root / "inv_child").exists()


def test_projection_schema_rejects_semantic_acceptance_and_paths(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path))
    payload = project_status(store, "inv_proj_test")
    schema = json.loads((SCHEMA_DIR / "investigation-status-projection-v1.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    widened = json.loads(json.dumps(payload))
    widened["semantic_acceptance"] = True
    assert list(validator.iter_errors(widened))

    with_path = json.loads(json.dumps(payload))
    with_path["run_dir"] = str(store.run_dir("inv_proj_test"))
    with pytest.raises(ValidationError):
        validator.validate(with_path)


def test_malformed_journal_fails_closed(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path))
    (store.run_dir("inv_proj_test") / "events.jsonl").write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(InvestigationStorageError, match="event journal is invalid"):
        project_events(store, "inv_proj_test")
