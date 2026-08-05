"""Corpus retention: content-addressed, idempotent, origin-honest."""

import pytest

from deepr.experts.corpus_store import CorpusStore, content_hash


@pytest.fixture
def store(tmp_path):
    return CorpusStore("Corpus Test Expert", storage_dir=tmp_path / "corpus")


class TestContentHash:
    def test_line_endings_do_not_fork_identity(self):
        """The same document fetched on two platforms must be one entry.

        Two entries would read as two independent origins and inflate
        corroboration on the strength of one publisher.
        """
        assert content_hash("a\r\nb\r\n") == content_hash("a\nb\n")

    def test_different_text_differs(self):
        assert content_hash("alpha") != content_hash("beta")


class TestAdd:
    def test_retains_text_and_is_readable_back(self, store):
        entry, was_new = store.add("The retained body text.", origin_key="url:example.org")
        assert was_new is True
        assert store.read(entry.sha256) == "The retained body text."

    def test_re_adding_identical_text_is_a_noop(self, store):
        """A refresh cadence must not duplicate storage or inflate origins."""
        first, new_first = store.add("same body", origin_key="url:example.org")
        second, new_second = store.add("same body", origin_key="url:example.org")
        assert new_first is True
        assert new_second is False
        assert first.sha256 == second.sha256
        assert store.stats().entry_count == 1

    def test_many_files_from_one_publisher_are_one_origin(self, store):
        """The invariant that keeps `expert quality` from lying.

        A crawl of one documentation site is one publisher's authority, however
        many pages it produced.
        """
        for i in range(12):
            store.add(f"page {i} body", origin_key="url:docs.example.org", publisher="example.org")
        stats = store.stats()
        assert stats.active_count == 12
        assert stats.distinct_origins == 1

    def test_distinct_publishers_count_separately(self, store):
        store.add("a", origin_key="url:one.org")
        store.add("b", origin_key="url:two.org")
        assert store.stats().distinct_origins == 2

    def test_empty_text_refused(self, store):
        with pytest.raises(ValueError):
            store.add("   ", origin_key="url:example.org")

    def test_missing_origin_key_refused(self, store):
        """Without an origin key there is no honest corroboration accounting."""
        with pytest.raises(ValueError):
            store.add("body", origin_key="")

    def test_bad_trust_class_refused(self, store):
        with pytest.raises(ValueError):
            store.add("body", origin_key="url:example.org", trust_class="excellent")

    def test_default_trust_is_secondary(self, store):
        entry, _ = store.add("body", origin_key="url:example.org")
        assert entry.trust_class == "secondary"


class TestPersistence:
    def test_survives_reload(self, tmp_path):
        first = CorpusStore("Reload Expert", storage_dir=tmp_path / "corpus")
        entry, _ = first.add("persisted body", origin_key="url:example.org", title="T")

        second = CorpusStore("Reload Expert", storage_dir=tmp_path / "corpus")
        assert entry.sha256 in second.entries
        assert second.entries[entry.sha256].title == "T"
        assert second.read(entry.sha256) == "persisted body"

    def test_torn_index_line_does_not_break_the_corpus(self, tmp_path):
        store = CorpusStore("Torn Expert", storage_dir=tmp_path / "corpus")
        store.add("good body", origin_key="url:example.org")
        with store.index_path.open("a", encoding="utf-8") as handle:
            handle.write("{not valid json\n")

        reloaded = CorpusStore("Torn Expert", storage_dir=tmp_path / "corpus")
        assert reloaded.stats().active_count == 1


class TestSupersede:
    def test_old_text_is_retained_not_deleted(self, store):
        """Knowing what a source used to say is how change becomes visible."""
        old, _ = store.add("version one", origin_key="url:example.org")
        new, _ = store.add("version two", origin_key="url:example.org")
        assert store.supersede(old.sha256, new.sha256) is True

        assert store.read(old.sha256) == "version one"
        assert store.entries[old.sha256].is_active is False
        assert store.stats().active_count == 1

    def test_supersede_unknown_hash_returns_false(self, store):
        entry, _ = store.add("body", origin_key="url:example.org")
        assert store.supersede("nosuchhash", entry.sha256) is False


class TestStudyMaterial:
    def test_ordering_is_deterministic(self, store):
        for i in range(6):
            store.add(f"body {i}", origin_key=f"url:site{i % 3}.org")
        first = [e.sha256 for e, _ in store.load_study_material()]
        second = [e.sha256 for e, _ in store.load_study_material()]
        assert first == second

    def test_superseded_sources_are_excluded(self, store):
        old, _ = store.add("old body", origin_key="url:example.org")
        new, _ = store.add("new body", origin_key="url:example.org")
        store.supersede(old.sha256, new.sha256)
        shas = [e.sha256 for e, _ in store.load_study_material()]
        assert shas == [new.sha256]

    def test_budget_never_truncates_a_source(self, store):
        """A lens reading half a document reports absences caused by the cut."""
        store.add("x" * 500, origin_key="url:a.org")
        store.add("y" * 500, origin_key="url:b.org")
        material = store.load_study_material(max_chars=600)
        assert len(material) == 1
        assert len(material[0][1]) == 500

    def test_budget_always_returns_at_least_one_source(self, store):
        store.add("z" * 5000, origin_key="url:a.org")
        assert len(store.load_study_material(max_chars=10)) == 1
