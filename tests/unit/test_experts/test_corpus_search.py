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
    interleave_by_arm,
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
        assert await search_once("q", client=client, min_interval_s=0) == []


class TestRunPlan:
    @pytest.mark.asyncio
    async def test_every_query_in_the_plan_is_carried_to_the_network(self):
        plan = plan_queries("widgets")
        client = _client({})
        await run_search_plan(plan, client=client, min_interval_s=0)
        assert len(client.calls) == len(plan.queries)

    @pytest.mark.asyncio
    async def test_hits_record_the_arm_that_surfaced_them(self):
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.by_arm("adversarial")})

        result = await run_search_plan(plan, client=client, min_interval_s=0)

        assert result.hits
        assert {h.arm for h in result.hits} == {"adversarial"}

    @pytest.mark.asyncio
    async def test_a_url_seen_twice_is_retained_once(self):
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.queries})

        result = await run_search_plan(plan, client=client, min_interval_s=0)

        assert len(result.hits) == len({h.url for h in result.hits})

    @pytest.mark.asyncio
    async def test_an_arm_whose_results_were_all_duplicates_is_still_reported(self):
        """Observed twice live: such an arm was neither found nor failed.

        Derived from failures alone it is invisible, which is a check passing
        because its subject is absent rather than sound.
        """
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.queries})

        result = await run_search_plan(plan, client=client, min_interval_s=0)

        empty = result.arms_that_found_nothing()
        assert "genre" in empty
        assert "descriptive" not in empty

    @pytest.mark.asyncio
    async def test_the_url_ceiling_says_what_it_did_not_run(self):
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.queries})

        result = await run_search_plan(plan, max_urls=1, client=client, min_interval_s=0)

        assert "ceiling" in result.stopped_early
        assert result.unrun_queries > 0


class TestEarlyStopping:
    """Running every query put ~120 requests at one free endpoint in a burst.

    Three builds came back rate-limited with zero results, which is
    indistinguishable from a subject nobody has written about. The goal was
    never to run every query; it was a corpus spanning enough publishers.
    """

    @pytest.mark.asyncio
    async def test_the_plan_stops_once_enough_hosts_are_found(self):
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.queries})

        result = await run_search_plan(plan, target_hosts=2, client=client, min_interval_s=0)

        assert "distinct hosts" in result.stopped_early
        assert len(client.calls) < len(plan.queries)

    @pytest.mark.asyncio
    async def test_it_will_not_stop_before_every_arm_has_run(self):
        """Coverage reached in the descriptive arm is the popular half only."""
        plan = plan_queries("widgets")
        client = _client({q.text: _HTML for q in plan.queries})

        result = await run_search_plan(plan, target_hosts=1, client=client, min_interval_s=0)

        assert result.every_arm_tried
        assert {"adversarial", "primary"} <= result.attempted_arms

    @pytest.mark.asyncio
    async def test_arms_are_interleaved_so_an_early_stop_is_unbiased(self):
        plan = plan_queries("widgets")
        arms = [q.arm for q in interleave_by_arm(list(plan.queries))]
        assert len(set(arms[:4])) == 4, "the first queries must span arms, not repeat one"

    @pytest.mark.asyncio
    async def test_running_the_whole_plan_is_still_possible(self):
        plan = plan_queries("widgets")
        client = _client({})

        result = await run_search_plan(plan, client=client, min_interval_s=0)

        assert not result.stopped_early
        assert len(client.calls) == len(plan.queries)


class TestReporting:
    def test_distinct_hosts_collapses_www(self):
        result = SearchResult(hits=[SearchHit(url="https://www.a.org/x", query="q")])
        assert result.distinct_hosts == {"a.org"}

    def test_arms_that_found_nothing_appears_in_the_payload(self):
        result = SearchResult(attempted_arms={"adversarial"})
        assert result.to_dict()["arms_that_found_nothing"] == ["adversarial"]


class TestCoverageIsJudgedAgainstThePlan:
    """The gate was hardcoded to 5 while ARMS held 6.

    A plan containing all six arms could satisfy the gate with one arm never
    run, and which arm got skipped was whatever the interleave left last.
    Comparing against ``len(ARMS)`` instead would break the other way: many
    plans carry no terminology queries at all, so the gate would never open
    and every query would run - the request burst the early stop exists to
    prevent.
    """

    def test_a_six_arm_plan_is_not_covered_by_five(self):
        result = SearchResult(
            planned_arms={"descriptive", "adversarial", "genre", "primary", "recency", "terminology"},
            attempted_arms={"descriptive", "adversarial", "genre", "primary", "recency"},
        )
        assert not result.every_arm_tried

    def test_a_five_arm_plan_is_covered_by_its_own_five(self):
        arms = {"descriptive", "adversarial", "genre", "primary", "recency"}
        assert SearchResult(planned_arms=arms, attempted_arms=set(arms)).every_arm_tried

    def test_a_real_plan_can_reach_coverage_at_all(self):
        """Guards the regression that would silence early stopping entirely."""
        plan = plan_queries("widgets")
        planned = {q.arm for q in plan.queries if q.arm}
        assert SearchResult(planned_arms=planned, attempted_arms=planned).every_arm_tried

    def test_a_hand_built_result_does_not_read_as_permanently_incomplete(self):
        assert SearchResult(attempted_arms={"descriptive"}).every_arm_tried
