"""MCP durable conversation validation CLI."""

from __future__ import annotations

import json
import os
import sys

import click

from deepr.cli.async_runner import run_async_command


@click.command("validate-conversation")
@click.argument("url", required=False)
@click.option("--auth-token", help="Bearer token or scoped-key secret for a remote HTTP MCP endpoint.")
@click.option("--expert", help="Optional canonical expert name. Omit to use focused auto-routing.")
@click.option("--local-model", help="Optional pinned Ollama model.")
@click.option("--start-message", default=None, help="Override the first validation question.")
@click.option("--continue-message", default=None, help="Override the follow-up validation question.")
@click.option("--timeout", "timeout_seconds", default=180.0, show_default=True, type=click.FloatRange(min=1.0))
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
    """Validate durable local expert conversation over authenticated MCP."""
    from deepr.mcp.conversation_validation import (
        DEFAULT_CONTINUE_MESSAGE,
        DEFAULT_START_MESSAGE,
        run_http_conversation_validation,
    )

    resolved_start = start_message or DEFAULT_START_MESSAGE
    resolved_continue = continue_message or DEFAULT_CONTINUE_MESSAGE
    try:
        if url:
            resolved_token = auth_token or os.getenv("MCP_AUTH_TOKEN") or os.getenv("DEEPR_MCP_AUTH_TOKEN")
            if not resolved_token:
                raise click.ClickException(
                    "Remote validation requires --auth-token, MCP_AUTH_TOKEN, or DEEPR_MCP_AUTH_TOKEN."
                )
            report = run_async_command(
                run_http_conversation_validation(
                    url,
                    auth_token=resolved_token,
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
        click.echo("Capacity: local owned, $0, no fallback")
        for check in report.checks:
            state = "ok" if check.status == "passed" else "fail"
            click.echo(f"[{state}] {check.name}: {check.detail}")
        click.echo("Result: passed" if report.ok else "Result: failed")

    if not report.ok:
        sys.exit(1)
