"""Tests for `deepr expert consult` - the first-class team-consultation verb.

The council itself is tested elsewhere; here we exercise the command layer
(artifact shaping, --json, exit codes, arg passing) with the council monkeypatched
so tests stay pure and $0.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from click.testing import CliRunner

import deepr.cli.commands.semantic.expert_consult as mod
from deepr.cli.commands.semantic.expert_consult import build_consult_payload, expert_consult


@pytest.fixture(autouse=True)
def consult_trace_path(monkeypatch, tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(path))
    return path


def _result(**over):
    base = {
        "query": "q",
        "perspectives": [
            {
                "expert_name": "A",
                "domain": "alpha",
                "response": "answer from A",
                "confidence": 0.9,
                "cost": 0.01,
                "context": {
                    "source": "belief_store",
                    "selection": "query_overlap",
                    "beliefs_available": 4,
                    "beliefs_included": 2,
                    "matched_terms": ["alpha"],
                },
            },
            {"expert_name": "B", "domain": "beta", "response": "answer from B", "confidence": 0.8, "cost": 0.01},
        ],
        "synthesis": "the synthesized answer",
        "agreements": ["both agree X"],
        "disagreements": ["they differ on Y"],
        "requested_budget_usd": 1.5,
        "total_cost": 0.0123,
    }
    base.update(over)
    return base


def _patch(monkeypatch, result):
    async def fake(question, experts, max_experts, budget, **_kwargs):
        return result

    monkeypatch.setattr(mod, "run_consult", fake)


def test_consult_registered_on_expert_group():
    from deepr.cli.commands.semantic.experts import expert

    assert "consult" in expert.commands


def test_build_payload_shape():
    p = build_consult_payload("q", _result())
    assert p["schema_version"] == "deepr-consult-v1"
    assert p["kind"] == "deepr.expert.consult"
    assert p["answer"] == "the synthesized answer"
    assert p["experts_consulted"] == ["A", "B"]
    assert p["perspectives"][0]["confidence"] == 0.9
    assert p["perspectives"][0]["context"]["source"] == "belief_store"
    assert "context" not in p["perspectives"][1]
    assert p["agreements"] == ["both agree X"]
    assert p["cost_usd"] == 0.0123
    assert p["contract"]["consultation_mode"] == "one_shot_stored_context_synthesis"
    assert p["contract"]["expert_generation_calls"] == 0
    assert p["contract"]["experts_exchange_turns"] is False
    assert p["contract"]["writes_graph"] is False
    assert p["collaboration"]["schema_version"] == "deepr-expert-collaboration-v1"
    assert p["collaboration"]["roster"][0]["role"] == "domain_perspective"
    assert p["collaboration"]["dissent_handling"]["dissent_preserved"] is True
    assert p["collaboration"]["budget_capacity_contract"]["requested_budget_usd"] == 1.5
    assert p["collaboration"]["interaction"]["peer_turns"] == 0
    assert p["collaboration"]["learning_boundary"]["discussion_is_evidence"] is False


def test_consult_json_emits_versioned_artifact(monkeypatch):
    _patch(monkeypatch, _result())
    result = CliRunner().invoke(expert_consult, ["q", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["schema_version"] == "deepr-consult-v1"
    assert parsed["answer"] == "the synthesized answer"
    assert parsed["cost_usd"] == 0.0123
    assert parsed["trace"]["schema_version"] == "deepr-consult-trace-v1"
    assert parsed["collaboration"]["task"]["consult_trace_id"] == parsed["trace"]["trace_id"]
    assert parsed["collaboration"]["budget_capacity_contract"]["capacity"]["synthesis_backend"] == "api"
    assert parsed["collaboration"]["budget_capacity_contract"]["total_spend_ceiling_usd"] == 1.5
    assert parsed["collaboration"]["budget_capacity_contract"]["metered_synthesis_ceiling_usd"] == 0.15


def test_consult_writes_replayable_trace(monkeypatch, consult_trace_path):
    _patch(monkeypatch, _result())

    result = CliRunner().invoke(expert_consult, ["q", "--json"])

    assert result.exit_code == 0
    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    parsed = json.loads(result.output)
    assert parsed["trace"]["trace_id"] == trace["trace_id"]
    assert trace["input"]["question"] == "q"
    assert trace["context_packet"]["selected"][0]["context"]["source"] == "belief_store"
    assert trace["capacity"]["synthesis_backend"] == "api"
    assert trace["output"]["collaboration"] == parsed["collaboration"]
    assert trace["output"]["collaboration"]["task"]["consult_trace_id"] == trace["trace_id"]
    assert trace["output"]["collaboration"]["budget_capacity_contract"]["capacity"] == parsed["capacity"]
    assert trace["output"]["collaboration"]["budget_capacity_contract"]["metered_fallback_allowed"] is False


def test_consult_human_render(monkeypatch):
    _patch(monkeypatch, _result())
    result = CliRunner().invoke(expert_consult, ["q", "-y"])
    assert result.exit_code == 0
    assert "Consult trace: consult_" in result.output
    assert "Synthesis" in result.output
    assert "the synthesized answer" in result.output
    assert "Disagreements" in result.output
    assert "one-shot stored-context council; experts do not exchange turns" in result.output
    assert "Knowledge writes: none" in result.output


def test_consult_output_path_explicitly_writes_full_artifact(monkeypatch, tmp_path):
    _patch(monkeypatch, _result())
    output = tmp_path / "council.json"

    result = CliRunner().invoke(expert_consult, ["q", "--output", str(output), "-y"])

    assert result.exit_code == 0, result.output
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema_version"] == "deepr-consult-v1"
    assert saved["trace"]["trace_id"].startswith("consult_")
    assert saved["contract"]["writes_expert_state"] is False
    assert f"Wrote consult artifact: {output}" in result.output


def test_consult_truncated_synthesis_emits_artifact_and_exits_nonzero(monkeypatch, consult_trace_path):
    _patch(
        monkeypatch,
        _result(
            synthesis="partial answer",
            synthesis_status="truncated",
            synthesis_error_type="OutputLimit",
            synthesis_stop_reason="length",
        ),
    )

    result = CliRunner().invoke(expert_consult, ["q", "--json"])

    assert result.exit_code == 1
    parsed = json.loads(result.output)
    assert parsed["answer"] == "partial answer"
    assert parsed["synthesis_status"] == "truncated"
    assert parsed["synthesis_stop_reason"] == "length"
    assert parsed["trace"]["status"] == "failed"
    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    assert trace["status"] == "failed"
    assert trace["output"]["collaboration"] == parsed["collaboration"]
    assert trace["output"]["collaboration"]["task"]["shared_task_trace_id"] == trace["trace_id"]


def test_consult_trace_records_effective_explicit_roster_size(monkeypatch, consult_trace_path):
    _patch(monkeypatch, _result())

    result = CliRunner().invoke(
        expert_consult,
        ["q", "-e", "A", "-e", "B", "-e", "C", "-e", "D", "--budget", "1", "--json"],
    )

    assert result.exit_code == 0
    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    assert trace["input"]["selection_mode"] == "explicit"
    assert trace["input"]["requested_max_experts"] == 3
    assert trace["input"]["max_experts"] == 4


def test_consult_no_experts_exits_2(monkeypatch):
    _patch(monkeypatch, _result(perspectives=[], synthesis="No experts available for this query."))
    result = CliRunner().invoke(expert_consult, ["q", "-y"])
    assert result.exit_code == 2


def test_api_budget_must_be_positive():
    result = CliRunner().invoke(expert_consult, ["q", "--budget", "0", "-y"])
    assert result.exit_code == 2
    assert "positive value" in " ".join(result.output.split())


@pytest.mark.parametrize("value", ["0", "11"])
def test_consult_rejects_invalid_expert_limit(value):
    result = CliRunner().invoke(expert_consult, ["q", "--max-experts", value, "--json"])

    assert result.exit_code == 2
    assert "Invalid value for '--max-experts'" in result.output


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_consult_rejects_nonfinite_budget(value):
    result = CliRunner().invoke(expert_consult, ["q", "--budget", value, "--local", "--json"])

    assert result.exit_code == 2
    assert "--budget must be finite" in result.output


@pytest.mark.parametrize("value", ["0", "nan", "inf", "21601"])
def test_consult_rejects_invalid_elapsed_ceiling(value):
    result = CliRunner().invoke(
        expert_consult,
        ["q", "--local", "--local-model", "fixture-local", "--max-elapsed-seconds", value, "--json"],
    )

    assert result.exit_code == 2
    assert "--max-elapsed-seconds must be finite" in result.output


def test_consult_elapsed_limit_is_recorded(monkeypatch, consult_trace_path):
    async def blocked(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(mod, "run_consult", blocked)
    result = CliRunner().invoke(
        expert_consult,
        [
            "q",
            "--local",
            "--local-model",
            "fixture-local",
            "--max-elapsed-seconds",
            "0.02",
            "-y",
        ],
    )

    assert result.exit_code == 1
    assert "elapsed-time ceiling" in result.output
    lifecycle_path = consult_trace_path.parent / "consult_lifecycle_events.jsonl"
    events = [json.loads(line) for line in lifecycle_path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["state"] == "failed"
    assert events[-1]["reason_code"] == "elapsed_limit"


def test_consult_storage_lock_timeout_is_retryable(monkeypatch):
    from deepr.experts.consult_transaction import ConsultStorageLockTimeoutError

    async def storage_busy(**_kwargs):
        raise ConsultStorageLockTimeoutError("consult_storage_busy", "trace lock busy")

    monkeypatch.setattr(mod, "execute_consult_transaction", storage_busy)
    result = CliRunner().invoke(expert_consult, ["q", "-y"])

    assert result.exit_code == 1
    assert "storage failed; retry safely" in result.output


def test_consult_post_work_storage_timeout_is_not_presented_as_retryable(monkeypatch):
    from deepr.experts.consult_transaction import ConsultStorageLockTimeoutError

    async def storage_busy(**_kwargs):
        raise ConsultStorageLockTimeoutError("consult_post_work_busy", "trace lock busy", retryable=False)

    monkeypatch.setattr(mod, "execute_consult_transaction", storage_busy)
    result = CliRunner().invoke(expert_consult, ["q", "-y"])

    assert result.exit_code == 1
    assert "do not retry the full consultation" in result.output
    assert "retry safely" not in result.output


def test_consult_help_describes_cancellable_checkpoint_ceiling():
    result = CliRunner().invoke(expert_consult, ["--help"])

    assert result.exit_code == 0
    assert "Hard wall-clock" not in result.output
    assert "Cumulative ceiling for cancellable" in result.output
    assert "Durable writes are" in result.output
    assert "awaited off the event loop" in result.output
    assert "lock waits are" in result.output
    assert "bounded separately" in result.output


def test_failure_surfaced_not_silent(monkeypatch, consult_trace_path):
    async def boom(*a, **k):
        raise RuntimeError("council down")

    monkeypatch.setattr(mod, "run_consult", boom)
    result = CliRunner().invoke(expert_consult, ["q", "-y"])
    assert result.exit_code == 1
    assert "Consultation failed" in result.output
    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    assert trace["status"] == "failed"
    assert trace["failure"]["error_type"] == "RuntimeError"


def test_explicit_experts_and_budget_passed_through(monkeypatch):
    captured = {}

    async def fake(question, experts, max_experts, budget, **_kwargs):
        captured["experts"] = experts
        captured["budget"] = budget
        return _result()

    monkeypatch.setattr(mod, "run_consult", fake)
    result = CliRunner().invoke(expert_consult, ["q", "-e", "A", "-e", "B", "-b", "1.5", "--json"])
    assert result.exit_code == 0
    assert captured["experts"] == ["A", "B"]
    assert captured["budget"] == 1.5


def test_consult_local_synthesis_passes_client_and_disables_live_fallback(monkeypatch):
    sentinel_client = object()
    captured = {}

    async def resolve_local_model():
        return "qwen-local"

    monkeypatch.setattr("deepr.backends.local.default_local_model_async", resolve_local_model)
    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: sentinel_client)

    async def fake(question, experts, max_experts, budget, **kwargs):
        captured["budget"] = budget
        captured.update(kwargs)
        return _result(total_cost=0.0)

    monkeypatch.setattr(mod, "run_consult", fake)

    result = CliRunner().invoke(expert_consult, ["q", "--local", "--budget", "0", "--json"])

    assert result.exit_code == 0
    assert captured["budget"] == 0.0
    assert captured["synthesis_client"] is sentinel_client
    assert captured["synthesis_model"] == "qwen-local"
    assert captured["synthesis_provider"] == "local"
    assert captured["allow_live_fallback"] is False


def test_consult_plan_synthesis_vets_backend_and_disables_live_fallback(monkeypatch):
    from deepr.backends.waterfall import BACKEND_PLAN_QUOTA, BackendChoice

    captured = {}

    class FakeAdapter:
        backend_id = "grok"
        tos_note = ""
        exe = "grok"
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
        captured["budget"] = budget
        captured.update(kwargs)
        return _result(total_cost=0.0)

    monkeypatch.setattr(mod, "run_consult", fake)

    result = CliRunner().invoke(
        expert_consult,
        ["q", "--plan", "grok", "--plan-model", "fast", "--budget", "0", "--json"],
    )

    assert result.exit_code == 0
    assert captured["budget"] == 0.0
    assert isinstance(captured["synthesis_client"], FakePlanClient)
    assert captured["synthesis_model"] == "fast"
    assert captured["synthesis_provider"] == "plan_quota:grok"
    assert captured["allow_live_fallback"] is False
    assert captured["plan_model"] == "fast"
    assert captured["operation"] == "plan_quota_consult_synthesis"


def test_consult_anthropic_api_synthesis_passes_provider_and_model(monkeypatch):
    captured = {}

    async def fake(question, experts, max_experts, budget, **kwargs):
        captured["budget"] = budget
        captured.update(kwargs)
        return _result(total_cost=0.0)

    monkeypatch.setattr(mod, "run_consult", fake)

    result = CliRunner().invoke(
        expert_consult,
        ["q", "--provider", "anthropic", "--model", "claude-sonnet-4-6", "--budget", "1", "--json"],
    )

    assert result.exit_code == 0
    assert captured["budget"] == 1.0
    assert captured["synthesis_provider"] == "anthropic"
    assert captured["synthesis_model"] == "claude-sonnet-4-6"
    assert captured["allow_live_fallback"] is False
    parsed = json.loads(result.output)
    assert parsed["capacity"]["synthesis_backend"] == "api"
    assert parsed["capacity"]["provider"] == "anthropic"
    assert parsed["capacity"]["model"] == "claude-sonnet-4-6"


def test_consult_capacity_flags_are_exclusive():
    result = CliRunner().invoke(expert_consult, ["q", "--local", "--plan", "grok", "--json"])
    assert result.exit_code == 2
    assert "Choose only one synthesis backend" in result.output


def test_consult_api_provider_rejected_for_owned_capacity():
    result = CliRunner().invoke(expert_consult, ["q", "--local", "--provider", "anthropic", "--budget", "0", "--json"])
    assert result.exit_code == 2
    assert "API provider/model overrides" in result.output
