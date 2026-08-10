"""One clock, one interval convention, one sentinel.

Closed-open is the only convention under which consecutive versions tile the
timeline with no gap and no overlap, so `predecessor.superseded_at ==
successor.recorded_at` exactly and a point-in-time read returns exactly one
version. Everything here exists so that is implemented once rather than three
times.
"""

from deepr.experts.record_time import (
    BEGINNING_OF_TIME,
    END_OF_TIME,
    age_days,
    contains,
    is_open,
    overlaps,
    parse_iso,
    utc_now,
)

JAN = "2026-01-01T00:00:00+00:00"
JUN = "2026-06-01T00:00:00+00:00"
DEC = "2026-12-01T00:00:00+00:00"


class TestClosedOpen:
    def test_the_start_instant_is_included(self):
        assert contains(JAN, DEC, JAN)

    def test_the_end_instant_is_excluded(self):
        assert not contains(JAN, DEC, DEC)

    def test_consecutive_versions_tile_with_no_gap_and_no_overlap(self):
        """The whole reason for the convention: exactly one version at a boundary."""
        first = (JAN, JUN)
        second = (JUN, DEC)

        at_boundary = [contains(*first, JUN), contains(*second, JUN)]

        assert at_boundary == [False, True], "the boundary belongs to exactly one version"

    def test_a_moment_before_the_interval_is_outside(self):
        assert not contains(JUN, DEC, JAN)


class TestTheSentinelRatherThanNull:
    def test_an_open_interval_contains_any_later_moment(self):
        assert contains(JAN, END_OF_TIME, DEC)

    def test_an_absent_end_is_treated_as_open_not_as_closed(self):
        """A record written before this module existed must read as live.

        The bug this avoids already exists elsewhere: a temporal filter that
        excludes records with missing endpoints, silently under-returning.
        """
        assert contains(JAN, "", DEC)

    def test_an_absent_start_means_it_has_always_applied(self):
        assert contains("", END_OF_TIME, JAN)

    def test_is_open_recognises_both_forms(self):
        assert is_open(END_OF_TIME)
        assert is_open("")
        assert not is_open(DEC)

    def test_the_sentinel_round_trips_through_the_parser(self):
        """It is datetime.max at UTC, so export and reparse are lossless."""
        assert parse_iso(END_OF_TIME) is not None
        assert parse_iso(END_OF_TIME).year == 9999

    def test_the_sentinel_sorts_after_real_timestamps_as_a_string(self):
        """Sorting without parsing is sometimes right, and must not mis-order."""
        assert sorted([DEC, END_OF_TIME, JAN])[-1] == END_OF_TIME
        assert sorted([DEC, BEGINNING_OF_TIME, JAN])[0] == BEGINNING_OF_TIME


class TestParsing:
    def test_a_trailing_z_is_accepted(self):
        assert parse_iso("2026-06-01T00:00:00Z") == parse_iso(JUN)

    def test_a_naive_timestamp_is_assumed_utc(self):
        assert parse_iso("2026-06-01T00:00:00") == parse_iso(JUN)

    def test_junk_returns_none_rather_than_raising(self):
        """One corrupt timestamp must not take down a read across a store."""
        assert parse_iso("not a date") is None
        assert parse_iso("") is None
        assert parse_iso(None) is None

    def test_utc_now_is_parseable_by_our_own_parser(self):
        assert parse_iso(utc_now()) is not None


class TestOverlaps:
    def test_a_successor_that_continues_does_not_overlap(self):
        assert not overlaps(JAN, JUN, JUN, DEC)

    def test_a_successor_that_contradicts_does_overlap(self):
        """Materially stronger than a revision, and worth flagging separately."""
        assert overlaps(JAN, DEC, JUN, END_OF_TIME)

    def test_two_open_intervals_always_overlap(self):
        assert overlaps(JAN, END_OF_TIME, JUN, END_OF_TIME)

    def test_disjoint_intervals_do_not(self):
        assert not overlaps(JAN, JUN, DEC, END_OF_TIME)


class TestAgeDays:
    def test_unknown_is_minus_one_rather_than_zero(self):
        """Zero is a real answer meaning today; a missing timestamp is not."""
        assert age_days("") == -1
        assert age_days("nonsense") == -1

    def test_it_counts_whole_days(self):
        assert age_days(JAN, now="2026-01-11T00:00:00+00:00") == 10

    def test_a_future_timestamp_clamps_to_zero(self):
        assert age_days(DEC, now=JAN) == 0
