"""Shared explicit-consent contract for metered API execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

METERED_API_CONSENT_ERROR = (
    "Metered API execution requires allow_metered_api=true and "
    "confirm_metered_cost=true; a budget is only a ceiling, not permission to spend."
)


def metered_api_consent_error(data: object) -> str | None:
    """Return the fail-closed denial when both exact acknowledgements are absent."""
    if not isinstance(data, Mapping):
        return METERED_API_CONSENT_ERROR
    request_data: Mapping[str, Any] = data
    if request_data.get("allow_metered_api") is not True:
        return METERED_API_CONSENT_ERROR
    if request_data.get("confirm_metered_cost") is not True:
        return METERED_API_CONSENT_ERROR
    return None


__all__ = ["METERED_API_CONSENT_ERROR", "metered_api_consent_error"]
