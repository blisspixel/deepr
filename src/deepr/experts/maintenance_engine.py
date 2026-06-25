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
        from deepr.experts.report_absorber import ReportAbsorber

        # The caller resolves and validates the local model before choosing the
        # local rung (sync_cmd errors out when none is available); guard the
        # contract with a real raise (asserts are stripped under -O).
        if local_model is None:
            raise ValueError("use_local requires a resolved local_model")
        absorber_kwargs = {"model": local_model, "client": ollama_chat_client()}
        if grounding_checker is not None:
            absorber_kwargs["grounding_checker"] = grounding_checker
        absorber = ReportAbsorber(profile, **absorber_kwargs)
        engine = ExpertSyncEngine(
            profile,
            research_fn=make_local_research_fn(local_model, context_builder=context_builder),
            absorber=absorber,
        )
        return engine, "local"

    if use_plan and plan_adapter is not None:
        from deepr.backends.plan_quota import PlanQuotaChatClient, make_plan_quota_research_fn
        from deepr.experts.report_absorber import ReportAbsorber

        # One client serves research and verified extraction, so the whole sync
        # stays on prepaid plan capacity with no silent metered call.
        client = PlanQuotaChatClient(plan_adapter, model=plan_model)
        absorber_kwargs = {"model": plan_model or plan_adapter.backend_id, "client": client}
        if grounding_checker is not None:
            absorber_kwargs["grounding_checker"] = grounding_checker
        absorber = ReportAbsorber(profile, **absorber_kwargs)
        engine = ExpertSyncEngine(
            profile,
            research_fn=make_plan_quota_research_fn(
                plan_adapter, model=plan_model, context_builder=context_builder, client=client
            ),
            absorber=absorber,
        )
        return engine, f"plan_quota:{plan_adapter.backend_id}"

    if grounding_checker is not None:
        from deepr.experts.report_absorber import ReportAbsorber

        return ExpertSyncEngine(
            profile, absorber=ReportAbsorber(profile, grounding_checker=grounding_checker)
        ), "api_metered"

    return ExpertSyncEngine(profile), "api_metered"
