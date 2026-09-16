"""OpenRouter current-key evidence authorizes a hard stop without a billing import."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deepr.observability import provider_account_controls as account_controls_module
from deepr.observability.provider_account_controls import (
    PaidApiAccountEvidence,
    ProviderAccountBinding,
    ProviderAccountControlError,
    ProviderAccountEvidenceStore,
    verify_paid_api_authorization,
)

_PRODUCTION_SOURCE_VERIFIER = account_controls_module._verify_authenticated_account_evidence_source
_PRODUCTION_BINDING_RESOLVER = account_controls_module._resolve_current_provider_account_binding
from deepr.providers.openrouter_account_controls import (
    OpenRouterAccountControlError,
    account_credential_fingerprint,
    authorize_openrouter_paid_api,
    binding_from_observation,
    build_openrouter_account_evidence,
    openrouter_account_id,
)
from deepr.providers.openrouter_key_controls import OpenRouterKeyControlObservation

_SCRYPT = "scrypt:" + "ab" * 32
_SOURCE = "a" * 64
_ACCOUNT_REF = "b" * 64
_OBSERVED = datetime(2026, 9, 15, 12, tzinfo=UTC)


def _observation(*, eligible: bool = True, limit: float | None = 20.0) -> OpenRouterKeyControlObservation:
    return OpenRouterKeyControlObservation(
        control_eligible=eligible,
        failures=() if eligible else ("current key limit $20.000000 exceeds Deepr maximum $5.000000",),
        account_ref_sha256=_ACCOUNT_REF,
        key_label_sha256="c" * 64,
        credential_fingerprint=_SCRYPT,
        required_headroom_usd=0.01,
        maximum_monthly_limit_usd=20.0,
        limit_usd=limit,
        limit_remaining_usd=20.0 if limit is not None else None,
        usage_usd=0.0,
        usage_monthly_usd=0.0,
        byok_usage_usd=0.0,
        byok_usage_monthly_usd=0.0,
        limit_reset=None,
        include_byok_in_limit=True,
        expires_at=None,
        observed_at=_OBSERVED.isoformat(),
        source_sha256=_SOURCE,
    )


def test_fingerprint_and_account_id_are_bounded_and_stable() -> None:
    assert account_credential_fingerprint(_SCRYPT).startswith("sha256:")
    assert openrouter_account_id(_ACCOUNT_REF) == f"or-{_ACCOUNT_REF[:32]}"
    binding = binding_from_observation(_observation())
    assert binding.provider == "openrouter"
    assert binding.scope_ref == "openrouter-current-key"


def test_ineligible_key_cannot_become_account_evidence() -> None:
    with pytest.raises(OpenRouterAccountControlError, match="not control-eligible"):
        build_openrouter_account_evidence(
            _observation(eligible=False),
            freeze_id="freeze-1",
            freeze_frozen_at=_OBSERVED,
            hard_limit_usd=20.0,
        )


def _restore_production_openrouter_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        account_controls_module, "_verify_authenticated_account_evidence_source", _PRODUCTION_SOURCE_VERIFIER
    )
    monkeypatch.setattr(
        account_controls_module, "_resolve_current_provider_account_binding", _PRODUCTION_BINDING_RESOLVER
    )


def test_openrouter_key_evidence_authorizes_without_a_billing_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _restore_production_openrouter_controls(monkeypatch)
    monkeypatch.setenv("DEEPR_MAX_SPEND_CEILING_USD", "20")
    observation = _observation()
    monkeypatch.setattr(
        "deepr.providers.openrouter_account_controls.inspect_current_openrouter_key",
        lambda **kwargs: observation,
    )
    evidence_id, authorization = authorize_openrouter_paid_api(
        freeze_id="freeze-openrouter",
        freeze_frozen_at=_OBSERVED,
        monthly_limit_usd=20.0,
        store_root=tmp_path / "store",
        now=_OBSERVED + timedelta(minutes=1),
    )
    assert authorization.providers == ("openrouter",)
    assert authorization.hard_monthly_limit_usd == 20.0
    assert authorization.evidence_ids == (evidence_id,)
    stored = ProviderAccountEvidenceStore(tmp_path / "store").load(evidence_id)
    assert stored.billing_reconciliation_sha256 == stored.source_evidence_sha256 == _SOURCE
    assert stored.overage_enabled is False


def test_mismatched_openrouter_identity_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _restore_production_openrouter_controls(monkeypatch)
    monkeypatch.setenv("DEEPR_MAX_SPEND_CEILING_USD", "20")
    observation = _observation()
    evidence = build_openrouter_account_evidence(
        observation,
        freeze_id="freeze-openrouter",
        freeze_frozen_at=_OBSERVED,
        hard_limit_usd=20.0,
        now=_OBSERVED,
    )
    store = ProviderAccountEvidenceStore(tmp_path / "store")
    evidence_id, _path = store.store(evidence)
    other = replace(observation, account_ref_sha256="d" * 64)
    monkeypatch.setattr(
        "deepr.providers.openrouter_account_controls.inspect_current_openrouter_key",
        lambda **kwargs: other,
    )
    with pytest.raises(ProviderAccountControlError, match="does not match"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-openrouter",
            expected_frozen_at=_OBSERVED,
            monthly_limit_usd=20.0,
            requested_provider="openrouter",
            store_root=tmp_path / "store",
            now=_OBSERVED + timedelta(minutes=1),
        )


def test_openai_evidence_still_requires_a_generic_verifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _restore_production_openrouter_controls(monkeypatch)
    evidence = PaidApiAccountEvidence(
        schema_version="deepr-paid-api-account-evidence-v1",
        kind="deepr.costs.paid_api_account_evidence",
        provider="openai",
        account_id="test-openai-account",
        scope_ref="test-openai-scope",
        credential_fingerprint="sha256:" + "3" * 64,
        freeze_id="freeze-current",
        freeze_frozen_at=_OBSERVED.isoformat(),
        observed_at=_OBSERVED.isoformat(),
        valid_until=(_OBSERVED + timedelta(hours=1)).isoformat(),
        source_posture="provider_api",
        source_evidence_sha256="1" * 64,
        billing_reconciliation_sha256="2" * 64,
        control_mode="hard_monthly_limit",
        currency="USD",
        overage_enabled=False,
        hard_monthly_limit_usd="5.00",
    )
    store = ProviderAccountEvidenceStore(tmp_path / "store")
    evidence_id, _path = store.store(evidence)
    with pytest.raises(ProviderAccountControlError, match="no authenticated provider-specific"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=_OBSERVED,
            monthly_limit_usd=5.0,
            requested_provider="openai",
            store_root=tmp_path / "store",
            now=_OBSERVED + timedelta(minutes=1),
        )


def test_binding_type_roundtrip() -> None:
    binding = binding_from_observation(_observation())
    assert isinstance(binding, ProviderAccountBinding)
    assert binding.account_id.startswith("or-")
