"""Reading how much plan is left, without spending any of it.

Deepr's own availability check dispatches a real request per backend, which
spends quota to discover whether there is quota. That is the wrong trade when
the answer is "almost none", and it is the reason this reads metadata instead.
"""

from deepr.backends.quota_headroom import (
    PlanHeadroom,
    exhausted,
    order_by_headroom,
    parse_snapshot,
)

_NOW = 1_000_000.0

_SNAPSHOT = {
    "providers": [
        {
            "provider": "claude",
            "ok": True,
            "plan": "max",
            "windows": [
                {"label": "5h", "used_percent": 95.0, "resets_at": _NOW + 900},
                {"label": "weekly", "used_percent": 52.0, "resets_at": _NOW + 400000},
            ],
        },
        {"provider": "codex", "ok": True, "windows": [{"label": "weekly", "used_percent": 4.0, "resets_at": _NOW}]},
        {"provider": "grok", "ok": True, "windows": [{"label": "weekly", "used_percent": 88.0, "resets_at": _NOW}]},
        {"provider": "dead", "ok": False, "windows": []},
    ]
}


class TestParsing:
    def test_the_tightest_window_is_the_one_that_binds(self):
        """A five-hour cap at 95% matters more than a weekly one at 52%."""
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        assert plans["claude"].used_percent == 95.0
        assert plans["claude"].window_label == "5h"

    def test_headroom_is_the_inverse_of_usage(self):
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        assert plans["codex"].headroom == 0.96
        assert plans["claude"].headroom < 0.1

    def test_reset_time_is_relative_and_never_negative(self):
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        assert plans["claude"].resets_in_s == 900
        assert plans["codex"].resets_in_s == 0.0

    def test_a_provider_reporting_not_ok_is_exhausted(self):
        assert parse_snapshot(_SNAPSHOT, now=_NOW)["dead"].is_exhausted

    def test_a_malformed_window_does_not_take_the_snapshot_down(self):
        payload = {"providers": [{"provider": "x", "windows": [{"used_percent": "lots"}]}]}
        assert parse_snapshot(payload, now=_NOW)["x"].used_percent == 0.0


class TestOrdering:
    def test_most_headroom_goes_first(self):
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        assert order_by_headroom(["claude", "grok", "codex"], plans) == ["codex", "grok", "claude"]

    def test_an_unreported_plan_sorts_in_the_middle(self):
        """Neither preferred nor starved: absence is not evidence either way."""
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        assert order_by_headroom(["claude", "unknown", "codex"], plans) == ["codex", "unknown", "claude"]

    def test_no_snapshot_leaves_the_given_order_alone(self):
        assert order_by_headroom(["a", "b"], {}) == ["a", "b"]


class TestExhaustion:
    def test_a_plan_at_its_cap_is_named(self):
        plans = {"claude": PlanHeadroom(provider="claude", used_percent=98.0, window_label="5h")}
        assert exhausted(["claude", "codex"], plans) == ["claude"]

    def test_a_plan_with_room_is_not(self):
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        assert exhausted(["codex", "grok"], plans) == []

    def test_describe_says_which_window_and_when_it_resets(self):
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        text = plans["claude"].describe()
        assert "5h" in text and "95%" in text and "15m" in text
