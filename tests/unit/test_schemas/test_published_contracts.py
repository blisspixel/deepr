"""Tests for published downstream-agent schemas."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.loop_runs import ExpertLoopRun, ExpertLoopRunStore, LoopRunStatus, LoopStopReason
from deepr.experts.loop_status_rollup import build_loop_status_rollup

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - local fallback when optional tooling is absent
    Draft202012Validator = None


SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _assert_required(schema: dict[str, Any], payload: dict[str, Any]) -> None:
    for field in schema.get("required", []):
        assert field in payload


def _validate(schema: dict[str, Any], payload: dict[str, Any]) -> None:
    if Draft202012Validator is not None:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        return
    _assert_required(schema, payload)


def test_schema_registry_points_to_existing_versioned_schemas():
    registry = _load_schema("registry.json")

    assert registry["schema_version"] == "deepr-schema-registry-v1"
    assert registry["compatibility_policy"]["additive_fields_within_version"] is True
    for entry in registry["schemas"]:
        schema = _load_schema(entry["path"])
        assert schema["properties"]["schema_version"]["const"] == entry["schema_version"]
        assert schema["properties"]["kind"]["const"] == entry["kind"]


def test_loop_status_schema_validates_rollup_payload(tmp_path):
    store = ExpertLoopRunStore("Contract Expert", path=tmp_path / "loop_runs.jsonl")
    store.append(
        ExpertLoopRun(
            run_id="loop_contract",
            expert_name="Contract Expert",
            loop_type="sync",
            goal="Keep expert current",
            trigger="scheduled",
            status=LoopRunStatus.COMPLETED,
            started_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 6, 19, 12, 1, tzinfo=UTC),
            finished_at=datetime(2026, 6, 19, 12, 1, tzinfo=UTC),
            budget_spent=0.0,
            capacity_source="local-ollama",
            accepted_changes=1,
            rejected_changes=0,
            stop_reason=LoopStopReason.VERIFIER_PASSED,
            next_action={},
        )
    )

    payload = build_loop_status_rollup("Contract Expert", store=store, limit=5)
    schema = _load_schema("loop-status-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == "deepr-loop-status-v1"
    assert payload["runs"][0]["schema_version"] == 1
    assert payload["runs"][0]["stop_reason"] == "verifier_passed"


def test_okf_profile_schema_validates_mapping_payload():
    payload: dict[str, Any] = {
        "schema_version": "deepr-okf-profile-v1",
        "kind": "deepr.okf.profile",
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "stability": "experimental",
            "compatibility": {
                "additive_fields": True,
                "breaking_changes_require_new_schema_version": True,
                "deprecation_policy": "Additive fields only within v1.",
            },
        },
        "derived_view": {
            "authoritative": False,
            "canonical_state": "deepr belief/event/edge store",
            "regeneration_command": "deepr expert export-okf NAME PATH",
        },
        "documents": {
            "index": {
                "path_pattern": "index.md",
                "frontmatter_type": "deepr.okf.index",
                "source": "expert profile, belief store, manifest summary",
            },
            "concept": {
                "path_pattern": "concepts/{domain}-{belief_id}.md",
                "frontmatter_type": "deepr.okf.concept",
                "source": "beliefs plus typed edges",
            },
            "gaps": {
                "path_pattern": "gaps.md",
                "frontmatter_type": "deepr.okf.gaps",
                "source": "expert manifest gaps",
            },
            "contested": {
                "path_pattern": "contested.md",
                "frontmatter_type": "deepr.okf.contested",
                "source": "contradicts edges",
            },
            "log": {
                "path_pattern": "log.md",
                "frontmatter_type": "deepr.okf.log",
                "source": "belief event log",
            },
            "llms": {
                "path_pattern": "llms.txt",
                "frontmatter_type": "none",
                "source": "bundle discovery hints",
            },
        },
        "field_mapping": {
            "profile": {"source": "ExpertProfile", "target": "index frontmatter and body", "authority": "derived"},
            "beliefs": {"source": "BeliefStore.beliefs", "target": "concept documents", "authority": "derived"},
            "events": {"source": "BeliefStore event log", "target": "log.md", "authority": "derived"},
            "edges": {"source": "BeliefStore.edges", "target": "concept relations", "authority": "derived"},
            "gaps": {"source": "ExpertManifest.gaps", "target": "gaps.md", "authority": "derived"},
            "contested": {"source": "contradicts edges", "target": "contested.md", "authority": "derived"},
        },
        "extensions": {
            "namespace": "deepr",
            "frontmatter_key": "deepr",
            "marker": "deepr:okf derived-view regenerable",
        },
    }
    schema = _load_schema("okf-profile-v1.json")

    _validate(schema, payload)
    assert payload["derived_view"]["authoritative"] is False
    assert payload["extensions"]["frontmatter_key"] == "deepr"
