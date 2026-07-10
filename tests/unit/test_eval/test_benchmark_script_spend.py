"""Regression tests that benchmark calls cannot bypass spend reservations."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from deepr.evals.benchmark_budget import BenchmarkBudgetExceeded

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_models.py"


@pytest.fixture(scope="module")
def benchmark_module():
    spec = importlib.util.spec_from_file_location("benchmark_models_spend_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_models_spend_test"] = module
    spec.loader.exec_module(module)
    return module


class OneCallGuard:
    def __init__(self):
        self.reserved = []
        self.settled = []

    def reserve(self, **kwargs):
        if self.reserved:
            raise BenchmarkBudgetExceeded("test ceiling reached")
        reservation = SimpleNamespace(cost_ceiling=kwargs["cost_ceiling"])
        self.reserved.append((reservation, kwargs))
        return reservation

    def settle(self, reservation, *, status):
        self.settled.append((reservation, status))

    def refund(self, _reservation):
        raise AssertionError("successfully submitted calls must not refund")


class StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def capability(*, input_cost=2.5, output_cost=15.0, per_query=0.0, context_window=1000):
    return SimpleNamespace(
        input_cost_per_1m=input_cost,
        output_cost_per_1m=output_cost,
        cost_per_query=per_query,
        context_window=context_window,
    )


def test_evaluations_submit_only_reserved_calls(benchmark_module, monkeypatch):
    prompts = [
        benchmark_module.EvalPrompt("a", "easy", "first", []),
        benchmark_module.EvalPrompt("b", "easy", "second", []),
    ]
    provider_calls = []

    def fake_eval(model_key, prompt, _registry):
        provider_calls.append(prompt.prompt)
        return (
            benchmark_module.EvalResult(model_key, prompt.task_type, prompt.difficulty, prompt.prompt, "ok", 1),
            0.005,
        )

    guard = OneCallGuard()
    monkeypatch.setattr(benchmark_module, "_eval_single", fake_eval)
    monkeypatch.setattr(benchmark_module, "_save_checkpoint", lambda _results: None)

    registry = {"openai/test": capability(input_cost=1.0, output_cost=1.0)}
    results = benchmark_module.run_evaluations(["openai/test"], prompts, registry, guard, max_workers=2)

    assert provider_calls == ["first"]
    assert len(results) == 1
    assert len(guard.reserved) == 1
    assert [status for _, status in guard.settled] == ["completed"]


def test_judge_submits_only_reserved_calls(benchmark_module, monkeypatch):
    results = [
        benchmark_module.EvalResult("openai/a", "a", "easy", "first", "ok", 1),
        benchmark_module.EvalResult("openai/b", "b", "easy", "second", "ok", 1),
    ]
    judge_calls = []

    def fake_judge(result, _judge_model):
        judge_calls.append(result.model_key)
        return {"correctness": 8.0}, 0.8

    guard = OneCallGuard()
    monkeypatch.setattr(benchmark_module, "_judge_single", fake_judge)

    judged = benchmark_module.run_judge(results, "openai/judge", guard, 0.01, max_workers=2)

    assert judge_calls == ["openai/a"]
    assert judged[0].judge_score == 0.8
    assert judged[1].judge_score == 0.0
    assert len(guard.reserved) == 1
    assert [status for _, status in guard.settled] == ["completed"]


def test_validation_reserves_and_settles_provider_call(benchmark_module, monkeypatch):
    guard = OneCallGuard()
    monkeypatch.setattr(benchmark_module, "call_model", lambda *_args, **_kwargs: ("4", 1, []))

    response = benchmark_module._accounted_validation_call(
        spend_guard=guard,
        registry={"openai/test": capability(input_cost=1.0, output_cost=1.0)},
        model_key="openai/test",
        prompt="What is 2+2?",
        max_tokens=10,
        tier="chat",
    )

    assert response == ("4", 1, [])
    assert guard.reserved[0][1]["operation"] == "benchmark_validation"
    assert [status for _, status in guard.settled] == ["completed"]


def test_openai_reservation_matches_outbound_reasoning_and_tool_maxima(benchmark_module, monkeypatch):
    request_body = {}

    def fake_post(_url, *, json, **_kwargs):
        request_body.update(json)
        return StubResponse({"output_text": "ok", "output": []})

    monkeypatch.setattr("requests.post", fake_post)
    prompt = benchmark_module.EvalPrompt("news", "hard", "current facts", [], max_tokens=500, tier="news")

    benchmark_module.call_openai_news("key", "gpt-5.4", prompt.prompt, prompt.max_tokens, max_tool_calls=3)
    ceiling = benchmark_module.estimate_eval_cost("openai/gpt-5.4", prompt, {"openai/gpt-5.4": capability()})

    assert request_body["max_output_tokens"] == 4096
    assert request_body["max_tool_calls"] == 3
    authorized_cost = ((3000 * 2.5 + 4096 * 15.0) / 1_000_000) * 2.2 + 3 * 0.05
    assert ceiling >= authorized_cost


def test_gemini_reservation_matches_outbound_thinking_maximum(benchmark_module, monkeypatch):
    request_body = {}

    def fake_post(_url, *, json, **_kwargs):
        request_body.update(json)
        return StubResponse({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr("requests.post", fake_post)
    prompt = benchmark_module.EvalPrompt("chat", "hard", "explain", [], max_tokens=500, tier="chat")

    benchmark_module.call_gemini("key", "gemini-2.5-pro", prompt.prompt, prompt.max_tokens)
    ceiling = benchmark_module.estimate_eval_cost(
        "gemini/gemini-2.5-pro",
        prompt,
        {"gemini/gemini-2.5-pro": capability(input_cost=1.25, output_cost=10.0)},
    )

    outbound_maximum = request_body["generationConfig"]["maxOutputTokens"]
    assert outbound_maximum == 4096
    authorized_cost = ((400 * 1.25 + outbound_maximum * 10.0) / 1_000_000) * 1.2
    assert ceiling >= authorized_cost


def test_xai_chat_response_does_not_enable_uncapped_search(benchmark_module, monkeypatch):
    request_body = {}

    def fake_post(_url, *, json, **_kwargs):
        request_body.update(json)
        return StubResponse({"output_text": "ok", "output": [], "citations": []})

    monkeypatch.setattr("requests.post", fake_post)

    benchmark_module.call_grok_response("key", "grok-4.3", "explain", 500)

    assert request_body["max_output_tokens"] == 500
    assert "tools" not in request_body
    assert "max_turns" not in request_body


def test_unpriced_and_uncapped_models_fail_closed(benchmark_module):
    prompt = benchmark_module.EvalPrompt("research", "hard", "investigate", [], tier="research")

    with pytest.raises(BenchmarkBudgetExceeded, match="trusted pricing"):
        benchmark_module.estimate_eval_cost("openai/unknown", prompt, {})
    with pytest.raises(BenchmarkBudgetExceeded, match="request-level spend ceiling"):
        benchmark_module.estimate_eval_cost(
            "openai/o3-deep-research",
            prompt,
            {"openai/o3-deep-research": capability(per_query=1.5)},
        )
    with pytest.raises(BenchmarkBudgetExceeded, match="search-cost ceiling"):
        benchmark_module.estimate_eval_cost(
            "gemini/gemini-3.1-pro-preview",
            prompt,
            {"gemini/gemini-3.1-pro-preview": capability(per_query=0.5)},
        )
    with pytest.raises(BenchmarkBudgetExceeded, match="search-cost ceiling"):
        benchmark_module.estimate_eval_cost(
            "xai/grok-4-3",
            prompt,
            {"xai/grok-4-3": capability(per_query=0.01)},
        )


def test_research_selection_uses_only_bounded_orchestration(benchmark_module, capsys):
    args = SimpleNamespace(model=None, provider=None, include_expensive=False)
    key_status = {"openai": True, "xai": True, "gemini": True}

    selected = benchmark_module.select_models(args, {}, key_status, tier="research")

    assert selected == benchmark_module.ORCHESTRATED_RESEARCH_MODELS
    assert all("deep-research" not in model for model in selected)
    assert all(not model.startswith("xai/") for model in selected)
    assert benchmark_module._selected_provider_count(selected) == 2

    args.model = "gemini/deep-research"
    assert benchmark_module.select_models(args, {}, key_status, tier="research") == []
    assert "without a deterministic request-level spend ceiling" in capsys.readouterr().out


def test_xai_search_dispatch_is_blocked_before_network(benchmark_module, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "unused")

    with pytest.raises(BenchmarkBudgetExceeded, match="search-cost ceiling"):
        benchmark_module.call_model("xai/grok-4-3", "latest", 500, tier="news")
