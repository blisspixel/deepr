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
) -> None:
    if checker_plan and not check_grounding:
        raise ValueError("Use --check-grounding with --checker-plan.")
    if checker_plan_model and not checker_plan:
        raise ValueError("Use --checker-plan-model with --checker-plan.")


def absorber_kwargs(
    *,
    model: str,
    client: Any | None = None,
    grounding_checker: GroundingChecker | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": model}
    if client is not None:
        kwargs["client"] = client
    if grounding_checker is not None:
        kwargs["grounding_checker"] = grounding_checker
    return kwargs


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

    choice = choose_checker_vendor(maker_vendor, [checker_vendor])
    return make_grounding_checker(
        client=client,
        checker_vendor=choice.vendor,
        assurance=choice.assurance,
        model=checker_model,
    )
