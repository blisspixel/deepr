"""Reflection loop: self-evaluate a research answer before it is delivered/absorbed.

ROADMAP Phase 4 "reflection loop (self-correction before delivery)". Given a
question and an answer, ``ReflectionEngine`` runs one LLM pass that scores the
answer on four dimensions - grounding, completeness, calibration, directness -
and surfaces concrete issues and follow-up queries.

Design split: the model does *perception* (per-dimension scores + issues +
follow-ups); this module does the *decision* (overall score = mean, and a
verdict from fixed thresholds). That keeps the accept/revise/re-research call
deterministic and unit-testable without depending on the model's own verdict.

Read-only and bounded: one model call regardless of answer length; it never
mutates an expert. ``depth=0`` short-circuits (reflection disabled); ``depth>=2``
asks for more rigorous gap-finding and always proposes re-research queries.
Actually re-running research from the follow-ups is a separate, opt-in step.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_REFLECTION_MODEL = "gpt-5-mini"

# The four dimensions the answer is scored on.
_DIMENSIONS = ("grounding", "completeness", "calibration", "directness")

# Verdict thresholds on the overall (mean) score, plus a floor: any single
# dimension below _CRITICAL_FLOOR forces at least "revise".
_ACCEPT_AT = 0.75
_RE_RESEARCH_BELOW = 0.5
_CRITICAL_FLOOR = 0.4


class ReflectionError(Exception):
    """Raised when reflection cannot be produced (empty input, bad model output)."""


@dataclass
class ReflectionDimension:
    """One scored quality dimension."""

    name: str
    score: float  # 0.0 - 1.0
    assessment: str
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "score": round(self.score, 3), "assessment": self.assessment, "issues": self.issues}


@dataclass
class ReflectionReport:
    """The result of a reflection pass."""

    question: str
    verdict: str  # accept | revise | re_research | skipped
    overall_score: float
    dimensions: list[ReflectionDimension] = field(default_factory=list)
    followups: list[str] = field(default_factory=list)
    model: str = DEFAULT_REFLECTION_MODEL
    depth: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "verdict": self.verdict,
            "overall_score": round(self.overall_score, 3),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "followups": self.followups,
            "model": self.model,
            "depth": self.depth,
        }


def _verdict_from_scores(dimensions: list[ReflectionDimension]) -> tuple[str, float]:
    """Deterministic verdict from per-dimension scores.

    Returns (verdict, overall_score). re_research if the mean is weak or any
    dimension is critically low; accept only when the mean is strong and nothing
    is critically low; revise otherwise.
    """
    if not dimensions:
        return "re_research", 0.0
    overall = sum(d.score for d in dimensions) / len(dimensions)
    worst = min(d.score for d in dimensions)
    if overall < _RE_RESEARCH_BELOW or worst < _CRITICAL_FLOOR:
        return "re_research", overall
    if overall >= _ACCEPT_AT and worst >= 0.5:
        return "accept", overall
    return "revise", overall


class ReflectionEngine:
    """Self-evaluate a research answer against its question."""

    def __init__(self, client: Any | None = None, model: str = DEFAULT_REFLECTION_MODEL) -> None:
        self._client = client
        self.model = model

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ReflectionError("OPENAI_API_KEY is not set. Pass a client explicitly or set the env var.")
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def reflect(
        self,
        question: str,
        answer: str,
        *,
        domain: str = "",
        depth: int = 1,
    ) -> ReflectionReport:
        """Reflect on an answer.

        Args:
            question: The question the answer was meant to address.
            answer: The research answer / report text to evaluate.
            domain: Optional expert domain, used to sharpen the evaluation.
            depth: 0 = skip (returns a "skipped"/accept report); 1 = single
                evaluation pass; >=2 = more rigorous, always proposes
                re-research follow-ups.

        Returns:
            ReflectionReport with per-dimension scores, a deterministic verdict,
            and follow-up queries.
        """
        question = (question or "").strip()
        answer = (answer or "").strip()
        if not question or not answer:
            raise ReflectionError("question and answer must both be non-empty")

        if depth <= 0:
            return ReflectionReport(
                question=question,
                verdict="skipped",
                overall_score=1.0,
                dimensions=[],
                followups=[],
                model=self.model,
                depth=0,
            )

        dimensions, followups = await self._evaluate(question, answer, domain, depth)
        verdict, overall = _verdict_from_scores(dimensions)
        return ReflectionReport(
            question=question,
            verdict=verdict,
            overall_score=overall,
            dimensions=dimensions,
            followups=followups,
            model=self.model,
            depth=depth,
        )

    async def _evaluate(
        self, question: str, answer: str, domain: str, depth: int
    ) -> tuple[list[ReflectionDimension], list[str]]:
        """One LLM call -> per-dimension scores + follow-up queries."""
        client = self._get_client()
        rigor = (
            "Be especially rigorous: actively hunt for unsupported claims and missing angles, "
            "and always propose concrete re-research queries."
            if depth >= 2
            else "Flag the most important issues; propose follow-up queries only where they matter."
        )
        system = (
            "You critically evaluate a research answer against the question it was meant to address. "
            "Return ONLY a JSON object. Score each dimension 0.0-1.0 (1.0 = excellent). Be a skeptical "
            "reviewer, not a cheerleader: reserve high scores for answers that are genuinely well-grounded "
            "and complete. " + rigor
        )
        domain_clause = f"\nExpert domain (judge relevance to this): {domain}" if domain else ""
        user = (
            f"QUESTION:\n{question}\n{domain_clause}\n\n"
            f"ANSWER TO EVALUATE:\n{answer}\n\n"
            "Score these four dimensions:\n"
            "- grounding: are the claims backed by cited, credible sources (vs unsupported assertion)?\n"
            "- completeness: does it cover the question's key facets with no major logical gaps?\n"
            "- calibration: does its stated confidence/hedging match the strength of its evidence?\n"
            "- directness: does it actually answer what was asked (vs adjacent/evasive)?\n\n"
            "Return JSON exactly:\n"
            '  {"dimensions": [{"name": "grounding", "score": 0-1, "assessment": "1 sentence", '
            '"issues": ["..."]}, ... one per dimension ...], '
            '"followups": ["specific re-research query to close a gap", ...]}'
        )

        from deepr.experts.cost_admission import admit_soft_cost_operation, record_soft_cost

        cost_safety, est_cost, deny_reason = admit_soft_cost_operation(
            session_id="reflection",
            operation_type="answer_reflection",
            estimated_cost=0.02,
        )
        if deny_reason is not None:
            raise ReflectionError(f"Reflection blocked by cost-safety: {deny_reason}")

        response = await client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        try:
            from deepr.experts.chat_turns import chat_token_cost

            actual = chat_token_cost(response.usage, self.model) if response.usage else est_cost
            record_soft_cost(
                cost_safety,
                session_id="reflection",
                operation_type="answer_reflection",
                actual_cost=float(actual),
                provider="openai",
                model=self.model,
                source="experts.reflection._evaluate",
            )
        except Exception as exc:
            logger.warning("Reflection cost recording failed: %s", exc)

        raw = response.choices[0].message.content or ""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ReflectionError(f"Reflection model returned non-JSON output: {e}. Raw: {raw[:200]!r}") from e

        by_name: dict[str, ReflectionDimension] = {}
        raw_dims = parsed.get("dimensions", []) if isinstance(parsed, dict) else []
        if isinstance(raw_dims, list):
            for item in raw_dims:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip().lower()
                if name not in _DIMENSIONS:
                    continue
                try:
                    score = max(0.0, min(1.0, float(item.get("score", 0.0))))
                except (TypeError, ValueError):
                    score = 0.0
                issues = [str(i).strip() for i in (item.get("issues") or []) if str(i).strip()]
                by_name[name] = ReflectionDimension(
                    name=name,
                    score=score,
                    assessment=str(item.get("assessment", "")).strip(),
                    issues=issues,
                )

        # Ensure all four dimensions are present (missing -> conservative 0.0).
        dimensions = [
            by_name.get(name, ReflectionDimension(name=name, score=0.0, assessment="(not assessed)", issues=[]))
            for name in _DIMENSIONS
        ]

        followups_raw = parsed.get("followups", []) if isinstance(parsed, dict) else []
        followups = [str(f).strip() for f in (followups_raw or []) if str(f).strip()][:10]
        return dimensions, followups
