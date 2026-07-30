"""Immutable, provider-bound account controls for paid API authorization.

Posture labels and local hashes are not proof. Production authorization stays
blocked until provider-specific authenticated evidence and credential identity
resolvers are implemented.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError, field_validator, model_validator

from deepr.observability.cost_ledger import default_cost_data_dir
from deepr.utils.atomic_io import atomic_write_bytes

PAID_API_ACCOUNT_EVIDENCE_SCHEMA_VERSION: Literal["deepr-paid-api-account-evidence-v1"] = (
    "deepr-paid-api-account-evidence-v1"
)
PAID_API_ACCOUNT_EVIDENCE_KIND: Literal["deepr.costs.paid_api_account_evidence"] = (
    "deepr.costs.paid_api_account_evidence"
)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,199}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_FINGERPRINT_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
_MONEY_PATTERN = re.compile(r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$")
_MAX_ACCOUNT_EVIDENCE_TTL = timedelta(hours=24)
_MAX_CLOCK_SKEW = timedelta(minutes=5)
_MAX_EVIDENCE_BYTES = 64 * 1024
_MAX_RECONCILIATION_BYTES = 5 * 1024 * 1024


class ProviderAccountControlError(RuntimeError):
    """Account-control evidence cannot safely authorize paid dispatch."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _identifier(value: str, *, field_name: str) -> str:
    if _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a bounded opaque identifier")
    return value


def _provider(value: str) -> str:
    return _identifier(value.strip().casefold(), field_name="provider")


def _utc(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a timezone-aware UTC timestamp") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{field_name} must be a timezone-aware UTC timestamp")
    return parsed.astimezone(UTC)


def _money(value: str, *, field_name: str) -> Decimal:
    if _MONEY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a positive decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the pattern
        raise ValueError(f"{field_name} must be a finite decimal string") from exc


