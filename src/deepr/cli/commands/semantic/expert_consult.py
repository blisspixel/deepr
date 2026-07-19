"""`deepr expert consult` - consult a team of experts as one knowledge transaction.

Extracted from experts.py (file-size cap). Routes a question to the relevant
experts (or an explicit set), gathers bounded perspectives, and synthesizes one
calibrated answer with agreements/disagreements - the single, bounded "knowledge
transaction" in docs/design/agentic-harness-boundary.md. This is the first-class
verb so any agentic harness can consult Deepr's expert team via one command (and
the matching MCP tool) instead of scripting the council.
"""

from __future__ import annotations

import asyncio
import json as _json
import sys
from math import isfinite
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_warning
from deepr.cli.commands.semantic.experts import expert

# Shared core (also used by the deepr_consult_experts MCP tool). Re-exported so
# existing importers/tests keep working.
from deepr.experts.consult import (
    MAX_CONSULT_EXPERTS,
    ConsultBackendError,
    build_consult_payload,
    build_synthesis_backend,
    run_consult,
)
from deepr.experts.consult_transaction import (
    DEFAULT_CONSULT_MAX_ELAPSED_SECONDS,
    MAX_CONSULT_MAX_ELAPSED_SECONDS,
    ConsultElapsedLimitError,
    ConsultStorageError,
    execute_consult_transaction,
    requested_consult_capacity,
)
from deepr.utils.atomic_io import atomic_write_json

__all__ = ["build_consult_payload", "expert_consult", "run_consult"]


def _build_cli_synthesis_backend(
    *,
    use_local: bool,
    local_model: str | None,
    plan_backend: str | None,
    plan_model: str | None,
    api_provider: str | None,
    api_model: str | None,
    json_output: bool,
):
    try:
        backend = build_synthesis_backend(
            use_local=use_local,
            local_model=local_model,
            plan_backend=plan_backend,
            plan_model=plan_model,
            api_provider=api_provider,
            api_model=api_model,
        )
    except ConsultBackendError as exc:
        raise click.UsageError(str(exc)) from exc
    if backend.tos_note and not json_output:
        print_warning(backend.tos_note)
    return backend


def _render(payload: dict[str, Any]) -> None:
    names = payload["experts_consulted"]
    console.print("[bold]Mode:[/bold] one-shot stored-context council; experts do not exchange turns")
    console.print(f"[bold]Consulted {len(names)} expert(s):[/bold] {', '.join(names) or '(none)'}")
    for p in payload["perspectives"]:
        console.print(f"\n[bold]{p['expert']}[/bold] [dim](conf {p['confidence']:.2f})[/dim]")
        console.print(f"  {p['response'][:600]}")
    console.print("\n[bold]Synthesis[/bold]")
    console.print(payload["answer"][:1400] or "  [dim](no synthesis)[/dim]")
    if payload["synthesis_status"] not in {"completed", "skipped_no_valid_perspectives"}:
        reason = payload.get("synthesis_stop_reason") or payload.get("synthesis_error_type") or "unknown"
        print_warning(f"Synthesis is incomplete: {payload['synthesis_status']} ({reason}).")
    for label, key in (("Agreements", "agreements"), ("Disagreements", "disagreements")):
        if payload[key]:
            console.print(f"\n[bold]{label}[/bold]")
            for item in payload[key][:6]:
                console.print(f"  - {item}")
    console.print(f"\n[dim]Cost: ${payload['cost_usd']:.4f}[/dim]")
    console.print("[dim]Knowledge writes: none; discussion output is a review-only proposal.[/dim]")


def _validate_consult_limits(
    *,
    budget: float,
    use_local: bool,
    plan_backend: str | None,
    max_elapsed_seconds: float,
) -> None:
    if not isfinite(budget) or budget < 0 or (budget <= 0 and not use_local and not plan_backend):
        print_error("--budget must be finite and non-negative; API-backed consults require a positive value.")
        sys.exit(2)
    if (
        not isfinite(max_elapsed_seconds)
        or max_elapsed_seconds <= 0
        or max_elapsed_seconds > MAX_CONSULT_MAX_ELAPSED_SECONDS
    ):
        print_error("--max-elapsed-seconds must be finite, greater than zero, and no more than 21600.")
        sys.exit(2)


