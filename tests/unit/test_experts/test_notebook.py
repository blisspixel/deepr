"""Notebook render: readable, honest about gaps, byte-stable."""


from deepr.experts.corpus_store import CorpusStore
from deepr.experts.notebook import NOTEBOOK_MARKER, build_notebook
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult
from deepr.experts.study_coverage import build_coverage_report


def _finding(lens="failure", *, title="Silent restore failure", grounded=True, payload=None):
    return StudyFinding(
        lens=lens,
        axis="interrogation",
        kind="fail_patterns",
        title=title,
        payload=payload
        or {
            "trigger": "restoring from an exported config",
            "symptom": "reports success while applying nothing",
            "correction": "read the values back and diff",
            "detection": "compare device state against the file",
        },
        anchors=["some quoted phrase"],
        grounded_anchor_count=1 if grounded else 0,
        ungrounded_anchor_count=0 if grounded else 1,
        corpus_shas=["abc123def456"] if grounded else [],
    )


def _result(findings=None, *, outcomes=None, limitations=None):
    result = StudyResult(expert_name="Test Expert")
    result.outcomes = outcomes or [
        LensOutcome(lens="failure", axis="interrogation", status="ok", findings=findings or [])
    ]
    result.limitations = limitations or []
    return result


class TestStructure:
    def test_marker_and_title_present(self):
        text = build_notebook(_result([_finding()]))
        assert text.startswith(NOTEBOOK_MARKER)
        assert "# Test Expert" in text

    def test_declares_itself_a_derived_view(self):
        """Canon is the corpus and the study record, not this file."""
        text = build_notebook(_result([_finding()]))
        assert "Derived view" in text
        assert "regenerated and safe to delete" in text

    def test_findings_render_with_their_structure(self):
        """A fail pattern is a conditional structure, not a sentence."""
        text = build_notebook(_result([_finding()]))
        assert "## What breaks" in text
        assert "Trigger: restoring from an exported config" in text
        assert "Correction: read the values back and diff" in text
        assert "Detection: compare device state against the file" in text

    def test_sections_follow_reading_order_not_lens_order(self):
        findings = [_finding("adversarial", title="abuse case"), _finding("mechanism", title="how it works")]
        result = _result(findings)
        result.outcomes = [
            LensOutcome(lens="adversarial", axis="perspective", status="ok", findings=[findings[0]]),
            LensOutcome(lens="mechanism", axis="interrogation", status="ok", findings=[findings[1]]),
        ]
        text = build_notebook(result)
        assert text.index("## How this works") < text.index("## How it gets abused")

    def test_purpose_and_domain_render_when_given(self):
        text = build_notebook(_result([_finding()]), domain="d", purpose="answer operators")
        assert "**Domain:** d" in text
        assert "**Purpose:** answer operators" in text


class TestHonesty:
    def test_unverified_finding_is_labeled_not_hidden(self):
        text = build_notebook(_result([_finding(grounded=False)]))
        assert "**Unverified**" in text
        assert "Check before relying on it" in text

    def test_grounded_finding_lists_its_sources(self):
        text = build_notebook(_result([_finding()]))
        assert "Sources: abc123def456" in text

    def test_lenses_that_ran_and_found_nothing_are_reported(self):
        """An empty lens is a result, not something to hide."""
        result = _result([])
        text = build_notebook(result)
        assert "## Read but empty" in text
        assert "What breaks" in text

    def test_failed_lenses_are_reported(self):
        result = _result(
            outcomes=[LensOutcome(lens="contention", axis="interrogation", status="parse_failed", detail="bad json")]
        )
        text = build_notebook(result)
        assert "## Lenses that failed" in text
        assert "contention: parse_failed - bad json" in text

    def test_limitations_are_rendered(self):
        text = build_notebook(_result([_finding()], limitations=["corpus has a single origin"]))
        assert "## Limitations" in text
        assert "corpus has a single origin" in text

    def test_confidence_number_is_not_the_headline(self):
        """Subjective confidence tracks internal consistency, not quality.

        A bare decimal invites exactly the over-reading it cannot support.
        """
        text = build_notebook(_result([_finding()]))
        assert "(0.6" not in text
        assert "confidence:" not in text.lower()


class TestCoverage:
    def test_coverage_section_reports_what_was_skipped(self, tmp_path):
        store = CorpusStore("Notebook Expert", storage_dir=tmp_path / "corpus")
        _a, _ = store.add("alpha body text", origin_key="url:a.org", publisher="a.org")
        store.add("beta body text", origin_key="url:b.org", publisher="b.org")

        result = _result([_finding()])
        result.coverage = build_coverage_report(
            studied=store.load_study_material(),
            findings=[],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        text = build_notebook(result, corpus_entries=store.active_entries())
        assert "## What this study read" in text
        assert "source_coverage=" in text
        assert "sole-source origin" in text

    def test_sources_table_lists_origins_and_trust(self, tmp_path):
        store = CorpusStore("Notebook Expert", storage_dir=tmp_path / "corpus")
        store.add("body", origin_key="url:docs.example", publisher="example", title="A Doc")
        text = build_notebook(_result([_finding()]), corpus_entries=store.active_entries())
        assert "## Sources" in text
        assert "url:docs.example" in text
        assert "secondary" in text

    def test_no_sources_says_so(self):
        text = build_notebook(_result([_finding()]))
        assert "_No sources retained._" in text


class TestDeterminism:
    def test_same_inputs_render_identical_bytes(self):
        """Unchanged inputs must regenerate without churn."""
        findings = [_finding()]
        first = build_notebook(_result(findings))
        second = build_notebook(_result(findings))
        assert first == second

    def test_empty_study_still_renders(self):
        text = build_notebook(StudyResult(expert_name="Empty"))
        assert "# Empty" in text
        assert "0 finding(s)" in text
