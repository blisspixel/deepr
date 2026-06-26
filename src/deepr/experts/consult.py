"""Shared expert-consultation core (used by the CLI verb and the MCP tool).

One bounded "knowledge transaction" (docs/design/agentic-harness-boundary.md):
route a question to the relevant experts (or an explicit set), run the bounded
council, and shape the result into the versioned ``deepr-consult-v1`` artifact.
Both ``deepr expert consult`` and the ``deepr_consult_experts`` MCP tool import
this, so the two surfaces share one contract and one code path - and the MCP
server never has to depend on the CLI layer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

CONSULT_SCHEMA_VERSION = "deepr-consult-v1"
CONSULT_KIND = "deepr.expert.consult"
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


def build_synthesis_backend(
    *,
    use_local: bool = False,
    local_model: str | None = None,
    plan_backend: str | None = None,
    plan_model: str | None = None,
) -> ConsultSynthesisBackend:
    """Build the shared consult synthesis backend for CLI and MCP callers."""
    if use_local and plan_backend:
        raise ConsultBackendError("Choose only one synthesis backend: local or plan.")

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

    return ConsultSynthesisBackend()


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
    }


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
