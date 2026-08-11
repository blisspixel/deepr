"""The cutoff helpers must name a freshness band, not a calendar date.

Sixteen tests hardcoded `datetime(2026, 6, 26)`, which read as `fresh` when
they were written and passed for weeks. At 45 days of real elapsed time it
crossed into `aging`, the self model started emitting an extra proposal, and
four tests that index into `proposals[0]` began asserting against a different
proposal. Nothing in the suite had changed.

These tests hold the property that made that possible impossible: the band a
helper produces is the same on any day it runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deepr.experts.profile import ExpertProfile
from tests.expert_time_helpers import recent_cutoff, stale_cutoff

_DOMAINS = ("consult reliability", "ai research", "medicine", "law")


def _status(cutoff: datetime, domain: str) -> str:
    profile = ExpertProfile(name="Probe", vector_store_id="vs-probe", domain=domain, knowledge_cutoff_date=cutoff)
    return str(profile.get_freshness_status().get("status") or "")


class TestTheBandDoesNotDriftWithTheCalendar:
    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_recent_reads_as_fresh_in_every_domain(self, domain: str) -> None:
        """Velocity differs by domain, so one age has to be safe for all."""
        assert _status(recent_cutoff(), domain) == "fresh"

    @pytest.mark.parametrize("domain", _DOMAINS)
    def test_stale_is_never_fresh_in_any_domain(self, domain: str) -> None:
        assert _status(stale_cutoff(), domain) != "fresh"

    def test_the_age_it_produces_is_constant(self) -> None:
        """The property that makes expiry impossible.

        Freshness is a function of `now - cutoff`. A hardcoded date makes that
        difference grow every day; a relative one keeps it fixed, so the band
        is whatever it was on the day the test was written, forever. Asserting
        the age directly is the honest form of "this will not expire" - the
        alternative is re-deriving `now - (now - k) == k`, which is arithmetic
        rather than a test.
        """
        age = datetime.now(UTC) - recent_cutoff()
        assert timedelta(days=3) <= age <= timedelta(days=4)

    def test_a_fixed_date_is_what_this_replaces(self) -> None:
        """The regression itself: a hardcoded date drifts out of its band.

        Asserted rather than described, so the reason these helpers exist
        cannot quietly stop being true.
        """
        fixed = datetime(2026, 6, 26, tzinfo=UTC)
        assert _status(fixed, "consult reliability") != _status(recent_cutoff(), "consult reliability")
