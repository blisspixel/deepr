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


@evaluate.command("local")
@click.option(
    "--model",
    "models",
    multiple=True,
    help="Local Ollama model to compare. Repeat for multiple models. Defaults to installed models.",
)
@click.option(
    "--judge-model",
    default=None,
    help="Local Ollama model used as judge. Defaults to the first selected model unless a CLI judge is used.",
)
@click.option(
    "--judge-cli",
    type=click.Choice(["grok"]),
    default=None,
    help="Use a known headless CLI judge preset. Requires --allow-cli-judge.",
)
@click.option(
    "--judge-command",
    default=None,
    help="Custom CLI judge command template containing {prompt_file}. Requires --allow-cli-judge.",
)
@click.option(
    "--judge-name",
    default=None,
    help="Display name for a custom CLI judge.",
)
@click.option(
    "--judge-timeout",
    type=float,
    default=120.0,
    show_default=True,
    help="CLI judge timeout in seconds.",
)
@click.option(
    "--allow-cli-judge",
    is_flag=True,
    help="Confirm the CLI judge is an intentional non-metered or bounded-capacity path.",
)
@click.option(
    "--prompt-set",
    type=click.Choice(["agentic-loops"]),
    default="agentic-loops",
    show_default=True,
    help="Built-in $0 prompt set to run.",
)
@click.option(
    "--max-models",
    type=int,
    default=2,
    show_default=True,
    help="Maximum installed models to compare when --model is omitted.",
)
@click.option(
    "--max-prompts",
    type=int,
    default=2,
    show_default=True,
    help="Maximum prompts from the prompt set to run.",
)
@click.option("--save", is_flag=True, help="Save JSON artifact under data/benchmarks.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def eval_local(
    models: tuple[str, ...],
    judge_model: str | None,
    judge_cli: str | None,
    judge_command: str | None,
    judge_name: str | None,
    judge_timeout: float,
    allow_cli_judge: bool,
    prompt_set: str,
    max_models: int,
    max_prompts: int,
    save: bool,
    json_output: bool,
):
    """Compare local Ollama models with a local LLM judge (cost $0)."""
    from deepr.cli.async_runner import run_async_command
    from deepr.evals.local_compare import run_local_comparison, write_report

    cli_judge = _build_cli_judge(judge_cli, judge_command, judge_name, judge_timeout, allow_cli_judge)
    if cli_judge and judge_model:
        raise click.ClickException("--judge-model is only for local Ollama judges; omit it when using a CLI judge.")

    selected, judge, prompts = _resolve_local_eval_inputs(
        models,
        judge_model,
        prompt_set,
        max_models,
        max_prompts,
        require_local_judge=cli_judge is None,
    )
    judge_label = cli_judge.display_name if cli_judge else judge

    if not json_output:
        click.echo(
            f"Running local comparison: models={', '.join(selected)}; judge={judge_label}; prompts={len(prompts)}"
        )
        click.echo("Deepr metered cost: $0. CLI judges may still consume external quota.")

    report = run_async_command(
        run_local_comparison(
            selected,
            judge_model=judge,
            judge_command=cli_judge,
            prompts=prompts,
            prompt_set=prompt_set,
        )
    )

    if save:
        path = write_report(report)
    else:
        path = None

    if json_output:
        _emit_local_eval_json(report, path)
        return

    _emit_local_eval_summary(report, path)


def _resolve_local_eval_inputs(
    models: tuple[str, ...],
    judge_model: str | None,
    prompt_set: str,
    max_models: int,
    max_prompts: int,
    *,
    require_local_judge: bool = True,
):
    from deepr.backends.capacity import available_local_models
    from deepr.evals.local_compare import default_prompts

    if max_models <= 0:
        raise click.ClickException("--max-models must be positive.")
    if max_prompts <= 0:
        raise click.ClickException("--max-prompts must be positive.")

    installed = available_local_models()
    if not installed:
        raise click.ClickException("No local Ollama models available. Start Ollama and pull a model first.")

    selected = list(models) if models else installed[:max_models]
    missing = [model for model in selected if model not in installed]
    if missing:
        raise click.ClickException(f"Local model(s) not installed: {', '.join(missing)}")

    judge = judge_model or (selected[0] if require_local_judge else "")
    if judge and judge not in installed:
        raise click.ClickException(f"Judge model is not installed locally: {judge}")

    prompts = default_prompts(prompt_set)[:max_prompts]
    if not prompts:
        raise click.ClickException(f"No prompts available for prompt set {prompt_set!r}.")
    return selected, judge, prompts


