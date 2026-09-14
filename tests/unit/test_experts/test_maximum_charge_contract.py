"""Tests for the offline maximum-charge contract (P1 metered re-enable substrate)."""

from __future__ import annotations

import pytest

from deepr.experts.chat_capacity import (
    MAXIMUM_CHARGE_CONTRACT_RUNTIME_PROVEN,
    METERED_EXPERT_CHAT_EXECUTION_ENABLED,
    MeteredExpertChatDisabledError,
    expert_chat_capacity,
)
from deepr.experts.chat_metered import execute_metered_chat_provider_call
from deepr.experts.maximum_charge_contract import (
    ABSOLUTE_DEEPR_CEILING_USD,
    DEEPR_MAX_SPEND_CEILING_ENV,
    MAX_RAISED_CEILING_USD,
    MaximumChargeContractError,
    absolute_deepr_ceiling_usd,
    evaluate_maximum_charge_contract,
    incomplete_contract_summary,
    require_complete_maximum_charge_contract,
)


def _complete_envelope(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "parent_ceiling_usd": 1.0,
        "provider": "openai",
        "model": "gpt-5-mini",
        "endpoint": "https://api.openai.com/v1",
        "account_scope": "org_test",
        "credential_fingerprint": "cred-fingerprint-test",
        "request_digest": "sha256:deadbeef",
        "input_tokens": 1_000,
        "output_tokens": 500,
        "reasoning_tokens": 0,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
        "tool_usd": 0.0,
        "hosted_storage_usd": 0.0,
        "background_jobs_usd": 0.0,
        "transport_surcharge_usd": 0.0,
        "fallback_usd": 0.0,
        "retries_disabled": True,
        "redirects_disabled": True,
        "deepr_owned_client": True,
        "official_endpoint_pinned": True,
        "injected_client_rejected": True,
        "overage_disabled": True,
    }
    base.update(overrides)
    return base


def test_release_flags_remain_fail_closed() -> None:
    assert METERED_EXPERT_CHAT_EXECUTION_ENABLED is False
    assert MAXIMUM_CHARGE_CONTRACT_RUNTIME_PROVEN is False


def test_incomplete_summary_lists_required_dimensions() -> None:
    summary = incomplete_contract_summary()
    assert summary["complete"] is False
    assert "input_tokens" in summary["required_token_dimensions"]
    assert "tool_usd" in summary["required_usd_dimensions"]
    assert summary["absolute_deepr_ceiling_usd"] == ABSOLUTE_DEEPR_CEILING_USD


def test_complete_envelope_evaluates_offline() -> None:
    verdict = evaluate_maximum_charge_contract(_complete_envelope())
    assert verdict.complete is True
    assert verdict.computed_max_usd is not None
    assert verdict.computed_max_usd > 0
    assert verdict.computed_max_usd <= 1.0
    assert "input_tokens" in verdict.priced_components
    require_complete_maximum_charge_contract(_complete_envelope())


def test_rejects_average_or_expected_only_authority() -> None:
    verdict = evaluate_maximum_charge_contract(_complete_envelope(expected_cost_usd=0.01, average_cost_usd=0.02))
    assert verdict.complete is False
    assert any("not spend authority" in item for item in verdict.failures)


def test_rejects_ceiling_above_absolute_deepr_limit() -> None:
    verdict = evaluate_maximum_charge_contract(_complete_envelope(parent_ceiling_usd=5.01))
    assert verdict.complete is False
    assert any("absolute Deepr ceiling" in item for item in verdict.failures)


def test_rejects_missing_posture_flags() -> None:
    verdict = evaluate_maximum_charge_contract(_complete_envelope(retries_disabled=False))
    assert verdict.complete is False
    assert any("retries_disabled" in item for item in verdict.failures)


def test_rejects_stringy_posture_flags() -> None:
    verdict = evaluate_maximum_charge_contract(_complete_envelope(retries_disabled="false"))  # type: ignore[arg-type]
    assert verdict.complete is False
    assert any("boolean" in item for item in verdict.failures)


def test_rejects_when_computed_max_exceeds_parent() -> None:
    # Tiny ceiling cannot cover 100k output tokens of gpt-5-mini.
    verdict = evaluate_maximum_charge_contract(_complete_envelope(parent_ceiling_usd=0.0001, output_tokens=100_000))
    assert verdict.complete is False
    assert any("exceeds parent_ceiling_usd" in item for item in verdict.failures)


