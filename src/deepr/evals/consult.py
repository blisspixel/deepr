"""Zero-cost consult harness regression suite.

The suite checks deterministic consult contracts that broke during dogfooding:
profile-backed expert resolution, stored belief context packets, synthesis
section parsing, and consult artifact context preservation. It does not judge
the semantic quality of an answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.config import runtime_data_path
from deepr.experts.beliefs import Belief
from deepr.experts.consult import attach_collaboration_runtime, build_consult_payload, resolve_explicit_expert_choices
from deepr.experts.consult_traces import build_consult_trace, build_consult_trace_candidates
from deepr.experts.council import ExpertCouncil, parse_synthesis_sections
from deepr.experts.profile import ExpertProfile

CONSULT_EVAL_METHODOLOGY_VERSION = "1.1"


@dataclass(frozen=True)
class ConsultEvalOutcome:
    """One consult harness regression case."""

    case_id: str
    category: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "failed": not self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ConsultEvalReport:
    """Zero-cost consult regression report."""

    outcomes: tuple[ConsultEvalOutcome, ...]
    suite_name: str = "consult-harness"
    methodology_version: str = CONSULT_EVAL_METHODOLOGY_VERSION
    cost_usd: float = 0.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_cases(self) -> int:
        return len(self.outcomes)

    @property
    def passed_cases(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.passed)

    @property
    def failed_cases(self) -> int:
        return self.total_cases - self.passed_cases

    @property
    def score(self) -> float:
        return self.passed_cases / self.total_cases if self.total_cases else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "methodology_version": self.methodology_version,
            "cost_usd": self.cost_usd,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "score": round(self.score, 6),
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "generated_at": self.generated_at.isoformat(),
        }


def run_consult_eval() -> ConsultEvalReport:
    """Run the built-in consult harness regression suite at $0."""
    return ConsultEvalReport(
        outcomes=(
            _check_explicit_slug_resolution(),
            _check_stored_belief_context_packet(),
            _check_synthesis_section_parser(),
            _check_payload_context_preservation(),
            _check_consult_trace_contract(),
            _check_consult_trace_candidate_contract(),
            _check_collaboration_capacity_contract(),
            _check_semantic_quality_eval_case_contract(),
        )
    )


def write_consult_eval_report(report: ConsultEvalReport, *, output_dir: Path | None = None) -> Path:
    """Write a consult eval artifact under the configured benchmarks directory."""
    root = output_dir or runtime_data_path("benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"consult_eval_{timestamp}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _check_explicit_slug_resolution() -> ConsultEvalOutcome:
    profile = ExpertProfile(
        name="AI Agent Harnesses",
        vector_store_id="vs-consult-eval",
        domain="agent harnesses",
        description="context engineering and long-running agent loops",
    )
    resolved = resolve_explicit_expert_choices(["ai_agent_harnesses"], profiles=[profile])
    expected = [{"name": "AI Agent Harnesses", "domain": "agent harnesses"}]
    return ConsultEvalOutcome(
        case_id="explicit_slug_resolution",
        category="routing",
        passed=resolved == expected,
        detail={"resolved": resolved, "expected": expected},
    )


def _check_stored_belief_context_packet() -> ConsultEvalOutcome:
    belief = Belief(
        claim="Prompt caching cost models must separate cache creation tokens from cache read tokens.",
        confidence=0.92,
        evidence_refs=("https://platform.claude.com/docs/en/build-with-claude/prompt-caching",),
        domain="provider economics",
        trust_class="secondary",
    )
    perspective = ExpertCouncil().build_stored_perspective(
        "How should prompt cache cost be modeled?",
        "Grounded Cost Expert",
        "provider economics",
        [belief],
    )
    context = perspective.context if perspective is not None else {}
    passed = (
        perspective is not None
        and perspective.cost == 0.0
        and context.get("source") == "belief_store"
        and context.get("selection") == "query_overlap"
        and context.get("beliefs_available") == 1
        and context.get("beliefs_included") == 1
        and "cache creation tokens" in perspective.response
    )
    return ConsultEvalOutcome(
        case_id="stored_belief_context_packet",
        category="context",
        passed=passed,
        detail={"context": context, "has_perspective": perspective is not None},
    )


def _check_synthesis_section_parser() -> ConsultEvalOutcome:
    text = """### 1. SYNTHESIS:
