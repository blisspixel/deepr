"""CLI: offline machine-checkable MCP conformance report."""

from __future__ import annotations

import json
import sys

import click


@click.command("conformance")
@click.option("--json", "as_json", is_flag=True, help="Emit the versioned conformance payload as JSON.")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=str),
    help="Write the full JSON report to a file.",
)
def conformance(as_json: bool, output: str | None) -> None:
    """Run offline MCP host-interop conformance checks ($0, no network, no model).

    Proves dual-era protocol constants, offline consult form contracts, remote
    smoke fail-closed posture, managed conversation fail-closed posture,
    registration-manifest offline shape, and the capabilities map. Does not
    score semantic answer quality and does not open remote connections.
    """
    from pathlib import Path

    from deepr.mcp.conformance import run_offline_mcp_conformance

    try:
        report = run_offline_mcp_conformance()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    payload = report.to_dict()
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    if output:
        Path(output).write_text(text, encoding="utf-8")
        if not as_json:
            click.echo(f"Wrote MCP conformance report: {output}")

    if as_json:
        click.echo(text, nl=False)
    elif not output:
        click.echo(f"MCP offline conformance (server {report.server_version})")
        click.echo(f"Protocol: modern {payload['protocol']['modern']}; legacy {payload['protocol']['legacy']}")
        for check in report.checks:
            state = "ok" if check.status == "passed" else "fail"
            click.echo(f"[{state}] {check.name}: {check.detail}")
        click.echo("Result: passed" if report.ok else "Result: failed")
        click.echo("Cost: $0.0000 (offline; no network; no model)")

    if not report.ok:
        sys.exit(1)
