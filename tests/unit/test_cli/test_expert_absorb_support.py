"""Tests for absorb backend selection + absorber construction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import deepr.backends.local as local_mod
import deepr.backends.plan_quota as plan_quota_mod
import deepr.backends.waterfall as waterfall_mod
import deepr.cli.commands.semantic.expert_absorb_support as absorb_support_mod
import deepr.experts.report_absorber as report_absorber_mod
from deepr.cli.commands.semantic.expert_absorb_support import (
    AbsorbBackend,
    AbsorbBackendError,
    build_absorb_backend,
)
from deepr.experts.grounding_escalation import GroundingEscalator


class _FakeAbsorber:
    """Records the kwargs the command would pass to the real ReportAbsorber."""

    def __init__(self, profile, **kwargs) -> None:
        self.profile = profile
        self.kwargs = kwargs


def _use_fake_absorber(monkeypatch):
    monkeypatch.setattr(report_absorber_mod, "ReportAbsorber", _FakeAbsorber)
    monkeypatch.setattr(report_absorber_mod, "ESTIMATED_EXTRACTION_COST", 0.05)


def test_metered_backend_builds_absorber_with_estimate(monkeypatch):
    _use_fake_absorber(monkeypatch)
    profile = SimpleNamespace(name="Expert")

    backend = build_absorb_backend(
        profile=profile,
        local=False,
        api=True,
        plan=None,
        plan_model=None,
        model="gpt-5-mini",
        run_grounding_checks=False,
        checker_plan=None,
        checker_plan_model=None,
        second_checker_plan=None,
        second_checker_plan_model=None,
        json_output=True,
    )

    assert isinstance(backend, AbsorbBackend)
    assert backend.cost_note == "~$0.05"
    assert isinstance(backend.absorber, _FakeAbsorber)
    # No grounding requested, so neither a checker nor an escalator is attached.
    assert "grounding_checker" not in backend.absorber.kwargs
    assert "grounding_escalator" not in backend.absorber.kwargs


def test_local_backend_without_model_raises_setup_error(monkeypatch):
    _use_fake_absorber(monkeypatch)
    monkeypatch.setattr(local_mod, "default_local_model", lambda: None)
    profile = SimpleNamespace(name="Expert")

    with pytest.raises(AbsorbBackendError, match="No local model available"):
        build_absorb_backend(
            profile=profile,
            local=True,
            api=False,
            plan=None,
            plan_model=None,
            model=None,
            run_grounding_checks=False,
            checker_plan=None,
            checker_plan_model=None,
            second_checker_plan=None,
            second_checker_plan_model=None,
            json_output=True,
        )


def test_local_backend_builds_zero_cost_absorber(monkeypatch):
    _use_fake_absorber(monkeypatch)
    sentinel_client = object()
    monkeypatch.setattr(local_mod, "default_local_model", lambda: "qwen-global")
    monkeypatch.setattr(local_mod, "ollama_chat_client", lambda: sentinel_client)
    profile = SimpleNamespace(name="Expert", provider="local", model="qwen-profile")

    backend = build_absorb_backend(
        profile=profile,
        local=True,
        api=False,
        plan=None,
        plan_model=None,
        model=None,
        run_grounding_checks=False,
        checker_plan=None,
        checker_plan_model=None,
        second_checker_plan=None,
        second_checker_plan_model=None,
        json_output=True,
    )

    assert backend.cost_note == "$0 (local model qwen-profile)"
    assert backend.absorber.kwargs["model"] == "qwen-profile"
    assert backend.absorber.kwargs["client"] is sentinel_client
    assert backend.absorber.kwargs["estimated_cost"] == 0.0


def test_plan_backend_rejects_non_plan_quota(monkeypatch):
    _use_fake_absorber(monkeypatch)
    monkeypatch.setattr(
        waterfall_mod,
        "choose_plan_quota_backend",
        lambda _bid, allow_metered_at_margin=False: SimpleNamespace(
            is_plan_quota=False, plan_backend_id=None, reason="codex requires paid-capacity acknowledgement"
        ),
    )
    profile = SimpleNamespace(name="Expert")

    with pytest.raises(AbsorbBackendError, match="paid-capacity acknowledgement"):
        build_absorb_backend(
            profile=profile,
            local=False,
            api=False,
            plan="codex",
            plan_model=None,
            model=None,
            run_grounding_checks=False,
            checker_plan=None,
            checker_plan_model=None,
            second_checker_plan=None,
            second_checker_plan_model=None,
            json_output=True,
        )


def test_metered_grounding_without_checker_plan_is_setup_error(monkeypatch):
    # A grounding request the metered path cannot build (no --checker-plan and
    # no local/plan default) is a user-facing setup failure, surfaced as
    # AbsorbBackendError so the command exits 2 before cost.
    _use_fake_absorber(monkeypatch)
    profile = SimpleNamespace(name="Expert")

    with pytest.raises(AbsorbBackendError, match="require --local, --plan, or --checker-plan"):
        build_absorb_backend(
            profile=profile,
            local=False,
            api=True,
            plan=None,
            plan_model=None,
            model="gpt-5-mini",
            run_grounding_checks=True,
            checker_plan=None,
            checker_plan_model=None,
            second_checker_plan=None,
            second_checker_plan_model=None,
            json_output=True,
        )


def test_unexpected_construction_valueerror_propagates_unconverted(monkeypatch):
    # An unrelated ValueError from provider/absorber construction must NOT be
    # relabeled a setup error; it propagates so the command surfaces it loudly
    # (exit 1) rather than as a clean exit-2 setup failure.
    _use_fake_absorber(monkeypatch)

    def boom():
        raise ValueError("ollama timeout env is not a number")

    monkeypatch.setattr(local_mod, "default_local_model", lambda: "qwen-local")
    monkeypatch.setattr(local_mod, "ollama_chat_client", boom)
    profile = SimpleNamespace(name="Expert")

    with pytest.raises(ValueError) as excinfo:
        build_absorb_backend(
            profile=profile,
            local=True,
            api=False,
            plan=None,
            plan_model=None,
            model=None,
            run_grounding_checks=False,
            checker_plan=None,
            checker_plan_model=None,
            second_checker_plan=None,
            second_checker_plan_model=None,
            json_output=True,
        )
    assert not isinstance(excinfo.value, AbsorbBackendError)


def test_plan_backend_wires_lazy_second_checker_escalator(monkeypatch):
    _use_fake_absorber(monkeypatch)
    built_clients = []

    plan_adapter = SimpleNamespace(backend_id="codex", metered_at_margin=False, tos_note="")
    kiro_adapter = SimpleNamespace(backend_id="kiro", metered_at_margin=False, tos_note="")
    claude_adapter = SimpleNamespace(backend_id="claude", metered_at_margin=False, tos_note="")
    adapters = {"codex": plan_adapter, "claude": claude_adapter, "kiro": kiro_adapter}

    def fake_choose(bid, allow_metered_at_margin=False):
        return SimpleNamespace(is_plan_quota=True, plan_backend_id=bid, reason=f"{bid} in plan mode")

    def fake_client(adapter, *, model=None, operation=None):
        built_clients.append(adapter.backend_id)
        return object()

    monkeypatch.setattr(waterfall_mod, "choose_plan_quota_backend", fake_choose)
    monkeypatch.setattr(plan_quota_mod, "get_adapter", lambda bid: adapters.get(bid))
    monkeypatch.setattr(plan_quota_mod, "PlanQuotaChatClient", fake_client)
    profile = SimpleNamespace(name="Expert")

    backend = build_absorb_backend(
        profile=profile,
        local=False,
        api=False,
        plan="codex",
        plan_model=None,
        model=None,
        run_grounding_checks=True,
        checker_plan="claude",
        checker_plan_model=None,
        second_checker_plan="kiro",
        second_checker_plan_model=None,
        json_output=True,
    )

    escalator = backend.absorber.kwargs["grounding_escalator"]
    assert isinstance(escalator, GroundingEscalator)
    assert escalator.maker_vendor == "codex"
    assert escalator.available_vendors == ("kiro",)
    # Cost bound: only the maker and first checker clients are built up front;
    # the kiro second checker stays unbuilt until a weak verdict escalates.
    assert built_clients == ["codex", "claude"]


def test_plan_backend_does_not_repeat_tos_note_already_in_selection_reason(monkeypatch):
    _use_fake_absorber(monkeypatch)
    tos_note = "Antigravity automation requires explicit operator opt-in."
    adapter = SimpleNamespace(backend_id="antigravity", metered_at_margin=False, tos_note=tos_note)
    warnings = []

    monkeypatch.setattr(
        waterfall_mod,
        "choose_plan_quota_backend",
        lambda _bid, allow_metered_at_margin=False: SimpleNamespace(
            is_plan_quota=True,
            plan_backend_id="antigravity",
            reason=f"Explicit plan selected. {tos_note}",
        ),
    )
    monkeypatch.setattr(plan_quota_mod, "get_adapter", lambda _bid: adapter)
    monkeypatch.setattr(plan_quota_mod, "PlanQuotaChatClient", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(absorb_support_mod, "print_warning", warnings.append)

    build_absorb_backend(
        profile=SimpleNamespace(name="Expert"),
        local=False,
        api=False,
        plan="antigravity",
        plan_model=None,
        model=None,
        run_grounding_checks=False,
        checker_plan=None,
        checker_plan_model=None,
        second_checker_plan=None,
        second_checker_plan_model=None,
        json_output=False,
    )

    assert warnings == []
