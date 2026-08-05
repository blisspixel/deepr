"""Structural expert quality scorecard tests."""

from __future__ import annotations

from deepr.experts.beliefs import Belief
from deepr.experts.quality_scorecard import build_quality_scorecard


def test_circular_intent_only_scores_poor() -> None:
    beliefs = [
        Belief(
            claim=f"Claim {i} about mesh gateways",
            confidence=0.9,
            evidence_refs=["report:file:nephmesh-intent.md"],
            trust_class="primary",
            domain="mesh",
        )
        for i in range(20)
    ]
    card = build_quality_scorecard(
        expert_name="Hybrid",
        domain="hybrid",
        beliefs=beliefs,
        open_gap_count=0,
        verified_learning_loops=0,
    )
    assert card.circularity_risk >= 0.9
    assert card.grade in {"C", "D", "F"}
    assert any("circularity" in b for b in card.blockers)


def test_secondary_multi_source_scores_better() -> None:
    beliefs = []
    for i in range(30):
        refs = [f"report:file:official-a.md", f"report:file:official-b.md"] if i < 10 else [f"report:file:official-a.md"]
        beliefs.append(
            Belief(
                claim=f"Official domain claim {i} about LoRa channel presets",
                confidence=0.95,
                evidence_refs=refs,
                trust_class="secondary",
                domain="mesh",
            )
        )
    card = build_quality_scorecard(
        expert_name="Meshtastic",
        domain="mesh",
        beliefs=beliefs,
        open_gap_count=3,
        verified_learning_loops=1,
    )
    assert card.secondary_or_better_share == 1.0
    assert card.multi_source_share >= 0.3
    assert card.circularity_risk == 0.0
    assert card.grade in {"A", "B"}
    assert not any("circularity" in b for b in card.blockers)
