"""Tests for deepr.experts.report_absorber.ReportAbsorber.

Absorption promotes a report into beliefs, verification-gated. These tests use
a fake async client (no provider) and a real BeliefStore on a tmp dir, and
assert:
- extraction output is parsed and clamped,
- the confidence gate and the cost-$0 contradiction gate reject correctly,
- survivors are integrated and deduped (added vs merged),
- dry_run writes nothing,
- the result serializes, and bad model output raises cleanly.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.report_absorber import (
    AbsorptionResult,
    ReportAbsorber,
    ReportAbsorberError,
)


class _FakeClient:
    """Minimal async OpenAI-shaped client returning canned completion content."""

    def __init__(self, content: str):
        self._content = content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


def _claims_json(*claims: dict) -> str:
    return json.dumps({"claims": list(claims)})


def _expert():
    return SimpleNamespace(name="Test Expert", domain="ai")


def _absorber(content: str, tmp_path, *, beliefs: list[Belief] | None = None) -> ReportAbsorber:
    store = BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")
    for b in beliefs or []:
        store.add_belief(b, check_conflicts=False)
    return ReportAbsorber(_expert(), client=_FakeClient(content), belief_store=store)


@pytest.mark.asyncio
async def test_empty_report_raises(tmp_path):
    absorber = _absorber(_claims_json(), tmp_path)
    with pytest.raises(ReportAbsorberError):
        await absorber.absorb("rep1", "   ")


@pytest.mark.asyncio
async def test_bad_json_raises(tmp_path):
    absorber = _absorber("not json at all", tmp_path)
    with pytest.raises(ReportAbsorberError):
        await absorber.absorb("rep1", "some report text")


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ['{"claims": null}', '{"claims": "none"}', "{}", '{"claims": {}}'])
async def test_malformed_claims_field_yields_no_candidates(tmp_path, payload):
    # A model returning null / a non-list / a missing claims field must degrade
    # to zero candidates, not raise (regression: {"claims": null} crashed with
    # TypeError on the None slice).
    absorber = _absorber(payload, tmp_path)
    result = await absorber.absorb("rep1", "some report text")
    assert result.total_candidates == 0
    assert result.absorbed == []


@pytest.mark.asyncio
async def test_absorbs_strong_claim_with_provenance(tmp_path):
    content = _claims_json({"statement": "Model X leads on benchmark Y", "confidence": 0.9, "evidence": ["table 2"]})
    absorber = _absorber(content, tmp_path)
    result = await absorber.absorb("rep-123", "report body")

    assert result.total_candidates == 1
    assert len(result.absorbed) == 1
    assert result.absorbed[0].outcome == "added"
    assert result.added_count == 1
    # Provenance: the report id is recorded on the stored belief's evidence.
    stored = next(iter(absorber.belief_store.beliefs.values()))
    assert "report:rep-123" in stored.evidence_refs
    assert stored.source_type == "absorbed_report"


@pytest.mark.asyncio
async def test_low_confidence_rejected(tmp_path):
    content = _claims_json({"statement": "Weakly supported thing", "confidence": 0.3, "evidence": []})
    absorber = _absorber(content, tmp_path)
    result = await absorber.absorb("rep1", "body", min_confidence=0.6)

    assert result.absorbed == []
    assert len(result.rejected) == 1
    assert result.rejected[0].reason == "low_confidence"
    assert absorber.belief_store.beliefs == {}


@pytest.mark.asyncio
async def test_contradicting_claim_rejected(tmp_path):
    existing = Belief(claim="The system is memory safe by default", confidence=0.9, domain="ai")
    content = _claims_json({"statement": "The system is not memory safe by default", "confidence": 0.9, "evidence": []})
    absorber = _absorber(content, tmp_path, beliefs=[existing])
    result = await absorber.absorb("rep1", "body")

    assert result.absorbed == []
    assert len(result.rejected) == 1
    assert result.rejected[0].reason == "contradicts_existing"
    # The contradicting candidate must NOT have been written.
    assert len(absorber.belief_store.beliefs) == 1


@pytest.mark.asyncio
async def test_duplicate_claim_merges_not_duplicates(tmp_path):
    existing = Belief(claim="Model X leads on benchmark Y consistently", confidence=0.7, domain="ai")
    content = _claims_json(
        {"statement": "Model X leads on benchmark Y consistently", "confidence": 0.95, "evidence": []}
    )
    absorber = _absorber(content, tmp_path, beliefs=[existing])
    result = await absorber.absorb("rep1", "body")

    # Near-identical statement should merge into the existing belief, not add a
    # second one.
    assert len(absorber.belief_store.beliefs) == 1
    assert result.merged_count == 1
    assert result.added_count == 0


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(tmp_path):
    content = _claims_json({"statement": "A solid grounded claim", "confidence": 0.9, "evidence": []})
    absorber = _absorber(content, tmp_path)
    result = await absorber.absorb("rep1", "body", dry_run=True)

    assert result.dry_run is True
    assert len(result.absorbed) == 1
    assert result.absorbed[0].outcome == "would_add"
    assert absorber.belief_store.beliefs == {}  # nothing persisted


@pytest.mark.asyncio
async def test_confidence_clamped_and_blank_skipped(tmp_path):
    content = _claims_json(
        {"statement": "Over-confident claim", "confidence": 5.0, "evidence": []},
        {"statement": "", "confidence": 0.9, "evidence": []},  # blank -> skipped
    )
    absorber = _absorber(content, tmp_path)
    result = await absorber.absorb("rep1", "body")

    assert result.total_candidates == 1  # blank dropped during parse
    assert result.absorbed[0].confidence == 1.0  # clamped


@pytest.mark.asyncio
async def test_result_serializes(tmp_path):
    content = _claims_json({"statement": "Grounded claim", "confidence": 0.8, "evidence": ["sec 1"]})
    absorber = _absorber(content, tmp_path)
    result = await absorber.absorb("rep1", "body")

    assert isinstance(result, AbsorptionResult)
    d = result.to_dict()
    assert d["report_id"] == "rep1"
    assert d["added_count"] == 1
    assert d["absorbed"][0]["outcome"] == "added"
    assert "generated_at" in d


def test_get_client_without_key_raises(monkeypatch):
    # No client injected and no API key -> clean error, not a bare KeyError.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    absorber = ReportAbsorber(_expert(), belief_store=MagicMock())
    with pytest.raises(ReportAbsorberError):
        absorber._get_client()
