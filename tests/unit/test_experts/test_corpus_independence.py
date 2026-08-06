"""Counting a corpus by origin rather than by document.

The run that motivated this scored three retained sources, forty anchored
findings, and zero warnings that mattered. All three sources were Wikipedia
pages. One number would have said so before any of it was spent.
"""

import pytest

from deepr.experts.corpus_independence import measure_independence
from deepr.experts.corpus_store import CorpusStore


@pytest.fixture
def store(tmp_path):
    return CorpusStore("Independence Expert", storage_dir=tmp_path / "corpus")


def _entries(store, spec):
    """spec: list of (body, origin_key, trust_class)."""
    for body, origin, trust in spec:
        store.add(body, origin_key=origin, trust_class=trust)
    return store.active_entries()


class TestEffectiveSourceCount:
    def test_one_publisher_many_pages_counts_as_one(self, store):
        """The exact shape of the run this was written for."""
        entries = _entries(
            store,
            [
                ("first body", "url:en.wikipedia.org", "tertiary"),
                ("second body", "url:en.wikipedia.org", "tertiary"),
                ("third body", "url:en.wikipedia.org", "tertiary"),
            ],
        )
        report = measure_independence(entries)

        assert report.source_count == 3
        assert report.effective_source_count == 1.0
        assert report.is_thin

    def test_distinct_publishers_count_separately(self, store):
        entries = _entries(
            store,
            [
                ("first body", "url:a.org", "primary"),
                ("second body", "url:b.org", "primary"),
                ("third body", "url:c.org", "primary"),
            ],
        )
        report = measure_independence(entries)

        assert report.effective_source_count == pytest.approx(3.0, abs=0.01)
        assert not report.is_thin

    def test_a_lopsided_corpus_scores_below_its_publisher_count(self, store):
        """Nine pages from one site plus one from another is not two sources."""
        spec = [(f"body {i}", "url:big.org", "secondary") for i in range(9)]
        spec.append(("lone body", "url:small.org", "secondary"))
        report = measure_independence(_entries(store, spec))

        assert report.origin_count == 2
        assert report.effective_source_count < 1.6
        assert report.is_thin

    def test_superseded_revisions_do_not_inflate_the_count(self, store):
        """The same source at an earlier moment is not a second source."""
        first, _ = store.add("original body", origin_key="url:a.org")
        second, _ = store.add("revised body", origin_key="url:a.org")
        store.supersede(first.sha256, second.sha256)
        store.add("other publisher body", origin_key="url:b.org")

        report = measure_independence(store.active_entries())

        assert report.source_count == 2
        assert report.effective_source_count == pytest.approx(2.0, abs=0.01)

    def test_an_empty_corpus_reports_rather_than_divides_by_zero(self):
        report = measure_independence([])
        assert report.source_count == 0
        assert report.concerns() == ["Corpus is empty."]


class TestConcerns:
    def test_a_single_origin_corpus_says_agreement_is_not_corroboration(self, store):
        entries = _entries(
            store,
            [("a body", "url:one.org", "secondary"), ("b body", "url:one.org", "secondary")],
        )
        assert any("agreeing with itself" in c for c in measure_independence(entries).concerns())

    def test_a_dominant_publisher_is_named(self, store):
        spec = [(f"body {i}", "url:big.org", "secondary") for i in range(8)]
        spec += [("x body", "url:b.org", "secondary"), ("y body", "url:c.org", "secondary")]
        concerns = measure_independence(_entries(store, spec)).concerns()

        assert any("url:big.org" in c and "sets what can be concluded" in c for c in concerns)

    def test_an_all_tertiary_corpus_is_flagged(self, store):
        entries = _entries(
            store,
            [
                ("a body", "url:a.org", "tertiary"),
                ("b body", "url:b.org", "tertiary"),
                ("c body", "url:c.org", "tertiary"),
            ],
        )
        assert any("tertiary" in c for c in measure_independence(entries).concerns())

    def test_a_genuinely_diverse_corpus_raises_nothing(self, store):
        entries = _entries(
            store,
            [
                ("a body", "url:a.org", "primary"),
                ("b body", "url:b.org", "primary"),
                ("c body", "url:c.org", "secondary"),
            ],
        )
        assert measure_independence(entries).concerns() == []
