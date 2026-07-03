"""`deepr eval grounding-correctness` - measure whether the grounding checker is right.

Split from eval.py so that file stays under the size ceiling. Registered on the
`eval` group; cli/main.py imports this module for its registration side effect.

Runs the grounding checker over a curated golden set of human-labeled
claim/evidence entailment triples and reports whether a SUPPORTED verdict is
actually correct - the number that turns "trust a verified belief" from an
assertion into a measurement. Defaults to a local Ollama checker at $0.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from deepr.cli.colors import console, print_error, print_header
from deepr.cli.commands.eval import evaluate


def _build_checker(checker_plan: str | None, checker_plan_model: str | None, model: str | None):
    """Build a grounding checker (local $0 by default, or an explicit plan CLI). No metered fallback.

    Reuses the canonical ``build_grounding_checker`` (the same builder the absorb/
    sync grounding path uses) so the plan-quota resolution and vendor/assurance
    selection are single-sourced; this command only supplies the local Ollama
    client as the default and computes a display label. Returns ``(checker, label)``.
    """
    from deepr.cli.commands.semantic.grounding_support import build_grounding_checker

    try:
        if checker_plan:
            checker = build_grounding_checker(
                enabled=True,
                checker_plan=checker_plan,
                checker_plan_model=checker_plan_model,
                maker_vendor="local",
            )
            return checker, f"plan:{checker_plan}"

        from deepr.backends.local import default_local_model, ollama_chat_client

        local_model = model or default_local_model()
        if not local_model:
            raise click.ClickException("No local model available. Is Ollama running? Check: deepr capacity --probe")
        checker = build_grounding_checker(
            enabled=True,
            checker_plan=None,
            checker_plan_model=None,
            maker_vendor="local",
            default_client=ollama_chat_client(),
            default_vendor="local",
            default_model=local_model,
        )
        return checker, f"local:{local_model}"
    except ValueError as exc:
        # build_grounding_checker raises ValueError for a bad plan/backend; surface
        # it as a clean click error the command turns into exit 2.
        raise click.ClickException(str(exc)) from exc


def _render_report(report: dict, checker_label: str) -> None:
    print_header("Grounding correctness")
    console.print(
        f"[dim]checker: {checker_label}  |  {report['case_count']} curated case(s) ({report['label_counts']})[/dim]"
    )
    console.print(
        f"  [bold]support precision[/bold]: {report['support_precision']:.1%}  "
        "[dim](when it says SUPPORTED, how often the evidence truly entails)[/dim]"
    )
    console.print(
        f"  [bold]false-support rate[/bold]: {report['false_support_rate']:.1%}  "
        "[dim](stamped SUPPORTED for contradicted/unrelated evidence - lower is safer)[/dim]"
    )
    console.print(f"  support recall: {report['support_recall']:.1%}   abstention: {report['abstention_rate']:.1%}")
    console.print(f"  overall accuracy: {report['overall_accuracy']:.1%}   per-label: {report['label_accuracy']}")
    console.print(
        "[dim]Agreement on a bounded curated set is not proof of world-truth; it measures "
        "entailment-verdict correctness. Labels are human-curated; the checker owns the verdict.[/dim]"
    )


@evaluate.command("grounding-correctness")
@click.option(
    "--checker-plan",
    default=None,
    help="Use this plan-quota CLI as the checker (default: local Ollama at $0)",
)
@click.option("--checker-plan-model", default=None, help="Model to pass to the checker plan CLI")
@click.option("--model", default=None, help="Local Ollama model to check with (default: auto)")
@click.option(
    "--set",
    "case_set",
    type=click.Choice(["baseline", "hard", "all"]),
    default="baseline",
    show_default=True,
    help="Which built-in golden set: baseline (clear), hard (adversarial), or all. Ignored when --cases is given.",
)
@click.option(
    "--cases",
    "cases_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="JSON array of {case_id, claim, evidence, label} triples (default: built-in golden set)",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the report as JSON")
@click.option("--save", is_flag=True, help="Write the report under the benchmarks directory")
def grounding_correctness(
    checker_plan: str | None,
    checker_plan_model: str | None,
    model: str | None,
    case_set: str,
    cases_path: Path | None,
    json_output: bool,
    save: bool,
) -> None:
    """Measure whether the grounding checker's SUPPORTED verdicts are actually correct.

    $0 by default (local Ollama). Reports support precision, false-support rate,
    recall, and abstention over a curated golden set of entailment triples. The
    `hard` set adds adversarial cases (lexical traps, unit/number flips, shared-
    entity distractors, and partial-entailment of conjunctive claims).

    EXAMPLES:
      deepr eval grounding-correctness
      deepr eval grounding-correctness --set hard --json
      deepr eval grounding-correctness --checker-plan codex --set all --save
    """
    from deepr.evals.grounding_correctness import (
        DEFAULT_GROUNDING_CASES,
        HARD_GROUNDING_CASES,
        load_grounding_cases,
        run_grounding_correctness_eval,
        write_grounding_correctness_report,
    )

    if cases_path is not None:
        try:
            cases = load_grounding_cases(json.loads(cases_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print_error(f"Could not load cases: {exc}")
            sys.exit(2)
    elif case_set == "hard":
        cases = list(HARD_GROUNDING_CASES)
    elif case_set == "all":
        cases = list(DEFAULT_GROUNDING_CASES) + list(HARD_GROUNDING_CASES)
    else:
        cases = list(DEFAULT_GROUNDING_CASES)

    try:
        checker, checker_label = _build_checker(checker_plan, checker_plan_model, model)
    except click.ClickException as exc:
        print_error(exc.message)
        sys.exit(2)

    report = asyncio.run(run_grounding_correctness_eval(cases, checker))

    if save:
        path = write_grounding_correctness_report(report)
        report["saved_to"] = str(path)

    if json_output:
        click.echo(json.dumps(report, indent=2))
        return

    _render_report(report, checker_label)
    if save:
        console.print(f"[dim]Saved: {report['saved_to']}[/dim]")
