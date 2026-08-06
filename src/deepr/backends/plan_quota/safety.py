"""No-surprise-bills and auth-mode gates for plan-quota CLI backends.

Determinism belongs on the money side-effect, not on meaning (AGENTIC_BALANCE.md).
This module is that deterministic gate. Before Deepr runs research through a
vendor CLI as "prepaid plan capacity", two things must hold:

1. **Child auth mode is provably plan/subscription, not a metered API key.** A
   CLI authenticated by an API key is metered spend wearing a CLI costume.
   Known metered credentials and unverified stored-provider authentication are
   refused before launch. The child receives only a small runtime allowlist.

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
    UNKNOWN = "unknown"  # stored/provider authentication cannot be proven


_PLAN_CHILD_ENV_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "CLAUDE_CONFIG_DIR",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOCALAPPDATA",
        "LOGNAME",
        "NO_COLOR",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
        "TZ",
        "USER",
        "USERNAME",
        "USERPROFILE",
        "WINDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    }
)


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
    """Deterministic auth-mode detection from what the dispatch can actually reach.

    **Holding a credential is not spending it.** Operators legitimately keep API
    keys in their environment for other tools. Refusing to run prepaid or local
    capacity because a key exists somewhere protects no money and blocks the
    free path, which pushes work toward the paid one - the opposite of the
    intent.

    What decides billing is whether the child process can *read* a metered
    credential. So the environment inspected here is the child environment
    (:func:`plan_quota_child_env`): allowlisted, with metered variables removed
    by name. If a metered var can still reach the child, the next run would
    authenticate with it and bill per use -> METERED, and the gate refuses
    exactly as it always did.

    Backends whose stored authentication provenance is unverified stay UNKNOWN.
    Closing the environment path does not prove which stored credential a CLI
    picks up from its own config directory, and that conservatism is retained.
    """
    if _first_set(adapter.metered_env_vars, plan_quota_child_env(adapter, env)):
        return AuthMode.METERED
    if not adapter.stored_plan_auth_verified:
        return AuthMode.UNKNOWN
    return AuthMode.PLAN


def plan_quota_child_env(adapter: PlanQuotaAdapter, env: Mapping[str, str]) -> dict[str, str]:
    """Return the least-privilege runtime and stored-session child environment.

    Allowlist-based, so a credential held for another tool is never forwarded.
    Metered variables are additionally removed by name: the allowlist already
    excludes them, and removing them explicitly keeps that guarantee true even
    if someone later adds a provider variable to the allowlist for an unrelated
    reason.
    """
    metered = {name.upper() for name in adapter.metered_env_vars}
    return {
        key: value
        for key, value in env.items()
        if key.upper() in _PLAN_CHILD_ENV_ALLOWLIST and key.upper() not in metered
    }


def evaluate_plan_quota_safety(adapter: PlanQuotaAdapter, *, env: Mapping[str, str]) -> SafetyDecision:
    """Return the pre-run safety decision for ``adapter``. Deterministic, $0."""
    mode = detect_auth_mode(adapter, env)
    metered_var = _first_set(adapter.metered_env_vars, plan_quota_child_env(adapter, env))

    if mode is AuthMode.METERED:
        return SafetyDecision(
            backend_id=adapter.backend_id,
            safe=False,
            auth_mode=mode,
            requires_ack=False,
            reason=(
                f"{adapter.display_name} cannot execute as plan capacity while {metered_var} is set; "
                "remove the API credential and use verified subscription auth, or use an explicitly budgeted API path"
            ),
        )

    if mode is AuthMode.UNKNOWN:
        return SafetyDecision(
            backend_id=adapter.backend_id,
            safe=False,
            auth_mode=mode,
            requires_ack=False,
            reason=(
                f"{adapter.display_name} stored authentication and provider provenance cannot be proven prepaid or "
                "local before dispatch; use a backend with verified plan auth or an explicitly budgeted API path"
            ),
        )

    if adapter.metered_at_margin:
        return SafetyDecision(
            backend_id=adapter.backend_id,
            safe=False,
            auth_mode=mode,
            requires_ack=False,
            reason=metered_plan_execution_block_reason(adapter),
        )

    if adapter.execution_block_reason:
        return SafetyDecision(
            backend_id=adapter.backend_id,
            safe=False,
            auth_mode=mode,
            requires_ack=False,
            reason=(
                f"{adapter.display_name} execution is disabled: {adapter.execution_block_reason}. "
                "Use a backend with verified no-tool execution or a hardened OS sandbox with an explicit allowlist."
            ),
        )

    note = f"; note: {adapter.tos_note}" if adapter.tos_note else ""
    runtime_note = (
        "; every dispatch also requires a live provider observation proving paid overage is disabled"
        if adapter.requires_live_overage_check
        else ""
    )
    return SafetyDecision(
        backend_id=adapter.backend_id,
        safe=True,
        auth_mode=mode,
        requires_ack=False,
        reason=(
            f"{adapter.display_name} in verified plan mode; prepaid capacity before metered API{runtime_note}{note}"
        ),
    )


def metered_plan_execution_block_reason(adapter: PlanQuotaAdapter) -> str:
    """Explain why a metered-at-margin adapter cannot execute yet."""
    return (
        f"{adapter.display_name} is metered at the margin and cannot execute through plan-quota paths until "
        "the adapter supports deterministic cost estimation, durable reservation, usage settlement, and "
        "canonical cost-ledger writes. Use a non-metered plan backend or an explicitly budgeted API path."
    )


def _first_set(vars_: tuple[str, ...], env: Mapping[str, str]) -> str:
    populated = {key.upper() for key, value in env.items() if value and value.strip()}
    for var in vars_:
        if var.upper() in populated:
            return var
    return ""
