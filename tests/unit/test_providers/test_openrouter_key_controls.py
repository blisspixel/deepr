"""Authenticated OpenRouter current-key observation tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from deepr.providers.openrouter_key_controls import (
    FetchedOpenRouterKeyDocument,
    OpenRouterKeyControlError,
    evaluate_openrouter_key_document,
    fetch_openrouter_current_key,
)

_API_KEY = "sk-or-v1-" + "a" * 64
_OBSERVED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
_FINGERPRINT = (
    "scrypt:"
    + hashlib.scrypt(
        _API_KEY.encode(),
        salt=b"deepr/openrouter/credential-fingerprint/v1",
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    ).hex()
)


def _payload(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "byok_usage": 0.2,
        "byok_usage_daily": 0.2,
        "byok_usage_monthly": 0.2,
        "byok_usage_weekly": 0.2,
        "creator_user_id": "user_example",
        "expires_at": "2026-10-01T00:00:00Z",
        "include_byok_in_limit": True,
        "is_free_tier": False,
        "is_management_key": False,
        "is_provisioning_key": False,
        "label": "sk-or-v1-abc...xyz",
        "limit": 5.0,
        "limit_remaining": 4.0,
        "limit_reset": "monthly",
        "usage": 0.8,
        "usage_daily": 0.8,
        "usage_monthly": 0.8,
        "usage_weekly": 0.8,
    }
    data.update(changes)
    return {"data": data}


def _document(**changes: Any) -> FetchedOpenRouterKeyDocument:
    return FetchedOpenRouterKeyDocument(
        payload=_payload(**changes),
        source_sha256="b" * 64,
        credential_fingerprint=_FINGERPRINT,
        observed_at=_OBSERVED_AT,
    )


def test_current_key_controls_are_sanitized_and_non_authorizing() -> None:
    observation = evaluate_openrouter_key_document(_document(), required_headroom_usd=4.0)
    assert observation.control_eligible is True
    assert observation.failures == ()
    assert observation.limit_usd == 5.0
    assert observation.limit_remaining_usd == 4.0
    assert observation.byok_usage_usd == 0.2
    assert observation.required_headroom_usd == 4.0
    assert observation.maximum_monthly_limit_usd == 5.0
    payload = observation.to_dict()
    assert payload["account_ref_sha256"] == hashlib.sha256(b"user_example").hexdigest()
    assert payload["key_label_sha256"] == hashlib.sha256(b"sk-or-v1-abc...xyz").hexdigest()
    assert payload["api_key_source"] == "caller_supplied"
    assert payload["inference_requests"] == 0
    assert payload["paid_requests"] == 0
    assert payload["billing_reconciliation_complete"] is False
    assert payload["dispatch_authorized"] is False
    assert "user_example" not in json.dumps(payload)
    assert "sk-or-v1-abc" not in json.dumps(payload)


@pytest.mark.parametrize(
    ("changes", "required", "failure"),
    [
        ({"limit": 6.0, "limit_remaining": 5.0}, 4.0, "exceeds Deepr maximum"),
        ({"limit_remaining": 3.99, "usage": 0.81}, 4.0, "below required headroom"),
        ({"include_byok_in_limit": False, "limit_remaining": 4.2}, 4.0, "BYOK usage is excluded"),
        ({"is_management_key": True}, 4.0, "management and provisioning"),
        ({"is_provisioning_key": True}, 4.0, "management and provisioning"),
        ({"is_free_tier": True}, 4.0, "free-tier"),
        ({"limit_reset": "daily"}, 4.0, "not monthly"),
        ({"limit_remaining": 5.1, "usage": 0.0, "byok_usage": 0.0}, 4.0, "exceeds its total"),
        ({"usage": 0.7}, 4.0, "do not reconcile"),
        ({"usage_monthly": 0.7}, 4.0, "monthly usage"),
        ({"expires_at": "2026-08-31T00:00:00Z"}, 4.0, "has expired"),
    ],
)
def test_current_key_controls_fail_closed(
    changes: dict[str, Any],
    required: float,
    failure: str,
) -> None:
    observation = evaluate_openrouter_key_document(_document(**changes), required_headroom_usd=required)
    assert observation.control_eligible is False
    assert any(failure in item for item in observation.failures)
    assert observation.to_dict()["dispatch_authorized"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"limit": None},
        {"limit": "5"},
        {"include_byok_in_limit": 1},
        {"creator_user_id": ""},
        {"label": "not-ascii-\N{LATIN SMALL LETTER E WITH ACUTE}"},
        {"byok_usage": -1},
    ],
)
def test_malformed_current_key_fields_return_non_authorizing_observation(changes: dict[str, Any]) -> None:
    observation = evaluate_openrouter_key_document(_document(**changes), required_headroom_usd=4.0)
    assert observation.control_eligible is False
    assert observation.limit_usd is None
    assert observation.to_dict()["dispatch_authorized"] is False


@pytest.mark.parametrize(
    ("required", "maximum", "message"),
    [
        (0.0, 5.0, "finite USD"),
        (5.01, 5.0, "absolute Deepr ceiling"),
        (4.0, 5.01, "absolute Deepr ceiling"),
        (4.0, 3.0, "exceeds maximum_monthly_limit_usd"),
    ],
)
def test_local_headroom_inputs_cannot_widen_the_absolute_ceiling(
    required: float,
    maximum: float,
    message: str,
) -> None:
    with pytest.raises(OpenRouterKeyControlError, match=message):
        evaluate_openrouter_key_document(
            _document(),
            required_headroom_usd=required,
            maximum_monthly_limit_usd=maximum,
        )


@pytest.mark.parametrize(
    ("source_sha256", "fingerprint", "message"),
    [
        ("opaque", _FINGERPRINT, "source digest"),
        ("b" * 64, "scrypt:" + "G" * 64, "credential fingerprint"),
    ],
)
def test_local_evidence_bindings_require_exact_digest_forms(
    source_sha256: str,
    fingerprint: str,
    message: str,
) -> None:
    document = FetchedOpenRouterKeyDocument(
        payload=_payload(),
        source_sha256=source_sha256,
        credential_fingerprint=fingerprint,
        observed_at=_OBSERVED_AT,
    )
    with pytest.raises(OpenRouterKeyControlError, match=message):
        evaluate_openrouter_key_document(document, required_headroom_usd=4.0)


class _FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status_code: int = 200,
        content_type: str = "application/json",
        content_length: str | None = None,
    ) -> None:
        self.body = body
        self.status_code = status_code
        self.headers: dict[str, str] = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [self.body[index : index + chunk_size] for index in range(0, len(self.body), chunk_size)]


def test_current_key_fetch_binds_prompted_credential_and_closes_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps(_payload()).encode()
    response = _FakeResponse(raw, content_length=str(len(raw)))
    captured: dict[str, Any] = {}
    closed: list[object] = []

    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        captured.update({"url": url, **kwargs})
        return response

    monkeypatch.setattr("deepr.providers.openrouter_key_controls.pinned_get", fake_get)
    monkeypatch.setattr("deepr.providers.openrouter_key_controls.close_pinned_response", closed.append)
    document = fetch_openrouter_current_key(_API_KEY)

    assert captured["url"] == "https://openrouter.ai/api/v1/key"
    assert captured["headers"]["Authorization"] == f"Bearer {_API_KEY}"
    assert captured["allow_redirects"] is False
    assert captured["stream"] is True
    assert document.credential_fingerprint == _FINGERPRINT
    assert document.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert closed == [response]


@pytest.mark.parametrize(
    "api_key",
    ["", "openrouter-key", "sk-or-\N{LATIN SMALL LETTER E WITH ACUTE}" * 20, "sk-or- has-space"],
)
def test_invalid_key_is_rejected_before_network(monkeypatch: pytest.MonkeyPatch, api_key: str) -> None:
    monkeypatch.setattr(
        "deepr.providers.openrouter_key_controls.pinned_get",
        lambda *args, **kwargs: pytest.fail("network must not run"),
    )
    with pytest.raises(OpenRouterKeyControlError):
        fetch_openrouter_current_key(api_key)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_FakeResponse(b"{}", status_code=401), "HTTP 401"),
        (_FakeResponse(b"{}", content_type="text/html"), "application/json"),
        (_FakeResponse(b"{}", content_length=str(128 * 1024)), "byte ceiling"),
        (_FakeResponse(b"{}", content_length="opaque"), "Content-Length"),
        (_FakeResponse(b'{"data":1,"data":2}'), "duplicate object key"),
    ],
)
def test_current_key_fetch_rejects_untrusted_responses(
    monkeypatch: pytest.MonkeyPatch,
    response: _FakeResponse,
    message: str,
) -> None:
    monkeypatch.setattr("deepr.providers.openrouter_key_controls.pinned_get", lambda *args, **kwargs: response)
    monkeypatch.setattr("deepr.providers.openrouter_key_controls.close_pinned_response", lambda value: None)
    with pytest.raises(OpenRouterKeyControlError, match=message):
        fetch_openrouter_current_key(_API_KEY)
