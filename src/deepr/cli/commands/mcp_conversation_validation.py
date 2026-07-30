"""MCP durable conversation validation CLI."""

from __future__ import annotations

import json
import sys

import click

from deepr.cli.async_runner import run_async_command


@click.command("validate-conversation")
@click.argument("url", required=False)
@click.option("--auth-token", help="Reserved for future cost-attested remote conversation validation.")
@click.option("--expert", help="Optional canonical expert name. Omit to use focused auto-routing.")
@click.option("--local-model", help="Optional pinned Ollama model.")
@click.option("--start-message", default=None, help="Override the first validation question.")
@click.option("--continue-message", default=None, help="Override the follow-up validation question.")
@click.option(
    "--timeout",
    "timeout_seconds",
    default=180.0,
    show_default=True,
    type=click.FloatRange(min=1.0, max=300.0),
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def validate_conversation(
    url: str | None,
    auth_token: str | None,
    expert: str | None,
    local_model: str | None,
    start_message: str | None,
    continue_message: str | None,
    timeout_seconds: float,
    as_json: bool,
) -> None:
    """Report the fail-closed MCP conversation-validation posture."""
    from deepr.mcp.conversation_validation import (
        DEFAULT_CONTINUE_MESSAGE,
        DEFAULT_START_MESSAGE,
        run_http_conversation_validation,
    )

    resolved_start = start_message or DEFAULT_START_MESSAGE
    resolved_continue = continue_message or DEFAULT_CONTINUE_MESSAGE
    try:
        if url:
            report = run_async_command(
                run_http_conversation_validation(
                    url,
                    auth_token=auth_token,
                    expert=expert,
                    local_model=local_model,
                    start_message=resolved_start,
                    continue_message=resolved_continue,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            from deepr.mcp.conversation_validation_managed import (
                run_managed_loopback_conversation_validation,
            )

            report = run_async_command(
                run_managed_loopback_conversation_validation(
                    expert=expert,
                    local_model=local_model,
                    start_message=resolved_start,
                    continue_message=resolved_continue,
                    timeout_seconds=timeout_seconds,
                )
            )
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(f"Conversation validation failed: {type(exc).__name__}") from exc

    payload = report.to_dict()
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        click.echo(f"MCP conversation validation: {report.endpoint}")
        click.echo(f"Mode: {report.mode}")
        if report.mode == "managed_loopback" and report.ok:
            click.echo("Capacity: local owned, $0, no fallback")
        else:
            click.echo("Capacity: unverified; no tool call submitted")
        for check in report.checks:
            state = "ok" if check.status == "passed" else "fail"
            click.echo(f"[{state}] {check.name}: {check.detail}")
        click.echo("Result: passed" if report.ok else "Result: failed")

    if not report.ok:
        sys.exit(1)
