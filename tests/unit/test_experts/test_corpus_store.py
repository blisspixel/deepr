"""Corpus retention: content-addressed, idempotent, origin-honest."""

import pytest

from deepr.experts.corpus_store import CorpusStore, active_source_count, content_hash


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


class TestActiveSourceCount:
    def test_header_and_superseded_lines_are_not_active(self):
        """Status used to count every non-empty line, including the schema header."""
        import json

        header = json.dumps({"schema_version": "deepr-expert-corpus-v1", "expert": "X"})
        live = json.dumps({"sha256": "aaa", "origin_key": "url:one.org", "superseded_by": ""})
        old = json.dumps({"sha256": "bbb", "origin_key": "url:one.org", "superseded_by": "aaa"})
        text = "\n".join([header, live, old, "{not json", ""]) + "\n"
        assert active_source_count(text) == 1

    def test_header_only_index_is_empty(self):
        import json

        header = json.dumps({"schema_version": "deepr-expert-corpus-v1", "expert": "X"})
        assert active_source_count(header + "\n") == 0


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

    def test_budget_is_a_hard_ceiling(self, store):
        """One oversized source must not silently blow the budget.

        Refusing to split returned 81k against a 45k budget, and the oversized
        prompt made models abandon their output contract and write prose.
        """
        store.add("x" * 500, origin_key="url:a.org")
        store.add("y" * 500, origin_key="url:b.org")
        material = store.load_study_material(max_chars=600)
        assert sum(len(text) for _, text in material) <= 600

    def test_a_single_oversized_source_is_cut_to_the_budget(self, store):
        store.add("z" * 5000, origin_key="url:a.org")
        material = store.load_study_material(max_chars=1000)
        assert len(material) == 1
        assert len(material[0][1]) == 1000


class TestStudyChunks:
    def test_a_large_source_splits_into_several_chunks(self, store):
        store.add("q" * 45000, origin_key="url:a.org")
        chunks = store.iter_study_chunks(chunk_chars=14000)
        assert len(chunks) == 4
        assert all(len(text) <= 14000 for chunk in chunks for _, text in chunk)

    def test_an_oversized_source_is_split_alone(self, store):
        """A source too big to share a slice keeps its own provenance."""
        store.add("a" * 20000, origin_key="url:a.org")
        store.add("b" * 20000, origin_key="url:b.org")
        chunks = store.iter_study_chunks(chunk_chars=14000)
        assert all(len(chunk) == 1 for chunk in chunks)

    def test_sources_share_a_chunk_when_the_budget_allows(self, store):
        """A lens shown one source at a time cannot compare sources.

        Packing is what makes cross-source contention possible at all: with a
        slice per source, disagreement between publishers is not merely rare,
        it cannot be found.
        """
        store.add("short one", origin_key="url:a.org")
        store.add("short two", origin_key="url:b.org")
        chunks = store.iter_study_chunks(chunk_chars=14000)
        assert len(chunks) == 1
        assert {entry.origin_key for entry, _ in chunks[0]} == {"url:a.org", "url:b.org"}

    def test_packing_stops_at_the_budget(self, store):
        store.add("a" * 6000, origin_key="url:a.org")
        store.add("b" * 6000, origin_key="url:b.org")
        store.add("c" * 6000, origin_key="url:c.org")
        chunks = store.iter_study_chunks(chunk_chars=10000)
        assert len(chunks) == 3
        assert all(sum(len(t) for _, t in chunk) <= 10000 for chunk in chunks)

    def test_every_retained_char_survives_chunking(self, store):
        """An off-by-one that dropped or duplicated text would pass a count check."""
        store.add("a" * 25000, origin_key="url:a.org")
        store.add("b" * 3000, origin_key="url:b.org")
        chunks = store.iter_study_chunks(chunk_chars=10000)
        rebuilt = "".join(text for chunk in chunks for _, text in chunk)
        assert rebuilt.count("a") == 25000
        assert rebuilt.count("b") == 3000

    def test_chunking_respects_the_overall_budget(self, store):
        store.add("m" * 40000, origin_key="url:a.org")
        chunks = store.iter_study_chunks(chunk_chars=10000, max_chars=20000)
        assert sum(len(text) for chunk in chunks for _, text in chunk) <= 20000
