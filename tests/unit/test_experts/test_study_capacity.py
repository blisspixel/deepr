"""Running out of capacity is not the same as finding nothing.

The bug this pins, measured on a live run: a plan backend exhausted its quota
mid-study. Every remaining call raised, each was caught as a per-chunk failure
string, the pass carried on calling a dead backend for every remaining chunk
and lens, and it then wrote a complete-looking study.json with 44 findings from
two of eight lenses. The reason was recorded only as prose in `limitations`
that no downstream code reads, and `brief` consumed the result as truth.

The distinction that has to survive into the artifact: "the corpus had nothing
to say" and "I could not ask" are different results.
"""

import pytest

from deepr.experts.study import _is_capacity_failure, run_study
from deepr.experts.study_lenses import LENSES

from .test_study import CORPUS_TEXT, _completion_returning, corpus  # noqa: F401


class TestTellingTheTwoApart:
    def test_a_plan_quota_error_is_a_capacity_failure(self):
        from deepr.backends.plan_quota.errors import PlanQuotaExhausted

        assert _is_capacity_failure(PlanQuotaExhausted("weekly limit reached"))

    def test_a_stringified_backend_failure_is_recognised_too(self):
        """Plan CLIs surface this through stderr, wrapped, not as our type."""
        assert _is_capacity_failure(RuntimeError("API error (status 402 Payment Required): usage balance exhausted"))
        assert _is_capacity_failure(RuntimeError("429 rate limit exceeded"))

    def test_a_model_answering_badly_is_not_a_capacity_failure(self):
        """A prose answer is a genuinely partial result; the pass should continue."""
        assert not _is_capacity_failure(ValueError("no JSON object in response"))
        assert not _is_capacity_failure(TimeoutError("read timed out"))


class TestTheStudyStopsRatherThanDegrading:
    @pytest.mark.asyncio
    async def test_exhaustion_stops_the_pass_instead_of_thinning_it(self, corpus):
        """It used to keep calling a dead backend for every remaining lens."""
        calls = {"n": 0}

        async def dies_after_one(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("API error (status 402 Payment Required): usage balance exhausted")
            return '{"fail_patterns": [{"name": "x", "anchors": ["' + CORPUS_TEXT[:60] + '"]}]}'

        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=dies_after_one,
            lens_keys=["failure", "contention", "mechanism"],
        )

        # Three lenses were asked for; it must not have called the backend once
        # per chunk per lens after capacity ran out.
        assert calls["n"] < 6
        assert any("Capacity ran out" in limit for limit in result.limitations)

    @pytest.mark.asyncio
    async def test_the_limitation_says_incomplete_rather_than_thin(self, corpus):
        async def dead(prompt: str) -> str:
            raise RuntimeError("plan quota exhausted")

        result = await run_study(expert_name="E", corpus=corpus, completion=dead, lens_keys=["failure", "contention"])

        note = next(limit for limit in result.limitations if "Capacity ran out" in limit)
        assert "incomplete rather than thin" in note
        assert "never read" in note

    @pytest.mark.asyncio
    async def test_findings_gathered_before_exhaustion_are_kept(self, corpus):
        """They were read before capacity ran out; they are real."""
        calls = {"n": 0}

        async def dies_after_first_lens(prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] > len(LENSES["failure"].output_field) * 0:  # first call only
                if calls["n"] > 1:
                    raise RuntimeError("quota exhausted")
            return '{"fail_patterns": [{"name": "kept", "anchors": ["' + CORPUS_TEXT[:60] + '"]}]}'

        result = await run_study(
            expert_name="E", corpus=corpus, completion=dies_after_first_lens, lens_keys=["failure", "contention"]
        )

        assert result.findings, "findings read before exhaustion must survive"

    @pytest.mark.asyncio
    async def test_a_parse_failure_still_lets_the_pass_continue(self, corpus):
        """Only capacity stops the run. A bad answer is tolerable per chunk."""
        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion_returning("this is prose, not JSON"),
            lens_keys=["failure", "contention"],
        )

        assert not any("Capacity ran out" in limit for limit in result.limitations)
        assert len(result.outcomes) == 2
