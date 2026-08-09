"""Identity that survives a rerun, which positional ids did not.

The bug being fixed: `finding_id = f"{lens}-{ordinal}"` renumbers when a
partial resume re-runs one lens, so a brief citing `failure-30` silently
repoints at a different finding. The citation still validates against the id
set, which is worse than failing - the provenance chain reports itself intact
while pointing at the wrong evidence.
"""

from deepr.experts.record_identity import (
    finding_thread_id,
    is_stable_id,
    normalize_text,
    position_thread_id,
    version_id,
)


class TestFindingIdentityIsAboutTheCorpus:
    def test_the_same_finding_keeps_its_id_across_runs(self):
        first = finding_thread_id(lens="failure", title="Harness over-shackling", anchors=["the agent could not"])
        second = finding_thread_id(lens="failure", title="Harness over-shackling", anchors=["the agent could not"])
        assert first == second

    def test_anchor_order_does_not_change_identity(self):
        """The model returns anchors in whatever order it likes."""
        a = finding_thread_id(lens="failure", title="T", anchors=["one", "two"])
        b = finding_thread_id(lens="failure", title="T", anchors=["two", "one"])
        assert a == b

    def test_reflowing_the_title_does_not_create_a_new_finding(self):
        """Same passages, same lens, cosmetically different wording."""
        a = finding_thread_id(lens="failure", title="Harness over-shackling.", anchors=["x"])
        b = finding_thread_id(lens="failure", title="harness  over shackling", anchors=["x"])
        assert a == b

    def test_different_anchors_are_a_different_finding(self):
        """Anchors are what a finding is about in the corpus."""
        a = finding_thread_id(lens="failure", title="T", anchors=["one"])
        b = finding_thread_id(lens="failure", title="T", anchors=["something else entirely"])
        assert a != b

    def test_the_same_title_from_a_different_lens_is_a_different_finding(self):
        a = finding_thread_id(lens="failure", title="T", anchors=["x"])
        b = finding_thread_id(lens="contention", title="T", anchors=["x"])
        assert a != b

    def test_the_lens_stays_readable_in_the_id(self):
        assert finding_thread_id(lens="failure", title="T", anchors=["x"]).startswith("failure-")

    def test_empty_anchors_still_yield_a_stable_id(self):
        """A lens that quoted nothing still produced a finding."""
        assert finding_thread_id(lens="failure", title="T", anchors=[]) == finding_thread_id(
            lens="failure", title="T", anchors=[""]
        )


class TestPositionIdentityIsTheQuestion:
    def test_revising_the_stance_keeps_the_same_thread(self):
        """The whole point. A revision is the same position, restated."""
        before = position_thread_id("Does multi-agent orchestration survive better models?")
        after = position_thread_id("Does multi-agent orchestration survive better models?")
        assert before == after

    def test_a_different_question_is_a_different_thread(self):
        assert position_thread_id("Does X hold?") != position_thread_id("Does Y hold?")

    def test_punctuation_and_case_do_not_fork_a_thread(self):
        assert position_thread_id("Does X hold?") == position_thread_id("does x hold")

    def test_it_does_not_depend_on_list_order(self):
        """position-1 became a different question whenever a brief reordered."""
        assert position_thread_id("Q") == position_thread_id("Q")


class TestVersionIsSeparateFromThread:
    def test_two_keys_because_one_cannot_do_both(self):
        """ExpertStance.create hashes title|statement, so a revised stance
        silently becomes an unrelated record. That is the bug being avoided."""
        thread = position_thread_id("Does X hold?")
        v1 = version_id("Does X hold?|likely|because A")
        v2 = version_id("Does X hold?|roughly even chance|because B")
        assert v1 != v2
        assert position_thread_id("Does X hold?") == thread

    def test_identical_content_is_the_same_version(self):
        assert version_id("same") == version_id("same")


class TestHashingHygiene:
    def test_the_separator_prevents_a_concatenation_collision(self):
        """Joining "ab"+"c" and "a"+"bc" to one string is how content ids
        collide on inputs that are not remotely alike."""
        a = finding_thread_id(lens="failure", title="ab", anchors=["c"])
        b = finding_thread_id(lens="failure", title="a", anchors=["bc"])
        assert a != b

    def test_accents_fold_so_one_source_does_not_fork_a_thread(self):
        assert normalize_text("Café") == normalize_text("Cafe")

    def test_normalize_tolerates_none_and_numbers(self):
        assert normalize_text(None) == ""
        assert normalize_text(12) == "12"


class TestTellingDurableIdsFromLegacyOnes:
    def test_a_positional_id_is_recognised_as_legacy(self):
        """Lets a migration find records to re-key without a separate flag."""
        assert not is_stable_id("failure-3")
        assert not is_stable_id("position-1")

    def test_a_derived_id_is_recognised_as_durable(self):
        assert is_stable_id(finding_thread_id(lens="failure", title="T", anchors=["x"]))
        assert is_stable_id(position_thread_id("Q"))

    def test_junk_is_not_mistaken_for_durable(self):
        assert not is_stable_id("")
        assert not is_stable_id("failure-zzzzzzzzzzzzzzzz")
