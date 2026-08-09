"""Which model read the corpus, and how coarse the answer honestly is.

The point of this record: a 14B model and a frontier model reading the same
corpus produce different experts, and no downstream statistic recovers the
difference - a shallow finding is grounded, traceable and cross-source just as
easily as a deep one. Unlike every other signal in expert_health, this one is a
fact about a subprocess rather than an inference about quality from structure.
"""

from deepr.experts.model_provenance import (
    TIER_FRONTIER,
    TIER_MID,
    TIER_SMALL,
    TIER_UNKNOWN,
    ModelProvenance,
    at_least,
    classify_tier,
    record,
    weakest,
)


class TestPlanBackends:
    def test_a_vendor_agent_cli_is_frontier_class(self):
        """The claim is about the family, not the exact checkpoint."""
        for backend in ("claude", "codex", "grok", "antigravity"):
            assert classify_tier(f"plan:{backend}") == TIER_FRONTIER, backend

    def test_an_unrecognised_plan_is_unknown_rather_than_assumed_good(self):
        assert classify_tier("plan:somethingnew") == TIER_UNKNOWN


class TestLocalModels:
    def test_size_comes_from_the_tag_because_that_is_where_it_is_stated(self):
        assert classify_tier("local:qwen2.5:14b") == TIER_SMALL
        assert classify_tier("local:mistral-small3.2:24b") == TIER_MID
        assert classify_tier("local:llama-3.3-70b-instruct") == TIER_FRONTIER

    def test_a_tag_with_no_parameter_count_is_unknown_not_guessed(self):
        """mistral-small and mistral-large are the same string to a guess."""
        assert classify_tier("local:mistral-small") == TIER_UNKNOWN
        assert classify_tier("local:gemma") == TIER_UNKNOWN

    def test_decimal_parameter_counts_parse(self):
        assert classify_tier("local:phi-3.5:3.8b") == TIER_SMALL

    def test_the_boundary_sizes_land_where_documented(self):
        assert classify_tier("local:x:20b") == TIER_MID
        assert classify_tier("local:x:19b") == TIER_SMALL
        assert classify_tier("local:x:65b") == TIER_FRONTIER


class TestTheWeakestLinkWins:
    def test_an_expert_is_ranked_by_the_worst_reading_in_its_chain(self):
        """A frontier brief over 7B findings inherits the 7B blind spots.

        The brief can only rank and reconcile what it was handed; it cannot
        recover a comparison that was never found.
        """
        chain = [record("plan:claude"), record("local:qwen2.5:7b"), record("plan:grok")]
        assert weakest(chain).tier == TIER_SMALL

    def test_artifacts_that_were_never_stamped_do_not_drag_the_rank_down(self):
        """An older artifact predating this record is absent, not bad."""
        chain = [record("plan:claude"), ModelProvenance()]
        assert weakest(chain).tier == TIER_FRONTIER

    def test_an_entirely_unstamped_expert_reports_unknown(self):
        assert weakest([ModelProvenance(), ModelProvenance()]).tier == TIER_UNKNOWN

    def test_an_empty_chain_is_unknown_rather_than_an_error(self):
        assert weakest([]).tier == TIER_UNKNOWN


class TestAtLeast:
    def test_unknown_never_satisfies_a_floor(self):
        """Absence of evidence must not read as evidence of quality."""
        assert not at_least(TIER_UNKNOWN, TIER_SMALL)
        assert not at_least(TIER_UNKNOWN, TIER_FRONTIER)

    def test_a_higher_tier_satisfies_a_lower_floor(self):
        assert at_least(TIER_FRONTIER, TIER_MID)
        assert at_least(TIER_MID, TIER_MID)
        assert not at_least(TIER_SMALL, TIER_MID)


class TestSerialization:
    def test_the_stamp_round_trips(self):
        original = record("local:qwen2.5:14b", "qwen2.5:14b")
        restored = ModelProvenance.from_dict(original.to_dict())
        assert restored == original

    def test_a_corrupt_stamp_reads_as_unknown_rather_than_raising(self):
        assert ModelProvenance.from_dict("not a dict").tier == TIER_UNKNOWN
        assert ModelProvenance.from_dict({"tier": "amazing"}).tier == TIER_UNKNOWN
