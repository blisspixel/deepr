"""Tests for explicit grounding-checker CLI support."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import deepr.backends.plan_quota as plan_quota_mod
import deepr.backends.waterfall as waterfall_mod
from deepr.cli.commands.semantic.grounding_support import (
    absorber_kwargs,
    build_grounding_checker,
    build_grounding_escalator,
    build_grounding_pair,
    validate_grounding_flags,
)
from deepr.experts.grounding_escalation import GroundingEscalator


class _FakeClient:
    def __init__(self) -> None:
        self.calls = []

        async def _create(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="SUPPORTED\nDirect."))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


def test_validate_grounding_flags_rejects_checker_plan_without_enable():
    with pytest.raises(ValueError, match="--check-grounding"):
        validate_grounding_flags(check_grounding=False, checker_plan="codex", checker_plan_model=None)


def test_absorber_kwargs_omits_optional_values():
    assert absorber_kwargs(model="m") == {"model": "m"}


async def test_default_grounding_checker_uses_same_vendor_fresh_context():
    client = _FakeClient()
    checker = build_grounding_checker(
        enabled=True,
        checker_plan=None,
        checker_plan_model=None,
        maker_vendor="local",
        default_client=client,
        default_vendor="local",
        default_model="qwen-local",
    )

    assert checker is not None
    verdict = await checker("claim", "evidence")

    assert verdict.supported is True
    assert verdict.assurance.value == "same_vendor_fresh_context"
    assert client.calls[0]["model"] == "qwen-local"


def test_grounding_checker_requires_default_or_plan():
    with pytest.raises(ValueError, match="--local, --plan, or --checker-plan"):
        build_grounding_checker(
            enabled=True,
            checker_plan=None,
            checker_plan_model=None,
            maker_vendor="api_metered",
        )


def test_validate_second_checker_requires_grounding_enabled():
    with pytest.raises(ValueError, match="--check-grounding"):
        validate_grounding_flags(
            check_grounding=False,
            checker_plan=None,
            checker_plan_model=None,
            second_checker_plan="claude",
        )


def test_validate_second_checker_requires_first_checker():
    with pytest.raises(ValueError, match="--second-checker-plan with --checker-plan"):
        validate_grounding_flags(
            check_grounding=True,
            checker_plan=None,
            checker_plan_model=None,
            second_checker_plan="claude",
        )


def test_validate_second_checker_must_differ_from_first():
    with pytest.raises(ValueError, match="must differ"):
        validate_grounding_flags(
            check_grounding=True,
            checker_plan="codex",
            checker_plan_model=None,
            second_checker_plan="codex",
        )


def test_validate_second_checker_model_requires_second_plan():
    with pytest.raises(ValueError, match="--second-checker-plan-model"):
        validate_grounding_flags(
            check_grounding=True,
            checker_plan="codex",
            checker_plan_model=None,
            second_checker_plan=None,
            second_checker_plan_model="claude-opus",
        )


def test_validate_accepts_independent_second_checker():
    # A complete, well-formed second-checker request raises nothing.
    validate_grounding_flags(
        check_grounding=True,
        checker_plan="codex",
        checker_plan_model=None,
        second_checker_plan="claude",
        second_checker_plan_model="claude-opus",
    )


def test_build_escalator_none_when_disabled():
    assert (
        build_grounding_escalator(
            enabled=False,
            second_checker_plan="claude",
            second_checker_plan_model=None,
            maker_vendor="local",
        )
        is None
    )


def test_build_escalator_none_without_second_plan():
    assert (
        build_grounding_escalator(
            enabled=True,
            second_checker_plan=None,
            second_checker_plan_model=None,
            maker_vendor="local",
        )
        is None
    )


class _RecordingPlanClient:
    """Fake PlanQuotaChatClient that records construction without any I/O."""

    def __init__(self, adapter, *, model=None, operation=None) -> None:
        self.adapter = adapter
        self.model = model
        self.operation = operation


def _patch_plan_quota(monkeypatch, *, backend_id="claude", is_plan_quota=True, reason="ok"):
    adapter = SimpleNamespace(backend_id=backend_id)
    choice = SimpleNamespace(is_plan_quota=is_plan_quota, plan_backend_id=backend_id, reason=reason)
    monkeypatch.setattr(waterfall_mod, "choose_plan_quota_backend", lambda _bid: choice)
    monkeypatch.setattr(plan_quota_mod, "get_adapter", lambda _bid: adapter)
    monkeypatch.setattr(plan_quota_mod, "PlanQuotaChatClient", _RecordingPlanClient)
    return adapter


def test_build_escalator_builds_bounded_second_vendor(monkeypatch):
    _patch_plan_quota(monkeypatch, backend_id="claude")

    escalator = build_grounding_escalator(
        enabled=True,
        second_checker_plan="claude",
        second_checker_plan_model="claude-opus",
        maker_vendor="local",
    )

    assert isinstance(escalator, GroundingEscalator)
    assert escalator.maker_vendor == "local"
    # Exactly one available vendor: the named second checker, so the escalator
    # can only ever reach for that distinct third opinion.
    assert escalator.available_vendors == ("claude",)

    # The factory is the spend gate: it yields a checker only for the second
    # vendor and refuses any other vendor request.
    assert escalator.second_checker_factory("codex") is None
    checker = escalator.second_checker_factory("claude")
    assert checker is not None


def test_build_escalator_factory_threads_plan_operation(monkeypatch):
    captured: dict[str, object] = {}

    class _Capture(_RecordingPlanClient):
        def __init__(self, adapter, *, model=None, operation=None) -> None:
            super().__init__(adapter, model=model, operation=operation)
            captured["model"] = model
            captured["operation"] = operation

    adapter = SimpleNamespace(backend_id="claude")
    choice = SimpleNamespace(is_plan_quota=True, plan_backend_id="claude", reason="ok")
    monkeypatch.setattr(waterfall_mod, "choose_plan_quota_backend", lambda _bid: choice)
    monkeypatch.setattr(plan_quota_mod, "get_adapter", lambda _bid: adapter)
    monkeypatch.setattr(plan_quota_mod, "PlanQuotaChatClient", _Capture)

    escalator = build_grounding_escalator(
        enabled=True,
        second_checker_plan="claude",
        second_checker_plan_model="claude-opus",
        maker_vendor="api_metered",
    )
    assert escalator is not None
    # Building the checker constructs the plan client under the grounding-check
    # operation so its spend is accounted against the right budget line.
    assert escalator.second_checker_factory("claude") is not None
    assert captured["operation"] == "plan_quota_grounding_check"
    assert captured["model"] == "claude-opus"


def test_build_escalator_rejects_non_plan_backend(monkeypatch):
    _patch_plan_quota(monkeypatch, is_plan_quota=False, reason="codex is not a plan-quota backend")

    with pytest.raises(ValueError, match="not a plan-quota backend"):
        build_grounding_escalator(
            enabled=True,
            second_checker_plan="codex",
            second_checker_plan_model=None,
            maker_vendor="local",
        )


def test_build_grounding_pair_none_when_disabled():
    checker, escalator = build_grounding_pair(
        enabled=False,
        checker_plan=None,
        checker_plan_model=None,
        second_checker_plan="claude",
        second_checker_plan_model=None,
        maker_vendor="local",
        default_client=_FakeClient(),
        default_vendor="local",
        default_model="qwen-local",
    )
    assert checker is None
    assert escalator is None


def test_build_grounding_pair_returns_checker_and_escalator(monkeypatch):
    _patch_plan_quota(monkeypatch, backend_id="claude")

    checker, escalator = build_grounding_pair(
        enabled=True,
        checker_plan=None,
        checker_plan_model=None,
        second_checker_plan="claude",
        second_checker_plan_model=None,
        maker_vendor="local",
        default_client=_FakeClient(),
        default_vendor="local",
        default_model="qwen-local",
    )
    # The first checker uses the injected local default; the escalator carries
    # the distinct second vendor built lazily behind its factory.
    assert callable(checker)
    assert isinstance(escalator, GroundingEscalator)
    assert escalator.available_vendors == ("claude",)
