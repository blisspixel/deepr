"""Shared-secret authentication policy for Deepr HTTP and Socket.IO surfaces.

The API, dashboard, and browser socket use the same fail-closed decision:
configured secrets require a constant-time exact match; missing secrets deny
access unless an operator explicitly enabled loopback-only compatibility.
"""

from __future__ import annotations

import hmac
import os
from enum import Enum

from deepr.utils.security import is_loopback_bind_host


class SharedSecretDecision(str, Enum):
    """Deterministic outcomes understood by each interface adapter."""

    ALLOW = "allow"
    NOT_CONFIGURED = "not_configured"
    UNAUTHORIZED = "unauthorized"


def env_flag(name: str) -> bool:
    """Read a conventional explicit opt-in environment flag."""
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def presented_http_secret(authorization: str, api_key: str = "") -> str:
    """Select a bearer token first, then an interface-specific key header."""
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return api_key


def check_shared_secret(
    *,
    configured_secret: str,
    presented_secret: str,
    allow_unauthenticated_loopback: bool,
    remote_addr: str | None,
) -> SharedSecretDecision:
    """Authorize one caller without treating loopback locality as identity."""
    if not configured_secret:
        if allow_unauthenticated_loopback and is_loopback_bind_host(remote_addr):
            return SharedSecretDecision.ALLOW
        return SharedSecretDecision.NOT_CONFIGURED
    if not presented_secret:
        return SharedSecretDecision.UNAUTHORIZED
    try:
        valid = hmac.compare_digest(presented_secret, configured_secret)
    except TypeError:
        valid = False
    return SharedSecretDecision.ALLOW if valid else SharedSecretDecision.UNAUTHORIZED
