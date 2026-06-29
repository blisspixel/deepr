"""Tests for deepr.experts.sync - subscriptions and the freshness sync engine.

The engine takes an injectable research_fn and a real BeliefStore /
SubscriptionStore on tmp dirs, so every test is free (no providers).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from deepr.experts.beliefs import Belief, BeliefStore
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
    ):
        self.calls.append(
            {
                "claim_extraction_artifact": claim_extraction_artifact,
                "source_note_artifact": source_note_artifact,
                "budget_usd": budget_usd,
                "session_id": session_id,
                "generated_at": generated_at,
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
    async def test_sync_can_write_claim_extraction_sidecar_artifact(self, tmp_path):
        store = _sub_store(tmp_path, Subscription(topic="Topic X", budget=0.5))
        source_pack = {
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

        async def research_fn(query: str, budget: float) -> dict:
            return {
                "answer": "Topic X gained capability Y in June 2026. [S1]",
                "cost": 0.0,
                "fresh_context": {"source_count": 1, "mode": "fresh"},
                "source_pack": source_pack,
            }

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
        source_pack = {
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

        async def research_fn(query: str, budget: float) -> dict:
            return {
                "answer": "Topic X gained capability Y in June 2026. [S1]",
                "cost": 0.0,
                "fresh_context": {"source_count": 1, "mode": "fresh"},
                "source_pack": source_pack,
            }

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
        assert graph_commit["schema_version"] == "deepr-graph-commit-envelope-v7"
        assert graph_commit["contract"]["writes_graph"] is False
        assert graph_commit["input"]["claim_extraction_artifact"] == outcome.claim_extraction_artifact
        assert graph_commit["input"]["claim_verification_artifact"] == outcome.claim_verification_artifact
        assert graph_commit["summary"]["status"] == "ready_for_commit"
        assert len(graph_commit["operations"]) == 1

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
