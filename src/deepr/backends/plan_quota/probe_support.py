"""Post-dispatch recovery and accounting for plan-quota probes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from deepr.backends.plan_quota.adapters import PlanQuotaAdapter, parse_reset_at_utc
from deepr.backends.plan_quota.antigravity_transcript import TranscriptOutputLimitError
from deepr.backends.plan_quota.attempt_accounting import (
    DEFAULT_PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS,
    AttemptAccountingError,
    AttemptAccountingStatus,
    record_plan_quota_attempt,
)
from deepr.backends.plan_quota.cli_runner import CliResult, safe_runtime_error
from deepr.backends.plan_quota.dispatch_boundary import (
    attach_attempt_accounting_error,
    attach_attempt_status,
    run_sync_through_cancellation,
)
from deepr.backends.plan_quota.errors import PlanQuotaError, plan_quota_accounting_error
from deepr.backends.quota_ledger import QuotaEventType


async def run_probe_finish(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run synchronous probe finalization without abandoning cancellation."""
    return await run_sync_through_cancellation(
        operation,
        propagate_cancellation=True,
        on_cancelled_result=_attach_probe_cancellation_result,
    )


def _attach_probe_cancellation_result(
    cancellation_error: asyncio.CancelledError,
    result: dict[str, Any],
) -> None:
    attach_attempt_status(
        cancellation_error,
        attempt_id=str(result["attempt_id"]),
        status=AttemptAccountingStatus(
            quota_recorded=bool(result["quota_observation_recorded"]),
            cost_recorded=bool(result["cost_event_recorded"]),
        ),
    )


