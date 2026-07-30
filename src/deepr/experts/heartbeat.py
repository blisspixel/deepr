"""Quarantined off-box heartbeat configuration for fleet maintenance.

Remote heartbeat delivery cannot prove whether the operator-configured service
is free, prepaid with overages disabled, or metered. Deepr therefore validates
and reports the configuration but never sends it in the no-surprise-spend
release profile.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

HEARTBEAT_ENV = "DEEPR_HEARTBEAT_URL"
MAX_HEARTBEAT_URL_LENGTH = 2048
REMOTE_HEARTBEAT_EXECUTION_ENABLED = False
REMOTE_HEARTBEAT_BLOCK_REASON = "unmetered_external_service"


class HeartbeatConfigurationError(ValueError):
    """The configured endpoint cannot satisfy the heartbeat safety contract."""


@dataclass(frozen=True)
class HeartbeatDelivery:
    """Credential-safe outcome of one bounded heartbeat delivery attempt."""

    attempted: bool
    delivered: bool
    failure_kind: str | None = None
    http_status: int | None = None


def heartbeat_url() -> str | None:
    """The configured dead-man's-switch base URL, or None when unset/blank."""
    url = os.getenv(HEARTBEAT_ENV, "").strip()
    return url or None


def validate_heartbeat_url(url: str) -> str:
    """Return a normalized endpoint when its non-network form is safe.

    The ping URL is a credential. Require HTTPS, a host, no authority
    credentials or fragment, bounded length, and no whitespace or controls.
    Public-address resolution is checked immediately before delivery so a
    scheduled dry-run can validate form without performing network I/O.
    """
    normalized = url.strip()
    if (
        not normalized
        or len(normalized) > MAX_HEARTBEAT_URL_LENGTH
        or any(character.isspace() or not character.isprintable() for character in normalized)
    ):
        raise HeartbeatConfigurationError("heartbeat URL has invalid form")
    try:
        parsed = urlsplit(normalized)
        _ = parsed.port
    except ValueError as exc:
        raise HeartbeatConfigurationError("heartbeat URL has invalid form") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise HeartbeatConfigurationError("heartbeat URL has invalid form")
    return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))


def deliver_heartbeat(
    *,
    success: bool = True,
    url: str | None = None,
    timeout: float = 5.0,
) -> HeartbeatDelivery:
    """Validate configuration and block before any remote request."""
    _ = success
    base = url or heartbeat_url()
    if not base:
        return HeartbeatDelivery(attempted=False, delivered=False, failure_kind="not_configured")
    if not math.isfinite(timeout) or timeout <= 0:
        return HeartbeatDelivery(attempted=False, delivered=False, failure_kind="invalid_configuration")
    try:
        validate_heartbeat_url(base)
    except HeartbeatConfigurationError:
        return HeartbeatDelivery(attempted=False, delivered=False, failure_kind="invalid_configuration")
    return HeartbeatDelivery(attempted=False, delivered=False, failure_kind=REMOTE_HEARTBEAT_BLOCK_REASON)


def send_heartbeat(*, success: bool = True, url: str | None = None, timeout: float = 5.0) -> bool:
    """Backward-compatible bool wrapper for best-effort heartbeat delivery."""
    return deliver_heartbeat(success=success, url=url, timeout=timeout).delivered
