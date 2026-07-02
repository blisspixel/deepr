"""`deepr eval recall` - $0 lexical-vs-vector recall routing eval.

Split from eval.py so that file stays under the size ceiling. Registered on
the `eval` group; cli/main.py imports this module for its registration side
effect, so importing eval.py alone does not expose the command.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from deepr.cli.commands.eval import evaluate


def _validate_embedding_flags(
    local_embedding_model: str | None,
    query_embeddings_json: Path | None,
    embedding_model: str | None,
) -> None:
    if local_embedding_model and query_embeddings_json:
        raise click.ClickException("Use either --local-embedding-model or --query-embeddings-json, not both.")
    if query_embeddings_json and not embedding_model:
        raise click.ClickException("--embedding-model is required with --query-embeddings-json.")
    if embedding_model and not query_embeddings_json:
        raise click.ClickException("--embedding-model applies only to --query-embeddings-json.")


def _render_recall_report(report: dict, name: str, top_k: int) -> None:
    click.echo(f"Recall routing eval for {name}  ({report['request']['case_count']} case(s), top_k={top_k})")
    for route_name, summary in report["routes"].items():
        click.echo(
            f"  - {route_name:18s}  hit@k {summary['hit_at_k']:6.1%}  "
            f"MRR {summary['mean_reciprocal_rank']:.3f}  "
            f"relevant/case {summary['mean_relevant_retrieved']:.2f}"
        )
    comparison = report["comparison"]
    if comparison["vector_route_evaluated"]:
        winners = comparison["winners_by_metric"]
        click.echo("  Winners: " + ", ".join(f"{metric}={winner}" for metric, winner in winners.items()))
    else:
        click.echo(f"  Vector route skipped: {comparison['skip_reason']}")
    click.echo("  Routing evidence only; labels are operator-supplied, not semantic verdicts.")


@evaluate.command("recall")
@click.argument("name")
@click.option(
    "--cases",
    "cases_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="JSON array of labeled cases: case_id, query, relevant_belief_ids.",
)
@click.option("--top-k", type=click.IntRange(min=1, max=50), default=5, show_default=True)
@click.option(
    "--local-embedding-model",
    default=None,
    help="Embed case queries through this local Ollama model at $0 for the vector route; no metered fallback.",
)
@click.option(
    "--query-embeddings-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="JSON object mapping case_id to a precomputed query vector.",
)
@click.option("--embedding-model", default=None, help="Model label for precomputed query vectors.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--save", is_flag=True, help="Save JSON artifact under the configured benchmarks directory.")
def eval_recall(
    name: str,
    cases_path: Path,
    top_k: int,
    local_embedding_model: str | None,
    query_embeddings_json: Path | None,
    embedding_model: str | None,
    json_output: bool,
    save: bool,
):
    """Compare lexical vs vector recall routing on labeled cases (cost $0).

    Relevance labels come from the operator-supplied cases file; this eval
    computes only deterministic retrieval metrics against them. A route
    winning here is routing evidence for schedulers and operators, never a
    semantic verdict about belief truth.
    """
    import asyncio

    from deepr.evals.recall_quality import load_recall_eval_cases, run_recall_quality_eval, write_recall_eval_report
    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.expert_semantic_recall import coerce_belief_embedding_map
    from deepr.experts.profile import ExpertStore

    _validate_embedding_flags(local_embedding_model, query_embeddings_json, embedding_model)
    if ExpertStore().load(name) is None:
        raise click.ClickException(f"Expert '{name}' not found. Create one: deepr expert make '{name}'.")

    try:
        cases = load_recall_eval_cases(json.loads(cases_path.read_text(encoding="utf-8")))
        embeddings_by_case = None
        embed_queries = None
        resolved_model = embedding_model
        if query_embeddings_json is not None:
            embeddings_by_case = coerce_belief_embedding_map(
                json.loads(query_embeddings_json.read_text(encoding="utf-8"))
            )
        elif local_embedding_model:
            from deepr.backends.local import make_local_embedder

            embed_queries = make_local_embedder(local_embedding_model)
            resolved_model = local_embedding_model
        report = asyncio.run(
            run_recall_quality_eval(
                BeliefStore(name),
                cases,
                expert_name=name,
                top_k=top_k,
                embedding_model=resolved_model,
                query_embeddings_by_case_id=embeddings_by_case,
                embed_queries=embed_queries,
            )
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(str(exc))
    except Exception as exc:
        raise click.ClickException(
            f"recall eval failed: {exc}. If using --local-embedding-model, check that Ollama is running "
            "and the embedding model is pulled; Deepr never falls back to a metered embedding provider."
        )

    path = write_recall_eval_report(report) if save else None
    if json_output:
        # Keep stdout one valid JSON document; the saved path rides inside the
        # payload, matching the sibling eval commands.
        payload = {**report, "saved_to": str(path)} if path else report
        click.echo(json.dumps(payload, indent=2))
        return
    _render_recall_report(report, name, top_k)
    if path:
        click.echo(f"\nSaved {path}")
