"""Tests for ExpertPolicy, ManifestDelta, and manifest comparison."""

from datetime import datetime, timezone

from deepr.core.contracts import (
    Claim,
    ExpertManifest,
    ExpertPolicy,
    Gap,
    ManifestDelta,
    Source,
    TrustClass,
)


def _make_claim(statement: str, confidence: float = 0.8) -> Claim:
    import hashlib

    cid = hashlib.sha256(f"{statement}:test".encode()).hexdigest()[:12]
    sid = hashlib.sha256(f"source:{statement}".encode()).hexdigest()[:12]
    return Claim(
        id=cid,
        statement=statement,
        domain="test",
        confidence=confidence,
        sources=[Source(id=sid, title="test-source", trust_class=TrustClass.SECONDARY, extraction_method="manual")],
    )


def _make_gap(topic: str, filled: bool = False) -> Gap:
    import hashlib

    gid = hashlib.sha256(topic.encode()).hexdigest()[:12]
    return Gap(id=gid, topic=topic, questions=[f"What about {topic}?"], priority=3, filled=filled)


def _make_manifest(
    claims: list[Claim] | None = None,
    gaps: list[Gap] | None = None,
    policies: dict | None = None,
    time: datetime | None = None,
) -> ExpertManifest:
    return ExpertManifest(
        expert_name="test-expert",
        domain="testing",
        claims=claims or [],
        gaps=gaps or [],
        policies=policies or {},
        generated_at=time or datetime.now(timezone.utc),
    )


class TestExpertPolicy:
    def test_defaults(self):
        p = ExpertPolicy()
        assert p.refresh_frequency_days == 7
        assert p.budget_cap_monthly == 50.0
        assert p.high_trust_only is False
        assert p.gap_fill_strategy == "ev_cost_ratio"

    def test_to_dict(self):
        p = ExpertPolicy(high_trust_only=True, budget_cap_monthly=100.0)
        d = p.to_dict()
        assert d["high_trust_only"] is True
        assert d["budget_cap_monthly"] == 100.0

    def test_from_dict(self):
        p = ExpertPolicy.from_dict({"high_trust_only": True, "domain_velocity": "fast"})
        assert p.high_trust_only is True
        assert p.domain_velocity == "fast"

    def test_roundtrip(self):
        original = ExpertPolicy(refresh_frequency_days=14, gap_fill_strategy="priority")
        restored = ExpertPolicy.from_dict(original.to_dict())
        assert restored.refresh_frequency_days == 14
        assert restored.gap_fill_strategy == "priority"


class TestManifestDelta:
    def test_no_changes(self):
        c1 = _make_claim("The sky is blue")
        before = _make_manifest(claims=[c1])
        after = _make_manifest(claims=[c1])

        delta = ManifestDelta.compute(before, after)
        assert not delta.has_changes
        assert delta.summary == "no changes"

    def test_claim_added(self):
        c1 = _make_claim("Claim A")
        c2 = _make_claim("Claim B")
        before = _make_manifest(claims=[c1])
        after = _make_manifest(claims=[c1, c2])

        delta = ManifestDelta.compute(before, after)
        assert len(delta.claims_added) == 1
        assert delta.claims_added[0].statement == "Claim B"
        assert "+1 claims" in delta.summary

    def test_claim_removed(self):
        c1 = _make_claim("Claim A")
        c2 = _make_claim("Claim B")
        before = _make_manifest(claims=[c1, c2])
        after = _make_manifest(claims=[c1])

        delta = ManifestDelta.compute(before, after)
        assert len(delta.claims_removed) == 1
        assert delta.claims_removed[0].statement == "Claim B"

    def test_confidence_changed(self):
        c_before = _make_claim("AI is useful", confidence=0.7)
        c_after = _make_claim("AI is useful", confidence=0.95)
        before = _make_manifest(claims=[c_before])
        after = _make_manifest(claims=[c_after])

        delta = ManifestDelta.compute(before, after)
        assert len(delta.claims_confidence_changed) == 1
        change = delta.claims_confidence_changed[0]
        assert change["old_confidence"] == 0.7
        assert change["new_confidence"] == 0.95
        assert change["delta"] == 0.25

    def test_confidence_unchanged_within_threshold(self):
        c_before = _make_claim("Fact", confidence=0.80)
        c_after = _make_claim("Fact", confidence=0.805)
        before = _make_manifest(claims=[c_before])
        after = _make_manifest(claims=[c_after])

        delta = ManifestDelta.compute(before, after)
        assert len(delta.claims_confidence_changed) == 0

    def test_gap_new(self):
        g1 = _make_gap("Topic A")
        before = _make_manifest(gaps=[])
        after = _make_manifest(gaps=[g1])

        delta = ManifestDelta.compute(before, after)
        assert len(delta.gaps_new) == 1

    def test_gap_resolved_by_filling(self):
        g_before = _make_gap("Topic A", filled=False)
        g_after = _make_gap("Topic A", filled=True)
        before = _make_manifest(gaps=[g_before])
        after = _make_manifest(gaps=[g_after])

        delta = ManifestDelta.compute(before, after)
        assert len(delta.gaps_resolved) == 1

    def test_gap_resolved_by_removal(self):
        g1 = _make_gap("Topic A", filled=False)
        before = _make_manifest(gaps=[g1])
        after = _make_manifest(gaps=[])

        delta = ManifestDelta.compute(before, after)
        assert len(delta.gaps_resolved) == 1

    def test_policy_changes(self):
        before = _make_manifest(policies={"refresh_days": 7, "velocity": "slow"})
        after = _make_manifest(policies={"refresh_days": 14, "velocity": "slow"})

        delta = ManifestDelta.compute(before, after)
        assert "refresh_days" in delta.policy_changes
        assert delta.policy_changes["refresh_days"]["old"] == 7
        assert delta.policy_changes["refresh_days"]["new"] == 14

    def test_to_dict(self):
        c1 = _make_claim("New claim")
        before = _make_manifest()
        after = _make_manifest(claims=[c1])

        delta = ManifestDelta.compute(before, after)
        d = delta.to_dict()
        assert d["expert_name"] == "test-expert"
        assert d["has_changes"] is True
        assert len(d["claims_added"]) == 1
        assert "summary" in d

    def test_complex_delta(self):
        """Multiple changes at once."""
        c1 = _make_claim("Old claim")
        c2 = _make_claim("Shared claim", confidence=0.5)
        g1 = _make_gap("Old gap", filled=False)

        c2_updated = _make_claim("Shared claim", confidence=0.9)
        c3 = _make_claim("New claim")
        g1_filled = _make_gap("Old gap", filled=True)
        g2 = _make_gap("New gap")

        before = _make_manifest(claims=[c1, c2], gaps=[g1])
        after = _make_manifest(claims=[c2_updated, c3], gaps=[g1_filled, g2])

        delta = ManifestDelta.compute(before, after)
        assert len(delta.claims_added) == 1  # c3
        assert len(delta.claims_removed) == 1  # c1
        assert len(delta.claims_confidence_changed) == 1  # c2: 0.5 -> 0.9
        assert len(delta.gaps_new) == 1  # g2
        assert len(delta.gaps_resolved) == 1  # g1
        assert delta.has_changes
