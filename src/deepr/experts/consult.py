"""Shared expert-consultation core (used by the CLI verb and the MCP tool).

One bounded "knowledge transaction" (docs/design/agentic-harness-boundary.md):
route a question to the relevant experts (or an explicit set), run the bounded
council, and shape the result into the versioned ``deepr-consult-v1`` artifact.
Both ``deepr expert consult`` and the ``deepr_consult_experts`` MCP tool import
this, so the two surfaces share one contract and one code path - and the MCP
server never has to depend on the CLI layer.
"""

from __future__ import annotations

from typing import Any

CONSULT_SCHEMA_VERSION = "deepr-consult-v1"
CONSULT_KIND = "deepr.expert.consult"
MAX_CONSULT_EXPERTS = 5


def build_consult_payload(question: str, result: dict[str, Any]) -> dict[str, Any]:
    """Shape a council result into the versioned consult artifact.

    The contract a harness consumes: the synthesized answer, each contributing
    expert's calibrated perspective, the points of agreement/dissent, and the
    cost. Single-shot and safe to render or machine-parse.
    """
    perspectives = result.get("perspectives", []) or []
    cost = round(float(result.get("total_cost", 0.0) or 0.0), 4)
    return {
        "schema_version": CONSULT_SCHEMA_VERSION,
        "kind": CONSULT_KIND,
        "contract": {"stability": "experimental", "cost_usd": cost},
        "question": question,
        "answer": result.get("synthesis", "") or "",
        "experts_consulted": [p.get("expert_name", "") for p in perspectives],
        "perspectives": [
            {
                "expert": p.get("expert_name", ""),
                "domain": p.get("domain", "") or "",
                "confidence": round(float(p.get("confidence", 0.0) or 0.0), 3),
                "response": p.get("response", "") or "",
            }
            for p in perspectives
        ],
        "agreements": list(result.get("agreements", []) or []),
        "disagreements": list(result.get("disagreements", []) or []),
        "cost_usd": cost,
    }


async def run_consult(question: str, experts: list[str], max_experts: int, budget: float) -> dict[str, Any]:
    """Resolve experts (explicit or auto-selected) and run one bounded council."""
    from deepr.experts.council import ExpertCouncil

    council = ExpertCouncil()
    if experts:
        chosen: list[dict[str, str]] = [{"name": name, "domain": ""} for name in experts]
    else:
        chosen = await council.select_experts(question, max_experts=min(max_experts, MAX_CONSULT_EXPERTS))
    return await council.consult(question, experts=chosen, budget=budget)
