"""The expert's own account of itself, and the name it answers to.

The naming instruction has one job and originally failed it. Told to pick
something "that fits the subject", four experts named themselves after terms
from their own fields - Green Tax, In-Domain Mirage, Hard Skip, The Missing
Ledger. Those are things an expert would write *about*. An economist is not
called "Marginal Utility".
"""

from deepr.experts.expert_profile_card import (
    ExpertProfile,
    PerspectiveShift,
    build_profile_prompt,
    parse_profile,
)

AT = "2026-08-09T00:00:00+00:00"


class TestItAsksForANameNotAThesis:
    def test_the_distinction_is_stated_first(self):
        prompt = build_profile_prompt("E", material="M")
        assert "a name for yourself. Not a label for your argument" in prompt

    def test_the_failure_mode_is_named_with_its_own_bad_output(self):
        """Showing the actual mistake beats describing it abstractly."""
        prompt = build_profile_prompt("E", material="M")
        assert "Green Tax" in prompt
        assert "In-Domain Mirage" in prompt

    def test_it_asks_for_temperament_rather_than_subject_fit(self):
        prompt = build_profile_prompt("E", material="M")
        assert "temperament" in prompt
        assert "a name, not a topic" in prompt

    def test_it_does_not_demand_a_human_first_name(self):
        """An entity may be called something other than Dave."""
        assert "does not have to be a human first name" in build_profile_prompt("E", material="M")


class TestThePriorStandpointIsShown:
    def test_a_prior_reading_reaches_the_prompt(self):
        """It cannot report a change it was never shown."""
        prior = ExpertProfile(expert_name="E", standpoint="An earlier reading.")
        assert "An earlier reading." in build_profile_prompt("E", material="M", prior=prior)

    def test_no_prior_shows_no_earlier_reading(self):
        assert "Your prior standpoint, from an earlier reading" not in build_profile_prompt("E", material="M")

    def test_a_prior_with_no_standpoint_is_not_shown_as_one(self):
        prior = ExpertProfile(expert_name="E", standpoint="")
        prompt = build_profile_prompt("E", material="M", prior=prior)
        assert "Your prior standpoint, from an earlier reading" not in prompt


class TestParsingCarriesHistoryForward:
    def test_a_reported_change_becomes_a_shift(self):
        prior = ExpertProfile(expert_name="E", standpoint="I read it as naming.")
        profile = parse_profile(
            {
                "chosen_name": "Ledger",
                "standpoint": "I read it as retraction.",
                "shift_from_prior": "I read it as naming.",
                "shift_because": "the failure lens moved it",
            },
            expert_name="E",
            at=AT,
            prior=prior,
        )

        assert len(profile.shifts) == 1
        assert profile.shifts[0].because == "the failure lens moved it"

    def test_earlier_shifts_survive(self):
        """Append-only. Overwriting leaves the state a new expert is in."""
        prior = ExpertProfile(expert_name="E", standpoint="second")
        prior.shifts = [PerspectiveShift(at="2026-01-01", was="first", now="second", because="x")]

        profile = parse_profile(
            {"standpoint": "third", "shift_from_prior": "second", "shift_because": "y"},
            expert_name="E",
            at=AT,
            prior=prior,
        )

        assert [s.was for s in profile.shifts] == ["first", "second"]

    def test_no_prior_means_no_shift_however_much_it_claims(self):
        """A first profile cannot have changed from anything."""
        profile = parse_profile(
            {"standpoint": "now", "shift_from_prior": "invented", "shift_because": "invented"},
            expert_name="E",
            at=AT,
            prior=None,
        )
        assert profile.shifts == []

    def test_an_unchanged_standpoint_records_nothing(self):
        prior = ExpertProfile(expert_name="E", standpoint="same")
        profile = parse_profile(
            {"standpoint": "same", "shift_from_prior": "same", "shift_because": "y"},
            expert_name="E",
            at=AT,
            prior=prior,
        )
        assert profile.shifts == []

    def test_the_corpus_state_is_stamped_on_the_profile(self):
        profile = parse_profile(
            {"standpoint": "s"}, expert_name="E", at=AT, corpus_fingerprint="abc123", sources_read=12
        )
        assert profile.corpus_fingerprint == "abc123"
        assert profile.sources_read == 12
