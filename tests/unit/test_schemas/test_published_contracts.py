"""Tests for published downstream-agent schemas."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.backends.capacity_actions import (
    CAPACITY_NEXT_KIND,
    CAPACITY_NEXT_SCHEMA_VERSION,
    CapacityJobContext,
    CapacityNextAction,
    build_capacity_next_payload,
)
from deepr.cli.commands.semantic.expert_maintenance import (
    SYNC_CAPACITY_GATE_KIND,
    SYNC_CAPACITY_GATE_SCHEMA_VERSION,
    _build_sync_capacity_payload,
)
from deepr.cli.output import (
    CLI_OPERATION_RESULT_KIND,
    CLI_OPERATION_RESULT_SCHEMA_VERSION,
    OperationResult,
)
from deepr.experts.loop_runs import ExpertLoopRun, ExpertLoopRunStore, LoopRunStatus, LoopStopReason
from deepr.experts.loop_status_rollup import build_loop_status_rollup
from deepr.mcp.security.scoped_keys import AUDIT_KIND, AUDIT_SCHEMA_VERSION, RemoteMCPAuditEvent
from deepr.mcp.security.tool_allowlist import ResearchMode
from deepr.mcp.smoke import (
    REGISTRATION_MANIFEST_KIND,
    REGISTRATION_MANIFEST_SCHEMA_VERSION,
    MCPHttpSmokeReport,
    MCPHttpSmokeStep,
    build_http_registration_manifest,
)

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


def test_mcp_remote_audit_schema_validates_runtime_event_payload():
    event = RemoteMCPAuditEvent(
        key_id="agent-alpha",
        mode=ResearchMode.READ_ONLY,
        tool="deepr_expert_handoff",
        args_hash="a" * 64,
        trace_id="trace-1",
        outcome="success",
        error_code="",
        expert_names=("AI Strategy Expert",),
        cost_usd=0.0,
        timestamp=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
    )
    payload = event.to_dict()
    schema = _load_schema("mcp-remote-audit-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == AUDIT_SCHEMA_VERSION
    assert payload["kind"] == AUDIT_KIND
    assert payload["args_hash"] == "a" * 64


def test_mcp_registration_manifest_schema_validates_runtime_payload():
    report = MCPHttpSmokeReport(
        url="https://mcp.example.com/mcp",
        steps=(MCPHttpSmokeStep("health", True, "healthy", status_code=200),),
    )
    payload = build_http_registration_manifest(
        "https://mcp.example.com/mcp",
        smoke_report=report,
        agent_name="planner",
        created_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
    )
    schema = _load_schema("mcp-registration-manifest-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == REGISTRATION_MANIFEST_SCHEMA_VERSION
    assert payload["kind"] == REGISTRATION_MANIFEST_KIND
    assert payload["auth"]["secret_included"] is False
    assert payload["smoke"]["ok"] is True


def test_capacity_next_schema_validates_runtime_payload():
    payload = build_capacity_next_payload(
        CapacityJobContext(
            task_class="sync",
            expert_name="Platform Expert",
            context_mode="fresh",
            scheduled=True,
        ),
        [
            CapacityNextAction(
                8,
                "wait",
                "Wait for cheap capacity",
                "This scheduled job should wait for owned/prepaid capacity instead of paying now.",
            )
        ],
    )
    schema = _load_schema("capacity-next-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == CAPACITY_NEXT_SCHEMA_VERSION
    assert payload["kind"] == CAPACITY_NEXT_KIND
    assert payload["job_context"]["requires_local"] is True


def test_sync_capacity_gate_schema_validates_runtime_payload(monkeypatch):
    monkeypatch.setattr(
        "deepr.backends.capacity_actions.build_capacity_next_actions",
        lambda **_: [
            CapacityNextAction(
                8,
                "wait",
                "Wait for cheap capacity",
                "scheduled wait",
            )
        ],
    )
    payload = _build_sync_capacity_payload(
        "Platform Expert",
        context_mode="fresh",
        scheduled=True,
        status="waiting_for_capacity",
        detail="local capacity is blocked",
    )
    schema = _load_schema("sync-capacity-gate-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == SYNC_CAPACITY_GATE_SCHEMA_VERSION
    assert payload["kind"] == SYNC_CAPACITY_GATE_KIND
    assert payload["capacity_next"]["schema_version"] == CAPACITY_NEXT_SCHEMA_VERSION


def test_cli_operation_result_schema_validates_success_payload():
    payload = json.loads(
        OperationResult(
            success=True,
            duration_seconds=12.5,
            cost_usd=0.03,
            report_path="data/reports/research-abc/report.md",
            job_id="research-abc",
        ).to_json()
    )
    schema = _load_schema("cli-operation-result-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == CLI_OPERATION_RESULT_SCHEMA_VERSION
    assert payload["kind"] == CLI_OPERATION_RESULT_KIND
    assert payload["status"] == "success"


def test_cli_operation_result_schema_validates_error_payload():
    payload = json.loads(
        OperationResult(
            success=False,
            duration_seconds=0.0,
            cost_usd=0.0,
            error="provider rate limited",
            error_code="PROVIDER_RATE_LIMIT",
            category="provider",
            retryable=True,
            retry_after=30,
        ).to_json()
    )
    schema = _load_schema("cli-operation-result-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == CLI_OPERATION_RESULT_SCHEMA_VERSION
    assert payload["kind"] == CLI_OPERATION_RESULT_KIND
    assert payload["status"] == "error"
    assert payload["retry_after"] == 30
