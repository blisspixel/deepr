"""Credential-safe heartbeat evidence and rendering for roster sync."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from deepr.cli.colors import console, print_warning


def heartbeat_evidence(*, scheduled: bool, dry_run: bool, success: bool) -> dict[str, Any]:
    """Report bounded heartbeat disposition without exposing its configured URL."""
    from deepr.experts.heartbeat import (
        HeartbeatConfigurationError,
        HeartbeatDelivery,
        deliver_heartbeat,
        heartbeat_url,
        validate_heartbeat_url,
    )

    configured_url = heartbeat_url()
    configured = configured_url is not None
    configuration_valid: bool | None = None
    if configured_url is not None:
        try:
            validate_heartbeat_url(configured_url)
            configuration_valid = True
        except HeartbeatConfigurationError:
            configuration_valid = False

    delivery = HeartbeatDelivery(attempted=False, delivered=False)
    attempted_at: str | None = None
    duration_ms: int | None = None
    if configured and configuration_valid is False:
        disposition = "invalid_configuration"
        failure_kind: str | None = "invalid_configuration"
    elif not configured:
        disposition = "not_configured"
        failure_kind = None
    elif not scheduled:
        disposition = "not_scheduled"
        failure_kind = None
    elif dry_run:
        disposition = "validated_not_sent"
        failure_kind = None
    else:
        attempt_candidate = datetime.now(UTC)
        started = perf_counter()
        delivery = deliver_heartbeat(success=success, url=configured_url)
        elapsed_ms = max(0, round((perf_counter() - started) * 1000))
        attempted_at = attempt_candidate.isoformat() if delivery.attempted else None
        duration_ms = elapsed_ms if delivery.attempted else None
        failure_kind = delivery.failure_kind
        if delivery.delivered:
            disposition = "delivered"
        elif delivery.failure_kind == "unmetered_external_service":
            disposition = "blocked_unmetered_external_service"
        elif delivery.failure_kind == "unsafe_target":
            disposition = "blocked_unsafe_target"
        elif delivery.failure_kind == "invalid_configuration":
            disposition = "invalid_configuration"
            configuration_valid = False
        else:
            disposition = "delivery_failed"

    return {
        "configured": configured,
        "configuration_valid": configuration_valid,
        "scheduled": scheduled,
        "dry_run": dry_run,
        "attempted": delivery.attempted,
        "attempt_count": 1 if delivery.attempted else 0,
        "attempted_at": attempted_at,
        "duration_ms": duration_ms,
        "delivered": delivery.delivered,
        "reported_status": ("success" if success else "failure") if delivery.attempted else None,
        "disposition": disposition,
        "failure_kind": failure_kind,
        "http_status": delivery.http_status,
    }


def render_heartbeat_evidence(heartbeat: dict[str, Any], *, json_output: bool) -> None:
    """Render one credential-safe operator state for the current heartbeat."""
    if json_output:
        return
    disposition = heartbeat["disposition"]
    if disposition == "not_configured" and heartbeat["scheduled"]:
        console.print("[dim]Off-box heartbeat is not configured (optional: DEEPR_HEARTBEAT_URL).[/dim]")
    elif disposition == "invalid_configuration":
        print_warning(
            "Configured heartbeat URL is invalid; use a public HTTPS URL without credentials or fragments. "
            "No request was sent."
        )
    elif disposition == "validated_not_sent":
        console.print("[dim]Off-box heartbeat configuration is valid; dry-run did not contact it.[/dim]")
    elif disposition == "blocked_unsafe_target":
        print_warning("Configured heartbeat target is not a public address; no request was sent.")
    elif disposition == "blocked_unmetered_external_service":
        print_warning(
            "Configured off-box heartbeat is blocked because its external cost cannot be proven before dispatch. "
            "No request was sent."
        )
    elif disposition == "delivered":
        console.print(f"[dim]Off-box heartbeat delivered as {heartbeat['reported_status']}.[/dim]")
    elif disposition == "delivery_failed" and heartbeat["http_status"] is not None:
        print_warning(
            f"Configured heartbeat delivery failed with HTTP {heartbeat['http_status']}; "
            "maintenance status is unchanged."
        )
    elif disposition == "delivery_failed":
        print_warning("Configured heartbeat delivery failed; maintenance status is unchanged.")
