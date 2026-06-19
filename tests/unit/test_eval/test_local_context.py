"""Tests for $0 local context-mode evaluation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from click.testing import CliRunner

from deepr.backends.fresh_context import FreshContext, FreshSource
from deepr.cli.main import cli
from deepr.evals.local_context import (
    LocalContextEvalReport,
    LocalContextModeResult,
    LocalContextPrompt,
    LocalContextVerdict,
    default_context_prompts,
    run_local_context_eval,
    write_context_report,
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
    def __init__(self, *, invalid_citation: bool = False):
        self.invalid_citation = invalid_citation
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        model = kwargs["model"]
        user_text = kwargs["messages"][-1]["content"]
        if model == "judge":
            mode = re.search(r"MODE: ([a-z]+)", user_text)
            mode_name = mode.group(1) if mode else "none"
            score = {"none": 0.3, "fresh": 0.78, "deep": 0.91}.get(mode_name, 0.0)
            return _FakeResponse(json.dumps({"score": score, "reason": f"{mode_name} context quality"}))
        if model == "local":
            if "No fresh retrieval context" in user_text:
                return _FakeResponse("Fresh context is unavailable for current facts.")
            if self.invalid_citation:
                return _FakeResponse("The retrieved source says the current detail is available [S99].")
            if "Mode: deep" in user_text:
                return _FakeResponse(
                    "The local deep research loop searches, summarizes, reflects on gaps, and repeats with "
                    "follow-up queries [S1]."
                )
            return _FakeResponse("The fresh context describes current implementation details [S1].")
        raise RuntimeError(f"unexpected model {model}")


class _FakeChat:
    def __init__(self, *, invalid_citation: bool = False):
        self.completions = _FakeCompletions(invalid_citation=invalid_citation)


class _FakeClient:
    def __init__(self, *, invalid_citation: bool = False):
        self.chat = _FakeChat(invalid_citation=invalid_citation)


def _prompt() -> LocalContextPrompt:
    return LocalContextPrompt(
        prompt_id="p1",
        task_class="freshness",
        query="Use https://example.com/current to answer with citations.",
        rubric="Needs retrieved context and honest citation behavior.",
    )


async def _fresh_context(query: str) -> FreshContext:
    return FreshContext(
        query=query,
        generated_at="2026-06-18T00:00:00Z",
        sources=(
            FreshSource(
                title="Current example",
                url="https://example.com/current",
                content="Current implementation details are available.",
                source="test",
                fetched=True,
            ),
        ),
        search_backend="test",
        browser_backend="test",
        mode="fresh",
        search_queries=(query,),
    )


async def _deep_context(query: str) -> FreshContext:
    return FreshContext(
        query=query,
        generated_at="2026-06-18T00:00:00Z",
        sources=(
            FreshSource(
                title="Deep example",
                url="https://example.com/deep",
                content="The loop searches, summarizes, reflects on gaps, and repeats with follow-up queries.",
                source="test",
                fetched=True,
            ),
        ),
        search_backend="test",
        browser_backend="test",
        mode="deep",
        search_queries=(query, f"{query} latest updates"),
    )


async def test_run_local_context_eval_compares_modes_with_local_judge():
    report = await run_local_context_eval(
        "local",
        judge_model="judge",
        prompts=[_prompt()],
        client=_FakeClient(),
        context_builders={"fresh": _fresh_context, "deep": _deep_context},
    )

    assert report.cost == 0.0
    assert report.winner_mode == "deep"
    assert report.mode_scores["none"] == 0.3
    assert report.mode_scores["fresh"] == 0.78
    assert report.mode_scores["deep"] == 0.91
    assert [result.mode for result in report.results] == ["none", "fresh", "deep"]
    assert report.results[1].source_count == 1
    assert report.results[1].citation_count == 1
    assert report.to_dict()["cost"] == 0.0


async def test_run_local_context_eval_caps_invalid_source_labels():
    report = await run_local_context_eval(
        "local",
        judge_model="judge",
        prompts=[_prompt()],
        modes=["fresh"],
        client=_FakeClient(invalid_citation=True),
        context_builders={"fresh": _fresh_context},
    )

    result = report.results[0]
    assert result.invalid_citation_labels == ("S99",)
    assert result.verdict.raw_score == 0.78
    assert result.verdict.score == 0.2
    assert result.verdict.adjustments == ("invalid source label",)


async def test_run_local_context_eval_requires_prompts():
    try:
        await run_local_context_eval("local", judge_model="judge", prompts=[], client=_FakeClient())
    except ValueError as exc:
        assert "at least one prompt" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_default_context_prompts_reject_unknown_set():
    try:
        default_context_prompts("unknown")
    except ValueError as exc:
        assert "unknown local context prompt set" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_write_context_report(tmp_path: Path):
    report = LocalContextEvalReport(
        model="local",
        judge_model="judge",
        prompt_set="local-freshness",
        prompts=(_prompt(),),
        results=(
            LocalContextModeResult(
                prompt_id="p1",
                task_class="freshness",
                mode="none",
                answer="answer",
                latency_ms=1,
                source_count=0,
                retrieved_source_count=0,
                citation_count=0,
                invalid_citation_labels=(),
                verdict=LocalContextVerdict(score=0.1, raw_score=0.1, reason="ok", raw="{}"),
            ),
        ),
    )

    path = write_context_report(report, output_dir=tmp_path)

    assert path.name.startswith("local_context_")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["winner_mode"] == "none"
    assert data["cost"] == 0.0


def test_eval_local_context_cli_requires_installed_models(monkeypatch):
    from deepr.backends import capacity

    monkeypatch.setattr(capacity, "available_local_models", lambda: [])

    result = CliRunner().invoke(cli, ["eval", "local-context"])

    assert result.exit_code != 0
    assert "No local Ollama models available" in result.output


def test_eval_local_context_cli_json(monkeypatch):
    from deepr.backends import capacity
    from deepr.evals import local_context

    monkeypatch.setattr(capacity, "available_local_models", lambda: ["local", "judge"])

    async def fake_run_local_context_eval(model, *, judge_model, prompts, prompt_set):
        assert model == "local"
        assert judge_model == "judge"
        return LocalContextEvalReport(
            model=model,
            judge_model=judge_model,
            prompt_set=prompt_set,
            prompts=tuple(prompts),
            results=(
                LocalContextModeResult(
                    prompt_id=prompts[0].prompt_id,
                    task_class=prompts[0].task_class,
                    mode="deep",
                    answer="answer [S1]",
                    latency_ms=1,
                    source_count=1,
                    retrieved_source_count=1,
                    citation_count=1,
                    invalid_citation_labels=(),
                    verdict=LocalContextVerdict(score=0.8, raw_score=0.8, reason="ok", raw="{}"),
                ),
            ),
        )

    monkeypatch.setattr(local_context, "run_local_context_eval", fake_run_local_context_eval)

    result = CliRunner().invoke(
        cli,
        ["eval", "local-context", "--model", "local", "--judge-model", "judge", "--json"],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["winner_mode"] == "deep"
    assert data["cost"] == 0.0


def test_eval_local_context_cli_rejects_missing_model(monkeypatch):
    from deepr.backends import capacity

    monkeypatch.setattr(capacity, "available_local_models", lambda: ["local"])

    result = CliRunner().invoke(cli, ["eval", "local-context", "--model", "missing"])

    assert result.exit_code != 0
    assert "Local model is not installed: missing" in result.output
