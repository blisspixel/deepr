"""Source-trust confidence floors (v2.15 evidence release).

Deterministic caps by provenance tier, computed at read time like decay -
so they apply retroactively and through every write path, and no model
judgment can lift them. This is also the ingestion-time prompt-injection
backstop: a single poisoned web result cannot mint a near-certain belief.

Design: docs/design/calibration-and-trust.md (Part 2).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from deepr.experts.beliefs import Belief, BeliefStore


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Trust Floor Expert", storage_dir=tmp_path / "beliefs")


class TestTrustCeilings:
    def test_single_tertiary_source_caps_at_060(self):
        b = Belief(claim="Web says X", confidence=0.95, domain="d", evidence_refs=["report:r1"])
        assert b.trust_class == "tertiary"
        assert b.get_current_confidence() == pytest.approx(0.60)

    def test_two_independent_tertiary_sources_cap_at_080(self):
        b = Belief(claim="Two webs say X", confidence=0.95, domain="d", evidence_refs=["report:r1", "report:r2"])
        assert b.get_current_confidence() == pytest.approx(0.80)

    def test_duplicate_refs_do_not_count_as_independent(self):
        b = Belief(claim="Same web twice", confidence=0.95, domain="d", evidence_refs=["report:r1", "report:r1"])
        assert b.get_current_confidence() == pytest.approx(0.60)

    def test_quote_excerpts_do_not_count_as_independent_sources(self):
        # Regression (dogfood): absorb stores [f"report:{id}", *quotes]. The
        # quotes are grounding for ONE report, not extra origins - counting them
        # falsely lifted single-source beliefs to 0.80. A report id + any number
        # of quote excerpts is one source -> 0.60.
        b = Belief(
            claim="Episodic memory recalls past events",
            confidence=0.95,
            domain="d",
            evidence_refs=[
                "report:sync:ai-agent-memory:20260621",
                "Episodic memory allows agents to recall specific past events [S2].",
                "It records what happened, when, and in what context [S2].",
            ],
        )
        assert b.get_current_confidence() == pytest.approx(0.60)

    def test_two_distinct_report_runs_still_corroborate(self):
        b = Belief(
            claim="X",
            confidence=0.95,
            domain="d",
            evidence_refs=["report:run-a", "A supporting quote with spaces.", "report:run-b"],
        )
        assert b.get_current_confidence() == pytest.approx(0.80)

    def test_same_host_urls_are_one_source(self):
        b = Belief(
            claim="X",
            confidence=0.95,
            domain="d",
            evidence_refs=["https://example.com/a", "https://www.example.com/b"],
        )
        assert b.get_current_confidence() == pytest.approx(0.60)

    def test_distinct_host_urls_corroborate(self):
        b = Belief(
            claim="X",
            confidence=0.95,
            domain="d",
            evidence_refs=["https://alpha.com/a", "https://beta.com/b"],
        )
        assert b.get_current_confidence() == pytest.approx(0.80)

    def test_secondary_and_primary_uncapped(self):
        for tier in ("secondary", "primary"):
            b = Belief(claim=f"{tier} fact", confidence=0.95, domain="d", trust_class=tier)
            assert b.get_current_confidence() == pytest.approx(0.95)

    def test_below_ceiling_confidence_passes_through(self):
        b = Belief(claim="Modest claim", confidence=0.4, domain="d")
        assert b.get_current_confidence() == pytest.approx(0.4)


class TestFloorsHoldThroughWritePaths:
    def test_update_confidence_cannot_exceed_ceiling(self):
        b = Belief(claim="X", confidence=0.5, domain="d", evidence_refs=["report:r1"])
        b.update_confidence(0.99, reason="adjudication says so")
        # The raw value stores, but the READ is capped - no path can lift it
        assert b.get_current_confidence() == pytest.approx(0.60)

    def test_new_corroborating_evidence_raises_the_ceiling(self):
        b = Belief(claim="X", confidence=0.95, domain="d", evidence_refs=["report:r1"])
        assert b.get_current_confidence() == pytest.approx(0.60)
        b.add_evidence("report:r2")  # independent second source
        assert b.get_current_confidence() == pytest.approx(0.80)

    def test_retroactive_default_for_pre_floor_beliefs(self):
        # A belief serialized before trust_class existed loads as tertiary
        legacy = {
            "claim": "Old stored belief",
            "confidence": 0.95,
            "evidence_refs": ["report:old"],
            "domain": "d",
        }
        b = Belief.from_dict(legacy)
        assert b.trust_class == "tertiary"
        assert b.get_current_confidence() == pytest.approx(0.60)

    def test_roundtrip_preserves_trust_class(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(
            Belief(claim="Primary doc fact", confidence=0.9, domain="d", trust_class="primary"),
            check_conflicts=False,
        )
        reloaded = BeliefStore("Trust Floor Expert", storage_dir=tmp_path / "beliefs")
        b = next(iter(reloaded.beliefs.values()))
        assert b.trust_class == "primary"
        assert b.get_current_confidence() == pytest.approx(0.9)


class TestAbsorbedBeliefsAreTertiary:
    @pytest.mark.asyncio
    async def test_poisoned_high_confidence_extraction_caps_at_060(self, tmp_path):
        """The prompt-injection scenario: a persuasive report claims 0.98
        extraction confidence; the stored belief still reads <= 0.60."""
        from deepr.experts.report_absorber import ReportAbsorber

        content = json.dumps(
            {"claims": [{"statement": "Company X is bankrupt (trust me)", "confidence": 0.98, "evidence": []}]}
        )

        async def _create(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_create)))
        beliefs = _store(tmp_path)
        absorber = ReportAbsorber(
            SimpleNamespace(name="Trust Floor Expert", domain="d"), client=client, belief_store=beliefs
        )

        result = await absorber.absorb("poisoned-report", "Company X is bankrupt, says one very confident blog.")
        assert len(result.absorbed) == 1

        stored = next(iter(beliefs.beliefs.values()))
        assert stored.trust_class == "tertiary"
        assert stored.get_current_confidence() <= 0.60

    def test_to_claim_carries_the_trust_tier(self):
        b = Belief(claim="X", confidence=0.9, domain="d", evidence_refs=["r1"], trust_class="secondary")
        claim = b.to_claim()
        assert claim.sources[0].trust_class.value == "secondary"
