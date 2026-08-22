"""Reading how much plan is left, without spending any of it.

Deepr's own availability check dispatches a real request per backend, which
spends quota to discover whether there is quota. That is the wrong trade when
the answer is "almost none", and it is the reason this reads metadata instead.
"""

from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

import deepr.backends.quota_headroom as quota_headroom
from deepr.backends.quota_headroom import (
    PlanHeadroom,
    exhausted,
    order_by_headroom,
    parse_snapshot,
    read_headroom,
)

_NOW = 1_000_000.0

_JSON_SCALARS = st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=40)
_JSON_VALUES = st.recursive(
    _JSON_SCALARS,
    lambda children: st.lists(children, max_size=8) | st.dictionaries(st.text(max_size=20), children, max_size=8),
    max_leaves=30,
)

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

    def test_malformed_provider_entries_are_ignored(self):
        payload = {"providers": [None, "provider", 42, {"provider": None}, {"provider": ""}]}
        assert parse_snapshot(payload, now=_NOW) == {}

    def test_non_object_snapshot_is_treated_as_unavailable(self):
        assert parse_snapshot([], now=_NOW) == {}
        assert parse_snapshot("invalid", now=_NOW) == {}

    def test_malformed_window_members_and_reset_values_are_bounded(self):
        payload = {
            "providers": [
                {
                    "provider": "x",
                    "windows": [
                        None,
                        {"used_percent": float("nan")},
                        {"label": "daily", "used_percent": 52, "resets_at": "later"},
                    ],
                }
            ]
        }
        plan = parse_snapshot(payload, now=_NOW)["x"]
        assert plan.used_percent == 52.0
        assert plan.window_label == "daily"
        assert plan.resets_in_s == 0.0

    def test_malformed_ok_value_fails_closed(self):
        plan = parse_snapshot({"providers": [{"provider": "x", "ok": "false"}]}, now=_NOW)["x"]
        assert plan.ok is False
        assert plan.is_exhausted

    def test_usage_is_clamped_to_a_percentage(self):
        too_high = parse_snapshot({"providers": [{"provider": "high", "windows": [{"used_percent": 500}]}]}, now=_NOW)
        below_zero = parse_snapshot({"providers": [{"provider": "low", "windows": [{"used_percent": -25}]}]}, now=_NOW)
        assert too_high["high"].used_percent == 100.0
        assert below_zero["low"].used_percent == 0.0

    @given(payload=_JSON_VALUES)
    def test_arbitrary_json_is_total_and_bounded(self, payload):
        plans = parse_snapshot(payload, now=_NOW)
        for provider, plan in plans.items():
            assert provider == provider.strip().lower()
            assert provider
            assert 0.0 <= plan.used_percent <= 100.0
            assert 0.0 <= plan.headroom <= 1.0
            assert plan.resets_in_s >= 0.0
            assert isinstance(plan.ok, bool)


class TestReading:
    def teardown_method(self):
        quota_headroom._cache = None

    def test_valid_json_with_wrong_top_level_type_never_raises(self, monkeypatch):
        monkeypatch.setattr(quota_headroom.shutil, "which", lambda _name: "quotabot")
        monkeypatch.setattr(
            quota_headroom.subprocess,
            "run",
            lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="[]"),
        )
        quota_headroom._cache = None

        assert read_headroom(force=True) == {}

    def test_failed_forced_refresh_invalidates_cached_snapshot(self, monkeypatch):
        executable_available = True
        monkeypatch.setattr(
            quota_headroom.shutil,
            "which",
            lambda _name: "quotabot" if executable_available else None,
        )
        monkeypatch.setattr(
            quota_headroom.subprocess,
            "run",
            lambda *_args, **_kwargs: SimpleNamespace(
                returncode=0,
                stdout='{"providers":[{"provider":"cached","windows":[]}]}',
            ),
        )
        quota_headroom._cache = None
        assert "cached" in read_headroom(force=True)

        executable_available = False
        assert read_headroom(force=True) == {}
        assert read_headroom() == {}


class TestOrdering:
    def test_most_headroom_goes_first(self):
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        assert order_by_headroom(["claude", "grok", "codex"], plans) == ["codex", "grok", "claude"]

    def test_an_unreported_plan_sorts_in_the_middle(self):
        """Neither preferred nor starved: absence is not evidence either way."""
        plans = parse_snapshot(_SNAPSHOT, now=_NOW)
        assert order_by_headroom(["claude", "unknown", "codex"], plans) == ["codex", "unknown", "claude"]

    def test_a_reported_plan_without_a_window_is_not_treated_as_fully_unused(self):
        plans = {
            "fresh": PlanHeadroom(provider="fresh", used_percent=10.0, window_label="weekly"),
            "unmeasured": PlanHeadroom(provider="unmeasured"),
            "busy": PlanHeadroom(provider="busy", used_percent=80.0, window_label="weekly"),
        }
        assert order_by_headroom(["busy", "unmeasured", "fresh"], plans) == ["fresh", "unmeasured", "busy"]

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
