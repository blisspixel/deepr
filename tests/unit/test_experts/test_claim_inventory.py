"""Claim inventory reads: unknown must never render as empty."""

from types import SimpleNamespace

from deepr.experts.claim_inventory import (
    ClaimInventory,
    format_knowledge_status,
    read_claim_inventory,
)


def _expert(*, manifest=None, raises=False, cutoff=None):
    def get_manifest():
        if raises:
            raise RuntimeError("belief store unreadable")
        return manifest

    return SimpleNamespace(get_manifest=get_manifest, knowledge_cutoff_date=cutoff)


class TestReadClaimInventory:
    def test_reads_counts_from_manifest(self):
        expert = _expert(manifest=SimpleNamespace(claim_count=42, avg_confidence=0.73))
        inventory = read_claim_inventory(expert)
        assert inventory.claim_count == 42
        assert inventory.avg_confidence == 0.73
        assert inventory.manifest_available is True
        assert inventory.is_empty is False

    def test_zero_claims_with_readable_manifest_is_empty(self):
        expert = _expert(manifest=SimpleNamespace(claim_count=0, avg_confidence=None))
        assert read_claim_inventory(expert).is_empty is True

    def test_unreadable_manifest_is_unknown_not_empty(self):
        """The regression this module exists to prevent.

        Hosts skip consults on an empty expert, so reporting an unreadable
        manifest as empty tells an agent a populated expert has nothing to say.
        """
        inventory = read_claim_inventory(_expert(raises=True))
        assert inventory.claim_count == 0
        assert inventory.manifest_available is False
        assert inventory.is_empty is False

    def test_missing_get_manifest_is_unknown(self):
        assert read_claim_inventory(object()).manifest_available is False

    def test_non_numeric_confidence_degrades_to_none(self):
        expert = _expert(manifest=SimpleNamespace(claim_count=3, avg_confidence="n/a"))
        assert read_claim_inventory(expert).avg_confidence is None

    def test_absent_manifest_fields_default(self):
        inventory = read_claim_inventory(_expert(manifest=SimpleNamespace()))
        assert inventory == ClaimInventory(claim_count=0, avg_confidence=None, manifest_available=True)


class TestFormatKnowledgeStatus:
    def test_freshness_wins_when_cutoff_present(self):
        expert = _expert(cutoff="2026-01-01")
        expert.get_freshness_status = lambda: {"age_days": 12, "status": "fresh"}
        line = format_knowledge_status(expert, ClaimInventory(claim_count=5, manifest_available=True))
        assert "12 days old" in line
        assert "green" in line

    def test_unknown_freshness_status_renders_red(self):
        expert = _expert(cutoff="2026-01-01")
        expert.get_freshness_status = lambda: {"age_days": 400, "status": "stale"}
        assert "red" in format_knowledge_status(expert, ClaimInventory(manifest_available=True))

    def test_claims_stand_in_when_no_cutoff(self):
        """absorb --file populates claims without vector-store documents."""
        inventory = ClaimInventory(claim_count=37, manifest_available=True)
        line = format_knowledge_status(_expert(), inventory)
        assert "37 claim(s) in belief store" in line
        assert "incomplete" not in line

    def test_no_claims_and_no_cutoff_reads_incomplete(self):
        line = format_knowledge_status(_expert(), ClaimInventory(manifest_available=True))
        assert "incomplete" in line
