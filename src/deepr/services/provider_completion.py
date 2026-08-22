"""Shared durable finalization for provider-completed research jobs."""

from collections.abc import Mapping
from math import isfinite
from typing import Any, cast

from deepr.experts.research_cost_gate import (
    reconcile_research_cost_from_ledger,
    record_unreserved_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from deepr.providers.base import UsageStats
from deepr.providers.dispatch_authority import canonical_provider_key
from deepr.providers.registry_pricing import get_resolved_model_capability
from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.provider_status import classify_provider_status, terminal_provider_error
from deepr.services.research_bounds import ResearchRequestBoundsError, research_tool_usage_cost

_EMPTY_COMPLETION_ERROR = (
    "Provider reported completion but no report content was extracted; "
    "cost settled conservatively and no artifact was saved"
)


def _response_content(response: Any) -> str:
    content = ""
    for block in response.output or []:
        if block.get("type") != "message":
            continue
        for item in block.get("content", []):
            if item.get("type") in {"output_text", "text"} and item.get("text"):
                content += str(item["text"]) + "\n"
    return content


async def _save_completion_report(*, storage: Any, job: ResearchJob, response: Any) -> str | None:
    """Persist a markdown report only when the provider returned extractable text."""
    content = _response_content(response)
    if not content.strip():
        return None
    report = await storage.save_report(
        job_id=job.id,
        filename="report.md",
        content=content.encode("utf-8"),
        content_type="text/markdown",
        metadata={
            "prompt": job.prompt,
            "model": job.model,
            "status": "completed",
            "provider_job_id": job.provider_job_id,
        },
    )
    return str(report.url)


async def _publish_completion_status(queue: Any, job_id: str, report_url: str | None) -> bool:
    """Mark empty provider completions FAILED after cost settlement."""
    if report_url:
        return await queue.update_status(job_id, JobStatus.COMPLETED)
    return await queue.update_status(job_id, JobStatus.FAILED, error=_EMPTY_COMPLETION_ERROR)


def _usage_int(usage: Any, field: str) -> int | None:
    value = getattr(usage, field, None)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _canonical_model(job: Any) -> str:
    metadata = getattr(job, "metadata", {})
    persisted = metadata.get("cost_reservation_model") if isinstance(metadata, Mapping) else None
    return str(persisted or getattr(job, "model", "") or "")


def _model_contract_matches(*, provider: str, canonical_model: str, observed_model: object) -> bool:
    if not canonical_model or not isinstance(observed_model, str) or not observed_model:
        return False
    canonical = get_resolved_model_capability(canonical_model)
    observed = get_resolved_model_capability(observed_model)
    if canonical is None or observed is None:
        return False
    if (canonical.provider, canonical.model) != (observed.provider, observed.model):
        return False
    provider_key = canonical_provider_key(provider)
    capability_provider = canonical_provider_key(canonical.provider)
    return provider_key == capability_provider or (provider_key == "azure" and capability_provider == "openai")


def _canonical_token_cost(usage: Any, *, model: str) -> tuple[float, int] | None:
    input_tokens = _usage_int(usage, "input_tokens")
    output_tokens = _usage_int(usage, "output_tokens")
    total_tokens = _usage_int(usage, "total_tokens")
    cached_input_tokens = _usage_int(usage, "cached_input_tokens")
    if input_tokens is None or output_tokens is None or total_tokens is None or cached_input_tokens is None:
        return None
    if total_tokens <= 0 or input_tokens + output_tokens != total_tokens or cached_input_tokens > input_tokens:
        return None
    cost = UsageStats.calculate_cost_with_cached_input(
        input_tokens,
        output_tokens,
        model,
        cached_input_tokens=cached_input_tokens,
    )
    if not isfinite(cost) or cost < 0:
        return None
    return cost, total_tokens


def _observed_tool_call_counts(output: object) -> tuple[int, int] | None:
    if not isinstance(output, list):
        return None
    web_search_calls = 0
    code_interpreter_calls = 0
    for block in output:
        if not isinstance(block, Mapping):
            return None
        block_type = block.get("type")
        if not isinstance(block_type, str) or not block_type:
            return None
        if block_type == "web_search_call":
            web_search_calls += 1
        elif block_type == "code_interpreter_call":
            code_interpreter_calls += 1
        elif block_type.endswith("_call"):
            # An unrecognized call can carry a separate provider charge that
            # this settlement path cannot prove from the normalized response.
            return None
    return web_search_calls, code_interpreter_calls


def _tool_calls_fit_job_envelope(job: Any, *, web_search_calls: int, code_interpreter_calls: int) -> bool:
    web_enabled = getattr(job, "enable_web_search", False) is True
    code_enabled = getattr(job, "enable_code_interpreter", False) is True
    if (web_search_calls and not web_enabled) or (code_interpreter_calls and not code_enabled):
        return False
    if not web_enabled and not code_enabled:
        return True
    metadata = getattr(job, "metadata", {})
    maximum = metadata.get("research_max_tool_calls") if isinstance(metadata, Mapping) else None
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
        return False
    return web_search_calls + code_interpreter_calls <= maximum


def _observed_tool_cost(job: Any, response: Any, *, provider: str) -> float | None:
    web_enabled = getattr(job, "enable_web_search", False) is True
    code_enabled = getattr(job, "enable_code_interpreter", False) is True
    output = getattr(response, "output", None)
    if not web_enabled and not code_enabled and output is None:
        return 0.0
    counts = _observed_tool_call_counts(output)
    if counts is None:
        return None
    web_search_calls, code_interpreter_calls = counts

    if not _tool_calls_fit_job_envelope(
        job,
        web_search_calls=web_search_calls,
        code_interpreter_calls=code_interpreter_calls,
    ):
        return None
    try:
        return research_tool_usage_cost(
            provider=provider,
            web_search_calls=web_search_calls,
            # One Responses request uses one billed container session even if
            # the model emits multiple code-interpreter call blocks.
            code_interpreter_sessions=int(code_interpreter_calls > 0),
        )
    except ResearchRequestBoundsError:
        return None


def authoritative_completion_usage(job: Any, response: Any) -> tuple[float | None, int]:
    """Resolve completion usage against canonical model and paid-tool evidence."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, 0
    raw_tokens = _usage_int(usage, "total_tokens")
    tokens = raw_tokens if raw_tokens is not None else 0
    provider = str(getattr(job, "provider", "") or "")
    model = _canonical_model(job)
    if not _model_contract_matches(
        provider=provider,
        canonical_model=model,
        observed_model=getattr(response, "model", None),
    ):
        return None, tokens
    priced = _canonical_token_cost(usage, model=model)
    tool_cost = _observed_tool_cost(job, response, provider=provider)
    if priced is None or tool_cost is None:
        return None, tokens
    token_cost, tokens = priced
    reported_cost = getattr(usage, "cost", None)
    if reported_cost is not None and (
        isinstance(reported_cost, bool)
        or not isinstance(reported_cost, (int, float))
        or not isfinite(float(reported_cost))
        or float(reported_cost) < 0
    ):
        return None, tokens
    # Current adapters report token-only cost. Taking the maximum also remains
    # safe if a future provider starts returning an all-in amount.
    return max(token_cost + tool_cost, float(reported_cost or 0.0)), tokens


def conservative_completion_cost(response: Any, reservation: Any) -> tuple[float | None, float, int]:
    """Return reported cost, ledger/display cost, and tokens for immediate work."""
    usage = getattr(response, "usage", None)
    raw_tokens = _usage_int(usage, "total_tokens") if usage is not None else None
    tokens = raw_tokens if raw_tokens is not None else 0
    provider = str(getattr(reservation, "provider", "") or "")
    model = str(getattr(reservation, "model", "") or "")
    reported_cost: float | None = None
    if usage is not None and _model_contract_matches(
        provider=provider,
        canonical_model=model,
        observed_model=getattr(response, "model", None),
    ):
        priced = _canonical_token_cost(usage, model=model)
        # The immediate helper lacks the admitted request's paid-tool evidence.
        # OpenAI-compatible tool usage therefore consumes the reserved ceiling.
        if priced is not None and canonical_provider_key(provider) not in {"openai", "azure"}:
            token_cost, tokens = priced
            raw_cost = getattr(usage, "cost", None)
            if raw_cost is None:
                reported_cost = token_cost
            elif (
                not isinstance(raw_cost, bool)
                and isinstance(raw_cost, (int, float))
                and isfinite(float(raw_cost))
                and float(raw_cost) >= 0
            ):
                reported_cost = max(token_cost, float(raw_cost))
    accounted_cost = reported_cost if reported_cost is not None else float(reservation.estimated_cost)
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
    report_url = await _save_completion_report(storage=storage, job=job, response=response)
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
        report_paths={"markdown": report_url} if report_url else {},
        cost=accounted_cost,
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
    if not await _publish_completion_status(queue, job.id, report_url):
        raise RuntimeError("queue rejected provider completion status")
    updated = await queue.get_job(job.id)
    if updated is None:
        raise RuntimeError("terminal job disappeared from the queue")
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
    classified = classify_provider_status(getattr(response, "status", None))
    error = str(getattr(response, "error", "") or "").strip() or (
        terminal_provider_error(classified) or "Unknown provider error"
    )
    terminal_status = JobStatus.CANCELLED if classified == "cancelled" else JobStatus.FAILED
    if not await queue.update_status(job.id, terminal_status, error=error):
        raise RuntimeError("queue rejected provider failure status")
    updated = await queue.get_job(job.id)
    if updated is None:
        raise RuntimeError("failed job disappeared from the queue")
    return cast(ResearchJob, updated)


async def reconcile_provider_job(
    *,
    queue: Any,
    storage: Any,
    provider: Any,
    job: ResearchJob,
    response: Any,
    source: str,
) -> ResearchJob | None:
    """Close a local job when the provider snapshot is terminal.

    Returns the updated job for completed, failed, cancelled, expired, and
    incomplete provider states. Returns None while the job is still in
    progress or the provider status is unsupported.
    """
    provider_status = classify_provider_status(getattr(response, "status", None))
    if provider_status == "completed":
        return await finalize_provider_completion(
            queue=queue,
            storage=storage,
            provider=provider,
            job=job,
            response=response,
            source=source,
        )
    if terminal_provider_error(provider_status):
        return await finalize_provider_failure(
            queue=queue,
            provider=provider,
            job=job,
            response=response,
            source=source,
        )
    return None


__all__ = [
    "authoritative_completion_usage",
    "conservative_completion_cost",
    "finalize_provider_completion",
    "finalize_provider_failure",
    "reconcile_provider_job",
]
