"""Expert semantic-recall command."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_header, print_key_value, print_section_header
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.beliefs import BeliefStore
from deepr.experts.expert_semantic_recall import (
    build_expert_semantic_recall,
    build_expert_semantic_recall_refresh,
    parse_query_embedding_json,
)
from deepr.experts.profile import ExpertStore


def _render_summary(payload: dict[str, Any]) -> None:
    expert_info = payload["expert"]
    query = payload["query"]
    summary = payload["summary"]
    contract = payload["contract"]
    candidates = payload["candidates"]
    print_header(f"Semantic recall: {expert_info['name']}")
    print_key_value("Query", str(query["text"]))
    print_key_value("Candidates", str(summary["candidate_count"]))
    print_key_value("Verdict", str(contract["candidate_verdict"]))
    print_key_value("Cost", "$0.00")
    print_key_value("Embedding generation", str(contract["embedding_generation"]))

    if not candidates:
        console.print("[dim]No recall candidates matched the current filters.[/dim]")
        return

    print_section_header("Candidates")
    for candidate in candidates:
        console.print(
            f"  - {candidate['score']:.3f} "
            f"[{candidate['method']}] {candidate['text']} "
            f"[dim]({candidate['item_id']}, {candidate['verdict']})[/dim]"
        )


def _load_json_file(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc.msg}") from exc
    except OSError as exc:
        raise ValueError(f"could not read {path}: {exc}") from exc


def _render_refresh_summary(payload: dict[str, Any]) -> None:
    expert_info = payload["expert"]
    summary = payload["summary"]
    request = payload["request"]
    contract = payload["contract"]
    refresh = payload["refresh"]
    print_header(f"Semantic recall refresh: {expert_info['name']}")
    print_key_value("Status", str(summary["status"]))
    print_key_value("Embedding model", str(request["embedding_model"]))
    print_key_value("Requested", str(summary["requested_count"]))
    print_key_value("Indexed", str(summary["indexed_count"]))
    print_key_value("Skipped", str(summary["skipped_count"]))
    print_key_value("Deepr cost", "$0.00")
    print_key_value("Estimated external cost", f"${contract['estimated_external_cost_usd']:.6f}")
    print_key_value("Embedding generation", str(contract["embedding_generation"]))

    blocked_reason = str(refresh.get("blocked_reason") or "")
    if blocked_reason:
        print_key_value("Blocked", blocked_reason)
    errors = refresh.get("errors") or []
    if errors:
        print_section_header("Errors")
        for error in errors:
            console.print(f"  - {error}")


@expert.command(name="semantic-recall")
@click.argument("name")
@click.argument("query")
@click.option("--top-k", type=click.IntRange(min=1, max=50), default=5, show_default=True, help="Candidate limit.")
@click.option("--min-score", type=click.FloatRange(min=0.0, max=1.0), default=0.0, show_default=True)
@click.option("--domain", default=None, help="Optional exact belief-domain filter.")
@click.option(
    "--query-embedding",
    default=None,
    help="Explicit JSON numeric query embedding. The command never generates embeddings.",
)
@click.option("--embedding-model", default=None, help="Model label for already-indexed belief vectors.")
@click.option("--no-lexical-fallback", is_flag=True, help="Only return vector hits when using a query embedding.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_semantic_recall(
    name: str,
    query: str,
    top_k: int,
    min_score: float,
    domain: str | None,
    query_embedding: str | None,
    embedding_model: str | None,
    no_lexical_fallback: bool,
    json_output: bool,
) -> None:
    """Recall candidate beliefs for verifier routing.

    Read-only and cost-$0. The default lexical route is a candidate router, not
    a truth verdict. Indexed vector recall runs only when the caller supplies an
    already-gated query embedding and matching embedding model.
    """
    profile = ExpertStore().load(name)
    if profile is None:
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    parsed_embedding = None
    if query_embedding:
        try:
            parsed_embedding = parse_query_embedding_json(query_embedding)
        except ValueError as exc:
            print_error(str(exc))
            sys.exit(2)

    try:
        payload = build_expert_semantic_recall(
            profile,
            BeliefStore(profile.name),
            query,
            top_k=top_k,
            min_score=min_score,
            domain=domain,
            query_embedding=parsed_embedding,
            embedding_model=embedding_model,
            include_lexical_fallback=not no_lexical_fallback,
        )
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    _render_summary(payload)


@expert.command(name="refresh-semantic-recall")
@click.argument("name")
@click.option("--embedding-model", required=True, help="Model label for the precomputed belief vectors.")
@click.option(
    "--embeddings-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="JSON object mapping belief id to an already-gated numeric vector.",
)
@click.option("--max-beliefs", type=click.IntRange(min=0), default=None, help="Maximum missing/stale beliefs to index.")
@click.option(
    "--budget",
    type=click.FloatRange(min=0.0),
    default=0.0,
    show_default=True,
    help="Ceiling for the declared upstream embedding estimate.",
)
@click.option(
    "--estimated-cost-per-belief",
    type=click.FloatRange(min=0.0),
    default=0.0,
    show_default=True,
    help="Declared upstream estimate per vector; Deepr does not call the embedding provider.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_refresh_semantic_recall(
    name: str,
    embedding_model: str,
    embeddings_json: Path,
    max_beliefs: int | None,
    budget: float,
    estimated_cost_per_belief: float,
    json_output: bool,
) -> None:
    """Refresh semantic recall from precomputed belief vectors.

    This command indexes only caller-supplied embeddings. It never calls an
    embedding provider or upgrades a recall score into a truth verdict.
    """
    profile = ExpertStore().load(name)
    if profile is None:
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    try:
        embedding_payload = _load_json_file(embeddings_json)
        payload = asyncio.run(
            build_expert_semantic_recall_refresh(
                profile,
                BeliefStore(profile.name),
                embedding_payload,
                embedding_model=embedding_model,
                budget_usd=budget,
                estimated_cost_per_belief=estimated_cost_per_belief,
                max_beliefs=max_beliefs,
            )
        )
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    _render_refresh_summary(payload)
