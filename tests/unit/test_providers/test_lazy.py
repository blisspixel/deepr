"""Tests for deferred provider construction."""

from unittest.mock import MagicMock, patch

import pytest

from deepr.providers.lazy import LazyProviderResolver, config_api_key


def test_resolver_defers_and_caches_provider_construction() -> None:
    provider = MagicMock()
    resolver = LazyProviderResolver("openai", "key", MagicMock())

    with patch("deepr.providers.lazy.create_provider", return_value=provider) as create:
        assert create.call_count == 0
        assert resolver.resolve() is provider
        assert resolver.resolve() is provider

    create.assert_called_once_with("openai", api_key="key")


@pytest.mark.parametrize("error", [ValueError("missing key"), ImportError("missing extra")])
def test_resolver_returns_none_and_logs_unavailable_provider(error: Exception) -> None:
    logger = MagicMock()
    resolver = LazyProviderResolver("openai", None, logger)

    with patch("deepr.providers.lazy.create_provider", side_effect=error):
        assert resolver.resolve() is None

    assert logger.warning.call_count == 1
    message, logged_error = logger.warning.call_args.args
    assert message == "Configured research provider is unavailable: %s"
    assert logged_error is error


def test_config_api_key_rejects_non_string_values() -> None:
    assert config_api_key("key") == "key"
    assert config_api_key(None) is None
    assert config_api_key(123) is None
