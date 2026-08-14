"""Shared expert-consultation core (used by the CLI verb and the MCP tool).

One bounded "knowledge transaction" (docs/design/agentic-harness-boundary.md):
route a question to the relevant experts (or an explicit set), run the bounded
council, and shape the result into the versioned ``deepr-consult-v1`` artifact.
Both ``deepr expert consult`` and the ``deepr_consult_experts`` MCP tool import
this, so the two surfaces share one contract and one code path - and the MCP
server never has to depend on the CLI layer.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deepr.experts.constants import SYNTHESIS_BUDGET_FRACTION

CONSULT_SCHEMA_VERSION = "deepr-consult-v1"
CONSULT_KIND = "deepr.expert.consult"
COLLABORATION_SCHEMA_VERSION = "deepr-expert-collaboration-v1"
COLLABORATION_KIND = "deepr.expert.collaboration"
# Hard ceiling on how many experts one consult transaction may fan out to when
# auto-selecting. A harness opts into wider fan-out by passing a larger
# max_experts (e.g. 10 for a Grok-Heavy style cross-domain sweep); the default
# stays small. Spend is still bounded by the council's upfront cost reservation
# and per-expert budget split, and parallelism by MAX_COUNCIL_CONCURRENCY.
MAX_CONSULT_EXPERTS = 10


class ConsultBackendError(ValueError):
    """Raised when a requested consult synthesis backend is unavailable."""


@dataclass(frozen=True)
class ConsultSynthesisBackend:
    """Synthesis backend selected for a consult transaction."""

    client: Any | None = None
    model: str | None = None
    provider: str = "openai"
    allow_live_fallback: bool = False
    note: str = ""
    tos_note: str = ""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _named_plans(plan_backend: str) -> list[str]:
    return [p.strip() for p in str(plan_backend or "").split(",") if p.strip()]


def _usable_plans(plan_backend: str) -> tuple[list[str], list[str]]:
    """Order named plans by headroom and drop ones already at their cap.

    ``--plan grok,codex,claude`` is a candidate list. Reading quota headroom
    first is what stops a consult beginning on a plan that is already
    exhausted, which costs a round-trip and a confusing error rather than a
    result. A single name passes straight through, so nothing changes for
    callers that name one plan.

    Falls back to the given order when headroom is unreadable: an unavailable
    quotabot must not turn into a refusal to consult at all.

    Safety-blocked backends stay in this list. The resolver walks it and skips
    those that cannot execute, so a blocked first name does not hide a later
    eligible one.
    """
    names = _named_plans(plan_backend)
    if len(names) <= 1:
        return list(names), []

    try:
        from deepr.backends.quota_headroom import exhausted, order_by_headroom, read_headroom

        headroom = read_headroom()
    except Exception:
        headroom = {}

    if not headroom:
        return list(names), []

    spent = exhausted(names, headroom)
    usable = [n for n in order_by_headroom(names, headroom) if n not in spent]
    why_not = [headroom[n.lower()].describe() for n in spent if n.lower() in headroom]
    return usable, why_not


def _first_usable_plan(plan_backend: str) -> tuple[str | None, list[str]]:
    """Pick the first named plan with headroom. Returns (choice, why-not)."""
    usable, why_not = _usable_plans(plan_backend)
    return (usable[0] if usable else None), why_not


def _plan_synthesis_backend(plan_backend: str, plan_model: str | None) -> ConsultSynthesisBackend:
    """Resolve a consult onto prepaid plan capacity.

    A list picks the first plan that resolves, is safety-eligible, and has
    headroom. Not the same as the study path's pool, and deliberately not
    pretending to be: a consult builds a chat *client* rather than a
    completion callable, so there is nowhere to fail over mid-call without
    wrapping the client. What this does buy is the larger half - not starting
    a consult on a plan that is already at its cap, or on a named backend
    that cannot execute, while a later name in the same list could.
    """
    from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter
    from deepr.backends.waterfall import choose_plan_quota_backend

    candidates, why_not = _usable_plans(plan_backend)
    if not candidates:
        raise ConsultBackendError(f"No plan backend has capacity: {'; '.join(why_not)}")

    for chosen in candidates:
        choice = choose_plan_quota_backend(chosen)
        if not choice.is_plan_quota:
            why_not.append(f"{chosen}: {choice.reason}")
            continue
        adapter = get_adapter(choice.plan_backend_id or chosen)
        if adapter is None:
            why_not.append(f"{chosen}: unknown plan-quota backend")
            continue
        return ConsultSynthesisBackend(
            client=PlanQuotaChatClient(adapter, model=plan_model, operation="plan_quota_consult_synthesis"),
            model=plan_model or adapter.backend_id,
            provider=f"plan_quota:{adapter.backend_id}",
            allow_live_fallback=False,
            note=f"{choice.reason}; live metered expert fallback disabled",
            tos_note=adapter.tos_note,
        )

    raise ConsultBackendError(f"No plan backend has capacity: {'; '.join(why_not)}")


def build_synthesis_backend(
    *,
    use_local: bool = False,
    local_model: str | None = None,
    plan_backend: str | None = None,
    plan_model: str | None = None,
    api_provider: str | None = None,
    api_model: str | None = None,
) -> ConsultSynthesisBackend:
    """Build an owned-capacity consult synthesis backend.

    Metered API synthesis is intentionally absent from this factory. Keeping
    the refusal at the shared boundary means CLI, MCP, A2A, and direct Python
    callers cannot turn compatibility fields or consent flags into spend.
    """
    if use_local and plan_backend:
        raise ConsultBackendError("Choose only one synthesis backend: local or plan.")
    if (use_local or plan_backend) and (api_provider or api_model):
        raise ConsultBackendError("API provider/model overrides are only valid for synthesis_backend='api'.")

    if use_local:
        from deepr.backends.local import default_local_model, ollama_chat_client

        model = local_model or default_local_model()
        if not model:
            raise ConsultBackendError("No local model available. Is Ollama running? Check: deepr capacity --probe")
        return ConsultSynthesisBackend(
            client=ollama_chat_client(),
            model=model,
            provider="local",
            allow_live_fallback=False,
            note=f"$0 local synthesis ({model}); live metered expert fallback disabled",
        )

    if plan_backend:
        return _plan_synthesis_backend(plan_backend, plan_model)

    raise ConsultBackendError(
        "Metered API synthesis is disabled for expert consults. Use local Ollama or an explicit "
        "safety-eligible plan-quota backend. No provider client was constructed."
    )


def build_consult_payload(question: str, result: dict[str, Any]) -> dict[str, Any]:
    """Shape a council result into the versioned consult artifact.

    The contract a harness consumes: the synthesized answer, each contributing
    expert's calibrated perspective, the points of agreement/dissent, and the
    cost. Single-shot and safe to render or machine-parse.
    """
    perspectives = result.get("perspectives", []) or []
    cost = float(result.get("total_cost", 0.0) or 0.0)
    shaped_perspectives = []
    for p in perspectives:
        shaped = {
            "expert": p.get("expert_name", ""),
            "domain": p.get("domain", "") or "",
            "confidence": round(float(p.get("confidence", 0.0) or 0.0), 3),
            "response": p.get("response", "") or "",
        }
        context = p.get("context") or {}
        if context:
            shaped["context"] = dict(context)
        shaped_perspectives.append(shaped)

    return {
        "schema_version": CONSULT_SCHEMA_VERSION,
        "kind": CONSULT_KIND,
        "contract": {
            "stability": "experimental",
            "cost_usd": cost,
            "consultation_mode": "one_shot_stored_context_synthesis",
            "expert_generation_calls": 0,
            "maximum_synthesis_calls": 1,
            "experts_exchange_turns": False,
            "proposal_only": True,
            "writes_expert_state": False,
            "writes_beliefs": False,
            "writes_graph": False,
        },
        "question": question,
        "answer": result.get("synthesis", "") or "",
        "synthesis_status": result.get("synthesis_status", "completed") or "completed",
        "synthesis_error_type": result.get("synthesis_error_type", "") or "",
        "synthesis_stop_reason": result.get("synthesis_stop_reason", "") or "",
        "experts_consulted": [p.get("expert_name", "") for p in perspectives],
        "perspectives": shaped_perspectives,
        "agreements": list(result.get("agreements", []) or []),
        "disagreements": list(result.get("disagreements", []) or []),
        "cost_usd": cost,
        "collaboration": build_collaboration_contract(question, result),
    }


def build_collaboration_contract(
    question: str,
    result: dict[str, Any],
    *,
    capacity: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the protocol-native expert collaboration metadata.

    This is a deterministic artifact contract over one council transaction. It
    records the roster, roles, budget and capacity posture, evidence packet, and
    dissent handling without changing the answer or adjudicating truth.
    """
    perspectives = result.get("perspectives", []) or []
    agreements = list(result.get("agreements", []) or [])
    disagreements = list(result.get("disagreements", []) or [])
    requested_budget = float(result.get("requested_budget_usd", 0.0) or 0.0)
    actual_cost = float(result.get("total_cost", 0.0) or 0.0)
    trace_id = str((trace or {}).get("trace_id", "") or result.get("shared_task_trace_id", "") or "")
    capacity_block = capacity or {}
    metered_synthesis = capacity_block.get("synthesis_backend") == "api"

    roster = []
    context_sources: dict[str, int] = {}
    for index, perspective in enumerate(perspectives):
        context = perspective.get("context") if isinstance(perspective, dict) else {}
        context = context if isinstance(context, dict) else {}
        source = str(context.get("source", "unknown") or "unknown")
        context_sources[source] = context_sources.get(source, 0) + 1
        roster.append(
            {
                "expert": str(perspective.get("expert_name", "") or ""),
                "domain": str(perspective.get("domain", "") or ""),
                "role": "domain_perspective",
                "order": index,
                "confidence": round(float(perspective.get("confidence", 0.0) or 0.0), 3),
                "context_source": source,
                "context_selection": str(context.get("selection", "") or ""),
                "beliefs_included": int(context.get("beliefs_included", 0) or 0),
                "cost_usd": float(perspective.get("cost", 0.0) or 0.0),
            }
        )

    return {
        "schema_version": COLLABORATION_SCHEMA_VERSION,
        "kind": COLLABORATION_KIND,
        "contract": {
            "cost_usd": actual_cost,
            "host_orchestrated": True,
            "deepr_enacts_downstream_actions": False,
            "semantic_verdict": False,
            "derived_from_consult_result": True,
            "breaking_changes_require_new_schema_version": True,
        },
        "task": {
            "question_hash": _sha256(question),
            "consult_trace_id": trace_id,
            "shared_task_trace_id": trace_id,
            "input_field": "question",
        },
        "roster": roster,
        "budget_capacity_contract": {
            "requested_budget_usd": requested_budget,
            "total_spend_ceiling_usd": requested_budget,
            "actual_cost_usd": actual_cost,
            "capacity": capacity_block,
            "metered_fallback_allowed": bool(capacity_block.get("live_metered_fallback", False)),
            "metered_perspective_calls_enabled": False,
            "maximum_metered_perspective_calls": 0,
            "maximum_synthesis_calls": 1,
            "synthesis_budget_fraction": SYNTHESIS_BUDGET_FRACTION,
            "metered_synthesis_ceiling_usd": round(
                requested_budget * SYNTHESIS_BUDGET_FRACTION if metered_synthesis else 0.0,
                6,
            ),
        },
        "interaction": {
            "mode": "one_shot_stored_context_synthesis",
            "expert_generation_calls": 0,
            "peer_turns": 0,
            "maximum_synthesis_calls": 1,
            "experts_exchange_turns": False,
        },
        "evidence_packet": {
            "perspective_count": len(perspectives),
            "context_sources": context_sources,
            "belief_store_perspective_count": context_sources.get("belief_store", 0),
            "failed_perspective_count": context_sources.get("failed", 0),
            "agreement_count": len(agreements),
            "disagreement_count": len(disagreements),
        },
        "dissent_handling": {
            "agreements_field": "agreements",
            "disagreements_field": "disagreements",
            "dissent_preserved": True,
            "synthesis_is_not_truth_adjudication": True,
        },
        "learning_boundary": {
            "proposal_only": True,
            "discussion_is_evidence": False,
            "writes_expert_state": False,
            "writes_beliefs": False,
            "writes_graph": False,
            "verification_required_before_graph_commit": True,
        },
        "result_artifact": {
            "schema_version": CONSULT_SCHEMA_VERSION,
            "kind": CONSULT_KIND,
            "answer_field": "answer",
            "perspectives_field": "perspectives",
            "agreements_field": "agreements",
            "disagreements_field": "disagreements",
        },
    }


