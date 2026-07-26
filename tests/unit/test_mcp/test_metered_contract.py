"""No-surprise-spend contract tests for paid MCP entry points."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from deepr.mcp.metered_contract import MeteredMCPContractError, require_metered_api_contract


def _authorize(budget: object = 1.0) -> float:
    return require_metered_api_contract(
        budget=budget,
        allow_metered_api=True,
        confirm_metered_cost=True,
    )


@pytest.mark.parametrize(
    ("allow_metered_api", "confirm_metered_cost"),
    [(False, False), (True, False), (False, True), (1, True), (True, 1)],
)
def test_both_consent_flags_must_be_explicit_true(allow_metered_api: object, confirm_metered_cost: object) -> None:
    with pytest.raises(MeteredMCPContractError) as caught:
        require_metered_api_contract(
            budget=1.0,
            allow_metered_api=allow_metered_api,
            confirm_metered_cost=confirm_metered_cost,
        )

    assert caught.value.code == "METERED_API_NOT_APPROVED"


@pytest.mark.parametrize("budget", [None, True, 0, -1, float("nan"), float("inf"), float("-inf"), "1"])
def test_budget_must_be_explicit_finite_and_positive(budget: object) -> None:
    with pytest.raises(MeteredMCPContractError) as caught:
        _authorize(budget)

    assert caught.value.code == "INVALID_BUDGET"


def test_ceiling_cannot_exceed_global_operator_per_call_cap() -> None:
    with (
        patch("deepr.core.cost_caps.resolve_spend_caps", return_value={"per_job": 0.50}),
        pytest.raises(MeteredMCPContractError) as caught,
    ):
        _authorize(0.51)

    assert caught.value.code == "BUDGET_EXCEEDED"


@pytest.mark.parametrize("caps", [{"per_job": 0.0}, {"per_job": float("nan")}])
def test_frozen_or_invalid_global_cap_blocks_paid_call(caps: dict[str, float]) -> None:
    with (
        patch("deepr.core.cost_caps.resolve_spend_caps", return_value=caps),
        pytest.raises(MeteredMCPContractError) as caught,
    ):
        _authorize()

    assert caught.value.code == "BUDGET_EXCEEDED"


def test_unreadable_global_authority_fails_closed() -> None:
    with (
        patch("deepr.core.cost_caps.resolve_spend_caps", side_effect=ValueError("bad policy")),
        pytest.raises(MeteredMCPContractError) as caught,
    ):
        _authorize()

    assert caught.value.code == "BUDGET_UNAVAILABLE"


def test_authorized_ceiling_is_returned_unchanged() -> None:
    with patch("deepr.core.cost_caps.resolve_spend_caps", return_value={"per_job": 2.0}):
        assert _authorize(0.75) == 0.75
