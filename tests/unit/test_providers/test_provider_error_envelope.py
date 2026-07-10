"""Tests for the provider-layer error envelope and SDK-exception classifier.

ProviderError carries the agent-classification envelope (category /
retryable / retry_after) and serializes it via to_dict(), matching
DeeprError's shape so any surface can classify a provider failure and
decide on backoff/fallback without parsing the message.
"""

from __future__ import annotations

from deepr.providers.base import ProviderError, classify_provider_exception


class _RateLimitError(Exception):
    def __init__(self, retry_after: int | None = None):
        super().__init__("rate limited")
        self.retry_after = retry_after


class _APITimeoutError(Exception):
    pass


class _AuthenticationError(Exception):
    pass


class _BadRequestError(Exception):
    pass


class TestProviderErrorEnvelope:
    def test_defaults(self):
        d = ProviderError("boom", provider="openai").to_dict()
        assert d["error"] is True
        assert d["error_code"] == "PROVIDER_ERROR"
        assert d["category"] == "provider"
        assert d["retryable"] is False
        assert d["details"] == {"provider": "openai"}
        assert "retry_after" not in d

    def test_retryable_with_retry_after(self):
        d = ProviderError("slow", provider="openai", category="provider", retryable=True, retry_after=30).to_dict()
        assert d["retryable"] is True
        assert d["retry_after"] == 30

    def test_to_dict_is_json_serializable(self):
        import json

        json.dumps(ProviderError("x", provider="grok", retryable=True).to_dict())


class TestProviderErrorAutoClassification:
    """ProviderError auto-classifies from original_error - so every adapter's
    `raise ProviderError(..., original_error=e)` gets the envelope for free."""

    def test_auto_classifies_rate_limit_from_original_error(self):
        err = ProviderError("wrapped", provider="openai", original_error=_RateLimitError(retry_after=7))
        d = err.to_dict()
        assert d["category"] == "provider"
        assert d["retryable"] is True
        assert d["retry_after"] == 7

    def test_auto_classifies_auth_from_original_error(self):
        err = ProviderError("wrapped", provider="anthropic", original_error=_AuthenticationError())
        assert err.category == "auth"
        assert err.retryable is False

    def test_explicit_values_override_auto_classification(self):
        # An explicit retryable=False wins even over a transient original_error.
        err = ProviderError("wrapped", provider="grok", original_error=_RateLimitError(retry_after=5), retryable=False)
        assert err.retryable is False

    def test_no_original_error_keeps_provider_defaults(self):
        err = ProviderError("plain", provider="gemini")
        assert err.category == "provider"
        assert err.retryable is False
        assert err.retry_after is None


class TestClassifyProviderException:
    def test_rate_limit_is_retryable_and_keeps_retry_after(self):
        category, retryable, retry_after = classify_provider_exception(_RateLimitError(retry_after=12))
        assert category == "provider"
        assert retryable is True
        assert retry_after == 12

    def test_timeout_is_retryable(self):
        category, retryable, _ = classify_provider_exception(_APITimeoutError())
        assert category == "provider"
        assert retryable is True

    def test_authentication_is_auth_and_not_retryable(self):
        category, retryable, _ = classify_provider_exception(_AuthenticationError())
        assert category == "auth"
        assert retryable is False

    def test_unknown_is_non_retryable_provider(self):
        category, retryable, _ = classify_provider_exception(_BadRequestError())
        assert category == "provider"
        assert retryable is False

    def test_non_int_retry_after_is_dropped(self):
        err = _RateLimitError(retry_after="60")  # header strings happen
        _, _, retry_after = classify_provider_exception(err)
        assert retry_after is None
