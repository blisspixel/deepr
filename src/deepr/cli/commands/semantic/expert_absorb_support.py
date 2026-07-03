"""Backend selection and absorber construction for ``deepr expert absorb``.

Extracted from ``expert_maintenance.py`` (Phase Q3 decomposition) so the command
module stays under the file-size ceiling and the capacity waterfall plus the
three-way (local / plan / metered) absorber construction can be unit-tested in
isolation. Existing-flag behavior is preserved: the same selection notes and ToS
warnings are printed in the same order, and the same spend gates apply. This
extraction additionally threads the optional second-checker escalator through
every backend and hardens the plan-adapter lookup with an explicit None guard.

The public entry point is :func:`build_absorb_backend`. It resolves the backend
once, then dispatches to a per-backend builder so each stays a small, readable,
independently testable unit (and under the complexity ratchet). Provider
clients, the absorber class, and backend resolvers are imported inside the
functions (as they were in the command) so the child process env stays clean
and tests can monkeypatch them at their source modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepr.cli.colors import console, print_warning
from deepr.cli.commands.semantic.grounding_support import absorber_kwargs, build_grounding_pair


class AbsorbBackendError(ValueError):
    """A user-facing setup failure that should exit non-zero before any cost.

    Subclasses ``ValueError`` so the command can catch it together with the
    grounding-flag errors raised by the checker/escalator builders and print
    both through the same non-zero exit path.
    """


@dataclass(frozen=True)
class AbsorbBackend:
    """A constructed absorber plus the cost note to show before running it."""

    absorber: Any
    cost_note: str


@dataclass(frozen=True)
class GroundingFlags:
    """The grounding-check flag bundle threaded to each backend builder.

    Bundling keeps the per-backend builder signatures small and avoids
    repeating the same five keyword arguments at every construction site.
    """

    enabled: bool
    checker_plan: str | None
    checker_plan_model: str | None
    second_checker_plan: str | None
    second_checker_plan_model: str | None


@dataclass(frozen=True)
class _Selection:
    """The resolved capacity-waterfall decision for one absorb run."""

    use_local: bool
    use_plan: bool
    plan_backend_id: str | None
    selection_note: str
    model: str | None


def build_absorb_backend(
    *,
    profile: Any,
    local: bool,
    api: bool,
    plan: str | None,
    plan_model: str | None,
    model: str | None,
    run_grounding_checks: bool,
    checker_plan: str | None,
    checker_plan_model: str | None,
    second_checker_plan: str | None,
    second_checker_plan_model: str | None,
    json_output: bool,
) -> AbsorbBackend:
    """Resolve the maintenance backend and build the matching ``ReportAbsorber``.

    The capacity waterfall picks owned local capacity before metered API:
    ``--local`` forces local, ``--plan`` forces an explicit plan CLI, ``--api``
    or an explicit ``--model`` forces metered, and otherwise an admitted and
    available local model is used, else metered. The reason is printed as a dim
    note (unless JSON output is requested), matching the command's prior output.

    Raises ``AbsorbBackendError`` for a user-facing setup failure (unknown plan
    backend or no local model). The grounding-pair builders may separately raise
    ``ValueError`` for a bad flag combination; both are meant to be caught by the
    caller and turned into a non-zero exit before any extraction cost.
    """
    grounding = GroundingFlags(
        enabled=run_grounding_checks,
        checker_plan=checker_plan,
        checker_plan_model=checker_plan_model,
        second_checker_plan=second_checker_plan,
        second_checker_plan_model=second_checker_plan_model,
    )
    selection = _resolve_backend_selection(local=local, api=api, plan=plan, model=model)
    if selection.use_local:
        return _build_local_absorber(
            profile=profile,
            model=selection.model,
            selection_note=selection.selection_note,
            grounding=grounding,
            json_output=json_output,
        )
    if selection.use_plan:
        return _build_plan_absorber(
            profile=profile,
            plan_backend_id=selection.plan_backend_id,
            plan_model=plan_model,
            selection_note=selection.selection_note,
            grounding=grounding,
            json_output=json_output,
        )
    return _build_metered_absorber(profile=profile, model=selection.model, grounding=grounding)


def _resolve_backend_selection(*, local: bool, api: bool, plan: str | None, model: str | None) -> _Selection:
    """Run the capacity waterfall and return the chosen backend + selection note."""
    use_local = local
    use_plan = False
    plan_backend_id = plan
    selection_note = ""
    if plan:
        from deepr.backends.waterfall import choose_plan_quota_backend

        choice = choose_plan_quota_backend(plan, allow_metered_at_margin=True)
        if not choice.is_plan_quota:
            raise AbsorbBackendError(choice.reason)
        use_plan = True
        plan_backend_id = choice.plan_backend_id
        selection_note = choice.reason
    elif not local and not api and model is None:
        from deepr.backends.admission import TASK_CLASS_ABSORB
        from deepr.backends.waterfall import choose_maintenance_backend

        choice = choose_maintenance_backend(TASK_CLASS_ABSORB)
        use_local = choice.is_local
        use_plan = choice.is_plan_quota
        plan_backend_id = choice.plan_backend_id
        if use_local:
            model = choice.model
            selection_note = choice.reason
        elif use_plan:
            selection_note = choice.reason
    return _Selection(use_local, use_plan, plan_backend_id, selection_note, model)


def _grounding_pair(grounding: GroundingFlags, *, maker_vendor: str, **defaults: Any) -> tuple[Any, Any]:
    """Build the checker + optional second-checker escalator for one maker vendor.

    A malformed grounding request (an unbuildable checker, or a second checker
    that is not a distinct plan-quota vendor) is a user-facing setup failure, so
    the underlying ``ValueError`` is re-raised as ``AbsorbBackendError`` to share
    the caller's exit-before-cost path. Any other ``ValueError`` from provider or
    absorber construction is deliberately left to propagate, matching the prior
    per-branch handling that only caught the grounding builders.
    """
    try:
        return build_grounding_pair(
            enabled=grounding.enabled,
            checker_plan=grounding.checker_plan,
            checker_plan_model=grounding.checker_plan_model,
            second_checker_plan=grounding.second_checker_plan,
            second_checker_plan_model=grounding.second_checker_plan_model,
            maker_vendor=maker_vendor,
            **defaults,
        )
    except ValueError as exc:
        raise AbsorbBackendError(str(exc)) from exc


def _emit_selection_note(selection_note: str, json_output: bool) -> None:
    if selection_note and not json_output:
        console.print(f"[dim]{selection_note}[/dim]")


def _build_local_absorber(
    *, profile: Any, model: str | None, selection_note: str, grounding: GroundingFlags, json_output: bool
) -> AbsorbBackend:
    from deepr.backends.local import default_local_model, ollama_chat_client
    from deepr.experts.report_absorber import ReportAbsorber

    local_model = model or default_local_model()
    if not local_model:
        raise AbsorbBackendError("No local model available. Is Ollama running? Check: deepr capacity --probe")
    local_client = ollama_chat_client()
    checker, escalator = _grounding_pair(
        grounding,
        maker_vendor="local",
        default_client=local_client,
        default_vendor="local",
        default_model=local_model,
    )
    absorber = ReportAbsorber(
        profile,
        **absorber_kwargs(
            model=local_model,
            client=local_client,
            grounding_checker=checker,
            grounding_escalator=escalator,
            estimated_cost=0.0,
        ),
    )
    _emit_selection_note(selection_note, json_output)
    return AbsorbBackend(absorber, f"$0 (local model {local_model})")


def _build_plan_absorber(
    *,
    profile: Any,
    plan_backend_id: str | None,
    plan_model: str | None,
    selection_note: str,
    grounding: GroundingFlags,
    json_output: bool,
) -> AbsorbBackend:
    from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter
    from deepr.experts.report_absorber import ReportAbsorber

    plan_adapter = get_adapter(plan_backend_id or "")
    if plan_adapter is None:
        raise AbsorbBackendError(f"unknown plan-quota backend {plan_backend_id!r}")
    client = PlanQuotaChatClient(plan_adapter, model=plan_model)
    checker, escalator = _grounding_pair(
        grounding,
        maker_vendor=plan_adapter.backend_id,
        default_client=client,
        default_vendor=plan_adapter.backend_id,
        default_model=plan_model or plan_adapter.backend_id,
    )
    absorber = ReportAbsorber(
        profile,
        **absorber_kwargs(
            model=plan_model or plan_adapter.backend_id,
            client=client,
            grounding_checker=checker,
            grounding_escalator=escalator,
            estimated_cost=0.0,
        ),
    )
    _emit_selection_note(selection_note, json_output)
    if plan_adapter.tos_note and not json_output:
        print_warning(plan_adapter.tos_note)
    cost_note = "billed per use" if plan_adapter.metered_at_margin else "$0 at the margin (prepaid plan)"
    return AbsorbBackend(absorber, cost_note)


def _build_metered_absorber(*, profile: Any, model: str | None, grounding: GroundingFlags) -> AbsorbBackend:
    from deepr.experts.report_absorber import ESTIMATED_EXTRACTION_COST, ReportAbsorber

    checker, escalator = _grounding_pair(grounding, maker_vendor="api_metered")
    absorber = ReportAbsorber(
        profile,
        **absorber_kwargs(model=model or "gpt-5-mini", grounding_checker=checker, grounding_escalator=escalator),
    )
    return AbsorbBackend(absorber, f"~${ESTIMATED_EXTRACTION_COST:.2f}")


__all__ = ["AbsorbBackend", "AbsorbBackendError", "build_absorb_backend"]
