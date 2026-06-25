"""Research backends and capacity sources (ROADMAP Phase 6 / v2.16).

A backend sits one level above providers and declares how its work is paid
for: metered API (today's path, the expensive last resort), plan quota
(drive a vendor CLI under its subscription), or local hardware (Ollama, free
at the margin). The capacity-aware router drains owned/prepaid capacity before
ever touching a metered API - so research stays affordable on capacity users
already have. Design: docs/design/capacity-waterfall.md.

This package currently provides capacity *visibility*, normalized backend
profiles, local admission, append-only quota observations, pure eligibility
decisions, deterministic backend selection, explicit plan-quota execution, and
the normalized quota-snapshot substrate for live availability probes.
"""

from deepr.backends.capacity import (
    BackendKind,
    CapacitySource,
    CostModel,
    detect_capacity,
)
from deepr.backends.eligibility import (
    BackendEligibility,
    BackendEligibilityStatus,
    evaluate_backend_eligibility,
)
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerEvent,
    QuotaState,
    QuotaWindowKind,
    summarize_quota_state,
)
from deepr.backends.quota_snapshot import (
    QuotaAvailability,
    QuotaSnapshot,
    QuotaWindowSnapshot,
    binding_window,
    snapshot_availability,
    snapshot_headroom,
    snapshot_to_ledger_event,
)
from deepr.backends.research_backend import (
    ResearchBackend,
    backend_from_capacity_source,
    discover_research_backends,
)
from deepr.backends.selection import (
    BackendCandidate,
    BackendQualityGate,
    BackendQualityStatus,
    BackendSelection,
    BackendSelectionStatus,
    select_capacity_backend,
)

__all__ = [
    "BackendCandidate",
    "BackendEligibility",
    "BackendEligibilityStatus",
    "BackendKind",
    "BackendQualityGate",
    "BackendQualityStatus",
    "BackendSelection",
    "BackendSelectionStatus",
    "CapacitySource",
    "CostModel",
    "QuotaAvailability",
    "QuotaConfidence",
    "QuotaEventType",
    "QuotaLedger",
    "QuotaLedgerEvent",
    "QuotaSnapshot",
    "QuotaState",
    "QuotaWindowKind",
    "QuotaWindowSnapshot",
    "ResearchBackend",
    "backend_from_capacity_source",
    "binding_window",
    "detect_capacity",
    "discover_research_backends",
    "evaluate_backend_eligibility",
    "select_capacity_backend",
    "snapshot_availability",
    "snapshot_headroom",
    "snapshot_to_ledger_event",
    "summarize_quota_state",
]
