"""`deepr eval recall` - $0 lexical-vs-vector recall routing eval.

Split from eval.py so that file stays under the size ceiling. Registered on
the `eval` group; cli/main.py imports this module for its registration side
effect, so importing eval.py alone does not expose the command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from deepr.cli.commands.eval import evaluate
from deepr.evals.recall_quality import (
    RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION,
    RecallEvalCase,
    build_recall_eval_case,
    build_recall_library_inventory,
    build_recall_operator_validation,
    load_recall_eval_case_library,
    load_recall_eval_cases,
    merge_recall_eval_case_library,
    recall_eval_case_library_path,
)


def _render_recall_library_inventory(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    click.echo(
        "Recall case libraries  "
        f"({summary['valid_library_count']} valid, {summary['invalid_library_count']} invalid, "
        f"{summary['case_count']} case(s))"
    )
    libraries = payload["libraries"]
    if not libraries:
        click.echo("  No accumulated recall case libraries found.")
        click.echo("  Add one with: deepr eval recall NAME --cases cases.json --record-cases")
        return
    for library in libraries:
        expert_name = library.get("expert", {}).get("name", library.get("path", "unknown"))
        state = "ready" if library.get("ready_for_scheduler_preference_eval") else "needs more labels"
        if library.get("status") != "valid":
            state = "invalid"
        click.echo(f"  - {expert_name}: {library['case_count']} case(s), {state}")
        blockers = library.get("blockers", [])
        if blockers:
            click.echo(f"    blockers: {', '.join(blockers)}")
    click.echo("  Inventory only; run `deepr eval recall NAME --save` to produce route evidence.")


@evaluate.command("recall-libraries")
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned library inventory as JSON.")
def eval_recall_libraries(json_output: bool):
    """List accumulated recall case libraries without running retrieval."""
    payload = build_recall_library_inventory()
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    _render_recall_library_inventory(payload)


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
    scheduler_preference = report.get("scheduler_preference", {})
    if scheduler_preference.get("eligible") is True:
        click.echo(f"  Scheduler preference: {scheduler_preference['preferred_route']} eligible")
    else:
        reasons = scheduler_preference.get("reasons", [])
        reason_text = ", ".join(reasons) if isinstance(reasons, list) else "insufficient evidence"
        click.echo(f"  Scheduler preference: not eligible ({reason_text})")
    operator_validation = report.get("operator_validation", {})
    if isinstance(operator_validation, dict):
        if operator_validation.get("eligible_for_explicit_sync_preference") is True:
            click.echo("  Explicit sync preference: ready when saved and supplied by the operator")
        else:
            blockers = operator_validation.get("blockers", [])
            blocker_text = ", ".join(blockers) if isinstance(blockers, list) and blockers else "not ready"
            click.echo(f"  Explicit sync preference: not ready ({blocker_text})")
        click.echo("  Default routing: lexical-first unchanged; explicit report required.")
    click.echo("  Routing evidence only; labels are operator-supplied, not semantic verdicts.")


def _single_case_requested(case_id: str | None, case_query: str | None, relevant_belief_ids: tuple[str, ...]) -> bool:
    return bool(case_id or case_query or relevant_belief_ids)


def _validate_case_input(
    *,
    cases_path: Path | None,
    case_id: str | None,
    case_query: str | None,
    relevant_belief_ids: tuple[str, ...],
    record_cases: bool,
) -> None:
    single_case = _single_case_requested(case_id, case_query, relevant_belief_ids)
    if cases_path is not None and single_case:
        raise click.ClickException("Use either --cases or --query/--relevant-belief-id, not both.")
    if single_case and not case_query:
        raise click.ClickException("--query is required with --case-id or --relevant-belief-id.")
    if case_query and not relevant_belief_ids:
        raise click.ClickException("--relevant-belief-id is required with --query.")
    if record_cases and cases_path is None and not single_case:
        raise click.ClickException("--record-cases requires --cases or --query with --relevant-belief-id.")


def _load_cases_for_eval(
    name: str,
    cases_path: Path | None,
    *,
    case_id: str | None,
    case_query: str | None,
    relevant_belief_ids: tuple[str, ...],
) -> tuple[list[RecallEvalCase], dict | None]:
    if cases_path is not None:
        return load_recall_eval_cases(json.loads(cases_path.read_text(encoding="utf-8"))), None
    if _single_case_requested(case_id, case_query, relevant_belief_ids):
        return [
            build_recall_eval_case(
                case_id=case_id,
                query=case_query or "",
                relevant_belief_ids=relevant_belief_ids,
            )
        ], None

    cases = load_recall_eval_case_library(name)
    return cases, {
        "schema_version": RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION,
        "path": str(recall_eval_case_library_path(name)),
        "case_count": len(cases),
        "source": "accumulated_library",
    }


def _resolve_query_embedding_inputs(
    *,
    local_embedding_model: str | None,
    query_embeddings_json: Path | None,
    embedding_model: str | None,
) -> tuple[dict[str, tuple[float, ...]] | None, Any, str | None]:
    if query_embeddings_json is not None:
        from deepr.experts.expert_semantic_recall import coerce_belief_embedding_map

        return (
            coerce_belief_embedding_map(json.loads(query_embeddings_json.read_text(encoding="utf-8"))),
            None,
            embedding_model,
        )
    if local_embedding_model:
        from deepr.backends.local import make_local_embedder

        return None, make_local_embedder(local_embedding_model), local_embedding_model
    return None, None, embedding_model


@evaluate.command("recall")
@click.argument("name")
@click.option(
    "--cases",
    "cases_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
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
@click.option("--case-id", default=None, help="Case id for a single operator-labeled --query input.")
@click.option("--query", "case_query", default=None, help="Single operator-labeled recall query to evaluate or record.")
@click.option(
    "--relevant-belief-id",
    "relevant_belief_ids",
    multiple=True,
    help="Relevant belief id for a single --query case; repeat for multiple labels.",
)
@click.option(
    "--record-cases",
    is_flag=True,
    help="Merge supplied cases into this expert's runtime-local labeled recall-case library.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--save", is_flag=True, help="Save JSON artifact under the configured benchmarks directory.")
def eval_recall(
    name: str,
    cases_path: Path | None,
    top_k: int,
    local_embedding_model: str | None,
    query_embeddings_json: Path | None,
    embedding_model: str | None,
    case_id: str | None,
    case_query: str | None,
    relevant_belief_ids: tuple[str, ...],
    record_cases: bool,
    json_output: bool,
    save: bool,
):
    """Compare lexical vs vector recall routing on labeled cases (cost $0).

    Relevance labels come from an operator-supplied cases file or one reviewed
    CLI case; this eval computes only deterministic retrieval metrics against
    them. A route winning here is routing evidence for schedulers and
    operators, never a semantic verdict about belief truth.
    """
    import asyncio

    from deepr.evals.recall_quality import run_recall_quality_eval, write_recall_eval_report
    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.profile import ExpertStore

    _validate_embedding_flags(local_embedding_model, query_embeddings_json, embedding_model)
    _validate_case_input(
        cases_path=cases_path,
        case_id=case_id,
        case_query=case_query,
        relevant_belief_ids=relevant_belief_ids,
        record_cases=record_cases,
    )
    if ExpertStore().load(name) is None:
        raise click.ClickException(f"Expert '{name}' not found. Create one: deepr expert make '{name}'.")

    try:
        cases, case_library = _load_cases_for_eval(
            name,
            cases_path,
            case_id=case_id,
            case_query=case_query,
            relevant_belief_ids=relevant_belief_ids,
        )
        embeddings_by_case, embed_queries, resolved_model = _resolve_query_embedding_inputs(
            local_embedding_model=local_embedding_model,
            query_embeddings_json=query_embeddings_json,
            embedding_model=embedding_model,
        )
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
        if case_library is not None:
            report["case_library"] = case_library
        if record_cases:
            report["case_library"] = merge_recall_eval_case_library(name, cases, source_path=cases_path)
        report["operator_validation"] = build_recall_operator_validation(report)
    except (ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(str(exc))
    except FileNotFoundError as exc:
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
