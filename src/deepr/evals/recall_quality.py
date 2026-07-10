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
from deepr.evals.retrieval_metrics import (
    BOOTSTRAP_CONFIDENCE_LEVEL as RECALL_PREFERENCE_CONFIDENCE_LEVEL,
)
from deepr.evals.retrieval_metrics import BOOTSTRAP_METHOD as RECALL_PREFERENCE_BOOTSTRAP_METHOD
from deepr.evals.retrieval_metrics import BOOTSTRAP_RESAMPLES as RECALL_PREFERENCE_BOOTSTRAP_RESAMPLES
from deepr.evals.retrieval_metrics import BOOTSTRAP_RNG as RECALL_PREFERENCE_BOOTSTRAP_RNG
from deepr.evals.retrieval_metrics import compare_retrieval_routes
from deepr.evals.retrieval_metrics import paired_vector_bootstrap_comparison as _paired_bootstrap_comparison
from deepr.evals.retrieval_metrics import ranked_binary_retrieval_metrics as _case_metrics
from deepr.evals.retrieval_metrics import summarize_retrieval_route as _route_summary
from deepr.experts.paths import expert_slug
from deepr.experts.recall_preference import belief_index_coverage as recall_index_coverage
from deepr.experts.recall_preference import recall_retrieval_contract
from deepr.experts.recall_preference import validate_belief_index_coverage as _validated_index_coverage
from deepr.utils.atomic_io import atomic_write_text

RECALL_EVAL_REPORT_SCHEMA_VERSION = "deepr-recall-eval-report-v2"
RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION = "deepr-recall-eval-case-library-v1"
RECALL_OPERATOR_VALIDATION_SCHEMA_VERSION = "deepr-recall-operator-validation-v1"
RECALL_OPERATOR_VALIDATION_KIND = "deepr.eval.recall_operator_validation"
RECALL_LIBRARY_INVENTORY_SCHEMA_VERSION = "deepr-recall-library-inventory-v1"
RECALL_LIBRARY_INVENTORY_KIND = "deepr.eval.recall_library_inventory"
RECALL_LIBRARY_VALIDATION_PLAN_SCHEMA_VERSION = "deepr-recall-library-validation-plan-v1"
RECALL_LIBRARY_VALIDATION_PLAN_KIND = "deepr.eval.recall_library_validation_plan"
LEXICAL_ROUTE = "lexical_router"
VECTOR_ROUTE = "vector_similarity"
MIN_SCHEDULER_PREFERENCE_CASES = 30
SCHEDULER_REQUIRED_VECTOR_WIN_METRICS = (
    "hit_at_k",
    "mean_reciprocal_rank",
    "mean_recall_at_k",
    "mean_ndcg_at_k",
)

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


def recall_eval_case_library_dir(*, output_dir: Path | None = None) -> Path:
    """Return the runtime-local directory containing labeled recall libraries."""
    return output_dir or runtime_data_path("benchmarks", "recall_cases")


def recall_eval_case_library_path(expert_name: str, *, output_dir: Path | None = None) -> Path:
    """Return the runtime-local labeled recall-case library path for an expert."""
    return recall_eval_case_library_dir(output_dir=output_dir) / f"{expert_slug(expert_name)}.json"


