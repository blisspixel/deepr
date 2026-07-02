"""Tests for deepr.experts.sync - subscriptions and the freshness sync engine.

The engine takes an injectable research_fn and a real BeliefStore /
SubscriptionStore on tmp dirs, so every test is free (no providers).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from deepr.experts import sync as sync_module
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.report_absorber import ReportAbsorber
from deepr.experts.source_pack_compiler import build_semantic_claim_extraction
from deepr.experts.sync import (
    _NO_CHANGES_MARKER,
    DEFAULT_SUBSCRIPTION_BUDGET,
    ExpertSyncEngine,
    Subscription,
    SubscriptionStore,
    fresh_sources_unchanged,
)


def _expert():
    return SimpleNamespace(name="Sync Test Expert", domain="ai")


def _sub_store(tmp_path, *subs) -> SubscriptionStore:
    store = SubscriptionStore("Sync Test Expert", storage_dir=tmp_path / "knowledge")
    for s in subs:
        store.add(s)
    return store


def _topic_x_source_pack() -> dict:
    return {
        "schema_version": "deepr.source_pack.v1",
        "mode": "fresh",
        "source_count": 1,
        "retrieved_source_count": 1,
        "sources": [
            {
                "label": "S1",
                "title": "Release notes",
                "url": "https://example.com/release",
                "excerpt": "Topic X gained capability Y in June 2026.",
                "content_hash": "c" * 64,
            }
        ],
    }


def _topic_x_research_fn(source_pack: dict):
    async def research_fn(query: str, budget: float) -> dict:
        return {
            "answer": "Topic X gained capability Y in June 2026. [S1]",
            "cost": 0.0,
            "fresh_context": {"source_count": 1, "mode": "fresh"},
            "source_pack": source_pack,
        }

    return research_fn


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


class _FakeClaimExtractor:
    def __init__(self):
        self.calls: list[dict] = []

    async def extract(
        self,
        source_notes,
        source_pack_payload,
        *,
        source_note_artifact="",
        budget_usd=0.0,
        session_id="semantic_claim_extraction",
        generated_at="",
    ):
        self.calls.append(
            {
                "source_note_artifact": source_note_artifact,
                "budget_usd": budget_usd,
                "session_id": session_id,
                "generated_at": generated_at,
                "source_count": len(source_pack_payload["source_pack"]["sources"]),
            }
        )
        note = source_notes["notes"][0]
        window = note["windows"][0]
        return build_semantic_claim_extraction(
            source_notes,
            {
                "claims": [
                    {
                        "statement": "Topic X gained capability Y in June 2026.",
                        "confidence": 0.9,
                        "source_refs": [
                            {
                                "note_id": note["note_id"],
                                "window_id": window["window_id"],
                                "quote": "Topic X gained capability Y in June 2026",
                            }
                        ],
                    }
                ]
            },
            source_note_artifact=source_note_artifact,
            provider="local",
            model="qwen",
            capacity_source="local",
            cost_usd=0.0,
            generated_at=generated_at,
        )


_PERSPECTIVE_CASES = [
    {
        "id": "knowledge_gap",
        "statement": "What statistical signals should drive expert gap prioritization?",
        "claim_kind": "knowledge_gap",
        "claim_fields": {
            "priority": 5,
            "expected_value": 0.9,
            "estimated_cost": 0.0,
            "questions": ["What statistical signals should drive expert gap prioritization?"],
        },
        "verification": {
            "origin": "The source note exposed an unresolved prioritization question.",
            "rationale": "The expert should retain the gap until a grounded scoring model exists.",
            "uncertainty": "The best statistical signal mix is not established by the cited source.",
            "confidence": 0.8,
        },
        "operation": "promote_gap",
        "payload_key": "gap",
        "tracker_attr": "knowledge_gaps",
        "identity_field": "topic",
        "result_identity_key": "gap_topic",
    },
    {
        "id": "exploration_agenda",
        "statement": "Map evidence needed for sync-side perspective compilation.",
        "claim_kind": "exploration_agenda",
        "claim_fields": {
            "title": "Map evidence needed for sync-side perspective compilation.",
            "priority": 4,
            "expected_value": 0.8,
            "estimated_cost": 0.0,
            "questions": ["Which evidence signals should drive sync-side perspective writes?"],
            "success_criteria": ["A follow-up sync run accepts every promoted state kind."],
        },
        "verification": {
            "origin": "The source note exposed a recurring exploration direction.",
            "rationale": "The expert should retain the agenda before widening default sync writes.",
            "uncertainty": "The best sequencing for promotion coverage is not fully settled.",
            "expected_observations": ["Future sync tests cover all promoted perspective kinds."],
            "disconfirming_signals": ["Default sync migration happens before coverage exists."],
            "confidence": 0.81,
        },
        "operation": "promote_exploration_agenda",
        "payload_key": "agenda",
        "tracker_attr": "exploration_agendas",
        "identity_field": "title",
        "result_identity_key": "agenda_title",
    },
    {
        "id": "hypothesis",
        "statement": "Sync apply coverage reduces unsafe default migration risk.",
        "claim_kind": "hypothesis",
        "claim_fields": {
            "title": "Sync apply coverage reduces unsafe default migration risk.",
            "priority": 4,
            "assumptions": ["Every promoted state kind can be replayed through one apply gate."],
        },
        "verification": {
            "origin": "The source note exposed a testable sync-migration idea.",
            "rationale": "The expert should retain the hypothesis without promoting it as fact.",
            "uncertainty": "The reduction in migration risk is not measured yet.",
            "expected_observations": ["Coverage finds promotion failures before defaults change."],
            "disconfirming_signals": ["Migration bugs occur despite the coverage."],
            "confidence": 0.72,
        },
        "operation": "promote_hypothesis",
        "payload_key": "hypothesis",
        "tracker_attr": "hypotheses",
        "identity_field": "title",
        "result_identity_key": "hypothesis_title",
    },
    {
        "id": "concept",
        "statement": "Promotion coverage is a reusable sync migration concept.",
        "claim_kind": "concept",
        "claim_fields": {
            "title": "Promotion coverage",
            "name": "Promotion coverage",
            "description": "A reusable coverage pattern for opt-in state writes before default migration.",
            "priority": 4,
            "key_properties": ["Opt-in first.", "One apply gate.", "Default migration last."],
            "related_terms": ["sync apply", "graph commit"],
        },
        "verification": {
            "origin": "The source note exposed a reusable migration concept.",
            "rationale": "The expert should retain the concept for future graph-write migrations.",
            "uncertainty": "The concept has not been calibrated across every write surface.",
            "expected_observations": ["Future migrations reuse the same opt-in coverage pattern."],
            "disconfirming_signals": ["The pattern adds tests without reducing migration risk."],
            "confidence": 0.7,
        },
        "operation": "promote_concept",
        "payload_key": "concept",
        "tracker_attr": "concepts",
        "identity_field": "name",
        "result_identity_key": "concept_name",
    },
    {
        "id": "stance",
        "statement": "Default sync should wait for full promoted-state apply coverage.",
        "claim_kind": "stance",
        "claim_fields": {
            "title": "Default sync should wait for full promoted-state apply coverage.",
            "position": "Keep legacy absorb as default until every promoted state kind has opt-in apply coverage.",
            "priority": 4,
            "tradeoffs": ["Migration speed is slower.", "Default write risk is lower."],
            "decision_criteria": ["Prefer coverage before widening durable writes."],
        },
        "verification": {
            "origin": "The source note exposed a migration sequencing position.",
            "rationale": "The expert should retain the stance without promoting it as fact.",
            "uncertainty": "The exact coverage threshold may change after failure testing.",
            "expected_observations": ["Default migration waits for all promotion tests."],
            "disconfirming_signals": ["Coverage blocks useful migration without catching defects."],
            "confidence": 0.68,
        },
        "operation": "promote_stance",
        "payload_key": "stance",
        "tracker_attr": "stances",
        "identity_field": "title",
        "result_identity_key": "stance_title",
    },
    {
        "id": "original_idea",
        "statement": "Use sync promotion packets as migration rehearsal artifacts.",
        "claim_kind": "original_idea",
        "claim_fields": {
            "title": "Sync promotion packets",
            "priority": 4,
            "assumptions": ["Promotion packets expose each state write without changing defaults."],
            "implications": ["Future default migration can replay the same evidence path."],
        },
        "verification": {
            "origin": "The source note exposed a new migration rehearsal idea.",
            "rationale": "The expert should retain the original idea without treating it as verified external fact.",
            "uncertainty": "The idea has not been validated across repeated sync migrations.",
            "expected_observations": ["Promotion packets become reusable migration fixtures."],
            "disconfirming_signals": ["The packets do not predict default migration behavior."],
            "confidence": 0.66,
        },
        "operation": "promote_original_idea",
        "payload_key": "original_idea",
        "tracker_attr": "original_ideas",
        "identity_field": "title",
        "result_identity_key": "original_idea_title",
    },
]


class _FakePerspectiveClaimExtractor:
    def __init__(self, case):
        self.case = case

    async def extract(
        self,
        source_notes,
        source_pack_payload,
        *,
        source_note_artifact="",
        budget_usd=0.0,
        session_id="semantic_claim_extraction",
        generated_at="",
    ):
        note = source_notes["notes"][0]
        window = note["windows"][0]
        claim = {
            "statement": self.case["statement"],
            "claim_kind": self.case["claim_kind"],
            "confidence": 0.72,
            "source_refs": [{"note_id": note["note_id"], "window_id": window["window_id"]}],
            **self.case["claim_fields"],
        }
        return build_semantic_claim_extraction(
            source_notes,
            {"claims": [claim]},
            source_note_artifact=source_note_artifact,
            provider="local",
            model="qwen",
            capacity_source="local",
            cost_usd=0.0,
            generated_at=generated_at,
        )


class _FakeClaimVerifier:
    def __init__(self):
        self.calls: list[dict] = []

    async def verify(
        self,
        claim_extraction,
        source_notes,
        source_pack_payload,
        *,
        claim_extraction_artifact="",
        source_note_artifact="",
        budget_usd=0.0,
        session_id="claim_verification",
        generated_at="",
        recall_belief_store=None,
        recall_domain=None,
    ):
        self.calls.append(
            {
                "claim_extraction_artifact": claim_extraction_artifact,
                "source_note_artifact": source_note_artifact,
                "budget_usd": budget_usd,
                "session_id": session_id,
                "generated_at": generated_at,
                "recall_belief_store": recall_belief_store,
                "recall_domain": recall_domain,
                "source_count": len(source_pack_payload["source_pack"]["sources"]),
                "note_count": len(source_notes["notes"]),
            }
        )
        return {
            "contract": {
                "provider": "local",
                "model": "qwen",
                "capacity_source": "local",
                "cost_usd": 0.0,
            },
            "verifications": [
                {
                    "candidate_id": claim_extraction["candidates"][0]["candidate_id"],
                    "support_verdict": "supported",
                    "contradiction_verdict": "none",
                    "dedup_verdict": "new",
                    "temporal_scope_verdict": "valid",
                    "confidence": 0.91,
                    "rationale": "The cited source window supports the claim.",
                }
            ],
        }


class _FakePerspectiveClaimVerifier:
    def __init__(self, case):
        self.case = case

    async def verify(
        self,
        claim_extraction,
        source_notes,
        source_pack_payload,
        *,
        claim_extraction_artifact="",
        source_note_artifact="",
        budget_usd=0.0,
        session_id="claim_verification",
        generated_at="",
        recall_belief_store=None,
        recall_domain=None,
    ):
        verification = {
            "candidate_id": claim_extraction["candidates"][0]["candidate_id"],
            "support_verdict": "not_applicable",
            "contradiction_verdict": "none",
            "dedup_verdict": "new",
            "temporal_scope_verdict": "not_applicable",
            **self.case["verification"],
        }
        return {
            "contract": {
                "provider": "local",
                "model": "qwen",
                "capacity_source": "local",
                "cost_usd": 0.0,
            },
            "verifications": [verification],
        }


class _InvalidClaimVerifier:
    async def verify(self, *args, **kwargs):
        return ["not", "a", "verifier", "object"]


class _FailingAbsorber:
    async def absorb(self, *args, **kwargs):
        raise AssertionError("legacy absorber should not run")


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
    def test_first_sync_is_comprehensive_baseline(self):
        # No last_synced -> populate the new expert, not a delta. This is what
        # lets evergreen topics ("coffee extraction") gain knowledge on sync 1.
        q = ExpertSyncEngine.build_freshness_query(Subscription(topic="MCP spec"))
        assert "comprehensive" in q
        assert "MCP spec" in q
        assert "What has changed" not in q
        assert _NO_CHANGES_MARKER not in q

    def test_subsequent_sync_uses_last_synced_date_as_delta(self):
        sub = Subscription(topic="MCP spec", last_synced=datetime(2026, 6, 1, tzinfo=UTC), query="transports only")
        q = ExpertSyncEngine.build_freshness_query(sub)
        assert "What has changed" in q
        assert "since 2026-06-01" in q
        assert "transports only" in q
        assert _NO_CHANGES_MARKER in q


class TestFreshSourcesUnchanged:
    """The pure change-detection gate fails safe toward 'changed'."""

    def test_no_prior_pack_is_changed(self):
        assert fresh_sources_unchanged(None, {"sources": [{"content_hash": "a"}]}) is False

    def test_no_current_hashes_is_changed(self):
        # Fetch failures / snippet-only sources cannot prove no-change.
        assert fresh_sources_unchanged({"sources": [{"content_hash": "a"}]}, {"sources": []}) is False
        assert fresh_sources_unchanged({"sources": [{"content_hash": "a"}]}, {"sources": [{"url": "x"}]}) is False

    def test_prior_without_hashes_is_changed(self):
        # Packs that predate this feature carry no content_hash -> proceed.
        assert fresh_sources_unchanged({"sources": [{"url": "x"}]}, {"sources": [{"content_hash": "a"}]}) is False

    def test_subset_of_prior_is_unchanged(self):
        prior = {"sources": [{"content_hash": "a"}, {"content_hash": "b"}]}
        current = {"sources": [{"content_hash": "a"}]}
        assert fresh_sources_unchanged(prior, current) is True

    def test_identical_hashes_are_unchanged(self):
        pack = {"sources": [{"content_hash": "a"}, {"content_hash": "b"}]}
        assert fresh_sources_unchanged(pack, dict(pack)) is True

    def test_any_new_hash_is_changed(self):
        prior = {"sources": [{"content_hash": "a"}]}
        current = {"sources": [{"content_hash": "a"}, {"content_hash": "c"}]}
        assert fresh_sources_unchanged(prior, current) is False


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
    async def test_markdown_wrapped_no_changes_skips_absorb(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Quiet Topic"))
        engine = _engine(tmp_path, store, {"Quiet Topic": {"answer": "**no significant changes**", "cost": 0.0}})

        result = await engine.sync(budget=1.0)

        assert result.outcomes[0].status == "no_changes"
        assert len(engine.belief_store.beliefs) == 0
        assert store.subscriptions[0].last_synced is not None

    @pytest.mark.asyncio
    async def test_unchanged_sources_skip_absorb_on_second_sync(self, tmp_path):
        # Same sources (same content hashes) as last sync -> skip the paid
        # absorb even though the model wrote a substantive (non-marker) answer.
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5, cadence_days=0))
        source_pack = {
            "schema_version": "deepr.source_pack.v1",
            "mode": "fresh",
            "source_count": 1,
            "retrieved_source_count": 1,
            "sources": [
                {
                    "label": "S1",
                    "url": "https://example.com/release",
                    "content_hash": "f" * 64,
                    "excerpt": "Topic X gained capability Y in June 2026.",
                }
            ],
        }
        engine = _engine(
            tmp_path,
            store,
            {
                "Topic X": {
                    "answer": "Topic X gained capability Y in June 2026. [S1]",
                    "cost": 0.01,
                    "fresh_context": {"source_count": 1, "mode": "fresh"},
                    "source_pack": source_pack,
                }
            },
        )

        first = await engine.sync(budget=2.0, only_due=False)
        assert first.outcomes[0].status == "synced"
        assert first.outcomes[0].absorbed == 1
        assert len(engine.belief_store.beliefs) == 1

        second = await engine.sync(budget=2.0, only_due=False)
        assert second.outcomes[0].status == "no_changes"
        assert "unchanged since last sync" in second.outcomes[0].detail
        assert second.outcomes[0].source_pack_artifact  # still records provenance
        # The gate fired before absorb: belief count is unchanged.
        assert len(engine.belief_store.beliefs) == 1

    @pytest.mark.asyncio
    async def test_sync_passes_prior_source_pack_to_prior_aware_research_fn(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5, cadence_days=0))
        calls = []

        async def research_fn(query: str, budget: float, *, prior_source_pack=None) -> dict:
            calls.append(prior_source_pack)
            return {
                "answer": "Topic X gained capability Y in June 2026. [S1]",
                "cost": 0.01,
                "fresh_context": {"source_count": 1, "mode": "fresh"},
                "source_pack": {
                    "schema_version": "deepr.source_pack.v1",
                    "mode": "fresh",
                    "source_count": 1,
                    "retrieved_source_count": 1,
                    "sources": [
                        {
                            "label": "S1",
                            "url": "https://example.com/release",
                            "etag": '"topic-x-v1"',
                            "last_modified": "Wed, 01 Jul 2026 00:00:00 GMT",
                            "content_hash": "d" * 64,
                            "excerpt": "Topic X gained capability Y in June 2026.",
                        }
                    ],
                },
            }

        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        absorber = ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs)
        engine = ExpertSyncEngine(
            _expert(), research_fn=research_fn, subscription_store=store, belief_store=beliefs, absorber=absorber
        )

        first = await engine.sync(budget=2.0, only_due=False)
        second = await engine.sync(budget=2.0, only_due=False)

        assert first.outcomes[0].status == "synced"
        assert second.outcomes[0].status == "no_changes"
        assert calls[0] is None
        assert calls[1]["sources"][0]["etag"] == '"topic-x-v1"'
        assert calls[1]["sources"][0]["last_modified"] == "Wed, 01 Jul 2026 00:00:00 GMT"

    @pytest.mark.asyncio
    async def test_changed_source_hash_proceeds_to_absorb(self, tmp_path):
        # A new content hash on the second sync falsifies the no-change subset,
        # so the pipeline runs normally and absorbs the delta.
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5, cadence_days=0))
        calls = {"n": 0}

        async def research_fn(query: str, budget: float) -> dict:
            calls["n"] += 1
            digest = "a" * 64 if calls["n"] == 1 else "b" * 64
            return {
                "answer": "Topic X gained capability Y in June 2026. [S1]",
                "cost": 0.01,
                "fresh_context": {"source_count": 1, "mode": "fresh"},
                "source_pack": {
                    "schema_version": "deepr.source_pack.v1",
                    "mode": "fresh",
                    "source_count": 1,
                    "sources": [{"label": "S1", "url": "https://example.com/release", "content_hash": digest}],
                },
            }

        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        absorber = ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs)
        engine = ExpertSyncEngine(
            _expert(), research_fn=research_fn, subscription_store=store, belief_store=beliefs, absorber=absorber
        )

        first = await engine.sync(budget=2.0, only_due=False)
        second = await engine.sync(budget=2.0, only_due=False)

        assert first.outcomes[0].status == "synced"
        assert second.outcomes[0].status == "synced"

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
        assert result.outcomes[0].source_pack_artifact.endswith("_quiet-topic.json")
        assert result.outcomes[0].source_count == 0
        assert len(engine.belief_store.beliefs) == 0
        assert store.subscriptions[0].last_synced is not None

    @pytest.mark.asyncio
    async def test_source_pack_artifact_records_context_used_for_sync(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        source_pack = {
            "schema_version": "deepr.source_pack.v1",
            "mode": "deep",
            "source_count": 1,
            "retrieved_source_count": 1,
            "sources": [
                {
                    "label": "S1",
                    "title": "Release notes",
                    "url": "https://example.com/release",
                    "excerpt": "Topic X gained capability Y in June 2026.",
                }
            ],
        }
        engine = _engine(
            tmp_path,
            store,
            {
                "Topic X": {
                    "answer": "Topic X gained capability Y in June 2026. [S1]",
                    "cost": 0.0,
                    "fresh_context": {"source_count": 1, "mode": "deep"},
                    "source_pack": source_pack,
                }
            },
        )

        result = await engine.sync(budget=1.0)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        assert outcome.source_count == 1
        assert outcome.context_mode == "deep"
        assert outcome.source_note_artifact.endswith("_topic-x.json")
        artifact = tmp_path / "knowledge" / outcome.source_pack_artifact
        assert artifact.exists()
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["schema_version"] == "deepr.sync_source_pack.v1"
        assert data["topic"] == "Topic X"
        assert data["source_pack"]["sources"][0]["url"] == "https://example.com/release"
        manifest_path = tmp_path / "knowledge" / outcome.source_pack_manifest_artifact
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["schema_version"] == "deepr-source-pack-manifest-v1"
        assert manifest["kind"] == "deepr.expert.source_pack_manifest"
        assert manifest["contract"]["semantic_judgment"] is False
        assert manifest["source_pack"]["artifact_path"] == outcome.source_pack_artifact
        assert manifest["manifest"]["source_entry_count"] == 1
        assert manifest["manifest"]["valid_content_hash_count"] == 0
        assert manifest["manifest"]["missing_content_hash_count"] == 1
        assert manifest["manifest"]["invalid_content_hash_count"] == 0
        assert manifest["manifest"]["ready_for_semantic_compile"] is False
        assert manifest["sources"][0]["url"] == "https://example.com/release"
        assert manifest["sources"][0]["excerpt_hash"]
        source_note_path = tmp_path / "knowledge" / outcome.source_note_artifact
        source_notes = json.loads(source_note_path.read_text(encoding="utf-8"))
        assert source_notes["schema_version"] == "deepr-source-note-v1"
        assert source_notes["kind"] == "deepr.expert.source_notes"
        assert source_notes["contract"]["semantic_judgment"] is False
        assert source_notes["contract"]["model_calls"] is False
        assert source_notes["source_pack"]["artifact_path"] == outcome.source_pack_artifact
        assert source_notes["source_pack"]["manifest_artifact_path"] == outcome.source_pack_manifest_artifact
        assert source_notes["summary"]["ready_for_claim_extraction"] is False
        assert source_notes["summary"]["failure_reasons"] == ["invalid_or_missing_content_hash"]
        assert source_notes["notes"][0]["source_pointer"] == "/source_pack/sources/0"
        assert source_notes["notes"][0]["windows"][0]["source_text_ref"] == "excerpt"

    @pytest.mark.asyncio
    async def test_source_pack_persist_writes_content_addressed_snapshots(self, tmp_path):
        import hashlib

        content = "Topic X gained capability Y in June 2026. Full fetched page text."
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        source_pack = {
            "schema_version": "deepr.source_pack.v1",
            "mode": "fresh",
            "source_count": 2,
            "retrieved_source_count": 2,
            "sources": [
                {
                    "label": "S1",
                    "title": "Release notes",
                    "url": "https://example.com/release",
                    "fetched": True,
                    "excerpt": content[:40],
                    "content": content,
                    "content_hash": content_hash,
                },
                {
                    "label": "S2",
                    "title": "Unfetched result",
                    "url": "https://example.com/other",
                    "fetched": False,
                    "excerpt": "",
                    "content": "",
                    "content_hash": "",
                },
            ],
        }
        engine = _engine(
            tmp_path,
            store,
            {
                "Topic X": {
                    "answer": "Topic X gained capability Y in June 2026. [S1]",
                    "cost": 0.0,
                    "fresh_context": {"source_count": 2, "mode": "fresh"},
                    "source_pack": source_pack,
                }
            },
        )

        result = await engine.sync(budget=1.0)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        pack = json.loads((tmp_path / "knowledge" / outcome.source_pack_artifact).read_text(encoding="utf-8"))
        fetched, unfetched = pack["source_pack"]["sources"]
        # Transient content never lands in the durable pack.
        assert "content" not in fetched
        assert "content" not in unfetched
        assert fetched["snapshot_ref"] == f"sync_artifacts/snapshots/{content_hash}.txt"
        assert "snapshot_ref" not in unfetched
        snapshot_path = tmp_path / "knowledge" / fetched["snapshot_ref"]
        snapshot_text = snapshot_path.read_text(encoding="utf-8")
        # Re-verifiability: hashing the snapshot file reproduces content_hash.
        assert hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest() == content_hash

    def test_snapshot_writer_refuses_content_that_does_not_hash_to_content_hash(self, tmp_path):
        from deepr.experts.sync_support import write_source_snapshots

        # The conditional 304 reuse shape: prior excerpt text carried with the
        # prior FULL-content hash. Writing it would corrupt the store forever.
        pack = {
            "sources": [
                {
                    "url": "https://example.com/release",
                    "content": "Truncated cached excerpt...",
                    "content_hash": "b" * 64,
                },
                {
                    "url": "https://example.com/evil",
                    "content": "attacker text",
                    "content_hash": "../outside",
                },
            ]
        }

        write_source_snapshots(pack, tmp_path)

        assert not (tmp_path / "sync_artifacts" / "snapshots").exists()
        assert not (tmp_path / "outside.txt").exists()
        for source in pack["sources"]:
            assert "content" not in source
            assert "snapshot_ref" not in source

    def test_snapshot_writer_skips_oversized_content_without_truncating(self, tmp_path):
        import hashlib

        from deepr.experts.sync_support import MAX_SNAPSHOT_CHARS, write_source_snapshots

        content = "x" * (MAX_SNAPSHOT_CHARS + 1)
        pack = {
            "sources": [
                {
                    "url": "https://example.com/huge",
                    "content": content,
                    "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                }
            ]
        }

        write_source_snapshots(pack, tmp_path)

        assert not (tmp_path / "sync_artifacts" / "snapshots").exists()
        assert "content" not in pack["sources"][0]
        assert "snapshot_ref" not in pack["sources"][0]

    @pytest.mark.asyncio
    async def test_sync_can_write_claim_extraction_sidecar_artifact(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        source_pack = _topic_x_source_pack()
        research_fn = _topic_x_research_fn(source_pack)

        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        absorber = ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs)
        claim_extractor = _FakeClaimExtractor()
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=research_fn,
            subscription_store=store,
            belief_store=beliefs,
            absorber=absorber,
            claim_extractor=claim_extractor,
        )

        result = await engine.sync(budget=1.0)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        assert outcome.claim_extraction_artifact.endswith("_topic-x.json")
        assert claim_extractor.calls[0]["source_note_artifact"] == outcome.source_note_artifact
        assert claim_extractor.calls[0]["budget_usd"] == 0.5
        artifact_path = tmp_path / "knowledge" / outcome.claim_extraction_artifact
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "deepr-semantic-claim-extraction-v1"
        assert payload["contract"]["writes_graph"] is False
        assert payload["summary"]["status"] == "ready_for_verification"
        assert result.delta["total_changes"] == 1

    @pytest.mark.asyncio
    async def test_sync_can_write_claim_verification_and_graph_commit_sidecars(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        source_pack = _topic_x_source_pack()
        research_fn = _topic_x_research_fn(source_pack)

        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        existing, _ = beliefs.add_belief(
            Belief(
                "Topic X gained capability Y in June 2026 from prior release notes.",
                0.8,
                domain="ai",
                source_type="report",
            ),
            check_conflicts=False,
        )
        absorber = ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs)
        claim_extractor = _FakeClaimExtractor()
        claim_verifier = _FakeClaimVerifier()
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=research_fn,
            subscription_store=store,
            belief_store=beliefs,
            absorber=absorber,
            claim_extractor=claim_extractor,
            claim_verifier=claim_verifier,
        )

        result = await engine.sync(budget=1.0)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        assert outcome.claim_extraction_artifact.endswith("_topic-x.json")
        assert outcome.claim_verification_artifact.endswith("_topic-x.json")
        assert outcome.graph_commit_envelope_artifact.endswith("_topic-x.json")
        assert claim_verifier.calls[0]["claim_extraction_artifact"] == outcome.claim_extraction_artifact
        assert claim_verifier.calls[0]["source_note_artifact"] == outcome.source_note_artifact
        assert claim_verifier.calls[0]["budget_usd"] == 0.5
        assert claim_verifier.calls[0]["recall_belief_store"] is beliefs
        assert claim_verifier.calls[0]["recall_domain"] == "ai"

        verification_path = tmp_path / "knowledge" / outcome.claim_verification_artifact
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        decision = verification["decisions"][0]
        assert verification["schema_version"] == "deepr-claim-verification-v1"
        assert verification["contract"]["writes_graph"] is False
        assert verification["summary"]["status"] == "ready_for_commit_envelope"
        assert decision["recall_context"]["candidate_count"] == 1
        recall_candidate = decision["recall_context"]["candidates"][0]
        assert recall_candidate["item_id"] == existing.id
        assert recall_candidate["verdict"] == "candidate_only"
        assert recall_candidate["metadata"]["recall_role"] == "memory_quality_candidate"

        graph_path = tmp_path / "knowledge" / outcome.graph_commit_envelope_artifact
        graph_commit = json.loads(graph_path.read_text(encoding="utf-8"))
        assert graph_commit["schema_version"] == "deepr-graph-commit-envelope-v8"
        assert graph_commit["contract"]["writes_graph"] is False
        assert graph_commit["input"]["claim_extraction_artifact"] == outcome.claim_extraction_artifact
        assert graph_commit["input"]["claim_verification_artifact"] == outcome.claim_verification_artifact
        assert graph_commit["summary"]["status"] == "ready_for_commit"
        assert len(graph_commit["operations"]) == 1

    @pytest.mark.asyncio
    async def test_sync_persists_the_recall_context_the_verifier_actually_used(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        existing, _ = beliefs.add_belief(
            Belief(
                "Topic X gained capability Y in June 2026 from prior release notes.",
                0.8,
                domain="ai",
                source_type="report",
            ),
            check_conflicts=False,
        )

        class _VectorRecallClaimVerifier(_FakeClaimVerifier):
            async def verify(self, claim_extraction, source_notes, source_pack_payload, **kwargs):
                output = await super().verify(claim_extraction, source_notes, source_pack_payload, **kwargs)
                candidate_id = claim_extraction["candidates"][0]["candidate_id"]
                output["recall"] = {
                    "context_by_candidate_id": {
                        candidate_id: [
                            {
                                "item_id": existing.id,
                                "kind": "belief",
                                "domain": "ai",
                                "text": existing.claim,
                                "score": 0.987654,
                                "method": "vector_similarity",
                                "matched_terms": [],
                                "metadata": {"recall_role": "memory_quality_candidate"},
                                "verdict": "candidate_only",
                                "guidance": "routing_only",
                            }
                        ]
                    },
                    "embedding_model": "nomic-embed-text",
                }
                return output

        engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=store,
            belief_store=beliefs,
            absorber=ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs),
            claim_extractor=_FakeClaimExtractor(),
            claim_verifier=_VectorRecallClaimVerifier(),
        )

        result = await engine.sync(budget=1.0)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        verification_path = tmp_path / "knowledge" / outcome.claim_verification_artifact
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        recall_candidate = verification["decisions"][0]["recall_context"]["candidates"][0]
        assert recall_candidate["method"] == "vector_similarity"
        assert recall_candidate["score"] == 0.987654
        assert recall_candidate["item_id"] == existing.id
        assert recall_candidate["verdict"] == "candidate_only"

    @pytest.mark.asyncio
    async def test_sync_can_apply_compiled_graph_commit_instead_of_legacy_absorb(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=store,
            belief_store=beliefs,
            absorber=_FailingAbsorber(),
            claim_extractor=_FakeClaimExtractor(),
            claim_verifier=_FakeClaimVerifier(),
        )

        result = await engine.sync(budget=1.0, apply_graph_commits=True)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        assert outcome.absorbed == 1
        assert outcome.flagged == 0
        assert outcome.graph_commit_apply_status == "applied"
        assert outcome.graph_commit_apply_artifact.endswith("_topic-x.json")
        assert outcome.claim_extraction_artifact.endswith("_topic-x.json")
        assert outcome.claim_verification_artifact.endswith("_topic-x.json")
        assert outcome.graph_commit_envelope_artifact.endswith("_topic-x.json")
        assert store.subscriptions[0].last_synced is not None
        assert result.delta["total_changes"] == 1
        assert len(beliefs.beliefs) == 1
        belief = next(iter(beliefs.beliefs.values()))
        assert belief.claim == "Topic X gained capability Y in June 2026."

        apply_path = tmp_path / "knowledge" / outcome.graph_commit_apply_artifact
        apply_result = json.loads(apply_path.read_text(encoding="utf-8"))
        assert apply_result["schema_version"] == "deepr-graph-commit-apply-v1"
        assert apply_result["summary"]["status"] == "applied"
        assert apply_result["summary"]["dry_run"] is False
        assert apply_result["summary"]["applied_write_count"] == 1

    @pytest.mark.asyncio
    async def test_sync_apply_compiled_graph_commit_requires_ready_envelope(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=store,
            belief_store=beliefs,
            absorber=_FailingAbsorber(),
            claim_extractor=_FakeClaimExtractor(),
            claim_verifier=_InvalidClaimVerifier(),
        )

        result = await engine.sync(budget=1.0, apply_graph_commits=True)

        outcome = result.outcomes[0]
        assert outcome.status == "failed"
        assert outcome.absorbed == 0
        assert outcome.graph_commit_apply_status == "blocked"
        assert outcome.graph_commit_apply_artifact == ""
        assert "claim verification failed: invalid verifier output" in outcome.detail
        assert "graph commit apply failed: compiled graph commit envelope required" in outcome.detail
        assert store.subscriptions[0].last_synced is None
        assert beliefs.beliefs == {}

    @pytest.mark.asyncio
    async def test_sync_apply_result_write_failure_keeps_cadence_due(self, tmp_path, monkeypatch):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        original_write = sync_module.atomic_write_json

        def fail_apply_result_write(path, payload):
            if "graph_commit_apply_results" in str(path):
                raise OSError("disk full")
            original_write(path, payload)

        monkeypatch.setattr(sync_module, "atomic_write_json", fail_apply_result_write)
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=store,
            belief_store=beliefs,
            absorber=_FailingAbsorber(),
            claim_extractor=_FakeClaimExtractor(),
            claim_verifier=_FakeClaimVerifier(),
        )

        result = await engine.sync(budget=1.0, apply_graph_commits=True)

        outcome = result.outcomes[0]
        assert outcome.status == "failed"
        assert outcome.absorbed == 1
        assert outcome.graph_commit_apply_status == "applied"
        assert outcome.graph_commit_apply_artifact == ""
        assert "graph commit apply artifact failed" in outcome.detail
        assert store.subscriptions[0].last_synced is None
        assert len(beliefs.beliefs) == 1

    @pytest.mark.parametrize("case", _PERSPECTIVE_CASES, ids=[case["id"] for case in _PERSPECTIVE_CASES])
    @pytest.mark.asyncio
    async def test_sync_can_apply_compiled_perspective_state_with_injected_tracker(self, tmp_path, case):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        tracker = MetaCognitionTracker("Sync Test Expert", base_path=str(tmp_path / "experts"))
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=store,
            belief_store=beliefs,
            absorber=_FailingAbsorber(),
            claim_extractor=_FakePerspectiveClaimExtractor(case),
            claim_verifier=_FakePerspectiveClaimVerifier(case),
            metacognition_tracker=tracker,
        )

        result = await engine.sync(budget=1.0, apply_graph_commits=True)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        assert outcome.absorbed == 1
        assert outcome.graph_commit_apply_status == "applied"
        assert outcome.graph_commit_apply_artifact.endswith("_topic-x.json")
        assert beliefs.beliefs == {}
        assert result.delta["total_changes"] == 0
        identity = case["claim_fields"].get(case["identity_field"], case["statement"])
        assert identity in getattr(tracker, case["tracker_attr"])
        assert tracker.uncertainty_log[-1]["topic"] == identity

        graph_path = tmp_path / "knowledge" / outcome.graph_commit_envelope_artifact
        graph_commit = json.loads(graph_path.read_text(encoding="utf-8"))
        operation = graph_commit["operations"][0]
        assert operation["operation"] == case["operation"]
        assert operation[case["payload_key"]][case["identity_field"]] == identity

        apply_path = tmp_path / "knowledge" / outcome.graph_commit_apply_artifact
        apply_result = json.loads(apply_path.read_text(encoding="utf-8"))
        assert apply_result["summary"]["status"] == "applied"
        assert apply_result["operation_results"][0]["operation"] == case["operation"]
        assert apply_result["operation_results"][0][case["result_identity_key"]] == identity

    @pytest.mark.asyncio
    async def test_sync_apply_compiled_perspective_state_replays_already_applied_tracker_state(self, tmp_path):
        case = _PERSPECTIVE_CASES[1]
        tracker_root = tmp_path / "experts"
        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        first_tracker = MetaCognitionTracker("Sync Test Expert", base_path=str(tracker_root))
        first_store = _sub_store(tmp_path / "first", Subscription(topic="Topic X", budget=0.5))
        first_engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=first_store,
            belief_store=beliefs,
            absorber=_FailingAbsorber(),
            claim_extractor=_FakePerspectiveClaimExtractor(case),
            claim_verifier=_FakePerspectiveClaimVerifier(case),
            metacognition_tracker=first_tracker,
        )

        first_result = await first_engine.sync(budget=1.0, apply_graph_commits=True)

        first_outcome = first_result.outcomes[0]
        assert first_outcome.status == "synced"
        assert first_outcome.graph_commit_apply_status == "applied"
        identity = case["claim_fields"].get(case["identity_field"], case["statement"])
        assert identity in getattr(first_tracker, case["tracker_attr"])
        assert len(getattr(first_tracker, case["tracker_attr"])) == 1
        assert len(first_tracker.uncertainty_log) == 1

        replay_tracker = MetaCognitionTracker("Sync Test Expert", base_path=str(tracker_root))
        replay_store = _sub_store(tmp_path / "replay", Subscription(topic="Topic X", budget=0.5))
        replay_engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=replay_store,
            belief_store=beliefs,
            absorber=_FailingAbsorber(),
            claim_extractor=_FakePerspectiveClaimExtractor(case),
            claim_verifier=_FakePerspectiveClaimVerifier(case),
            metacognition_tracker=replay_tracker,
        )

        replay_result = await replay_engine.sync(budget=1.0, apply_graph_commits=True)

        replay_outcome = replay_result.outcomes[0]
        assert replay_outcome.status == "synced"
        assert replay_outcome.absorbed == 0
        assert replay_outcome.graph_commit_apply_status == "already_applied"
        assert replay_outcome.graph_commit_apply_artifact.endswith("_topic-x.json")
        assert replay_store.subscriptions[0].last_synced is not None
        assert beliefs.beliefs == {}
        assert identity in getattr(replay_tracker, case["tracker_attr"])
        assert len(getattr(replay_tracker, case["tracker_attr"])) == 1
        assert len(replay_tracker.uncertainty_log) == 1

        apply_path = tmp_path / "replay" / "knowledge" / replay_outcome.graph_commit_apply_artifact
        apply_result = json.loads(apply_path.read_text(encoding="utf-8"))
        assert apply_result["summary"]["status"] == "already_applied"
        assert apply_result["summary"]["applied_write_count"] == 0
        assert apply_result["summary"]["already_applied_count"] == 1
        assert apply_result["operation_results"][0]["status"] == "already_applied"
        assert apply_result["operation_results"][0]["operation"] == case["operation"]
        assert apply_result["operation_results"][0][case["result_identity_key"]] == identity

    @pytest.mark.asyncio
    async def test_sync_invalid_claim_verifier_output_fails_closed_as_detail(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        absorber = ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs)
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=store,
            belief_store=beliefs,
            absorber=absorber,
            claim_extractor=_FakeClaimExtractor(),
            claim_verifier=_InvalidClaimVerifier(),
        )

        result = await engine.sync(budget=1.0)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        assert outcome.claim_extraction_artifact.endswith("_topic-x.json")
        assert outcome.claim_verification_artifact == ""
        assert outcome.graph_commit_envelope_artifact == ""
        assert "claim verification failed: invalid verifier output" in outcome.detail

    @pytest.mark.asyncio
    async def test_sync_graph_commit_write_failure_keeps_verification_artifact(self, tmp_path, monkeypatch):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        absorber = ReportAbsorber(_expert(), client=_FakeExtractionClient(), belief_store=beliefs)
        original_write = sync_module.atomic_write_json

        def fail_graph_commit_write(path, payload):
            if "graph_commit_envelopes" in str(path):
                raise OSError("disk full")
            original_write(path, payload)

        monkeypatch.setattr(sync_module, "atomic_write_json", fail_graph_commit_write)
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=_topic_x_research_fn(_topic_x_source_pack()),
            subscription_store=store,
            belief_store=beliefs,
            absorber=absorber,
            claim_extractor=_FakeClaimExtractor(),
            claim_verifier=_FakeClaimVerifier(),
        )

        result = await engine.sync(budget=1.0)

        outcome = result.outcomes[0]
        assert outcome.status == "synced"
        assert outcome.claim_extraction_artifact.endswith("_topic-x.json")
        assert outcome.claim_verification_artifact.endswith("_topic-x.json")
        assert outcome.graph_commit_envelope_artifact == ""
        assert "graph commit envelope artifact failed" in outcome.detail

    @pytest.mark.asyncio
    async def test_source_pack_write_failure_blocks_absorb(self, tmp_path, monkeypatch):
        store = _sub_store(tmp_path, Subscription(topic="Topic X"))
        engine = _engine(
            tmp_path,
            store,
            {
                "Topic X": {
                    "answer": "Topic X gained capability Y in June 2026. [S1]",
                    "cost": 0.0,
                    "fresh_context": {"source_count": 1, "mode": "fresh"},
                    "source_pack": {
                        "schema_version": "deepr.source_pack.v1",
                        "mode": "fresh",
                        "source_count": 1,
                    },
                }
            },
        )

        def fail_write(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("deepr.experts.sync.atomic_write_json", fail_write)

        result = await engine.sync(budget=1.0)

        outcome = result.outcomes[0]
        assert outcome.status == "failed"
        assert "source pack artifact failed" in outcome.detail
        assert outcome.source_count == 1
        assert len(engine.belief_store.beliefs) == 0
        assert store.subscriptions[0].last_synced is None

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
    async def test_spend_decision_denial_skips_before_research(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))

        async def exploding_research(query, budget):
            raise AssertionError("metered value gate must run before research")

        beliefs = BeliefStore("Sync Test Expert", storage_dir=tmp_path / "beliefs")
        engine = ExpertSyncEngine(
            _expert(),
            research_fn=exploding_research,
            subscription_store=store,
            belief_store=beliefs,
            spend_decision_fn=lambda subscription, estimated_cost: SimpleNamespace(
                allowed=False,
                reason="value 0.010 below conserve hurdle 0.200; defer or use local",
            ),
        )

        result = await engine.sync(budget=1.0)

        assert result.total_cost == 0.0
        assert result.outcomes[0].status == "skipped"
        assert "metered deferred" in result.outcomes[0].detail
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
