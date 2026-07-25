"""Unified spend caps: both env families bind, tighter wins, never fail open."""

from __future__ import annotations

import pytest

from deepr.core.cost_caps import resolve_spend_caps

_ALL_VARS = [
    "DEEPR_MAX_COST_PER_JOB",
    "DEEPR_MAX_COST_PER_DAY",
    "DEEPR_MAX_COST_PER_MONTH",
    "DEEPR_PER_JOB_LIMIT",
    "DEEPR_DAILY_LIMIT",
    "DEEPR_MONTHLY_LIMIT",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for name in _ALL_VARS:
        monkeypatch.delenv(name, raising=False)


def test_documented_caps_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "10")
    assert resolve_spend_caps()["monthly"] == 10.0


def test_tighter_bound_wins_when_both_families_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "10")
    monkeypatch.setenv("DEEPR_MONTHLY_LIMIT", "20")
    assert resolve_spend_caps()["monthly"] == 10.0

    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "50")
    monkeypatch.setenv("DEEPR_DAILY_LIMIT", "5")
    assert resolve_spend_caps()["daily"] == 5.0


def test_malformed_values_never_fall_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "not-a-number")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "0")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "-3")
    caps = resolve_spend_caps()
    # Malformed/zero/negative values fall back to defaults, not unlimited.
    assert caps == {"per_job": 5.0, "daily": 10.0, "monthly": 20.0}


def test_defaults_without_any_env() -> None:
    assert resolve_spend_caps() == {"per_job": 5.0, "daily": 10.0, "monthly": 20.0}
