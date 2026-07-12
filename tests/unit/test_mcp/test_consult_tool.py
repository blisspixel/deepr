"""Tests for the deepr_consult_experts MCP tool - the harness-native consult path.

The council + consult core are tested elsewhere; here we exercise the MCP handler
(artifact shape, budget guard, error mapping) and registration, with the shared
``run_consult`` core monkeypatched so tests stay pure and $0.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from deepr.mcp.consult_tool import CONSULT_EXPERTS_INPUT_SCHEMA, consult_experts_tool
from deepr.mcp.server import DeeprMCPServer

_RESULT = {
    "perspectives": [
        {
            "expert_name": "A",
            "domain": "alpha",
            "response": "answer A",
            "confidence": 0.9,
            "cost": 0.01,
            "context": {"source": "belief_store", "selection": "query_overlap", "beliefs_included": 1},
        },
    ],
    "synthesis": "the synthesized answer",
    "agreements": ["both agree"],
    "disagreements": [],
    "requested_budget_usd": 1.0,
    "total_cost": 0.0212,
}


@pytest.fixture
def server():
    with (
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler", return_value=MagicMock()),
    ):
        yield DeeprMCPServer()


@pytest.fixture(autouse=True)
def consult_trace_path(monkeypatch, tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(path))
    return path


def test_consult_tool_registered(server):
    names = [t.name for t in server.registry.all_tools()]
    assert "deepr_consult_experts" in names


def test_consult_output_schema_exposes_completion_reason():
    from deepr.mcp.consult_tool import CONSULT_EXPERTS_OUTPUT_SCHEMA

    assert "synthesis_stop_reason" in CONSULT_EXPERTS_OUTPUT_SCHEMA["properties"]


@pytest.mark.asyncio
async def test_consult_returns_versioned_artifact(server, monkeypatch):
    async def fake(question, experts, max_experts, budget, **_kwargs):
        return _RESULT

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)
    out = await server.consult_experts(question="how do we harden absorb?", max_experts=2, budget=1.0)
    assert out["schema_version"] == "deepr-consult-v1"
    assert out["answer"] == "the synthesized answer"
    assert out["synthesis_status"] == "completed"
    assert out["synthesis_error_type"] == ""
    assert out["experts_consulted"] == ["A"]
    assert out["perspectives"][0]["context"]["selection"] == "query_overlap"
    assert out["cost_usd"] == 0.0212
    assert out["trace"]["schema_version"] == "deepr-consult-trace-v1"
    assert out["collaboration"]["schema_version"] == "deepr-expert-collaboration-v1"
    assert out["collaboration"]["task"]["consult_trace_id"] == out["trace"]["trace_id"]
    assert out["collaboration"]["evidence_packet"]["belief_store_perspective_count"] == 1


@pytest.mark.asyncio
async def test_consult_mcp_writes_trace(server, monkeypatch, consult_trace_path):
    async def resolve_local_model():
        return "qwen-local"

    monkeypatch.setattr("deepr.backends.local.default_local_model_async", resolve_local_model)
    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: object())

    async def fake(question, experts, max_experts, budget, **_kwargs):
        return {**_RESULT, "synthesis_status": "completed", "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)

    out = await server.consult_experts(
        question="q",
        experts=["A"],
        synthesis_backend="local",
        budget=0.0,
    )

    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    assert out["trace"]["trace_id"] == trace["trace_id"]
    assert trace["input"]["requested_experts"] == ["A"]
    assert trace["capacity"]["synthesis_backend"] == "local"
    assert trace["output"]["collaboration"] == out["collaboration"]
    assert trace["output"]["collaboration"]["task"]["consult_trace_id"] == trace["trace_id"]
    assert trace["output"]["collaboration"]["budget_capacity_contract"]["capacity"] == out["capacity"]
    assert trace["output"]["collaboration"]["budget_capacity_contract"]["metered_fallback_allowed"] is False


@pytest.mark.asyncio
async def test_consult_local_backend_disables_metered_fallback(server, monkeypatch):
    sentinel_client = object()
    captured: dict[str, object] = {}

    async def resolve_local_model():
        return "qwen-local"

    monkeypatch.setattr("deepr.backends.local.default_local_model_async", resolve_local_model)
    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: sentinel_client)

    async def fake(question, experts, max_experts, budget, **kwargs):
        captured.update(kwargs)
        return {**_RESULT, "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)

    out = await server.consult_experts(question="q", synthesis_backend="local", budget=0.0)

    assert captured["synthesis_client"] is sentinel_client
    assert captured["synthesis_model"] == "qwen-local"
    assert captured["synthesis_provider"] == "local"
    assert captured["allow_live_fallback"] is False
    assert out["capacity"]["live_metered_fallback"] is False
    assert out["capacity"]["synthesis_backend"] == "local"


@pytest.mark.asyncio
async def test_consult_plan_backend_vets_capacity_and_disables_metered_fallback(
    server, monkeypatch, consult_trace_path
):
    from deepr.backends.waterfall import BACKEND_PLAN_QUOTA, BackendChoice

    captured: dict[str, object] = {}

    class FakeAdapter:
        backend_id = "codex"
        tos_note = ""
        exe = "codex"
        needs_pty = False
        cost_model = type("CostModel", (), {"value": "prepaid"})()
        window_kind = "daily"
        unit_name = "request"

    class FakePlanClient:
        def __init__(self, adapter, *, model=None, operation=""):
            captured["adapter"] = adapter
            captured["plan_model"] = model
            captured["operation"] = operation

    monkeypatch.setattr(
        "deepr.backends.waterfall.choose_plan_quota_backend",
        lambda backend: BackendChoice(BACKEND_PLAN_QUOTA, None, "plan ok", plan_backend_id=backend),
    )
    monkeypatch.setattr("deepr.backends.plan_quota.get_adapter", lambda backend: FakeAdapter())
    monkeypatch.setattr("deepr.backends.plan_quota.PlanQuotaChatClient", FakePlanClient)

    async def fake(question, experts, max_experts, budget, **kwargs):
        captured.update(kwargs)
        return {**_RESULT, "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)

    out = await server.consult_experts(question="q", synthesis_backend="plan", plan="codex", plan_model="fast")

    assert isinstance(captured["synthesis_client"], FakePlanClient)
    assert captured["synthesis_model"] == "fast"
    assert captured["synthesis_provider"] == "plan_quota:codex"
    assert captured["allow_live_fallback"] is False
    assert captured["plan_model"] == "fast"
    assert captured["operation"] == "plan_quota_consult_synthesis"
    assert out["capacity"]["synthesis_backend"] == "plan"
    assert out["capacity"]["provider"] == "plan_quota:codex"
    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    assert trace["output"]["collaboration"] == out["collaboration"]
    assert trace["output"]["collaboration"]["budget_capacity_contract"]["capacity"] == out["capacity"]
    assert trace["output"]["collaboration"]["budget_capacity_contract"]["metered_fallback_allowed"] is False


@pytest.mark.asyncio
async def test_consult_api_provider_and_model_pass_to_shared_core(server, monkeypatch):
    captured: dict[str, object] = {}

    async def fake(question, experts, max_experts, budget, **kwargs):
        captured["budget"] = budget
        captured.update(kwargs)
        return {**_RESULT, "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)

    out = await server.consult_experts(
        question="q",
        synthesis_backend="api",
        provider="anthropic",
        model="claude-sonnet-4-6",
        budget=1.0,
    )

    assert captured["budget"] == 1.0
    assert captured["synthesis_provider"] == "anthropic"
    assert captured["synthesis_model"] == "claude-sonnet-4-6"
    assert captured["allow_live_fallback"] is False
    assert out["capacity"]["synthesis_backend"] == "api"
    assert out["capacity"]["provider"] == "anthropic"
    assert out["capacity"]["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_consult_rejects_api_provider_for_owned_capacity(server):
    out = await server.consult_experts(
        question="q",
        synthesis_backend="local",
        provider="anthropic",
        budget=0.0,
    )
    assert out["error_code"] == "INVALID_BACKEND"
    assert "provider and model are only valid" in out["message"]


@pytest.mark.asyncio
async def test_consult_rejects_nonpositive_budget(server):
    out = await server.consult_experts(question="q", budget=0)
    assert "INVALID_BUDGET" in str(out)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 11, True, 1.5])
async def test_consult_rejects_invalid_expert_limit(server, value):
    out = await server.consult_experts(question="q", max_experts=value, budget=1.0)

    assert out["error_code"] == "INVALID_EXPERT_LIMIT"


@pytest.mark.asyncio
async def test_consult_rejects_oversized_explicit_roster(server):
    out = await server.consult_experts(
        question="q",
        experts=[f"Expert {index}" for index in range(11)],
        budget=1.0,
    )

    assert out["error_code"] == "INVALID_EXPERT_LIMIT"


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [float("nan"), float("inf"), float("-inf")])
async def test_consult_rejects_nonfinite_budget(server, budget):
    out = await server.consult_experts(
        question="q",
        synthesis_backend="local",
        budget=budget,
    )

    assert out["error_code"] == "INVALID_BUDGET"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 21_601, True])
async def test_consult_rejects_invalid_elapsed_limit(server, value):
    out = await server.consult_experts(
        question="q",
        synthesis_backend="local",
        local_model="fixture-local",
        budget=0.0,
        max_elapsed_seconds=value,
    )

    assert out["error_code"] == "INVALID_ELAPSED_LIMIT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "error_code"),
    [
        ({"question": 1}, "INVALID_QUESTION"),
        ({"synthesis_backend": 1}, "INVALID_BACKEND"),
        ({"budget": "1.0"}, "INVALID_BUDGET"),
        ({"max_elapsed_seconds": []}, "INVALID_ELAPSED_LIMIT"),
        ({"experts": "Expert A"}, "INVALID_EXPERT_LIMIT"),
        ({"experts": ["Expert A", 2]}, "INVALID_EXPERT_LIMIT"),
        ({"provider": 2}, "INVALID_BACKEND"),
        ({"model": {}}, "INVALID_BACKEND"),
        ({"synthesis_backend": "plan", "plan": 3}, "INVALID_BACKEND"),
        ({"synthesis_backend": "local", "local_model": []}, "INVALID_BACKEND"),
        ({"synthesis_backend": "plan", "plan": "codex", "plan_model": []}, "INVALID_BACKEND"),
    ],
)
async def test_consult_direct_call_rejects_malformed_runtime_types(arguments, error_code):
    out = await consult_experts_tool(**{"question": "q", **arguments})

    assert out["error_code"] == error_code
    assert out["category"] == "internal"
    assert out["retryable"] is False


@pytest.mark.asyncio
async def test_consult_failure_mapped_to_error(server, monkeypatch, consult_trace_path):
    async def boom(*args, **kwargs):
        raise ValueError("council down")

    monkeypatch.setattr("deepr.experts.consult.run_consult", boom)
    out = await server.consult_experts(question="q", budget=1.0)
    assert "CONSULT_FAILED" in str(out)
    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    assert trace["status"] == "failed"
    assert trace["failure"]["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_consult_post_dispatch_elapsed_limit_is_not_retryable_and_exposes_trace_id(server, monkeypatch):
    from deepr.experts.consult_transaction import ConsultElapsedLimitError

    async def elapsed_after_dispatch(**_kwargs):
        raise ConsultElapsedLimitError("consult_post_dispatch_elapsed", 1.0, retryable=False)

    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", elapsed_after_dispatch)
    out = await server.consult_experts(question="q", synthesis_backend="local", budget=0.0)

    assert out["error_code"] == "CONSULT_ELAPSED_LIMIT"
    assert out["retryable"] is False
    assert out["trace_id"] == "consult_post_dispatch_elapsed"


@pytest.mark.asyncio
async def test_consult_pre_dispatch_elapsed_limit_honors_retryable_value(server, monkeypatch):
    from deepr.experts.consult_transaction import ConsultElapsedLimitError

    async def elapsed_before_dispatch(**_kwargs):
        raise ConsultElapsedLimitError("consult_pre_dispatch_elapsed", 1.0, retryable=True)

    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", elapsed_before_dispatch)
    out = await server.consult_experts(question="q", synthesis_backend="local", budget=0.0)

    assert out["error_code"] == "CONSULT_ELAPSED_LIMIT"
    assert out["retryable"] is True
    assert out["trace_id"] == "consult_pre_dispatch_elapsed"


@pytest.mark.asyncio
async def test_consult_storage_lock_timeout_is_retryable_and_exposes_trace_id(server, monkeypatch):
    from deepr.experts.consult_transaction import ConsultStorageLockTimeoutError

    async def storage_busy(**_kwargs):
        raise ConsultStorageLockTimeoutError("consult_storage_busy", r"C:\Users\private\trace.lock")

    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", storage_busy)
    out = await server.consult_experts(question="q", budget=1.0)

    assert out["error_code"] == "CONSULT_STORAGE_LOCK_TIMEOUT"
    assert out["retryable"] is True
    assert out["trace_id"] == "consult_storage_busy"
    assert "C:\\Users\\private" not in out["message"]


@pytest.mark.asyncio
async def test_consult_post_work_storage_timeout_honors_nonretryable_value(server, monkeypatch):
    from deepr.experts.consult_transaction import ConsultStorageLockTimeoutError

    async def storage_busy(**_kwargs):
        raise ConsultStorageLockTimeoutError(
            "consult_post_work_busy",
            r"C:\Users\private\trace.lock",
            retryable=False,
        )

    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", storage_busy)
    out = await server.consult_experts(question="q", budget=1.0)

    assert out["error_code"] == "CONSULT_STORAGE_LOCK_TIMEOUT"
    assert out["retryable"] is False
    assert out["trace_id"] == "consult_post_work_busy"
    assert "C:\\Users\\private" not in out["message"]


@pytest.mark.asyncio
async def test_consult_storage_io_error_uses_distinct_path_safe_code(server, monkeypatch):
    from deepr.experts.consult_transaction import ConsultStorageIOError

    async def storage_failed(**_kwargs):
        raise ConsultStorageIOError(
            "consult_storage_io",
            r"C:\Users\private\trace.jsonl",
            retryable=False,
            partial_write_possible=True,
        )

    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", storage_failed)
    out = await server.consult_experts(question="q", budget=1.0)

    assert out["error_code"] == "CONSULT_STORAGE_IO_ERROR"
    assert out["retryable"] is False
    assert out["trace_id"] == "consult_storage_io"
    assert "C:\\Users\\private" not in out["message"]


def test_consult_elapsed_schema_describes_cancellable_checkpoint_contract():
    description = CONSULT_EXPERTS_INPUT_SCHEMA["properties"]["max_elapsed_seconds"]["description"]

    assert "Hard wall-clock" not in description
    assert "cancellable consult work" in description
    assert "Durable writes are awaited off the event loop" in description
    assert "lock waits are bounded separately" in description


@pytest.mark.asyncio
async def test_consult_unexpected_runtime_failure_is_structured(server, monkeypatch):
    async def boom(*_args, **_kwargs):
        raise RuntimeError("unexpected council failure")

    monkeypatch.setattr("deepr.experts.consult.run_consult", boom)
    out = await server.consult_experts(question="q", budget=1.0)

    assert out["error_code"] == "CONSULT_FAILED"
    assert out["trace_id"].startswith("consult_")
    assert "unexpected council failure" in out["message"]
