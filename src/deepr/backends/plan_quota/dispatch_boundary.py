"""Shared post-dispatch exception accounting for plan-quota runners."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from functools import partial
from typing import TypeVar

from deepr.backends.plan_quota.attempt_accounting import AttemptAccountingStatus
from deepr.backends.plan_quota.cli_runner import CliResult

Runner = Callable[..., Awaitable[CliResult]]
ErrorObserver = Callable[[BaseException], None]
logger = logging.getLogger(__name__)
T = TypeVar("T")


def copy_attempt_context(target: BaseException, source: BaseException) -> None:
    """Copy non-secret replay/status attributes without rendering the source."""
    for attribute in (
        "plan_quota_attempt_id",
        "quota_recorded",
        "cost_recorded",
        "plan_quota_accounting_error",
    ):
        if attribute in source.__dict__:
            target.__dict__[attribute] = source.__dict__[attribute]


async def run_sync_through_cancellation(
    operation: Callable[[], T],
    *,
    propagate_cancellation: bool,
    on_cancelled_result: Callable[[asyncio.CancelledError, T], None] | None = None,
) -> T:
    """Own one thread operation to completion without blocking the event loop."""
    task = asyncio.create_task(asyncio.to_thread(operation), name="plan-quota-durable-accounting")
    cancellation_error: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            if cancellation_error is None:
                cancellation_error = error
        except BaseException:
            break
    if cancellation_error is not None and propagate_cancellation:
        try:
            result = task.result()
        except BaseException as operation_error:
            cancellation_error.__dict__["plan_quota_post_dispatch_error"] = operation_error
            copy_attempt_context(cancellation_error, operation_error)
        else:
            if on_cancelled_result is not None:
                on_cancelled_result(cancellation_error, result)
        raise cancellation_error from None
    return task.result()


def attach_attempt_status(
    primary_error: BaseException,
    *,
    attempt_id: str,
    status: AttemptAccountingStatus,
) -> None:
    """Expose replay identity and paired-ledger status on a primary error."""
    primary_error.__dict__["plan_quota_attempt_id"] = attempt_id
    primary_error.__dict__["quota_recorded"] = status.quota_recorded
    primary_error.__dict__["cost_recorded"] = status.cost_recorded


def attach_attempt_accounting_error(
    primary_error: BaseException,
    *,
    attempt_id: str,
    accounting_error: BaseException,
    context: str,
) -> None:
    """Keep the primary failure while exposing bounded partial accounting."""
    attach_attempt_status(
        primary_error,
        attempt_id=attempt_id,
        status=AttemptAccountingStatus(
            quota_recorded=bool(getattr(accounting_error, "quota_recorded", False)),
            cost_recorded=bool(getattr(accounting_error, "cost_recorded", False)),
        ),
    )
    primary_error.__dict__["plan_quota_accounting_error"] = accounting_error
    primary_error.add_note(f"plan-quota {context} accounting failed for attempt {attempt_id}: {accounting_error}")
    logger.error(
        "plan-quota %s accounting failed for attempt %s: %s",
        context,
        attempt_id,
        accounting_error,
    )


async def dispatch_runner_with_accounting(
    runner: Runner,
    argv: list[str],
    *,
    stdin: str | None,
    timeout: float,
    env: Mapping[str, object] | None,
    cwd: str | None,
    on_cancelled: ErrorObserver,
    on_error: ErrorObserver,
) -> CliResult:
    """Dispatch once and observe every ambiguous post-boundary exception."""
    try:
        return await runner(
            argv,
            stdin=stdin,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )
    except asyncio.CancelledError as cancellation_error:
        await run_sync_through_cancellation(
            partial(on_cancelled, cancellation_error),
            propagate_cancellation=False,
        )
        raise
    except Exception as runner_error:
        await run_sync_through_cancellation(
            partial(on_error, runner_error),
            propagate_cancellation=False,
        )
        raise