Unified answer.

### 2. AGREEMENTS:
- Shared point

### 3. DISAGREEMENTS:
- Divergent point
"""
    agreements, disagreements = parse_synthesis_sections(text)
    return ConsultEvalOutcome(
        case_id="synthesis_section_parser",
        category="artifact",
        passed=agreements == ["Shared point"] and disagreements == ["Divergent point"],
        detail={"agreements": agreements, "disagreements": disagreements},
    )


def _check_payload_context_preservation() -> ConsultEvalOutcome:
    payload = build_consult_payload(
        "q",
        {
            "perspectives": [
                {
                    "expert_name": "A",
                    "domain": "alpha",
                    "response": "answer",
                    "confidence": 0.9,
                    "context": {"source": "belief_store", "selection": "query_overlap"},
                },
                {"expert_name": "B", "domain": "beta", "response": "answer", "confidence": 0.8},
            ],
            "synthesis": "summary",
            "agreements": [],
            "disagreements": [],
            "total_cost": 0.0,
        },
    )
    first = payload["perspectives"][0]
    second = payload["perspectives"][1]
    passed = (
        payload["schema_version"] == "deepr-consult-v1"
        and payload["cost_usd"] == 0.0
        and first.get("context", {}).get("source") == "belief_store"
        and "context" not in second
    )
    return ConsultEvalOutcome(
        case_id="payload_context_preservation",
        category="artifact",
        passed=passed,
        detail={"first": first, "second_has_context": "context" in second},
    )


def _check_consult_trace_contract() -> ConsultEvalOutcome:
    payload = build_consult_payload(
        "q",
        {
            "perspectives": [
                {
                    "expert_name": "A",
                    "domain": "alpha",
                    "response": "answer",
                    "confidence": 0.9,
                    "context": {"source": "belief_store", "selection": "query_overlap"},
                }
            ],
            "synthesis": "summary",
            "agreements": [],
            "disagreements": [],
            "total_cost": 0.0,
        },
    )
    trace = build_consult_trace(
        question="q",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        payload=payload,
        result={"perspectives": [{}], "synthesis_status": "failed", "synthesis_error_type": "RuntimeError"},
        trace_id="consult_abcdef123456",
    )
    synthesis_check = next(check for check in trace["checks"] if check["name"] == "synthesis_status")
    passed = (
        trace["schema_version"] == "deepr-consult-trace-v1"
        and trace["context_packet"]["selected"][0]["context"]["source"] == "belief_store"
        and any(event["name"] == "synthesis_failed" for event in trace["events"])
        and synthesis_check["status"] == "failed"
    )
    return ConsultEvalOutcome(
        case_id="consult_trace_contract",
        category="trace",
        passed=passed,
        detail={"trace_id": trace["trace_id"], "synthesis_check": synthesis_check},
    )


def _check_consult_trace_candidate_contract() -> ConsultEvalOutcome:
    trace = build_consult_trace(
        question="What did this consult fail to answer?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id="consult_abcdef123456",
    )
    payload = build_consult_trace_candidates([trace])
    first = payload["candidates"][0]
    passed = (
        payload["schema_version"] == "deepr-consult-trace-candidates-v1"
        and payload["candidate_count"] == 1
        and first["reason"] == "failed_consult"
        and first["eval_case"]["source_trace_id"] == trace["trace_id"]
        and "failure" not in first
    )
    return ConsultEvalOutcome(
        case_id="consult_trace_candidate_contract",
        category="trace",
        passed=passed,
        detail={"candidate_count": payload["candidate_count"], "reason": first["reason"]},
    )


def _check_collaboration_capacity_contract() -> ConsultEvalOutcome:
    result = {
        "perspectives": [
            {
                "expert_name": "Agent Harness Expert",
                "domain": "agent harnesses",
                "response": "Use bounded trace artifacts.",
                "confidence": 0.9,
                "cost": 0.0,
                "context": {"source": "belief_store", "selection": "query_overlap", "beliefs_included": 2},
            },
            {
                "expert_name": "TKG Expert",
                "domain": "temporal graphs",
                "response": "Preserve temporal disagreement.",
                "confidence": 0.84,
                "cost": 0.0,
                "context": {"source": "belief_store", "selection": "query_overlap", "beliefs_included": 1},
            },
        ],
        "synthesis": "Bounded guidance with preserved dissent.",
        "agreements": ["Use traceable context."],
        "disagreements": ["How much graph mutation should be allowed immediately."],
        "requested_budget_usd": 0.0,
        "total_cost": 0.0,
        "shared_task_trace_id": "consult_abcdef123456",
    }
    payload = build_consult_payload("How should expert consult improve?", result)
    trace = build_consult_trace(
        question="How should expert consult improve?",
        requested_experts=["Agent Harness Expert", "TKG Expert"],
        max_experts=3,
        budget=0.0,
        payload=payload,
        result={**result, "synthesis_status": "completed"},
        capacity={"synthesis_backend": "local", "provider": "local", "model": "qwen", "live_metered_fallback": False},
        trace_id="consult_abcdef123456",
    )
    attach_collaboration_runtime(
        payload,
        result=result,
        capacity={"synthesis_backend": "local", "provider": "local", "model": "qwen", "live_metered_fallback": False},
        trace=trace,
    )
    collaboration = payload["collaboration"]
    passed = (
        collaboration["schema_version"] == "deepr-expert-collaboration-v1"
        and collaboration["contract"]["host_orchestrated"] is True
        and collaboration["contract"]["semantic_verdict"] is False
        and collaboration["budget_capacity_contract"]["capacity"]["live_metered_fallback"] is False
        and collaboration["evidence_packet"]["belief_store_perspective_count"] == 2
        and collaboration["evidence_packet"]["disagreement_count"] == 1
        and collaboration["dissent_handling"]["dissent_preserved"] is True
        and collaboration["task"]["consult_trace_id"] == "consult_abcdef123456"
    )
    return ConsultEvalOutcome(
        case_id="collaboration_capacity_contract",
        category="collaboration",
        passed=passed,
        detail={
            "capacity": collaboration["budget_capacity_contract"]["capacity"],
            "dissent": collaboration["dissent_handling"],
        },
    )


def _check_semantic_quality_eval_case_contract() -> ConsultEvalOutcome:
    trace = build_consult_trace(
        question="How should an expert answer when the useful idea is not yet online?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        payload={
            "schema_version": "deepr-consult-v1",
            "kind": "deepr.expert.consult",
            "question": "How should an expert answer when the useful idea is not yet online?",
            "answer": "Thin answer.",
            "experts_consulted": ["A"],
            "perspectives": [{"expert": "A", "confidence": 0.2, "response": "thin"}],
            "agreements": [],
            "disagreements": [],
            "cost_usd": 0.0,
        },
        result={"perspectives": [{}], "synthesis_status": "completed"},
        capacity={"synthesis_backend": "local", "provider": "local", "model": "qwen", "live_metered_fallback": False},
        trace_id="consult_abcdef123456",
    )
    payload = build_consult_trace_candidates([trace])
    first = payload["candidates"][0]
    case = first["semantic_eval_case"]
    dimensions = {item["dimension"] for item in case["rubric"]}
    serialized = json.dumps(case, sort_keys=True)
    passed = (
        payload["semantic_eval_case_count"] == 1
        and case["schema_version"] == "deepr-consult-quality-eval-case-v1"
        and case["kind"] == "deepr.eval.consult_quality_case"
        and case["contract"]["cost_usd"] == 0.0
        and case["contract"]["writes_state"] is False
        and case["contract"]["semantic_verdict"] is False
        and case["contract"]["lexical_verdict_allowed"] is False
        and case["contract"]["requires_human_or_calibrated_model_judge"] is True
        and {"uses_expert_state", "preserves_dissent", "grounded_when_factual", "original_thought"} <= dimensions
        and case["acceptance_policy"]["never_commits_beliefs"] is True
        and "output" not in first
        and "failure" not in first
        and "Thin answer." not in serialized
    )
    return ConsultEvalOutcome(
        case_id="semantic_quality_eval_case_contract",
        category="semantic_eval",
        passed=passed,
        detail={"dimensions": sorted(dimensions), "reason": first["reason"]},
    )
