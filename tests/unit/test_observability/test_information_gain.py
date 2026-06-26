"""Tests for InformationGainTracker - pure-logic coverage."""

from __future__ import annotations

import pytest

from deepr.observability.information_gain import (
    InformationGainMetrics,
    InformationGainTracker,
    PriorContext,
)


class TestPriorContext:
    def test_to_dict_summarises_state(self):
        ctx = PriorContext(
            known_facts=["a", "b"],
            known_entities={"E1", "E2"},
            known_topics={"T1"},
            content_hashes={"h1", "h2", "h3"},
        )
        data = ctx.to_dict()
        assert data["known_facts_count"] == 2
        assert set(data["known_entities"]) == {"E1", "E2"}
        assert set(data["known_topics"]) == {"T1"}
        assert data["content_hashes_count"] == 3


class TestMetricsSerialization:
    def test_to_dict_round_trip(self):
        m = InformationGainMetrics(
            phase=1,
            gain_score=0.7,
            novelty_rate=0.8,
            redundancy_rate=0.2,
            coverage_expansion=0.5,
            topic_diversity=0.6,
            new_entities=3,
            new_topics=2,
            total_findings=5,
            unique_findings=4,
        )
        d = m.to_dict()
        assert d["phase"] == 1
        assert d["gain_score"] == pytest.approx(0.7)
        assert d["unique_findings"] == 4
        assert "timestamp" in d


class TestRecordPhaseFindings:
    def test_empty_findings_returns_zero_metrics(self):
        tracker = InformationGainTracker()
        m = tracker.record_phase_findings(phase=1, findings=[])
        assert m.gain_score == 0.0
        assert m.total_findings == 0
        assert m.redundancy_rate == 1.0

    def test_first_phase_high_novelty(self):
        tracker = InformationGainTracker()
        findings = [
            "GPT-5 is OpenAI's latest model with strong reasoning",
            "Quantum entanglement enables non-classical correlations",
            "RISC-V is an open instruction set architecture",
        ]
        m = tracker.record_phase_findings(phase=1, findings=findings)
        # All findings are novel in phase 1
        assert m.total_findings == 3
        assert m.novelty_rate >= 0.5
        assert m.gain_score > 0.0

    def test_repeated_findings_reduce_novelty(self):
        tracker = InformationGainTracker()
        tracker.record_phase_findings(phase=1, findings=["The sky is blue"])
        # Same finding again in phase 2 - should not be novel
        m = tracker.record_phase_findings(phase=2, findings=["The sky is blue"])
        assert m.unique_findings == 0
        assert m.novelty_rate < 0.5

    def test_accumulated_context_grows(self):
        tracker = InformationGainTracker()
        tracker.record_phase_findings(phase=1, findings=["Apple is a fruit"])
        tracker.record_phase_findings(phase=2, findings=["Microsoft makes Windows"])
        # Both phases recorded
        assert len(tracker.phases) == 2

    def test_phase_findings_are_stored(self):
        tracker = InformationGainTracker()
        tracker.record_phase_findings(phase=1, findings=["A", "B"])
        assert tracker._phase_findings[1] == ["A", "B"]