def _requested_capacity(
    *,
    use_local: bool,
    local_model: str | None,
    plan_backend: str | None,
    plan_model: str | None,
    api_provider: str | None,
    api_model: str | None,
) -> tuple[str, dict[str, object]]:
    backend_mode = "local" if use_local else "plan" if plan_backend else "api"
    capacity = requested_consult_capacity(
        backend_mode=backend_mode,
        provider=("local" if use_local else f"plan_quota:{plan_backend}" if plan_backend else api_provider or "openai"),
        model=(local_model or "" if use_local else plan_model or "" if plan_backend else api_model or ""),
    )
    return backend_mode, capacity


def _make_backend_factory(
    *,
    use_local: bool,
    local_model: str | None,
    plan_backend: str | None,
    plan_model: str | None,
    api_provider: str | None,
    api_model: str | None,
    json_output: bool,
):
    async def build_backend():
        resolved_local_model = local_model
        if use_local and not resolved_local_model:
            from deepr.backends.local import default_local_model_async

            resolved_local_model = await default_local_model_async()
        return await asyncio.to_thread(
            _build_cli_synthesis_backend,
            use_local=use_local,
            local_model=resolved_local_model,
            plan_backend=plan_backend,
            plan_model=plan_model,
            api_provider=api_provider,
            api_model=api_model,
            json_output=json_output,
        )

    return build_backend


def _make_report_callbacks(json_output: bool):
    def report_started(trace_id: str) -> None:
        if not json_output:
            console.print(f"[dim]Consult trace: {trace_id}[/dim]")

    def report_backend(backend: Any) -> None:
        if backend.note and not json_output:
            console.print(f"[dim]{backend.note}[/dim]")

    return report_started, report_backend


def _execute_cli_consult(
    *,
    question: str,
    experts: tuple[str, ...],
    max_experts: int,
    budget: float,
    backend_mode: str,
    backend_factory: Any,
    capacity_request: dict[str, object],
    max_elapsed_seconds: float,
    report_started: Any,
    report_backend: Any,
) -> dict[str, Any]:
    try:
        return asyncio.run(
            execute_consult_transaction(
                question=question,
                requested_experts=list(experts),
                max_experts=max_experts,
                budget=budget,
                backend_mode=backend_mode,
                backend_factory=backend_factory,
                requested_capacity=capacity_request,
                max_elapsed_seconds=max_elapsed_seconds,
                run_consult_fn=run_consult,
                on_started=report_started,
                on_backend_ready=report_backend,
            )
        )
    except click.UsageError as exc:
        print_error(str(exc))
        sys.exit(2)
    except ConsultElapsedLimitError as exc:
        guidance = "retry safely" if exc.retryable else "do not retry the full consultation"
        print_error(f"{exc} {guidance}.")
        sys.exit(1)
    except ConsultStorageError as exc:
        guidance = "retry safely" if exc.retryable else "do not retry the full consultation"
        print_error(f"Consultation storage failed; {guidance}: {exc}")
        sys.exit(1)
    except Exception as exc:  # surface the failure honestly; never a silent empty result
        print_error(f"Consultation failed: {exc}")
        sys.exit(1)


def _emit_consult_result(
    payload: dict[str, Any],
    *,
    json_output: bool,
    output: Path | None,
) -> None:
    if output is not None:
        try:
            atomic_write_json(output, payload, indent=2, fsync=True)
        except OSError as exc:
            raise click.ClickException(f"Could not write consult artifact: {exc}") from exc
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
    else:
        _render(payload)
        if output is not None:
            click.echo(f"Wrote consult artifact: {output}")

    if not payload["experts_consulted"]:
        if not json_output:
            print_warning("No experts were consulted - create experts first or name them with -e.")
        sys.exit(2)
    if payload["synthesis_status"] not in {"completed", "skipped_no_valid_perspectives"}:
        sys.exit(1)


