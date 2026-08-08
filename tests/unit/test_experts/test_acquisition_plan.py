"""Diversification is a mechanism, not an instruction.

The evidence this is built on: prompting a searcher to broaden had limited
effect across 21 studies and roughly 9,900 participants, while changing what
the algorithm returned worked, and searchers did not spontaneously broaden.
So every test here asserts that an arm is emitted whether or not anything
asked for it.
"""

import pytest

from deepr.experts.acquisition_plan import (
    ARM_ADVERSARIAL,
    ARM_DESCRIPTIVE,
    ARM_GENRE,
    ARM_PRIMARY,
    ARM_TERMINOLOGY,
    ARMS,
    harvest_alternates,
    plan_queries,
)


class TestDiversificationIsMechanical:
    def test_the_adversarial_arm_is_always_emitted(self):
        """Nobody searches for the case against their own topic unprompted."""
        plan = plan_queries("mycorrhizal networks")
        texts = [q.text for q in plan.by_arm(ARM_ADVERSARIAL)]
        assert "criticism of mycorrhizal networks" in texts
        assert "failure to replicate mycorrhizal networks" in texts

    def test_the_genre_arm_reaches_documents_that_must_disagree(self):
        """Comments, replies and retractions exist because somebody objected."""
        texts = [q.text for q in plan_queries("X").by_arm(ARM_GENRE)]
        assert "comment on X" in texts
        assert "X retraction" in texts

    def test_primary_sources_are_sought_separately_from_the_topic(self):
        texts = [q.text for q in plan_queries("X").by_arm(ARM_PRIMARY)]
        assert "X specification" in texts
        assert "X original paper" in texts

    def test_a_plan_covers_every_arm_it_can_without_extra_input(self):
        covered = plan_queries("X").arms_covered
        assert {ARM_DESCRIPTIVE, ARM_ADVERSARIAL, ARM_GENRE, ARM_PRIMARY} <= covered

    def test_no_arm_is_silently_dropped_from_the_vocabulary(self):
        """A new arm must be reachable, or it is decoration."""
        plan = plan_queries("X", alternates=("Y",), exclude_publishers=("a.org",))
        assert plan.arms_covered <= set(ARMS)
        assert len(plan.arms_covered) >= 5

    def test_an_empty_topic_plans_nothing_rather_than_searching_for_nothing(self):
        assert plan_queries("   ").queries == []


class TestBreakingPublisherCapture:
    def test_a_dominant_publisher_is_excluded_and_re_asked(self):
        """A corpus collapsed onto one site keeps collapsing; ask who else."""
        plan = plan_queries("mycorrhizal networks", exclude_publishers=("en.wikipedia.org",))
        texts = [q.text for q in plan.queries]
        assert "mycorrhizal networks -site:en.wikipedia.org" in texts

    def test_the_exclusion_names_why_it_is_there(self):
        plan = plan_queries("X", exclude_publishers=("a.org",))
        excl = [q for q in plan.queries if "-site:" in q.text]
        assert "already dominates" in excl[0].rationale


class TestTerminology:
    def test_alternates_become_their_own_queries(self):
        plan = plan_queries("mycorrhizal networks", alternates=("wood wide web", "common mycorrhizal network"))
        texts = [q.text for q in plan.by_arm(ARM_TERMINOLOGY)]
        assert "wood wide web" in texts

    def test_alternates_are_harvested_from_what_was_read_not_guessed(self):
        texts = [
            "Common mycorrhizal networks (CMNs) link plants together.",
            "The common mycorrhizal network (CMNs) is popularly called the wood wide web.",
        ]
        found = harvest_alternates(texts, topic="mycorrhizal networks")
        assert "CMNs" in found

    def test_harvesting_ignores_restatements_of_the_topic_itself(self):
        found = harvest_alternates(["A study of networks (mycorrhizal networks) here."], topic="mycorrhizal networks")
        assert "mycorrhizal networks" not in found

    def test_harvesting_nothing_is_not_an_error(self):
        assert harvest_alternates(["plain text with no parentheticals"], topic="X") == ()


class TestConcerns:
    def test_a_plan_without_alternate_terminology_says_so(self):
        """The documented miss is a paper using the out-group's word."""
        assert any("alternate terminology" in c for c in plan_queries("X").concerns())

    def test_a_full_plan_still_flags_only_what_is_genuinely_missing(self):
        plan = plan_queries("X", alternates=("Y",))
        assert not any("alternate terminology" in c for c in plan.concerns())
        assert not any("adversarial" in c for c in plan.concerns())


class TestSerialization:
    def test_a_plan_is_inspectable_before_anything_is_spent(self):
        payload = plan_queries("X", alternates=("Y",)).to_dict()
        assert payload["query_count"] > 0
        assert ARM_ADVERSARIAL in payload["arms_covered"]
        assert all({"text", "arm", "rationale"} <= set(q) for q in payload["queries"])

    @pytest.mark.parametrize("arm", [ARM_DESCRIPTIVE, ARM_ADVERSARIAL, ARM_GENRE, ARM_PRIMARY])
    def test_every_query_states_why_it_is_in_the_plan(self, arm):
        assert all(q.rationale for q in plan_queries("X").by_arm(arm))


class TestLongTopics:
    """Found by using it: a sentence-length topic makes every query unusable."""

    def test_a_long_topic_is_shortened_for_templating(self):
        plan = plan_queries("How to keep AI agent produced software work from degrading into low quality output")
        assert plan.search_key
        assert len(plan.search_key.split()) <= 6
        assert all(len(q.text) < 90 for q in plan.by_arm(ARM_ADVERSARIAL))

    def test_the_shortening_is_reported_not_done_quietly(self):
        plan = plan_queries("How to keep AI agent produced software work from degrading into low quality output")
        assert any("too" in c and "template" in c for c in plan.concerns())

    def test_a_short_topic_is_left_alone(self):
        plan = plan_queries("AI generated code slop")
        assert plan.search_key == plan.topic
        assert not any("shortened" in c for c in plan.concerns())

    def test_stopwords_do_not_consume_the_budget(self):
        """Six content words, not six tokens of 'how to the of'."""
        assert "slop" in plan_queries("how to deal with the problem of AI slop in code").search_key
