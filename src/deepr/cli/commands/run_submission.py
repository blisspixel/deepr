"""Durable queue admission for the modern research CLI."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import click

from deepr.cli.output import OperationResult, OutputContext, OutputFormatter, OutputMode
from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    refund_research_cost,
    reserve_configured_cost_ceiling,
)
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue
from deepr.services.research_cost_reconciliation import reconcile_research_cost_reservations

logger = logging.getLogger(__name__)


class AcceptedProviderTrackingError(RuntimeError):
    """Provider accepted work but local tracking or persistence failed."""

    def __init__(self, message: str, *, cancellation_confirmed: bool = False) -> None:
        super().__init__(message)
        self.cancellation_confirmed = cancellation_confirmed


def _extract_response_content(response: Any) -> str:
    content = ""
    for block in response.output or []:
        if block.get("type") == "message":
            for item in block.get("content", []):
                if item.get("type") in ["output_text", "text"] and item.get("text"):
                    content += str(item["text"]) + "\n"
    return content


async def reserve_job_submission(
    model: str,
    provider: str,
    limit: float | None,
    queue_db_path: str | None = None,
) -> tuple[str, ResearchCostReservation]:
    """Admit one job before any provider-side preparation occurs."""
    job_id = f"research-{uuid.uuid4().hex[:12]}"
    queue = SQLiteQueue(queue_db_path) if queue_db_path else SQLiteQueue()
    await reconcile_research_cost_reservations(queue, default_provider=provider)
    reservation = reserve_configured_cost_ceiling(
        job_id=job_id,
        provider=provider,
        model=model,
        max_cost_per_job=limit,
    )
    return job_id, reservation


async def enqueue_reserved_job(
    *,
    job_id: str,
    reservation: ResearchCostReservation,
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    document_ids: list[str],
    vector_store_id: str | None,
    limit: float | None,
    upload: tuple[Any, ...],
    queue_db_path: str | None = None,
    provider_file_ids: list[str] | None = None,
) -> tuple[str, ResearchJob]:
    """Persist a job after its durable reservation and preparation succeed."""
    job_metadata: dict[str, Any] = {}
    if vector_store_id:
        job_metadata["vector_store_id"] = vector_store_id
        job_metadata["cleanup_vector_store"] = True
    if upload:
        job_metadata["uploaded_files"] = list(upload)
    if provider_file_ids:
        job_metadata["provider_file_ids"] = list(provider_file_ids)

    queue = SQLiteQueue(queue_db_path) if queue_db_path else SQLiteQueue()
    job_metadata.update(reservation.metadata())
    job = ResearchJob(
        id=job_id,
        prompt=query,
        model=model,
        provider=provider,
        status=JobStatus.QUEUED,
        submitted_at=datetime.now(UTC),
        enable_web_search=not no_web,
        enable_code_interpreter=not no_code,
        documents=document_ids,
        cost_limit=limit,
        metadata=job_metadata,
    )

    queued_job_id = await queue.enqueue(job)
    return queued_job_id, job


async def create_and_enqueue_job(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    document_ids: list[str],
    vector_store_id: str | None,
    limit: float | None,
    upload: tuple[Any, ...],
    queue_db_path: str | None = None,
    provider_file_ids: list[str] | None = None,
) -> tuple[str, ResearchJob, ResearchCostReservation]:
    """Reserve and enqueue a job that needs no provider-side preparation."""
    job_id, reservation = await reserve_job_submission(model, provider, limit, queue_db_path)
    try:
        queued_job_id, job = await enqueue_reserved_job(
            job_id=job_id,
            reservation=reservation,
            query=query,
            model=model,
            provider=provider,
            no_web=no_web,
            no_code=no_code,
            document_ids=document_ids,
            vector_store_id=vector_store_id,
            limit=limit,
            upload=upload,
            queue_db_path=queue_db_path,
            provider_file_ids=provider_file_ids,
        )
    except Exception:
        refund_research_cost(reservation)
        raise
    return queued_job_id, job, reservation


async def ensure_cli_dispatch_reservation(
    queue: Any,
    job_id: str,
    reservation: ResearchCostReservation,
    upload_result: Any | None,
    formatter: OutputFormatter,
) -> ResearchCostReservation:
    """Restore the CLI job's durable hold immediately before queue claim."""
    from deepr.services.research_submission import (
        ResearchDispatchReservationError,
        restore_active_queued_reservation,
    )

    try:
        _, restored = await restore_active_queued_reservation(
            queue=queue,
            job_id=job_id,
            expected=reservation,
        )
    except ResearchDispatchReservationError as exc:
        if not exc.retryable:
            await rollback_prepared_submission(
                reservation,
                upload_result,
                source=f"cli.run.{exc.code}",
                formatter=formatter,
            )
        raise
    return restored


async def rollback_prepared_submission(
    reservation: ResearchCostReservation,
    upload_result: Any | None,
    *,
    source: str,
    formatter: OutputFormatter | None = None,
) -> bool:
    """Close provider preparation before releasing its durable cost hold."""
    cleanup_confirmed = True
    provider_prepared = bool(
        upload_result is not None
        and (getattr(upload_result, "uploaded_ids", None) or getattr(upload_result, "vector_store_id", None))
    )
    if upload_result is not None:
        from deepr.cli.commands.file_handler import cleanup_file_uploads

        cleanup_confirmed = await cleanup_file_uploads(upload_result, formatter)
    if provider_prepared:
        from deepr.experts.research_cost_gate import settle_research_cost

        suffix = "cleanup_confirmed" if cleanup_confirmed else "cleanup_unconfirmed"
        settle_research_cost(reservation, actual_cost=None, source=f"{source}.{suffix}")
    else:
        refund_research_cost(reservation)
    return cleanup_confirmed


