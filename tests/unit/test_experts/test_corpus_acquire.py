"""Acquisition: the expert fetches for itself, and a refresh is not a new source.

This module had no tests at all, which is how a refresh came to create a
duplicate corpus entry every time. Nothing downstream could tell the difference
between one page fetched seven times and seven independent sources, so every
corroboration count inflated with the refresh cadence.
"""

from types import SimpleNamespace

import pytest

from deepr.experts.corpus_acquire import _as_source_text, acquire_sources
from deepr.experts.corpus_store import CorpusStore, content_hash


_BODY = "Retained pages must clear the nav-shell guard, so fixture bodies are realistic rather than a few words. " * 4


def _page(text=_BODY, title="A Title"):
    """A fetched page. Bodies must exceed the minimum-useful-length guard."""
    return SimpleNamespace(text=text, title=title, status_code=200)


def _fetcher(pages):
    """Serve canned pages by URL, recording what was asked for."""
    calls = []

    async def fetch(url):
        calls.append(url)
        page = pages.get(url)
        if isinstance(page, Exception):
            raise page
        return page

    fetch.calls = calls
    return fetch


@pytest.fixture
def store(tmp_path):
    return CorpusStore("Acquire Expert", storage_dir=tmp_path / "corpus")


class TestSourceIdentity:
    def test_retained_text_is_stable_across_fetches(self):
        """Nothing that varies between two fetches may enter the hashed body."""
        first = _as_source_text(_page(), "https://ex.com/a")
        second = _as_source_text(_page(), "https://ex.com/a")
        assert content_hash(first) == content_hash(second)

    def test_the_retrieval_date_is_not_part_of_the_content(self):
        """A date in the body made every refresh a brand new source."""
        text = _as_source_text(_page(), "https://ex.com/a")
        assert "fetched_at" not in text

    def test_different_bodies_stay_different_sources(self):
        a = _as_source_text(_page(_BODY + " one"), "https://ex.com/a")
        b = _as_source_text(_page(_BODY + " two"), "https://ex.com/a")
        assert content_hash(a) != content_hash(b)


class TestRefresh:
    @pytest.mark.asyncio
    async def test_refetching_an_unchanged_page_adds_no_source(self, store):
        pages = {"https://ex.com/a": _page()}

        await acquire_sources(expert_name="E", urls=list(pages), corpus=store, fetch_page=_fetcher(pages))
        after_first = len(store.active_entries())
        result = await acquire_sources(expert_name="E", urls=list(pages), corpus=store, fetch_page=_fetcher(pages))

        assert after_first == 1
        assert len(store.active_entries()) == 1
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_a_changed_page_is_retained_as_a_new_revision(self, store):
        url = "https://ex.com/a"
        await acquire_sources(
            expert_name="E", urls=[url], corpus=store, fetch_page=_fetcher({url: _page(_BODY + " first revision")})
        )
        await acquire_sources(
            expert_name="E", urls=[url], corpus=store, fetch_page=_fetcher({url: _page(_BODY + " second revision")})
        )

        assert len(store.entries) == 2

    @pytest.mark.asyncio
    async def test_one_origin_for_every_page_from_a_publisher(self, store):
        """Counting each page as its own origin would read as broad corroboration."""
        pages = {
            "https://ex.com/a": _page(_BODY + " page a"),
            "https://ex.com/b": _page(_BODY + " page b"),
        }
        await acquire_sources(expert_name="E", urls=list(pages), corpus=store, fetch_page=_fetcher(pages))

        assert len(store.active_entries()) == 2
        assert len(store.distinct_origins()) == 1


class TestFailureIsolation:
    @pytest.mark.asyncio
    async def test_one_failed_url_does_not_abort_the_others(self, store):
        pages = {
            "https://ex.com/good": _page(),
            "https://ex.com/bad": RuntimeError("connection reset"),
        }
        result = await acquire_sources(expert_name="E", urls=list(pages), corpus=store, fetch_page=_fetcher(pages))

        assert len(store.active_entries()) == 1
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_every_url_failing_is_reported_as_such(self, store):
        pages = {"https://ex.com/bad": RuntimeError("connection reset")}
        result = await acquire_sources(expert_name="E", urls=list(pages), corpus=store, fetch_page=_fetcher(pages))

        assert not store.active_entries()
        assert result.exit_code == 2

    @pytest.mark.asyncio
    async def test_a_repeated_url_is_fetched_once(self, store):
        url = "https://ex.com/a"
        fetch = _fetcher({url: _page()})
        await acquire_sources(expert_name="E", urls=[url, url, url], corpus=store, fetch_page=fetch)

        assert fetch.calls == [url]
