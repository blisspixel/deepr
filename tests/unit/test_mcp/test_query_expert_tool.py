"""Focused tests for ``deepr_query_expert`` read-only backend helpers."""

from types import SimpleNamespace

from deepr.experts.semantic_model_gate import _mark_zero_dollar_client
from deepr.mcp.query_expert_tool import QUERY_EXPERT_INPUT_SCHEMA, _build_readonly_query_backend


def test_build_readonly_query_backend_uses_local_ollama_client(monkeypatch):
    from deepr.backends import local as local_backend

    plan_description = QUERY_EXPERT_INPUT_SCHEMA["properties"]["plan"]["description"]
    assert "Claude is the current executable adapter" in plan_description
    assert "Codex" not in plan_description

    client = _mark_zero_dollar_client(SimpleNamespace(), capacity_source="local")
    monkeypatch.setattr(local_backend, "default_local_model", lambda: "mistral")
    monkeypatch.setattr(local_backend, "ollama_chat_client", lambda: client)
    monkeypatch.setattr(local_backend, "_KEEP_ALIVE", "45m")

    backend = _build_readonly_query_backend("local", local_model=None, plan=None, plan_model=None)

    assert backend.provider == "local"
    assert backend.model == "mistral"
    assert backend.client is client
    assert backend.keep_alive == "45m"


def test_build_readonly_query_backend_uses_explicit_local_model(monkeypatch):
    from deepr.backends import local as local_backend

    client = _mark_zero_dollar_client(SimpleNamespace(), capacity_source="local")
    monkeypatch.setattr(local_backend, "default_local_model", lambda: "should-not-be-used")
    monkeypatch.setattr(local_backend, "ollama_chat_client", lambda: client)

    backend = _build_readonly_query_backend("local", local_model="llama3.1", plan=None, plan_model=None)

    assert backend.provider == "local"
    assert backend.model == "llama3.1"
    assert backend.client is client


def test_build_readonly_query_backend_uses_plan_quota_chat_client(monkeypatch):
    from deepr.backends import plan_quota, waterfall

    captured: dict[str, object] = {}
    adapter = SimpleNamespace(backend_id="claude")

    class FakePlanQuotaChatClient:
        def __init__(self, adapter_arg, *, model, operation):
            captured["adapter"] = adapter_arg
            captured["model"] = model
            captured["operation"] = operation
            _mark_zero_dollar_client(self, capacity_source=f"plan_quota:{adapter_arg.backend_id}")

    monkeypatch.setattr(
        waterfall,
        "choose_plan_quota_backend",
        lambda backend_id: SimpleNamespace(is_plan_quota=True, plan_backend_id=backend_id, reason="ready"),
    )
    monkeypatch.setattr(plan_quota, "get_adapter", lambda backend_id: adapter if backend_id == "claude" else None)
    monkeypatch.setattr(plan_quota, "PlanQuotaChatClient", FakePlanQuotaChatClient)

    backend = _build_readonly_query_backend("plan", local_model=None, plan="claude", plan_model="sonnet")

    assert backend.provider == "plan_quota:claude"
    assert backend.model == "sonnet"
    assert backend.backend_id == "claude"
    assert captured == {
        "adapter": adapter,
        "model": "sonnet",
        "operation": "plan_quota_query_expert",
    }
