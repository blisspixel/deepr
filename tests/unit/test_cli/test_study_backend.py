"""Study capacity selection: prepaid plan first, local as the floor, never metered."""

from dataclasses import replace
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


@pytest.fixture
def synthetic_eligible_claude(monkeypatch):
    """Exercise dormant plan preference with a synthetic eligible adapter."""
    from deepr.backends.plan_quota import adapters

    adapter = replace(adapters.REGISTRY["claude"], execution_block_reason="", enabled_by_default=True)
    monkeypatch.setitem(adapters.REGISTRY, "claude", adapter)
    monkeypatch.setattr(adapters, "_ADAPTERS", (adapter,))


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
    def test_auto_prefers_synthetic_eligible_plan_over_local(self, monkeypatch, profile, synthetic_eligible_claude):
        """An eligible plan candidate takes precedence over local capacity."""
        _stub_plan(monkeypatch, works=True)
        _stub_local(monkeypatch)
        backend = build_study_backend(profile=profile)
        assert backend.capacity_source.startswith("plan:")

    def test_auto_falls_back_to_local_when_no_plan_is_usable(self, monkeypatch, profile, synthetic_eligible_claude):
        """An unavailable eligible plan candidate falls through to local."""
        _stub_plan(monkeypatch, works=False)
        _stub_local(monkeypatch)
        backend = build_study_backend(profile=profile)
        assert backend.capacity_source == "local:stub"

    def test_explicit_local_is_honoured_over_the_preference(self, monkeypatch, profile, synthetic_eligible_claude):
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

        Claude managed-policy hooks and other adapters' native tool permissions
        cannot be proven confined before dispatch. Capacity preference must
        preserve these refusals even when plan quota might remain.
        """
        preferred = _preferred_plan_backends()
        assert preferred == []
        for blocked in ("claude", "codex", "grok", "antigravity", "kiro", "opencode", "copilot"):
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

    with pytest.raises(StudyBackendError, match="8192-token context, 2048-token output ceiling"):
        await completion("Study this corpus")


@pytest.mark.asyncio
async def test_native_local_truncation_can_exhaust_context_before_output_ceiling():
    class Backend:
        async def complete(self, _request):
            return ExpertChatResult(
                message=SimpleNamespace(content=""),
                usage=SimpleNamespace(prompt_tokens=11598, completion_tokens=4786),
                stop_reason="length",
            )

    completion = _completion_from_native_ollama(Backend(), "fixture", max_tokens=16000, context_tokens=16384)
    with pytest.raises(StudyBackendError, match="observed 11598 input and 4786 generated tokens"):
        await completion("A large briefing")


def test_fit_metadata_fetch_keeps_only_reported_models():
    from deepr.cli.commands.semantic.study_backend import _kv_per_token_by_model

    info = {
        "general.architecture": "qwen35",
        "qwen35.block_count": 65,
        "qwen35.attention.head_count": 24,
        "qwen35.attention.head_count_kv": 4,
        "qwen35.attention.key_length": 256,
        "qwen35.attention.value_length": 256,
        "qwen35.full_attention_interval": 4,
    }

    class Response:
        def __init__(self, payload, status=200):
            self._payload, self._status = payload, status

        def raise_for_status(self):
            if self._status >= 400:
                raise RuntimeError("show failed")

        def json(self):
            return self._payload

    class Client:
        def __init__(self):
            self.calls = []

        def post(self, url, json):
            self.calls.append((url, json["model"]))
            if json["model"] == "broken:1b":
                return Response({}, status=500)
            if json["model"] == "bare:1b":
                return Response({"model_info": {}})
            return Response({"model_info": info})

    client = Client()
    tags = {"models": [{"name": "qwen3.8:27b"}, {"name": "broken:1b"}, {"name": "bare:1b"}, {"name": ""}]}
    assert _kv_per_token_by_model(client, "http://127.0.0.1:11434", tags) == {"qwen3.8:27b": 65_536}
    assert [model for _, model in client.calls] == ["qwen3.8:27b", "broken:1b", "bare:1b"]
    assert all(url == "http://127.0.0.1:11434/api/show" for url, _ in client.calls)


def test_legacy_study_backend_has_unknown_output_budget():
    backend = study_backend.StudyBackend(completion=lambda prompt: None, capacity_source="fixture", cost_note="fixture")
    assert backend.max_output_tokens is None


@pytest.mark.asyncio
async def test_local_backend_reports_exact_dispatched_output_budget(monkeypatch, profile):
    requests = []

    class NativeBackend:
        def __init__(self, **kwargs):
            pass

        async def complete(self, request):
            requests.append(request)
            return ExpertChatResult(message=SimpleNamespace(content="{}"), stop_reason="stop")

    monkeypatch.setattr(
        "deepr.backends.local.resolve_local_maintenance_model", lambda profile, explicit_model: explicit_model
    )
    monkeypatch.setattr("deepr.experts.investigation.ollama_backend.NativeOllamaInvestigationBackend", NativeBackend)
    backend = study_backend._build_local_backend(profile=profile, model="fixture", max_tokens=3072)

    await backend.completion("Read these sources")

    assert backend.max_output_tokens == requests[0].extra["max_tokens"] == 3072


@pytest.mark.asyncio
async def test_plan_requested_budget_remains_unknown_transport_ceiling(monkeypatch):
    from unittest.mock import AsyncMock

    from deepr.backends import plan_quota

    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(
        plan_quota, "get_adapter", lambda name: SimpleNamespace(backend_id="fixture", metered_at_margin=False)
    )
    monkeypatch.setattr(plan_quota, "PlanQuotaChatClient", lambda adapter, model: client)
    backend = study_backend._build_plan_backend(plan="fixture", plan_model="fixture-model", max_tokens=5120)

    await backend.completion("Read these sources")

    assert create.call_args.kwargs["max_tokens"] == 5120
    assert backend.max_output_tokens is None


def test_pooled_backend_reports_common_synthetic_member_budget(monkeypatch, profile):
    calls = []

    def build(**kwargs):
        calls.append(kwargs)
        return study_backend.StudyBackend(
            completion=lambda prompt: None,
            capacity_source=f"plan:{kwargs['plan']}",
            cost_note="fixture",
            max_output_tokens=kwargs["max_tokens"],
        )

    monkeypatch.setattr(study_backend, "build_study_backend", build)
    monkeypatch.setattr("deepr.backends.quota_headroom.read_headroom", lambda: {})
    backend = study_backend._build_pooled_backend(profile=profile, plans=["first", "second"], max_tokens=6144)

    assert backend.max_output_tokens == 6144
    assert [call["max_tokens"] for call in calls] == [6144, 6144]


def test_plan_pool_does_not_promote_requested_budget_to_ceiling(monkeypatch, profile):
    from deepr.backends import plan_quota

    monkeypatch.setattr("deepr.backends.quota_headroom.read_headroom", lambda: {})
    monkeypatch.setattr(
        plan_quota, "get_adapter", lambda name: SimpleNamespace(backend_id=name, metered_at_margin=False)
    )
    monkeypatch.setattr(plan_quota, "PlanQuotaChatClient", lambda adapter, model: object())

    backend = study_backend._build_pooled_backend(profile=profile, plans=["first", "second"], max_tokens=6144)

    assert backend.max_output_tokens is None