def attach_collaboration_runtime(
    payload: dict[str, Any],
    *,
    result: dict[str, Any],
    capacity: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
) -> None:
    """Attach runtime trace and capacity refs to the consult collaboration block."""
    payload["collaboration"] = build_collaboration_contract(
        str(payload.get("question", "")),
        result,
        capacity=capacity,
        trace=trace,
    )


def record_consult_payload_trace(
    payload: dict[str, Any],
    *,
    question: str,
    requested_experts: list[str],
    max_experts: int,
    budget: float,
    result: dict[str, Any],
    capacity: dict[str, Any],
    trace_id: str | None = None,
    path: Path | None = None,
    lock_timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Enrich and append one consult trace before exposing its public reference.

    Trace storage is append-only, so runtime collaboration metadata must be
    attached before the record is written. Preallocating the trace id keeps the
    durable collaboration contract and the returned artifact linked to the same
    transaction without rewriting the stored record.
    """
    from deepr.experts.consult_traces import new_consult_trace_id, record_consult_trace

    shared_trace_id = trace_id or new_consult_trace_id()
    attach_collaboration_runtime(payload, result=result, capacity=capacity, trace={"trace_id": shared_trace_id})
    trace_ref = record_consult_trace(
        path=path,
        question=question,
        requested_experts=requested_experts,
        max_experts=max_experts,
        budget=budget,
        payload=payload,
        result=result,
        capacity=capacity,
        trace_id=shared_trace_id,
        lock_timeout_seconds=lock_timeout_seconds,
    )
    payload["trace"] = trace_ref
    return trace_ref


def resolve_explicit_expert_choices(experts: list[str], profiles: Iterable[Any] | None = None) -> list[dict[str, str]]:
    """Resolve user-supplied expert names or slugs to profile-backed choices."""
    from deepr.experts.paths import expert_slug

    if profiles is None:
        from deepr.experts.profile import ExpertStore

        profiles = ExpertStore().list_all()

    profile_list = list(profiles)
    by_name = {profile.name.casefold(): profile for profile in profile_list}
    by_slug = {expert_slug(profile.name): profile for profile in profile_list}

    chosen: list[dict[str, str]] = []
    for name in experts:
        profile = by_name.get(name.casefold()) or by_slug.get(expert_slug(name))
        if profile is None:
            chosen.append({"name": name, "domain": ""})
            continue
        chosen.append(
            {
                "name": profile.name,
                "domain": profile.domain or profile.description or "",
            }
        )
    validate_consult_roster(chosen)
    return chosen


def validate_consult_roster(experts: list[dict[str, str]]) -> None:
    """Reject oversized rosters and aliases for the same expert identity."""
    from deepr.experts.paths import expert_slug

    if len(experts) > MAX_CONSULT_EXPERTS:
        raise ValueError(f"Consult roster cannot exceed {MAX_CONSULT_EXPERTS} experts.")

    seen: dict[str, str] = {}
    for expert in experts:
        name = expert["name"]
        task_id = expert_slug(name)
        previous = seen.get(task_id)
        if previous is not None:
            raise ValueError(
                f"Duplicate expert roster entry: {name!r} resolves to the same canonical expert as {previous!r}."
            )
        seen[task_id] = name


async def run_consult(
    question: str,
    experts: list[str],
    max_experts: int,
    budget: float,
    *,
    synthesis_client: Any | None = None,
    synthesis_model: str | None = None,
    synthesis_provider: str = "openai",
    allow_live_fallback: bool = False,
    progress_callback: Any = None,
) -> dict[str, Any]:
    """Resolve experts (explicit or auto-selected) and run one bounded council."""
    from deepr.experts.constants import UTILITY_MODEL
    from deepr.experts.council import ExpertCouncil

    if isinstance(max_experts, bool) or not isinstance(max_experts, int) or not 1 <= max_experts <= MAX_CONSULT_EXPERTS:
        raise ValueError(f"max_experts must be between 1 and {MAX_CONSULT_EXPERTS}.")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
        raise ValueError("budget must be finite and non-negative.")

    if experts:
        if len(experts) > MAX_CONSULT_EXPERTS:
            raise ValueError(f"Consult roster cannot exceed {MAX_CONSULT_EXPERTS} experts.")
        chosen = resolve_explicit_expert_choices(experts)
    else:
        chosen = None

    council = ExpertCouncil(
        synthesis_client=synthesis_client,
        synthesis_model=synthesis_model or UTILITY_MODEL,
        synthesis_provider=synthesis_provider,
        allow_live_fallback=allow_live_fallback,
    )
    if chosen is None:
        chosen = await council.select_experts(question, max_experts=max_experts)
    consult_kwargs: dict[str, Any] = {"experts": chosen, "budget": budget}
    if progress_callback is not None:
        consult_kwargs["progress_callback"] = progress_callback
    return await council.consult(question, **consult_kwargs)
