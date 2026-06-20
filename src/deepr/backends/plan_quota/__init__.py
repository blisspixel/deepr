"""Plan-quota CLI research backends (ROADMAP Phase 6).

Drive a vendor's own coding/agent CLI (codex, claude, opencode, ...) as a
subprocess so quality-tolerant expert maintenance runs on capacity the operator
already pays for, at $0 at the margin, before any metered API call. The
no-surprise-bills and auth-mode gates are deterministic (``safety``); only
backends that are genuinely free at the margin and ToS-clean are auto-routable.
"""

from __future__ import annotations

from deepr.backends.plan_quota.adapters import (
    REGISTRY,
    PlanQuotaAdapter,
    all_adapters,
    auto_routable_adapters,
    get_adapter,
)
from deepr.backends.plan_quota.client import (
    PlanQuotaChatClient,
    PlanQuotaError,
    PlanQuotaExhausted,
    make_plan_quota_research_fn,
    probe_plan_quota,
)
from deepr.backends.plan_quota.fleet import (
    FLEET_KIND,
    FLEET_SCHEMA_VERSION,
    build_fleet_payload,
    build_fleet_status,
)
from deepr.backends.plan_quota.safety import (
    AuthMode,
    SafetyDecision,
    detect_auth_mode,
    evaluate_plan_quota_safety,
)

__all__ = [
    "FLEET_KIND",
    "FLEET_SCHEMA_VERSION",
    "REGISTRY",
    "AuthMode",
    "PlanQuotaAdapter",
    "PlanQuotaChatClient",
    "PlanQuotaError",
    "PlanQuotaExhausted",
    "SafetyDecision",
    "all_adapters",
    "auto_routable_adapters",
    "build_fleet_payload",
    "build_fleet_status",
    "detect_auth_mode",
    "evaluate_plan_quota_safety",
    "get_adapter",
    "make_plan_quota_research_fn",
    "probe_plan_quota",
]
