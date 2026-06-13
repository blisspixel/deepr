from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_models.py"


@click.group(name="eval")
def evaluate():
    """Run model evaluation workflows with cost safety defaults."""


@evaluate.command("new")
@click.option(
    "--tier", type=click.Choice(["chat", "news", "research", "docs", "all"]), default="all", show_default=True
)
@click.option("--dry-run", is_flag=True, help="Only show plan + estimated cost.")
@click.option("--quick", is_flag=True, help="Use smaller prompt set.")
@click.option("--no-judge", is_flag=True, help="Skip judge model to reduce cost.")
@click.option(
    "--max-estimated-cost",
    type=float,
    default=1.0,
    show_default=True,
    help="Abort if estimate exceeds this amount (USD).",
)
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
    # Internal benchmark_models.py; CLI user-invoked, no untrusted input in command construction.
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise click.ClickException(f"Benchmark exited with status {result.returncode}")


@evaluate.command("continuity")
@click.argument("name")
@click.option(
    "--threshold",
    type=float,
    default=0.3,
    show_default=True,
    help="Effective-confidence floor for staleness checks.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def eval_continuity(name: str, threshold: float, json_output: bool):
    """Measure an expert's continuity properties from stored state (cost $0).

    Unlike `eval new/all`, this makes no API calls: it reads the expert's
    belief store and scores four properties - staleness honesty, abstention
    correctness, contradiction surfacing, and what-changed exactness -
    deepr's own continuity surface rather than a borrowed memory benchmark.
    """
    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.continuity_metrics import measure_continuity

    store = BeliefStore(name)
    if not store.beliefs and not store.has_event_log:
        raise click.ClickException(f"Expert '{name}' has no belief store to measure. Create or learn an expert first.")

    report = measure_continuity(store, staleness_threshold=threshold, expert_name=name)

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    overall = report.overall
    click.echo(f"Continuity report for {name}  (methodology v{report.methodology_version})")
    click.echo(f"Overall: {overall:.1%}" if overall is not None else "Overall: n/a (no applicable metrics)")
    click.echo("")
    for metric in report.metrics:
        label = metric.name.replace("_", " ")
        if not metric.applicable:
            reason = metric.detail.get("reason", "not applicable")
            click.echo(f"  - {label:24s}  n/a  ({reason})")
            continue
        click.echo(f"  - {label:24s}  {metric.score:6.1%}  (n={metric.sample_size})")
        if metric.name == "staleness_honesty" and metric.detail.get("hidden_stale"):
            click.echo(f"      WARNING: {metric.detail['hidden_stale']} aged belief(s) reported fresh")
        if metric.name == "abstention_correctness" and metric.detail.get("over_asserted"):
            click.echo(f"      WARNING: {len(metric.detail['over_asserted'])} ungrounded belief(s) over-asserted")
        if metric.name == "contradiction_surfacing" and metric.detail.get("missed_pairs"):
            click.echo(f"      WARNING: {len(metric.detail['missed_pairs'])} recorded contradiction(s) not surfaced")
        if metric.name == "what_changed_exactness" and metric.detail.get("window_truncated"):
            click.echo("      note: legacy bounded-window store - history truncated, not exact")


@evaluate.command("calibrate")
@click.option(
    "--from",
    "from_file",
    type=click.Path(exists=True, dir_okay=False),
    help='Graded-pairs JSONL: one {"confidence": float, "grounded": bool} per line.',
)
@click.option(
    "--model",
    default="unknown",
    show_default=True,
    help="Extraction model the pairs were graded against (stamped in the report).",
)
@click.option(
    "--target",
    type=float,
    default=0.8,
    show_default=True,
    help="Grounding rate the derived absorb threshold should guarantee.",
)
@click.option(
    "--decision-threshold",
    type=float,
    default=0.6,
    show_default=True,
    help="Confidence at/above which a claim counts as a grounded prediction.",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False),
    default="docs/CALIBRATION.md",
    show_default=True,
    help="Where to write the published report.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON instead of writing the doc.")