def _load_recall_eval_case_library_payload(path: Path) -> tuple[list[RecallEvalCase], Mapping[str, Any] | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        if payload.get("schema_version") != RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION:
            raise ValueError("recall case library has an unsupported schema_version")
        raw_cases = payload.get("cases")
        return load_recall_eval_cases(raw_cases), payload
    return load_recall_eval_cases(payload), None


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
    cases, _ = _load_recall_eval_case_library_payload(path)
    return cases


def _library_record(path: Path) -> dict[str, Any]:
    try:
        cases, payload = _load_recall_eval_case_library_payload(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "path": str(path),
            "status": "invalid",
            "expert": {"name": path.stem},
            "case_count": 0,
            "ready_for_recall_eval": False,
            "ready_for_scheduler_preference_eval": False,
            "blockers": ["invalid_case_library"],
            "error": str(exc),
        }

    expert = payload.get("expert", {}) if isinstance(payload, Mapping) else {}
    expert_name = str(expert.get("name", "") or path.stem) if isinstance(expert, Mapping) else path.stem
    case_count = len(cases)
    blockers = []
    if case_count < MIN_SCHEDULER_PREFERENCE_CASES:
        blockers.append("insufficient_case_count_for_scheduler_preference")
    return {
        "path": str(path),
        "status": "valid",
        "schema_version": RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION if payload is not None else "",
        "expert": {"name": expert_name},
        "case_count": case_count,
        "ready_for_recall_eval": case_count > 0,
        "ready_for_scheduler_preference_eval": case_count >= MIN_SCHEDULER_PREFERENCE_CASES,
        "blockers": blockers,
        "updated_at": str(payload.get("updated_at", "") or "") if isinstance(payload, Mapping) else "",
    }


def build_recall_library_inventory(*, output_dir: Path | None = None) -> dict[str, Any]:
    """Inventory accumulated recall-case libraries without running retrieval.

    This is the cheap first step for live/operator validation: it shows which
    real accumulated libraries have enough labeled cases to run route evidence,
    but it never runs an embedder, changes routing, writes graph state, or
    infers semantic relevance.
    """
    root = recall_eval_case_library_dir(output_dir=output_dir)
    records = [_library_record(path) for path in sorted(root.glob("*.json"))] if root.exists() else []
    valid = [record for record in records if record["status"] == "valid"]
    ready = [record for record in records if record["ready_for_scheduler_preference_eval"]]
    return {
        "schema_version": RECALL_LIBRARY_INVENTORY_SCHEMA_VERSION,
        "kind": RECALL_LIBRARY_INVENTORY_KIND,
        "root": str(root),
        "contract": {
            "cost_usd": 0.0,
            "writes_graph": False,
            "writes_beliefs": False,
            "writes_belief_vectors": False,
            "runs_retrieval": False,
            "semantic_verdict": False,
            "routing_evidence_only": True,
        },
        "summary": {
            "library_count": len(records),
            "valid_library_count": len(valid),
            "invalid_library_count": len(records) - len(valid),
            "case_count": sum(int(record["case_count"]) for record in valid),
            "ready_for_scheduler_preference_eval_count": len(ready),
            "required_case_count": MIN_SCHEDULER_PREFERENCE_CASES,
        },
        "libraries": records,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _validation_plan_step(
    library: Mapping[str, Any],
    *,
    top_k: int,
    local_embedding_model: str | None,
) -> dict[str, Any]:
    expert = library.get("expert", {})
    expert_name = str(expert.get("name", "") or "") if isinstance(expert, Mapping) else ""
    blockers = [str(blocker) for blocker in library.get("blockers", []) if str(blocker).strip()]
    if library.get("ready_for_scheduler_preference_eval") is not True:
        if "insufficient_case_count_for_scheduler_preference" not in blockers:
            blockers.append("insufficient_case_count_for_scheduler_preference")
    if not local_embedding_model:
        blockers.append("missing_local_embedding_model_for_vector_route")

    ready = library.get("status") == "valid" and not blockers
    command = ["deepr", "eval", "recall", expert_name, "--top-k", str(top_k), "--save"]
    if local_embedding_model:
        command.extend(["--local-embedding-model", local_embedding_model])
    return {
        "expert": {"name": expert_name},
        "library_path": str(library.get("path", "") or ""),
        "case_count": int(library.get("case_count", 0) or 0),
        "status": "ready" if ready else "blocked",
        "ready_for_operator_validation": ready,
        "blockers": sorted(set(blockers)),
        "eval_command_argv": command if ready else [],
        "expected_report_schema_version": RECALL_EVAL_REPORT_SCHEMA_VERSION,
        "expected_operator_validation_schema_version": RECALL_OPERATOR_VALIDATION_SCHEMA_VERSION,
        "post_eval_acceptance": {
            "requires_saved_report": True,
            "requires_operator_validation_ready": True,
            "sync_requires_explicit_report": True,
            "default_routing_change_allowed": False,
            "routing_evidence_only": True,
            "semantic_verdict": False,
        },
    }


def build_recall_library_validation_plan(
    *,
    output_dir: Path | None = None,
    top_k: int = 5,
    local_embedding_model: str | None = None,
) -> dict[str, Any]:
    """Build a read-only plan for validating accumulated recall libraries.

    The plan emits command argv for ready libraries only. It does not call an
    embedder, run retrieval, save reports, or change scheduler behavior.
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    model = str(local_embedding_model or "").strip()
    inventory = build_recall_library_inventory(output_dir=output_dir)
    steps = [
        _validation_plan_step(library, top_k=top_k, local_embedding_model=model or None)
        for library in inventory["libraries"]
    ]
    ready_steps = [step for step in steps if step["ready_for_operator_validation"]]
    return {
        "schema_version": RECALL_LIBRARY_VALIDATION_PLAN_SCHEMA_VERSION,
        "kind": RECALL_LIBRARY_VALIDATION_PLAN_KIND,
        "inventory": {
            "schema_version": inventory["schema_version"],
            "root": inventory["root"],
            "generated_at": inventory["generated_at"],
        },
        "request": {
            "top_k": top_k,
            "local_embedding_model": model,
        },
        "contract": {
            "cost_usd": 0.0,
            "writes_graph": False,
            "writes_beliefs": False,
            "writes_belief_vectors": False,
            "runs_retrieval": False,
            "executes_commands": False,
            "semantic_verdict": False,
            "routing_evidence_only": True,
            "default_routing_change_allowed": False,
        },
        "summary": {
            "library_count": inventory["summary"]["library_count"],
            "valid_library_count": inventory["summary"]["valid_library_count"],
            "invalid_library_count": inventory["summary"]["invalid_library_count"],
            "case_count": inventory["summary"]["case_count"],
            "ready_for_scheduler_preference_eval_count": inventory["summary"][
                "ready_for_scheduler_preference_eval_count"
            ],
            "ready_for_operator_validation_count": len(ready_steps),
            "blocked_count": len(steps) - len(ready_steps),
            "required_case_count": MIN_SCHEDULER_PREFERENCE_CASES,
        },
        "steps": steps,
        "generated_at": datetime.now(UTC).isoformat(),
    }


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


def _case_library_source(report: Mapping[str, Any]) -> str:
    case_library = report.get("case_library", {})
    if isinstance(case_library, Mapping):
        source = str(case_library.get("source", "") or "").strip()
        if source:
            return source
        if case_library.get("path"):
            return "recorded_case_merge"
    if report.get("cases"):
        return "ad_hoc_cases"
    return "unknown"


def build_recall_operator_validation(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the operator-facing validation state for a recall eval report.

    This block is deliberately conservative: it can mark an accumulated-library
    report ready for explicit sync preference, but it never authorizes a default
    scheduler change. The scheduler still requires an operator-supplied saved
    report at the sync boundary.
    """
    request = report.get("request", {})
    preference = report.get("scheduler_preference", {})
    case_library = report.get("case_library", {})
    embedding_model = str(request.get("embedding_model", "") or "").strip() if isinstance(request, Mapping) else ""
    case_count = int(request.get("case_count", 0) or 0) if isinstance(request, Mapping) else 0
    source = _case_library_source(report)
    accumulated_library = source == "accumulated_library"
    preference_eligible = isinstance(preference, Mapping) and preference.get("eligible") is True
    blockers: list[str] = []

    if not accumulated_library:
        blockers.append("not_accumulated_library_run")
    if not embedding_model:
        blockers.append("missing_embedding_model")
    if not preference_eligible:
        reasons = preference.get("reasons", []) if isinstance(preference, Mapping) else []
        if isinstance(reasons, list):
            blockers.extend(str(reason) for reason in reasons if str(reason).strip())
        else:
            blockers.append("scheduler_preference_not_eligible")

    eligible_for_explicit_sync = accumulated_library and bool(embedding_model) and preference_eligible
    library_payload: dict[str, Any] = {}
    if isinstance(case_library, Mapping):
        library_payload = {
            "path": str(case_library.get("path", "") or ""),
            "case_count": int(case_library.get("case_count", case_count) or 0),
            "source": source,
        }

    return {
        "schema_version": RECALL_OPERATOR_VALIDATION_SCHEMA_VERSION,
        "kind": RECALL_OPERATOR_VALIDATION_KIND,
        "case_source": source,
        "case_library": library_payload,
        "case_count": case_count,
        "embedding_model": embedding_model,
        "scheduler_preference_eligible": preference_eligible,
        "eligible_for_explicit_sync_preference": eligible_for_explicit_sync,
        "sync_requires_explicit_report": True,
        "default_routing_change_allowed": False,
        "routing_evidence_only": True,
        "semantic_verdict": False,
        "blockers": sorted(set(blockers)),
    }


def _route_comparison(lexical: Mapping[str, Any], vector: Mapping[str, Any]) -> dict[str, str]:
    return compare_retrieval_routes(
        lexical,
        vector,
        baseline_label=LEXICAL_ROUTE,
        candidate_label=VECTOR_ROUTE,
    )


def _scheduler_preference(
    routes: Mapping[str, Any],
    comparison: Mapping[str, Any],
    index_coverage: Mapping[str, Any],
    retrieval_contract: Mapping[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    vector_summary = routes.get(VECTOR_ROUTE, {})
    winners = comparison.get("winners_by_metric", {})
    bootstrap = comparison.get("paired_bootstrap", {})
    evaluated_case_count = int(vector_summary.get("case_count", 0) or 0) if isinstance(vector_summary, Mapping) else 0

    if comparison.get("vector_route_evaluated") is not True:
        reasons.append("vector_route_not_evaluated")
    if evaluated_case_count < MIN_SCHEDULER_PREFERENCE_CASES:
        reasons.append("insufficient_case_count")
    if (
        not index_coverage
        or int(index_coverage.get("current_vector_count", 0) or 0) <= 0
        or int(index_coverage.get("missing_or_stale_count", 0) or 0) > 0
        or not str(index_coverage.get("state_digest", "") or "")
    ):
        reasons.append("belief_vector_index_incomplete")
    if not isinstance(winners, Mapping) or any(
        winners.get(metric) != VECTOR_ROUTE for metric in SCHEDULER_REQUIRED_VECTOR_WIN_METRICS
    ):
        reasons.append("vector_route_did_not_win_required_metrics")

    bootstrap_metrics = bootstrap.get("metrics", {}) if isinstance(bootstrap, Mapping) else {}
    confidence_supported_metrics = [
        metric
        for metric in SCHEDULER_REQUIRED_VECTOR_WIN_METRICS
        if isinstance(bootstrap_metrics, Mapping)
        and isinstance(bootstrap_metrics.get(metric), Mapping)
        and bootstrap_metrics[metric].get("vector_superiority_supported") is True
    ]
    bootstrap_contract_valid = (
        isinstance(bootstrap, Mapping)
        and bootstrap.get("method") == RECALL_PREFERENCE_BOOTSTRAP_METHOD
        and bootstrap.get("rng") == RECALL_PREFERENCE_BOOTSTRAP_RNG
        and bootstrap.get("case_count") == evaluated_case_count
        and bootstrap.get("resamples") == RECALL_PREFERENCE_BOOTSTRAP_RESAMPLES
        and bootstrap.get("confidence_level") == RECALL_PREFERENCE_CONFIDENCE_LEVEL
    )
    if not bootstrap_contract_valid or len(confidence_supported_metrics) != len(SCHEDULER_REQUIRED_VECTOR_WIN_METRICS):
        reasons.append("vector_route_superiority_not_confident")

    eligible = not reasons
    return {
        "eligible": eligible,
        "preferred_route": VECTOR_ROUTE if eligible else "",
        "fallback_route": LEXICAL_ROUTE,
        "required_case_count": MIN_SCHEDULER_PREFERENCE_CASES,
        "evaluated_case_count": evaluated_case_count,
        "required_win_metrics": list(SCHEDULER_REQUIRED_VECTOR_WIN_METRICS),
        "winners_by_metric": dict(winners) if isinstance(winners, Mapping) else {},
        "minimum_confidence_level": RECALL_PREFERENCE_CONFIDENCE_LEVEL,
        "minimum_bootstrap_resamples": RECALL_PREFERENCE_BOOTSTRAP_RESAMPLES,
        "confidence_supported_metrics": confidence_supported_metrics,
        "embedding_model": str(index_coverage.get("embedding_model", "") or ""),
        "index_state_digest": str(index_coverage.get("state_digest", "") or ""),
        "retrieval_contract": dict(retrieval_contract),
        "reasons": sorted(set(reasons)),
        "routing_evidence_only": True,
        "semantic_verdict": False,
    }


def _recomputed_case_routes(raw_case: Mapping[str, Any], *, top_k: int) -> tuple[dict[str, Any], dict[str, Any]]:
    relevant_ids = raw_case.get("relevant_belief_ids")
    routes = raw_case.get("routes")
    if (
        not isinstance(relevant_ids, list)
        or not relevant_ids
        or not all(isinstance(item, str) for item in relevant_ids)
    ):
        raise ValueError("recall eval report case has invalid relevance labels")
    if not isinstance(routes, Mapping):
        raise ValueError("recall eval report case is missing route results")

    recomputed: dict[str, dict[str, Any]] = {}
    for route in (LEXICAL_ROUTE, VECTOR_ROUTE):
        result = routes.get(route)
        if not isinstance(result, Mapping):
            raise ValueError(f"recall eval report case is missing {route} results")
        candidate_ids = result.get("candidate_ids")
        if not isinstance(candidate_ids, list) or not all(isinstance(item, str) for item in candidate_ids):
            raise ValueError(f"recall eval report case has invalid {route} candidate ids")
        expected = _case_metrics(candidate_ids, relevant_ids, top_k=top_k)
        if dict(result) != expected:
            raise ValueError(f"recall eval report case has inconsistent {route} metrics")
        recomputed[route] = expected
    return recomputed[LEXICAL_ROUTE], recomputed[VECTOR_ROUTE]


def _validated_report_retrieval_contract(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the report's measured retrieval parameters."""
    top_k = request.get("top_k")
    domain = request.get("domain")
    min_score = request.get("min_score")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("recall eval report has invalid top_k")
    if not isinstance(domain, str):
        raise ValueError("recall eval report has invalid domain")
    if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
        raise ValueError("recall eval report has invalid min_score")
    try:
        retrieval_contract = recall_retrieval_contract(top_k=top_k, domain=domain, min_score=float(min_score))
    except (TypeError, ValueError) as exc:
        raise ValueError("recall eval report has invalid retrieval parameters") from exc
    return retrieval_contract


def _validated_preference_report_cases(
    report: Mapping[str, Any],
) -> tuple[int, str, float, str, list[Mapping[str, Any]]]:
    if report.get("schema_version") != RECALL_EVAL_REPORT_SCHEMA_VERSION:
        raise ValueError(f"recall eval report must use {RECALL_EVAL_REPORT_SCHEMA_VERSION}")
    if report.get("kind") != "deepr.eval.recall_quality":
        raise ValueError("recall eval report has an invalid kind")
    request = report.get("request")
    raw_cases = report.get("cases")
    if not isinstance(request, Mapping) or not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("recall eval report is missing request or case evidence")
    retrieval_contract = _validated_report_retrieval_contract(request)
    case_count = request.get("case_count")
    embedding_model = request.get("embedding_model")
    if isinstance(case_count, bool) or not isinstance(case_count, int) or case_count != len(raw_cases):
        raise ValueError("recall eval report case count is inconsistent")
    if not isinstance(embedding_model, str) or not embedding_model.strip():
        raise ValueError("recall eval report has an invalid embedding model")
    case_objects: list[Mapping[str, Any]] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise ValueError("recall eval report cases must be objects")
        case_objects.append(raw_case)
    load_recall_eval_cases(
        [
            {
                "case_id": raw_case.get("case_id"),
                "query": raw_case.get("query"),
                "relevant_belief_ids": raw_case.get("relevant_belief_ids"),
            }
            for raw_case in case_objects
        ]
    )
    return (
        retrieval_contract["top_k"],
        retrieval_contract["domain"],
        retrieval_contract["min_score"],
        embedding_model,
        case_objects,
    )


def validate_recall_preference_evidence(report: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute and validate an eligible v2 scheduler-preference report."""
    top_k, domain, min_score, embedding_model, raw_cases = _validated_preference_report_cases(report)

    lexical_cases: list[dict[str, Any]] = []
    vector_cases: list[dict[str, Any]] = []
    for raw_case in raw_cases:
        lexical_case, vector_case = _recomputed_case_routes(raw_case, top_k=top_k)
        lexical_cases.append(lexical_case)
        vector_cases.append(vector_case)

    expected_routes = {
        LEXICAL_ROUTE: _route_summary(lexical_cases),
        VECTOR_ROUTE: _route_summary(vector_cases),
    }
    expected_comparison = {
        "vector_route_evaluated": True,
        "winners_by_metric": _route_comparison(expected_routes[LEXICAL_ROUTE], expected_routes[VECTOR_ROUTE]),
        "paired_bootstrap": _paired_bootstrap_comparison(lexical_cases, vector_cases),
    }
    index = _validated_index_coverage(report.get("index"), embedding_model=embedding_model)
    expected_preference = _scheduler_preference(
        expected_routes,
        expected_comparison,
        index,
        recall_retrieval_contract(top_k=top_k, domain=domain, min_score=min_score),
    )

    if report.get("routes") != expected_routes:
        raise ValueError("recall eval report route summaries are inconsistent")
    if report.get("comparison") != expected_comparison:
        raise ValueError("recall eval report paired comparison is inconsistent")
    if report.get("scheduler_preference") != expected_preference:
        raise ValueError("recall eval report scheduler preference is inconsistent")
    if expected_preference["eligible"] is not True:
        raise ValueError("recall eval report does not contain eligible vector preference evidence")
    return expected_preference


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


async def run_recall_quality_eval(
    belief_store: Any,
    cases: Sequence[RecallEvalCase],
    *,
    expert_name: str = "",
    top_k: int = 5,
    domain: str | None = None,
    min_score: float = 0.0,
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
    retrieval_contract = recall_retrieval_contract(top_k=top_k, domain=domain, min_score=min_score)
    retrieval_domain = retrieval_contract["domain"] or None
    resolved_embeddings, vector_route_skip_reason = await _resolve_query_embeddings(
        cases,
        embedding_model=embedding_model,
        query_embeddings_by_case_id=query_embeddings_by_case_id,
        embed_queries=embed_queries,
    )
    index_coverage = recall_index_coverage(belief_store, embedding_model if resolved_embeddings else None)
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
        lexical_hits = belief_store.recall_belief_candidates(
            case.query,
            top_k=top_k,
            min_score=min_score,
            domain=retrieval_domain,
        )
        lexical_result = _case_metrics(
            [hit.item_id for hit in lexical_hits],
            case.relevant_belief_ids,
            top_k=top_k,
        )
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
                min_score=min_score,
                domain=retrieval_domain,
                query_embedding=resolved_embeddings[case.case_id],
                embedding_model=embedding_model,
                include_lexical_fallback=False,
            )
            vector_result = _case_metrics(
                [hit.item_id for hit in vector_hits],
                case.relevant_belief_ids,
                top_k=top_k,
            )
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
        comparison["paired_bootstrap"] = _paired_bootstrap_comparison(lexical_cases, vector_cases)
    else:
        comparison["skip_reason"] = vector_route_skip_reason
    scheduler_preference = _scheduler_preference(routes, comparison, index_coverage, retrieval_contract)

    return {
        "schema_version": RECALL_EVAL_REPORT_SCHEMA_VERSION,
        "kind": "deepr.eval.recall_quality",
        "expert": {"name": expert_name},
        "request": {
            "case_count": len(cases),
            "top_k": top_k,
            "domain": retrieval_contract["domain"],
            "min_score": retrieval_contract["min_score"],
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
        "scheduler_preference": scheduler_preference,
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
    "MIN_SCHEDULER_PREFERENCE_CASES",
    "RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION",
    "RECALL_EVAL_REPORT_SCHEMA_VERSION",
    "RECALL_LIBRARY_INVENTORY_KIND",
    "RECALL_LIBRARY_INVENTORY_SCHEMA_VERSION",
    "RECALL_LIBRARY_VALIDATION_PLAN_KIND",
    "RECALL_LIBRARY_VALIDATION_PLAN_SCHEMA_VERSION",
    "RECALL_OPERATOR_VALIDATION_KIND",
    "RECALL_OPERATOR_VALIDATION_SCHEMA_VERSION",
    "SCHEDULER_REQUIRED_VECTOR_WIN_METRICS",
    "VECTOR_ROUTE",
    "RecallEvalCase",
    "build_recall_eval_case",
    "build_recall_library_inventory",
    "build_recall_library_validation_plan",
    "build_recall_operator_validation",
    "load_recall_eval_case_library",
    "load_recall_eval_cases",
    "merge_recall_eval_case_library",
    "recall_eval_case_id",
    "recall_eval_case_library_dir",
    "recall_eval_case_library_path",
    "run_recall_quality_eval",
    "write_recall_eval_report",
]
