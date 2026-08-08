"""Search carries the plan's questions to the network and nothing more.

The discipline being tested is restraint: no ranking beyond the engine's, no
relevance judgment, no filtering on content. Selection belongs to the plan
upstream and the independence measurement downstream, and a search module that
also judged quality would put three decisions in one place with no way to
inspect any of them.
"""

from types import SimpleNamespace

import pytest

from deepr.experts.acquisition_plan import plan_queries
from deepr.experts.corpus_search import (
    SearchHit,
    SearchResult,
    parse_result_urls,
    run_search_plan,
    search_once,
)

_HTML = """
<a href="https://duckduckgo.com/y.js?ad=1">ad</a>
<a href="https://example.org/one">One</a>
<a href="https://example.org/one">One again</a>
<a href="https://other.test/two">Two</a>
<a href="https://cdn.test/logo.png">image</a>
"""


def _client(pages):
    """A stubbed HTTP client. Deepr's search is one POST; nothing else."""
    calls = []

    class _Stub:
        async def post(self, url, data=None, headers=None):
            calls.append(data["q"])
            body = pages.get(data["q"], "")
            if isinstance(body, Exception):
                raise body
            return SimpleNamespace(status_code=200, text=body)

        async def aclose(self):
            return None

    stub = _Stub()
    stub.calls = calls
    return stub


class TestParsing:
    def test_engine_and_asset_links_are_not_candidates(self):
        urls = parse_result_urls(_HTML, limit=10)
        assert "https://example.org/one" in urls
        assert not any("duckduckgo" in u or u.endswith(".png") for u in urls)

    def test_order_is_the_engines_order(self):
        """Deepr has no basis for a better ranking; inventing one hides a judgment."""
        assert parse_result_urls(_HTML, limit=10) == ["https://example.org/one", "https://other.test/two"]

    def test_duplicates_collapse(self):
        assert parse_result_urls(_HTML, limit=10).count("https://example.org/one") == 1

    def test_limit_is_respected(self):
        assert len(parse_result_urls(_HTML, limit=1)) == 1

    def test_empty_html_yields_nothing_rather_than_raising(self):
        assert parse_result_urls("", limit=5) == []


class TestSearchOnce:
    @pytest.mark.asyncio
    async def test_a_failing_query_returns_empty_rather_than_raising(self):
        """One dead query must not abort a plan of thirty."""
        client = _client({"q": RuntimeError("network down")})
        assert await search_once("q", client=client) == []


class TestRunPlan:
    @pytest.mark.asyncio
    async def test_every_query_in_the_plan_is_carried_to_the_network(self):
        plan = plan_queries("widgets")
        client = _client({})
        await run_search_plan(plan, client=client)
        assert len(client.calls) == len(plan.queries)

    @pytest.mark.asyncio
    async def test_hits_record_the_arm_that_surfaced_them(self):
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.by_arm("adversarial")})

        result = await run_search_plan(plan, client=client)

        assert result.hits
        assert {h.arm for h in result.hits} == {"adversarial"}

    @pytest.mark.asyncio
    async def test_a_url_seen_twice_is_retained_once(self):
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.queries})

        result = await run_search_plan(plan, client=client)

        assert len(result.hits) == len({h.url for h in result.hits})

    @pytest.mark.asyncio
    async def test_an_arm_whose_results_were_all_duplicates_is_still_reported(self):
        """Observed twice live: such an arm was neither found nor failed.

        Derived from failures alone it is invisible, which is a check passing
        because its subject is absent rather than sound.
        """
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.queries})

        result = await run_search_plan(plan, client=client)

        empty = result.arms_that_found_nothing()
        assert "genre" in empty
        assert "descriptive" not in empty

    @pytest.mark.asyncio
    async def test_the_url_ceiling_says_what_it_did_not_run(self):
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.queries})

        result = await run_search_plan(plan, max_urls=1, client=client)

        assert any("unrun" in f for f in result.failures)


class TestReporting:
    def test_distinct_hosts_collapses_www(self):
        result = SearchResult(hits=[SearchHit(url="https://www.a.org/x", query="q")])
        assert result.distinct_hosts == {"a.org"}

    def test_arms_that_found_nothing_appears_in_the_payload(self):
        result = SearchResult(attempted_arms={"adversarial"})
        assert result.to_dict()["arms_that_found_nothing"] == ["adversarial"]
