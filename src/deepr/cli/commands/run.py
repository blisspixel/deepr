"""Run research jobs with modern CLI interface."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import click

from deepr.cli.async_runner import run_async_command
from deepr.cli.colors import console, print_warning
from deepr.cli.commands.budget import check_budget_approval
from deepr.cli.commands.run_submission import (
    AcceptedProviderTrackingError,
)
from deepr.cli.commands.run_submission import enqueue_reserved_job as _enqueue_reserved_job
from deepr.cli.commands.run_submission import ensure_cli_dispatch_reservation as _ensure_reservation
from deepr.cli.commands.run_submission import (
    handle_immediate_job as _handle_immediate_job,
)
from deepr.cli.commands.run_submission import recover_provider_tracking_failure as _recover_provider_tracking_failure
from deepr.cli.commands.run_submission import reserve_job_submission as _reserve_job_submission
from deepr.cli.commands.run_submission import rollback_prepared_submission as _rollback_prepared_submission
from deepr.cli.live_status import shimmer_status
from deepr.cli.output import (
    OperationResult,
    OutputContext,
    OutputFormatter,
    OutputMode,
    format_cost,
    format_duration,
    output_options,
)
from deepr.queue.base import JobStatus
from deepr.queue.local_queue import SQLiteQueue

MAX_FALLBACK_ATTEMPTS = 3

logger = logging.getLogger(__name__)


def _classify_provider_error(exc: Exception, provider: str) -> None:
    """Re-raise exception as a core ProviderError subclass for fallback routing.

    Maps provider-layer exceptions (deepr.providers.base.ProviderError and
    generic exceptions) into the core error hierarchy so the fallback loop
    can make smart decisions based on error type.
    """
    from deepr.core.errors import (
        ProviderAuthError,
        ProviderRateLimitError,
        ProviderTimeoutError,
        ProviderUnavailableError,
    )
    from deepr.core.errors import (
        ProviderError as CoreProviderError,
    )

    # Already a core error - re-raise as-is
    if isinstance(exc, CoreProviderError):
        raise exc

    error_str = str(exc).lower()

    if "timeout" in error_str or "timed out" in error_str:
        raise ProviderTimeoutError(provider, timeout_seconds=0) from exc
    elif "rate limit" in error_str or "429" in error_str or "rate_limit" in error_str:
        raise ProviderRateLimitError(provider) from exc
    elif "auth" in error_str or "401" in error_str or "api key" in error_str or "unauthorized" in error_str:
        raise ProviderAuthError(provider) from exc
    elif "503" in error_str or "502" in error_str or "unavailable" in error_str:
        raise ProviderUnavailableError(provider) from exc
    else:
        raise CoreProviderError(f"{provider}: {exc}") from exc


@dataclass
class TraceFlags:
    """Flags for trace visibility after research completion."""

    explain: bool = False
    timeline: bool = False
    full_trace: bool = False

    @property
    def any_enabled(self) -> bool:
        return self.explain or self.timeline or self.full_trace


def _show_trace_explain(emitter) -> None:
    """Show decision reasoning from trace data."""
    from rich.panel import Panel

    total_cost = emitter.get_total_cost()
    task_count = len(emitter.tasks)

    console.print()
    console.print(
        Panel(
            f"[bold]Research Path[/bold]\n\n"
            f"Trace ID: {emitter.trace_context.trace_id}\n"
            f"Tasks: {task_count}\n"
            f"Total Cost: {format_cost(total_cost)}",
            title="Explain",
            border_style="dim",
        )
    )

    for task in emitter.tasks:
        indent = "  " if task.parent_task_id else ""
        icon = "+" if task.status == "completed" else "x" if task.status == "failed" else "o"
        color = "green" if task.status == "completed" else "red" if task.status == "failed" else "yellow"
        console.print(f"{indent}[{color}]{icon}[/] {task.task_type}")
        if task.model:
            reason = f"Used {task.model}"
            if task.provider:
                reason += f" via {task.provider}"
            if task.cost > 0:
                reason += f", cost {format_cost(task.cost)}"
            console.print(f"{indent}  [dim]{reason}[/dim]")

    # Show fallback events if any occurred
    fallback_events = []
    for span in emitter.trace_context.spans:
        for event in getattr(span, "events", []):
            if event.get("name") == "fallback_triggered":
                fallback_events.append(event.get("attributes", {}))

    if fallback_events:
        console.print("\n[bold]Fallback Events[/bold]")
        for attrs in fallback_events:
            console.print(
                f"  [yellow]![/] {attrs.get('from_provider')}/{attrs.get('from_model')} "
                f"-> {attrs.get('to_provider')}/{attrs.get('to_model')}"
            )
            console.print(f"    [dim]Reason: {attrs.get('reason', 'unknown')}[/dim]")


def _show_decision_records(emitter) -> None:
    """Show structured decision records if ThoughtStream has them."""
    from rich.table import Table

    # Check if emitter has a thought_stream with decision_records
    thought_stream = getattr(emitter, "thought_stream", None)
    if thought_stream is None:
        return
    records = getattr(thought_stream, "decision_records", [])
    if not records:
        return

    console.print()
    table = Table(title="Decision Records", border_style="dim", show_lines=False)
    table.add_column("Type", style="cyan", width=18)
    table.add_column("Decision", style="white")
    table.add_column("Confidence", style="yellow", width=12, justify="right")
    table.add_column("Cost Impact", style="green", width=12, justify="right")

    for rec in records:
        conf_str = f"{rec.confidence:.0%}" if rec.confidence else "-"
        cost_str = format_cost(rec.cost_impact) if rec.cost_impact else "-"
        table.add_row(rec.decision_type.value, rec.title, conf_str, cost_str)

    console.print(table)


def _show_trace_timeline(emitter) -> None:
    """Show phase timeline from trace data."""
    from rich.table import Table

    timeline_data = emitter.get_timeline()
    if not timeline_data:
        return

    console.print()
    table = Table(title="Timeline", border_style="dim", show_lines=False)
    table.add_column("Offset", style="dim", width=8)
    table.add_column("Task", style="cyan")
    table.add_column("Status", width=10)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Cost", justify="right", width=8)

    # Calculate offsets from first task
    first_start = None
    for entry in timeline_data:
        from datetime import datetime as _dt

        try:
            start = _dt.fromisoformat(entry["start_time"])
            if first_start is None:
                first_start = start
            offset_s = (start - first_start).total_seconds()
            offset_str = f"[{format_duration(offset_s)}]" if offset_s > 0 else "[0s]"
        except (ValueError, KeyError):
            offset_str = "[-]"

        status_color = "green" if entry.get("status") == "completed" else "red"
        duration = format_duration(entry["duration_ms"] / 1000) if entry.get("duration_ms") else "-"
        cost = format_cost(entry["cost"]) if entry.get("cost", 0) > 0 else "-"

        table.add_row(
            offset_str,
            entry.get("task_type", "unknown"),
            f"[{status_color}]{entry.get('status', '?')}[/{status_color}]",
            duration,
            cost,
        )

    console.print(table)

    breakdown = emitter.get_cost_breakdown()
    if any(v > 0 for v in breakdown.values()):
        console.print("\n[dim]Cost by type:[/dim]")
        for task_type, cost in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            if cost > 0:
                console.print(f"  {task_type}: {format_cost(cost)}")


def _save_and_show_full_trace(emitter, job_id: str) -> None:
    """Save full trace to disk and print path."""
    trace_path = Path(f"data/traces/{job_id[:12]}_trace.json")
    emitter.save_trace(trace_path)
    console.print(f"\n[dim]Full trace saved to {trace_path}[/dim]")
    console.print(f"[dim]  {len(emitter.tasks)} tasks, {len(emitter.trace_context.spans)} spans[/dim]")


def estimate_cost(model: str, enable_web_search: bool = True) -> float:
    """Simple cost estimation."""
    # Based on real API tests
    if "o4-mini" in model:
        return 0.10  # $0.10 average for o4-mini
    elif "o3" in model:
        return 0.50  # $0.50 average for o3
    else:
        return 0.15  # Default estimate


@click.group()
def run():
    """Run research jobs (single, campaign, or team)."""
    pass


@run.command()
@click.argument("query")
@click.option("--model", "-m", default="o3-deep-research", help="Research model to use")
@click.option(
    "--provider",
    "-p",
    default="openai",
    type=click.Choice(["openai", "azure", "gemini", "grok"]),
    help="Research provider (openai, azure, gemini, grok)",
)
@click.option("--no-web", is_flag=True, help="Disable web search")
@click.option("--no-code", is_flag=True, help="Disable code interpreter")
@click.option("--upload", "-u", multiple=True, help="Upload files for context")
@click.option("--limit", "-l", type=float, help="Cost limit in dollars")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
@click.option("--explain", "--why", is_flag=True, help="Show decision reasoning after completion")
@click.option("--timeline", is_flag=True, help="Show phase timeline after completion")
@click.option("--full-trace", is_flag=True, help="Export full trace to data/traces/")
@click.option("--no-fallback", is_flag=True, help="Disable automatic provider fallback on failure")
@output_options
def focus(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: float | None,
    yes: bool,
    explain: bool,
    timeline: bool,
    full_trace: bool,
    no_fallback: bool,
    output_context: OutputContext,
):
    """Run a focused research job (quick, single-turn research).

    Examples:
        deepr run focus "Analyze AI code editor market 2025"
        deepr run focus "Latest quantum computing trends" -m o3-deep-research
        deepr run focus "Company analysis" --upload data.csv --limit 5.00
        deepr run focus "Query" --provider gemini -m gemini-2.5-flash
        deepr run focus "Latest from xAI" --provider grok -m grok-4.3
        deepr run focus "AI trends" --explain --timeline
    """
    trace_flags = TraceFlags(explain=explain, timeline=timeline, full_trace=full_trace)
    run_async_command(
        _run_single(
            query,
            model,
            provider,
            no_web,
            no_code,
            upload,
            limit,
            yes,
            output_context,
            trace_flags=trace_flags,
            no_fallback=no_fallback,
        ),
        runner=asyncio.run,
    )


def _model_supports_web_search(model: str) -> bool:
    """Return whether a model accepts the web-search tool on submission."""
    return "nano" not in model.lower()


def _provider_for_model(model: str) -> str | None:
    """Resolve which provider serves an explicitly requested model."""
    try:
        from deepr.providers.registry import MODEL_CAPABILITIES

        normalized = model.lower().replace(".", "-")
        for key, cap in MODEL_CAPABILITIES.items():
            if cap.model.lower().replace(".", "-") == normalized:
                return key.split("/", 1)[0]
    except Exception as exc:
        logger.debug("Provider lookup for model %s failed: %s", model, exc, exc_info=exc)
    return None


async def _mark_job_failed(job_id: str, error: str) -> None:
    """Mark a queued job FAILED so a failed submission never leaves a zombie.

    Live finding (2026-06-11): an all-providers-failed --auto run exited
    with the job still QUEUED, which the user had to cancel manually.
    Best-effort: a queue error must not mask the original failure.
    """
    try:
        from deepr.config import load_config

        queue = SQLiteQueue(str(load_config().get("queue_db_path") or "queue/research_queue.db"))
        await queue.update_status(job_id=job_id, status=JobStatus.FAILED, error=str(error)[:500])
    except Exception as exc:
        logger.warning("Could not mark job %s as failed: %s", job_id, exc)


async def _run_single(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: float | None,
    yes: bool,
    output_context: OutputContext | None = None,
    trace_flags: TraceFlags | None = None,
    no_fallback: bool = False,
    user_specified_provider: bool = True,
    user_specified_model: bool = False,
):
    """Execute single research job with automatic provider fallback.

    Orchestrates the research workflow:
    1. Router-based provider selection (if user didn't specify --provider)
    2. Budget approval
    3. File uploads (if any)
    4. Job submission to queue
    5. Provider API submission with fallback loop
    6. Result handling
    7. Trace display (if --explain/--timeline/--full-trace)

    Args:
        query: Research query
        model: Model to use
        provider: Provider name
        no_web: Disable web search
        no_code: Disable code interpreter
        upload: Files to upload
        limit: Cost limit
        yes: Skip confirmation
        output_context: Output formatting context (optional for backward compatibility)
        trace_flags: Optional trace visibility flags
        no_fallback: Disable automatic provider fallback on failure
        user_specified_provider: True when user explicitly passed --provider
    """
    # Import refactored modules
    from deepr.cli.commands.file_handler import handle_file_uploads
    from deepr.cli.commands.provider_factory import (
        supports_vector_stores,
    )
    from deepr.core.errors import (
        ProviderAuthError,
        ProviderRateLimitError,
        ProviderTimeoutError,
    )
    from deepr.core.errors import (
        ProviderError as CoreProviderError,
    )
    from deepr.observability.metadata import MetadataEmitter
    from deepr.observability.provider_router import AutonomousProviderRouter

    if trace_flags is None:
        trace_flags = TraceFlags()

    # Create default output context if not provided (backward compatibility)
    if output_context is None:
        output_context = OutputContext(mode=OutputMode.VERBOSE)

    formatter = OutputFormatter(output_context)
    start_time = time.time()

    # Initialize provider router for intelligent selection and fallback
    router = AutonomousProviderRouter()

    # Router-based provider selection - ONLY when the user specified neither
    # provider nor model. An explicit -m must always win (live finding
    # 2026-06-11: -m o4-mini-deep-research was silently overridden to the
    # pinned default, which also made the cheaper model unselectable).
    if not user_specified_provider and not user_specified_model:
        try:
            selected_provider, selected_model = router.select_provider(
                task_type="research",
            )
            provider = selected_provider
            model = selected_model
            if output_context.mode == OutputMode.VERBOSE:
                console.print(f"  [dim]Router selected: {provider}/{model}[/dim]")
        except Exception as exc:
            logger.debug("Router selection failed; using requested/default provider: %s", exc, exc_info=exc)
    elif user_specified_model and not user_specified_provider:
        # Honor the explicit model; just resolve which provider serves it.
        inferred = _provider_for_model(model)
        if inferred and inferred != provider:
            provider = inferred
            if output_context.mode == OutputMode.VERBOSE:
                console.print(f"  [dim]Using {provider} (serves requested model {model})[/dim]")

    # Drop the web-search tool up front for models known to reject it
    # (the submit loop also retries once without it on rejection).
    if not no_web and not _model_supports_web_search(model):
        no_web = True
        if output_context.mode == OutputMode.VERBOSE:
            print_warning(f"{model} does not support the web-search tool; running without web search")

    # Check for deprecated model and display warning
    from deepr.routing.deprecation import check_deprecation

    # Only warn for entries with a real sunset date. Date-less entries are
    # informational mappings; warning on every default run trained users to
    # ignore the warnings (and one stale date outlived the model's actual
    # retirement plan - live finding 2026-06-11).
    dep_entry = check_deprecation(model)
    if dep_entry and dep_entry.sunset_date:
        msg = (
            f"WARNING: Model '{dep_entry.old_model}' is deprecated (retires {dep_entry.sunset_date}). "
            f"Recommended successor: {dep_entry.new_model}"
        )
        click.echo(msg, err=True)

    # Initialize trace emitter
    emitter = MetadataEmitter()
    op = emitter.start_task(
        "research_job",
        prompt=query,
        attributes={
            "provider": provider,
            "model": model,
            "web_search": not no_web,
            "code_interpreter": not no_code,
            "router_selected": not user_specified_provider,
        },
    )
    op.set_model(model, provider)

    # Estimate cost and show header
    estimated_cost = estimate_cost(model, enable_web_search=not no_web)
    _show_research_header(output_context, query, provider, model, estimated_cost, upload)

    # Start operation feedback
    formatter.start_operation(f"Researching: {query[:50]}...")

    with shimmer_status(
        "Preparing research request...",
        console=console,
        enabled=output_context.mode == OutputMode.VERBOSE,
    ) as live_status:
        live_status.update("Checking budget...")
        if not _check_budget(yes, estimated_cost, output_context):
            emitter.fail_task(op, "budget_declined")
            return

        if no_web and no_code and not upload and supports_vector_stores(provider) and "deep-research" in model:
            _handle_missing_tools_error(None, model, formatter, start_time)
            emitter.fail_task(op, "missing_required_tools")
            return

        from deepr.config import load_config

        config = load_config()
        queue_db_path = str(config.get("queue_db_path") or "queue/research_queue.db")
        live_status.update("Reserving cost ceiling...")
        job_id, reservation = await _reserve_job_submission(model, provider, limit, queue_db_path)

        # Handle file uploads using refactored module
        document_ids = []
        vector_store_id = None
        upload_result = None
        try:
            if upload:
                live_status.update("Uploading context files...")

                upload_op = emitter.start_task(
                    "file_upload",
                    attributes={
                        "file_count": len(upload),
                    },
                )

                upload_result = await handle_file_uploads(provider, upload, formatter, config)

                # Report errors in verbose mode
                if upload_result.has_errors and output_context.mode == OutputMode.VERBOSE:
                    for error in upload_result.errors:
                        print_warning(error)

                # Extract results
                vector_store_id = upload_result.vector_store_id
                if not supports_vector_stores(provider):
                    document_ids = upload_result.uploaded_ids

                upload_op.set_attribute("uploaded_count", len(upload_result.uploaded_ids))
                emitter.complete_task(upload_op)

            if (
                no_web
                and no_code
                and not vector_store_id
                and supports_vector_stores(provider)
                and "deep-research" in model
            ):
                await _rollback_prepared_submission(
                    reservation,
                    upload_result,
                    source="cli.run.missing_tools",
                    formatter=formatter,
                )
                _handle_missing_tools_error(None, model, formatter, start_time)
                emitter.fail_task(op, "missing_required_tools")
                return

            live_status.update("Queueing job...")
            await _enqueue_reserved_job(
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
                provider_file_ids=upload_result.uploaded_ids if upload_result is not None else [],
            )
        except Exception:
            await _rollback_prepared_submission(
                reservation,
                upload_result,
                source="cli.run.pre_submit_failure",
                formatter=formatter,
            )
            raise

        submission_queue = SQLiteQueue(queue_db_path)
        reservation = await _ensure_reservation(submission_queue, job_id, reservation, upload_result, formatter)
        if not await submission_queue.claim_submission(job_id):
            await _rollback_prepared_submission(
                reservation,
                upload_result,
                source="cli.run.claim_failure",
                formatter=formatter,
            )
            raise RuntimeError("Research job could not be claimed for provider submission")
        op.set_attribute("job_id", job_id)
        formatter.progress("Submitting research job...")

        # === Fallback loop: submit to provider with automatic retry/fallback ===
        current_provider = provider
        current_model = model
        attempted = []  # (provider, model) tuples that have failed
        fallback_count = 0
        last_error = None
        success = False
        web_tool_retry_done = False  # one retry without web tool on rejection

        while fallback_count <= MAX_FALLBACK_ATTEMPTS:
            try:
                live_status.update(f"Submitting to {current_provider}/{current_model}...")
                # Handle vector_store degradation on fallback to non-supporting provider
                effective_vector_store_id = vector_store_id
                if vector_store_id and not supports_vector_stores(current_provider):
                    effective_vector_store_id = None
                    if output_context.mode == OutputMode.VERBOSE:
                        print_warning(
                            f"{current_provider} does not support file search; proceeding without uploaded file context"
                        )

                submit_start = time.time()
                submission_terminal = await _submit_to_provider(
                    job_id,
                    query,
                    current_model,
                    current_provider,
                    no_web,
                    no_code,
                    document_ids,
                    effective_vector_store_id,
                    output_context,
                    formatter,
                    start_time,
                    emitter,
                    reservation,
                )
                if submission_terminal and upload_result is not None:
                    from deepr.cli.commands.file_handler import cleanup_file_uploads

                    await cleanup_file_uploads(upload_result, formatter)

                # Success - record metrics
                submit_latency = (time.time() - submit_start) * 1000
                try:
                    router.record_result(
                        current_provider,
                        current_model,
                        success=True,
                        latency_ms=submit_latency,
                    )
                except Exception as exc:
                    logger.debug("Failed to record provider router metric: %s", exc, exc_info=exc)
                success = True
                break

            except AcceptedProviderTrackingError as e:
                if e.cancellation_confirmed and upload_result is not None:
                    from deepr.cli.commands.file_handler import cleanup_file_uploads

                    await cleanup_file_uploads(upload_result, formatter)
                await _mark_job_failed(job_id, str(e))
                formatter.complete(
                    OperationResult(
                        success=False,
                        duration_seconds=time.time() - start_time,
                        cost_usd=reservation.estimated_cost,
                        job_id=job_id,
                        error=str(e),
                        error_code="PROVIDER_TRACKING_FAILED",
                    )
                )
                emitter.fail_task(op, "provider_tracking_failed")
                return

            except ProviderAuthError as e:
                # Auth errors: skip provider entirely, don't retry same provider
                last_error = e
                try:
                    router.record_result(current_provider, current_model, success=False, error=str(e))
                except Exception as exc:
                    logger.debug("Failed to record provider router metric: %s", exc, exc_info=exc)
                if output_context.mode == OutputMode.VERBOSE:
                    print_warning(f"{current_provider}: authentication failed, skipping")
                attempted.append((current_provider, current_model))

            except ProviderRateLimitError as e:
                # Rate limit: immediate fallback (provider already retried internally)
                last_error = e
                try:
                    router.record_result(current_provider, current_model, success=False, error=str(e))
                except Exception as exc:
                    logger.debug("Failed to record provider router metric: %s", exc, exc_info=exc)
                attempted.append((current_provider, current_model))

            except ProviderTimeoutError as e:
                last_error = e
                from deepr.experts.research_cost_gate import settle_research_cost

                settle_research_cost(
                    reservation,
                    actual_cost=None,
                    source="cli.run.ambiguous_provider_timeout",
                )
                await _mark_job_failed(job_id, f"Provider outcome uncertain: {e}")
                formatter.complete(
                    OperationResult(
                        success=False,
                        duration_seconds=time.time() - start_time,
                        cost_usd=reservation.estimated_cost,
                        job_id=job_id,
                        error="Provider outcome is uncertain; automatic fallback was suppressed",
                        error_code="AMBIGUOUS_PROVIDER_OUTCOME",
                    )
                )
                emitter.fail_task(op, "ambiguous_provider_outcome")
                return

            except CoreProviderError as e:
                # Generic provider error or unavailable: immediate fallback
                last_error = e
                from deepr.services.research_submission import submission_outcome_is_ambiguous

                if submission_outcome_is_ambiguous(e):
                    from deepr.experts.research_cost_gate import settle_research_cost

                    settle_research_cost(
                        reservation,
                        actual_cost=None,
                        source="cli.run.ambiguous_provider_error",
                    )
                    await _mark_job_failed(job_id, f"Provider outcome uncertain: {e}")
                    formatter.complete(
                        OperationResult(
                            success=False,
                            duration_seconds=time.time() - start_time,
                            cost_usd=reservation.estimated_cost,
                            job_id=job_id,
                            error="Provider outcome is uncertain; automatic fallback was suppressed",
                            error_code="AMBIGUOUS_PROVIDER_OUTCOME",
                        )
                    )
                    emitter.fail_task(op, "ambiguous_provider_outcome")
                    return
                # Tool-rejection defense: if the model rejected the web-search
                # tool, retry the SAME provider/model once without it instead
                # of burning through every fallback with the same bad request.
                err_text = str(e).lower()
                if (
                    not no_web
                    and not web_tool_retry_done
                    and ("web_search" in err_text or "tool" in err_text)
                    and ("not supported" in err_text or "unsupported" in err_text or "invalid" in err_text)
                ):
                    web_tool_retry_done = True
                    no_web = True
                    if output_context.mode == OutputMode.VERBOSE:
                        print_warning(f"{current_model} rejected the web-search tool; retrying without it")
                    continue
                try:
                    router.record_result(current_provider, current_model, success=False, error=str(e))
                except Exception as exc:
                    logger.debug("Failed to record provider router metric: %s", exc, exc_info=exc)
                attempted.append((current_provider, current_model))

            # === Fallback selection ===

            # If --no-fallback, stop after first error
            if no_fallback:
                await _rollback_prepared_submission(
                    reservation, upload_result, source="cli.run.no_fallback", formatter=formatter
                )
                duration = time.time() - start_time
                result = OperationResult(
                    success=False,
                    duration_seconds=duration,
                    cost_usd=0.0,
                    job_id=job_id,
                    error=f"Provider {current_provider}/{current_model} failed: {last_error}",
                    error_code="PROVIDER_ERROR",
                )
                formatter.complete(result)
                emitter.fail_task(op, str(last_error))
                await _mark_job_failed(job_id, f"{current_provider}/{current_model} failed: {last_error}")
                return

            # Get fallback from router
            fallback = router.get_fallback(current_provider, current_model, reason=str(last_error))

            # If router returned an already-attempted provider, try select_provider with exclusions
            if fallback and fallback in attempted:
                try:
                    fallback = router.select_provider(task_type="research", exclude=attempted)
                    if fallback in attempted:
                        fallback = None
                except Exception as exc:
                    logger.debug("Fallback provider selection failed with exclusions: %s", exc, exc_info=exc)
                    fallback = None

            if fallback is None:
                await _rollback_prepared_submission(
                    reservation, upload_result, source="cli.run.no_fallback_available", formatter=formatter
                )
                # No more fallbacks available
                duration = time.time() - start_time
                result = OperationResult(
                    success=False,
                    duration_seconds=duration,
                    cost_usd=0.0,
                    job_id=job_id,
                    error=f"All providers failed. Last error: {last_error}",
                    error_code="ALL_PROVIDERS_FAILED",
                )
                formatter.complete(result)
                emitter.fail_task(op, "all_providers_failed")
                await _mark_job_failed(job_id, f"All providers failed. Last error: {last_error}")
                return

            fallback_provider, fallback_model = fallback
            live_status.update(f"Fallback to {fallback_provider}/{fallback_model}...")

            # Emit fallback event to trace
            op.add_event(
                "fallback_triggered",
                {
                    "from_provider": current_provider,
                    "from_model": current_model,
                    "to_provider": fallback_provider,
                    "to_model": fallback_model,
                    "reason": str(last_error),
                    "attempt": fallback_count + 1,
                },
            )

            if output_context.mode == OutputMode.VERBOSE:
                console.print(
                    f"  [yellow]Falling back: {current_provider}/{current_model} "
                    f"-> {fallback_provider}/{fallback_model}[/yellow]"
                )

            current_provider, current_model = fallback
            fallback_count += 1

        live_status.update("Finalizing trace...")

    if not success:
        await _rollback_prepared_submission(
            reservation, upload_result, source="cli.run.fallback_exhausted", formatter=formatter
        )
        duration = time.time() - start_time
        result = OperationResult(
            success=False,
            duration_seconds=duration,
            cost_usd=0.0,
            job_id=job_id,
            error=f"Exhausted all fallback attempts. Last error: {last_error}",
            error_code="FALLBACK_EXHAUSTED",
        )
        formatter.complete(result)
        emitter.fail_task(op, "fallback_exhausted")
        return

    # Complete top-level span
    actual_cost = 0.0
    for task in emitter.tasks:
        actual_cost += task.cost
    op.set_cost(actual_cost)
    if op.metadata.status == "running":
        emitter.complete_task(op)

    # Save trace (always, for later `deepr research trace` viewing)
    trace_path = Path(f"data/traces/research_{job_id[:12]}.json")
    try:
        emitter.save_trace(trace_path)
    except Exception as exc:
        logger.warning("Failed to save research trace to %s: %s", trace_path, exc)

    # Display trace info if flags are set (skip for JSON/QUIET modes)
    if trace_flags.any_enabled and output_context.mode not in (OutputMode.JSON, OutputMode.QUIET):
        if trace_flags.explain:
            _show_trace_explain(emitter)
            _show_decision_records(emitter)
        if trace_flags.timeline:
            _show_trace_timeline(emitter)
        if trace_flags.full_trace:
            _save_and_show_full_trace(emitter, job_id)


def _show_research_header(
    output_context: OutputContext, query: str, provider: str, model: str, estimated_cost: float, upload: tuple
) -> bool:
    """Display research header in verbose mode."""
    if output_context.mode == OutputMode.VERBOSE:
        console.print()
        console.print("[bold]Research[/bold]", highlight=False)
        console.print(f"[dim]{'─' * 40}[/dim]")
        console.print(f"  Query:    {query}")
        console.print(f"  Provider: {provider}")
        console.print(f"  Model:    {model}")
        console.print(f"  Est cost: {format_cost(estimated_cost)}")
        if upload:
            console.print(f"  Files:    {', '.join(upload)}")
        console.print()


def _check_budget(yes: bool, estimated_cost: float, output_context: OutputContext) -> bool:
    """Check budget approval. Returns True if approved, False if cancelled.

    -y skips the *confirmation*, never the *budget gate*. Previously
    `yes` short-circuited before check_budget_approval, so any headless
    run (`-y`, every --auto execution, agents driving deepr) could spend
    past the monthly budget without the gate ever being consulted - the
    exact "surprise bill" path the budget exists to prevent. When the
    gate requires human judgment and there is no human (-y), the run is
    REFUSED with instructions, not waved through: a non-interactive
    caller cannot consent on the operator's behalf.
    """
    if check_budget_approval(estimated_cost):
        return True

    # Gate says this spend needs a human decision.
    if yes:
        click.echo(
            f"Budget gate: estimated ${estimated_cost:.2f} needs confirmation "
            "(over/near the monthly budget, or above the $1 cautious-mode floor) "
            "and -y cannot consent to it. Raise the budget with "
            "'deepr budget set <amount>' to authorize headless spend at this level, "
            "or run interactively.",
            err=True,
        )
        return False

    if output_context.mode == OutputMode.VERBOSE:
        if not click.confirm(f"Proceed with estimated cost ${estimated_cost:.2f}?"):
            click.echo("Cancelled.")
            return False
        return True

    return False


async def _submit_to_provider(
    job_id: str,
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    document_ids: list[str],
    vector_store_id: str | None,
    output_context: OutputContext,
    formatter: OutputFormatter,
    start_time: float,
    emitter=None,
    reservation=None,
) -> None:
    """Submit job to provider API and handle response."""
    from deepr.cli.commands.provider_factory import (
        create_provider_instance,
        supports_background_jobs,
        supports_vector_stores,
    )
    from deepr.config import load_config
    from deepr.providers.base import ResearchRequest

    config = load_config()
    queue = SQLiteQueue(str(config.get("queue_db_path") or "queue/research_queue.db"))

    # Start provider submission span
    submit_op = None
    if emitter:
        submit_op = emitter.start_task(
            "provider_submit",
            attributes={
                "provider": provider,
                "model": model,
                "job_id": job_id,
            },
        )
        submit_op.set_model(model, provider)

    try:
        provider_instance = create_provider_instance(provider, config)

        # Build tools list using provider factory
        tools = _build_tools_list(provider, no_web, no_code, vector_store_id)

        # Validate tools for deep research models
        if supports_vector_stores(provider) and "deep-research" in model and not tools:
            raise ValueError(f"{model} requires at least one tool")

        # Create and submit research request
        request = ResearchRequest(
            prompt=query,
            model=model,
            system_message="You are a research assistant. Provide comprehensive, citation-backed analysis.",
            tools=tools,
            background=supports_background_jobs(provider),
            document_ids=document_ids if document_ids else None,
            idempotency_key=f"deepr-research-{job_id}",
        )

        provider_job_id = await provider_instance.submit_research(request)
        if submit_op:
            submit_op.set_attribute("provider_job_id", provider_job_id)

    except Exception as e:
        if submit_op and emitter:
            emitter.fail_task(submit_op, str(e))
        # Re-raise as classified core error for the fallback loop in _run_single
        _classify_provider_error(e, provider)

    try:
        if supports_background_jobs(provider):
            if submit_op:
                emitter.complete_task(submit_op)
            await _handle_background_job(job_id, provider_job_id, output_context, queue)
            return False
        else:
            return await _handle_immediate_job(
                job_id=job_id,
                provider_job_id=provider_job_id,
                query=query,
                model=model,
                provider_instance=provider_instance,
                output_context=output_context,
                formatter=formatter,
                start_time=start_time,
                config=config,
                queue=queue,
                reservation=reservation,
                emitter=emitter,
                submit_op=submit_op,
            )
    except Exception as exc:
        cancellation_confirmed = await _recover_provider_tracking_failure(
            provider_instance, provider_job_id, reservation
        )
        raise AcceptedProviderTrackingError(
            f"Provider accepted work, but local tracking failed: {exc}",
            cancellation_confirmed=cancellation_confirmed,
        ) from exc


def _build_tools_list(provider: str, no_web: bool, no_code: bool, vector_store_id: str | None) -> list:
    """Build provider-specific tools list."""
    from deepr.cli.commands.provider_factory import get_tool_name, supports_vector_stores
    from deepr.providers.base import ToolConfig

    tools = []
    if not no_web:
        tool_name = get_tool_name(provider, "web_search")
        tools.append(ToolConfig(type=tool_name))
    if not no_code:
        tools.append(ToolConfig(type="code_interpreter"))

    # Add file_search tool when vector store is available
    if vector_store_id and supports_vector_stores(provider):
        tools.append(ToolConfig(type="file_search", vector_store_ids=[vector_store_id]))

    return tools


def _handle_missing_tools_error(job_id: str | None, model: str, formatter: OutputFormatter, start_time: float) -> None:
    """Handle error when deep research model has no tools."""
    duration = time.time() - start_time
    result = OperationResult(
        success=False,
        duration_seconds=duration,
        cost_usd=0.0,
        job_id=job_id,
        error=f"{model} requires at least one tool (web search, code interpreter, or file upload)",
        error_code="MISSING_TOOLS",
    )
    formatter.complete(result)


async def _handle_background_job(
    job_id: str, provider_job_id: str, output_context: OutputContext, queue: SQLiteQueue
) -> None:
    """Handle OpenAI/Azure background job submission."""
    updated = await queue.update_status(job_id=job_id, status=JobStatus.PROCESSING, provider_job_id=provider_job_id)
    if not updated:
        raise RuntimeError("queue rejected background provider tracking update")

    if output_context.mode == OutputMode.VERBOSE:
        click.echo(f"\nJob submitted: {job_id[:12]}")
        click.echo(f"Provider job ID: {provider_job_id}")
        click.echo(f"\nCheck status: deepr status {job_id[:12]}")
        click.echo(f"View results: deepr get {job_id[:12]}")
        click.echo("List all jobs: deepr list")
    elif output_context.mode == OutputMode.JSON:
        import json as json_module

        print(json_module.dumps({"status": "pending", "job_id": job_id, "provider_job_id": provider_job_id}))


@run.command()
@click.argument("scenario")
@click.option("--model", "-m", default="o3-deep-research", help="Research model")
@click.option("--lead", default="gpt-5", help="Lead planner model")
@click.option("--phases", "-p", type=click.IntRange(1, 10), default=3, help="Number of phases (1-10)")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def project(
    scenario: str,
    model: str,
    lead: str,
    phases: int,
    yes: bool,
):
    """Run a multi-phase research project with context chaining.

    The lead model plans the research, then executes multiple phases
    with context chaining between them.

    Examples:
        deepr run project "Ford EV strategy for 2026"
        deepr run project "Market entry analysis" --phases 4
        deepr run project "Competitive landscape" -m o3-deep-research
    """
    run_async_command(_run_campaign(scenario, model, lead, phases, yes), runner=asyncio.run)


async def _run_campaign(
    scenario: str,
    model: str,
    lead: str,
    phases: int,
    yes: bool,
):
    """Execute campaign."""
    click.echo("\n" + "=" * 70)
    click.echo("  DEEPR - Multi-Phase Campaign")
    click.echo("=" * 70 + "\n")

    # Estimate cost (phases * per-job cost)
    per_job_cost = estimate_cost(model, enable_web_search=True)
    estimated_cost = per_job_cost * phases

    click.echo(f"Scenario: {scenario}")
    click.echo(f"Lead model: {lead}")
    click.echo(f"Research model: {model}")
    click.echo(f"Phases: {phases}")
    click.echo(f"Estimated cost: ${estimated_cost:.2f} ({phases} x ${per_job_cost:.2f})")
    click.echo()

    # Budget check
    if not yes and not check_budget_approval(estimated_cost):
        if not click.confirm(f"Proceed with estimated cost ${estimated_cost:.2f}?"):
            click.echo("Cancelled.")
            return

    click.echo("Planning campaign phases...")
    click.echo(
        "\nNOTE: This command is deprecated. Please use 'deepr prep plan' and 'deepr prep execute' for better control.\n"
    )

    # Import prep functionality - use the working implementation
    from deepr.services.research_planner import ResearchPlanner

    # Generate plan using lead model (planner for planning, model for execution)
    planner_svc = ResearchPlanner(model=lead)
    tasks = planner_svc.plan_research(scenario=scenario, max_tasks=phases, context=None)

    # Add task IDs and model info
    for i, task in enumerate(tasks, 1):
        task["id"] = i
        task["model"] = model
        task["approved"] = True  # Auto-approve for deprecated command

    plan = {"scenario": scenario, "tasks": tasks, "model": model, "metadata": {"planner": lead}}

    click.echo("\nCampaign plan generated:")
    click.echo(f"  Tasks: {len(plan['tasks'])}")
    click.echo()

    # Execute campaign
    click.echo("Executing campaign phases...")

    # Import the async executor instead of the sync wrapper
    import time

    from deepr.config import load_config
    from deepr.providers import create_provider
    from deepr.queue import create_queue
    from deepr.services.batch_executor import BatchExecutor
    from deepr.services.context_builder import ContextBuilder
    from deepr.storage import create_storage

    config = load_config()

    # Determine provider based on model
    is_deep_research = "deep-research" in model.lower()
    if is_deep_research:
        provider_name = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
    else:
        provider_name = os.getenv("DEEPR_DEFAULT_PROVIDER", "xai")

    # Get API key
    if provider_name == "gemini":
        api_key = config.get("gemini_api_key")
    elif provider_name in ["grok", "xai"]:
        api_key = config.get("xai_api_key")
        provider_name = "xai"
    elif provider_name == "azure":
        api_key = config.get("azure_api_key")
    else:
        api_key = config.get("api_key")
        provider_name = "openai"

    # Initialize services
    queue = create_queue("local", db_path=str(config.get("queue_db_path") or "queue/research_queue.db"))
    provider_instance = create_provider(provider_name, api_key=api_key)
    storage = create_storage(config.get("storage", "local"), base_path=config.get("results_dir", "data/reports"))
    context_builder = ContextBuilder(api_key=config.get("api_key"))

    executor = BatchExecutor(queue=queue, provider=provider_instance, storage=storage, context_builder=context_builder)

    campaign_id = f"campaign-{int(time.time())}"
    results = await executor.execute_campaign(tasks, campaign_id)

    if results.get("status") == "pending":
        click.echo("\nCampaign remains in progress; durable job tracking was retained.")
    else:
        click.echo("\nCampaign completed!")
    click.echo(f"Results: {len(results.get('tasks', {}))} tasks recorded")
    click.echo("\nFor better control, use: deepr prep plan / deepr prep execute")


@run.command()
@click.argument("question")
@click.option("--model", "-m", default="o3-deep-research", help="Research model")
@click.option("--perspectives", "-p", type=click.IntRange(1, 12), default=6, help="Number of perspectives (1-12)")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def team(
    question: str,
    model: str,
    perspectives: int,
    yes: bool,
):
    """Run research with multiple perspectives (dream team).

    Uses Six Thinking Hats methodology to analyze the question
    from different angles simultaneously.

    Examples:
        deepr run team "Should we pivot to enterprise?"
        deepr run team "Evaluate merger opportunity" --perspectives 8
        deepr run team "Technology decision" -m o3-deep-research
    """
    run_async_command(_run_team(question, model, perspectives, yes), runner=asyncio.run)


async def _run_team(
    question: str,
    model: str,
    perspectives: int,
    yes: bool,
):
    """Execute team research."""
    click.echo("\n" + "=" * 70)
    click.echo("  DEEPR - Dream Team Research")
    click.echo("=" * 70 + "\n")

    # Estimate cost
    per_job_cost = estimate_cost(model, enable_web_search=True)
    estimated_cost = per_job_cost * perspectives

    click.echo(f"Question: {question}")
    click.echo(f"Model: {model}")
    click.echo(f"Perspectives: {perspectives}")
    click.echo(f"Estimated cost: ${estimated_cost:.2f} ({perspectives} x ${per_job_cost:.2f})")
    click.echo()

    # Budget check
    if not yes and not check_budget_approval(estimated_cost):
        if not click.confirm(f"Proceed with estimated cost ${estimated_cost:.2f}?"):
            click.echo("Cancelled.")
            return

    click.echo("Assembling research team...")

    # Import team functionality
    from deepr.cli.commands.team import run_dream_team

    # Determine provider based on model
    is_deep_research = "deep-research" in model.lower()
    if is_deep_research:
        provider = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
    else:
        provider = os.getenv("DEEPR_DEFAULT_PROVIDER", "xai")

    # Execute team research
    await run_dream_team(question, model, perspectives, provider=provider)


@run.command()
@click.argument("topic")
@click.option("--model", "-m", default="o3-deep-research", help="Research model to use")
@click.option(
    "--provider",
    "-p",
    default="openai",
    type=click.Choice(["openai", "azure", "gemini", "grok"]),
    help="Research provider",
)
@click.option("--upload", "-u", multiple=True, help="Upload existing documentation for context")
@click.option("--limit", "-l", type=float, help="Cost limit in dollars")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
@click.option("--no-fallback", is_flag=True, help="Disable automatic provider fallback on failure")
@output_options
def docs(
    topic: str,
    model: str,
    provider: str,
    upload: tuple,
    limit: float | None,
    yes: bool,
    no_fallback: bool,
    output_context: OutputContext,
):
    """Run documentation-oriented research.

    Focused on creating comprehensive, well-structured documentation
    with clear explanations, examples, and references.

    Examples:
        deepr run docs "API authentication flow"
        deepr run docs "Database schema design" --upload existing_docs.md
        deepr run docs "Deployment guide for Kubernetes"
    """
    # NOTE: Documentation-specific system message could be passed through _run_single
    # but for now we use a docs-optimized prompt prefix instead.
    # TODO: Add system_message parameter to _run_single for customization

    # Call _run_single with docs-specific parameters
    run_async_command(
        _run_single(
            query=f"Create comprehensive documentation for: {topic}",
            model=model,
            provider=provider,
            no_web=False,  # Enable web search for docs research
            no_code=False,  # Enable code interpreter for examples
            upload=upload,
            limit=limit,
            yes=yes,
            output_context=output_context,
            no_fallback=no_fallback,
        ),
        runner=asyncio.run,
    )


# Aliases
@click.command(name="r")
@click.argument("query")
@click.option("--model", "-m", default="o3-deep-research")
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "azure", "gemini", "grok"]))
@click.option("--no-web", is_flag=True)
@click.option("--no-code", is_flag=True)
@click.option("--upload", "-u", multiple=True)
@click.option("--limit", "-l", type=float)
@click.option("--yes", "-y", is_flag=True)
@click.option("--no-fallback", is_flag=True)
@output_options
def run_alias(query, model, provider, no_web, no_code, upload, limit, yes, no_fallback, output_context):
    """Quick alias for 'deepr run focus' - run a focused research job."""
    run_async_command(
        _run_single(
            query, model, provider, no_web, no_code, upload, limit, yes, output_context, no_fallback=no_fallback
        ),
        runner=asyncio.run,
    )


if __name__ == "__main__":
    run()
