from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_models.py"


@click.group(name="eval")
def evaluate():
    """Run model evaluation workflows with cost safety defaults."""


@evaluate.command("new")
@click.option("--tier", type=click.Choice(["chat", "news", "research", "docs", "all"]), default="all", show_default=True)
@click.option("--dry-run", is_flag=True, help="Only show plan + estimated cost.")
@click.option("--quick", is_flag=True, help="Use smaller prompt set.")
@click.option("--no-judge", is_flag=True, help="Skip judge model to reduce cost.")
@click.option("--max-estimated-cost", type=float, default=1.0, show_default=True, help="Abort if estimate exceeds this amount (USD).")
@click.option("--save/--no-save", default=True, show_default=True, help="Save benchmark output artifacts.")
def eval_new(tier: str, dry_run: bool, quick: bool, no_judge: bool, max_estimated_cost: float, save: bool):
    """Evaluate only newly added or missing model+tier combinations."""
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--new-models",
        "--tier",
        tier,
        "--max-estimated-cost",
        str(max_estimated_cost),
    ]

    if dry_run:
        cmd.append("--dry-run")
    if quick:
        cmd.append("--quick")
    if no_judge:
        cmd.append("--no-judge")
    if save:
        cmd.append("--save")

    click.echo(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise click.ClickException(f"Benchmark exited with status {result.returncode}")


@evaluate.command("all")
@click.option("--dry-run", is_flag=True, help="Only show plan + estimated cost.")
@click.option("--quick", is_flag=True, help="Use smaller prompt set.")
@click.option("--no-judge", is_flag=True, help="Skip judge model to reduce cost.")
@click.option("--max-estimated-cost", type=float, default=1.0, show_default=True, help="Abort if estimate exceeds this amount (USD).")
@click.option("--approve-expensive", is_flag=True, help="Required to run full all-tier benchmark (non-dry-run).")
@click.option("--save/--no-save", default=True, show_default=True, help="Save benchmark output artifacts.")
def eval_all(dry_run: bool, quick: bool, no_judge: bool, max_estimated_cost: float, approve_expensive: bool, save: bool):
    """Evaluate all configured model tiers (requires explicit approval to execute)."""
    if not dry_run and not approve_expensive:
        raise click.ClickException(
            "Full eval requires --approve-expensive. Use --dry-run first to inspect estimated cost."
        )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--tier",
        "all",
        "--max-estimated-cost",
        str(max_estimated_cost),
    ]

    if dry_run:
        cmd.append("--dry-run")
    if quick:
        cmd.append("--quick")
    if no_judge:
        cmd.append("--no-judge")
    if save:
        cmd.append("--save")

    click.echo(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise click.ClickException(f"Benchmark exited with status {result.returncode}")
