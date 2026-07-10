"""Thread-safe, deferred construction for metered research providers."""

from __future__ import annotations

import logging
import threading
from typing import Any, cast

from deepr.providers import ProviderType, create_provider
from deepr.providers.base import DeepResearchProvider


class LazyProviderResolver:
    """Resolve one configured provider without constructing it at import time."""

    def __init__(self, provider_name: str, api_key: str | None, logger: logging.Logger) -> None:
        self._provider_name = cast(ProviderType, provider_name)
        self._api_key = api_key
        self._logger = logger
        self._provider: DeepResearchProvider | None = None
        self._lock = threading.Lock()

    def resolve(self) -> DeepResearchProvider | None:
        """Return the cached provider, or ``None`` when configuration is invalid."""
        if self._provider is not None:
            return self._provider
        with self._lock:
            if self._provider is not None:
                return self._provider
            try:
                self._provider = create_provider(self._provider_name, api_key=self._api_key)
            except (ImportError, TypeError, ValueError) as exc:
                self._logger.warning("Configured research provider is unavailable: %s", exc)
                return None
            return self._provider


def config_api_key(value: Any) -> str | None:
    """Narrow the legacy configuration value to the provider factory contract."""
    return value if isinstance(value, str) else None
