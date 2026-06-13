"""Research backends and capacity sources (ROADMAP Phase 6 / v2.16).

A backend sits one level above providers and declares how its work is paid
for: metered API (today's path, the expensive last resort), plan quota
(drive a vendor CLI under its subscription), or local hardware (Ollama, free
at the margin). The capacity-aware router drains owned/prepaid capacity before
ever touching a metered API - so research stays affordable on capacity users
already have. Design: docs/design/capacity-waterfall.md.

This package currently provides capacity *visibility* (detection of what is
available); the backend execution + waterfall routing land in later v2.16
increments.
"""

from deepr.backends.capacity import (
    BackendKind,
    CapacitySource,
    CostModel,
    detect_capacity,
)

__all__ = ["BackendKind", "CapacitySource", "CostModel", "detect_capacity"]
