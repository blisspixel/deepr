"""Shared durable finalization for provider-completed research jobs."""

from typing import Any, cast

from deepr.experts.research_cost_gate import (
    reconcile_research_cost_from_ledger,
    record_unreserved_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from deepr.providers.base import UsageStats
from deepr.queue.base import JobStatus, ResearchJob


def _response_content(response: Any) -> str:
    content = ""
    for block in response.output or []:
        if block.get("type") != "message":
            continue
        for item in block.get("content", []):
            if item.get("type") in {"output_text", "text"} and item.get("text"):
                content += str(item["text"]) + "\n"
    return content


def authoritative_completion_usage(job: ResearchJob, response: Any) -> tuple[float | None, int]:
    """Resolve completion usage against the job's canonical pricing model."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, 0
    tokens = max(0, int(getattr(usage, "total_tokens", 0) or 0))
    if str(job.provider).lower() != "azure":
        return getattr(usage, "cost", None), tokens

    input_tokens = max(0, int(getattr(usage, "input_tokens", 0) or 0))
    output_tokens = max(0, int(getattr(usage, "output_tokens", 0) or 0))
    if input_tokens + output_tokens <= 0:
        return None, tokens
    metadata = job.metadata if isinstance(job.metadata, dict) else {}
    canonical_model = str(metadata.get("cost_reservation_model") or job.model)
    cost = UsageStats.calculate_cost_with_cached_input(
        input_tokens,
        output_tokens,
        canonical_model,
        cached_input_tokens=max(0, int(getattr(usage, "cached_input_tokens", 0) or 0)),
    )
    return cost, tokens


def conservative_completion_cost(response: Any, reservation: Any) -> tuple[float | None, float, int]:
    """Return reported cost, ledger/display cost, and tokens for immediate work."""
    usage = getattr(response, "usage", None)
    raw_cost = getattr(usage, "cost", None) if usage is not None else None
    reported_cost = float(raw_cost) if raw_cost is not None else None
    accounted_cost = reported_cost if reported_cost is not None else float(reservation.estimated_cost)
    tokens = max(0, int(getattr(usage, "total_tokens", 0) or 0)) if usage is not None else 0
    return reported_cost, accounted_cost, tokens


async def finalize_provider_completion(
    *,
    queue: Any,
    storage: Any,
    provider: Any,
    job: ResearchJob,
    response: Any,
    source: str,
) -> ResearchJob:
    """Persist results, cost, cleanup, and terminal state in safety order."""
    report = await storage.save_report(
        job_id=job.id,
        filename="report.md",
        content=_response_content(response).encode("utf-8"),
        content_type="text/markdown",
        metadata={
            "prompt": job.prompt,
            "model": job.model,
            "status": "completed",
            "provider_job_id": job.provider_job_id,
        },
    )
    cost, tokens = authoritative_completion_usage(job, response)
    reservation = restore_research_cost_reservation(
        job_id=job.id,
        metadata=job.metadata,
        provider=job.provider,
        model=job.model,
    )
    if reservation is not None:
        settle_research_cost(
            reservation,
            actual_cost=cost,
            tokens=tokens,
            request_id=str(job.provider_job_id or ""),
            source=source,
        )
    else:
        cost = record_unreserved_research_cost(
            job_id=job.id,
            provider=job.provider,
            model=job.model,
            actual_cost=cost,
            tokens=tokens,
            request_id=str(job.provider_job_id or ""),
            source=source,
        )
    if not await queue.update_results(
        job.id,
        report_paths={"markdown": str(report.url)},
        cost=cost,
        tokens_used=tokens,
    ):
        raise RuntimeError("queue rejected provider result update")
    if not reconcile_research_cost_from_ledger(reservation, job_id=job.id):
        raise RuntimeError("canonical provider cost settlement is missing")

    from deepr.cli.commands.run_submission import cleanup_persisted_uploads

    if not await cleanup_persisted_uploads(provider, job):
        raise RuntimeError("provider resource cleanup was not confirmed")
    metadata = job.metadata if isinstance(job.metadata, dict) else {}
    has_cleanup_metadata = bool(metadata.get("provider_file_ids") or metadata.get("vector_store_id"))
    if has_cleanup_metadata and not await queue.clear_cleanup_metadata(job.id):
        raise RuntimeError("provider cleanup state was not persisted")
    if not await queue.update_status(job.id, JobStatus.COMPLETED):
        raise RuntimeError("queue rejected provider completion status")
    updated = await queue.get_job(job.id)
    if updated is None:
        raise RuntimeError("completed job disappeared from the queue")
    return cast(ResearchJob, updated)


async def finalize_provider_failure(
    *,
    queue: Any,
    provider: Any,
    job: ResearchJob,
    response: Any,
    source: str,
) -> ResearchJob:
    """Settle possible provider spend before publishing terminal failure."""
    cost, tokens = authoritative_completion_usage(job, response)
    reservation = restore_research_cost_reservation(
        job_id=job.id,
        metadata=job.metadata,
        provider=job.provider,
        model=job.model,
    )
    if reservation is not None:
        settle_research_cost(
            reservation,
            actual_cost=cost,
            tokens=tokens,
            request_id=str(job.provider_job_id or ""),
            source=source,
        )
        accounted_cost = cost if cost is not None else reservation.estimated_cost
    else:
        accounted_cost = record_unreserved_research_cost(
            job_id=job.id,
            provider=job.provider,
            model=job.model,
            actual_cost=cost,
            tokens=tokens,
            request_id=str(job.provider_job_id or ""),
            source=source,
        )
    if not await queue.update_results(
        job.id,
        report_paths={},
        cost=accounted_cost,
        tokens_used=tokens,
    ):
        raise RuntimeError("queue rejected provider failure cost update")
    if not reconcile_research_cost_from_ledger(reservation, job_id=job.id):
        raise RuntimeError("canonical provider failure cost settlement is missing")

    metadata = job.metadata if isinstance(job.metadata, dict) else {}
    has_cleanup_metadata = bool(metadata.get("provider_file_ids") or metadata.get("vector_store_id"))
    if has_cleanup_metadata:
        from deepr.cli.commands.run_submission import cleanup_persisted_uploads

        if not await cleanup_persisted_uploads(provider, job):
            raise RuntimeError("provider resource cleanup was not confirmed")
        if not await queue.clear_cleanup_metadata(job.id):
            raise RuntimeError("provider cleanup state was not persisted")
    error = str(getattr(response, "error", "") or "Unknown provider error")
    if not await queue.update_status(job.id, JobStatus.FAILED, error=error):
        raise RuntimeError("queue rejected provider failure status")
    updated = await queue.get_job(job.id)
    if updated is None:
        raise RuntimeError("failed job disappeared from the queue")
    return cast(ResearchJob, updated)


__all__ = [
    "authoritative_completion_usage",
    "conservative_completion_cost",
    "finalize_provider_completion",
    "finalize_provider_failure",
]
