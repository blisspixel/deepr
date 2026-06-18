"""Tests for deepr.experts.sync - subscriptions and the freshness sync engine.

The engine takes an injectable research_fn and a real BeliefStore /
SubscriptionStore on tmp dirs, so every test is free (no providers).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from deepr.experts.beliefs import BeliefStore
from deepr.experts.report_absorber import ReportAbsorber
from deepr.experts.sync import (
    DEFAULT_SUBSCRIPTION_BUDGET,
    ExpertSyncEngine,
    Subscription,
    SubscriptionStore,
)


def _expert():
    return SimpleNamespace(name="Sync Test Expert", domain="ai")


def _sub_store(tmp_path, *subs) -> SubscriptionStore:
    store = SubscriptionStore("Sync Test Expert", storage_dir=tmp_path / "knowledge")
    for s in subs:
        store.add(s)
    return store


class _FakeExtractionClient:
    """OpenAI-shaped client whose extraction returns one strong claim."""

    def __init__(self, statement="Topic X gained capability Y in June 2026"):
        import json

        content = json.dumps({"claims": [{"statement": statement, "confidence": 0.9, "evidence": ["src"]}]})
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._make_create(content)),
        )

    def _make_create(self, content):
        async def _create(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        return _create


def _engine(tmp_path, sub_store, research_answers: dict[str, dict]):
    """Engine with injected research + a real absorber on a tmp belief store."""
    beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
    absorber = ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs)

    async def research_fn(query: str, budget: float) -> dict:
        for key, answer in research_answers.items():
            if key.lower() in query.lower():
                return answer
        return {"answer": "no significant changes", "cost": 0.0}

    return ExpertSyncEngine(
        _expert(),
        research_fn=research_fn,
        subscription_store=sub_store,
        belief_store=beliefs,
        absorber=absorber,
    )


class TestSubscriptionStore:
    def test_add_list_remove_roundtrip(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="MCP spec changes"))
        assert len(store.subscriptions) == 1

        reloaded = SubscriptionStore("Sync Test Expert", storage_dir=tmp_path / "knowledge")
        assert reloaded.subscriptions[0].topic == "MCP spec changes"
        assert reloaded.subscriptions[0].budget == DEFAULT_SUBSCRIPTION_BUDGET

        assert reloaded.remove("mcp SPEC changes") is True  # case-insensitive
        assert reloaded.subscriptions == []

    def test_duplicate_topic_rejected(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic A"))
        with pytest.raises(ValueError, match="Already subscribed"):
            store.add(Subscription(topic="topic a"))

    def test_due_respects_cadence(self, tmp_path):
        fresh = Subscription(topic="Fresh", last_synced=datetime.now(UTC) - timedelta(days=1), cadence_days=7)
        stale = Subscription(topic="Stale", last_synced=datetime.now(UTC) - timedelta(days=8), cadence_days=7)
        never = Subscription(topic="Never")
        store = _sub_store(tmp_path, fresh, stale, never)

        due_topics = {s.topic for s in store.due()}
        assert due_topics == {"Stale", "Never"}


class TestFreshnessQuery:
    def test_first_sync_uses_30_day_window(self):
        q = ExpertSyncEngine.build_freshness_query(Subscription(topic="MCP spec"))
        assert "in the last 30 days" in q
        assert "MCP spec" in q

    def test_subsequent_sync_uses_last_synced_date(self):
        sub = Subscription(topic="MCP spec", last_synced=datetime(2026, 6, 1, tzinfo=UTC), query="transports only")
        q = ExpertSyncEngine.build_freshness_query(sub)
        assert "since 2026-06-01" in q
        assert "transports only" in q


class TestSyncEngine:
    @pytest.mark.asyncio
    async def test_sync_absorbs_delta_and_reports_what_changed(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        engine = _engine(
            tmp_path, store, {"Topic X": {"answer": "Topic X gained capability Y in June 2026.", "cost": 0.01}}
        )

        result = await engine.sync(budget=2.0)

        assert result.synced_count == 1
        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        assert outcome.absorbed == 1
        # last_synced persisted
        reloaded = SubscriptionStore("Sync Test Expert", storage_dir=tmp_path / "knowledge")
        assert reloaded.subscriptions[0].last_synced is not None
        # The perspective delta reflects the new belief
        assert result.delta["total_changes"] == 1
        assert "capability Y" in result.delta["added"][0]["claim"]

    @pytest.mark.asyncio
    async def test_no_changes_skips_absorb_but_updates_cadence(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Quiet Topic"))
        engine = _engine(tmp_path, store, {"Quiet Topic": {"answer": "No significant changes.", "cost": 0.0}})

        result = await engine.sync(budget=1.0)

        assert result.outcomes[0].status == "no_changes"
        assert len(engine.belief_store.beliefs) == 0
        assert store.subscriptions[0].last_synced is not None  # cadence advanced

    @pytest.mark.asyncio
    async def test_empty_fresh_context_skips_absorb(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Quiet Topic"))
        engine = _engine(
            tmp_path,
            store,
            {
                "Quiet Topic": {
                    "answer": "Fresh context is unavailable, so no meaningful changes can be reported.",
                    "cost": 0.0,
                    "fresh_context": {"source_count": 0},
                }
            },
        )

        result = await engine.sync(budget=1.0)

        assert result.outcomes[0].status == "no_changes"
        assert "no sources" in result.outcomes[0].detail
        assert len(engine.belief_store.beliefs) == 0
        assert store.subscriptions[0].last_synced is not None

    @pytest.mark.asyncio
    async def test_dry_run_spends_and_writes_nothing(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X"))

        async def exploding_research(query, budget):  # must never be called
            raise AssertionError("dry run must not research")

        engine = ExpertSyncEngine(
            _expert(),
            research_fn=exploding_research,
            subscription_store=store,
            belief_store=BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs"),
        )
        result = await engine.sync(budget=1.0, dry_run=True)

        assert result.outcomes[0].status == "would_sync"
        assert result.total_cost == 0.0
        assert store.subscriptions[0].last_synced is None

    @pytest.mark.asyncio
    async def test_budget_exhaustion_skips_remaining(self, tmp_path):
        store = _sub_store(
            tmp_path,
            Subscription(topic="Topic X", budget=0.5),
            Subscription(topic="Topic Z", budget=0.5),
        )
        engine = _engine(
            tmp_path,
            store,
            {
                "Topic X": {"answer": "Topic X gained capability Y in June 2026.", "cost": 0.99},
                "Topic Z": {"answer": "irrelevant", "cost": 0.5},
            },
        )

        result = await engine.sync(budget=1.0)

        statuses = {o.topic: o.status for o in result.outcomes}
        assert statuses["Topic X"] == "synced"
        assert statuses["Topic Z"] == "skipped"

    @pytest.mark.asyncio
    async def test_research_error_marks_failed_not_fatal(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X"))
        engine = _engine(tmp_path, store, {"Topic X": {"error": "provider down"}})

        result = await engine.sync(budget=1.0)

        assert result.outcomes[0].status == "failed"
        assert "provider down" in result.outcomes[0].detail
        assert store.subscriptions[0].last_synced is None  # not advanced on failure

    @pytest.mark.asyncio
    async def test_only_due_subscriptions_run(self, tmp_path):
        fresh = Subscription(topic="Fresh", last_synced=datetime.now(UTC) - timedelta(hours=1))
        store = _sub_store(tmp_path, fresh)
        engine = _engine(tmp_path, store, {})

        result = await engine.sync(budget=1.0)
        assert result.outcomes == []

        result_all = await engine.sync(budget=1.0, only_due=False)
        assert len(result_all.outcomes) == 1
