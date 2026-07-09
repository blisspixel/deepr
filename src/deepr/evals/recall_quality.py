"""$0 recall-route quality eval over stored belief state.

Compares the lexical candidate router against indexed vector recall on
operator-labeled cases. Relevance labels come from supplied cases or a
single reviewed case (human or calibrated-model judgment); this module computes
only deterministic retrieval metrics against those labels. A route winning here
is routing evidence, never a semantic verdict about belief truth.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.config import runtime_data_path
from deepr.experts.paths import expert_slug
from deepr.utils.atomic_io import atomic_write_text

RECALL_EVAL_REPORT_SCHEMA_VERSION = "deepr-recall-eval-report-v1"
RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION = "deepr-recall-eval-case-library-v1"
LEXICAL_ROUTE = "lexical_router"
VECTOR_ROUTE = "vector_similarity"
_ROUTE_METRICS = ("hit_at_k", "mean_reciprocal_rank", "mean_relevant_retrieved")

# One batcher shape shared with deepr.backends.local.make_local_embedder.
QueryEmbedder = Callable[[list[str]], Awaitable[list[tuple[float, ...]]]]


@dataclass(frozen=True)
class RecallEvalCase:
    """One labeled retrieval case: a query and the belief ids that answer it."""

    case_id: str
    query: str
    relevant_belief_ids: tuple[str, ...]


def load_recall_eval_cases(payload: Any) -> list[RecallEvalCase]:
    """Validate an operator-supplied cases payload.

    Expected shape: a JSON array of objects with ``case_id``, ``query``, and a
    non-empty ``relevant_belief_ids`` array. Labels are trusted as supplied;
    Deepr does not second-guess relevance with lexical rules.
    """
    if not isinstance(payload, list) or not payload:
        raise ValueError("recall eval cases must be a non-empty JSON array")

    cases: list[RecallEvalCase] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            raise ValueError(f"case {index} must be a JSON object")
        case_id = str(raw.get("case_id", "") or "").strip()
        query = str(raw.get("query", "") or "").strip()
        raw_ids = raw.get("relevant_belief_ids")
        if not case_id:
            raise ValueError(f"case {index} is missing case_id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        if not query:
            raise ValueError(f"case {case_id} is missing query")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValueError(f"case {case_id} needs a non-empty relevant_belief_ids array")
        if any(not isinstance(belief_id, str) for belief_id in raw_ids):
            raise ValueError(f"case {case_id} relevant_belief_ids must all be strings")
        relevant = tuple(dict.fromkeys(belief_id.strip() for belief_id in raw_ids if belief_id.strip()))
        if not relevant:
            raise ValueError(f"case {case_id} needs at least one non-blank relevant belief id")
        seen_ids.add(case_id)
        cases.append(RecallEvalCase(case_id=case_id, query=query, relevant_belief_ids=relevant))
    return cases


def recall_eval_case_id(
    query: str,
    relevant_belief_ids: Sequence[str],
    *,
    prefix: str = "operator",
) -> str:
    """Return a stable id for one operator-labeled recall case."""
    cleaned_query = " ".join(str(query).split())
    cleaned_ids = sorted({str(belief_id).strip() for belief_id in relevant_belief_ids if str(belief_id).strip()})
    if not cleaned_query:
        raise ValueError("recall eval case query is required")
    if not cleaned_ids:
        raise ValueError("recall eval case needs at least one relevant belief id")
    normalized_prefix = "_".join(str(prefix).strip().lower().split()) or "operator"
    seed = json.dumps(
        {"query": cleaned_query, "relevant_belief_ids": cleaned_ids},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"{normalized_prefix}_{digest}"


def build_recall_eval_case(
    *,
    case_id: str | None,
    query: str,
    relevant_belief_ids: Sequence[str],
) -> RecallEvalCase:
    """Build and validate one operator-labeled recall eval case."""
    cleaned_query = " ".join(str(query).split())
    resolved_case_id = str(case_id or "").strip() or recall_eval_case_id(query, relevant_belief_ids)
    return load_recall_eval_cases(
        [
            {
                "case_id": resolved_case_id,
                "query": cleaned_query,
                "relevant_belief_ids": list(relevant_belief_ids),
            }
        ]
    )[0]


def _case_payload(case: RecallEvalCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "query": case.query,
        "relevant_belief_ids": list(case.relevant_belief_ids),
    }


def _case_library_meta(
    path: Path,
    case_count: int,
    *,
    added: int,
    updated: int,
    unchanged: int,
) -> dict[str, Any]:
    return {
        "schema_version": RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION,
        "path": str(path),
        "case_count": case_count,
        "added_count": added,
        "updated_count": updated,
        "unchanged_count": unchanged,
    }


def recall_eval_case_library_path(expert_name: str, *, output_dir: Path | None = None) -> Path:
    """Return the runtime-local labeled recall-case library path for an expert."""
    root = output_dir or runtime_data_path("benchmarks", "recall_cases")
    return root / f"{expert_slug(expert_name)}.json"


def load_recall_eval_case_library(expert_name: str, *, output_dir: Path | None = None) -> list[RecallEvalCase]:
    """Load accumulated labeled recall cases for one expert.

    The library is operator-supplied evaluation data. It is never graph memory,
    never a belief write, and never a semantic verdict. A raw JSON array is
    accepted for migration from an ad hoc cases file; versioned libraries are
    written by ``merge_recall_eval_case_library``.
    """
    path = recall_eval_case_library_path(expert_name, output_dir=output_dir)
    if not path.exists():
        raise FileNotFoundError(f"no recall case library found for {expert_name!r}; pass --cases first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        if payload.get("schema_version") != RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION:
            raise ValueError("recall case library has an unsupported schema_version")
        raw_cases = payload.get("cases")
    else:
        raw_cases = payload
    return load_recall_eval_cases(raw_cases)


def merge_recall_eval_case_library(
    expert_name: str,
    cases: Sequence[RecallEvalCase],
    *,
    output_dir: Path | None = None,
    source_path: Path | None = None,
) -> dict[str, Any]:
    """Merge labeled cases into the expert's local recall-case library.

    Existing case ids are updated only when the query or relevant ids changed.
    The result is deterministic by case id so repeated imports of the same data
    do not churn the file. This is evaluation data only; it does not mutate
    beliefs, graph state, or vector indexes.
    """
    if not cases:
        raise ValueError("cannot merge an empty recall case set")
    path = recall_eval_case_library_path(expert_name, output_dir=output_dir)
    existing_cases: list[RecallEvalCase] = []
    if path.exists():
        existing_cases = load_recall_eval_case_library(expert_name, output_dir=output_dir)

    by_id = {case.case_id: case for case in existing_cases}
    added = 0
    updated = 0
    unchanged = 0
    for case in cases:
        prior = by_id.get(case.case_id)
        if prior is None:
            added += 1
        elif prior != case:
            updated += 1
        else:
            unchanged += 1
        by_id[case.case_id] = case

    merged = [by_id[case_id] for case_id in sorted(by_id)]
    if path.exists() and added == 0 and updated == 0:
        return _case_library_meta(path, len(merged), added=added, updated=updated, unchanged=unchanged)

    payload = {
        "schema_version": RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION,
        "kind": "deepr.eval.recall_case_library",
        "expert": {"name": expert_name},
        "contract": {
            "cost_usd": 0.0,
            "writes_graph": False,
            "writes_beliefs": False,
            "writes_belief_vectors": False,
            "semantic_verdict": False,
            "relevance_labels": "operator_supplied",
        },
        "summary": {
            "case_count": len(merged),
            "added_count": added,
            "updated_count": updated,
            "unchanged_count": unchanged,
        },
        "source": {"path": str(source_path) if source_path else ""},
        "cases": [_case_payload(case) for case in merged],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    return _case_library_meta(path, len(merged), added=added, updated=updated, unchanged=unchanged)


def _case_metrics(candidate_ids: Sequence[str], relevant_ids: Sequence[str]) -> dict[str, Any]:
    relevant = set(relevant_ids)
    first_relevant_rank = next(
        (rank for rank, candidate_id in enumerate(candidate_ids, start=1) if candidate_id in relevant),
        None,
    )
    retrieved_relevant = sum(1 for candidate_id in candidate_ids if candidate_id in relevant)
    return {
        "candidate_ids": list(candidate_ids),
        "hit_at_k": first_relevant_rank is not None,
        "reciprocal_rank": 0.0 if first_relevant_rank is None else round(1.0 / first_relevant_rank, 6),
        "relevant_retrieved": retrieved_relevant,
        "relevant_total": len(relevant),
    }


def _route_summary(case_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not case_results:
        return {"case_count": 0}
    count = len(case_results)
    return {
        "case_count": count,
        "hit_at_k": round(sum(1 for case in case_results if case["hit_at_k"]) / count, 6),
        "mean_reciprocal_rank": round(sum(case["reciprocal_rank"] for case in case_results) / count, 6),
        "mean_relevant_retrieved": round(sum(case["relevant_retrieved"] for case in case_results) / count, 6),
    }


def _route_comparison(lexical: Mapping[str, Any], vector: Mapping[str, Any]) -> dict[str, str]:
    comparison: dict[str, str] = {}
    for metric in _ROUTE_METRICS:
        lexical_score = float(lexical.get(metric, 0.0))
        vector_score = float(vector.get(metric, 0.0))
        if vector_score > lexical_score:
            comparison[metric] = VECTOR_ROUTE
        elif lexical_score > vector_score:
            comparison[metric] = LEXICAL_ROUTE
        else:
            comparison[metric] = "tie"
    return comparison


async def _resolve_query_embeddings(
    cases: Sequence[RecallEvalCase],
    *,
    embedding_model: str | None,
    query_embeddings_by_case_id: Mapping[str, Sequence[float]] | None,
    embed_queries: QueryEmbedder | None,
) -> tuple[dict[str, tuple[float, ...]], str]:
    """Resolve per-case query vectors; returns them plus a skip reason when absent."""
    if query_embeddings_by_case_id is not None and embed_queries is not None:
        raise ValueError("supply either precomputed query embeddings or an embedder, not both")

    if query_embeddings_by_case_id is not None:
        if not embedding_model:
            raise ValueError("embedding_model is required for the vector route")
        resolved = {
            case_id: tuple(float(value) for value in vector) for case_id, vector in query_embeddings_by_case_id.items()
        }
        missing = [case.case_id for case in cases if case.case_id not in resolved]
        if missing:
            raise ValueError(f"query embeddings JSON is missing case id(s): {', '.join(missing[:5])}")
        return resolved, ""

    if embed_queries is None:
        return {}, "no query embeddings supplied; pass a local embedding model or precomputed vectors"
    if not embedding_model:
        raise ValueError("embedding_model is required for the vector route")
    vectors = await embed_queries([case.query for case in cases])
    if len(vectors) != len(cases):
        raise ValueError(f"embedder returned {len(vectors)} vector(s) for {len(cases)} case(s)")
    return {case.case_id: tuple(vector) for case, vector in zip(cases, vectors, strict=True)}, ""


def _index_coverage(belief_store: Any, embedding_model: str | None) -> dict[str, Any]:
    """Sanitized belief-vector index coverage for the requested model label.

    The local index path is deliberately omitted from the payload. An empty
    dict means no model label was requested or the store exposes no stats.
    """
    stats_fn = getattr(belief_store, "belief_embedding_stats", None)
    if not callable(stats_fn) or not embedding_model:
        return {}
    stats = dict(stats_fn(embedding_model=embedding_model))
    return {
        "embedding_model": embedding_model,
        "current_vector_count": int(stats.get("current_vector_count", 0) or 0),
        "missing_or_stale_count": int(stats.get("missing_or_stale_count", 0) or 0),
        "record_count": int(stats.get("record_count", 0) or 0),
    }


async def run_recall_quality_eval(
    belief_store: Any,
    cases: Sequence[RecallEvalCase],
    *,
    expert_name: str = "",
    top_k: int = 5,
    embedding_model: str | None = None,
    query_embeddings_by_case_id: Mapping[str, Sequence[float]] | None = None,
    embed_queries: QueryEmbedder | None = None,
) -> dict[str, Any]:
    """Run both recall routes over labeled cases and report retrieval metrics.

    The lexical route always runs. The vector route runs when query embeddings
    are available, either precomputed per case or computed in one batch through
    an injected local embedder; without either it is skipped with a recorded
    reason instead of silently reporting a hollow comparison.
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    resolved_embeddings, vector_route_skip_reason = await _resolve_query_embeddings(
        cases,
        embedding_model=embedding_model,
        query_embeddings_by_case_id=query_embeddings_by_case_id,
        embed_queries=embed_queries,
    )
    index_coverage = _index_coverage(belief_store, embedding_model if resolved_embeddings else None)
    if resolved_embeddings and index_coverage and index_coverage["current_vector_count"] == 0:
        # Without usable belief vectors under this model label, every vector
        # query would return nothing and the comparison would read as a
        # measured lexical win. Skip honestly instead.
        resolved_embeddings = {}
        vector_route_skip_reason = (
            f"no usable belief vectors indexed under model label {embedding_model!r}; "
            "run deepr expert refresh-semantic-recall first"
        )

    lexical_cases: list[dict[str, Any]] = []
    vector_cases: list[dict[str, Any]] = []
    case_payloads: list[dict[str, Any]] = []
    for case in cases:
        lexical_hits = belief_store.recall_belief_candidates(case.query, top_k=top_k)
        lexical_result = _case_metrics([hit.item_id for hit in lexical_hits], case.relevant_belief_ids)
        lexical_cases.append(lexical_result)
        case_payload: dict[str, Any] = {
            "case_id": case.case_id,
            "query": case.query,
            "relevant_belief_ids": list(case.relevant_belief_ids),
            "routes": {LEXICAL_ROUTE: lexical_result},
        }
        if case.case_id in resolved_embeddings:
            vector_hits = belief_store.recall_belief_candidates(
                case.query,
                top_k=top_k,
                query_embedding=resolved_embeddings[case.case_id],
                embedding_model=embedding_model,
                include_lexical_fallback=False,
            )
            vector_result = _case_metrics([hit.item_id for hit in vector_hits], case.relevant_belief_ids)
            vector_cases.append(vector_result)
            case_payload["routes"][VECTOR_ROUTE] = vector_result
        case_payloads.append(case_payload)

    lexical_summary = _route_summary(lexical_cases)
    vector_summary = _route_summary(vector_cases)
    routes: dict[str, Any] = {LEXICAL_ROUTE: lexical_summary}
    comparison: dict[str, Any] = {"vector_route_evaluated": bool(vector_cases)}
    if vector_cases:
        routes[VECTOR_ROUTE] = vector_summary
        comparison["winners_by_metric"] = _route_comparison(lexical_summary, vector_summary)
    else:
        comparison["skip_reason"] = vector_route_skip_reason

    return {
        "schema_version": RECALL_EVAL_REPORT_SCHEMA_VERSION,
        "kind": "deepr.eval.recall_quality",
        "expert": {"name": expert_name},
        "request": {
            "case_count": len(cases),
            "top_k": top_k,
            "embedding_model": embedding_model or "",
        },
        "contract": {
            "cost_usd": 0.0,
            "writes_graph": False,
            "writes_beliefs": False,
            "writes_belief_vectors": False,
            "semantic_verdict": False,
            "relevance_labels": "operator_supplied",
            "routing_evidence_only": True,
        },
        "index": index_coverage,
        "routes": routes,
        "comparison": comparison,
        "cases": case_payloads,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def write_recall_eval_report(report: Mapping[str, Any], *, output_dir: Path | None = None) -> Path:
    """Write a recall eval artifact under the configured benchmarks directory."""
    root = output_dir or runtime_data_path("benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"recall_eval_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


__all__ = [
    "LEXICAL_ROUTE",
    "RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION",
    "RECALL_EVAL_REPORT_SCHEMA_VERSION",
    "VECTOR_ROUTE",
    "RecallEvalCase",
    "build_recall_eval_case",
    "load_recall_eval_case_library",
    "load_recall_eval_cases",
    "merge_recall_eval_case_library",
    "recall_eval_case_id",
    "recall_eval_case_library_path",
    "run_recall_quality_eval",
    "write_recall_eval_report",
]
