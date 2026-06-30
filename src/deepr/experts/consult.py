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
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

CONSULT_SCHEMA_VERSION = "deepr-consult-v1"
CONSULT_KIND = "deepr.expert.consult"
COLLABORATION_SCHEMA_VERSION = "deepr-expert-collaboration-v1"
COLLABORATION_KIND = "deepr.expert.collaboration"
DEFAULT_API_SYNTHESIS_PROVIDER = "openai"
DEFAULT_ANTHROPIC_SYNTHESIS_MODEL = "claude-opus-4-8"
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
    allow_live_fallback: bool = True
    note: str = ""
    tos_note: str = ""


class AnthropicConsultSynthesisClient:
    """Lazy AsyncAnthropic holder for consult synthesis.

    Construction is intentionally side-effect light so CLI and schema tests can
    select the backend without requiring a local API key. The real SDK client is
    created only when an explicit API consult reaches the paid call path.
    """

    def __init__(self, *, api_key: str | None = None, client: Any | None = None) -> None:
        self._api_key = api_key
        self._client = client

    def _resolve_client(self) -> Any:
        if self._client is None:
            import os

            from anthropic import AsyncAnthropic

            api_key = self._api_key or os.getenv("ANTHROPIC_API_KEY")
            kwargs = {"api_key": api_key} if api_key else {}
            self._client = AsyncAnthropic(**kwargs)
        return self._client

    @property
    def messages(self) -> Any:
        return self._resolve_client().messages


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_synthesis_backend(
    *,
    use_local: bool = False,
    local_model: str | None = None,
    plan_backend: str | None = None,
    plan_model: str | None = None,
    api_provider: str | None = None,
    api_model: str | None = None,
) -> ConsultSynthesisBackend:
    """Build the shared consult synthesis backend for CLI and MCP callers."""
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
        from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter
        from deepr.backends.waterfall import choose_plan_quota_backend

        choice = choose_plan_quota_backend(plan_backend)
        if not choice.is_plan_quota:
            raise ConsultBackendError(
                f"Plan backend {plan_backend!r} is not available for explicit plan use: {choice.reason}"
            )
        adapter = get_adapter(choice.plan_backend_id or plan_backend)
        if adapter is None:
            raise ConsultBackendError(f"Unknown plan-quota backend {plan_backend!r}.")
        return ConsultSynthesisBackend(
            client=PlanQuotaChatClient(adapter, model=plan_model, operation="plan_quota_consult_synthesis"),
            model=plan_model or adapter.backend_id,
            provider=f"plan_quota:{adapter.backend_id}",
            allow_live_fallback=False,
            note=f"{choice.reason}; live metered expert fallback disabled",
            tos_note=adapter.tos_note,
        )

    provider = (api_provider or DEFAULT_API_SYNTHESIS_PROVIDER).strip().lower()
    if provider == "openai":
        return ConsultSynthesisBackend(
            model=api_model,
            provider="openai",
            allow_live_fallback=True,
            note=f"API synthesis via OpenAI {api_model}" if api_model else "",
        )
    if provider == "anthropic":
        model = api_model or DEFAULT_ANTHROPIC_SYNTHESIS_MODEL
        return ConsultSynthesisBackend(
            client=AnthropicConsultSynthesisClient(),
            model=model,
            provider="anthropic",
            allow_live_fallback=True,
            note=f"API synthesis via Anthropic {model}; prompt-cache controls disabled",
        )
    raise ConsultBackendError("API synthesis provider must be one of: openai, anthropic.")


def build_consult_payload(question: str, result: dict[str, Any]) -> dict[str, Any]:
    """Shape a council result into the versioned consult artifact.

    The contract a harness consumes: the synthesized answer, each contributing
    expert's calibrated perspective, the points of agreement/dissent, and the
    cost. Single-shot and safe to render or machine-parse.
    """
    perspectives = result.get("perspectives", []) or []
    cost = round(float(result.get("total_cost", 0.0) or 0.0), 4)
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
        "contract": {"stability": "experimental", "cost_usd": cost},
        "question": question,
        "answer": result.get("synthesis", "") or "",
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
    requested_budget = round(float(result.get("requested_budget_usd", 0.0) or 0.0), 4)
    actual_cost = round(float(result.get("total_cost", 0.0) or 0.0), 4)
    trace_id = str((trace or {}).get("trace_id", "") or result.get("shared_task_trace_id", "") or "")

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
                "cost_usd": round(float(perspective.get("cost", 0.0) or 0.0), 4),
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
            "actual_cost_usd": actual_cost,
            "capacity": capacity or {},
            "metered_fallback_allowed": bool((capacity or {}).get("live_metered_fallback", True)),
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
    return chosen


async def run_consult(
    question: str,
    experts: list[str],
    max_experts: int,
    budget: float,
    *,
    synthesis_client: Any | None = None,
    synthesis_model: str | None = None,
    synthesis_provider: str = "openai",
    allow_live_fallback: bool = True,
) -> dict[str, Any]:
    """Resolve experts (explicit or auto-selected) and run one bounded council."""
    from deepr.experts.constants import UTILITY_MODEL
    from deepr.experts.council import ExpertCouncil

    council = ExpertCouncil(
        synthesis_client=synthesis_client,
        synthesis_model=synthesis_model or UTILITY_MODEL,
        synthesis_provider=synthesis_provider,
        allow_live_fallback=allow_live_fallback,
    )
    if experts:
        chosen = resolve_explicit_expert_choices(experts)
    else:
        chosen = await council.select_experts(question, max_experts=min(max_experts, MAX_CONSULT_EXPERTS))
    return await council.consult(question, experts=chosen, budget=budget)
