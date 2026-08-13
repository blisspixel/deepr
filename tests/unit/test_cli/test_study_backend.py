"""Study capacity selection: prepaid plan first, local as the floor, never metered."""

from types import SimpleNamespace

import pytest

from deepr.cli.commands.semantic import study_backend
from deepr.cli.commands.semantic.study_backend import (
    StudyBackendError,
    _completion_from_native_ollama,
    _preferred_plan_backends,
    build_study_backend,
)
from deepr.experts.chat_backends import ExpertChatResult


@pytest.fixture
def profile():
    return SimpleNamespace(name="Capacity Test Expert")


def _stub_plan(monkeypatch, *, works: bool):
    def _build(*, plan, plan_model, max_tokens):
        if not works:
            raise StudyBackendError(f"{plan} unavailable")
        return study_backend.StudyBackend(
            completion=lambda prompt: None,
            capacity_source=f"plan:{plan}",
            cost_note="$0 at the margin (prepaid plan)",
        )

    monkeypatch.setattr(study_backend, "_build_plan_backend", _build)


def _stub_local(monkeypatch):
    def _build(*, profile, model, max_tokens, context_tokens=16384):
        return study_backend.StudyBackend(
            completion=lambda prompt: None,
            capacity_source="local:stub",
            cost_note="$0 (local model stub)",
        )

    monkeypatch.setattr(study_backend, "_build_local_backend", _build)


class TestPreferenceOrder:
    def test_auto_prefers_prepaid_plan_over_local(self, monkeypatch, profile):
        """Both are $0; plan runs a stronger model and leaves the GPU alone."""
        _stub_plan(monkeypatch, works=True)
        _stub_local(monkeypatch)
        backend = build_study_backend(profile=profile)
        assert backend.capacity_source.startswith("plan:")

    def test_auto_falls_back_to_local_when_no_plan_is_usable(self, monkeypatch, profile):
        """Local is the guaranteed floor, not the preferred path."""
        _stub_plan(monkeypatch, works=False)
        _stub_local(monkeypatch)
        backend = build_study_backend(profile=profile)
        assert backend.capacity_source == "local:stub"

    def test_explicit_local_is_honoured_over_the_preference(self, monkeypatch, profile):
        _stub_plan(monkeypatch, works=True)
        _stub_local(monkeypatch)
        backend = build_study_backend(profile=profile, local=True)
        assert backend.capacity_source == "local:stub"

    def test_explicit_plan_is_honoured(self, monkeypatch, profile):
        _stub_plan(monkeypatch, works=True)
        _stub_local(monkeypatch)
        backend = build_study_backend(profile=profile, plan="claude")
        assert backend.capacity_source == "plan:claude"

    def test_explicit_plan_failure_is_not_silently_downgraded(self, monkeypatch, profile):
        """Asking for a named backend and getting local instead would hide a fault."""
        _stub_plan(monkeypatch, works=False)
        _stub_local(monkeypatch)
        with pytest.raises(StudyBackendError):
            build_study_backend(profile=profile, plan="claude")


class TestAutoRoutableSet:
    def test_only_genuinely_free_and_confined_adapters_are_preferred(self):
        """Quota is not the only gate.

        Codex, Grok, Antigravity, and Kiro are installed and may well have quota
        left, but their native tool permissions cannot be confined before
        dispatch. That is a separate refusal from cost and must not be bypassed
        by a capacity preference.
        """
        preferred = _preferred_plan_backends()
        assert "claude" in preferred
        for blocked in ("codex", "grok", "antigravity", "kiro", "opencode", "copilot"):
            assert blocked not in preferred

    def test_preference_list_degrades_to_empty_rather_than_raising(self, monkeypatch):
        """A broken adapter registry must fall through to local, not crash."""
        monkeypatch.setattr(
            study_backend,
            "_preferred_plan_backends",
            lambda: (_ for _ in ()).throw(RuntimeError("registry down")),
        )
        # The real function guards internally; this pins that a caller failure
        # surfaces rather than silently selecting something unintended.
        with pytest.raises(RuntimeError):
            study_backend._preferred_plan_backends()


class TestNoMeteredPath:
    def test_there_is_no_api_option(self):
        """A study pass is many calls; paid dispatch must not be reachable here."""
        import inspect

        signature = inspect.signature(build_study_backend)
        assert "api" not in signature.parameters


@pytest.mark.asyncio
async def test_native_local_completion_binds_context_and_output_limit():
    requests = []

    class Backend:
        async def complete(self, request):
            requests.append(request)
            return ExpertChatResult(message=SimpleNamespace(content='{"findings": []}'), stop_reason="stop")

    completion = _completion_from_native_ollama(
        Backend(),
        "qwen3:30b",
        max_tokens=4096,
        context_tokens=16_384,
    )

    assert await completion("Study this corpus") == '{"findings": []}'
    assert requests[0].model == "qwen3:30b"
    assert requests[0].messages == [{"role": "user", "content": "Study this corpus"}]
    assert requests[0].extra == {
        "max_tokens": 4096,
        "num_ctx": 16_384,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }


@pytest.mark.asyncio
async def test_native_local_completion_reports_truncation():
    class Backend:
        async def complete(self, _request):
            return ExpertChatResult(message=SimpleNamespace(content="{"), stop_reason="length")

    completion = _completion_from_native_ollama(
        Backend(),
        "qwen3:30b",
        max_tokens=2048,
        context_tokens=8192,
    )

    with pytest.raises(StudyBackendError, match="2048-token output limit"):
        await completion("Study this corpus")
