"""Local Ollama model comparison with a local LLM judge.

This is the $0 counterpart to paid benchmark runs. Candidate models answer a
small prompt set, and a local judge model scores the answers against rubrics.
The judge owns semantic quality; deterministic code owns shape, ranges, cost,
and reporting.
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.backends.local import ollama_chat_client

METHODOLOGY_VERSION = "1.0"
PROMPT_SET_AGENTIC_LOOPS = "agentic-loops"
GROK_JUDGE_COMMAND = "grok --prompt-file {prompt_file} --output-format plain --disable-web-search --max-turns 1"


@dataclass(frozen=True)
class LocalEvalPrompt:
    """One local comparison prompt and its scoring rubric."""

    prompt_id: str
    task_class: str
    prompt: str
    rubric: str

    def to_dict(self) -> dict[str, str]:
        return {
            "prompt_id": self.prompt_id,
            "task_class": self.task_class,
            "prompt": self.prompt,
            "rubric": self.rubric,
        }


@dataclass(frozen=True)
class LocalJudgeVerdict:
    """A local judge score for one answer."""

    score: float
    reason: str
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "reason": self.reason, "raw": self.raw}


@dataclass(frozen=True)
class CliJudgeCommand:
    """Explicit non-API CLI judge command template."""

    template: str
    display_name: str = "cli"
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if "{prompt_file}" not in self.template:
            raise ValueError("CLI judge command must include {prompt_file}")
        if self.timeout_seconds <= 0:
            raise ValueError("CLI judge timeout must be positive")


@dataclass(frozen=True)
class LocalPromptResult:
    """Candidate answer plus judge result for one prompt."""

    prompt_id: str
    task_class: str
    answer: str
    latency_ms: int
    verdict: LocalJudgeVerdict
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "task_class": self.task_class,
            "answer": self.answer,
            "latency_ms": self.latency_ms,
            "verdict": self.verdict.to_dict(),
            "error": self.error,
        }


@dataclass(frozen=True)
class LocalModelComparison:
    """Aggregate score for one local candidate model."""

    model: str
    prompt_results: tuple[LocalPromptResult, ...]

    @property
    def average_score(self) -> float:
        if not self.prompt_results:
            return 0.0
        return sum(result.verdict.score for result in self.prompt_results) / len(self.prompt_results)

    @property
    def average_latency_ms(self) -> int:
        if not self.prompt_results:
            return 0
        return round(sum(result.latency_ms for result in self.prompt_results) / len(self.prompt_results))

    @property
    def cost(self) -> float:
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "average_score": self.average_score,
            "average_latency_ms": self.average_latency_ms,
            "cost": self.cost,
            "prompt_results": [result.to_dict() for result in self.prompt_results],
        }


@dataclass(frozen=True)
class LocalComparisonReport:
    """Full local comparison report."""

    prompt_set: str
    judge_model: str
    prompts: tuple[LocalEvalPrompt, ...]
    comparisons: tuple[LocalModelComparison, ...]
    methodology_version: str = METHODOLOGY_VERSION
    generated_at: datetime | None = None

    @property
    def winner(self) -> str:
        if not self.comparisons:
            return ""
        best = max(
            self.comparisons,
            key=lambda comparison: (comparison.average_score, -comparison.average_latency_ms, comparison.model),
        )
        return best.model

    @property
    def cost(self) -> float:
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        generated_at = self.generated_at or datetime.now(UTC)
        return {
            "methodology_version": self.methodology_version,
            "generated_at": generated_at.isoformat(),
            "prompt_set": self.prompt_set,
            "judge_model": self.judge_model,
            "winner": self.winner,
            "cost": self.cost,
            "prompts": [prompt.to_dict() for prompt in self.prompts],
            "comparisons": [comparison.to_dict() for comparison in self.comparisons],
        }


def default_prompts(prompt_set: str = PROMPT_SET_AGENTIC_LOOPS) -> tuple[LocalEvalPrompt, ...]:
    """Return built-in $0 comparison prompts."""
    if prompt_set != PROMPT_SET_AGENTIC_LOOPS:
        raise ValueError(f"unknown local prompt set: {prompt_set}")
    return (
        LocalEvalPrompt(
            prompt_id="bounded-loop-contract",
            task_class="agentic_loop",
            prompt=(
                "Design a bounded expert-maintenance loop for Deepr in one paragraph. "
                "It must include context assembly, action, observation, verifier outcome, "
                "budget or capacity stop, and a clear reason it is safe to run unattended."
            ),
            rubric=(
                "High scores require a concrete loop contract, explicit stop conditions, "
                "verifier separation, budget or capacity safety, and no vague autonomy claims."
            ),
        ),
        LocalEvalPrompt(
            prompt_id="capacity-routing-decision",
            task_class="capacity_routing",
            prompt=(
                "A Deepr job can run on local Ollama, a subscription CLI with unknown quota, "
                "or a metered API. Explain the safe routing decision when no quota observation "
                "exists for the subscription CLI."
            ),
            rubric=(
                "High scores require local-first preference when quality permits, blocking "
                "unknown subscription quota, and requiring an explicit budget gate before metered use."
            ),
        ),
    )


async def run_local_comparison(
    models: Sequence[str],
    *,
    judge_model: str = "",
    judge_command: CliJudgeCommand | None = None,
    prompts: Sequence[LocalEvalPrompt] | None = None,
    prompt_set: str = PROMPT_SET_AGENTIC_LOOPS,
    base_url: str | None = None,
    client: Any | None = None,
) -> LocalComparisonReport:
    """Compare local models with a local judge model.

    All model calls go to the local Ollama OpenAI-compatible endpoint unless a
    fake client is injected by tests. The returned cost is always 0.0.
    """
    if not models:
        raise ValueError("at least one local model is required")
    if judge_command is None and not judge_model:
        raise ValueError("judge_model is required")

    prompt_tuple = tuple(prompts) if prompts is not None else default_prompts(prompt_set)
    if not prompt_tuple:
        raise ValueError("at least one prompt is required")

    chat = client if client is not None else ollama_chat_client(base_url)
    judge_label = judge_command.display_name if judge_command else judge_model
    comparisons: list[LocalModelComparison] = []
    for model in models:
        prompt_results = []
        for prompt in prompt_tuple:
            prompt_results.append(await _run_prompt(chat, model, judge_model, prompt, judge_command=judge_command))
        comparisons.append(LocalModelComparison(model=model, prompt_results=tuple(prompt_results)))

    return LocalComparisonReport(
        prompt_set=prompt_set,
        judge_model=judge_label,
        prompts=prompt_tuple,
        comparisons=tuple(comparisons),
    )


def write_report(report: LocalComparisonReport, *, output_dir: Path | None = None) -> Path:
    """Write a local comparison artifact under ``data/benchmarks``."""
    root = output_dir or Path("data/benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = root / f"local_compare_{timestamp}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


async def _run_prompt(
    chat: Any,
    model: str,
    judge_model: str,
    prompt: LocalEvalPrompt,
    *,
    judge_command: CliJudgeCommand | None = None,
) -> LocalPromptResult:
    start = time.perf_counter()
    try:
        answer = await _complete(
            chat,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer directly and concretely. Prefer operational detail over broad claims. "
                        "Keep the answer under 180 words."
                    ),
                },
                {"role": "user", "content": prompt.prompt},
            ],
            max_tokens=320,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LocalPromptResult(
            prompt_id=prompt.prompt_id,
            task_class=prompt.task_class,
            answer="",
            latency_ms=latency_ms,
            verdict=LocalJudgeVerdict(score=0.0, reason="candidate model failed", raw=""),
            error=str(exc),
        )

    verdict = (
        await _judge_answer_with_cli(judge_command, prompt=prompt, answer=answer)
        if judge_command
        else await _judge_answer(chat, judge_model=judge_model, prompt=prompt, answer=answer)
    )
    return LocalPromptResult(
        prompt_id=prompt.prompt_id,
        task_class=prompt.task_class,
        answer=answer,
        latency_ms=latency_ms,
        verdict=verdict,
    )


async def _judge_answer(chat: Any, *, judge_model: str, prompt: LocalEvalPrompt, answer: str) -> LocalJudgeVerdict:
    try:
        raw = await _complete(
            chat,
            model=judge_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict evaluator. Return only JSON with keys score and reason. "
                        "score must be a number from 0 to 1. Judge whether the answer satisfies the rubric."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"PROMPT:\n{prompt.prompt}\n\nRUBRIC:\n{prompt.rubric}\n\n"
                        f"ANSWER:\n{answer}\n\nReturn JSON only."
                    ),
                },
            ],
            max_tokens=220,
        )
    except Exception as exc:
        return LocalJudgeVerdict(score=0.0, reason=f"judge model failed: {exc}", raw="")
    return parse_judge_verdict(raw)


async def _judge_answer_with_cli(
    judge_command: CliJudgeCommand, *, prompt: LocalEvalPrompt, answer: str
) -> LocalJudgeVerdict:
    judge_prompt = _build_judge_prompt(prompt, answer)
    try:
        raw = await asyncio.to_thread(_run_cli_judge_command, judge_command, judge_prompt)
    except Exception as exc:
        return LocalJudgeVerdict(score=0.0, reason=f"CLI judge failed: {exc}", raw="")
    return parse_judge_verdict(raw)


def _build_judge_prompt(prompt: LocalEvalPrompt, answer: str) -> str:
    return (
        "You are a strict evaluator. Evaluate only the text below. Do not use web search or tools.\n"
        "Return only JSON with keys score and reason. score must be a number from 0 to 1.\n\n"
        f"PROMPT:\n{prompt.prompt}\n\nRUBRIC:\n{prompt.rubric}\n\n"
        f"ANSWER:\n{answer}\n\nReturn JSON only."
    )


def _run_cli_judge_command(judge_command: CliJudgeCommand, judge_prompt: str) -> str:
    with tempfile.TemporaryDirectory(prefix="deepr-cli-judge-") as tmp:
        prompt_file = Path(tmp) / "judge_prompt.txt"
        prompt_file.write_text(judge_prompt, encoding="utf-8")
        args = _render_cli_judge_args(judge_command.template, prompt_file)
        completed = subprocess.run(  # noqa: S603 - explicit CLI judge opt-in; shell disabled, prompt file only.
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=judge_command.timeout_seconds,
            check=False,
            shell=False,
        )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(stderr or f"judge command exited with status {completed.returncode}")
    return completed.stdout


def _render_cli_judge_args(template: str, prompt_file: Path) -> list[str]:
    parts = shlex.split(template)
    return [part.replace("{prompt_file}", str(prompt_file)) for part in parts]


async def _complete(chat: Any, *, model: str, messages: list[dict[str, str]], max_tokens: int) -> str:
    response = await chat.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens)
    return response.choices[0].message.content or ""


def parse_judge_verdict(raw: str) -> LocalJudgeVerdict:
    """Parse and range-check local judge JSON."""
    payload = _extract_json_object(raw)
    if payload is None:
        return LocalJudgeVerdict(score=0.0, reason="judge did not return JSON", raw=raw)

    score_value = payload.get("score")
    try:
        score = float(score_value)
    except (TypeError, ValueError):
        return LocalJudgeVerdict(score=0.0, reason="judge score was not numeric", raw=raw)

    if score < 0.0 or score > 1.0:
        return LocalJudgeVerdict(score=0.0, reason="judge score was outside 0..1", raw=raw)

    reason = payload.get("reason")
    return LocalJudgeVerdict(score=score, reason=str(reason or ""), raw=raw)


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
