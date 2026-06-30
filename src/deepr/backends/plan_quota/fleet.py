"""Fleet status across all plan-quota CLI backends (read-only, $0).

One glance at every supported CLI: is it installed, what auth mode would it run
in, may Deepr auto-route to it, and what is the latest *observed* quota state
(active / exhausted / quarantined / unobserved) - with a reset time when the
vendor's exhaustion message gave us one. Derived purely from detection (PATH),
the deterministic auth-mode gate, and the append-only quota ledger; it never runs
a CLI and never spends. "Unobserved" and a blank reset are honest: Deepr only
knows what it has seen, and vendors do not expose remaining quota reliably.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from deepr.backends.plan_quota.adapters import PlanQuotaAdapter, all_adapters
from deepr.backends.plan_quota.safety import detect_auth_mode, evaluate_plan_quota_safety
from deepr.backends.quota_ledger import QuotaEventType, QuotaState, summarize_quota_state

FLEET_SCHEMA_VERSION = "deepr-plan-fleet-v1"
FLEET_KIND = "deepr.capacity.fleet"

_TERMINAL_STATUS = {
    QuotaEventType.EXHAUSTED: "exhausted",
    QuotaEventType.QUARANTINED: "quarantined",
}


def _routability(adapter: PlanQuotaAdapter) -> str:
    """How Deepr may use this backend: auto-routed, explicit-only, or metered."""
    if adapter.metered_at_margin:
        return "metered"
    return "auto" if adapter.enabled_by_default else "explicit"


def _latest_per_backend(states: list[QuotaState]) -> dict[str, QuotaState]:
    latest: dict[str, QuotaState] = {}
    for state in states:
        current = latest.get(state.backend_id)
        if current is None or state.latest_event.timestamp >= current.latest_event.timestamp:
            latest[state.backend_id] = state
    return latest


def build_fleet_status(
    *,
    which: Callable[[str], str | None] = shutil.which,
    env: Mapping[str, str] | None = None,
    quota_ledger_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return one status row per plan-quota adapter. Pure, read-only, $0."""
    resolved_env = env if env is not None else dict(os.environ)
    states = _latest_per_backend(summarize_quota_state(quota_ledger_path))

    rows: list[dict[str, Any]] = []
    for adapter in all_adapters():
        installed = which(adapter.exe) is not None
        state = states.get(adapter.backend_id)
        event = state.latest_event if state else None
        status = "unobserved" if event is None else _TERMINAL_STATUS.get(event.event_type, "active")
        raw_auth_mode = detect_auth_mode(adapter, resolved_env).value if installed else None
        auth_mode = evaluate_plan_quota_safety(adapter, env=resolved_env).auth_mode.value if installed else None
        rows.append(
            {
                "backend": adapter.backend_id,
                "name": adapter.display_name,
                "exe": adapter.exe,
                "installed": installed,
                "auth_mode": auth_mode,
                "raw_auth_mode": raw_auth_mode,
                "routable": _routability(adapter),
                "experimental": adapter.experimental,
                "status": status,
                "reset_at": event.reset_at.isoformat() if event and event.reset_at else None,
                "last_event_at": event.timestamp.isoformat() if event else None,
                "detail": event.detail if event else "",
                "value_note": adapter.value_note,
            }
        )
    return rows


def build_fleet_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap fleet rows in the versioned, read-only `$0` envelope for consumers."""
    return {
        "schema_version": FLEET_SCHEMA_VERSION,
        "kind": FLEET_KIND,
        "contract": {"read_only": True, "cost_usd": 0.0, "stability": "experimental"},
        "backends": rows,
    }
