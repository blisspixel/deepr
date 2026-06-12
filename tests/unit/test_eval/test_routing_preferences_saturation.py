"""Saturation-aware routing-preference generation (scripts/benchmark_models.py).

Live consequence this guards against (2026-06-11): gpt-4.1-nano scored a
mean 1.00 over 896 reasoning evals (the question set has no headroom at the
top), plain max() elected it best_quality for "reasoning", and auto mode
routed real reasoning queries to a nano model. Rankings must regenerate at
$0 from stored data (--regenerate-rankings), and saturated tasks must pick
by discriminative quality above a competence floor.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_models.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("benchmark_models_under_test", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_models_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _summary(bench, model_key: str, scores: dict[str, float], cost: float = 1.0):
    return bench.ModelSummary(model_key=model_key, scores_by_type=dict(scores), total_cost=cost, num_evals=10)


def _result(bench, model_key: str, task_type: str):
    return bench.EvalResult(
        model_key=model_key, task_type=task_type, difficulty="basic", prompt="", response="", latency_ms=100
    )


def _emit(bench, tmp_path, summaries, results) -> dict:
    bench.PROJECT_ROOT = tmp_path  # redirect output away from real data/benchmarks
    # registry filter: accept exactly the synthetic models under test
    bench.load_registry = lambda: {s.model_key: object() for s in summaries}
    out = bench.emit_routing_config(summaries, results)
    return json.loads(out.read_text())


class TestSaturationDetection:
    def test_ceiling_score_marks_task_saturated(self, bench, tmp_path):
        # nano "aces" the task (the live artifact); the frontier model is
        # close behind. Top >= ceiling => saturated, and the pick must go
        # to the model with better discriminative quality, not the artifact.
        summaries = [
            _summary(bench, "openai/gpt-4.1-nano", {"reasoning": 1.00, "comprehensive_research": 0.40}),
            _summary(bench, "openai/gpt-5.2", {"reasoning": 0.9799, "comprehensive_research": 0.97}),
            _summary(bench, "openai/gpt-5.4", {"reasoning": 0.88, "comprehensive_research": 0.90}),
        ]
        results = [_result(bench, s.model_key, tt) for s in summaries for tt in ("reasoning", "comprehensive_research")]
        config = _emit(bench, tmp_path, summaries, results)

        reasoning = config["task_preferences"]["reasoning"]
        assert reasoning["saturated"] is True
        assert reasoning["best_quality"] == "openai/gpt-5.2"
        # The discriminative task keeps its plain max
        research = config["task_preferences"]["comprehensive_research"]
        assert research["saturated"] is False
        assert research["best_quality"] == "openai/gpt-5.2"

    def test_two_way_tie_at_top_is_saturated(self, bench, tmp_path):
        summaries = [
            _summary(bench, "openai/gpt-4.1-nano", {"synthesis": 0.95, "comprehensive_research": 0.30}),
            _summary(bench, "openai/gpt-5.2", {"synthesis": 0.94, "comprehensive_research": 0.95}),
            _summary(bench, "openai/gpt-5.4", {"synthesis": 0.70, "comprehensive_research": 0.90}),
        ]
        results = [_result(bench, s.model_key, tt) for s in summaries for tt in ("synthesis", "comprehensive_research")]
        config = _emit(bench, tmp_path, summaries, results)
        assert config["task_preferences"]["synthesis"]["saturated"] is True
        assert config["task_preferences"]["synthesis"]["best_quality"] == "openai/gpt-5.2"

    def test_clear_winner_stays_unsaturated_and_wins(self, bench, tmp_path):
        summaries = [
            _summary(bench, "openai/gpt-5.2", {"synthesis": 0.90}),
            _summary(bench, "openai/gpt-5.4", {"synthesis": 0.70}),
        ]
        results = [_result(bench, s.model_key, "synthesis") for s in summaries]
        config = _emit(bench, tmp_path, summaries, results)
        pref = config["task_preferences"]["synthesis"]
        assert pref["saturated"] is False
        assert pref["best_quality"] == "openai/gpt-5.2"


class TestRegenerateRankings:
    def test_rehydrates_saved_results_without_api_calls(self, bench):
        saved = {
            "model": "openai/gpt-5.2",
            "task_type": "reasoning",
            "tier": "chat",
            "quality": 0.97,
            "judge_score": 0.95,
            "latency_ms": 1200,
        }
        er = bench.saved_result_to_eval(saved)
        assert er.model_key == "openai/gpt-5.2"
        assert er.combined_score == 0.97
        assert er.tier == "chat"
