"""Bounded pre-dispatch ownership for transcript-backed plan CLIs."""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Any
from uuid import uuid4

from filelock import Timeout as FileLockTimeout

from deepr.backends.plan_quota.adapters import PlanQuotaAdapter
from deepr.backends.plan_quota.antigravity_transcript import (
    TranscriptSnapshotError,
    TranscriptSnapshotTimeoutError,
    antigravity_brain_dir,
    transcript_recovery_lock,
    transcript_snapshot,
)
from deepr.backends.plan_quota.attempt_accounting import AttemptAccountingStatus
from deepr.backends.plan_quota.dispatch_boundary import (
    attach_attempt_status,
    run_sync_through_cancellation,
)
from deepr.backends.plan_quota.errors import PlanQuotaError


class TranscriptLease:
    """Cross-process ownership and pre-dispatch transcript identity."""

    def __init__(self, lock: Any, baseline: dict[str, tuple[int, int]]) -> None:
        self.lock = lock
        self.baseline = baseline

    def release(self, *, vendor_dispatched: bool) -> PlanQuotaError | None:
        """Release ownership without allowing a raw lock error to escape."""
        return _release_lock(self.lock, vendor_dispatched=vendor_dispatched)


async def acquire_transcript_lease(
    adapter: PlanQuotaAdapter,
    *,
    deadline: float,
) -> TranscriptLease | None:
    """Serialize transcript dispatch and capture its bounded baseline off-loop."""
    if not adapter.answer_from_transcript:
        return None
    try:
        lock = transcript_recovery_lock()
    except Exception as error:
        raise transcript_pre_dispatch_error("lock initialization", error) from None
    try:
        await _acquire_lock_until(lock, deadline=deadline)
        remaining = remaining_operation_timeout(deadline)
        if remaining <= 0:
            raise transcript_lock_timeout_error()
        snapshot_deadline = time.monotonic() + remaining
        baseline = await run_sync_through_cancellation(
            partial(
                transcript_snapshot,
                antigravity_brain_dir(),
                deadline=snapshot_deadline,
            ),
            propagate_cancellation=True,
        )
        return TranscriptLease(lock, baseline)
    except (PlanQuotaError, asyncio.CancelledError) as error:
        _attach_release_failure(
            error,
            _release_lock(lock, vendor_dispatched=False),
        )
        raise
    except TranscriptSnapshotTimeoutError as error:
        converted = transcript_lock_timeout_error()
        converted.__dict__["plan_quota_transcript_exception"] = error
        _attach_release_failure(
            converted,
            _release_lock(lock, vendor_dispatched=False),
        )
        raise converted from None
    except TranscriptSnapshotError as error:
        converted = transcript_pre_dispatch_error("snapshot", error)
        _attach_release_failure(
            converted,
            _release_lock(lock, vendor_dispatched=False),
        )
        raise converted from None
    except Exception as error:
        converted = transcript_pre_dispatch_error("snapshot", error)
        _attach_release_failure(
            converted,
            _release_lock(lock, vendor_dispatched=False),
        )
        raise converted from None


async def _acquire_lock_until(lock: Any, *, deadline: float) -> None:
    while True:
        try:
            lock.acquire(timeout=0)
            return
        except FileLockTimeout:
            remaining = remaining_operation_timeout(deadline)
            if remaining <= 0:
                raise transcript_lock_timeout_error() from None
            await asyncio.sleep(min(0.05, remaining))
        except Exception as error:
            raise transcript_pre_dispatch_error("lock acquisition", error) from None


def remaining_operation_timeout(deadline: float) -> float:
    return max(0.0, deadline - asyncio.get_running_loop().time())


def transcript_lock_timeout_error() -> PlanQuotaError:
    error = PlanQuotaError("Antigravity transcript dispatch lock timed out")
    error.__dict__.update(
        error_code="transcript_lock_timeout",
        plan_quota_outcome="transcript_lock_timeout",
        retryable=True,
        no_metered_fallback=True,
        vendor_dispatched=False,
    )
    return error


def transcript_pre_dispatch_error(stage: str, error: BaseException) -> PlanQuotaError:
    converted = PlanQuotaError(f"Antigravity transcript {stage} failed ({type(error).__name__})")
    converted.__dict__.update(
        error_code="transcript_pre_dispatch_error",
        plan_quota_outcome="transcript_pre_dispatch_error",
        retryable=True,
        no_metered_fallback=True,
        vendor_dispatched=False,
        plan_quota_transcript_exception=error,
    )
    return converted


def attach_release_failure(
    primary_error: BaseException,
    release_error: PlanQuotaError | None,
) -> None:
    """Preserve a primary failure while exposing path-safe lock uncertainty."""
    _attach_release_failure(primary_error, release_error)


def release_chat_lease(
    lease: TranscriptLease,
    *,
    primary_error: BaseException | None,
    vendor_dispatched: bool,
    attempt_id: str,
    status: AttemptAccountingStatus | None,
) -> None:
    """Release a chat lease while preserving primary and accounting outcomes."""
    release_error = lease.release(vendor_dispatched=vendor_dispatched)
    if release_error is None:
        return
    if primary_error is not None:
        _attach_release_failure(primary_error, release_error)
        return
    if attempt_id and status is not None:
        attach_attempt_status(release_error, attempt_id=attempt_id, status=status)
    raise release_error


def release_probe_lease(
    lease: TranscriptLease,
    *,
    primary_error: BaseException | None,
    probe_result: dict[str, Any] | None,
) -> None:
    """Release a probe lease without violating its ordinary-failure contract."""
    vendor_dispatched = bool(
        probe_result.get("vendor_dispatched", False)
        if probe_result is not None
        else getattr(primary_error, "plan_quota_attempt_id", "")
    )
    release_error = lease.release(vendor_dispatched=vendor_dispatched)
    if release_error is None:
        return
    if primary_error is not None:
        _attach_release_failure(primary_error, release_error)
        return
    if probe_result is None:
        raise release_error
    probe_result["attempt_outcome"] = probe_result.get("outcome", "")
    probe_result["ok"] = False
    probe_result["error"] = str(release_error)
    probe_result["error_code"] = str(release_error.__dict__["error_code"])
    probe_result["outcome"] = str(release_error.__dict__["plan_quota_outcome"])
    probe_result["no_metered_fallback"] = True
    probe_result["vendor_dispatched"] = vendor_dispatched


def _attach_release_failure(
    primary_error: BaseException,
    release_error: PlanQuotaError | None,
) -> None:
    if release_error is None:
        return
    primary_error.__dict__["plan_quota_transcript_release_error"] = release_error
    primary_error.add_note(str(release_error))


def _release_lock(lock: Any, *, vendor_dispatched: bool) -> PlanQuotaError | None:
    try:
        lock.release()
    except Exception as error:
        converted = PlanQuotaError(f"Antigravity transcript lock release failed ({type(error).__name__})")
        converted.__dict__.update(
            error_code="transcript_lock_release_error",
            plan_quota_outcome="transcript_lock_release_error",
            retryable=False,
            no_metered_fallback=True,
            vendor_dispatched=vendor_dispatched,
            plan_quota_transcript_exception=error,
        )
        return converted
    return None


def correlated_transcript_prompt(adapter: PlanQuotaAdapter, prompt: str) -> str:
    """Give transcript-backed attempts an identity external peers cannot reuse."""
    if not adapter.answer_from_transcript:
        return prompt
    return f"{prompt}\n\n[Deepr invocation id: {uuid4().hex}]"
