"""Autonomous gap-fill execution - route-gaps graduated from advisory to action.

The loop-closer (ROADMAP Phase 4, v2.14): ``deepr expert route-gaps`` ranks
which instrument should fill each knowledge gap; with ``--execute`` the
highest-value fills actually run, budget-bounded, and the findings absorb
through the verification-gated pipeline (dedup + contradiction flagging).

Bounded autonomy, deliberately:
- Only the ``research`` route auto-executes (the universal, cheap path -
  same injectable research function the sync engine uses). Specialist
  instrument routes (recon/distillr/primr) are DEFERRED with their exact
  command printed: those are approval-gated, multi-minute paid jobs that
  must not start as a side effect of a fill sweep.
- Per-gap budgets inside a run ceiling, skip-not-fail on exhaustion,
  ``--dry-run`` at $0 - the same money discipline as expert sync.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deepr.experts.beliefs import BeliefStore
from deepr.experts.report_absorber import (
    ReportAbsorberCostError,
    absorber_estimated_cost,
    absorption_result_cost,
)

if TYPE_CHECKING:
    from deepr.experts.gap_router import GapRoute
    from deepr.experts.profile import ExpertProfile

logger = logging.getLogger(__name__)

# Same refuse-below-floor preflight as sync: a fill that cannot afford a
# single research call is refused before any spend.
MIN_PER_GAP_BUDGET = 0.05

ResearchFn = Callable[[str, float], Awaitable[dict[str, Any]]]
SpendDecisionFn = Callable[[Any, float], Any]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "gap"


@dataclass
class GapFillOutcome:
    """Result of attempting one gap."""

    topic: str
    status: str  # "filled" | "deferred" | "skipped" | "failed" | "would_fill"
    instrument: str = "research"
    cost: float = 0.0
    absorbed: int = 0
    flagged: int = 0
    detail: str = ""
    knowledge_observed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "status": self.status,
            "instrument": self.instrument,
            "cost": round(self.cost, 4),
            "absorbed": self.absorbed,
            "flagged": self.flagged,
            "detail": self.detail,
            "knowledge_observed_at": self.knowledge_observed_at.isoformat() if self.knowledge_observed_at else None,
        }


@dataclass
class GapFillResult:
    """One execution sweep over routed gaps."""

    expert_name: str
    started_at: datetime
    outcomes: list[GapFillOutcome] = field(default_factory=list)
    total_cost: float = 0.0

    @property
    def filled_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "filled")

    @property
    def knowledge_observed_at(self) -> datetime | None:
        observations = [outcome.knowledge_observed_at for outcome in self.outcomes if outcome.knowledge_observed_at]
        return max(observations) if observations else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "started_at": self.started_at.isoformat(),
            "outcomes": [o.to_dict() for o in self.outcomes],
            "total_cost": round(self.total_cost, 4),
            "filled_count": self.filled_count,
            "knowledge_observed_at": (self.knowledge_observed_at.isoformat() if self.knowledge_observed_at else None),
        }


def routes_from_queries(queries: list[str], *, estimated_cost: float = 0.05) -> list[GapRoute]:
    """Adapt plain research queries (e.g. reflection follow-ups) to GapRoutes.

    Reflection emits follow-up queries when a report is weak; running them
    is the same job as filling a routed gap, so they reuse the engine and
    all of its budget discipline. Order is preserved via descending
    ev_cost_ratio (the engine sorts by it).
    """
    from deepr.experts.gap_router import GapRoute

    total = len(queries)
    return [
        GapRoute(
            topic=q,
            instrument="research",
            available=True,
            estimated_cost=estimated_cost,
            rationale="reflection follow-up",
            suggestion="",
            ev_cost_ratio=float(total - i),
        )
        for i, q in enumerate(queries)
    ]


class GapFillEngine:
    """Execute the router's highest-value research-route fills within budget."""

    def __init__(
        self,
        expert: ExpertProfile,
        *,
        research_fn: ResearchFn | None = None,
        belief_store: BeliefStore | None = None,
        absorber: Any | None = None,
        spend_decision_fn: SpendDecisionFn | None = None,
    ) -> None:
        self.expert = expert
        self._research_fn = research_fn
        self.belief_store = belief_store or BeliefStore(expert.name)
        self._absorber = absorber
        self._spend_decision_fn = spend_decision_fn

    async def _default_research(self, query: str, budget: float) -> dict[str, Any]:
        from deepr.experts.chat import ExpertChatSession

        session = ExpertChatSession(self.expert, budget=budget, agentic=True)
        return await session._standard_research(query)

    def _get_absorber(self) -> Any:
        if self._absorber is None:
            from deepr.experts.report_absorber import ReportAbsorber

            self._absorber = ReportAbsorber(self.expert, belief_store=self.belief_store)
        return self._absorber

    @staticmethod
    def build_fill_query(route: GapRoute) -> str:
        """The research question for one gap: its topic plus the suggestion."""
        suggestion = route.suggestion or ""
        return (
            f"Fill this knowledge gap with well-sourced findings: {route.topic}. "
            f"{suggestion} Cite sources with dates; state clearly what remains unknown."
        )

    def _spend_decision_skip(self, route: GapRoute, estimated_cost: float) -> GapFillOutcome | None:
        if self._spend_decision_fn is None:
            return None
        try:
            decision = self._spend_decision_fn(route, estimated_cost)
        except Exception as exc:
            detail = f"metered deferred: spend decision unavailable ({exc})"
            return GapFillOutcome(route.topic, "skipped", detail=detail)
        if bool(getattr(decision, "allowed", False)):
            return None
        reason = str(getattr(decision, "reason", "value gate denied"))
        return GapFillOutcome(route.topic, "skipped", detail=f"metered deferred: {reason}")

    async def _run_research_fill(
        self,
        route: GapRoute,
        *,
        per_gap_budget: float,
        remaining_budget: float,
        extraction_estimate: float,
        started_at: datetime,
    ) -> tuple[GapFillOutcome, float]:
        try:
            fn = self._research_fn or self._default_research
            research = await fn(self.build_fill_query(route), per_gap_budget)
        except Exception as exc:
            return GapFillOutcome(route.topic, "failed", detail=str(exc)), 0.0

        if "error" in research:
            return GapFillOutcome(route.topic, "failed", detail=str(research["error"])), 0.0

        cost = float(research.get("cost", 0.0) or 0.0)
        remaining_after_research = remaining_budget - cost
        answer = (research.get("answer") or "").strip()
        if not answer:
            return GapFillOutcome(route.topic, "failed", cost=cost, detail="empty answer"), cost
        if remaining_after_research < extraction_estimate:
            return (
                GapFillOutcome(
                    route.topic,
                    "skipped",
                    cost=cost,
                    detail=(
                        f"run budget exhausted before extraction "
                        f"(${remaining_after_research:.2f} left; needs ${extraction_estimate:.2f})"
                    ),
                ),
                cost,
            )

        try:
            absorber = self._get_absorber()
            report_id = f"gapfill:{_slug(route.topic)}:{started_at.strftime('%Y%m%d')}"
            absorption = await absorber.absorb(
                report_id,
                answer,
                flag_contradictions=True,
                budget=max(0.0, remaining_after_research),
            )
            extraction_cost = absorption_result_cost(absorption)
            from deepr.experts.knowledge_freshness import advance_from_absorption

            knowledge_changed = advance_from_absorption(self.expert, absorption)
            return (
                GapFillOutcome(
                    route.topic,
                    "filled",
                    cost=cost + extraction_cost,
                    absorbed=len(absorption.absorbed),
                    flagged=len(absorption.flagged),
                    knowledge_observed_at=(self.expert.last_knowledge_refresh if knowledge_changed else None),
                ),
                cost + extraction_cost,
            )
        except ReportAbsorberCostError as exc:
            spent = cost + exc.actual_cost
            return GapFillOutcome(route.topic, "failed", cost=spent, detail=f"absorb failed: {exc}"), spent
        except Exception as exc:
            return GapFillOutcome(route.topic, "failed", cost=cost, detail=f"absorb failed: {exc}"), cost

    async def execute(
        self,
        routes: list[GapRoute],
        *,
        budget: float = 2.0,
        top: int = 3,
        dry_run: bool = False,
    ) -> GapFillResult:
        """Run the top-N highest-value fills, bounded by ``budget``.

        Ordering: ev_cost_ratio desc (the router's value-per-dollar signal),
        then priority. Specialist-instrument routes are deferred with their
        command, never auto-executed.
        """
        started_at = datetime.now(UTC)
        result = GapFillResult(expert_name=self.expert.name, started_at=started_at)

        ranked = sorted(routes, key=lambda r: (-r.ev_cost_ratio, -r.priority))[: max(1, top)]
        remaining = budget

        for route in ranked:
            if route.instrument != "research":
                result.outcomes.append(
                    GapFillOutcome(
                        route.topic,
                        "deferred",
                        instrument=route.instrument,
                        detail=f"specialist instrument is approval-gated; run: {route.suggestion}",
                    )
                )
                continue

            absorber = self._get_absorber()
            extraction_estimate = absorber_estimated_cost(absorber)
            per_gap = min(max(route.estimated_cost, MIN_PER_GAP_BUDGET), remaining - extraction_estimate)
            if per_gap < MIN_PER_GAP_BUDGET:
                result.outcomes.append(
                    GapFillOutcome(
                        route.topic,
                        "skipped",
                        detail=(
                            f"run budget exhausted (${remaining:.2f} left; "
                            f"needs ${MIN_PER_GAP_BUDGET + extraction_estimate:.2f})"
                        ),
                    )
                )
                continue
            if dry_run:
                result.outcomes.append(
                    GapFillOutcome(route.topic, "would_fill", detail=self.build_fill_query(route)[:120])
                )
                continue

            if skip := self._spend_decision_skip(route, per_gap + extraction_estimate):
                result.outcomes.append(skip)
                continue

            outcome, spent = await self._run_research_fill(
                route,
                per_gap_budget=per_gap,
                remaining_budget=remaining,
                extraction_estimate=extraction_estimate,
                started_at=started_at,
            )
            remaining -= spent
            result.total_cost += spent
            result.outcomes.append(outcome)

        return result
