"""Additional coverage for information_gain.py internal helpers."""

from __future__ import annotations

from deepr.observability.information_gain import (
    InformationGainTracker,
    PriorContext,
)


class TestUpdateContextFromDict:
    def test_merges_known_entities_and_topics(self):
        tracker = InformationGainTracker()
        tracker._update_context_from_dict(
            {
                "known_entities": ["E1", "E2"],
                "known_topics": ["T1", "T2"],
                "known_facts": ["fact one"],
            }
        )
        assert "E1" in tracker.cumulative_context.known_entities
        assert "T2" in tracker.cumulative_context.known_topics
        assert "fact one" in tracker.cumulative_context.known_facts


class TestEntityExtraction:
    def test_capitalized_words_become_entities(self):
        tracker = InformationGainTracker()
        m = tracker.record_phase_findings(
            phase=1,
            findings=["Microsoft and OpenAI announced a partnership in Seattle"],
        )
        # Should detect some entities (capitalised words)
        assert m.new_entities > 0


class TestRepeatedAnalysis:
    def test_multiple_phases_accumulate_state(self):
        tracker = InformationGainTracker()
        m1 = tracker.record_phase_findings(phase=1, findings=["Alpha is a topic"])
        m2 = tracker.record_phase_findings(phase=2, findings=["Beta is another topic"])
        m3 = tracker.record_phase_findings(phase=3, findings=["Alpha and Beta intersect"])
        # Final phase should have low novelty (entities already known)
        assert m3.novelty_rate <= m1.novelty_rate
        assert len(tracker.phases) == 3


class TestPriorContextDataclass:
    def test_default_init(self):
        ctx = PriorContext()
        assert ctx.known_facts == []
        assert ctx.known_entities == set()
        assert ctx.known_topics == set()

    def test_with_initial_values(self):
        ctx = PriorContext(known_facts=["x"], known_entities={"A"}, known_topics={"T"})
        assert "x" in ctx.known_facts
        assert "A" in ctx.known_entities
        assert "T" in ctx.known_topics