async def cleanup_persisted_uploads(provider: Any, job: ResearchJob) -> bool:
    """Delete upload resources recorded on a persisted research job."""
    from deepr.cli.commands.file_handler import FileUploadResult, cleanup_file_uploads

    result = FileUploadResult(
        resolved_files=[],
        uploaded_ids=list(job.metadata.get("provider_file_ids", [])),
        vector_store_id=job.metadata.get("vector_store_id"),
        errors=[],
        provider_instance=provider,
    )
    return await cleanup_file_uploads(result)


async def rollback_persisted_submission(
    provider: Any,
    job: ResearchJob,
    reservation: ResearchCostReservation,
    *,
    source: str,
) -> bool:
    """Clean and account for provider preparation on a persisted queued job."""
    from deepr.cli.commands.file_handler import FileUploadResult

    upload_result = FileUploadResult(
        resolved_files=[],
        uploaded_ids=list(job.metadata.get("provider_file_ids", [])),
        vector_store_id=job.metadata.get("vector_store_id"),
        errors=[],
        provider_instance=provider,
    )
    return await rollback_prepared_submission(reservation, upload_result, source=source)


async def recover_provider_tracking_failure(
    provider_instance: Any,
    provider_job_id: str,
    reservation: ResearchCostReservation | None,
) -> bool:
    """Cancel accepted work when possible, then close any active cost hold."""
    from deepr.experts.research_reservation_store import ResearchReservationStore

    try:
        cancellation_confirmed = bool(await provider_instance.cancel_job(provider_job_id))
    except Exception:
        cancellation_confirmed = False
        logger.exception("Could not cancel provider job %s after tracking failure", provider_job_id)
    if reservation is not None and ResearchReservationStore().is_active(reservation.reservation_id):
        from deepr.experts.research_cost_gate import settle_research_cost

        settle_research_cost(
            reservation,
            actual_cost=None,
            request_id=provider_job_id,
            source="cli.run.provider_tracking_failure",
        )
    return cancellation_confirmed


async def handle_immediate_job(
    *,
    job_id: str,
    provider_job_id: str,
    query: str,
    model: str,
    provider_instance: Any,
    output_context: OutputContext,
    formatter: OutputFormatter,
    start_time: float,
    config: dict[str, Any],
    queue: SQLiteQueue,
    reservation: ResearchCostReservation,
    emitter: Any = None,
    submit_op: Any = None,
) -> bool:
    """Settle and persist an immediate Gemini or Grok response."""
    import time

    response = await provider_instance.get_status(provider_job_id)
    if response.status != "completed":
        if submit_op and emitter:
            emitter.complete_task(submit_op)
        updated = await queue.update_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            provider_job_id=provider_job_id,
        )
        if not updated:
            raise RuntimeError("queue rejected immediate provider tracking update")
        if output_context.mode == OutputMode.VERBOSE:
            click.echo(f"\nJob submitted: {job_id[:12]}")
            click.echo(f"Provider job ID: {provider_job_id}")
        elif output_context.mode == OutputMode.JSON:
            import json

            print(json.dumps({"status": "pending", "job_id": job_id, "provider_job_id": provider_job_id}))
        return False

    from deepr.experts.research_cost_gate import settle_research_cost
    from deepr.storage import create_storage

    actual_cost = float(response.usage.cost or 0.0) if response.usage else 0.0
    settle_research_cost(
        reservation,
        actual_cost=actual_cost,
        tokens=response.usage.total_tokens if response.usage else 0,
        request_id=provider_job_id,
        source="cli.run.immediate_completion",
    )
    content = _extract_response_content(response)
    storage = create_storage(config.get("storage", "local"), base_path=config.get("results_dir", "data/reports"))
    report_metadata = await storage.save_report(
        job_id=job_id,
        filename="report.md",
        content=content.encode("utf-8"),
        content_type="text/markdown",
        metadata={
            "prompt": query,
            "model": model,
            "status": "completed",
            "provider_job_id": provider_job_id,
            "total_cost": actual_cost,
            "cost_by_model": {model: actual_cost},
        },
    )
    await _persist_immediate_completion(
        queue=queue,
        job_id=job_id,
        report_url=str(report_metadata.url),
        cost=actual_cost,
        tokens=response.usage.total_tokens if response.usage else 0,
    )
    if submit_op:
        submit_op.set_cost(actual_cost)
        if response.usage:
            submit_op.set_tokens(
                getattr(response.usage, "input_tokens", 0) or 0,
                getattr(response.usage, "output_tokens", 0) or 0,
            )
        if emitter:
            emitter.complete_task(submit_op)
    formatter.complete(
        OperationResult(
            success=True,
            duration_seconds=time.time() - start_time,
            cost_usd=actual_cost,
            report_path=str(report_metadata.url),
            job_id=job_id,
        )
    )
    return True


async def _persist_immediate_completion(
    *, queue: SQLiteQueue, job_id: str, report_url: str, cost: float, tokens: int
) -> None:
    """Persist immediate results and require both queue transitions."""
    results_updated = await queue.update_results(
        job_id,
        report_paths={"markdown": report_url},
        cost=cost,
        tokens_used=tokens,
    )
    if not results_updated:
        raise RuntimeError("queue rejected immediate provider result update")
    if not await queue.update_status(job_id, JobStatus.COMPLETED):
        raise RuntimeError("queue rejected immediate completion status update")


__all__ = [
    "AcceptedProviderTrackingError",
    "cleanup_persisted_uploads",
    "create_and_enqueue_job",
    "enqueue_reserved_job",
    "ensure_cli_dispatch_reservation",
    "handle_immediate_job",
    "recover_provider_tracking_failure",
    "reserve_job_submission",
    "rollback_persisted_submission",
    "rollback_prepared_submission",
]
