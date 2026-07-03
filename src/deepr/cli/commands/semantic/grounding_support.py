"""CLI support for explicit maker-checker grounding checks."""

from __future__ import annotations

from typing import Any

from deepr.experts.maker_checker import GroundingChecker, choose_checker_vendor, make_grounding_checker

PLAN_BACKEND_CHOICES = ("codex", "claude", "opencode", "kiro", "grok", "antigravity", "copilot")


def validate_grounding_flags(
    *,
    check_grounding: bool,
    checker_plan: str | None,
    checker_plan_model: str | None,
    second_checker_plan: str | None = None,
    second_checker_plan_model: str | None = None,
) -> None:
    if checker_plan and not check_grounding:
        raise ValueError("Use --check-grounding with --checker-plan.")
    if checker_plan_model and not checker_plan:
        raise ValueError("Use --checker-plan-model with --checker-plan.")
    if second_checker_plan and not check_grounding:
        raise ValueError("Use --check-grounding with --second-checker-plan.")
    if second_checker_plan and not checker_plan:
        raise ValueError("Use --second-checker-plan with --checker-plan (it escalates a weak first check).")
    if second_checker_plan and second_checker_plan == checker_plan:
        raise ValueError("--second-checker-plan must differ from --checker-plan for an independent second opinion.")
    if second_checker_plan_model and not second_checker_plan:
        raise ValueError("Use --second-checker-plan-model with --second-checker-plan.")


def absorber_kwargs(
    *,
    model: str,
    client: Any | None = None,
    grounding_checker: GroundingChecker | None = None,
    grounding_escalator: Any | None = None,
    estimated_cost: float | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": model}
    if client is not None:
        kwargs["client"] = client
    if grounding_checker is not None:
        kwargs["grounding_checker"] = grounding_checker
    if grounding_escalator is not None:
        kwargs["grounding_escalator"] = grounding_escalator
    if estimated_cost is not None:
        kwargs["estimated_cost"] = estimated_cost
    return kwargs


def build_grounding_escalator(
    *,
    enabled: bool,
    second_checker_plan: str | None,
    second_checker_plan_model: str | None,
    maker_vendor: str,
) -> Any | None:
    """Build a bounded second-checker escalator, or ``None`` when not requested.

    Only constructed when grounding checks are enabled and the operator named
    an explicit ``--second-checker-plan``. The second checker is a distinct
    plan-quota vendor, built lazily through the escalator's factory so a
    metered/plan second check runs only when the first verdict is weak. The
    escalator derives the first-checker vendor to exclude from the runtime
    verdict, so it is not needed here.
    """
    if not enabled or not second_checker_plan:
        return None

    from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter
    from deepr.backends.waterfall import choose_plan_quota_backend
    from deepr.experts.grounding_escalation import GroundingEscalator
    from deepr.experts.maker_checker import CheckAssurance, make_grounding_checker

    choice = choose_plan_quota_backend(second_checker_plan)
    if not choice.is_plan_quota:
        raise ValueError(choice.reason)
    adapter = get_adapter(choice.plan_backend_id or second_checker_plan)
    if adapter is None:
        raise ValueError(f"unknown plan-quota backend {second_checker_plan!r}")
    second_vendor = adapter.backend_id
    second_model = second_checker_plan_model or adapter.backend_id

    def factory(vendor: str) -> GroundingChecker | None:
        if vendor != second_vendor:
            return None
        client = PlanQuotaChatClient(adapter, model=second_checker_plan_model, operation="plan_quota_grounding_check")
        return make_grounding_checker(
            client=client,
            checker_vendor=second_vendor,
            assurance=CheckAssurance.CROSS_VENDOR,
            model=second_model,
        )

    return GroundingEscalator(
        maker_vendor=maker_vendor,
        available_vendors=(second_vendor,),
        second_checker_factory=factory,
    )


def build_grounding_pair(
    *,
    enabled: bool,
    checker_plan: str | None,
    checker_plan_model: str | None,
    second_checker_plan: str | None,
    second_checker_plan_model: str | None,
    maker_vendor: str,
    default_client: Any | None = None,
    default_vendor: str | None = None,
    default_model: str | None = None,
) -> tuple[GroundingChecker | None, Any | None]:
    """Build the first checker and the optional second-checker escalator together.

    The two always share the same maker vendor and enable flag, so a caller's
    per-backend branch constructs them as one pair instead of repeating both
    calls. Returns ``(checker, escalator)`` where either may be ``None`` when
    that layer was not requested. Either builder may raise ``ValueError`` for an
    ill-formed backend request; the caller is expected to surface and exit on it.
    """
    checker = build_grounding_checker(
        enabled=enabled,
        checker_plan=checker_plan,
        checker_plan_model=checker_plan_model,
        maker_vendor=maker_vendor,
        default_client=default_client,
        default_vendor=default_vendor,
        default_model=default_model,
    )
    escalator = build_grounding_escalator(
        enabled=enabled,
        second_checker_plan=second_checker_plan,
        second_checker_plan_model=second_checker_plan_model,
        maker_vendor=maker_vendor,
    )
    return checker, escalator


def build_grounding_checker(
    *,
    enabled: bool,
    checker_plan: str | None,
    checker_plan_model: str | None,
    maker_vendor: str,
    default_client: Any | None = None,
    default_vendor: str | None = None,
    default_model: str | None = None,
) -> GroundingChecker | None:
    """Build an explicit grounding checker without introducing metered fallback."""

    if not enabled:
        return None

    if checker_plan:
        from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter
        from deepr.backends.waterfall import choose_plan_quota_backend

        choice = choose_plan_quota_backend(checker_plan)
        if not choice.is_plan_quota:
            raise ValueError(choice.reason)
        adapter = get_adapter(choice.plan_backend_id or checker_plan)
        if adapter is None:
            raise ValueError(f"unknown plan-quota backend {checker_plan!r}")
        client = PlanQuotaChatClient(adapter, model=checker_plan_model, operation="plan_quota_grounding_check")
        checker_vendor = adapter.backend_id
        checker_model = checker_plan_model or adapter.backend_id
    else:
        if default_client is None or not default_vendor or not default_model:
            raise ValueError("Grounding checks require --local, --plan, or --checker-plan.")
        client = default_client
        checker_vendor = default_vendor
        checker_model = default_model

    checker_choice = choose_checker_vendor(maker_vendor, [checker_vendor])
    return make_grounding_checker(
        client=client,
        checker_vendor=checker_choice.vendor,
        assurance=checker_choice.assurance,
        model=checker_model,
    )
