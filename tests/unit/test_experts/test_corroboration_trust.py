"""Corroboration merge and absorb trust_class ceilings."""

from __future__ import annotations

from datetime import UTC, datetime

from deepr.experts.beliefs import Belief, BeliefStore, ConflictResolution
from deepr.experts.report_absorber import ReportAbsorber


def test_tertiary_single_source_caps_at_0_6() -> None:
    b = Belief(
        claim="HackRF covers 100 kHz to 6 GHz",
        confidence=0.98,
        evidence_refs=["report:file:hackrf.md"],
        trust_class="tertiary",
        domain="sdr",
    )
    assert b.get_current_confidence() == 0.6


def test_secondary_uncapped() -> None:
    b = Belief(
        claim="HackRF covers 100 kHz to 6 GHz",
        confidence=0.95,
        evidence_refs=["report:file:hackrf.md"],
        trust_class="secondary",
        domain="sdr",
    )
    assert b.get_current_confidence() == 0.95


def test_two_independent_tertiary_sources_cap_at_0_8() -> None:
    b = Belief(
        claim="Meshtastic uses LoRa",
        confidence=0.95,
        evidence_refs=["report:file:meshtastic.md", "report:file:other.md"],
        trust_class="tertiary",
        domain="mesh",
    )
    assert b._independent_source_count() == 2
    assert b.get_current_confidence() == 0.8


def test_corroboration_merges_evidence_and_raises_ceiling(tmp_path) -> None:
    store = BeliefStore("t", storage_dir=tmp_path / "beliefs")
    store.conflict_resolution = ConflictResolution.HIGHER_CONFIDENCE
    first = Belief(
        claim="Porch is kpt-as-a-service",
        confidence=0.9,
        evidence_refs=["report:file:nephio.md"],
        trust_class="tertiary",
        domain="nephio",
    )
    store.add_belief(first, dedup=True)
    second = Belief(
        claim="Porch is kpt as a service package orchestration",
        confidence=0.85,
        evidence_refs=["report:file:porch-docs.md"],
        trust_class="tertiary",
        domain="nephio",
    )
    # Force similar match: same claim text for stable dedup in test
    second.claim = first.claim
    stored, _change = store.add_belief(second, dedup=True)
    assert "report:file:nephio.md" in stored.evidence_refs
    assert "report:file:porch-docs.md" in stored.evidence_refs
    assert stored._independent_source_count() >= 2
    assert stored.get_current_confidence() == 0.8
    assert "conflicting:" not in " ".join(stored.evidence_refs)


def test_corroboration_upgrades_trust_class_to_secondary(tmp_path) -> None:
    store = BeliefStore("t", storage_dir=tmp_path / "beliefs")
    store.conflict_resolution = ConflictResolution.HIGHER_CONFIDENCE
    first = Belief(
        claim="YAML export is the machine config surface",
        confidence=0.7,
        evidence_refs=["report:file:intent.md"],
        trust_class="tertiary",
        domain="mesh",
    )
    store.add_belief(first, dedup=True)
    second = Belief(
        claim="YAML export is the machine config surface",
        confidence=0.9,
        evidence_refs=["report:file:meshtastic-cli.md"],
        trust_class="secondary",
        domain="mesh",
    )
    stored, _ = store.add_belief(second, dedup=True)
    assert stored.trust_class == "secondary"
    assert stored.get_current_confidence() == 0.9


def test_exact_claim_corroboration_preserves_strongest_complete_verification(tmp_path) -> None:
    store = BeliefStore("t", storage_dir=tmp_path / "beliefs")
    store.conflict_resolution = ConflictResolution.HIGHER_CONFIDENCE
    older = datetime(2026, 8, 19, tzinfo=UTC)
    newer = datetime(2026, 8, 20, tzinfo=UTC)
    store.add_belief(
        Belief(
            "Portable claims retain checker provenance",
            0.7,
            domain="interop",
            grounding_assurance="same_vendor_fresh_context",
            grounding_verified_at=older,
        )
    )
    candidate = Belief(
        "Portable claims retain checker provenance",
        0.8,
        domain="interop",
        grounding_assurance="cross_vendor",
        grounding_verified_at=newer,
    )

    stored, _ = store.add_belief(candidate)

    assert (stored.grounding_assurance, stored.grounding_verified_at) == ("cross_vendor", newer)


def test_higher_confidence_does_not_transfer_verification_between_different_claims(tmp_path) -> None:
    store = BeliefStore("t", storage_dir=tmp_path / "beliefs")
    store.add_belief(
        Belief(
            "The platform supports regulated production workloads in ten regional deployment zones under the current agreement",
            0.9,
            domain="capacity",
            trust_class="secondary",
        )
    )
    checked_at = datetime(2026, 8, 20, tzinfo=UTC)
    candidate = Belief(
        "The platform supports regulated staging workloads in ten regional deployment zones under the current agreement",
        0.7,
        domain="capacity",
        trust_class="secondary",
        grounding_assurance="cross_vendor",
        grounding_verified_at=checked_at,
    )

    stored, _ = store.add_belief(candidate)

    assert "production workloads" in stored.claim
    assert stored.grounding_assurance == "unverified"
    assert stored.grounding_verified_at is None


def test_merge_does_not_transfer_verification_between_different_claims(tmp_path) -> None:
    store = BeliefStore(
        "t",
        storage_dir=tmp_path / "beliefs",
        conflict_resolution=ConflictResolution.MERGE,
    )
    store.add_belief(
        Belief(
            "The platform supports regulated production workloads in ten regional deployment zones under the current agreement",
            0.8,
            domain="capacity",
        )
    )
    checked_at = datetime(2026, 8, 20, tzinfo=UTC)
    candidate = Belief(
        "The platform supports regulated staging workloads in ten regional deployment zones under the current agreement",
        0.7,
        domain="capacity",
        grounding_assurance="cross_vendor",
        grounding_verified_at=checked_at,
    )

    stored, _ = store.add_belief(candidate)

    assert "production workloads" in stored.claim
    assert stored.grounding_assurance == "unverified"
    assert stored.grounding_verified_at is None


def test_report_absorber_respects_trust_class_parameter() -> None:
    """Construction path stamps caller trust_class (not hard-coded tertiary)."""
    from unittest.mock import MagicMock

    profile = MagicMock()
    profile.domain = "test"
    profile.name = "T"
    absorber = ReportAbsorber(profile, model="x", client=None, estimated_cost=0.0)
    # Inspect default signature
    import inspect

    sig = inspect.signature(absorber.absorb)
    assert "trust_class" in sig.parameters
    assert sig.parameters["trust_class"].default == "tertiary"
