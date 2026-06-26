"""Tests for published downstream-agent schemas."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from deepr.a2a.models import A2A_TASK_KIND, A2A_TASK_SCHEMA_VERSION, Task, TaskState
from deepr.backends.capacity_actions import (
    CAPACITY_NEXT_KIND,
    CAPACITY_NEXT_SCHEMA_VERSION,
    CapacityJobContext,
    CapacityNextAction,
    build_capacity_next_payload,
)
from deepr.cli.commands.semantic.expert_gap_routes import (
    SCHEDULED_GAP_FILL_WAIT_KIND,
    SCHEDULED_GAP_FILL_WAIT_SCHEMA_VERSION,
    _scheduled_gap_fill_wait_payload,
)
from deepr.cli.commands.semantic.expert_health_schedule import (
    HEALTH_CHECK_ACTION_PLAN_KIND,
    HEALTH_CHECK_ACTION_PLAN_SCHEMA_VERSION,
    HEALTH_CHECK_ARCHIVE_CONFIRMATION_KIND,
    HEALTH_CHECK_ARCHIVE_CONFIRMATION_SCHEMA_VERSION,
    scheduled_archive_confirmation_payload,
    scheduled_health_payload,
)
from deepr.cli.commands.semantic.expert_maintenance import (
    SYNC_CAPACITY_GATE_KIND,
    SYNC_CAPACITY_GATE_SCHEMA_VERSION,
    _build_sync_capacity_payload,
)
from deepr.cli.commands.semantic.expert_reflect_schedule import (
    SCHEDULED_REFLECTION_WAIT_KIND,
    SCHEDULED_REFLECTION_WAIT_SCHEMA_VERSION,
    scheduled_reflection_wait_payload,
)
from deepr.cli.output import (
    CLI_OPERATION_RESULT_KIND,
    CLI_OPERATION_RESULT_SCHEMA_VERSION,
    OperationResult,
)
from deepr.core.contracts import Claim, ExpertManifest
from deepr.experts.consult_traces import (
    CONSULT_TRACE_CANDIDATES_KIND,
    CONSULT_TRACE_CANDIDATES_SCHEMA_VERSION,
    CONSULT_TRACE_KIND,
    CONSULT_TRACE_SCHEMA_VERSION,
    build_consult_trace,
    build_consult_trace_candidates,
)
from deepr.experts.handoff import build_expert_handoff
from deepr.experts.loop_runs import ExpertLoopRun, ExpertLoopRunStore, LoopRunStatus, LoopStopReason
from deepr.experts.loop_status_rollup import build_loop_status_rollup
from deepr.experts.profile import ExpertProfile
from deepr.experts.self_model import (
    EXPERT_SELF_MODEL_KIND,
    EXPERT_SELF_MODEL_SCHEMA_VERSION,
    build_expert_self_model,
)
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


def test_expert_handoff_schema_validates_grounding_assurance_payload():
    profile = SimpleNamespace(
        name="Contract Expert",
        domain="contracts",
        description="Contract surface expert",
        created_at=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 6, 20, 12, 1, tzinfo=UTC),
        knowledge_cutoff_date=None,
        last_knowledge_refresh=None,
        refresh_frequency_days=30,
        domain_velocity="medium",
        source_files=[],
        research_jobs=[],
        total_documents=0,
    )
    manifest = ExpertManifest(
        expert_name="Contract Expert",
        domain="contracts",
        claims=[
            Claim.create("Cross-vendor checked claim", "contracts", 0.9, grounding_assurance="cross_vendor"),
            Claim.create("Unchecked claim", "contracts", 0.5),
        ],
    )
    payload = build_expert_handoff(
        profile,
        manifest=manifest,
        telemetry={"contested_claims": {"open_count": 0}},
        loop_status={"count": 0, "runs": []},
    )
    schema = _load_schema("expert-handoff-v1.json")

    _validate(schema, payload)
    assert payload["summary"]["verified_claim_count"] == 1
    assert payload["summary"]["cross_vendor_verified_claim_count"] == 1
    assert payload["summary"]["grounding_assurance"]["cross_vendor"] == 1
    assert payload["claims"][0]["grounding_assurance"] == "cross_vendor"


def test_expert_self_model_schema_validates_runtime_payload():
    profile = ExpertProfile(
        name="Self Model Expert",
        vector_store_id="vs-self-model",
        domain="self models",
        knowledge_cutoff_date=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
        last_knowledge_refresh=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
        installed_skills=["consult-review"],
    )
    manifest = ExpertManifest(
        expert_name="Self Model Expert",
        domain="self models",
        claims=[Claim.create("Experts need bounded current-focus packets.", "self models", 0.86)],
    )
    payload = build_expert_self_model(profile, manifest, focus_limit=1)
    schema = _load_schema("expert-self-model-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == EXPERT_SELF_MODEL_SCHEMA_VERSION
    assert payload["kind"] == EXPERT_SELF_MODEL_KIND
    assert payload["contract"]["goal_changes_require_review"] is True


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


def test_a2a_task_schema_validates_runtime_payload():
    task = Task(
        id="task_contract",
        state=TaskState.COMPLETED,
        skill="deepr_research",
        input="summarize this report",
        result={"summary": "complete"},
        cost=0.0,
        trace_id="trace-a2a",
        created_at=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 6, 20, 12, 1, tzinfo=UTC),
        metadata={"budget_cap": 1.0},
    )
    payload = task.to_dict()
    schema = _load_schema("a2a-task-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == A2A_TASK_SCHEMA_VERSION
    assert payload["kind"] == A2A_TASK_KIND
    assert payload["contract"]["result_untrusted"] is True


def test_consult_trace_schema_validates_runtime_payload():
    payload = build_consult_trace(
        question="What should the expert loop improve next?",
        requested_experts=["AI Agent Harnesses"],
        max_experts=3,
        budget=0.0,
        payload={
            "schema_version": "deepr-consult-v1",
            "kind": "deepr.expert.consult",
            "question": "What should the expert loop improve next?",
            "answer": "Use traces and evals.",
            "experts_consulted": ["AI Agent Harnesses"],
            "perspectives": [
                {
                    "expert": "AI Agent Harnesses",
                    "domain": "agent harnesses",
                    "confidence": 0.9,
                    "response": "Trace failed consults.",
                    "context": {"source": "belief_store", "selection": "query_overlap"},
                }
            ],
            "agreements": [],
            "disagreements": [],
            "cost_usd": 0.0,
        },
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
    schema = _load_schema("consult-trace-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == CONSULT_TRACE_SCHEMA_VERSION
    assert payload["kind"] == CONSULT_TRACE_KIND
    assert payload["events"][-1]["name"] == "synthesis_finished"


def test_consult_trace_candidates_schema_validates_runtime_payload():
    trace = build_consult_trace(
        question="What should the expert loop improve next?",
        requested_experts=["AI Agent Harnesses"],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id="consult_abcdef123456",
        recorded_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    )
    payload = build_consult_trace_candidates([trace])
    schema = _load_schema("consult-trace-candidates-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == CONSULT_TRACE_CANDIDATES_SCHEMA_VERSION
    assert payload["kind"] == CONSULT_TRACE_CANDIDATES_KIND
    assert payload["candidates"][0]["eval_case"]["source_trace_id"] == "consult_abcdef123456"


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


def test_scheduled_gap_fill_wait_schema_validates_runtime_payload():
    from deepr.experts.gap_router import GapRoute

    route = GapRoute(
        topic="open model benchmark drift",
        instrument="research",
        available=True,
        estimated_cost=0.25,
        rationale="general research",
        suggestion="deepr research 'open model benchmark drift'",
        priority=4,
        ev_cost_ratio=2.0,
        matched_keywords=[],
    )
    with patch("deepr.experts.loop_runs.record_loop_run") as mock_record:
        loop_run = MagicMock()
        loop_run.to_dict.return_value = {"run_id": "loop_gap_contract"}
        mock_record.return_value = loop_run

        payload = _scheduled_gap_fill_wait_payload("Platform Expert", [route], budget=2.0, top_n=5)
    schema = _load_schema("scheduled-gap-fill-wait-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == SCHEDULED_GAP_FILL_WAIT_SCHEMA_VERSION
    assert payload["kind"] == SCHEDULED_GAP_FILL_WAIT_KIND
    assert payload["scheduled"] is True
    assert payload["loop_run"]["run_id"] == "loop_gap_contract"


def test_scheduled_reflection_wait_schema_validates_runtime_payload():
    with patch("deepr.experts.loop_runs.record_loop_run") as mock_record:
        loop_run = MagicMock()
        loop_run.to_dict.return_value = {"run_id": "loop_reflect_contract"}
        mock_record.return_value = loop_run

        payload = scheduled_reflection_wait_payload(
            "Platform Expert",
            "job-123",
            "What changed?",
            depth=2,
            execute_followups=True,
            budget=1.0,
        )
    schema = _load_schema("scheduled-reflection-wait-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == SCHEDULED_REFLECTION_WAIT_SCHEMA_VERSION
    assert payload["kind"] == SCHEDULED_REFLECTION_WAIT_KIND
    assert payload["pending_work"] == ["reflection_evaluation", "followup_research"]
    assert payload["loop_run"]["run_id"] == "loop_reflect_contract"


def test_health_check_action_plan_schema_validates_runtime_payload():
    from deepr.experts.health_check import HealthFinding, HealthReport, RecommendedAction

    report = HealthReport(
        expert_name="Platform Expert",
        domain="platform",
        status="needs_attention",
        findings=[HealthFinding("freshness", "warning", "Knowledge is stale.")],
        actions=[
            RecommendedAction(
                category="freshness",
                description="Refresh knowledge",
                command='deepr expert sync "Platform Expert"',
                estimated_cost=0.5,
                approval_tier="notify",
            )
        ],
        generated_at=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
    )
    with patch("deepr.experts.loop_runs.record_loop_run") as mock_record:
        loop_run = MagicMock()
        loop_run.to_dict.return_value = {"run_id": "loop_health_contract"}
        mock_record.return_value = loop_run

        payload = scheduled_health_payload(report)
    schema = _load_schema("health-check-action-plan-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == HEALTH_CHECK_ACTION_PLAN_SCHEMA_VERSION
    assert payload["kind"] == HEALTH_CHECK_ACTION_PLAN_KIND
    assert payload["scheduled_action_plan"]["status"] == "waiting_for_capacity"
    assert payload["loop_run"]["run_id"] == "loop_health_contract"


def test_health_check_archive_confirmation_schema_validates_runtime_payload():
    candidate = MagicMock()
    candidate.id = "belief-1"
    candidate.claim = "Stale claim"
    candidate.get_current_confidence.return_value = 0.2
    candidate.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    candidate.retrieval_count = 0

    with patch("deepr.experts.loop_runs.record_loop_run") as mock_record:
        loop_run = MagicMock()
        loop_run.to_dict.return_value = {"run_id": "loop_archive_contract"}
        mock_record.return_value = loop_run

        payload = scheduled_archive_confirmation_payload("Platform Expert", [candidate])
    schema = _load_schema("health-check-archive-confirmation-v1.json")

    _validate(schema, payload)
    assert payload["schema_version"] == HEALTH_CHECK_ARCHIVE_CONFIRMATION_SCHEMA_VERSION
    assert payload["kind"] == HEALTH_CHECK_ARCHIVE_CONFIRMATION_KIND
    assert payload["expert_name"] == "Platform Expert"
    assert payload["loop_run"]["run_id"] == "loop_archive_contract"


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
