"""Off-box liveness heartbeat for scheduled fleet maintenance.

A same-host watchdog cannot catch the one failure that matters most for an
unattended fleet: the machine never woke up (Win11 Modern Standby missed the
timer, the laptop stayed asleep, the box was off). Nothing on that host runs to
notice, so nothing alerts. The only signal is *absence* of an expected check-in,
observed off-box.

On each expected scheduled, non-dry terminal outcome we ping an
operator-configured, public HTTPS endpoint that follows the Healthchecks
success and ``/fail`` path convention. Completed and no-work outcomes report
success; non-completion and failed outcomes report failure. The service also
alerts when no ping arrives on schedule. This is opt-in (set
``DEEPR_HEARTBEAT_URL``) and strictly best-effort: a heartbeat delivery failure
must never change the maintenance result. Pure side-effect at the edge - no
model judgment.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import requests

from deepr.utils.pinned_http import close_pinned_response, pinned_get
from deepr.utils.security import SSRFError

logger = logging.getLogger(__name__)

HEARTBEAT_ENV = "DEEPR_HEARTBEAT_URL"
MAX_HEARTBEAT_URL_LENGTH = 2048


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


def _heartbeat_target(url: str, *, success: bool) -> str:
    base = validate_heartbeat_url(url)
    if success:
        return base
    parsed = urlsplit(base)
    failure_path = parsed.path.rstrip("/") + "/fail"
    return urlunsplit((parsed.scheme, parsed.netloc, failure_path, parsed.query, ""))


def deliver_heartbeat(
    *,
    success: bool = True,
    url: str | None = None,
    timeout: float = 5.0,
) -> HeartbeatDelivery:
    """Attempt one bounded ping and return a credential-safe typed outcome.

    The endpoint uses the Healthchecks-compatible convention: GET the base URL
    for success and append ``/fail`` to its path for failure while preserving
    its query. Redirects are refused. The response is streamed and closed after
    header inspection, so endpoint-controlled response content is not consumed.
    No error includes the credential-bearing target.
    """
    base = url or heartbeat_url()
    if not base:
        return HeartbeatDelivery(attempted=False, delivered=False, failure_kind="not_configured")
    if not math.isfinite(timeout) or timeout <= 0:
        return HeartbeatDelivery(attempted=False, delivered=False, failure_kind="invalid_configuration")
    try:
        target = _heartbeat_target(base, success=success)
    except HeartbeatConfigurationError:
        logger.debug("heartbeat configuration is invalid")
        return HeartbeatDelivery(attempted=False, delivered=False, failure_kind="invalid_configuration")
    response: requests.Response | None = None
    try:
        response = pinned_get(
            target,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
            address_failover=False,
            redact_request_target=True,
        )
    except SSRFError:
        logger.debug("heartbeat target failed peer-bound public-address safety checks")
        return HeartbeatDelivery(attempted=False, delivered=False, failure_kind="unsafe_target")
    except requests.RequestException:
        logger.debug("heartbeat request failed")
        return HeartbeatDelivery(attempted=True, delivered=False, failure_kind="network_error")
    try:
        status = int(response.status_code)
        if 200 <= status < 300:
            return HeartbeatDelivery(attempted=True, delivered=True, http_status=status)
        logger.debug("heartbeat request returned HTTP %s", status)
        return HeartbeatDelivery(
            attempted=True,
            delivered=False,
            failure_kind="http_error",
            http_status=status,
        )
    finally:
        try:
            close_pinned_response(response)
        except Exception:
            logger.debug("heartbeat response close failed")


def send_heartbeat(*, success: bool = True, url: str | None = None, timeout: float = 5.0) -> bool:
    """Backward-compatible bool wrapper for best-effort heartbeat delivery."""
    return deliver_heartbeat(success=success, url=url, timeout=timeout).delivered
