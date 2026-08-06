"""Coverage reporting: what a study pass read, and what it silently skipped."""

import pytest

from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study_contracts import StudyFinding
from deepr.experts.study_coverage import build_coverage_report


def _finding(shas, *, grounded=True):
    return StudyFinding(
        lens="failure",
        axis="interrogation",
        kind="fail_patterns",
        title="t",
        grounded_anchor_count=1 if grounded else 0,
        ungrounded_anchor_count=0 if grounded else 1,
        corpus_shas=list(shas),
    )


@pytest.fixture
def store(tmp_path):
    return CorpusStore("Coverage Expert", storage_dir=tmp_path / "corpus")


class TestCoverage:
    def test_cited_sources_counted(self, store):
        a, _ = store.add("alpha body", origin_key="url:a.org")
        store.add("beta body", origin_key="url:b.org")
        studied = store.load_study_material()

        report = build_coverage_report(
            studied=studied,
            findings=[_finding([a.sha256])],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert report.studied_sources == 2
        assert report.cited_sources == 1
        assert report.source_coverage == 0.5

    def test_untouched_studied_source_is_reported(self, store):
        a, _ = store.add("alpha body", origin_key="url:a.org")
        b, _ = store.add("beta body", origin_key="url:b.org")
        report = build_coverage_report(
            studied=store.load_study_material(),
            findings=[_finding([a.sha256])],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert b.sha256 in report.untouched_sources
        assert any("no anchored finding" in c for c in report.concerns())

    def test_unstudied_source_is_reported_separately(self, store):
        """Never read is a different failure from read and not cited."""
        store.add("x" * 400, origin_key="url:a.org")
        store.add("y" * 400, origin_key="url:b.org")
        studied = store.load_study_material(max_chars=500)
        assert len(studied) == 1

        report = build_coverage_report(
            studied=studied,
            findings=[],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert len(report.unstudied_sources) == 1
        assert any("not studied at all" in c for c in report.concerns())

    def test_ungrounded_finding_does_not_count_as_citing(self, store):
        """An unverified quote is not evidence the source was consulted."""
        a, _ = store.add("alpha body", origin_key="url:a.org")
        report = build_coverage_report(
            studied=store.load_study_material(),
            findings=[_finding([a.sha256], grounded=False)],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert report.cited_sources == 0


class TestSingletonOrigins:
    def test_sole_source_origins_are_identified(self, store):
        """Hidden profiles live in evidence held by exactly one source."""
        store.add("page one", origin_key="url:big.org")
        store.add("page two", origin_key="url:big.org")
        lone, _ = store.add("the lone dissenting source", origin_key="url:small.org")

        report = build_coverage_report(
            studied=store.load_study_material(),
            findings=[],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert report.singleton_origin_sources == [lone.sha256]

    def test_uncited_singleton_is_flagged_prominently(self, store):
        big1, _ = store.add("page one", origin_key="url:big.org")
        store.add("page two", origin_key="url:big.org")
        lone, _ = store.add("the lone dissenting source", origin_key="url:small.org")

        report = build_coverage_report(
            studied=store.load_study_material(),
            findings=[_finding([big1.sha256])],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert lone.sha256 in report.uncited_singleton_origins
        assert any("sole-source origin" in c for c in report.concerns())

    def test_cited_singleton_is_not_flagged(self, store):
        store.add("page one", origin_key="url:big.org")
        store.add("page two", origin_key="url:big.org")
        lone, _ = store.add("the lone dissenting source", origin_key="url:small.org")

        report = build_coverage_report(
            studied=store.load_study_material(),
            findings=[_finding([lone.sha256])],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert report.uncited_singleton_origins == []


class TestOriginCoverage:
    def test_one_publisher_many_pages_does_not_look_like_broad_coverage(self, store):
        """Source coverage can look healthy while most origins go unread."""
        cited = []
        for i in range(8):
            entry, _ = store.add(f"big page {i}", origin_key="url:big.org")
            cited.append(entry.sha256)
        for i in range(4):
            store.add(f"other {i}", origin_key=f"url:other{i}.org")

        report = build_coverage_report(
            studied=store.load_study_material(),
            findings=[_finding(cited)],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert report.cited_sources == 8
        assert report.corpus_origins == 5
        assert report.cited_origins == 1
        assert report.origin_coverage == 0.2
        assert any("origin_coverage" in c for c in report.concerns())

    def test_full_coverage_raises_no_concerns(self, store):
        a, _ = store.add("alpha body", origin_key="url:a.org")
        b, _ = store.add("beta body", origin_key="url:b.org")
        report = build_coverage_report(
            studied=store.load_study_material(),
            findings=[_finding([a.sha256, b.sha256])],
            stats=store.stats(),
            all_active=store.active_entries(),
        )
        assert report.concerns() == []
        assert report.source_coverage == 1.0
        assert report.origin_coverage == 1.0

    def test_empty_corpus_does_not_divide_by_zero(self, store):
        report = build_coverage_report(studied=[], findings=[], stats=store.stats(), all_active=[])
        assert report.source_coverage == 0.0
        assert report.origin_coverage == 0.0
