"""Content-free cost-ledger records for local structured consult runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deepr.evals.consult_graph_contract import StructuredConsultContractError


def record_local_dispatch(
    brief: Mapping[str, Any],
    node: Mapping[str, Any],
    usage: Mapping[str, Any],
    run_id: str,
) -> None:
    """Durably record one content-free $0 marker before local work."""
    from deepr.observability.cost_ledger import CostLedger

    capacity = _mapping_value(brief, "capacity")
    provenance = _mapping_value(capacity, "model_provenance")
    node_id = str(node["node_id"])
    try:
        CostLedger().record_event(
            operation="structured_consult_local_dispatch",
            provider="ollama_local",
            model=str(capacity["model"]),
            cost_usd=0.0,
            task_id=run_id,
            session_id=str(brief["graph_id"]),
            source="eval.structured_consult.local_dispatch",
            metadata={
                "brief_hash": brief["brief_hash"],
                "run_id": run_id,
                "node_id": node_id,
                "node_kind": node["node_kind"],
                "capacity_kind": capacity["capacity_kind"],
                "model_digest": provenance["digest"],
                "cloud_disabled": provenance["cloud_disabled"],
                "max_cost_usd": 0.0,
                "transport_attempts_ceiling": 1,
                "usage_ambiguous_until_completion": True,
                "input_tokens_reserved": usage["input_tokens_reserved"],
                "output_tokens_reserved": usage["output_tokens_reserved"],
            },
            idempotency_key=f"structured-consult:{run_id}:{node_id}:dispatch",
            require_fsync=True,
        )
    except Exception as exc:
        raise StructuredConsultContractError(
            "COST_LEDGER_REQUIRED",
            f"local dispatch blocked because the cost ledger was not durable: {type(exc).__name__}",
        ) from exc


def record_local_run_terminal(run: Mapping[str, Any]) -> None:
    """Durably close one run with content-free accounting totals."""
    from deepr.observability.cost_ledger import CostLedger

    usage = _mapping_value(run, "usage")
    counts = _mapping_value(run, "node_counts")
    capacity = _mapping_value(run, "capacity")
    try:
        CostLedger().record_event(
            operation="structured_consult_local_run_terminal",
            provider="ollama_local",
            model=str(capacity["model"]),
            cost_usd=0.0,
            task_id=str(run["run_id"]),
            session_id=str(run["graph_id"]),
            source="eval.structured_consult.run_terminal",
            metadata={
                "run_id": run["run_id"],
                "brief_hash": run["brief_hash"],
                "status": run["status"],
                "stop_reason": run["stop_reason"],
                "expected_nodes": counts["expected"],
                "terminal_nodes": counts["terminal"],
                "transport_attempts": usage["transport_attempts"],
                "usage_ambiguous_nodes": usage["usage_ambiguous_nodes"],
                "max_cost_usd": 0.0,
            },
            idempotency_key=f"structured-consult:{run['run_id']}:terminal",
            require_fsync=True,
        )
    except Exception as exc:
        raise StructuredConsultContractError(
            "COST_LEDGER_REQUIRED",
            f"local run terminal record was not durable: {type(exc).__name__}",
        ) from exc


def _mapping_value(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    nested = value.get(field)
    if not isinstance(nested, Mapping):
        raise StructuredConsultContractError("INVALID_TYPE", f"{field} must be an object")
    return nested