def test_rejects_cache_tokens_without_usable_bound_when_unpriced() -> None:
    # Use a model alias that has token pricing but force cache traffic; gpt-5-mini
    # has cache pricing, so force an unknown model for the failure path.
    verdict = evaluate_maximum_charge_contract(_complete_envelope(model="not-a-real-model-xyz", cache_read_tokens=100))
    assert verdict.complete is False
    assert verdict.failures


def test_explicit_openrouter_cache_write_rate_is_not_underpriced() -> None:
    verdict = evaluate_maximum_charge_contract(
        _complete_envelope(
            provider="openrouter",
            model="anthropic/claude-sonnet-5",
            cache_write_tokens=1_000_000,
            parent_ceiling_usd=5.0,
        )
    )
    assert verdict.complete is True
    assert verdict.priced_components["cache_write_tokens"] == pytest.approx(4.0)


def test_require_raises_on_incomplete() -> None:
    with pytest.raises(MaximumChargeContractError):
        require_complete_maximum_charge_contract(_complete_envelope(deepr_owned_client=False))


@pytest.mark.asyncio
async def test_metered_chat_call_still_blocked_with_contract_payload() -> None:
    with pytest.raises(MeteredExpertChatDisabledError) as caught:
        await execute_metered_chat_provider_call(
            provider="openai",
            model="gpt-5-mini",
            source="test",
            max_cost_per_job=0.5,
            call=lambda: None,  # type: ignore[arg-type,return-value]
            request_envelope={"messages": []},
        )
    payload = caught.value.to_dict()
    assert payload["provider_work_dispatched"] is False
    assert payload["metered_chat_execution_enabled"] is False
    assert payload["maximum_charge_contract"]["complete"] is False
    assert "messages" in payload["maximum_charge_contract"]["request_envelope_keys"]


def test_expert_chat_capacity_exposes_contract_summary() -> None:
    class _Metered:
        metered = True

    capacity = expert_chat_capacity(_Metered())
    assert capacity["execution_enabled"] is False
    assert capacity["maximum_charge_contract_runtime_proven"] is False
    assert capacity["maximum_charge_contract"]["complete"] is False


class TestOperatorRaisableCeiling:
    """A cap the owner cannot raise is a wall, not a budget control."""

    def test_defaults_to_the_fail_closed_ceiling(self, monkeypatch):
        monkeypatch.delenv(DEEPR_MAX_SPEND_CEILING_ENV, raising=False)
        assert absolute_deepr_ceiling_usd() == ABSOLUTE_DEEPR_CEILING_USD

    def test_operator_can_authorize_more(self, monkeypatch):
        monkeypatch.setenv(DEEPR_MAX_SPEND_CEILING_ENV, "20")
        assert absolute_deepr_ceiling_usd() == 20.0

    def test_operator_can_authorize_less(self, monkeypatch):
        # Asking for less exposure must never be clamped back up to the default.
        monkeypatch.setenv(DEEPR_MAX_SPEND_CEILING_ENV, "1.50")
        assert absolute_deepr_ceiling_usd() == 1.50

    @pytest.mark.parametrize(
        "value",
        ["", "   ", "abc", "0", "-5", str(MAX_RAISED_CEILING_USD + 0.01), "1e9"],
        ids=["empty", "blank", "unparseable", "zero", "negative", "over-bound", "huge"],
    )
    def test_anything_unusable_falls_back_to_the_default(self, monkeypatch, value):
        monkeypatch.setenv(DEEPR_MAX_SPEND_CEILING_ENV, value)
        assert absolute_deepr_ceiling_usd() == ABSOLUTE_DEEPR_CEILING_USD

    def test_parent_transaction_honours_a_raised_ceiling(self, monkeypatch):
        from deepr.experts.parent_budget_transaction import (
            ParentBudgetError,
            open_parent_budget_transaction,
        )

        monkeypatch.delenv(DEEPR_MAX_SPEND_CEILING_ENV, raising=False)
        with pytest.raises(ParentBudgetError, match="exceeds absolute Deepr ceiling"):
            open_parent_budget_transaction(run_id="r1", parent_ceiling_usd=20.0, surface="api_expert_sync")

        monkeypatch.setenv(DEEPR_MAX_SPEND_CEILING_ENV, "20")
        txn = open_parent_budget_transaction(run_id="r2", parent_ceiling_usd=20.0, surface="api_expert_sync")
        assert txn.parent_ceiling_usd == 20.0

    def test_the_ceiling_in_force_is_reported_for_audit(self, monkeypatch):
        monkeypatch.setenv(DEEPR_MAX_SPEND_CEILING_ENV, "20")
        summary = incomplete_contract_summary()
        assert summary["absolute_deepr_ceiling_usd"] == 20.0