def _build_cli_judge(
    judge_cli: str | None,
    judge_command: str | None,
    judge_name: str | None,
    judge_timeout: float,
    allow_cli_judge: bool,
):
    from deepr.evals.local_compare import GROK_JUDGE_COMMAND, CliJudgeCommand

    if judge_cli and judge_command:
        raise click.ClickException("Use --judge-cli or --judge-command, not both.")
    if not judge_cli and not judge_command:
        return None
    if not allow_cli_judge:
        raise click.ClickException(
            "CLI judges can consume remote quota. Re-run with --allow-cli-judge after confirming the CLI is not a "
            "metered API path."
        )
    try:
        if judge_cli == "grok":
            return CliJudgeCommand(
                template=GROK_JUDGE_COMMAND,
                display_name=judge_name or "cli:grok",
                timeout_seconds=judge_timeout,
            )
        return CliJudgeCommand(
            template=judge_command or "",
            display_name=judge_name or "cli:custom",
            timeout_seconds=judge_timeout,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


def _emit_local_eval_json(report, path: Path | None) -> None:
    data = report.to_dict()
    if path:
        data["saved_to"] = str(path)
    click.echo(json.dumps(data, indent=2))


def _emit_local_eval_summary(report, path: Path | None) -> None:
    click.echo("")
    click.echo(f"Winner: {report.winner or 'n/a'}")
    click.echo("")
    click.echo(f"{'Model':32s} {'Score':>7s} {'Latency':>10s} {'Cost':>7s}")
    for comparison in sorted(
        report.comparisons,
        key=lambda item: (item.average_score, -item.average_latency_ms, item.model),
        reverse=True,
    ):
        click.echo(
            f"{comparison.model[:32]:32s} {comparison.average_score:7.3f} "
            f"{comparison.average_latency_ms:8d}ms ${comparison.cost:5.2f}"
        )
    if path:
        click.echo(f"\nSaved {path}")
    click.echo("\nScores are local-judge estimates; use them as routing evidence, not ground truth.")


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
    from deepr.experts.profile import ExpertStore

    # Check the expert exists before touching BeliefStore (whose constructor
    # would otherwise create an empty dir for a typo'd name).
    if ExpertStore().load(name) is None:
        raise click.ClickException(f"Expert '{name}' not found. Create one: deepr expert make '{name}'.")

    store = BeliefStore(name)
    if not store.beliefs and not store.has_event_log:
        raise click.ClickException(
            f"Expert '{name}' has no beliefs yet to measure. Synthesize its documents into beliefs first: "
            f"deepr expert refresh '{name}' --synthesize (or recreate it with --learn)."
        )

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


def _load_corpus(corpus_dir: str, sample: int) -> dict[str, str]:
    """Load .md/.txt reports from a directory (optionally capped to `sample`)."""
    paths = sorted(p for p in Path(corpus_dir).iterdir() if p.suffix.lower() in (".md", ".txt"))
    if sample > 0:
        paths = paths[:sample]
    return {p.stem: p.read_text(encoding="utf-8") for p in paths}


def _calibration_extract_fn(model: str):
    """Reuse the absorb extraction (the model being calibrated) over raw text."""
    import tempfile

    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.profile import ExpertProfile
    from deepr.experts.report_absorber import ReportAbsorber

    profile = ExpertProfile(name="__calibration__", vector_store_id="", domain="general")
    belief_store = BeliefStore("__calibration__", storage_dir=Path(tempfile.mkdtemp()) / "beliefs")
    absorber = ReportAbsorber(profile, model=model, belief_store=belief_store)

    async def extract(text: str) -> list[tuple[str, float]]:
        cands = await absorber._extract_claims(text, 25)
        return [(c.statement, c.confidence) for c in cands]

    return extract


def _calibration_grade_fn(grader_model: str):
    """Strong-model pre-grader: is a claim grounded in its report? (spot-correct after)."""
    import json as _json

    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    system = (
        "You judge whether a CLAIM is directly supported by a REPORT. Grounded means the report "
        "states or directly entails the claim - not merely that the claim is plausible. "
        'Answer ONLY JSON: {"grounded": true|false}.'
    )

    async def grade(claim: str, report_text: str) -> bool:
        resp = await client.chat.completions.create(
            model=grader_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"REPORT:\n{report_text}\n\nCLAIM: {claim}\n\nIs the claim grounded?"},
            ],
            response_format={"type": "json_object"},
        )
        return bool(_json.loads(resp.choices[0].message.content or "{}").get("grounded", False))

    return grade