def eval_calibrate(
    from_file: str | None, model: str, target: float, decision_threshold: float, out: str, json_output: bool
):
    """Measure and publish absorb-confidence calibration from graded pairs (cost $0).

    Does 0.7 extraction confidence mean ~70% grounded? This consumes graded
    (confidence, grounded) pairs and produces the calibration curve, ECE,
    Platt-scaled threshold, and docs/CALIBRATION.md. No API calls: the grading
    run that produces the pairs (extraction + pre-grade over a corpus) is a
    separate, budget-gated step.
    """
    from deepr.experts.calibration import measure_calibration, parse_graded_pairs, render_calibration_markdown

    if not from_file:
        raise click.ClickException(
            "Provide --from <graded.jsonl> (the $0 publish path). The paid grading step that "
            "produces graded pairs from a report corpus is a separate command."
        )

    pairs = parse_graded_pairs(Path(from_file).read_text(encoding="utf-8"))
    if not pairs:
        raise click.ClickException(f"No graded pairs found in {from_file}.")

    report = measure_calibration(pairs, target_grounding=target, decision_threshold=decision_threshold)

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    Path(out).write_text(render_calibration_markdown(report, model=model), encoding="utf-8")
    threshold = "n/a" if report.derived_threshold is None else f"{report.derived_threshold:.3f}"
    click.echo(
        f"Calibration: n={report.sample_size}, ECE={report.ece:.3f} "
        f"(Platt {report.ece_platt:.3f}), derived threshold={threshold}"
    )
    click.echo(f"Wrote {out}")


@evaluate.command("status")
def eval_status():
    """Show which models have benchmark data vs provisional rankings."""
    from deepr.providers.registry import MODEL_CAPABILITIES
    from deepr.routing.auto_mode import _compute_registry_hash, _load_benchmark_rankings

    real = _load_benchmark_rankings()
    benchmarked: set[str] = set()
    if real:
        for entries in real.values():
            for provider, model, _q, _c in entries:
                benchmarked.add(f"{provider}/{model}")

    all_models = sorted(MODEL_CAPABILITIES.keys())
    missing = [m for m in all_models if m not in benchmarked]

    click.echo(f"Registry models: {len(all_models)}")
    click.echo(f"Benchmarked:     {len(benchmarked)}")
    click.echo(f"Provisional:     {len(missing)}")

    if missing:
        click.echo("\nModels using provisional (estimated) rankings:")
        for m in missing:
            cap = MODEL_CAPABILITIES[m]
            click.echo(f"  {m:45s}  cost=${cap.cost_per_query:.3f}  specs={','.join(cap.specializations[:3])}")

    hash_file = Path("data/benchmarks/.registry_hash")
    if hash_file.exists():
        stored = hash_file.read_text().strip()
        current = _compute_registry_hash()
        if stored == current:
            click.echo("\nRegistry hash: up to date")
        else:
            click.echo("\nRegistry hash: STALE (new models added since last eval)")
            click.echo("  Run: deepr eval new --dry-run")
    else:
        click.echo("\nRegistry hash: not found (no auto-eval has run yet)")
        click.echo("  Run: deepr eval new --dry-run")


@evaluate.command("all")
@click.option("--dry-run", is_flag=True, help="Only show plan + estimated cost.")
@click.option("--quick", is_flag=True, help="Use smaller prompt set.")
@click.option("--no-judge", is_flag=True, help="Skip judge model to reduce cost.")
@click.option(
    "--max-estimated-cost",
    type=float,
    default=1.0,
    show_default=True,
    help="Abort if estimate exceeds this amount (USD).",
)
@click.option("--approve-expensive", is_flag=True, help="Required to run full all-tier benchmark (non-dry-run).")
@click.option("--save/--no-save", default=True, show_default=True, help="Save benchmark output artifacts.")
def eval_all(
    dry_run: bool, quick: bool, no_judge: bool, max_estimated_cost: float, approve_expensive: bool, save: bool
):
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
    # Internal benchmark_models.py; CLI user-invoked, no untrusted input in command construction.
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise click.ClickException(f"Benchmark exited with status {result.returncode}")
