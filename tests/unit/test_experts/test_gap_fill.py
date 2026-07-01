"""Tests for deepr.experts.gap_fill - route-gaps graduated to execution.

Same harness discipline as the sync engine: injectable research function,
real BeliefStore + ReportAbsorber (fake extraction client) on tmp dirs -
every test free.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from deepr.experts.beliefs import BeliefStore
from deepr.experts.gap_fill import GapFillEngine
from deepr.experts.gap_router import GapRoute
from deepr.experts.report_absorber import ReportAbsorber


def _expert():
    return SimpleNamespace(name="GapFill Test Expert", domain="ai")


def _route(topic: str, instrument: str = "research", ev: float = 1.0, cost: float = 0.10) -> GapRoute:
    return GapRoute(
        topic=topic,
        instrument=instrument,
        available=True,
        estimated_cost=cost,
        rationale="test",
        suggestion=f"deepr something '{topic}'",
        ev_cost_ratio=ev,
    )


class _FakeExtractionClient:
    def __init__(self, statement="Gap topic finding from research"):
        content = json.dumps({"claims": [{"statement": statement, "confidence": 0.9, "evidence": ["src"]}]})

        async def _create(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


class _FakeAbsorber:
    def __init__(self, estimated_cost: float = 0.03):
        self.estimated_cost = estimated_cost
        self.calls = 0

    async def absorb(self, report_id: str, report_text: str, **kwargs):
        self.calls += 1
        return SimpleNamespace(absorbed=[object()], flagged=[], estimated_cost=self.estimated_cost)


def _engine(tmp_path, answers: dict[str, dict]):
    beliefs = BeliefStore("GapFill Test Expert", storage_dir=tmp_path / "beliefs")
    absorber = ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs)

    calls: list[str] = []

    async def research_fn(query: str, budget: float) -> dict:
        calls.append(query)
        for key, answer in answers.items():
            if key.lower() in query.lower():
                return answer
        return {"answer": "Default finding.", "cost": 0.01}

    engine = GapFillEngine(_expert(), research_fn=research_fn, belief_store=beliefs, absorber=absorber)
    return engine, calls


class TestGapFillEngine:
    @pytest.mark.asyncio
    async def test_fills_research_routes_and_absorbs(self, tmp_path):
        engine, calls = _engine(tmp_path, {"Topic A": {"answer": "Topic A finding, well sourced.", "cost": 0.02}})
        result = await engine.execute([_route("Topic A")], budget=1.0)

        assert result.filled_count == 1
        outcome = result.outcomes[0]
        assert outcome.status == "filled"
        assert outcome.absorbed == 1
        assert outcome.cost == pytest.approx(0.05)
        assert result.total_cost == pytest.approx(0.05)
        assert len(engine.belief_store.beliefs) == 1
        assert "Topic A" in calls[0]

    @pytest.mark.asyncio
    async def test_reserves_and_counts_absorption_cost(self, tmp_path):
        budgets: list[float] = []

        async def research_fn(query: str, budget: float) -> dict:
            budgets.append(budget)
            return {"answer": "Budgeted finding.", "cost": 0.20}

        absorber = _FakeAbsorber(estimated_cost=0.07)
        engine = GapFillEngine(_expert(), research_fn=research_fn, absorber=absorber)

        result = await engine.execute([_route("Budgeted", cost=0.50)], budget=0.30)

        assert budgets == [pytest.approx(0.23)]
        assert absorber.calls == 1
        assert result.outcomes[0].status == "filled"
        assert result.outcomes[0].cost == pytest.approx(0.27)
        assert result.total_cost == pytest.approx(0.27)

    @pytest.mark.asyncio
    async def test_budget_floor_includes_absorption_cost(self, tmp_path):
        async def exploding_research(query: str, budget: float) -> dict:
            raise AssertionError("research must not start when absorption cannot fit")

        absorber = _FakeAbsorber(estimated_cost=0.04)
        engine = GapFillEngine(_expert(), research_fn=exploding_research, absorber=absorber)

        result = await engine.execute([_route("Too small", cost=0.05)], budget=0.08)

        assert absorber.calls == 0
        assert result.outcomes[0].status == "skipped"
        assert "needs $0.09" in result.outcomes[0].detail
        assert result.total_cost == 0.0

    @pytest.mark.asyncio
    async def test_orders_by_value_per_dollar(self, tmp_path):
        engine, calls = _engine(tmp_path, {})
        routes = [_route("Low value", ev=0.1), _route("High value", ev=9.0), _route("Mid value", ev=1.0)]
        await engine.execute(routes, budget=1.0, top=3)
        assert "High value" in calls[0]
        assert "Mid value" in calls[1]

    @pytest.mark.asyncio
    async def test_specialist_routes_deferred_never_executed(self, tmp_path):
        engine, calls = _engine(tmp_path, {})
        routes = [_route("Company dive", instrument="primr", ev=9.9), _route("Plain gap", ev=1.0)]
        result = await engine.execute(routes, budget=1.0, top=2)

        statuses = {o.topic: o.status for o in result.outcomes}
        assert statuses["Company dive"] == "deferred"
        assert statuses["Plain gap"] == "filled"
        assert all("Company dive" not in c for c in calls)  # specialist never researched
        deferred = next(o for o in result.outcomes if o.status == "deferred")
        assert "deepr something" in deferred.detail  # the command to run is surfaced

    @pytest.mark.asyncio
    async def test_budget_exhaustion_skips_not_fails(self, tmp_path):
        engine, _ = _engine(
            tmp_path,
            {
                "First": {"answer": "First finding.", "cost": 0.90},
                "Second": {"answer": "Second finding.", "cost": 0.5},
            },
        )
        routes = [_route("First", ev=2.0, cost=0.90), _route("Second", ev=1.0, cost=0.5)]
        result = await engine.execute(routes, budget=1.0, top=2)

        statuses = {o.topic: o.status for o in result.outcomes}
        assert statuses["First"] == "filled"
        assert statuses["Second"] == "skipped"

    @pytest.mark.asyncio
    async def test_dry_run_spends_and_writes_nothing(self, tmp_path):
        beliefs = BeliefStore("GapFill Test Expert", storage_dir=tmp_path / "beliefs")

        async def exploding(query, budget):
            raise AssertionError("dry run must not research")

        engine = GapFillEngine(_expert(), research_fn=exploding, belief_store=beliefs)
        result = await engine.execute([_route("Topic A")], budget=1.0, dry_run=True)

        assert result.outcomes[0].status == "would_fill"
        assert result.total_cost == 0.0
        assert len(beliefs.beliefs) == 0

    @pytest.mark.asyncio
    async def test_research_error_is_per_gap_not_fatal(self, tmp_path):
        engine, _ = _engine(tmp_path, {"Broken": {"error": "provider down"}, "Fine": {"answer": "ok", "cost": 0.01}})
        routes = [_route("Broken", ev=2.0), _route("Fine", ev=1.0)]
        result = await engine.execute(routes, budget=1.0, top=2)

        statuses = {o.topic: o.status for o in result.outcomes}
        assert statuses["Broken"] == "failed"
        assert statuses["Fine"] == "filled"

    @pytest.mark.asyncio
    async def test_spend_decision_denial_skips_before_research(self, tmp_path):
        async def exploding_research(query: str, budget: float) -> dict:
            raise AssertionError("research must not start when value gate denies metered spend")

        absorber = _FakeAbsorber(estimated_cost=0.03)
        engine = GapFillEngine(
            _expert(),
            research_fn=exploding_research,
            absorber=absorber,
            spend_decision_fn=lambda route, estimated_cost: SimpleNamespace(
                allowed=False,
                reason=f"value too low for ${estimated_cost:.2f}",
            ),
        )

        result = await engine.execute([_route("Low value gap", cost=0.20)], budget=1.0)

        assert absorber.calls == 0
        assert result.total_cost == 0.0
        assert result.outcomes[0].status == "skipped"
        assert result.outcomes[0].detail.startswith("metered deferred: value too low")


class TestRoutesFromQueries:
    """Reflection follow-ups adapt to GapRoutes and reuse the engine."""

    def test_preserves_order_and_marks_research_route(self):
        from deepr.experts.gap_fill import routes_from_queries

        routes = routes_from_queries(["first query", "second query", "third query"])
        assert [r.topic for r in routes] == ["first query", "second query", "third query"]
        assert all(r.instrument == "research" for r in routes)
        # ev_cost_ratio descends so the engine executes in emitted order
        assert routes[0].ev_cost_ratio > routes[1].ev_cost_ratio > routes[2].ev_cost_ratio

    @pytest.mark.asyncio
    async def test_followups_execute_through_the_engine(self, tmp_path):
        from deepr.experts.gap_fill import routes_from_queries

        engine, calls = _engine(tmp_path, {"alpha": {"answer": "Alpha finding.", "cost": 0.01}})
        routes = routes_from_queries(["alpha question", "beta question"])
        result = await engine.execute(routes, budget=1.0, top=2)

        assert result.filled_count == 2
        assert "alpha question" in calls[0]
        assert "beta question" in calls[1]
