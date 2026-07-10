"""Fail-closed web research cost coordination."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from deepr.experts.research_cost_gate import (
    ResearchCostBlocked,
    ResearchCostReservation,
    reconcile_research_cost_from_ledger,
    record_unreserved_research_cost,
    refund_research_cost,
    reserve_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from deepr.queue.base import JobStatus
from deepr.services.research_cancellation import cancel_reserved_research

logger = logging.getLogger(__name__)
OPENAI_NOT_CONFIGURED = "OpenAI is not configured; set OPENAI_API_KEY before submitting research"


class WebProviderNotConfiguredError(RuntimeError):
    """Raised when web research lacks required provider configuration."""


def resolve_web_research_provider(factory: Callable[[], Any]) -> tuple[Any | None, tuple[dict[str, str], int] | None]:
    """Resolve a gated provider without exposing construction exceptions."""
    try:
        return factory(), None
    except WebProviderNotConfiguredError:
        return None, ({"error": OPENAI_NOT_CONFIGURED}, 503)
    except Exception as exc:
        logger.error("Research provider construction failed: %s", type(exc).__name__)
        return None, ({"error": "Research provider is unavailable"}, 503)


def validate_web_research_input(
    *,
    prompt: str,
    model: str,
    max_prompt_length: int,
    allowed_models: set[str],
) -> tuple[dict[str, str], int] | None:
    """Return an HTTP-safe deterministic input denial, if any."""
    if not prompt:
        return {"error": "Prompt required"}, 400
    if len(prompt) > max_prompt_length:
        return {"error": f"Prompt exceeds {max_prompt_length} character limit"}, 400
    if model not in allowed_models:
        return {"error": "Invalid model"}, 400
    return None


class WebResearchCostCoordinator:
    """Own web-job reservations from estimate through completion or failure."""

    def __init__(self, controller: Any, estimator: Any) -> None:
        self._controller = controller
        self._estimator = estimator
        self._reservations: dict[str, ResearchCostReservation] = {}
        self._lock = threading.Lock()

    def reserve(
        self,
        *,
        job_id: str,
        prompt: str,
        model: str,
    ) -> tuple[dict[str, float] | None, ResearchCostReservation | None, tuple[dict[str, Any], int] | None]:
        """Estimate, check, and atomically reserve web research spend."""
        if self._controller is None or self._estimator is None:
            logger.error("Paid submission denied because cost controls are unavailable")
            return None, None, ({"error": "Cost controls unavailable; submission denied"}, 503)
        try:
            estimate = self._estimator.estimate_cost(prompt, model)
        except Exception as exc:
            logger.error("Paid submission denied because cost estimation failed: %s", exc)
            return None, None, ({"error": "Cost estimation unavailable; submission denied"}, 503)
        try:
            allowed, deny_reason = self._controller.check_cost_limit(estimate)
        except Exception as exc:
            logger.error("Paid submission denied because the cost limit check failed: %s", exc)
            return None, None, ({"error": "Cost limit check unavailable; submission denied"}, 503)
        estimated_cost = {
            "min_cost": estimate.min_cost,
            "max_cost": estimate.max_cost,
            "expected_cost": estimate.expected_cost,
        }
        if not allowed:
            return (
                estimated_cost,
                None,
                (
                    {"error": deny_reason or "Cost limit exceeded", "estimated_cost": estimated_cost},
                    429,
                ),
            )
        try:
            reservation = reserve_research_cost(
                job_id=job_id,
                provider="openai",
                model=model,
                estimate=estimate,
                max_cost_per_job=self._controller.max_cost_per_job,
                max_daily_cost=self._controller.max_daily_cost,
                max_monthly_cost=self._controller.max_monthly_cost,
            )
        except ResearchCostBlocked:
            return (
                estimated_cost,
                None,
                ({"error": "Research cost limit exceeded", "estimated_cost": estimated_cost}, 429),
            )
        except Exception as exc:
            logger.error("Paid submission denied because cost reservation failed: %s", exc)
            return None, None, ({"error": "Cost reservation unavailable; submission denied"}, 503)
        return estimated_cost, reservation, None

    def remember(self, reservation: ResearchCostReservation | None) -> None:
        if reservation is None:
            return
        with self._lock:
            self._reservations[reservation.job_id] = reservation

    def refund(self, reservation: ResearchCostReservation | None) -> None:
        if reservation is not None:
            with self._lock:
                self._reservations.pop(reservation.job_id, None)
        refund_research_cost(reservation)

    def forget(self, job_id: str) -> None:
        """Drop an in-memory handle after another service closes its cost."""
        with self._lock:
            self._reservations.pop(job_id, None)

    def cleanup_uploads(self, *, loop: Any, job: Any, provider_factory: Callable[[], Any]) -> None:
        """Delete persisted provider resources after terminal work."""
        from deepr.cli.commands.run_submission import cleanup_persisted_uploads

        cleaned = loop.run_until_complete(cleanup_persisted_uploads(provider_factory(), job))
        if not cleaned:
            logger.error("Poller: provider upload cleanup incomplete for job %s", job.id)

    def _take(self, job: Any) -> ResearchCostReservation | None:
        with self._lock:
            reservation = self._reservations.pop(str(job.id), None)
        return reservation or restore_research_cost_reservation(
            job_id=str(job.id),
            metadata=getattr(job, "metadata", None),
            provider="openai",
            model=str(getattr(job, "model", "") or ""),
        )

    def refund_job(self, job: Any) -> None:
        refund_research_cost(self._take(job))

    def fail_job(self, job: Any) -> None:
        """Conservatively settle accepted failures and refund pre-submit jobs."""
        reservation = self._take(job)
        provider_job_id = str(getattr(job, "provider_job_id", "") or "")
        if reservation is not None and provider_job_id:
            settle_research_cost(
                reservation,
                actual_cost=None,
                request_id=provider_job_id,
                source="web.poller._handle_failure",
            )
        else:
            refund_research_cost(reservation)

    async def cancel_job(self, *, queue: Any, job: Any, provider_factory: Callable[[], Any]) -> bool:
        """Close provider, queue, and reservation state in safety order."""
        active_provider = None
        metadata = getattr(job, "metadata", {}) or {}
        has_provider_resources = bool(metadata.get("provider_file_ids") or metadata.get("vector_store_id"))
        if getattr(job, "provider_job_id", None) or has_provider_resources:
            try:
                active_provider = provider_factory()
            except Exception as exc:
                logger.error("Cannot cancel provider job %s safely: %s", job.provider_job_id, exc)
                return False
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=active_provider,
            job=job,
            default_provider="openai",
            source="web.cancel_job",
        )
        if outcome.cost_closed:
            self.forget(str(job.id))
        return outcome.queue_cancelled

    def safe_settle_job(self, job: Any, *, actual_cost: float | None, tokens: int) -> None:
        """Settle completion without breaking queue finalization on ledger errors."""
        try:
            self.settle_job(job, actual_cost=actual_cost, tokens=tokens)
        except Exception:
            logger.exception("Poller: failed to record provider cost for job %s", job.id)

    def reconcile_completed_job(self, job: Any) -> bool:
        """Require canonical spend and release any hold closed by queue fallback."""
        reservation = self._take(job)
        recorded = reconcile_research_cost_from_ledger(reservation, job_id=str(job.id))
        if reservation is not None and not recorded:
            self.remember(reservation)
        return recorded

    def finalize_completed_job(
        self,
        *,
        loop: Any,
        queue: Any,
        job: Any,
        actual_cost: float | None,
        tokens: int | None,
    ) -> None:
        """Persist results, settle cost, and only then mark completion."""
        if actual_cost is not None or tokens is not None:
            loop.run_until_complete(
                queue.update_results(
                    job_id=job.id,
                    report_paths={"markdown": "report.md"},
                    cost=actual_cost,
                    tokens_used=tokens,
                )
            )
        self.safe_settle_job(job, actual_cost=actual_cost, tokens=tokens or 0)
        if not self.reconcile_completed_job(job):
            raise RuntimeError(f"Canonical cost settlement missing for completed job {job.id}")
        loop.run_until_complete(queue.update_status(job_id=job.id, status=JobStatus.COMPLETED))

    def settle_job(self, job: Any, *, actual_cost: float | None, tokens: int) -> None:
        """Settle actual cost, or the reserved estimate when usage is absent."""
        reservation = self._take(job)
        request_id = str(getattr(job, "provider_job_id", "") or "")
        if reservation is not None:
            settle_research_cost(
                reservation,
                actual_cost=actual_cost,
                tokens=tokens,
                request_id=request_id,
                source="web.poller._handle_completion",
            )
            return
        record_unreserved_research_cost(
            job_id=str(job.id),
            provider="openai",
            model=str(getattr(job, "model", "") or ""),
            actual_cost=float(actual_cost or 0.0),
            tokens=tokens,
            request_id=request_id,
            source="web.poller._handle_completion",
        )


__all__ = [
    "OPENAI_NOT_CONFIGURED",
    "WebProviderNotConfiguredError",
    "WebResearchCostCoordinator",
    "resolve_web_research_provider",
    "validate_web_research_input",
]
