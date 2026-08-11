"""Knowledge-cutoff dates expressed as an age, not as a calendar date.

Freshness is computed as ``datetime.now(UTC) - knowledge_cutoff_date``, checked
against thresholds that are fractions of the domain's velocity. A test that
hardcodes ``datetime(2026, 6, 26)`` therefore does not pin a freshness band -
it pins a date whose band changes as real time passes, and the test silently
becomes a different test every day.

That is not hypothetical. Sixteen tests across eleven files were written when
that date read as `fresh`, and they passed for weeks. At 45 days of real
elapsed time the same date crossed into `aging`, the self model began emitting
a `self_model_review` proposal, and four tests that index into
``proposals[0]`` started asserting against a different proposal than the one
they were written for. Nothing in the suite had changed.

Ages are expressed as fractions of the fresh/aging thresholds rather than as
day counts, so they hold for any domain velocity rather than only for the
default one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

_FRESH_FRACTION = 0.25
"""Comfortably inside `fresh`, which begins at 0.5 x velocity.

Half the threshold rather than just under it: a value near the boundary is the
same time bomb with a shorter fuse."""

_STALE_MULTIPLE = 4.0
"""Well past `critical`, which begins at 1.5 x velocity."""

_MIN_VELOCITY_DAYS = 14
"""The shortest velocity any domain uses, so one age is safe for all of them."""


def recent_cutoff() -> datetime:
    """A cutoff that reads as `fresh` today and every day after.

    Use where the test is about something other than staleness and simply
    needs an expert that is not overdue for a refresh.
    """
    return datetime.now(UTC) - timedelta(days=_MIN_VELOCITY_DAYS * _FRESH_FRACTION)


def stale_cutoff() -> datetime:
    """A cutoff that reads as `critical` today and every day after.

    Use where the test is specifically exercising the overdue path, so that
    intent is stated rather than encoded in a date that happens to be old.
    """
    return datetime.now(UTC) - timedelta(days=365 * _STALE_MULTIPLE)
