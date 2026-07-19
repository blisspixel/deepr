"""Finite budget validation for A2A consult requests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.a2a.consult_tasks import _budget_value, _validate_capacity_request, run_consult_task


@pytest.mark.parametrize("budget", [float("nan"), float("inf"), float("-inf")])
def test_a2a_consult_rejects_nonfinite_budget(budget: float) -> None:
    error = _validate_capacity_request("local", budget, {})

    assert error is not None
    assert error["error_code"] == "INVALID_BUDGET"


def test_a2a_boolean_budget_is_not_coerced_to_one_dollar() -> None:
    assert _budget_value(True) == -1.0


@pytest.mark.parametrize("approval", ["false", "true", "0", 1, [], {}])
def test_a2a_metered_approval_requires_exact_boolean_true(approval: object) -> None:
    error = _validate_capacity_request(
        "api",
        1.0,
        {"allow_metered_api": approval, "confirm_metered_cost": True},
    )

    assert error is not None
    assert error["error_code"] == "METERED_API_NOT_APPROVED"


def test_a2a_metered_approval_accepts_exact_boolean_true() -> None:
    metadata = {"allow_metered_api": True, "confirm_metered_cost": True}
    assert _validate_capacity_request("api", 1.0, metadata) is None


@pytest.mark.parametrize("confirmation", [None, False, "true", 1, [], {}])
def test_a2a_metered_cost_confirmation_requires_exact_boolean_true(confirmation: object) -> None:
    metadata = {"allow_metered_api": True, "confirm_metered_cost": confirmation}

    error = _validate_capacity_request("api", 1.0, metadata)

    assert error is not None
    assert error["error_code"] == "METERED_API_NOT_APPROVED"


@pytest.mark.parametrize("max_experts", [float("inf"), float("-inf"), float("nan"), True, 0, 11, 1.5, "3"])
async def test_a2a_invalid_max_experts_returns_structured_error_before_work(monkeypatch, max_experts: object) -> None:
    called = False

    async def fail_if_called(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("consult work must not start for invalid max_experts")

    monkeypatch.setattr("deepr.a2a.consult_tasks.consult_experts_tool", fail_if_called)
    request = SimpleNamespace(
        metadata={"synthesis_backend": "local", "max_experts": max_experts},
        budget=0.0,
        input="q",
    )

    result = await run_consult_task(request)

    assert result.ok is False
    assert result.error is not None
    assert result.error["error_code"] == "INVALID_MAX_EXPERTS"
    assert result.error["retryable"] is False
    assert called is False


@pytest.mark.parametrize("metadata", [None, "local", [], 1, True])
async def test_a2a_rejects_non_object_metadata_before_work(monkeypatch, metadata: object) -> None:
    called = False

    async def fail_if_called(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("consult work must not start for malformed metadata")

    monkeypatch.setattr("deepr.a2a.consult_tasks.consult_experts_tool", fail_if_called)
    request = SimpleNamespace(metadata=metadata, budget=0.0, input="q")

    result = await run_consult_task(request)

    assert result.ok is False
    assert result.error is not None
    assert result.error["error_code"] == "INVALID_METADATA"
    assert result.error["retryable"] is False
    assert called is False


@pytest.mark.parametrize(
    "experts",
    ["Expert A", ["Expert A", 2], [""], ["   "], [f"Expert {index}" for index in range(11)]],
)
async def test_a2a_rejects_malformed_expert_rosters_before_work(monkeypatch, experts: object) -> None:
    called = False

    async def fail_if_called(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("consult work must not start for a malformed roster")

    monkeypatch.setattr("deepr.a2a.consult_tasks.consult_experts_tool", fail_if_called)
    request = SimpleNamespace(
        metadata={"synthesis_backend": "local", "experts": experts},
        budget=0.0,
        input="q",
    )

    result = await run_consult_task(request)

    assert result.ok is False
    assert result.error is not None
    assert result.error["error_code"] == "INVALID_EXPERT_LIMIT"
    assert result.error["retryable"] is False
    assert called is False


@pytest.mark.parametrize(
    "metadata",
    [
        {"synthesis_backend": {}},
        {"synthesis_backend": "local", "local_model": {}},
        {"synthesis_backend": "plan", "plan": {}},
        {"synthesis_backend": "plan", "plan": "codex", "plan_model": []},
    ],
)
async def test_a2a_rejects_non_string_backend_fields_before_work(monkeypatch, metadata: dict[str, object]) -> None:
    called = False

    async def fail_if_called(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("consult work must not start for malformed backend metadata")

    monkeypatch.setattr("deepr.a2a.consult_tasks.consult_experts_tool", fail_if_called)
    request = SimpleNamespace(metadata=metadata, budget=0.0, input="q")

    result = await run_consult_task(request)

    assert result.ok is False
    assert result.error is not None
    assert result.error["error_code"] == "INVALID_BACKEND"
    assert result.error["retryable"] is False
    assert called is False
