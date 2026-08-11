"""Spreading a run across prepaid plans, and moving on as each runs out.

The failure this pins was watched repeatedly rather than imagined: a study or
brief died on one plan's weekly cap while three other plans sat idle, and the
run was restarted by hand against a different `--plan`.

The distinction that makes the pool adaptive rather than merely redundant: a
plan that is out of quota fails identically for every remaining call, so it is
retired from rotation. A prompt that fails is one call, and gets one retry
somewhere else.
"""

import asyncio

import pytest

from deepr.experts.backend_pool import BackendPool, PooledBackend


def _backend(name: str, behaviour):
    return PooledBackend(name=name, completion=behaviour)


def _ok(text: str):
    async def run(prompt: str) -> str:
        return text

    return run


def _dies(message: str):
    async def run(prompt: str) -> str:
        raise RuntimeError(message)

    return run


def _dies_after(n: int, message: str, text: str = "ok"):
    state = {"calls": 0}

    async def run(prompt: str) -> str:
        state["calls"] += 1
        if state["calls"] > n:
            raise RuntimeError(message)
        return text

    return run


class TestAnExhaustedPlanIsRetired:
    def test_it_moves_to_the_next_plan_rather_than_failing(self):
        pool = BackendPool(
            backends=[
                _backend("grok", _dies("API error (status 402 Payment Required): usage balance exhausted")),
                _backend("codex", _ok("from codex")),
            ]
        )
        assert asyncio.run(pool.complete("p")) == "from codex"

    def test_the_dead_plan_leaves_rotation_instead_of_being_re_poked(self):
        """Round-robin used to hand it work every cycle and waste a call."""
        grok = _backend("grok", _dies("quota exhausted"))
        pool = BackendPool(backends=[grok, _backend("codex", _ok("ok"))])

        for _ in range(4):
            asyncio.run(pool.complete("p"))

        assert grok.calls == 1, "an exhausted plan must be asked exactly once"
        assert pool.names == ["codex"]

    def test_retirement_is_reported_rather_than_silent(self):
        pool = BackendPool(backends=[_backend("grok", _dies("usage balance exhausted")), _backend("codex", _ok("ok"))])
        asyncio.run(pool.complete("p"))

        assert any("grok" in note for note in pool.retired)

    def test_a_plan_that_dies_mid_run_is_retired_then(self):
        """The real shape: it worked, then the weekly cap hit."""
        grok = _backend("grok", _dies_after(1, "429 rate limit"))
        pool = BackendPool(backends=[grok, _backend("codex", _ok("codex"))])

        first = asyncio.run(pool.complete("p"))
        second = asyncio.run(pool.complete("p"))
        third = asyncio.run(pool.complete("p"))

        assert first == "ok"
        assert second == third == "codex"
        assert pool.names == ["codex"]

    def test_every_plan_running_out_raises_and_names_them_all(self):
        pool = BackendPool(
            backends=[_backend("grok", _dies("quota exhausted")), _backend("codex", _dies("quota exhausted"))]
        )
        with pytest.raises(Exception) as caught:
            asyncio.run(pool.complete("p"))

        assert "quota" in str(caught.value).lower()
        assert pool.backends == []


class TestAPromptFailureIsNotAPlanFailure:
    def test_a_bad_prompt_retries_elsewhere_without_retiring_anything(self):
        """A prompt that fails twice is usually the prompt."""
        pool = BackendPool(
            backends=[_backend("grok", _dies("no JSON object in response")), _backend("codex", _ok("recovered"))]
        )
        assert asyncio.run(pool.complete("p")) == "recovered"
        assert pool.retired == []
        assert len(pool.names) == 2

    def test_it_gives_up_after_one_retry_rather_than_walking_the_pool(self):
        pool = BackendPool(
            backends=[
                _backend("a", _dies("bad prompt")),
                _backend("b", _dies("bad prompt")),
                _backend("c", _ok("never reached")),
            ]
        )
        with pytest.raises(RuntimeError):
            asyncio.run(pool.complete("p"))

        assert len(pool.names) == 3, "a prompt failure must not shrink the pool"


class TestReporting:
    def test_usage_shows_where_the_work_actually_went(self):
        pool = BackendPool(backends=[_backend("grok", _ok("a")), _backend("codex", _ok("b"))])
        asyncio.run(pool.complete("p"))
        asyncio.run(pool.complete("p"))

        usage = pool.usage()
        assert usage["grok"]["calls"] == 1
        assert usage["codex"]["calls"] == 1

    def test_chunk_size_is_the_smallest_member_can_hold(self):
        """A chunk sized for the largest would break on the tightest, and the
        run cannot know which member serves any given call."""
        pool = BackendPool(
            backends=[
                PooledBackend(name="a", completion=_ok("x"), chunk_chars=200_000),
                PooledBackend(name="b", completion=_ok("x"), chunk_chars=14_000),
            ]
        )
        assert pool.chunk_chars == 14_000

    def test_an_empty_pool_says_so_rather_than_hanging(self):
        with pytest.raises(RuntimeError, match="no plan-quota backend"):
            asyncio.run(BackendPool().complete("p"))
