"""Unified spend caps: both env families bind, tighter wins, never fail open."""

from __future__ import annotations

import json

import pytest

from deepr.core.cost_caps import SpendCapConfigurationError, freeze_paid_api, resolve_spend_caps

_ALL_VARS = [
    "DEEPR_MAX_COST_PER_JOB",
    "DEEPR_MAX_COST_PER_DAY",
    "DEEPR_MAX_COST_PER_WEEK",
    "DEEPR_MAX_COST_PER_MONTH",
    "DEEPR_PER_JOB_LIMIT",
    "DEEPR_DAILY_LIMIT",
    "DEEPR_WEEKLY_LIMIT",
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
    with pytest.raises(SpendCapConfigurationError, match="DEEPR_MAX_COST_PER_JOB"):
        resolve_spend_caps()


def test_zero_is_a_real_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "0")
    assert resolve_spend_caps() == {"per_job": 0.0, "daily": 0.0, "weekly": 200.0, "monthly": 200.0}


def test_operator_budget_is_a_binding_ceiling(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text('{"monthly_limit": 10}', encoding="utf-8")
    assert resolve_spend_caps(budget_path=path) == {
        "per_job": 5.0,
        "daily": 10.0,
        "weekly": 10.0,
        "monthly": 10.0,
    }


def test_manual_freeze_collapses_every_window(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text('{"monthly_limit": 10, "paid_api_frozen": true}', encoding="utf-8")
    assert resolve_spend_caps(budget_path=path) == {
        "per_job": 0.0,
        "daily": 0.0,
        "weekly": 0.0,
        "monthly": 0.0,
    }


def test_missing_monthly_authority_is_default_off(tmp_path) -> None:
    assert resolve_spend_caps(budget_path=tmp_path / "missing.json") == {
        "per_job": 0.0,
        "daily": 0.0,
        "weekly": 0.0,
        "monthly": 0.0,
    }


def test_weekly_cap_is_normalized_into_narrower_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_WEEK", "3")
    assert resolve_spend_caps() == {"per_job": 3.0, "daily": 3.0, "weekly": 3.0, "monthly": 200.0}


def test_automatic_freeze_preserves_budget_document_fields(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        '{"monthly_limit": 10, "monthly_spending": 3, "history": [{"job_id": "kept"}]}',
        encoding="utf-8",
    )

    operator = freeze_paid_api("reported cost divergence", path=path)

    assert operator.frozen is True
    assert operator.freeze_reason == "reported cost divergence"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["monthly_limit"] == 10
    assert document["monthly_spending"] == 3
    assert document["history"] == [{"job_id": "kept"}]