def _canonical_bytes(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProviderAccountControlError("account-control evidence contains a duplicate object key")
        result[key] = value
    return result


def _safe_validation_message(exc: ValidationError) -> str:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    locations = [".".join(str(part) for part in error.get("loc", ())) or "document" for error in errors[:8]]
    return "account-control evidence failed validation at " + "; ".join(locations)


class PaidApiAccountEvidence(_StrictModel):
    """Content-addressed observation of one provider billing account."""

    schema_version: Literal["deepr-paid-api-account-evidence-v1"]
    kind: Literal["deepr.costs.paid_api_account_evidence"]
    provider: StrictStr
    account_id: StrictStr
    scope_ref: StrictStr
    credential_fingerprint: StrictStr
    freeze_id: StrictStr
    freeze_frozen_at: StrictStr
    observed_at: StrictStr
    valid_until: StrictStr
    source_posture: Literal["provider_api", "cryptographically_verified_provider_export"]
    source_evidence_sha256: StrictStr
    billing_reconciliation_sha256: StrictStr
    control_mode: Literal["hard_monthly_limit", "prepaid_no_overage"]
    currency: Literal["USD"]
    overage_enabled: Literal[False]
    hard_monthly_limit_usd: StrictStr

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        return _provider(value)

    @field_validator("account_id", "scope_ref", "freeze_id")
    @classmethod
    def validate_bindings(cls, value: str, info: Any) -> str:
        return _identifier(value, field_name=str(info.field_name))

    @field_validator("credential_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        if _FINGERPRINT_PATTERN.fullmatch(value) is None:
            raise ValueError("credential_fingerprint must be an external SHA-256 fingerprint")
        return value

    @field_validator("source_evidence_sha256", "billing_reconciliation_sha256")
    @classmethod
    def validate_source_digest(cls, value: str, info: Any) -> str:
        if _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError(f"{info.field_name} must be a lowercase SHA-256 value")
        return value

    @field_validator("hard_monthly_limit_usd")
    @classmethod
    def validate_hard_limit(cls, value: str) -> str:
        if _money(value, field_name="hard_monthly_limit_usd") <= 0:
            raise ValueError("hard_monthly_limit_usd must be positive")
        return value

    @model_validator(mode="after")
    def validate_observation_window(self) -> PaidApiAccountEvidence:
        frozen_at = _utc(self.freeze_frozen_at, field_name="freeze_frozen_at")
        observed_at = _utc(self.observed_at, field_name="observed_at")
        valid_until = _utc(self.valid_until, field_name="valid_until")
        if observed_at < frozen_at:
            raise ValueError("observed_at must be at or after freeze_frozen_at")
        if valid_until <= observed_at:
            raise ValueError("valid_until must be after observed_at")
        if valid_until - observed_at > _MAX_ACCOUNT_EVIDENCE_TTL:
            raise ValueError("account-control evidence validity exceeds the 24 hour maximum")
        return self


@dataclass(frozen=True)
class ProviderAccountBinding:
    """Current provider identity resolved from the credential in use."""

    provider: str
    account_id: str
    scope_ref: str
    credential_fingerprint: str


@dataclass(frozen=True)
class VerifiedPaidApiAuthorization:
    """Aggregate paid authority derived only from authenticated evidence."""

    evidence_ids: tuple[str, ...]
    recovered_freeze_id: str
    valid_until: datetime
    providers: tuple[str, ...]
    bindings: tuple[ProviderAccountBinding, ...]
    hard_monthly_limit_usd: float


def _verify_authenticated_account_evidence_source(evidence: PaidApiAccountEvidence) -> None:
    """Authenticate a provider API response or a signed provider export."""
    del evidence
    raise ProviderAccountControlError(
        "no authenticated provider-specific account-control evidence verifier is installed"
    )


def _resolve_current_provider_account_binding(provider: str) -> ProviderAccountBinding:
    """Resolve account, scope, and credential identity for the active client."""
    del provider
    raise ProviderAccountControlError("no provider-specific account and credential identity resolver is installed")


class ProviderAccountEvidenceStore:
    """Immutable content-addressed storage for account-control evidence."""

    def __init__(self, root: Path | None = None) -> None:
        target = root or default_cost_data_dir() / "provider_billing"
        if not target.is_absolute():
            raise ProviderAccountControlError("account-control evidence root must be an absolute path")
        self.root = target

    @staticmethod
    def _store_once(path: Path, payload: bytes) -> None:
        if path.exists():
            try:
                if path.read_bytes() == payload:
                    return
            except OSError as exc:
                raise ProviderAccountControlError("existing account-control evidence is unreadable") from exc
            raise ProviderAccountControlError("immutable account-control evidence path contains different content")
        try:
            atomic_write_bytes(path, payload, fsync=True, overwrite=False)
        except FileExistsError:
            try:
                if path.read_bytes() == payload:
                    return
            except OSError as exc:
                raise ProviderAccountControlError("account-control evidence replay could not be verified") from exc
            raise ProviderAccountControlError("immutable account-control evidence changed during creation") from None
        except OSError as exc:
            raise ProviderAccountControlError("account-control evidence could not be persisted durably") from exc

    def store(self, evidence: PaidApiAccountEvidence) -> tuple[str, Path]:
        """Persist canonical evidence without treating it as authenticated."""
        payload = _canonical_bytes(evidence)
        evidence_id = hashlib.sha256(payload).hexdigest()
        evidence_path = self.root / "account_evidence" / f"{evidence_id}.json"
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.root / ".lock"), timeout=10.0, thread_local=False):
            self._store_once(evidence_path, payload + b"\n")
        return evidence_id, evidence_path

    def load(self, evidence_id: str) -> PaidApiAccountEvidence:
        """Load evidence only when its canonical content address matches."""
        if _SHA256_PATTERN.fullmatch(evidence_id) is None:
            raise ProviderAccountControlError("account-control evidence ID must be a lowercase SHA-256 value")
        path = self.root / "account_evidence" / f"{evidence_id}.json"
        try:
            if path.stat().st_size > _MAX_EVIDENCE_BYTES:
                raise ProviderAccountControlError("account-control evidence exceeds the 64 KiB limit")
            raw = path.read_bytes()
            parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_guard)
        except ProviderAccountControlError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderAccountControlError("account-control evidence is missing or unreadable") from exc
        try:
            evidence = PaidApiAccountEvidence.model_validate(parsed)
        except ValidationError as exc:
            raise ProviderAccountControlError(_safe_validation_message(exc)) from exc
        canonical = _canonical_bytes(evidence)
        if raw != canonical + b"\n" or hashlib.sha256(canonical).hexdigest() != evidence_id:
            raise ProviderAccountControlError("account-control evidence content address does not match")
        return evidence

    def load_reconciliation(self, reconciliation_id: str) -> Any:
        """Load a stored reconciliation by exact canonical content digest."""
        if _SHA256_PATTERN.fullmatch(reconciliation_id) is None:
            raise ProviderAccountControlError("billing reconciliation ID must be a lowercase SHA-256 value")
        path = self.root / "reconciliations_by_hash" / f"{reconciliation_id}.json"
        try:
            if path.stat().st_size > _MAX_RECONCILIATION_BYTES:
                raise ProviderAccountControlError("billing reconciliation exceeds the 5 MiB limit")
            raw = path.read_bytes()
            parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_guard)
        except ProviderAccountControlError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderAccountControlError("billing reconciliation evidence is missing or unreadable") from exc
        from deepr.observability.provider_billing import BillingReconciliation

        try:
            report = BillingReconciliation.model_validate(parsed)
        except ValidationError as exc:
            raise ProviderAccountControlError(_safe_validation_message(exc)) from exc
        canonical = _canonical_bytes(report)
        if raw != canonical + b"\n" or hashlib.sha256(canonical).hexdigest() != reconciliation_id:
            raise ProviderAccountControlError("billing reconciliation content address does not match")
        return report

    def load_reconciled_import(self, report: Any) -> Any:
        """Load the exact normalized import that a reconciliation claims to use."""
        path = self.root / "imports" / f"{report.source_sha256}.json"
        try:
            if path.stat().st_size > _MAX_RECONCILIATION_BYTES:
                raise ProviderAccountControlError("normalized billing import exceeds the 5 MiB limit")
            raw = path.read_bytes()
            parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_guard)
        except ProviderAccountControlError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderAccountControlError("normalized billing import is missing or unreadable") from exc
        from deepr.observability.provider_billing import LoadedBillingImport, ProviderBillingImport

        try:
            document = ProviderBillingImport.model_validate(parsed)
        except ValidationError as exc:
            raise ProviderAccountControlError(_safe_validation_message(exc)) from exc
        canonical = _canonical_bytes(document)
        normalized_sha256 = hashlib.sha256(canonical).hexdigest()
        if raw != canonical + b"\n" or normalized_sha256 != report.normalized_sha256:
            raise ProviderAccountControlError("normalized billing import does not bind the reconciliation")
        return LoadedBillingImport(
            document=document,
            source_sha256=report.source_sha256,
            normalized_sha256=normalized_sha256,
            normalized_bytes=canonical,
        )


