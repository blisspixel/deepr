"""Offline provider-billing reconciliation CLI."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from deepr.observability.provider_billing import ProviderBillingError, reconcile_billing_file

console = Console()


def _usd(microusd: int) -> str:
    return f"${microusd / 1_000_000:.6f}"


@click.command("reconcile-billing")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--apply", "apply_result", is_flag=True, help="Persist sanitized evidence and freeze on uncertainty")
@click.option("--json", "json_output", is_flag=True, help="Emit the published machine-readable contract")
@click.option("--expect-provider", default=None, help="Require this provider identity")
@click.option("--expect-scope-ref", default=None, help="Require this opaque billing scope")
@click.option("--ledger-path", type=click.Path(dir_okay=False, path_type=Path), default=None, hidden=True)
@click.option("--store-root", type=click.Path(file_okay=False, path_type=Path), default=None, hidden=True)
@click.option("--budget-path", type=click.Path(dir_okay=False, path_type=Path), default=None, hidden=True)
def reconcile_billing_command(
    path: Path,
    apply_result: bool,
    json_output: bool,
    expect_provider: str | None,
    expect_scope_ref: str | None,
    ledger_path: Path | None,
    store_root: Path | None,
    budget_path: Path | None,
) -> None:
    """Compare normalized provider charges with exact local receipt evidence."""
    try:
        report = reconcile_billing_file(
            path,
            apply=apply_result,
            expect_provider=expect_provider,
            expect_scope_ref=expect_scope_ref,
            ledger_path=ledger_path,
            store_root=store_root,
            budget_path=budget_path,
        )
    except ProviderBillingError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException("Billing reconciliation failed closed; paid dispatch remains blocked.") from exc

    if json_output:
        click.echo(json.dumps(report.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))
    else:
        table = Table(title="Provider Billing Reconciliation")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("Mode", "applied" if apply_result else "write-free preview")
        table.add_row("Status", report.status.upper())
        table.add_row("Provider", report.provider)
        table.add_row("Scope", report.scope_ref)
        table.add_row("Statement", report.statement_id)
        table.add_row("Provider net", _usd(report.provider_net_microusd))
        table.add_row("Local ledger", _usd(report.local_ledger_microusd))
        table.add_row("Gross unexplained positive", _usd(report.gross_unexplained_positive_microusd))
        table.add_row("Unmatched provider lines", str(report.match_counts.unmatched_positive_lines))
        table.add_row("Ambiguous provider lines", str(report.match_counts.ambiguous_positive_lines))
        table.add_row("Unmatched local events", str(report.match_counts.unmatched_local_events))
        table.add_row("Paid freeze required", "yes" if report.freeze_required else "no")
        table.add_row("Paid freeze applied", "yes" if report.freeze_applied else "no")
        console.print(table)
        console.print("No network or provider call was made.")
        if not apply_result:
            console.print("Preview wrote no files and changed no spend authority.")
        if report.status == "clean":
            console.print("Clean reconciliation does not unfreeze paid API capacity.")
    if report.status != "clean":
        raise SystemExit(1)


__all__ = ["reconcile_billing_command"]
