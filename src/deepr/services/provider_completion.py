"""Shared durable finalization for provider-completed research jobs."""

from typing import Any

from deepr.experts.research_cost_gate import (
    reconcile_research_cost_from_ledger,
    record_unreserved_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
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
    usage = response.usage
    cost = usage.cost if usage else None
    tokens = usage.total_tokens if usage else 0
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
        record_unreserved_research_cost(
            job_id=job.id,
            provider=job.provider,
            model=job.model,
            actual_cost=float(cost or 0),
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
    has_cleanup_metadata = bool(job.metadata.get("provider_file_ids") or job.metadata.get("vector_store_id"))
    if has_cleanup_metadata and not await queue.clear_cleanup_metadata(job.id):
        raise RuntimeError("provider cleanup state was not persisted")
    if not await queue.update_status(job.id, JobStatus.COMPLETED):
        raise RuntimeError("queue rejected provider completion status")
    updated = await queue.get_job(job.id)
    if updated is None:
        raise RuntimeError("completed job disappeared from the queue")
    return updated


__all__ = ["finalize_provider_completion"]
