"""Coverage tests for ``deepr/services/context_chainer.py``.

Targets the previously-uncovered branches: build_structured_context,
merge_contexts, _format_phase_context, plus the finding-classification,
confidence-estimation, importance, and source-extraction helpers.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.observability.temporal_tracker import FindingType, TemporalKnowledgeTracker
from deepr.services.context_chainer import (
    ContextChainer,
    ExtractedFinding,
    StructuredPhaseOutput,
)


@pytest.fixture
def chainer():
    return ContextChainer(max_tokens=400, importance_threshold=0.3)


class TestStructurePhaseOutput:
    def test_extracts_findings_entities_questions(self, chainer):
        text = (
            "Research indicates that quantum entanglement violates Bell's theorem. "
            "Experiments at CERN have confirmed this result with high precision.\n\n"
            "However, in contrast, classical interpretations remain debated.\n\n"
            "Does this imply faster-than-light communication?\n\n"
            "The Higgs boson was first discovered in 2012 at the LHC."
        )
        out = chainer.structure_phase_output(text, phase=1)
        assert out.phase == 1
        # At least one entity captured (CERN, LHC, etc.)
        assert any(e in {"CERN", "LHC", "Higgs", "Bell", "Research"} for e in out.entities)
        # Question extracted
        assert any("?" in q for q in out.open_questions)
        # Contradiction caught (we used "in contrast")
        assert out.contradictions

    def test_records_findings_in_tracker(self, chainer):
        tracker = TemporalKnowledgeTracker(job_id="t1")
        text = "Data shows that hydrogen fuel cells achieve 60% efficiency. " * 5
        chainer.structure_phase_output(text, phase=2, tracker=tracker)
        # Tracker should have at least one recorded finding.
        assert len(tracker.findings) >= 1

    def test_no_findings_returns_default_confidence(self, chainer):
        out = chainer.structure_phase_output("short.", phase=1)
        # No paragraphs >= 30 chars => no findings, conf_avg falls back to 0.5
        assert out.confidence_avg == 0.5
        assert out.key_findings == []


class TestBuildStructuredContext:
    def test_includes_summary_findings_questions_contradictions(self, chainer):
        finding = ExtractedFinding(
            text="The system uses Rust for parts of its critical path.",
            confidence=0.8,
            finding_type=FindingType.FACT,
            importance=0.7,
        )
        prior = StructuredPhaseOutput(
            phase=1,
            key_findings=[finding],
            summary="Phase 1 covered architecture.",
            entities=["Rust", "Tokio"],
            open_questions=["What does Tokio offer?"],
            contradictions=["Some say Rust is too restrictive."],
            confidence_avg=0.8,
        )
        ctx = chainer.build_structured_context([prior], current_phase=2, max_tokens=4000)
        assert "Phase 1" in ctx
        assert "Open Questions" in ctx
        assert "Contradictions to Resolve" in ctx
        assert "Phase 2" in ctx

    def test_no_questions_no_contradictions_section(self, chainer):
        prior = StructuredPhaseOutput(
            phase=1,
            key_findings=[],
            summary="empty",
            entities=[],
            open_questions=[],
            contradictions=[],
            confidence_avg=0.5,
        )
        ctx = chainer.build_structured_context([prior], current_phase=2)
        assert "Open Questions" not in ctx
        assert "Contradictions" not in ctx

    def test_focus_query_reorders_findings(self, chainer):
        f1 = ExtractedFinding(
            text="alpha experiment results were promising",
            confidence=0.7,
            finding_type=FindingType.OBSERVATION,
            importance=0.8,
        )
        f2 = ExtractedFinding(
            text="beta findings on graviton emission",
            confidence=0.7,
            finding_type=FindingType.OBSERVATION,
            importance=0.6,
        )
        prior = StructuredPhaseOutput(
            phase=1,
            key_findings=[f1, f2],
            summary="s",
            entities=[],
            open_questions=[],
            contradictions=[],
            confidence_avg=0.7,
        )
        ctx = chainer.build_structured_context(
            [prior], current_phase=2, focus_query="graviton emission", max_tokens=4000
        )
        # The graviton text should appear (focus_query keeps it in the budget).
        assert "graviton" in ctx


class TestMergeContexts:
    def test_dedupes_identical_bullets(self, chainer):
        c1 = "## A\n- alpha\n- beta\n"
        c2 = "## B\n- alpha\n- gamma\n"
        merged = chainer.merge_contexts([c1, c2])
        # alpha should appear once
        assert merged.count("- alpha") == 1
        assert "- gamma" in merged
        assert "Merged Research Context" in merged

    def test_truncates_when_over_budget(self, chainer):
        # Build something that overflows the supplied max_tokens budget.
        bullets = "\n".join(f"- point {i}" for i in range(100))
        merged = chainer.merge_contexts([bullets], max_tokens=10)
        # Result has at most max_tokens words
        assert len(merged.split()) <= 10


class TestClassifyFinding:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Data shows the bond energy is high.", FindingType.FACT),
            ("Observed that the gas expanded.", FindingType.OBSERVATION),
            ("This suggests a phase transition.", FindingType.INFERENCE),
            ("Hypothesis: gravity is curvature.", FindingType.HYPOTHESIS),
            ("However, this contradicts the Standard Model.", FindingType.CONTRADICTION),
            ("New data confirms the previous claim.", FindingType.CONFIRMATION),
            ("Just random unrelated text without keywords.", FindingType.OBSERVATION),
        ],
    )
    def test_classify(self, chainer, text, expected):
        assert chainer._classify_finding(text) == expected


class TestEstimateConfidence:
    @pytest.mark.parametrize(
        "text, lo, hi",
        [
            ("This is definitely proven and confirmed.", 0.85, 0.95),
            ("This might possibly happen, unclear.", 0.25, 0.35),
            ("It probably suggests a pattern.", 0.55, 0.65),
            ("Some neutral statement here.", 0.45, 0.55),
        ],
    )
    def test_confidence_buckets(self, chainer, text, lo, hi):
        c = chainer._estimate_confidence(text)
        assert lo <= c <= hi


class TestImportance:
    def test_digit_boost(self, chainer):
        s = chainer._calculate_importance("There were 5 events recorded.")
        assert s > 0.5

    def test_citation_boost(self, chainer):
        s = chainer._calculate_importance("According to a 2024 study, x is true.")
        assert s > 0.5

    def test_novelty_boost(self, chainer):
        s = chainer._calculate_importance("First discovered in 2023, this is novel.")
        assert s > 0.5

    def test_hedge_penalty(self, chainer):
        s_plain = chainer._calculate_importance("This is true.")
        s_hedged = chainer._calculate_importance("This might possibly be true perhaps.")
        assert s_hedged <= s_plain

    def test_score_bounded(self, chainer):
        # Many boosters but still capped at 1.0
        s = chainer._calculate_importance("First novel discovery: according to 2024 study, 50% of new effects.")
        assert 0.0 <= s <= 1.0


class TestExtractSource:
    def test_url_extraction(self, chainer):
        src = chainer._extract_source("See more at https://example.com/x for details")
        assert src == "https://example.com/x"

    def test_citation_extraction(self, chainer):
        src = chainer._extract_source("This was reported (Smith 2024) in the journal.")
        assert src is not None
        assert "2024" in src

    def test_none_when_no_source(self, chainer):
        assert chainer._extract_source("No citation here.") is None


class TestFormatPhaseContext:
    def test_truncates_findings_when_over_budget(self, chainer):
        # Build many big findings; budget should cut them.
        findings = [
            ExtractedFinding(
                text="A " * 80,  # 160 chars truncated to 150 but ~80 words
                confidence=0.5,
                finding_type=FindingType.OBSERVATION,
                importance=0.5,
            )
            for _ in range(20)
        ]
        phase = StructuredPhaseOutput(
            phase=1,
            key_findings=findings,
            summary="s",
            entities=["E1"],
            open_questions=[],
            contradictions=[],
            confidence_avg=0.5,
        )
        section, tokens = chainer._format_phase_context(phase, budget=200, focus_query=None)
        # We should not have included all 20 since budget is small.
        assert section.count("[observation]") < 20

    def test_no_findings_still_renders_header(self, chainer):
        phase = StructuredPhaseOutput(
            phase=1,
            key_findings=[],
            summary="s",
            entities=[],
            open_questions=[],
            contradictions=[],
            confidence_avg=0.5,
        )
        section, _ = chainer._format_phase_context(phase, budget=1000, focus_query=None)
        assert "### Phase 1" in section
