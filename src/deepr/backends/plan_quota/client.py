"""Driving a plan-quota CLI as a Deepr chat backend.

``PlanQuotaChatClient`` adapts a vendor CLI to the *minimal* async chat surface
Deepr's seams already use - ``client.chat.completions.create(model=, messages=)``
returning an object with ``.choices[0].message.content`` - exactly like
``ollama_chat_client`` does for a local model. Because it satisfies that one
surface, a single instance serves *both* the research answer and the
verification-gated belief extraction in ``ReportAbsorber``, so ``expert sync
--plan <id>`` runs end to end on prepaid capacity with no silent metered call.

Every eligible non-metered dispatch records one $0 cost-ledger event when
canonical storage succeeds, including nonzero, timeout, cancellation, and
empty-output outcomes, so ``costs show`` and anomaly detection see the whole
attempt volume. A canonical write failure fails closed on ordinary results and
remains attached to cancellation with the attempt id. Quota observations
distinguish known usage, exhaustion, and attempts whose usage remains unknown;
a process that never launched does not claim quota use. Metered-at-margin
adapters fail before client setup or subprocess dispatch until they support
estimate, reservation, usage settlement, and canonical cost-ledger accounting.
An exhaustion signature in the CLI output is recorded as a terminal quota event
and surfaced as an error so the scheduler reschedules instead of silently
failing.

``make_plan_quota_research_fn`` wraps the same client as the ``research_fn`` seam
``(query, budget) -> {"answer", "cost", ...}`` (report, never raise).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, NoReturn
from uuid import uuid4

from deepr.backends.context_building import (
    ContextBuilder,
    build_context,
    context_evidence_fields,
    context_generation_readiness,
    context_not_ready_error,
)
from deepr.backends.local import _local_prompt  # shared research-prompt builder
from deepr.backends.plan_quota import output_safety, prompt_delivery
from deepr.backends.plan_quota.adapters import PlanQuotaAdapter, parse_reset_at_utc
from deepr.backends.plan_quota.antigravity_transcript import TranscriptOutputLimitError
from deepr.backends.plan_quota.attempt_accounting import (
    DEFAULT_PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS as _PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS,
)
from deepr.backends.plan_quota.attempt_accounting import (
    AttemptAccountingError,
    AttemptAccountingStatus,
    record_plan_quota_attempt,
)
from deepr.backends.plan_quota.cli_runner import (
    DEFAULT_TIMEOUT_S,
    CliResult,
    run_cli,
    safe_runtime_error,
    validate_timeout,
)
from deepr.backends.plan_quota.dispatch_boundary import (
    attach_attempt_accounting_error,
    attach_attempt_status,
    copy_attempt_context,
    dispatch_runner_with_accounting,
    run_sync_through_cancellation,
)
from deepr.backends.plan_quota.errors import PlanQuotaError, PlanQuotaExhausted
from deepr.backends.plan_quota.errors import (
    plan_quota_accounting_error as _plan_quota_accounting_error,
)
from deepr.backends.plan_quota.probe_support import (
    account_probe_dispatch_error as _account_probe_dispatch_error,
)
from deepr.backends.plan_quota.probe_support import (
    finish_probe_attempt as _finish_probe_attempt,
)
from deepr.backends.plan_quota.probe_support import (
    finish_probe_response as _finish_probe_response,
)
from deepr.backends.plan_quota.probe_support import (
    reset_at_from_output as _reset_at_from_output,
)
from deepr.backends.plan_quota.probe_support import (
    run_probe_finish as _run_probe_finish,
)
from deepr.backends.plan_quota.probe_support import (
    safe_probe_runner_error_result as _safe_probe_runner_error_result,
)
from deepr.backends.plan_quota.response import PlanQuotaResponse
from deepr.backends.plan_quota.safety import evaluate_plan_quota_safety, plan_quota_child_env
from deepr.backends.plan_quota.transcript_dispatch import (
    TranscriptLease as _TranscriptLease,
)
from deepr.backends.plan_quota.transcript_dispatch import (
    acquire_transcript_lease as _acquire_transcript_lease,
)
from deepr.backends.plan_quota.transcript_dispatch import (
    correlated_transcript_prompt as _correlated_transcript_prompt,
)
from deepr.backends.plan_quota.transcript_dispatch import (
    release_chat_lease as _release_chat_lease,
)
from deepr.backends.plan_quota.transcript_dispatch import (
    release_probe_lease as _release_probe_lease,
)
from deepr.backends.plan_quota.transcript_dispatch import (
    remaining_operation_timeout as _remaining_operation_timeout,
)
from deepr.backends.plan_quota.transcript_dispatch import (
    transcript_lock_timeout_error as _transcript_lock_timeout_error,
)
from deepr.backends.quota_ledger import QuotaEventType
from deepr.utils.security import sanitize_log_message

ResearchFn = Callable[[str, float], Awaitable[dict[str, Any]]]
CliRunner = Callable[..., Awaitable[CliResult]]
_build_invocation = prompt_delivery.build_invocation
_cleanup_prompt_file = prompt_delivery.cleanup_prompt_file
_exhaustion_output = output_safety.exhaustion_output
_flatten_messages = prompt_delivery.flatten_messages
_safe_cli_error_summary = output_safety.safe_cli_error_summary


def _safe_runner_boundary_error(
    adapter: PlanQuotaAdapter,
    runner_error: BaseException,
) -> PlanQuotaError:
    converted = PlanQuotaError(f"{adapter.exe} {safe_runtime_error(runner_error)}")
    copy_attempt_context(converted, runner_error)
    converted.__dict__["plan_quota_runner_exception"] = runner_error
    converted.__dict__.update(
        error_code="runner_error",
        plan_quota_outcome="runner_error",
        retryable=False,
        no_metered_fallback=True,
        vendor_dispatched=True,
    )
    return converted


def _attach_chat_cancellation_result(
    cancellation_error: asyncio.CancelledError,
    result: tuple[str, AttemptAccountingStatus],
    *,
    attempt_id: str,
) -> None:
    attach_attempt_status(
        cancellation_error,
        attempt_id=attempt_id,
        status=result[1],
    )


class _Completions:
    def __init__(self, client: PlanQuotaChatClient) -> None:
        self._client = client

    async def create(self, **kwargs: Any) -> PlanQuotaResponse:
        return await self._client._run_chat(kwargs)


class _Chat:
    def __init__(self, client: PlanQuotaChatClient) -> None:
        self.completions = _Completions(client)


class PlanQuotaChatClient:
    """An AsyncOpenAI-shaped chat client backed by a vendor CLI subprocess."""

    def __init__(
        self,
        adapter: PlanQuotaAdapter,
        *,
        model: str | None = None,
        runner: CliRunner = run_cli,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        account_id: str = "",
        quota_ledger_path: Path | None = None,
        cost_ledger_path: Path | None = None,
        operation: str = "plan_quota_research",
    ) -> None:
        try:
            validated_timeout = validate_timeout(timeout)
        except ValueError as error:
            raise PlanQuotaError(str(error)) from None
        resolved_env = env if env is not None else dict(os.environ)
        decision = evaluate_plan_quota_safety(adapter, env=resolved_env)
        if not decision.safe:
            raise PlanQuotaError(decision.reason)
        self.adapter = adapter
        self.model = model
        self._runner = runner
        self._env = plan_quota_child_env(adapter, resolved_env)
        self._cwd = cwd
        self._timeout = validated_timeout
        self._account_id = account_id
        self._quota_ledger_path = quota_ledger_path
        self._cost_ledger_path = cost_ledger_path
        self._operation = operation
        self.chat = _Chat(self)

    async def _run_chat(self, kwargs: dict[str, Any]) -> PlanQuotaResponse:
        messages = kwargs.get("messages") or []
        wants_json = (kwargs.get("response_format") or {}).get("type") == "json_object"
        prompt = _correlated_transcript_prompt(
            self.adapter,
            _flatten_messages(messages, wants_json=wants_json),
        )
        # Ignore the caller's model name: Deepr's internal ids (e.g. gpt-5-mini)
        # are meaningless to a vendor CLI, which uses its plan's model or the
        # operator's explicit --plan-model. Passing the wrong --model would fail.
        model = self.model
        deadline = asyncio.get_running_loop().time() + self._timeout
        transcript_lease = await _acquire_transcript_lease(self.adapter, deadline=deadline)
        dispatch_entered = False
        attempt_id = ""
        accounted: tuple[str, AttemptAccountingStatus] | None = None
        primary_error: BaseException | None = None
        try:
            argv, stdin, temp_path = _build_invocation(self.adapter, prompt, model)
            try:
                dispatch_timeout = _remaining_operation_timeout(deadline)
                if dispatch_timeout <= 0:
                    raise _transcript_lock_timeout_error()
                attempt_id = f"plan-quota:{self.adapter.backend_id}:{uuid4().hex}"
                try:
                    dispatch_entered = True
                    result = await dispatch_runner_with_accounting(
                        self._runner,
                        argv,
                        stdin=stdin,
                        timeout=dispatch_timeout,
                        env=self._env,
                        cwd=self._cwd,
                        on_cancelled=partial(
                            self._account_dispatch_error,
                            attempt_id=attempt_id,
                            outcome="cancelled",
                            context="cancellation",
                        ),
                        on_error=partial(
                            self._account_dispatch_error,
                            attempt_id=attempt_id,
                            outcome="runner_error",
                            context="runner error",
                        ),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as runner_error:
                    raise _safe_runner_boundary_error(
                        self.adapter,
                        runner_error,
                    ) from None
            finally:
                _cleanup_prompt_file(temp_path)
            completed_accounting = await run_sync_through_cancellation(
                partial(
                    self._complete_chat_attempt,
                    result,
                    attempt_id=attempt_id,
                    prompt=prompt,
                    transcript_baseline=transcript_lease.baseline if transcript_lease is not None else None,
                ),
                propagate_cancellation=True,
                on_cancelled_result=partial(
                    _attach_chat_cancellation_result,
                    attempt_id=attempt_id,
                ),
            )
            accounted = completed_accounting
            return PlanQuotaResponse(completed_accounting[0])
        except BaseException as error:
            primary_error = error
            raise
        finally:
            if transcript_lease is not None:
                _release_chat_lease(
                    transcript_lease,
                    primary_error=primary_error,
                    vendor_dispatched=dispatch_entered,
                    attempt_id=attempt_id,
                    status=accounted[1] if accounted is not None else None,
                )

    def _complete_chat_attempt(
        self,
        result: CliResult,
        *,
        attempt_id: str,
        prompt: str,
        transcript_baseline: dict[str, tuple[int, int]] | None,
    ) -> tuple[str, AttemptAccountingStatus]:
        """Recover, interpret, and account one completed CLI result off-loop."""
        answer_override = None
        if result.ok and _exhaustion_output(self.adapter, result) is None:
            try:
                answer_override = self._recover_transcript_answer(
                    transcript_baseline=transcript_baseline,
                    expected_prompt=prompt,
                )
            except TranscriptOutputLimitError:
                self._fail_attempt(
                    PlanQuotaError,
                    f"{self.adapter.exe} transcript output limit exceeded",
                    attempt_id=attempt_id,
                    outcome="output_limit_exceeded",
                    quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                    quota_units=None,
                    vendor_dispatched=True,
                    detail="CLI transcript output exceeded the capture limit; quota usage is unknown",
                )
            except Exception as error:
                self._fail_attempt(
                    PlanQuotaError,
                    f"{self.adapter.exe} transcript recovery failed ({type(error).__name__})",
                    attempt_id=attempt_id,
                    outcome="post_dispatch_error",
                    quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                    quota_units=None,
                    vendor_dispatched=True,
                    detail="CLI completed but answer recovery failed; quota usage is unknown",
                )
        try:
            accounted = self._interpret(
                result,
                attempt_id=attempt_id,
                answer_override=answer_override,
                prompt=prompt,
            )
        except PlanQuotaError:
            raise
        except Exception as error:
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} response interpretation failed ({type(error).__name__})",
                attempt_id=attempt_id,
                outcome="post_dispatch_error",
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail="CLI completed but response interpretation failed; quota usage is unknown",
            )
        return accounted

    def _account_dispatch_error(
        self,
        primary_error: BaseException,
        *,
        attempt_id: str,
        outcome: str,
        context: str,
    ) -> None:
        try:
            status = self._record_attempt(
                attempt_id=attempt_id,
                outcome=outcome,
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail=f"CLI attempt ended with {context} after entering the dispatch boundary; quota usage is unknown",
                lock_timeout_seconds=_PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS,
            )
            attach_attempt_status(
                primary_error,
                attempt_id=attempt_id,
                status=status,
            )
        except PlanQuotaError as accounting_error:
            attach_attempt_accounting_error(
                primary_error,
                attempt_id=attempt_id,
                accounting_error=accounting_error,
                context=context,
            )

    def _recover_transcript_answer(
        self,
        *,
        transcript_baseline: dict[str, tuple[int, int]] | None,
        expected_prompt: str,
    ) -> str | None:
        """Read the answer from the CLI's transcript when it drops stdout.

        Antigravity exits 0 with empty stdout under a non-TTY pipe; its reply is
        only in its per-conversation transcript. None means "use stdout" (every
        other CLI) or "no transcript answer found" (which then fails as no output).
        """
        if not self.adapter.answer_from_transcript:
            return None
        from deepr.backends.plan_quota.antigravity_transcript import antigravity_brain_dir, recover_answer

        return recover_answer(
            antigravity_brain_dir(),
            baseline=transcript_baseline or {},
            expected_prompt=expected_prompt,
        )

    def _interpret(
        self,
        result: CliResult,
        *,
        attempt_id: str,
        answer_override: str | None = None,
        prompt: str = "",
    ) -> tuple[str, AttemptAccountingStatus]:
        """Turn a CliResult into an answer or raise a typed error. Records quota.

        ``answer_override`` supplies the answer when the CLI does not print it to
        stdout (Antigravity, recovered from its transcript). None means parse
        stdout as usual.
        """
        if result.launch_error and result.cleanup_error:
            self._fail_attempt(
                PlanQuotaError,
                (
                    f"{self.adapter.exe} failed to launch and process cleanup was not confirmed: "
                    f"{sanitize_log_message(result.cleanup_error)}"
                ),
                attempt_id=attempt_id,
                outcome="cleanup_error",
                quota_event_type=None,
                quota_units=None,
                vendor_dispatched=False,
                detail="CLI ownership setup failed and pre-dispatch cleanup could not be confirmed",
                primary_cause=result.cleanup_exception,
            )
        if result.launch_error:
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} failed to launch: {sanitize_log_message(result.launch_error)}",
                attempt_id=attempt_id,
                outcome="launch_error",
                quota_event_type=None,
                quota_units=None,
                vendor_dispatched=False,
                detail="CLI process did not launch; no quota usage observed",
            )
        if result.runtime_error:
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} {result.runtime_error}",
                attempt_id=attempt_id,
                outcome=result.runtime_failure_outcome,
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail=result.runtime_failure_detail,
                primary_cause=result.runtime_exception,
            )
        # Exhaustion is an error condition. Broad legacy signatures may inspect
        # all failed output, but vendor phrases that can also occur in ordinary
        # answer text are registered as error-channel-only and inspect stderr.
        # Successful stdout is never scanned.
        exhaustion_text = _exhaustion_output(self.adapter, result)
        if exhaustion_text is not None:
            reset_at = self._reset_at_from(exhaustion_text)
            when = f" (resets ~{reset_at:%H:%M UTC})" if reset_at else ""
            self._fail_attempt(
                PlanQuotaExhausted,
                f"{self.adapter.display_name} quota appears exhausted - reschedule after reset{when}",
                attempt_id=attempt_id,
                outcome="exhausted",
                quota_event_type=QuotaEventType.EXHAUSTED,
                quota_units=None,
                vendor_dispatched=True,
                detail="exhaustion signature in CLI output",
                reset_at=reset_at,
            )
        if result.timed_out:
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} timed out after {self._timeout:.0f}s",
                attempt_id=attempt_id,
                outcome="timeout",
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail="CLI attempt timed out; quota usage is unknown",
            )
        if not result.ok:
            summary = _safe_cli_error_summary(result.stderr, prompt=prompt)
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} exited {result.returncode}: {summary}",
                attempt_id=attempt_id,
                outcome="nonzero_exit",
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail=f"CLI attempt exited {result.returncode}; quota usage is unknown",
            )

        answer = answer_override if answer_override is not None else self.adapter.parse_answer(result.stdout)
        if not answer:
            hint = (
                " (agy drops stdout under a non-TTY pipe; transcript recovery found no answer)"
                if self.adapter.needs_pty
                else ""
            )
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} returned no output{hint}",
                attempt_id=attempt_id,
                outcome="empty_output",
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail="CLI exited successfully but returned no answer; quota usage is unknown",
            )

        status = self._record_attempt(
            attempt_id=attempt_id,
            outcome="success",
            quota_event_type=QuotaEventType.USAGE_OBSERVED,
            quota_units=1.0,
            vendor_dispatched=True,
            detail="one successful plan-quota call",
        )
        return answer, status

    def _reset_at_from(self, text: str) -> datetime | None:
        return parse_reset_at_utc(text)

    def _fail_attempt(
        self,
        error_type: type[PlanQuotaError],
        message: str,
        *,
        attempt_id: str,
        outcome: str,
        quota_event_type: QuotaEventType | None,
        quota_units: float | None,
        vendor_dispatched: bool,
        detail: str,
        reset_at: datetime | None = None,
        primary_cause: BaseException | None = None,
    ) -> NoReturn:
        """Record a failed attempt, then preserve its primary typed failure."""
        accounting_error: PlanQuotaError | None = None
        try:
            status = self._record_attempt(
                attempt_id=attempt_id,
                outcome=outcome,
                quota_event_type=quota_event_type,
                quota_units=quota_units,
                vendor_dispatched=vendor_dispatched,
                detail=detail,
                reset_at=reset_at,
            )
        except PlanQuotaError as error:
            accounting_error = error
            message = f"{message}; {accounting_error}"
            status = AttemptAccountingStatus(
                quota_recorded=bool(getattr(error, "quota_recorded", False)),
                cost_recorded=bool(getattr(error, "cost_recorded", False)),
            )
        primary_error = error_type(message)
        attach_attempt_status(
            primary_error,
            attempt_id=attempt_id,
            status=status,
        )
        primary_error.__dict__["plan_quota_outcome"] = outcome
        primary_error.__dict__["error_code"] = outcome
        primary_error.__dict__["retryable"] = error_type is PlanQuotaExhausted
        primary_error.__dict__["no_metered_fallback"] = True
        primary_error.__dict__["vendor_dispatched"] = vendor_dispatched
        if accounting_error is not None:
            primary_error.__dict__["plan_quota_accounting_error"] = accounting_error
        if primary_cause is not None:
            primary_error.__dict__["plan_quota_runner_exception"] = primary_cause
        raise primary_error

    def _record_attempt(
        self,
        *,
        attempt_id: str,
        outcome: str,
        quota_event_type: QuotaEventType | None,
        quota_units: float | None,
        vendor_dispatched: bool,
        detail: str,
        reset_at: datetime | None = None,
        lock_timeout_seconds: float | None = None,
    ) -> AttemptAccountingStatus:
        try:
            return record_plan_quota_attempt(
                self.adapter,
                attempt_id=attempt_id,
                operation=self._operation,
                model=self.model,
                account_id=self._account_id,
                quota_ledger_path=self._quota_ledger_path,
                cost_ledger_path=self._cost_ledger_path,
                outcome=outcome,
                quota_event_type=quota_event_type,
                quota_units=quota_units,
                vendor_dispatched=vendor_dispatched,
                detail=detail,
                reset_at=reset_at,
                lock_timeout_seconds=lock_timeout_seconds,
            )
        except AttemptAccountingError as error:
            raise _plan_quota_accounting_error(
                error,
                attempt_id=attempt_id,
                outcome=outcome,
                vendor_dispatched=vendor_dispatched,
            ) from error.primary_cause


def make_plan_quota_research_fn(
    adapter: PlanQuotaAdapter,
    *,
    model: str | None = None,
    context_builder: ContextBuilder | None = None,
    client: PlanQuotaChatClient | None = None,
    **client_kwargs: Any,
) -> ResearchFn:
    """Build a ``research_fn`` that answers via a plan-quota CLI at $0 marginal.

    Satisfies the sync/gap-fill seam ``(query, budget) -> {"answer", "cost"}``.
    ``cost`` is always 0.0 (prepaid plan capacity); ``budget`` is ignored. Errors
    are returned in the result, never raised, per the seam contract.
    """
    chat = client if client is not None else PlanQuotaChatClient(adapter, model=model, **client_kwargs)

    async def research_fn(
        query: str,
        budget: float,
        *,
        prior_source_pack: dict[str, Any] | None = None,
        retrieval_query: str | None = None,
    ) -> dict[str, Any]:
        try:
            context = await build_context(
                context_builder,
                retrieval_query or query,
                prior_source_pack=prior_source_pack,
            )
            evidence_fields = context_evidence_fields(context)
            readiness = context_generation_readiness(context)
            if readiness is not None and not readiness.ready:
                return {
                    "answer": "",
                    "cost": 0.0,
                    "backend": f"plan_quota:{adapter.backend_id}",
                    "error": context_not_ready_error(readiness),
                    "error_code": "fresh_context_not_ready",
                    "retryable": readiness.retryable,
                    "no_metered_fallback": readiness.no_metered_fallback,
                    "context_preflight": readiness.to_dict(),
                    **evidence_fields,
                }
            prompt, metadata = _local_prompt(query, context)
            response = await chat.chat.completions.create(
                model=model or "",
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.choices[0].message.content or ""
            result: dict[str, Any] = {"answer": answer, "cost": 0.0, "backend": f"plan_quota:{adapter.backend_id}"}
            result.update(evidence_fields)
            if metadata is not None and "fresh_context" not in result:
                result["fresh_context"] = metadata
            return result
        except PlanQuotaError as error:
            return _plan_quota_research_error_result(adapter, error)
        except Exception as e:  # seam contract: report, do not raise
            return {
                "answer": "",
                "cost": 0.0,
                "error": f"{adapter.backend_id} backend error: {e}",
                "error_code": "plan_quota_backend_error",
                "retryable": False,
                "no_metered_fallback": True,
            }

    return research_fn


def _plan_quota_research_error_result(
    adapter: PlanQuotaAdapter,
    error: PlanQuotaError,
) -> dict[str, Any]:
    """Preserve typed no-fallback and accounting state across the research seam."""
    outcome = str(getattr(error, "plan_quota_outcome", "plan_quota_error"))
    result: dict[str, Any] = {
        "answer": "",
        "cost": 0.0,
        "backend": f"plan_quota:{adapter.backend_id}",
        "error": str(error),
        "error_code": str(getattr(error, "error_code", outcome)),
        "outcome": outcome,
        "retryable": bool(getattr(error, "retryable", False)),
        "no_metered_fallback": bool(getattr(error, "no_metered_fallback", True)),
        "vendor_dispatched": bool(getattr(error, "vendor_dispatched", False)),
        "attempt_id": str(getattr(error, "plan_quota_attempt_id", "")),
        "quota_observation_recorded": bool(getattr(error, "quota_recorded", False)),
        "cost_event_recorded": bool(getattr(error, "cost_recorded", False)),
    }
    if isinstance(error, PlanQuotaExhausted):
        result["quota_exhausted"] = True
    attempt_outcome = error.__dict__.get("plan_quota_attempt_outcome")
    if attempt_outcome is not None:
        result["attempt_outcome"] = str(attempt_outcome)
    return result


async def probe_plan_quota(
    adapter: PlanQuotaAdapter,
    *,
    model: str | None = None,
    runner: CliRunner = run_cli,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: float = 60.0,
    quota_ledger_path: Path | None = None,
    cost_ledger_path: Path | None = None,
) -> dict[str, Any]:
    """A small round-trip proving the CLI runs and is authenticated.

    Eligible backends have $0/prepaid marginal cost but consume one plan unit.
    Metered-at-margin adapters return a typed failure before argv construction
    or runner dispatch. Ordinary failures are returned in the result. Task
    cancellation propagates after bounded attempt accounting and runner cleanup.
    """
    try:
        validated_timeout = validate_timeout(timeout)
    except ValueError as validation_error:
        return {
            "ok": False,
            "backend": adapter.backend_id,
            "reply": "",
            "latency_ms": 0,
            "error": str(validation_error),
        }
    resolved_env = env if env is not None else dict(os.environ)
    decision = evaluate_plan_quota_safety(adapter, env=resolved_env)
    if not decision.safe:
        return {
            "ok": False,
            "backend": adapter.backend_id,
            "reply": "",
            "latency_ms": 0,
            "error": decision.reason,
        }
    deadline = asyncio.get_running_loop().time() + validated_timeout
    try:
        transcript_lease = await _acquire_transcript_lease(adapter, deadline=deadline)
    except PlanQuotaError as error:
        return {
            "ok": False,
            "backend": adapter.backend_id,
            "reply": "",
            "latency_ms": 0,
            "error": str(error),
            "outcome": str(getattr(error, "plan_quota_outcome", "transcript_lock_error")),
            "vendor_dispatched": False,
            "cost_event_recorded": False,
            "quota_observation_recorded": False,
        }
    probe_result: dict[str, Any] | None = None
    primary_error: BaseException | None = None
    try:
        dispatch_timeout = _remaining_operation_timeout(deadline) if transcript_lease is not None else validated_timeout
        if dispatch_timeout <= 0:
            timeout_error = _transcript_lock_timeout_error()
            probe_result = {
                "ok": False,
                "backend": adapter.backend_id,
                "reply": "",
                "latency_ms": 0,
                "error": str(timeout_error),
                "outcome": "transcript_lock_timeout",
                "vendor_dispatched": False,
                "cost_event_recorded": False,
                "quota_observation_recorded": False,
            }
            return probe_result
        probe_result = await _probe_plan_quota_dispatch(
            adapter,
            model=model,
            runner=runner,
            resolved_env=resolved_env,
            cwd=cwd,
            validated_timeout=dispatch_timeout,
            deadline=deadline if transcript_lease is not None else None,
            quota_ledger_path=quota_ledger_path,
            cost_ledger_path=cost_ledger_path,
            transcript_lease=transcript_lease,
        )
        return probe_result
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if transcript_lease is not None:
            _release_probe_lease(
                transcript_lease,
                primary_error=primary_error,
                probe_result=probe_result,
            )


async def _probe_plan_quota_dispatch(
    adapter: PlanQuotaAdapter,
    *,
    model: str | None,
    runner: CliRunner,
    resolved_env: dict[str, str],
    cwd: str | None,
    validated_timeout: float,
    deadline: float | None,
    quota_ledger_path: Path | None,
    cost_ledger_path: Path | None,
    transcript_lease: _TranscriptLease | None,
) -> dict[str, Any]:
    run_env = plan_quota_child_env(adapter, resolved_env)
    prompt = _correlated_transcript_prompt(adapter, "Reply with exactly: OK")
    argv, stdin, temp_path = _build_invocation(adapter, prompt, model)
    dispatch_timeout = _remaining_operation_timeout(deadline) if deadline is not None else validated_timeout
    if dispatch_timeout <= 0:
        _cleanup_prompt_file(temp_path)
        timeout_error = _transcript_lock_timeout_error()
        return {
            "ok": False,
            "backend": adapter.backend_id,
            "reply": "",
            "latency_ms": 0,
            "error": str(timeout_error),
            "outcome": "transcript_lock_timeout",
            "vendor_dispatched": False,
            "cost_event_recorded": False,
            "quota_observation_recorded": False,
        }
    attempt_id = f"plan-quota:{adapter.backend_id}:{uuid4().hex}"
    try:
        try:
            result = await dispatch_runner_with_accounting(
                runner,
                argv=argv,
                stdin=stdin,
                timeout=dispatch_timeout,
                env=run_env,
                cwd=cwd,
                on_cancelled=partial(
                    _account_probe_dispatch_error,
                    adapter,
                    attempt_id=attempt_id,
                    model=model,
                    quota_ledger_path=quota_ledger_path,
                    cost_ledger_path=cost_ledger_path,
                    outcome="cancelled",
                    context="cancellation",
                ),
                on_error=partial(
                    _account_probe_dispatch_error,
                    adapter,
                    attempt_id=attempt_id,
                    model=model,
                    quota_ledger_path=quota_ledger_path,
                    cost_ledger_path=cost_ledger_path,
                    outcome="runner_error",
                    context="runner error",
                ),
            )
        except asyncio.CancelledError:
            raise
        except Exception as runner_error:
            return _safe_probe_runner_error_result(
                adapter,
                runner_error,
                attempt_id=attempt_id,
            )
    finally:
        _cleanup_prompt_file(temp_path)
    finish_probe = partial(
        _finish_probe_attempt,
        adapter,
        attempt_id=attempt_id,
        model=model,
        quota_ledger_path=quota_ledger_path,
        cost_ledger_path=cost_ledger_path,
        result=result,
    )
    if result.launch_error and result.cleanup_error:
        return await _run_probe_finish(
            partial(
                finish_probe,
                ok=False,
                reply="",
                error=(
                    f"process launch failed and cleanup was not confirmed: {sanitize_log_message(result.cleanup_error)}"
                ),
                outcome="cleanup_error",
                quota_event_type=None,
                quota_units=None,
                vendor_dispatched=False,
                detail="probe ownership setup failed and pre-dispatch cleanup could not be confirmed",
            )
        )
    if result.launch_error:
        return await _run_probe_finish(
            partial(
                finish_probe,
                ok=False,
                reply="",
                error=sanitize_log_message(result.launch_error),
                outcome="launch_error",
                quota_event_type=None,
                quota_units=None,
                vendor_dispatched=False,
                detail="probe CLI process did not launch; no quota usage observed",
            )
        )
    if result.runtime_error:
        return await _run_probe_finish(
            partial(
                finish_probe,
                ok=False,
                reply="",
                error=result.runtime_error,
                outcome=result.runtime_failure_outcome,
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail=f"probe {result.runtime_failure_detail}",
            )
        )
    exhaustion_text = _exhaustion_output(adapter, result, allow_success_stdout=True)
    if exhaustion_text is not None:
        reset_at = _reset_at_from_output(exhaustion_text)
        return await _run_probe_finish(
            partial(
                finish_probe,
                ok=False,
                reply="",
                error="quota exhausted",
                outcome="exhausted",
                quota_event_type=QuotaEventType.EXHAUSTED,
                quota_units=None,
                vendor_dispatched=True,
                detail="probe-plan exhaustion signature",
                reset_at=reset_at,
            )
        )
    if not result.ok:
        if result.timed_out:
            failure_message = f"timed out after {dispatch_timeout:.0f}s"
            outcome = "timeout"
            quota_event_type = QuotaEventType.ATTEMPT_OBSERVED
            quota_units = None
            vendor_dispatched = True
            detail = "probe CLI attempt timed out; quota usage is unknown"
        else:
            failure_message = f"exit {result.returncode}: {_safe_cli_error_summary(result.stderr, prompt=prompt)}"
            outcome = "nonzero_exit"
            quota_event_type = QuotaEventType.ATTEMPT_OBSERVED
            quota_units = None
            vendor_dispatched = True
            detail = f"probe CLI attempt exited {result.returncode}; quota usage is unknown"
        return await _run_probe_finish(
            partial(
                finish_probe,
                ok=False,
                reply="",
                error=failure_message,
                outcome=outcome,
                quota_event_type=quota_event_type,
                quota_units=quota_units,
                vendor_dispatched=vendor_dispatched,
                detail=detail,
            )
        )
    return await _run_probe_finish(
        partial(
            _finish_probe_response,
            adapter,
            result=result,
            expected_prompt=prompt,
            transcript_baseline=transcript_lease.baseline if transcript_lease is not None else None,
            finish_probe=finish_probe,
        )
    )