def finish_probe_response(
    adapter: PlanQuotaAdapter,
    *,
    result: CliResult,
    expected_prompt: str,
    transcript_baseline: dict[str, tuple[int, int]] | None,
    finish_probe: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Recover one successful probe response and account its final outcome."""
    reply, recovery_error, recovery_outcome = _recover_probe_reply(
        adapter,
        result=result,
        expected_prompt=expected_prompt,
        transcript_baseline=transcript_baseline,
    )
    if recovery_error:
        return finish_probe(
            ok=False,
            reply="",
            error=recovery_error,
            outcome=recovery_outcome,
            quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
            quota_units=None,
            vendor_dispatched=True,
            detail=(
                "probe CLI transcript output exceeded the capture limit; quota usage is unknown"
                if recovery_outcome == "output_limit_exceeded"
                else "probe CLI completed but answer recovery failed; quota usage is unknown"
            ),
        )
    if not reply:
        return finish_probe(
            ok=False,
            reply="",
            error="no output",
            outcome="empty_output",
            quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
            quota_units=None,
            vendor_dispatched=True,
            detail="probe CLI exited successfully but returned no answer; quota usage is unknown",
        )
    return finish_probe(
        ok=True,
        reply=reply,
        error="",
        outcome="success",
        quota_event_type=QuotaEventType.USAGE_OBSERVED,
        quota_units=1.0,
        vendor_dispatched=True,
        detail="probe-plan successful plan call",
    )


def account_probe_dispatch_error(
    adapter: PlanQuotaAdapter,
    primary_error: BaseException,
    *,
    attempt_id: str,
    model: str | None,
    quota_ledger_path: Path | None,
    cost_ledger_path: Path | None,
    outcome: str,
    context: str,
) -> None:
    """Record a probe error after the dispatch boundary was entered."""
    try:
        status = _record_probe_attempt(
            adapter,
            attempt_id=attempt_id,
            model=model,
            quota_ledger_path=quota_ledger_path,
            cost_ledger_path=cost_ledger_path,
            outcome=outcome,
            quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
            quota_units=None,
            vendor_dispatched=True,
            detail=f"probe CLI attempt ended with {context} after entering the dispatch boundary; quota usage is unknown",
        )
        attach_attempt_status(primary_error, attempt_id=attempt_id, status=status)
    except PlanQuotaError as accounting_error:
        attach_attempt_accounting_error(
            primary_error,
            attempt_id=attempt_id,
            accounting_error=accounting_error,
            context=f"probe {context}",
        )


def safe_probe_runner_error_result(
    adapter: PlanQuotaAdapter,
    runner_error: BaseException,
    *,
    attempt_id: str,
) -> dict[str, Any]:
    """Return a sanitized probe result for an exception at the runner seam."""
    return {
        "ok": False,
        "backend": adapter.backend_id,
        "reply": "",
        "latency_ms": 0,
        "error": f"{adapter.exe} {safe_runtime_error(runner_error)}",
        "outcome": "runner_error",
        "vendor_dispatched": True,
        "attempt_id": attempt_id,
        "cost_event_recorded": bool(getattr(runner_error, "cost_recorded", False)),
        "quota_observation_recorded": bool(getattr(runner_error, "quota_recorded", False)),
    }


def finish_probe_attempt(
    adapter: PlanQuotaAdapter,
    *,
    attempt_id: str,
    model: str | None,
    quota_ledger_path: Path | None,
    cost_ledger_path: Path | None,
    result: CliResult,
    ok: bool,
    reply: str,
    error: str,
    outcome: str,
    quota_event_type: QuotaEventType | None,
    quota_units: float | None,
    vendor_dispatched: bool,
    detail: str,
    reset_at: datetime | None = None,
) -> dict[str, Any]:
    """Persist one probe outcome and expose paired-ledger status."""
    ledger_error = ""
    final_outcome = outcome
    error_code = outcome
    try:
        status = _record_probe_attempt(
            adapter,
            attempt_id=attempt_id,
            model=model,
            quota_ledger_path=quota_ledger_path,
            cost_ledger_path=cost_ledger_path,
            outcome=outcome,
            quota_event_type=quota_event_type,
            quota_units=quota_units,
            vendor_dispatched=vendor_dispatched,
            detail=detail,
            reset_at=reset_at,
        )
    except PlanQuotaError as accounting_error:
        status = AttemptAccountingStatus(
            quota_recorded=bool(getattr(accounting_error, "quota_recorded", False)),
            cost_recorded=bool(getattr(accounting_error, "cost_recorded", False)),
        )
        ledger_error = str(accounting_error)
        final_outcome = str(getattr(accounting_error, "plan_quota_outcome", "plan_quota_accounting_error"))
        error_code = str(getattr(accounting_error, "error_code", "plan_quota_accounting_error"))
    if ledger_error:
        error = f"{error}; {ledger_error}" if error else ledger_error
        ok = False
    response = {
        "ok": ok,
        "backend": adapter.backend_id,
        "reply": reply,
        "latency_ms": result.duration_ms,
        "error": error,
        "outcome": final_outcome,
        "vendor_dispatched": vendor_dispatched,
        "attempt_id": attempt_id,
        "cost_event_recorded": status.cost_recorded,
        "quota_observation_recorded": status.quota_recorded,
    }
    if ledger_error:
        response["error_code"] = error_code
        response["attempt_outcome"] = outcome
        response["no_metered_fallback"] = True
    return response


def _record_probe_attempt(
    adapter: PlanQuotaAdapter,
    *,
    attempt_id: str,
    model: str | None,
    quota_ledger_path: Path | None,
    cost_ledger_path: Path | None,
    outcome: str,
    quota_event_type: QuotaEventType | None,
    quota_units: float | None,
    vendor_dispatched: bool,
    detail: str,
    reset_at: datetime | None = None,
) -> AttemptAccountingStatus:
    try:
        return record_plan_quota_attempt(
            adapter,
            attempt_id=attempt_id,
            operation="plan_quota_probe",
            model=model,
            quota_ledger_path=quota_ledger_path,
            cost_ledger_path=cost_ledger_path,
            outcome=outcome,
            quota_event_type=quota_event_type,
            quota_units=quota_units,
            vendor_dispatched=vendor_dispatched,
            detail=detail,
            reset_at=reset_at,
            lock_timeout_seconds=DEFAULT_PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS,
        )
    except AttemptAccountingError as error:
        raise plan_quota_accounting_error(
            error,
            attempt_id=attempt_id,
            outcome=outcome,
            vendor_dispatched=vendor_dispatched,
        ) from error.primary_cause


def reset_at_from_output(text: str) -> datetime | None:
    """Parse an optional vendor reset timestamp from exhaustion output."""
    return parse_reset_at_utc(text)


def _recover_probe_reply(
    adapter: PlanQuotaAdapter,
    *,
    result: CliResult,
    expected_prompt: str,
    transcript_baseline: dict[str, tuple[int, int]] | None,
) -> tuple[str, str, str]:
    try:
        if adapter.answer_from_transcript:
            from deepr.backends.plan_quota.antigravity_transcript import antigravity_brain_dir, recover_answer

            return (
                recover_answer(
                    antigravity_brain_dir(),
                    baseline=transcript_baseline or {},
                    expected_prompt=expected_prompt,
                )
                or "",
                "",
                "",
            )
        return adapter.parse_answer(result.stdout), "", ""
    except TranscriptOutputLimitError:
        return "", "transcript output limit exceeded", "output_limit_exceeded"
    except Exception as error:
        return "", f"answer recovery failed ({type(error).__name__})", "post_dispatch_error"
