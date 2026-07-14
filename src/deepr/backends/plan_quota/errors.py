"""Shared typed failures for plan-quota dispatch and accounting."""

from __future__ import annotations

from deepr.backends.plan_quota.attempt_accounting import AttemptAccountingError


class PlanQuotaError(RuntimeError):
    """A plan-quota CLI call failed before or after dispatch."""


class PlanQuotaExhausted(PlanQuotaError):
    """The plan-quota CLI reported its quota or credits are exhausted."""


def plan_quota_accounting_error(
    error: AttemptAccountingError,
    *,
    attempt_id: str,
    outcome: str,
    vendor_dispatched: bool,
) -> PlanQuotaError:
    """Convert ledger failure while preserving bounded replay status."""
    converted = PlanQuotaError(str(error))
    converted.__dict__["plan_quota_attempt_id"] = attempt_id
    converted.__dict__["quota_recorded"] = error.status.quota_recorded
    converted.__dict__["cost_recorded"] = error.status.cost_recorded
    converted.__dict__["error_code"] = "plan_quota_accounting_error"
    converted.__dict__["plan_quota_outcome"] = f"{outcome}_accounting_error"
    converted.__dict__["plan_quota_attempt_outcome"] = outcome
    converted.__dict__["vendor_dispatched"] = vendor_dispatched
    converted.__dict__["no_metered_fallback"] = True
    converted.__dict__["retryable"] = False
    return converted
