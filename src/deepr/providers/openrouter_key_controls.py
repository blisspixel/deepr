"""Authenticated, non-authorizing OpenRouter current-key inspection.

The endpoint is read-only and does not run a model. A successful observation
is still not paid dispatch authority because it is not a final billing
reconciliation and is not wired into Deepr's generic account-control gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

from deepr.experts.maximum_charge_contract import ABSOLUTE_DEEPR_CEILING_USD
from deepr.utils.pinned_http import close_pinned_response, pinned_get

OPENROUTER_KEY_CHECK_KIND = "deepr.providers.openrouter_key_control_observation"
OPENROUTER_KEY_CHECK_SCHEMA_VERSION = "deepr-openrouter-key-control-v2"
OPENROUTER_CURRENT_KEY_URL = "https://openrouter.ai/api/v1/key"

_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_KEY_BYTES = 512
_MAX_TEXT_BYTES = 512
_MONEY_TOLERANCE = 1e-6
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_CREDENTIAL_FINGERPRINT_PATTERN = re.compile(r"^scrypt:[a-f0-9]{64}$")
_CREDENTIAL_FINGERPRINT_SALT = b"deepr/openrouter/credential-fingerprint/v1"


class OpenRouterKeyControlError(RuntimeError):
    """The authenticated current-key observation could not be inspected."""


@dataclass(frozen=True)
class FetchedOpenRouterKeyDocument:
    """Authenticated response plus local binding to the credential used."""

    payload: object
    source_sha256: str
    credential_fingerprint: str
    observed_at: datetime


@dataclass(frozen=True)
class _ParsedOpenRouterKey:
    creator_user_id: str
    label: str
    include_byok: bool
    is_free_tier: bool
    is_management_key: bool
    is_provisioning_key: bool
    limit: float | None
    remaining: float | None
    usage: float
    usage_monthly: float
    byok_usage: float
    byok_usage_monthly: float
    limit_reset: str | None
    expires_at: str | None
    expiration_failure: str | None


@dataclass(frozen=True)
class OpenRouterKeyControlObservation:
    """Sanitized current-key limit and identity observation."""

    control_eligible: bool
    failures: tuple[str, ...]
    account_ref_sha256: str
    key_label_sha256: str
    credential_fingerprint: str
    required_headroom_usd: float
    maximum_monthly_limit_usd: float
    limit_usd: float | None
    limit_remaining_usd: float | None
    usage_usd: float | None
    usage_monthly_usd: float | None
    byok_usage_usd: float | None
    byok_usage_monthly_usd: float | None
    limit_reset: str | None
    include_byok_in_limit: bool | None
    expires_at: str | None
    observed_at: str
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OPENROUTER_KEY_CHECK_SCHEMA_VERSION,
            "kind": OPENROUTER_KEY_CHECK_KIND,
            "provider": "openrouter",
            "control_eligible": self.control_eligible,
            "failures": list(self.failures),
            "account_ref_sha256": self.account_ref_sha256,
            "key_label_sha256": self.key_label_sha256,
            "credential_fingerprint": self.credential_fingerprint,
            "required_headroom_usd": self.required_headroom_usd,
            "maximum_monthly_limit_usd": self.maximum_monthly_limit_usd,
            "limit_usd": self.limit_usd,
            "limit_remaining_usd": self.limit_remaining_usd,
            "usage_usd": self.usage_usd,
            "usage_monthly_usd": self.usage_monthly_usd,
            "byok_usage_usd": self.byok_usage_usd,
            "byok_usage_monthly_usd": self.byok_usage_monthly_usd,
            "limit_reset": self.limit_reset,
            "include_byok_in_limit": self.include_byok_in_limit,
            "expires_at": self.expires_at,
            "observed_at": self.observed_at,
            "source_sha256": self.source_sha256,
            "api_key_source": "caller_supplied",
            "inference_requests": 0,
            "paid_requests": 0,
            "billing_reconciliation_complete": False,
            "dispatch_authorized": False,
        }


def _credential_bytes(api_key: str) -> bytes:
    if not isinstance(api_key, str):
        raise OpenRouterKeyControlError("OpenRouter API key must be text from one explicit local secret source")
    try:
        encoded = api_key.encode("ascii")
    except UnicodeEncodeError as exc:
        raise OpenRouterKeyControlError("OpenRouter API key must be bounded ASCII text") from exc
    if (
        not api_key.startswith("sk-or-")
        or not 20 <= len(encoded) <= _MAX_KEY_BYTES
        or any(character.isspace() for character in api_key)
        or any(ord(character) < 33 or ord(character) > 126 for character in api_key)
    ):
        raise OpenRouterKeyControlError("OpenRouter API key has an invalid bounded format")
    return encoded


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OpenRouterKeyControlError("OpenRouter current-key response contains a duplicate object key")
        result[key] = value
    return result


def _read_bounded_body(response: requests.Response) -> bytes:
    declared_length = response.headers.get("Content-Length")
    if declared_length is not None:
        try:
            length = int(declared_length)
        except (TypeError, ValueError) as exc:
            raise OpenRouterKeyControlError("OpenRouter current-key response has an invalid Content-Length") from exc
        if length < 0 or length > _MAX_RESPONSE_BYTES:
            raise OpenRouterKeyControlError("OpenRouter current-key response exceeds the response byte ceiling")
    body = bytearray()
    for chunk in response.iter_content(chunk_size=16 * 1024):
        if not isinstance(chunk, bytes):
            raise OpenRouterKeyControlError("OpenRouter current-key response returned a non-byte response chunk")
        body.extend(chunk)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise OpenRouterKeyControlError("OpenRouter current-key response exceeds the response byte ceiling")
    return bytes(body)


def fetch_openrouter_current_key(api_key: str) -> FetchedOpenRouterKeyDocument:
    """Fetch current-key controls with the exact prompted credential."""
    credential = _credential_bytes(api_key)
    fingerprint = (
        "scrypt:"
        + hashlib.scrypt(
            credential,
            salt=_CREDENTIAL_FINGERPRINT_SALT,
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        ).hex()
    )
    try:
        response = pinned_get(
            OPENROUTER_CURRENT_KEY_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "deepr-openrouter-key-check/1",
            },
            timeout=(5.0, 15.0),
            allow_redirects=False,
            stream=True,
        )
    except (requests.RequestException, OSError) as exc:
        raise OpenRouterKeyControlError("OpenRouter current-key request failed") from exc
    try:
        if response.status_code != 200:
            raise OpenRouterKeyControlError(f"OpenRouter current-key endpoint returned HTTP {response.status_code}")
        content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().casefold()
        if content_type != "application/json":
            raise OpenRouterKeyControlError("OpenRouter current-key endpoint did not return application/json")
        raw = _read_bounded_body(response)
    finally:
        close_pinned_response(response)
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_guard)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenRouterKeyControlError("OpenRouter current-key response is not strict UTF-8 JSON") from exc
    return FetchedOpenRouterKeyDocument(
        payload=payload,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        credential_fingerprint=fingerprint,
        observed_at=datetime.now(UTC),
    )


def _mapping(value: object, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpenRouterKeyControlError(f"OpenRouter current-key {field_name} must be an object")
    return value


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise OpenRouterKeyControlError(f"OpenRouter current-key {field_name} must be bounded ASCII text")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise OpenRouterKeyControlError(f"OpenRouter current-key {field_name} must be bounded ASCII text") from exc
    if not encoded or len(encoded) > _MAX_TEXT_BYTES or any(byte < 32 or byte > 126 for byte in encoded):
        raise OpenRouterKeyControlError(f"OpenRouter current-key {field_name} must be bounded ASCII text")
    return value


def _optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name=field_name)


def _boolean(value: object, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise OpenRouterKeyControlError(f"OpenRouter current-key {field_name} must be a boolean")
    return value


def _money(value: object, *, field_name: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenRouterKeyControlError(f"OpenRouter current-key {field_name} must be finite USD")
    amount = float(value)
    if not math.isfinite(amount) or amount < 0 or (positive and amount <= 0):
        raise OpenRouterKeyControlError(f"OpenRouter current-key {field_name} must be finite USD")
    return amount


def _optional_money(value: object, *, field_name: str, positive: bool = False) -> float | None:
    if value is None:
        return None
    return _money(value, field_name=field_name, positive=positive)


def _utc_expiration(value: str | None, observed_at: datetime) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value, "current key expiration is not a timezone-aware UTC timestamp"
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        return value, "current key expiration is not a timezone-aware UTC timestamp"
    if parsed.astimezone(UTC) <= observed_at:
        return value, "current key has expired"
    return parsed.astimezone(UTC).isoformat(), None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _parse_key_data(document: FetchedOpenRouterKeyDocument) -> _ParsedOpenRouterKey:
    root = _mapping(document.payload, field_name="document")
    data = _mapping(root.get("data"), field_name="data")
    expires_at, expiration_failure = _utc_expiration(
        _optional_text(data.get("expires_at"), field_name="expires_at"),
        document.observed_at.astimezone(UTC),
    )
    return _ParsedOpenRouterKey(
        creator_user_id=_text(data.get("creator_user_id"), field_name="creator_user_id"),
        label=_text(data.get("label"), field_name="label"),
        include_byok=_boolean(data.get("include_byok_in_limit"), field_name="include_byok_in_limit"),
        is_free_tier=_boolean(data.get("is_free_tier"), field_name="is_free_tier"),
        is_management_key=_boolean(data.get("is_management_key"), field_name="is_management_key"),
        is_provisioning_key=_boolean(data.get("is_provisioning_key"), field_name="is_provisioning_key"),
        limit=_optional_money(data.get("limit"), field_name="limit", positive=True),
        remaining=_optional_money(data.get("limit_remaining"), field_name="limit_remaining"),
        usage=_money(data.get("usage"), field_name="usage"),
        usage_monthly=_money(data.get("usage_monthly"), field_name="usage_monthly"),
        byok_usage=_money(data.get("byok_usage"), field_name="byok_usage"),
        byok_usage_monthly=_money(data.get("byok_usage_monthly"), field_name="byok_usage_monthly"),
        limit_reset=_optional_text(data.get("limit_reset"), field_name="limit_reset"),
        expires_at=expires_at,
        expiration_failure=expiration_failure,
    )


def _invalid_key_observation(
    document: FetchedOpenRouterKeyDocument,
    *,
    required: float,
    maximum_limit: float,
    failure: str,
) -> OpenRouterKeyControlObservation:
    return OpenRouterKeyControlObservation(
        control_eligible=False,
        failures=(failure,),
        account_ref_sha256="",
        key_label_sha256="",
        credential_fingerprint=document.credential_fingerprint,
        required_headroom_usd=required,
        maximum_monthly_limit_usd=maximum_limit,
        limit_usd=None,
        limit_remaining_usd=None,
        usage_usd=None,
        usage_monthly_usd=None,
        byok_usage_usd=None,
        byok_usage_monthly_usd=None,
        limit_reset=None,
        include_byok_in_limit=None,
        expires_at=None,
        observed_at=document.observed_at.astimezone(UTC).isoformat(),
        source_sha256=document.source_sha256,
    )


def _key_posture_failures(key: _ParsedOpenRouterKey) -> list[str]:
    failures: list[str] = []
    if key.is_management_key or key.is_provisioning_key:
        failures.append("management and provisioning keys cannot be inference authority")
    if key.is_free_tier:
        failures.append("current key is free-tier and cannot prove the proposed paid route")
    if not key.include_byok:
        failures.append("BYOK usage is excluded from the current key limit")
    if key.limit_reset != "monthly":
        failures.append("current key limit_reset is not monthly")
    if key.expiration_failure is not None:
        failures.append(key.expiration_failure)
    return failures


def _limited_usage(key: _ParsedOpenRouterKey) -> tuple[float, float]:
    if key.include_byok:
        return key.usage + key.byok_usage, key.usage_monthly + key.byok_usage_monthly
    return key.usage, key.usage_monthly


def _key_limit_failures(
    key: _ParsedOpenRouterKey,
    *,
    required: float,
    maximum_limit: float,
) -> list[str]:
    failures: list[str] = []
    if key.limit is None:
        failures.append("current key has no finite USD limit")
    if key.remaining is None:
        failures.append("current key has no finite remaining limit")
    if key.limit is None or key.remaining is None:
        return failures
    if key.limit > maximum_limit + _MONEY_TOLERANCE:
        failures.append(f"current key limit ${key.limit:.6f} exceeds Deepr maximum ${maximum_limit:.6f}")
    if key.remaining > key.limit + _MONEY_TOLERANCE:
        failures.append("current key remaining limit exceeds its total limit")
    if key.remaining + _MONEY_TOLERANCE < required:
        failures.append(f"current key remaining ${key.remaining:.6f} is below required headroom ${required:.6f}")
    limited_usage, limited_usage_monthly = _limited_usage(key)
    if abs((key.limit - key.remaining) - limited_usage) > _MONEY_TOLERANCE:
        failures.append("current key limit, remaining, and usage do not reconcile")
    if key.limit_reset == "monthly" and abs(limited_usage_monthly - limited_usage) > _MONEY_TOLERANCE:
        failures.append("current key monthly usage does not match current limited usage")
    return failures


def evaluate_openrouter_key_document(
    document: FetchedOpenRouterKeyDocument,
    *,
    required_headroom_usd: float,
    maximum_monthly_limit_usd: float = ABSOLUTE_DEEPR_CEILING_USD,
) -> OpenRouterKeyControlObservation:
    """Evaluate current-key controls without granting dispatch authority."""
    required = _money(required_headroom_usd, field_name="required_headroom_usd", positive=True)
    maximum_limit = _money(maximum_monthly_limit_usd, field_name="maximum_monthly_limit_usd", positive=True)
    if required > ABSOLUTE_DEEPR_CEILING_USD + _MONEY_TOLERANCE:
        raise OpenRouterKeyControlError("required_headroom_usd exceeds the absolute Deepr ceiling")
    if maximum_limit > ABSOLUTE_DEEPR_CEILING_USD + _MONEY_TOLERANCE:
        raise OpenRouterKeyControlError("maximum_monthly_limit_usd exceeds the absolute Deepr ceiling")
    if required > maximum_limit + _MONEY_TOLERANCE:
        raise OpenRouterKeyControlError("required_headroom_usd exceeds maximum_monthly_limit_usd")
    if document.observed_at.tzinfo is None or document.observed_at.utcoffset() is None:
        raise OpenRouterKeyControlError("OpenRouter current-key observation time must be timezone-aware")
    if _CREDENTIAL_FINGERPRINT_PATTERN.fullmatch(document.credential_fingerprint) is None:
        raise OpenRouterKeyControlError("OpenRouter current-key credential fingerprint is invalid")
    if _SHA256_PATTERN.fullmatch(document.source_sha256) is None:
        raise OpenRouterKeyControlError("OpenRouter current-key source digest is invalid")
    try:
        key = _parse_key_data(document)
    except OpenRouterKeyControlError as exc:
        return _invalid_key_observation(
            document,
            required=required,
            maximum_limit=maximum_limit,
            failure=str(exc),
        )

    failures = _key_posture_failures(key)
    failures.extend(_key_limit_failures(key, required=required, maximum_limit=maximum_limit))
    return OpenRouterKeyControlObservation(
        control_eligible=not failures,
        failures=tuple(failures),
        account_ref_sha256=_sha256_text(key.creator_user_id),
        key_label_sha256=_sha256_text(key.label),
        credential_fingerprint=document.credential_fingerprint,
        required_headroom_usd=required,
        maximum_monthly_limit_usd=maximum_limit,
        limit_usd=key.limit,
        limit_remaining_usd=key.remaining,
        usage_usd=key.usage,
        usage_monthly_usd=key.usage_monthly,
        byok_usage_usd=key.byok_usage,
        byok_usage_monthly_usd=key.byok_usage_monthly,
        limit_reset=key.limit_reset,
        include_byok_in_limit=key.include_byok,
        expires_at=key.expires_at,
        observed_at=document.observed_at.astimezone(UTC).isoformat(),
        source_sha256=document.source_sha256,
    )


def inspect_openrouter_key(
    api_key: str,
    *,
    required_headroom_usd: float,
) -> OpenRouterKeyControlObservation:
    """Fetch and evaluate one non-authorizing current-key observation."""
    document = fetch_openrouter_current_key(api_key)
    return evaluate_openrouter_key_document(document, required_headroom_usd=required_headroom_usd)


__all__ = [
    "OPENROUTER_KEY_CHECK_KIND",
    "OPENROUTER_KEY_CHECK_SCHEMA_VERSION",
    "FetchedOpenRouterKeyDocument",
    "OpenRouterKeyControlError",
    "OpenRouterKeyControlObservation",
    "evaluate_openrouter_key_document",
    "fetch_openrouter_current_key",
    "inspect_openrouter_key",
]
