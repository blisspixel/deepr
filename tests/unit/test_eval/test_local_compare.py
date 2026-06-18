"""Tests for $0 local model comparison."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals.local_compare import (
    LocalEvalPrompt,
    default_prompts,
    parse_judge_verdict,
    run_local_comparison,
)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        model = kwargs["model"]
        user_text = kwargs["messages"][-1]["content"]
        if model == "judge":
            answer = user_text.split("ANSWER:\n", 1)[-1]
            score = 0.9 if "verifier" in answer and "budget" in answer else 0.2
            return _FakeResponse(json.dumps({"score": score, "reason": "rubric match"}))
        if model == "good-local":
            return _FakeResponse("Use context, act, observe verifier output, and stop on budget or pass.")
        if model == "weak-local":
            return _FakeResponse("Run it forever because local is free.")
        raise RuntimeError(f"unexpected model {model}")


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()


def test_parse_judge_verdict_accepts_json_with_extra_text():
    verdict = parse_judge_verdict('prefix {"score": 0.75, "reason": "solid"} suffix')

    assert verdict.score == 0.75
    assert verdict.reason == "solid"


@pytest.mark.parametrize("raw", ["", "not json", '{"score": 2}', '{"score": "bad"}'])
def test_parse_judge_verdict_rejects_invalid_payloads(raw):
    verdict = parse_judge_verdict(raw)

    assert verdict.score == 0.0
    assert verdict.reason


async def test_run_local_comparison_scores_models_with_local_judge():
    prompt = LocalEvalPrompt(
        prompt_id="p1",
        task_class="loop",
        prompt="Describe a loop with verifier and budget stop.",
        rubric="Needs verifier and budget.",
    )

    report = await run_local_comparison(
        ["good-local", "weak-local"],
        judge_model="judge",
        prompts=[prompt],
        client=_FakeClient(),
    )

    assert report.cost == 0.0
    assert report.winner == "good-local"
    assert report.comparisons[0].average_score == 0.9
    assert report.comparisons[1].average_score == 0.2
    assert report.to_dict()["comparisons"][0]["cost"] == 0.0


async def test_run_local_comparison_reports_candidate_errors():
    report = await run_local_comparison(
        ["missing"],
        judge_model="judge",
        prompts=[default_prompts()[0]],
        client=_FakeClient(),
    )

    result = report.comparisons[0].prompt_results[0]
    assert result.error
    assert result.verdict.score == 0.0


def test_eval_local_cli_requires_installed_models(monkeypatch):
    from deepr.backends import capacity

    monkeypatch.setattr(capacity, "available_local_models", lambda: [])

    result = CliRunner().invoke(cli, ["eval", "local"])

    assert result.exit_code != 0
    assert "No local Ollama models available" in result.output


def test_eval_local_cli_json(monkeypatch):
    from deepr.backends import capacity
    from deepr.evals import local_compare

    monkeypatch.setattr(capacity, "available_local_models", lambda: ["good-local", "weak-local", "judge"])

    async def fake_run_local_comparison(models, *, judge_model, prompts, prompt_set):
        return await run_local_comparison(models, judge_model=judge_model, prompts=prompts, client=_FakeClient())

    monkeypatch.setattr(local_compare, "run_local_comparison", fake_run_local_comparison)

    result = CliRunner().invoke(cli, ["eval", "local", "--model", "good-local", "--judge-model", "judge", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["winner"] == "good-local"
    assert data["cost"] == 0.0
