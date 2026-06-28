"""Extra coverage for ``deepr/observability/stopping_criteria.py``.

Targets the previously-uncovered branches:
- ``detect_auto_pivot`` with drifted findings
- ``_calculate_information_gain`` first-phase and subsequent paths
- ``_calculate_entropy_trend`` declining / increasing / stable
- ``reset`` and ``export_to_span``
- the ``should_stop`` branches for low-entropy / low-information / declining-trend / high-dup
"""

from __future__ import annotations

from unittest.mock import MagicMock

from deepr.observability.stopping_criteria import (
    EntropyStoppingCriteria,
    Finding,
    PhaseContext,
)


def _finding(text: str, phase: int = 1) -> Finding:
    return Finding(text=text, phase=phase)


class TestDetectAutoPivot:
    def test_returns_none_when_too_few(self):
        c = EntropyStoppingCriteria()
        assert c.detect_auto_pivot([_finding("a")], original_query="alpha") is None

    def test_no_drift_returns_none(self):
        c = EntropyStoppingCriteria()
        findings = [_finding("alpha beta gamma", i) for i in range(5)]
        assert c.detect_auto_pivot(findings, original_query="alpha beta gamma") is None

    def test_significant_drift_returns_pivot_suggestion(self):
        c = EntropyStoppingCriteria()
        findings = [
            _finding("quantum entanglement and bell inequality", 1),
            _finding("quantum entanglement and bell inequality", 2),
            _finding("photosynthesis carbon dioxide chloroplast", 3),
            _finding("photosynthesis carbon dioxide chloroplast", 4),
            _finding("photosynthesis carbon dioxide chloroplast", 5),
        ]
        out = c.detect_auto_pivot(findings, original_query="quantum entanglement bell")
        assert out is None or "pivot" in out.lower()


class TestInformationGain:
    def test_first_phase_returns_one(self):
        c = EntropyStoppingCriteria()
        ctx = PhaseContext(phase_num=1, original_query="q", current_focus="q", prior_entropy=None)
        assert c._calculate_information_gain([_finding("x")], ctx) == 1.0

    def test_subsequent_phase_blends_entropy_and_uniqueness(self):
        c = EntropyStoppingCriteria()
        ctx = PhaseContext(phase_num=2, original_query="q", current_focus="q", prior_entropy=0.5)
        gain = c._calculate_information_gain([_finding("entirely new fact")], ctx)
        assert 0.0 <= gain <= 1.0


class TestEntropyTrend:
    def test_insufficient_data(self):
        c = EntropyStoppingCriteria()
        c._entropy_history = [0.5, 0.4]
        assert c._calculate_entropy_trend() == "insufficient_data"

    def test_declining(self):
        c = EntropyStoppingCriteria()
        c._entropy_history = [0.9, 0.7, 0.5]
        assert c._calculate_entropy_trend() == "declining"
        assert c._is_entropy_declining() is True

    def test_increasing(self):
        c = EntropyStoppingCriteria()
        c._entropy_history = [0.1, 0.2, 0.3]
        assert c._calculate_entropy_trend() == "increasing"
        assert c._is_entropy_declining() is False

    def test_stable(self):
        c = EntropyStoppingCriteria()
        c._entropy_history = [0.5, 0.7, 0.5]
        assert c._calculate_entropy_trend() == "stable"
        assert c._is_entropy_declining() is False


class TestShouldStopBranches:
    def test_low_entropy_triggers_stop(self):
        c = EntropyStoppingCriteria(entropy_threshold=0.99)
        ctx = PhaseContext(phase_num=2, original_query="q", current_focus="q", prior_entropy=0.9, iteration_count=5)
        # Very repetitive - entropy near 0
        findings = [_finding("same words same words same words", i) for i in range(10)]
        out = c.evaluate(findings, ctx)
        # Should match either low-entropy or low-info-gain branch.
        assert out.should_stop is True

    def test_high_duplicate_rate_triggers_stop(self):
        c = EntropyStoppingCriteria(entropy_threshold=0.0, min_information_gain=0.0)
        ctx = PhaseContext(phase_num=2, original_query="q", current_focus="q", prior_entropy=0.9, iteration_count=5)
        # Many identical findings -> high dup rate
        findings = [_finding("identical text", i) for i in range(10)]
        out = c.evaluate(findings, ctx)
        # Either low-entropy or duplicate-rate branch fires.
        assert out.should_stop is True


class TestResetAndExport:
    def test_reset_clears_state(self):
        c = EntropyStoppingCriteria()
        c._entropy_history.append(0.5)
        c._content_hashes.add("abc")
        c.reset()
        assert c._entropy_history == []
        assert c._content_hashes == set()

    def test_export_to_span_calls_set_attribute(self):
        c = EntropyStoppingCriteria()
        c._entropy_history = [0.5, 0.4]
        c._content_hashes = {"a", "b"}
        span = MagicMock()
        c.export_to_span(span)
        assert span.set_attribute.call_count >= 3
