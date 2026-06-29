"""Expert semantic-recall command."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_header, print_key_value, print_section_header
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.beliefs import BeliefStore
from deepr.experts.expert_semantic_recall import build_expert_semantic_recall, parse_query_embedding_json
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