@evaluate.command("calibrate")
@click.option(
    "--from",
    "from_file",
    type=click.Path(exists=True, dir_okay=False),
    help='Graded-pairs JSONL: one {"confidence": float, "grounded": bool} per line.',
)
@click.option(
    "--corpus",
    "corpus_dir",
    type=click.Path(exists=True, file_okay=False),
    help="Directory of report .md/.txt files to extract + pre-grade (PAID).",
)
@click.option("--grader-model", default="gpt-5", show_default=True, help="Strong model used to pre-grade grounding.")
@click.option("--sample", type=int, default=0, help="Cap the number of corpus reports (0 = all).")
@click.option(
    "--max-cost", type=float, default=3.0, show_default=True, help="Abort if the estimate exceeds this (USD)."
)
@click.option("-y", "--yes", is_flag=True, help="Skip the spend confirmation.")
@click.option(
    "--model",
    default="unknown",
    show_default=True,
    help="Extraction model (the one being calibrated). With --corpus, this model runs.",
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
    from_file: str | None,
    corpus_dir: str | None,
    grader_model: str,
    sample: int,
    max_cost: float,
    yes: bool,
    model: str,
    target: float,
    decision_threshold: float,
    out: str,
    json_output: bool,
):
    """Measure and publish absorb-confidence calibration.

    Does 0.7 extraction confidence mean ~70% grounded? With --from <graded.jsonl>
    it publishes the curve from already-graded pairs (cost $0). With --corpus
    <dir> it runs the PAID pipeline: extract claims (the --model being
    calibrated) and pre-grade their grounding with --grader-model, then publish.
    The pre-grade is a starting point - the saved <out>.graded.jsonl is meant to
    be spot-corrected for a definitive curve.
    """
    import asyncio

    from deepr.experts.calibration import (
        grade_corpus,
        measure_calibration,
        parse_graded_pairs,
        render_calibration_markdown,
    )

    if not from_file and not corpus_dir:
        raise click.ClickException("Provide --from <graded.jsonl> ($0) or --corpus <dir> (paid extraction + grading).")

    if corpus_dir:
        reports = _load_corpus(corpus_dir, sample)
        if not reports:
            raise click.ClickException(f"No .md/.txt reports found in {corpus_dir}.")
        # Conservative estimate: per-report extraction + grading of ~10 claims.
        estimate = len(reports) * (0.03 + 10 * 0.02)
        click.echo(f"Corpus: {len(reports)} report(s); estimated cost up to ${estimate:.2f} (cap ${max_cost:.2f}).")
        if estimate > max_cost:
            raise click.ClickException(
                f"Estimate ${estimate:.2f} exceeds --max-cost ${max_cost:.2f}. Raise it or --sample fewer."
            )
        if not yes and not click.confirm("Run paid extraction + grading?", default=False):
            raise click.ClickException("Cancelled.")
        pairs, records = asyncio.run(
            grade_corpus(
                reports,
                extract_fn=_calibration_extract_fn(model),
                grade_fn=_calibration_grade_fn(grader_model),
                on_progress=lambda m: click.echo(f"  {m}"),
            )
        )
        graded_path = Path(out).with_suffix(".graded.jsonl")
        graded_path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        click.echo(f"Wrote {graded_path} (spot-correct it, then re-publish with --from)")
    else:
        pairs = parse_graded_pairs(Path(from_file).read_text(encoding="utf-8"))

    if not pairs:
        raise click.ClickException("No graded pairs produced.")

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
