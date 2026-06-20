"""No-surprise-bills and auth-mode gates for plan-quota CLI backends.

Determinism belongs on the money side-effect, not on meaning (AGENTIC_BALANCE.md).
This module is that deterministic gate. Before Deepr runs research through a
vendor CLI as "prepaid plan capacity", two things must hold:

1. **Auth mode is plan/subscription, not a metered API key.** A CLI
   authenticated by an API key is metered spend wearing a CLI costume; treating
   it as free plan capacity is exactly the surprise bill the waterfall exists to
   prevent (ROADMAP Phase 6: "refuse to classify an API-key CLI as plan_quota").
   Detection is env-based and deterministic: if a backend's metered-env var is
   set, the next subprocess run would bill that key, so we block and tell the
   operator to unset it (or use the metered API backend on purpose).

2. **The operator accepts the billing shape of a metered-by-nature CLI.** A few
   supported CLIs (e.g. Copilot, post-2026-06 usage-based) are not free at the
   margin at all. They are off by default and, when invoked explicitly, require
   an acknowledgement so a paid call is never a side effect.

The gate returns a typed decision the caller logs/prints before any subprocess
runs. It does not judge answer quality - that stays calibrated model judgment.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepr.backends.plan_quota.adapters import PlanQuotaAdapter


class AuthMode(str, Enum):
    """How a plan-quota CLI would authenticate its next run."""

    PLAN = "plan"  # subscription / OAuth session - prepaid, $0 at the margin
    METERED = "metered"  # an API key is set - this would bill per use


@dataclass(frozen=True)
class SafetyDecision:
    """A deterministic pre-run gate result for one plan-quota backend."""

    backend_id: str
    safe: bool
    auth_mode: AuthMode
    requires_ack: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "backend_id": self.backend_id,
            "safe": self.safe,
            "auth_mode": self.auth_mode.value,
            "requires_ack": self.requires_ack,
            "reason": self.reason,
        }


def detect_auth_mode(adapter: PlanQuotaAdapter, env: Mapping[str, str]) -> AuthMode:
    """Deterministic auth-mode detection from the environment.

    If any of the backend's metered-env vars is set and non-empty, the next
    ``argv`` run would authenticate with that key and bill per use -> METERED.
    Otherwise the CLI uses its stored subscription/OAuth session -> PLAN. This
    is intentionally conservative on the money side: a key in the env always
    wins on every vendor's precedence rules, so its mere presence is enough to
    refuse the "plan capacity" classification.
    """
    for var in adapter.metered_env_vars:
        value = env.get(var)
        if value and value.strip():
            return AuthMode.METERED
    return AuthMode.PLAN


def evaluate_plan_quota_safety(adapter: PlanQuotaAdapter, *, env: Mapping[str, str]) -> SafetyDecision:
    """Return the pre-run safety decision for ``adapter``. Deterministic, $0."""
    mode = detect_auth_mode(adapter, env)

    if mode == AuthMode.METERED:
        blocking_var = _first_set(adapter.metered_env_vars, env)
        return SafetyDecision(
            backend_id=adapter.backend_id,
            safe=False,
            auth_mode=mode,
            requires_ack=False,
            reason=(
                f"{blocking_var} is set, so {adapter.exe!r} would authenticate with a metered API key "
                f"and bill per call - not plan capacity. Unset {blocking_var} to run on your "
                f"subscription, or use the metered API backend on purpose (--api)."
            ),
        )

    if adapter.metered_at_margin:
        return SafetyDecision(
            backend_id=adapter.backend_id,
            safe=True,
            auth_mode=mode,
            requires_ack=True,
            reason=(
                f"{adapter.display_name} bills usage per call (not free at the margin); "
                "explicit confirmation required so a paid run is never a side effect."
            ),
        )

    note = f"; note: {adapter.tos_note}" if adapter.tos_note else ""
    return SafetyDecision(
        backend_id=adapter.backend_id,
        safe=True,
        auth_mode=mode,
        requires_ack=False,
        reason=f"{adapter.display_name} in plan mode; prepaid capacity before metered API{note}",
    )


def _first_set(vars_: tuple[str, ...], env: Mapping[str, str]) -> str:
    for var in vars_:
        value = env.get(var)
        if value and value.strip():
            return var
    return vars_[0] if vars_ else ""
