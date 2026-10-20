"""A lexical neighbor or unknown verdict cannot authorize a durable merge."""

import json
from types import SimpleNamespace

import pytest

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.report_absorber import ReportAbsorber
from deepr.experts.report_absorber_commit import StagedAbsorption, commit_staged_absorptions
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client


class Client:
    def __init__(self, claim, verdict):
        self.claim = claim
        self.verdict = verdict
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        _mark_zero_dollar_client(self, capacity_source="local")

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            text = json.dumps({"claims": [{"statement": self.claim, "confidence": 0.9, "evidence": []}]})
        elif isinstance(self.verdict, Exception):
            raise self.verdict
        else:
            text = self.verdict
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def belief(claim, confidence=0.6, source="old-source"):
    return Belief(claim=claim, confidence=confidence, domain="ai", trust_class="secondary", evidence_refs=[source])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "old_claim",
    [
        "The Lakeside production inference price is exactly 10 USD per million input tokens for all regional deployments",
        "The inference price is 10 USD per million input tokens",
    ],
    ids=["near_identical", "uncertain_band"],
)
@pytest.mark.parametrize("verdict", ["DIFFERENT", "UNKNOWN", "SAME but actually DIFFERENT", RuntimeError("offline")])
async def test_changed_price_is_not_merged_without_same(tmp_path, verdict, old_claim):
    new_claim = old_claim.replace("10 USD", "30 USD")
    store = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    old = belief(old_claim)
    store.add_belief(old, check_conflicts=False)
    client = Client(new_claim, verdict)
    absorber = ReportAbsorber(
        SimpleNamespace(name="Test", domain="ai"), client=client, belief_store=store, estimated_cost=0
    )

    result = await absorber.absorb("report-new", "synthetic report")

    assert client.calls == 2
    assert {b.claim for b in store.beliefs.values()} == {old_claim, new_claim}
    assert store.beliefs[old.id].evidence_refs == ["old-source"]
    assert store.beliefs[old.id].confidence == 0.6
    assert result.merges_blocked == 1
    assert result.absorbed[0].outcome == "added"


@pytest.mark.asyncio
async def test_disabled_verification_preserves_both_without_a_verdict_call(tmp_path):
    store = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    old = belief("The inference price is 10 USD per million input tokens")
    store.add_belief(old, check_conflicts=False)
    new_claim = old.claim.replace("10 USD", "30 USD")
    client = Client(new_claim, "SAME")
    absorber = ReportAbsorber(
        SimpleNamespace(name="Test", domain="ai"), client=client, belief_store=store, estimated_cost=0
    )

    result = await absorber.absorb("report-new", "synthetic report", verify_dedup=False)

    assert client.calls == 1
    assert {b.claim for b in store.beliefs.values()} == {old.claim, new_claim}
    assert result.merges_blocked == 1


@pytest.mark.asyncio
async def test_explicit_same_still_combines_provenance(tmp_path):
    store = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    old = belief("Python uses dynamic typing at runtime")
    store.add_belief(old, check_conflicts=False)
    client = Client("Python performs dynamic typing at runtime", "SAME")
    absorber = ReportAbsorber(
        SimpleNamespace(name="Test", domain="ai"), client=client, belief_store=store, estimated_cost=0
    )

    result = await absorber.absorb("report-new", "synthetic report")

    assert client.calls == 2
    assert len(store.beliefs) == 1
    assert "old-source" in store.beliefs[old.id].evidence_refs
    assert "report:report-new" in store.beliefs[old.id].evidence_refs
    assert result.absorbed[0].outcome == "merged"


@pytest.mark.parametrize("change", ["changed", "removed", "different_target", "candidate_changed"])
def test_commit_cannot_transfer_verdict_to_a_different_pair(tmp_path, change):
    store = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    old = belief("Python uses dynamic typing at runtime")
    store.add_belief(old, check_conflicts=False)
    new = belief("Python performs dynamic typing at runtime", 0.9, "new-source")
    staged = StagedAbsorption(belief=new, merge_target=(old.id, old.claim))
    writer = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    if change == "changed":
        writer.revise_belief(
            old.id, new_claim="Python uses static typing at runtime", new_confidence=0.7, reason="concurrent source"
        )
    elif change == "removed":
        writer.archive_belief(old.id, reason="withdrawn")
    elif change == "candidate_changed":
        new.claim = "Python performs static typing at runtime"
    else:
        # A different live neighbor can be selected by the store router.
        staged = StagedAbsorption(belief=new, merge_target=("not-this-target", old.claim))

    result = commit_staged_absorptions(store, [staged], report_id="new")

    assert result[0].outcome == "added"
    assert store.beliefs[new.id].claim == new.claim
    if change != "removed":
        assert "new-source" not in store.beliefs[old.id].evidence_refs


def test_staged_target_resolves_to_earlier_inserted_belief(tmp_path):
    store = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    first = belief("Python uses dynamic typing at runtime")
    second = belief("Python performs dynamic typing at runtime", 0.9, "new-source")

    result = commit_staged_absorptions(
        store,
        [StagedAbsorption(first), StagedAbsorption(second, merge_target=(first.id, first.claim))],
        report_id="new",
    )

    assert [item.outcome for item in result] == ["added", "merged"]
    assert len(store.beliefs) == 1


def test_unverified_staged_claim_never_implicitly_merges(tmp_path):
    store = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    old = belief("The inference price is 10 USD per million input tokens")
    store.add_belief(old, check_conflicts=False)
    new = belief(old.claim.replace("10 USD", "30 USD"), 0.9, "new-source")

    result = commit_staged_absorptions(store, [StagedAbsorption(new)], report_id="new")

    assert result[0].outcome == "added"
    assert len(store.beliefs) == 2


def test_two_live_neighbors_cannot_share_one_verdict(tmp_path):
    store = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    first = belief("The inference price is 10 USD per million input tokens")
    other = belief(first.claim.replace("10 USD", "20 USD"))
    store.add_belief(first, check_conflicts=False, dedup=False)
    store.add_belief(other, check_conflicts=False, dedup=False)
    new = belief(first.claim.replace("10 USD", "30 USD"), 0.9, "new-source")
    actual = store.find_similar_with_score(new)[0]
    verified = other if actual.id == first.id else first

    result = commit_staged_absorptions(
        store, [StagedAbsorption(new, merge_target=(verified.id, verified.claim))], report_id="new"
    )

    assert result[0].outcome == "added"
    assert len(store.beliefs) == 3
    assert store.beliefs[actual.id].evidence_refs == ["old-source"]


def test_staged_target_id_can_resolve_through_an_earlier_merge(tmp_path):
    store = BeliefStore("Test", storage_dir=tmp_path / "beliefs")
    old = belief("Python uses dynamic typing at runtime", 0.9)
    store.add_belief(old, check_conflicts=False)
    first = belief(old.claim, 0.6, "first-source")
    second = belief("Python performs dynamic typing at runtime", 0.7, "second-source")

    result = commit_staged_absorptions(
        store,
        [
            StagedAbsorption(first, merge_target=(old.id, old.claim)),
            StagedAbsorption(second, merge_target=(first.id, first.claim)),
        ],
        report_id="new",
    )

    assert [item.outcome for item in result] == ["merged", "merged"]
    assert len(store.beliefs) == 1
    assert set(store.beliefs[old.id].evidence_refs) == {"old-source", "first-source", "second-source"}
