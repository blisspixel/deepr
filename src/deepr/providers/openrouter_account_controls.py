"""OpenRouter current-key observation as provider hard-stop evidence.

A finite OpenRouter key limit is a provider-side stop: the key cannot spend
past remaining. The generic account-control gate requires a final billing
import, which cannot exist before the first Deepr spend. This module
authenticates the live GET /api/v1/key document instead and binds it to the
current freeze. It is not an inference client and does not authorize MCP,
schedules, or automatic fallback.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from deepr.config import default_data_dir
from deepr.experts.maximum_charge_contract import absolute_deepr_ceiling_usd
from deepr.observability.provider_account_controls import (
    PaidApiAccountEvidence,
    ProviderAccountBinding,
    ProviderAccountControlError,
    ProviderAccountEvidenceStore,
    VerifiedPaidApiAuthorization,
    verify_paid_api_authorization,
)
from deepr.providers.openrouter_key_controls import (
    OpenRouterKeyControlError,
    OpenRouterKeyControlObservation,
    inspect_openrouter_key,
)
from deepr.security.key_quarantine import QUARANTINE_PREFIX

_OPENROUTER_KEY_NAME = "OPENROUTER_API_KEY"
_SCOPE_REF = "openrouter-current-key"
_MIN_HEADROOM_USD = 0.01
_EVIDENCE_TTL = timedelta(hours=24)
_MAX_ENV_BYTES = 64 * 1024


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists() or path.stat().st_size > _MAX_ENV_BYTES:
        return {}
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", 1)
            entries[name.strip()] = value.strip()
    return entries


class OpenRouterAccountControlError(ProviderAccountControlError):
    """OpenRouter key observation cannot authorize paid dispatch."""


def load_openrouter_api_key() -> str:
    """Load the current OpenRouter credential without printing it."""
    process = os.environ.get(_OPENROUTER_KEY_NAME, "").strip()
    if process:
        return process
    quarantined = os.environ.get(QUARANTINE_PREFIX + _OPENROUTER_KEY_NAME, "").strip()
    if quarantined:
        return quarantined
    merged = dict(_parse_env_file(default_data_dir() / ".env"))
    merged.update(_parse_env_file(Path(".env")))
    return str(merged.get(_OPENROUTER_KEY_NAME, "")).strip()


def account_credential_fingerprint(scrypt_fingerprint: str) -> str:
    """Map the OpenRouter scrypt fingerprint onto the generic SHA-256 form."""
    if not scrypt_fingerprint.startswith("scrypt:") or len(scrypt_fingerprint) != 71:
        raise OpenRouterAccountControlError("OpenRouter credential fingerprint is invalid")
    digest = hashlib.sha256(scrypt_fingerprint.encode("ascii")).hexdigest()
    return f"sha256:{digest}"


def openrouter_account_id(account_ref_sha256: str) -> str:
    if len(account_ref_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in account_ref_sha256):
        raise OpenRouterAccountControlError("OpenRouter account reference is invalid")
    return f"or-{account_ref_sha256[:32]}"


def _usd_text(value: float) -> str:
    text = f"{value:.2f}"
    if text.startswith("-") or text == "0.00":
        raise OpenRouterAccountControlError("OpenRouter hard limit must be a positive USD amount")
    return text


def binding_from_observation(observation: OpenRouterKeyControlObservation) -> ProviderAccountBinding:
    return ProviderAccountBinding(
        provider="openrouter",
        account_id=openrouter_account_id(observation.account_ref_sha256),
        scope_ref=_SCOPE_REF,
        credential_fingerprint=account_credential_fingerprint(observation.credential_fingerprint),
    )


def inspect_current_openrouter_key(
    *, required_headroom_usd: float = _MIN_HEADROOM_USD
) -> OpenRouterKeyControlObservation:
    api_key = load_openrouter_api_key()
    if not api_key:
        raise OpenRouterAccountControlError("OPENROUTER_API_KEY is not available")
    try:
        return inspect_openrouter_key(api_key, required_headroom_usd=required_headroom_usd)
    except OpenRouterKeyControlError as exc:
        raise OpenRouterAccountControlError(str(exc)) from exc


def resolve_openrouter_account_binding() -> ProviderAccountBinding:
    """Resolve the live OpenRouter account identity from the current key."""
    return binding_from_observation(inspect_current_openrouter_key())


def verify_openrouter_account_evidence_source(evidence: PaidApiAccountEvidence) -> None:
    """Re-fetch the current key and require it still matches stored evidence."""
    if evidence.provider != "openrouter" or evidence.source_posture != "provider_api":
        raise OpenRouterAccountControlError("OpenRouter account evidence has an invalid source posture")
    if evidence.overage_enabled is not False:
        raise OpenRouterAccountControlError("OpenRouter account evidence must disable overage")
    if evidence.control_mode != "hard_monthly_limit":
        raise OpenRouterAccountControlError("OpenRouter account evidence must use a hard key limit")
    observation = inspect_current_openrouter_key()
    if not observation.control_eligible:
        reason = "; ".join(observation.failures) or "current key is not control-eligible"
        raise OpenRouterAccountControlError(reason)
    expected = binding_from_observation(observation)
    actual = ProviderAccountBinding(
        provider=evidence.provider,
        account_id=evidence.account_id,
        scope_ref=evidence.scope_ref,
        credential_fingerprint=evidence.credential_fingerprint,
    )
    if expected != actual:
        raise OpenRouterAccountControlError(
            "current OpenRouter account, scope, or credential fingerprint does not match account-control evidence"
        )
    if observation.limit_usd is None or float(evidence.hard_monthly_limit_usd) - observation.limit_usd > 1e-6:
        raise OpenRouterAccountControlError("current OpenRouter key limit is below the stored hard limit")


def build_openrouter_account_evidence(
    observation: OpenRouterKeyControlObservation,
    *,
    freeze_id: str,
    freeze_frozen_at: datetime,
    hard_limit_usd: float,
    now: datetime | None = None,
) -> PaidApiAccountEvidence:
    """Build immutable evidence from one control-eligible current-key observation."""
    if not observation.control_eligible or observation.limit_usd is None:
        raise OpenRouterAccountControlError("OpenRouter key is not control-eligible")
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    frozen_at = freeze_frozen_at.astimezone(UTC)
    if observed < frozen_at:
        raise OpenRouterAccountControlError("OpenRouter key observation predates the current freeze")
    binding = binding_from_observation(observation)
    return PaidApiAccountEvidence(
        schema_version="deepr-paid-api-account-evidence-v1",
        kind="deepr.costs.paid_api_account_evidence",
        provider="openrouter",
        account_id=binding.account_id,
        scope_ref=binding.scope_ref,
        credential_fingerprint=binding.credential_fingerprint,
        freeze_id=freeze_id,
        freeze_frozen_at=frozen_at.isoformat(),
        observed_at=observed.isoformat(),
        valid_until=(observed + _EVIDENCE_TTL).isoformat(),
        source_posture="provider_api",
        source_evidence_sha256=observation.source_sha256,
        billing_reconciliation_sha256=observation.source_sha256,
        control_mode="hard_monthly_limit",
        currency="USD",
        overage_enabled=False,
        hard_monthly_limit_usd=_usd_text(hard_limit_usd),
    )


def authorize_openrouter_paid_api(
    *,
    freeze_id: str,
    freeze_frozen_at: datetime,
    monthly_limit_usd: float,
    store_root: Path | None = None,
    now: datetime | None = None,
) -> tuple[str, VerifiedPaidApiAuthorization]:
    """Store current-key evidence and verify OpenRouter-only paid authority."""
    ceiling = absolute_deepr_ceiling_usd()
    if monthly_limit_usd <= 0:
        raise OpenRouterAccountControlError("Set a positive monthly budget before authorizing OpenRouter")
    observation = inspect_current_openrouter_key()
    if not observation.control_eligible or observation.limit_usd is None:
        reason = "; ".join(observation.failures) or "current key is not control-eligible"
        raise OpenRouterAccountControlError(reason)
    hard_limit = min(float(observation.limit_usd), float(monthly_limit_usd), ceiling)
    if hard_limit <= 0:
        raise OpenRouterAccountControlError("OpenRouter hard limit resolved to zero")
    evidence = build_openrouter_account_evidence(
        observation,
        freeze_id=freeze_id,
        freeze_frozen_at=freeze_frozen_at,
        hard_limit_usd=hard_limit,
        now=now,
    )
    store = ProviderAccountEvidenceStore(store_root)
    evidence_id, _path = store.store(evidence)
    authorization = verify_paid_api_authorization(
        [evidence_id],
        expected_freeze_id=freeze_id,
        expected_frozen_at=freeze_frozen_at,
        monthly_limit_usd=monthly_limit_usd,
        requested_provider="openrouter",
        store_root=store_root,
        now=now,
    )
    return evidence_id, authorization


__all__ = [
    "OpenRouterAccountControlError",
    "account_credential_fingerprint",
    "authorize_openrouter_paid_api",
    "binding_from_observation",
    "build_openrouter_account_evidence",
    "inspect_current_openrouter_key",
    "load_openrouter_api_key",
    "openrouter_account_id",
    "resolve_openrouter_account_binding",
    "verify_openrouter_account_evidence_source",
]
