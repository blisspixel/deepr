"""Off-box liveness heartbeat for scheduled fleet maintenance.

A same-host watchdog cannot catch the one failure that matters most for an
unattended fleet: the machine never woke up (Win11 Modern Standby missed the
timer, the laptop stayed asleep, the box was off). Nothing on that host runs to
notice, so nothing alerts. The only signal is *absence* of an expected check-in,
observed off-box.

On each expected scheduled, non-dry terminal outcome we ping an
operator-configured dead-man's-switch (healthchecks.io, Dead Man's Snitch, or
any URL). Completed and no-work outcomes report success; non-completion and
failed outcomes report failure. The service also alerts when no ping arrives on
schedule. This is opt-in (set ``DEEPR_HEARTBEAT_URL``) and strictly best-effort:
a heartbeat delivery failure must never change the maintenance result. Pure
side-effect at the edge - no model judgment.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

HEARTBEAT_ENV = "DEEPR_HEARTBEAT_URL"


def heartbeat_url() -> str | None:
    """The configured dead-man's-switch base URL, or None when unset/blank."""
    url = os.getenv(HEARTBEAT_ENV, "").strip()
    return url or None


def send_heartbeat(*, success: bool = True, url: str | None = None, timeout: float = 5.0) -> bool:
    """Best-effort ping to the dead-man's-switch; return whether it was delivered.

    healthchecks.io / Dead Man's Snitch convention: GET the base URL to report
    success, and ``<url>/fail`` to report a failed run (so the operator is
    alerted on a real failure as well as on silence). Returns True only on an
    HTTP 2xx. Never raises - the heartbeat is liveness telemetry, not part of the
    job. A no-op (returns False) when no URL is configured.
    """
    base = url or heartbeat_url()
    if not base:
        return False
    target = base if success else base.rstrip("/") + "/fail"
    try:
        response = requests.get(target, timeout=timeout, allow_redirects=False)
    except requests.RequestException:
        logger.debug("heartbeat request failed")
        return False
    if 200 <= response.status_code < 300:
        return True
    logger.debug("heartbeat request returned HTTP %s", response.status_code)
    return False
