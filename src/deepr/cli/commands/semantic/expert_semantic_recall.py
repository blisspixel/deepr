"""Expert semantic-recall command."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from deepr.backends.local import make_local_embedder
from deepr.cli.colors import console, print_error, print_header, print_key_value, print_section_header
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.beliefs import BeliefStore
from deepr.experts.expert_semantic_recall import (
    build_expert_semantic_recall,
    build_expert_semantic_recall_refresh,
    build_expert_semantic_recall_refresh_local,
    parse_query_embedding_json,
)
from deepr.experts.profile import ExpertStore

# Contract label for a query vector computed on local owned hardware. The
# recall itself still never generates embeddings; only the query side does,
# and only when the operator asks for it explicitly.
_LOCAL_QUERY_GENERATION = "local_ollama_query"


def _embed_query_locally(local_embedding_model: str, query: str) -> tuple[float, ...]:
    """Compute one query embedding through the local $0 Ollama endpoint.

    Raises ``ValueError`` with an operator-facing message on any failure;
    there is no metered fallback on this path.
    """
    embedder = make_local_embedder(local_embedding_model)
    try:
        vectors = asyncio.run(embedder([query]))
    except Exception as exc:
        raise ValueError(_local_embedding_failure(local_embedding_model, exc)) from exc
    return vectors[0]


def _local_embedding_failure(local_embedding_model: str, exc: Exception) -> str:
    return (
        f"local embedding failed for model {local_embedding_model!r}: {exc}. "
        "Check that Ollama is running and the embedding model is pulled; "
        "Deepr never falls back to a metered embedding provider."
    )


def _validated_local_model_flag(local_embedding_model: str | None) -> str | None:
    """Normalize --local-embedding-model; a provided-but-blank value is an error."""
    if local_embedding_model is None:
        return None
    stripped = local_embedding_model.strip()
    if not stripped:
        print_error("--local-embedding-model must not be blank")
        sys.exit(2)
    return stripped


async def _refresh_semantic_recall_locally(
    profile: Any,
    local_embedding_model: str,
    *,
    max_beliefs: int | None,
) -> dict[str, Any]:
    """Refresh the belief-vector index through the local $0 embedder."""
    embedder = make_local_embedder(local_embedding_model)

    async def embed_claims(claims: list[str]) -> list[tuple[float, ...]]:
        try:
            return await embedder(claims)
        except Exception as exc:
            raise ValueError(_local_embedding_failure(local_embedding_model, exc)) from exc

    return await build_expert_semantic_recall_refresh_local(
        profile,
        BeliefStore(profile.name),
        embed_claims,
        embedding_model=local_embedding_model,
        max_beliefs=max_beliefs,
    )


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
@click.option(
    "--local-embedding-model",
    default=None,
    help="Compute the query embedding through a local Ollama model at $0; no metered fallback.",
)
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
    local_embedding_model: str | None,
    no_lexical_fallback: bool,
    json_output: bool,
) -> None:
    """Recall candidate beliefs for verifier routing.

    Read-only and cost-$0. The default lexical route is a candidate router, not
    a truth verdict. Indexed vector recall runs when the caller supplies an
    already-gated query embedding, or asks for a local $0 query embedding with
    --local-embedding-model.
    """
    local_embedding_model = _validated_local_model_flag(local_embedding_model)
    if local_embedding_model and (query_embedding or embedding_model):
        print_error("--local-embedding-model cannot be combined with --query-embedding or --embedding-model")
        sys.exit(2)
    if local_embedding_model and not query.strip():
        print_error("query must not be empty")
        sys.exit(2)

    profile = ExpertStore().load(name)
    if profile is None:
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    embedding_generation = "not_performed"
    parsed_embedding = None
    try:
        if query_embedding:
            parsed_embedding = parse_query_embedding_json(query_embedding)
        elif local_embedding_model:
            parsed_embedding = _embed_query_locally(local_embedding_model, query)
            embedding_model = local_embedding_model
            embedding_generation = _LOCAL_QUERY_GENERATION
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
            embedding_generation=embedding_generation,
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
@click.option("--embedding-model", default=None, help="Model label for the precomputed belief vectors.")
@click.option(
    "--embeddings-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="JSON object mapping belief id to an already-gated numeric vector.",
)
@click.option(
    "--local-embedding-model",
    default=None,
    help="Embed missing/stale belief claims through a local Ollama model at $0; no metered fallback.",
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
    help="Declared upstream estimate per vector; Deepr does not call a metered embedding provider.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_refresh_semantic_recall(
    name: str,
    embedding_model: str | None,
    embeddings_json: Path | None,
    local_embedding_model: str | None,
    max_beliefs: int | None,
    budget: float,
    estimated_cost_per_belief: float,
    json_output: bool,
) -> None:
    """Refresh semantic recall from precomputed belief vectors or a local model.

    With --embeddings-json this command indexes only caller-supplied precomputed
    belief vectors. With --local-embedding-model it computes the vectors through
    a local Ollama embedding model at $0. Neither path calls a metered embedding
    provider or upgrades a recall score into a truth verdict.
    """
    local_embedding_model = _validated_local_model_flag(local_embedding_model)
    if (embeddings_json is None) == (local_embedding_model is None):
        print_error("exactly one embedding source is required: --embeddings-json or --local-embedding-model")
        sys.exit(2)
    if embeddings_json is not None and not embedding_model:
        print_error("--embedding-model is required with --embeddings-json")
        sys.exit(2)
    if local_embedding_model and embedding_model:
        print_error("--embedding-model applies only to --embeddings-json; the local model is its own label")
        sys.exit(2)
    if local_embedding_model and estimated_cost_per_belief > 0.0:
        print_error("--estimated-cost-per-belief applies only to --embeddings-json; local embedding runs at $0")
        sys.exit(2)
    if local_embedding_model and budget > 0.0:
        print_error("--budget applies only to --embeddings-json; local embedding runs at $0 with no spend gate")
        sys.exit(2)

    profile = ExpertStore().load(name)
    if profile is None:
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    try:
        if embeddings_json is not None:
            embedding_payload = _load_json_file(embeddings_json)
            payload = asyncio.run(
                build_expert_semantic_recall_refresh(
                    profile,
                    BeliefStore(profile.name),
                    embedding_payload,
                    embedding_model=embedding_model or "",
                    budget_usd=budget,
                    estimated_cost_per_belief=estimated_cost_per_belief,
                    max_beliefs=max_beliefs,
                )
            )
        else:
            payload = asyncio.run(
                _refresh_semantic_recall_locally(
                    profile,
                    local_embedding_model or "",
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
