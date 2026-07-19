"""Live paid-overage guard for subscription-backed CLI dispatch.

Static environment checks can prove that a CLI is not using an API key, but
some subscription accounts can automatically continue on paid usage credits.
Adapters with that billing mode must prove the provider-reported overage switch
is off immediately before every model dispatch.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from deepr.backends.plan_quota.adapters import PlanQuotaAdapter
from deepr.backends.plan_quota.quota_probes import collect_plan_quota_snapshot
from deepr.backends.quota_ledger import QuotaLedger
from deepr.backends.quota_snapshot import QuotaSnapshot, snapshot_to_ledger_event


class QuotaSnapshotCollector(Protocol):
    """Callable shape for metadata-only provider quota collectors."""

    def __call__(
        self,
        backend_id: str,
        *,
        claude_config_dir: Path | None = None,
    ) -> QuotaSnapshot: ...


class PlanQuotaOverageGuardError(RuntimeError):
    """A plan call could not prove that paid overage was disabled."""

    def __init__(self, message: str, *, observation_recorded: bool = False) -> None:
        super().__init__(message)
        self.observation_recorded = observation_recorded


async def require_paid_overage_disabled(
    adapter: PlanQuotaAdapter,
    *,
    env: Mapping[str, str],
    quota_ledger_path: Path | None,
    collector: QuotaSnapshotCollector | None = None,
) -> bool | None:
    """Return False after a durable live proof, or None when not required.

    The metadata observation is written before evaluating it so both refusal
    and admission remain auditable. Any read or ledger failure stops before the
    vendor model process starts.
    """
    if not adapter.requires_live_overage_check:
        return None

    resolved_collector: QuotaSnapshotCollector = collector or collect_plan_quota_snapshot
    config_dir = env.get("CLAUDE_CONFIG_DIR", "").strip()

    try:
        if adapter.backend_id == "claude" and config_dir:
            snapshot = await asyncio.to_thread(
                resolved_collector,
                adapter.backend_id,
                claude_config_dir=Path(config_dir).expanduser(),
            )
        else:
            snapshot = await asyncio.to_thread(resolved_collector, adapter.backend_id)
    except Exception as error:
        raise PlanQuotaOverageGuardError(
            f"{adapter.display_name} live paid-overage check failed ({type(error).__name__}); vendor not dispatched"
        ) from None

    if snapshot.backend_id != adapter.backend_id:
        raise PlanQuotaOverageGuardError(
            f"{adapter.display_name} live paid-overage check returned the wrong backend; vendor not dispatched"
        )

    try:
        event = snapshot_to_ledger_event(snapshot)
        QuotaLedger(quota_ledger_path).record_event(event, require_fsync=True)
    except Exception as error:
        raise PlanQuotaOverageGuardError(
            f"{adapter.display_name} paid-overage observation could not be durably recorded "
            f"({type(error).__name__}); vendor not dispatched"
        ) from None

    if not snapshot.ok or snapshot.overage_enabled is None:
        raise PlanQuotaOverageGuardError(
            f"{adapter.display_name} did not prove that paid extra usage is disabled; vendor not dispatched",
            observation_recorded=True,
        )
    if snapshot.overage_enabled:
        raise PlanQuotaOverageGuardError(
            f"{adapter.display_name} reports paid extra usage enabled; disable it before using plan capacity",
            observation_recorded=True,
        )
    return False


__all__ = [
    "PlanQuotaOverageGuardError",
    "QuotaSnapshotCollector",
    "require_paid_overage_disabled",
]
