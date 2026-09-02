"""OpenRouter public catalog proof command."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

from deepr.providers.openrouter_catalog_check import (
    OPENROUTER_CATALOG_CHECK_KIND,
    OPENROUTER_CATALOG_CHECK_SCHEMA_VERSION,
    OpenRouterCatalogCheckError,
    check_openrouter_catalog,
    openrouter_models,
)

console = Console()


@click.command("openrouter-check")
@click.option("--model", type=click.Choice(openrouter_models()), help="Check one exact OpenRouter model slug")
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned machine-readable proof")
def openrouter_check(model: str | None, json_output: bool) -> None:
    """Check exact OpenRouter routes using public metadata and no API key."""
    targets = (model,) if model is not None else openrouter_models()
    try:
        proofs = check_openrouter_catalog(targets)
    except OpenRouterCatalogCheckError as exc:
        raise click.ClickException(str(exc)) from exc
    all_eligible = all(proof.catalog_eligible for proof in proofs)
    payload = {
        "schema_version": OPENROUTER_CATALOG_CHECK_SCHEMA_VERSION,
        "kind": OPENROUTER_CATALOG_CHECK_KIND,
        "checked_count": len(proofs),
        "all_catalog_eligible": all_eligible,
        "public_metadata_requests": len(targets),
        "paid_requests": 0,
        "api_key_loaded": False,
        "dispatch_authorized": False,
        "proofs": [proof.to_dict() for proof in proofs],
    }
    if json_output:
        click.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))
    else:
        table = Table(title="OpenRouter Public Catalog Proof")
        table.add_column("Model", style="cyan")
        table.add_column("Exact upstream")
        table.add_column("Observed input / output / cache-write $/M", justify="right")
        table.add_column("Registered input / output / cache-write cap $/M", justify="right")
        table.add_column("Result")
        for proof in proofs:
            observed = (
                "unknown"
                if (
                    proof.observed_input_cost_per_1m is None
                    or proof.observed_output_cost_per_1m is None
                    or proof.observed_cache_write_cost_per_1m is None
                )
                else (
                    f"{proof.observed_input_cost_per_1m:g} / "
                    f"{proof.observed_output_cost_per_1m:g} / "
                    f"{proof.observed_cache_write_cost_per_1m:g}"
                )
            )
            cap = (
                f"{proof.registered_input_cap_per_1m:g} / "
                f"{proof.registered_output_cap_per_1m:g} / "
                f"{proof.registered_cache_write_cap_per_1m:g}"
            )
            result = "eligible" if proof.catalog_eligible else "; ".join(proof.failures)
            table.add_row(proof.model, proof.upstream_tag, observed, cap, result)
        console.print(table)
        click.echo("Public metadata only: 0 paid requests, no API key loaded, dispatch remains blocked.")
    if not all_eligible:
        raise click.exceptions.Exit(1)


__all__ = ["openrouter_check"]
