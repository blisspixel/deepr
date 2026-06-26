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

from deepr.experts.beliefs import Belief
from deepr.experts.consult import build_consult_payload, resolve_explicit_expert_choices
from deepr.experts.council import ExpertCouncil, parse_synthesis_sections
from deepr.experts.profile import ExpertProfile

CONSULT_EVAL_METHODOLOGY_VERSION = "1.0"


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
        )
    )


def write_consult_eval_report(report: ConsultEvalReport, *, output_dir: Path | None = None) -> Path:
    """Write a consult eval artifact under ``data/benchmarks``."""
    root = output_dir or Path("data/benchmarks")
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
