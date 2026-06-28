"""A2A host validation commands."""

from __future__ import annotations

import sys

import click

from deepr.cli.async_runner import run_async_command


@click.group()
def a2a() -> None:
    """Agent-to-Agent interoperability tools."""
    pass


@a2a.command("validate-host")
@click.argument("endpoint", required=False)
@click.option("--auth-token", help="Bearer token for POST /tasks on a remote A2A endpoint.")
@click.option(
    "--synthesis-backend",
    type=click.Choice(["local", "plan"], case_sensitive=False),
    default="local",
    show_default=True,
    help="No-metered consult backend to validate.",
)
@click.option("--local-model", help="Optional Ollama model when --synthesis-backend=local.")
@click.option("--plan", help="Explicit plan id when --synthesis-backend=plan, such as codex or claude.")
@click.option("--plan-model", help="Optional model hint for the plan-quota CLI.")
@click.option("--expert", "experts", multiple=True, help="Expert to target. Repeatable.")
@click.option("--question", default=None, help="Validation consult question.")
@click.option("--timeout", "timeout_seconds", default=60.0, show_default=True, type=click.FloatRange(min=0.1))
@click.option("--poll-attempts", default=5, show_default=True, type=click.IntRange(min=0))
@click.option(
    "--poll-interval", "poll_interval_seconds", default=0.25, show_default=True, type=click.FloatRange(min=0.0)
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def validate_host(
    endpoint: str | None,
    auth_token: str | None,
    synthesis_backend: str,
    local_model: str | None,
    plan: str | None,
    plan_model: str | None,
    experts: tuple[str, ...],
    question: str | None,
    timeout_seconds: float,
    poll_attempts: int,
    poll_interval_seconds: float,
    as_json: bool,
) -> None:
    """Validate Deepr A2A discovery plus no-metered consult task handling."""
    import json
    from typing import cast

    from deepr.a2a.validation import (
        DEFAULT_A2A_VALIDATION_QUESTION,
        run_http_a2a_host_validation,
        run_offline_a2a_host_validation,
    )
    from deepr.mcp.consult_validation import ValidationBackend

    backend = cast(ValidationBackend, synthesis_backend.lower())
    if backend == "plan" and not plan:
        raise click.ClickException("--plan is required when --synthesis-backend=plan")

    resolved_question = question or DEFAULT_A2A_VALIDATION_QUESTION
    try:
        if endpoint:
            report = run_async_command(
                run_http_a2a_host_validation(
                    endpoint,
                    auth_token=auth_token,
                    question=resolved_question,
                    experts=experts,
                    backend=backend,
                    local_model=local_model,
                    plan=plan,
                    plan_model=plan_model,
                    timeout_seconds=timeout_seconds,
                    poll_attempts=poll_attempts,
                    poll_interval_seconds=poll_interval_seconds,
                )
            )
        else:
            report = run_offline_a2a_host_validation(
                question=resolved_question,
                experts=experts,
                backend=backend,
                plan=plan,
                model=plan_model or local_model,
            )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    payload = report.to_dict()
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        target = report.endpoint or "offline fixture"
        click.echo(f"A2A host validation: {target}")
        click.echo(f"Discovery path: {report.discovery_path or 'not resolved'}")
        click.echo(f"Backend: {report.backend}")
        for check in report.checks:
            state = "ok" if check.status == "passed" else check.status
            click.echo(f"[{state}] {check.name}: {check.detail}")
        click.echo("Result: passed" if report.ok else "Result: failed")

    if not report.ok:
        sys.exit(1)