@expert.command(name="consult")
@click.argument("question")
@click.option(
    "--expert",
    "-e",
    "experts",
    multiple=True,
    help="Expert to include (repeatable). Omit to auto-select relevant experts.",
)
@click.option(
    "--max-experts",
    type=click.IntRange(1, MAX_CONSULT_EXPERTS),
    default=3,
    show_default=True,
    help="Max experts when auto-selecting (capped at 10).",
)
@click.option(
    "--budget",
    "-b",
    default=2.0,
    show_default=True,
    help="Hard transaction ceiling. Current API mode meters final synthesis only; local and plan cost $0 in Deepr.",
)
@click.option(
    "--provider",
    "api_provider",
    type=click.Choice(["openai", "anthropic"], case_sensitive=False),
    default=None,
    help="API synthesis provider when not using --local or --plan.",
)
@click.option("--model", "api_model", default=None, help="API synthesis model when not using --local or --plan.")
@click.option("--local", "use_local", is_flag=True, help="Use local Ollama synthesis at $0.")
@click.option("--local-model", default=None, help="Local Ollama model for synthesis. Defaults to detected model.")
@click.option("--plan", "plan_backend", default=None, help="Use an explicit plan-quota CLI for synthesis.")
@click.option("--plan-model", default=None, help="Model hint for the plan-quota CLI.")
@click.option(
    "--max-elapsed-seconds",
    default=DEFAULT_CONSULT_MAX_ELAPSED_SECONDS,
    show_default=True,
    help=(
        "Cumulative ceiling for cancellable consult work and lifecycle checkpoints. "
        "Durable writes are awaited off the event loop and lock waits are bounded separately; "
        "no backend fallback occurs."
    ),
)
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned consult artifact (deepr-consult-v1).")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Explicit path for the full consult artifact. No file is written here by default.",
)
@click.option("-y", "--yes", is_flag=True, help="Run without an interactive confirmation.")
@click.option(
    "--confirm-metered-cost",
    is_flag=True,
    help="With --yes, explicitly authorize metered API synthesis up to --budget.",
)
def expert_consult(
    question,
    experts,
    max_experts,
    budget,
    api_provider,
    api_model,
    use_local,
    local_model,
    plan_backend,
    plan_model,
    max_elapsed_seconds,
    json_output,
    output,
    yes,
    confirm_metered_cost,
):
    """Consult a team of experts and synthesize one calibrated answer.

    One bounded knowledge transaction: route to the relevant experts (or the ones
    you name with -e), read a stored perspective from each, and synthesize an
    answer with agreements and dissent. Experts do not exchange model-generated
    turns, and the consultation never writes beliefs or graph state.

    EXAMPLES:
      deepr expert consult "How should we harden absorption provenance?"
      deepr expert consult "Cost vs quality tradeoff?" -e "AI Cost Optimization" -e "LLM Evaluation and Calibration"
      deepr expert consult "What changed in MCP?" --local --json
    """
    _validate_consult_limits(
        budget=budget,
        use_local=use_local,
        plan_backend=plan_backend,
        max_elapsed_seconds=max_elapsed_seconds,
    )
    backend_mode, capacity_request = _requested_capacity(
        use_local=use_local,
        local_model=local_model,
        plan_backend=plan_backend,
        plan_model=plan_model,
        api_provider=api_provider,
        api_model=api_model,
    )

    if backend_mode == "api":
        if yes and not confirm_metered_cost:
            raise click.UsageError(
                "Metered API consult with --yes requires --confirm-metered-cost; --budget is only a hard ceiling."
            )
        if not yes:
            if json_output or not sys.stdin.isatty():
                raise click.UsageError(
                    "Noninteractive metered API consult requires --yes --confirm-metered-cost. "
                    "Use --local or --plan for an explicit non-metered path."
                )
            if not click.confirm(
                f"Authorize metered API synthesis with a hard ceiling of ${budget:.2f}?",
                default=False,
            ):
                print_warning("Cancelled.")
                return

    backend_factory = _make_backend_factory(
        use_local=use_local,
        local_model=local_model,
        plan_backend=plan_backend,
        plan_model=plan_model,
        api_provider=api_provider,
        api_model=api_model,
        json_output=json_output,
    )
    report_started, report_backend = _make_report_callbacks(json_output)
    payload = _execute_cli_consult(
        question=question,
        experts=experts,
        max_experts=max_experts,
        budget=budget,
        backend_mode=backend_mode,
        backend_factory=backend_factory,
        capacity_request=capacity_request,
        max_elapsed_seconds=max_elapsed_seconds,
        report_started=report_started,
        report_backend=report_backend,
    )
    _emit_consult_result(payload, json_output=json_output, output=output)