def _validated_monthly_limit(value: float) -> Decimal:
    if isinstance(value, bool):
        raise ProviderAccountControlError("monthly_limit_usd must be a finite positive amount")
    try:
        limit = _money(str(value), field_name="monthly_limit_usd")
    except ValueError as exc:
        raise ProviderAccountControlError("monthly_limit_usd must be a finite positive amount") from exc
    if limit <= 0:
        raise ProviderAccountControlError("monthly_limit_usd must be a finite positive amount")
    return limit


def _validated_current_time(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ProviderAccountControlError("authorization clock must be timezone-aware")
    return current.astimezone(UTC)


def _validated_expected_frozen_at(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProviderAccountControlError("expected_frozen_at must be timezone-aware")
    return value.astimezone(UTC)


def _validate_evidence_window(
    evidence: PaidApiAccountEvidence,
    *,
    expected_freeze_id: str,
    expected_frozen_at: datetime,
    current: datetime,
    monthly_limit: Decimal,
) -> tuple[datetime, Decimal]:
    if evidence.freeze_id != expected_freeze_id:
        raise ProviderAccountControlError("account-control evidence does not bind the current freeze ID")
    evidence_frozen_at = _utc(evidence.freeze_frozen_at, field_name="freeze_frozen_at")
    if evidence_frozen_at != expected_frozen_at:
        raise ProviderAccountControlError("account-control evidence does not bind the current frozen_at value")
    observed_at = _utc(evidence.observed_at, field_name="observed_at")
    valid_until = _utc(evidence.valid_until, field_name="valid_until")
    if observed_at < expected_frozen_at:
        raise ProviderAccountControlError("account-control evidence predates the current freeze")
    if observed_at > current + _MAX_CLOCK_SKEW:
        raise ProviderAccountControlError("account-control evidence observation is in the future")
    if valid_until <= current:
        raise ProviderAccountControlError("account-control evidence has expired")
    hard_limit = _money(evidence.hard_monthly_limit_usd, field_name="hard_monthly_limit_usd")
    if hard_limit > monthly_limit:
        raise ProviderAccountControlError("provider account hard monthly limit exceeds the operator monthly budget")
    return valid_until, hard_limit


def _validated_current_binding(provider: str, evidence: PaidApiAccountEvidence) -> ProviderAccountBinding:
    binding = _resolve_current_provider_account_binding(provider)
    try:
        normalized = ProviderAccountBinding(
            provider=_provider(binding.provider),
            account_id=_identifier(binding.account_id, field_name="account_id"),
            scope_ref=_identifier(binding.scope_ref, field_name="scope_ref"),
            credential_fingerprint=binding.credential_fingerprint,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProviderAccountControlError("provider account identity resolver returned an invalid binding") from exc
    if _FINGERPRINT_PATTERN.fullmatch(normalized.credential_fingerprint) is None:
        raise ProviderAccountControlError(
            "provider account identity resolver returned an invalid credential fingerprint"
        )
    expected = ProviderAccountBinding(
        provider=evidence.provider,
        account_id=evidence.account_id,
        scope_ref=evidence.scope_ref,
        credential_fingerprint=evidence.credential_fingerprint,
    )
    if normalized != expected:
        raise ProviderAccountControlError(
            "current provider account, scope, or credential fingerprint does not match account-control evidence"
        )
    return normalized


def _strict_current_ledger_snapshot() -> Any:
    from deepr.observability.cost_ledger import CostLedger
    from deepr.observability.provider_billing import locked_ledger_snapshot

    try:
        return locked_ledger_snapshot(CostLedger())
    except Exception as exc:
        raise ProviderAccountControlError("current strict ledger snapshot is unavailable") from exc


def _validate_clean_reconciliation(
    evidence: PaidApiAccountEvidence,
    report: Any,
    *,
    current_snapshot: Any | None,
) -> None:
    expected_posture = "provider_api" if evidence.source_posture == "provider_api" else "provider_export"
    if (
        report.status != "clean"
        or report.freeze_required
        or report.statement_status != "final"
        or report.statement_complete is not True
        or report.currency != "USD"
    ):
        raise ProviderAccountControlError("billing reconciliation is not final, complete, clean USD evidence")
    if (
        report.provider != evidence.provider
        or report.account_id != evidence.account_id
        or report.scope_ref != evidence.scope_ref
    ):
        raise ProviderAccountControlError("billing reconciliation account binding does not match account evidence")
    if report.statement_source_posture != expected_posture or report.source_sha256 != evidence.source_evidence_sha256:
        raise ProviderAccountControlError("billing reconciliation does not bind the authenticated provider source")
    period_start = _utc(report.period_start, field_name="period_start")
    period_end = _utc(report.period_end, field_name="period_end")
    observed_at = _utc(evidence.observed_at, field_name="observed_at")
    if not period_start <= observed_at <= period_end:
        raise ProviderAccountControlError("billing reconciliation statement is stale for account recovery")
    if current_snapshot is None:
        return
    if report.ledger_snapshot_sha256 != current_snapshot.sha256:
        raise ProviderAccountControlError("billing reconciliation no longer binds the current strict ledger snapshot")
    uncovered = any(
        event.provider.strip().casefold() == evidence.provider
        and event.cost_usd > 0
        and event.timestamp <= observed_at
        and not period_start <= event.timestamp <= period_end
        for event in current_snapshot.events
    )
    if uncovered:
        raise ProviderAccountControlError(
            "billing reconciliation period does not cover every positive local provider event through observed_at"
        )


def verify_paid_api_authorization(
    evidence_ids: tuple[str, ...] | list[str],
    *,
    expected_freeze_id: str,
    expected_frozen_at: datetime,
    monthly_limit_usd: float,
    requested_provider: str | None = None,
    store_root: Path | None = None,
    now: datetime | None = None,
) -> VerifiedPaidApiAuthorization:
    """Derive paid authority from fresh, authenticated, exactly bound evidence."""
    identifiers = tuple(evidence_ids)
    if not 1 <= len(identifiers) <= 32 or len(set(identifiers)) != len(identifiers):
        raise ProviderAccountControlError("account-control evidence IDs must be a unique non-empty list")
    if any(_SHA256_PATTERN.fullmatch(identifier) is None for identifier in identifiers):
        raise ProviderAccountControlError("account-control evidence IDs must be lowercase SHA-256 values")
    try:
        _identifier(expected_freeze_id, field_name="expected_freeze_id")
        provider = _provider(requested_provider) if requested_provider is not None else None
    except ValueError as exc:
        raise ProviderAccountControlError(str(exc)) from exc
    frozen_at = _validated_expected_frozen_at(expected_frozen_at)
    current = _validated_current_time(now)
    monthly_limit = _validated_monthly_limit(monthly_limit_usd)
    evidence_by_provider: dict[str, PaidApiAccountEvidence] = {}
    valid_until_values: list[datetime] = []
    hard_limits: list[Decimal] = []
    store = ProviderAccountEvidenceStore(store_root)
    current_snapshot = _strict_current_ledger_snapshot() if provider is None else None
    for evidence_id in identifiers:
        evidence = store.load(evidence_id)
        _verify_authenticated_account_evidence_source(evidence)
        if evidence.provider in evidence_by_provider:
            raise ProviderAccountControlError("account-control evidence has an ambiguous provider binding")
        valid_until, hard_limit = _validate_evidence_window(
            evidence,
            expected_freeze_id=expected_freeze_id,
            expected_frozen_at=frozen_at,
            current=current,
            monthly_limit=monthly_limit,
        )
        reconciliation = store.load_reconciliation(evidence.billing_reconciliation_sha256)
        _validate_clean_reconciliation(evidence, reconciliation, current_snapshot=current_snapshot)
        loaded = store.load_reconciled_import(reconciliation)
        if current_snapshot is not None:
            from deepr.observability.provider_billing import reconcile_billing

            recomputed = reconcile_billing(loaded, current_snapshot)
            if _canonical_bytes(recomputed) != _canonical_bytes(reconciliation):
                raise ProviderAccountControlError(
                    "billing reconciliation clean status was not reproduced from immutable evidence"
                )
        evidence_by_provider[evidence.provider] = evidence
        valid_until_values.append(valid_until)
        hard_limits.append(hard_limit)
    if provider is not None and provider not in evidence_by_provider:
        raise ProviderAccountControlError("account-control evidence does not authorize the requested provider")
    ordered_evidence = tuple(sorted(evidence_by_provider.values(), key=lambda item: item.provider))
    providers_to_validate = ordered_evidence if provider is None else (evidence_by_provider[provider],)
    for evidence in providers_to_validate:
        _validated_current_binding(evidence.provider, evidence)
    bindings = tuple(
        ProviderAccountBinding(
            provider=evidence.provider,
            account_id=evidence.account_id,
            scope_ref=evidence.scope_ref,
            credential_fingerprint=evidence.credential_fingerprint,
        )
        for evidence in ordered_evidence
    )
    return VerifiedPaidApiAuthorization(
        evidence_ids=identifiers,
        recovered_freeze_id=expected_freeze_id,
        valid_until=min(valid_until_values),
        providers=tuple(evidence.provider for evidence in ordered_evidence),
        bindings=bindings,
        hard_monthly_limit_usd=float(min(hard_limits)),
    )


__all__ = [
    "PAID_API_ACCOUNT_EVIDENCE_KIND",
    "PAID_API_ACCOUNT_EVIDENCE_SCHEMA_VERSION",
    "PaidApiAccountEvidence",
    "ProviderAccountBinding",
    "ProviderAccountControlError",
    "ProviderAccountEvidenceStore",
    "VerifiedPaidApiAuthorization",
    "verify_paid_api_authorization",
]
