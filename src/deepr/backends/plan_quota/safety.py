"""No-surprise-bills and auth-mode gates for plan-quota CLI backends.

Determinism belongs on the money side-effect, not on meaning (AGENTIC_BALANCE.md).
This module is that deterministic gate. Before Deepr runs research through a
vendor CLI as "prepaid plan capacity", two things must hold:

1. **Child auth mode is plan/subscription, not a metered API key.** A CLI
   authenticated by an API key is metered spend wearing a CLI costume. Deepr
   removes known metered env vars from the child process before launch, then
   evaluates that sanitized env so a normal API-capable shell can still run
   explicit plan-quota commands without mutating the user's environment.

2. **Metered-at-margin CLIs have complete cost accounting before execution.** A
   few detected CLIs (e.g. Copilot, post-2026-06 usage-based) are not free at
   the margin. Until an adapter can deterministically estimate and reserve the
   maximum cost, settle reported usage, and write the canonical cost ledger,
   Deepr exposes it as read-only capacity metadata but refuses execution. An
   acknowledgement cannot replace those controls.

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
    refuse the "plan capacity" classification unless the caller sanitizes the
    child environment first.
    """
    for var in adapter.metered_env_vars:
        value = env.get(var)
        if value and value.strip():
            return AuthMode.METERED
    return AuthMode.PLAN


def plan_quota_child_env(adapter: PlanQuotaAdapter, env: Mapping[str, str]) -> dict[str, str]:
    """Return a subprocess env that cannot authenticate this adapter by API key."""
    blocked = set(adapter.metered_env_vars)
    return {key: value for key, value in env.items() if key not in blocked}


def evaluate_plan_quota_safety(adapter: PlanQuotaAdapter, *, env: Mapping[str, str]) -> SafetyDecision:
    """Return the pre-run safety decision for ``adapter``. Deterministic, $0."""
    sanitized_env = plan_quota_child_env(adapter, env)
    mode = detect_auth_mode(adapter, sanitized_env)
    removed_var = _first_set(adapter.metered_env_vars, env)

    if adapter.metered_at_margin:
        return SafetyDecision(
            backend_id=adapter.backend_id,
            safe=False,
            auth_mode=mode,
            requires_ack=False,
            reason=metered_plan_execution_block_reason(adapter),
        )

    removed_note = f"; removed {removed_var} from child env" if removed_var else ""
    note = f"; note: {adapter.tos_note}" if adapter.tos_note else ""
    return SafetyDecision(
        backend_id=adapter.backend_id,
        safe=True,
        auth_mode=mode,
        requires_ack=False,
        reason=f"{adapter.display_name} in plan mode; prepaid capacity before metered API{removed_note}{note}",
    )


def metered_plan_execution_block_reason(adapter: PlanQuotaAdapter) -> str:
    """Explain why a metered-at-margin adapter cannot execute yet."""
    return (
        f"{adapter.display_name} is metered at the margin and cannot execute through plan-quota paths until "
        "the adapter supports deterministic cost estimation, durable reservation, usage settlement, and "
        "canonical cost-ledger writes. Use a non-metered plan backend or an explicitly budgeted API path."
    )


def _first_set(vars_: tuple[str, ...], env: Mapping[str, str]) -> str:
    for var in vars_:
        value = env.get(var)
        if value and value.strip():
            return var
    return vars_[0] if vars_ else ""
