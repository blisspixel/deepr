from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from deepr.experts.investigation.inputs import compile_input_bundle
from deepr.experts.investigation.models import (
    PLAN_KIND,
    PLAN_SCHEMA_VERSION,
    InvestigationBounds,
    LearningMode,
    Phase,
    ProtocolMode,
    sha256_json,
    validate_plan,
)
from deepr.experts.investigation.store import (
    InvestigationBusyError,
    InvestigationStorageError,
    InvestigationStore,
)

NOW = "2026-07-17T00:00:00+00:00"


def _plan(tmp_path: Path, *, run_id: str = "inv_store_test") -> dict[str, Any]:
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
            "dialogue_is_evidence": False,
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


def test_store_create_state_events_and_control_are_durable(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    plan = _plan(tmp_path)

    created = store.create(plan)
    reopened = store.create(copy.deepcopy(plan))
    control = store.request_control("inv_store_test", "pause")

    assert reopened == created
    assert store.load_plan("inv_store_test") == plan
    assert store.load_state("inv_store_test")["state"] == "planned"
    assert control["requested"] == "pause"
    assert control["revision"] == 2
    events = store.load_events("inv_store_test")
    assert [event["sequence"] for event in events] == [1]
    assert events[0]["event_type"] == "run_created"


def test_store_state_uses_optimistic_versions(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    state = store.create(_plan(tmp_path))
    updated = copy.deepcopy(state)
    updated["phase"] = "charters"

    saved = store.save_state("inv_store_test", updated, expected_version=1)
    assert saved["version"] == 2
    with pytest.raises(InvestigationStorageError, match="changed"):
        store.save_state("inv_store_test", updated, expected_version=1)


def test_artifacts_are_idempotent_hash_checked_and_disk_bounded(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path))
    payload = {"schema_version": "fixture-v1", "kind": "fixture", "value": 1}

    first = store.write_artifact(
        "inv_store_test",
        phase=Phase.CHARTERS,
        key="fixture",
        payload=payload,
        max_disk_bytes=1_000_000,
    )
    second = store.write_artifact(
        "inv_store_test",
        phase=Phase.CHARTERS,
        key="fixture",
        payload=copy.deepcopy(payload),
        max_disk_bytes=1_000_000,
    )
    assert first == second
    assert store.read_artifact("inv_store_test", first) == payload

    with pytest.raises(InvestigationStorageError, match="idempotency conflict"):
        store.write_artifact(
            "inv_store_test",
            phase=Phase.CHARTERS,
            key="fixture",
            payload={**payload, "value": 2},
            max_disk_bytes=1_000_000,
        )
    with pytest.raises(InvestigationStorageError, match="disk ceiling"):
        store.write_artifact(
            "inv_store_test",
            phase=Phase.CHARTERS,
            key="too-large",
            payload={"data": "x" * 100},
            max_disk_bytes=store.disk_usage("inv_store_test") + 1,
        )

    artifact_path = store.run_dir("inv_store_test") / first["path"]
    artifact_path.write_text("{}", encoding="utf-8")
    with pytest.raises(InvestigationStorageError, match="hash verification"):
        store.read_artifact("inv_store_test", first)


def test_execution_lock_has_one_owner(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path))

    with store.execution_lock("inv_store_test"):
        with pytest.raises(InvestigationBusyError, match="active executor"):
            with store.execution_lock("inv_store_test"):
                raise AssertionError("second owner must not enter")


def test_artifact_reference_cannot_escape_run(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "runs")
    store.create(_plan(tmp_path))

    with pytest.raises(InvestigationStorageError, match="escapes"):
        store.read_artifact(
            "inv_store_test",
            {"path": "../../outside.json", "sha256": "0" * 64},
        )
