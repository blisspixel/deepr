"""Build an ``ExpertSyncEngine`` wired to a chosen maintenance backend.

`ExpertSyncEngine` is deliberately backend-agnostic - it takes an injected
``research_fn`` and ``absorber``. This module is the one place that wires a
resolved capacity choice (local Ollama, a plan-quota CLI, or metered API) to a
concrete engine, so the `expert sync` CLI and the `expert sync-all` roster loop
share exactly one construction path and cannot drift apart.

Imports are deferred to call time on purpose: it keeps module import cheap, and
it lets tests monkeypatch the backend factories at their source modules
(``deepr.backends.local.*``, ``deepr.experts.report_absorber.ReportAbsorber``,
``deepr.experts.sync.ExpertSyncEngine``) and have those patches take effect here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from deepr.backends.fresh_context import FreshContext
    from deepr.experts.maker_checker import GroundingChecker
    from deepr.experts.profile import ExpertProfile
    from deepr.experts.sync import ExpertSyncEngine


def _with_claim_services(
    engine_kwargs: dict[str, Any],
    claim_extractor: Any | None,
    claim_verifier: Any | None,
) -> dict[str, Any]:
    if claim_extractor is None:
        return engine_kwargs if claim_verifier is None else {**engine_kwargs, "claim_verifier": claim_verifier}
    kwargs = {**engine_kwargs, "claim_extractor": claim_extractor}
    if claim_verifier is not None:
        kwargs["claim_verifier"] = claim_verifier
    return kwargs


def _with_spend_decision(engine_kwargs: dict[str, Any], spend_decision_fn: Any | None) -> dict[str, Any]:
    if spend_decision_fn is None:
        return engine_kwargs
    return {**engine_kwargs, "spend_decision_fn": spend_decision_fn}


def _local_research_kwargs(context_builder: Any, client: Any, claim_extractor: Any | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"context_builder": context_builder}
    if claim_extractor is not None:
        kwargs["client"] = client
    return kwargs


def _metered_claim_services(compile_claims: bool) -> tuple[Any | None, Any | None]:
    if not compile_claims:
        return None, None
    from deepr.experts.claim_extraction import SemanticClaimExtractor
    from deepr.experts.claim_verification import SemanticClaimVerifier

    service_kwargs = {
        "provider": "openai",
        "model": "gpt-5-mini",
        "capacity_source": "api_metered",
        "allow_metered": True,
    }
    return (
        SemanticClaimExtractor(**service_kwargs),
        SemanticClaimVerifier(**service_kwargs),
    )


def build_sync_engine(
    profile: ExpertProfile,
    *,
    use_local: bool = False,
    local_model: str | None = None,
    use_plan: bool = False,
    plan_adapter: Any | None = None,
    plan_model: str | None = None,
    context_builder: Callable[[str], Awaitable[FreshContext]] | None = None,
    grounding_checker: GroundingChecker | None = None,
    compile_claims: bool = False,
    spend_decision_fn: Any | None = None,
) -> tuple[ExpertSyncEngine, str]:
    """Construct a sync engine for the resolved backend and report its source.

    Returns ``(engine, capacity_source)`` where ``capacity_source`` is the
    cost-ledger label: ``"local"``, ``"plan_quota:<id>"``, or ``"api_metered"``.
    The waterfall decision (which backend) is made by the caller; this only
    wires it. A local or plan engine drives both research and verified
    extraction off one client, so the whole sync runs on that capacity with no
    silent metered fallback.
    """
    from deepr.experts.sync import ExpertSyncEngine

    if use_local:
        from deepr.backends.local import make_local_research_fn, ollama_chat_client
        from deepr.experts.claim_extraction import SemanticClaimExtractor
        from deepr.experts.claim_verification import SemanticClaimVerifier
        from deepr.experts.report_absorber import ReportAbsorber

        # The caller resolves and validates the local model before choosing the
        # local rung (sync_cmd errors out when none is available); guard the
        # contract with a real raise (asserts are stripped under -O).
        if local_model is None:
            raise ValueError("use_local requires a resolved local_model")
        client = ollama_chat_client()
        absorber_kwargs = {"model": local_model, "client": client, "estimated_cost": 0.0}
        if grounding_checker is not None:
            absorber_kwargs["grounding_checker"] = grounding_checker
        absorber = ReportAbsorber(profile, **absorber_kwargs)
        claim_extractor = (
            SemanticClaimExtractor(
                provider="local",
                model=local_model,
                capacity_source="local",
                client=client,
                estimated_cost_usd=0.0,
            )
            if compile_claims
            else None
        )
        claim_verifier = (
            SemanticClaimVerifier(
                provider="local",
                model=local_model,
                capacity_source="local",
                client=client,
                estimated_cost_usd=0.0,
            )
            if compile_claims
            else None
        )
        engine_kwargs: dict[str, Any] = {
            "research_fn": make_local_research_fn(
                local_model, **_local_research_kwargs(context_builder, client, claim_extractor)
            ),
            "absorber": absorber,
        }
        engine_kwargs = _with_spend_decision(engine_kwargs, spend_decision_fn)
        engine = ExpertSyncEngine(profile, **_with_claim_services(engine_kwargs, claim_extractor, claim_verifier))
        return engine, "local"

    if use_plan and plan_adapter is not None:
        from deepr.backends.plan_quota import PlanQuotaChatClient, make_plan_quota_research_fn
        from deepr.experts.claim_extraction import SemanticClaimExtractor
        from deepr.experts.claim_verification import ESTIMATED_VERIFICATION_COST, SemanticClaimVerifier
        from deepr.experts.report_absorber import ESTIMATED_EXTRACTION_COST, ReportAbsorber

        # One client serves research and verified extraction, so the whole sync
        # stays on prepaid plan capacity with no silent metered call.
        client = PlanQuotaChatClient(plan_adapter, model=plan_model)
        absorber_kwargs = {"model": plan_model or plan_adapter.backend_id, "client": client, "estimated_cost": 0.0}
        if grounding_checker is not None:
            absorber_kwargs["grounding_checker"] = grounding_checker
        absorber = ReportAbsorber(profile, **absorber_kwargs)
        claim_extractor = (
            SemanticClaimExtractor(
                provider=plan_adapter.backend_id,
                model=plan_model or plan_adapter.backend_id,
                capacity_source=f"plan_quota:{plan_adapter.backend_id}",
                client=client,
                estimated_cost_usd=ESTIMATED_EXTRACTION_COST
                if bool(getattr(plan_adapter, "metered_at_margin", False))
                else 0.0,
                allow_metered=bool(getattr(plan_adapter, "metered_at_margin", False)),
            )
            if compile_claims
            else None
        )
        claim_verifier = (
            SemanticClaimVerifier(
                provider=plan_adapter.backend_id,
                model=plan_model or plan_adapter.backend_id,
                capacity_source=f"plan_quota:{plan_adapter.backend_id}",
                client=client,
                estimated_cost_usd=ESTIMATED_VERIFICATION_COST
                if bool(getattr(plan_adapter, "metered_at_margin", False))
                else 0.0,
                allow_metered=bool(getattr(plan_adapter, "metered_at_margin", False)),
            )
            if compile_claims
            else None
        )
        engine_kwargs = {
            "research_fn": make_plan_quota_research_fn(
                plan_adapter, model=plan_model, context_builder=context_builder, client=client
            ),
            "absorber": absorber,
        }
        engine_kwargs = _with_spend_decision(engine_kwargs, spend_decision_fn)
        engine = ExpertSyncEngine(profile, **_with_claim_services(engine_kwargs, claim_extractor, claim_verifier))
        return engine, f"plan_quota:{plan_adapter.backend_id}"

    if grounding_checker is not None:
        from deepr.experts.report_absorber import ReportAbsorber

        claim_extractor, claim_verifier = _metered_claim_services(compile_claims)
        engine_kwargs = _with_claim_services(
            {"absorber": ReportAbsorber(profile, grounding_checker=grounding_checker)},
            claim_extractor,
            claim_verifier,
        )
        engine_kwargs = _with_spend_decision(engine_kwargs, spend_decision_fn)
        return ExpertSyncEngine(profile, **engine_kwargs), "api_metered"

    if compile_claims:
        claim_extractor, claim_verifier = _metered_claim_services(True)
        engine_kwargs = _with_claim_services({}, claim_extractor, claim_verifier)
        engine_kwargs = _with_spend_decision(engine_kwargs, spend_decision_fn)
        return ExpertSyncEngine(profile, **engine_kwargs), "api_metered"

    if spend_decision_fn is None:
        return ExpertSyncEngine(profile), "api_metered"
    return ExpertSyncEngine(profile, spend_decision_fn=spend_decision_fn), "api_metered"
