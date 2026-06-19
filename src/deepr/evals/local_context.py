"""Evaluate local freshness context modes at $0.

This complements ``deepr eval local``. That command compares local models; this
one compares the context envelope for one local model: no context, fresh
context, and deep context. The judge handles semantic quality. Deterministic
code owns source counts, citation-label shape, score ranges, latency, failures,
and the zero-cost contract.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from deepr.backends.fresh_context import (
    FreshContext,
    FreshContextConfig,
    make_free_deep_context_builder,
    make_free_fresh_context_builder,
)
from deepr.backends.local import ollama_chat_client
from deepr.evals.local_compare import parse_judge_verdict

METHODOLOGY_VERSION = "1.0"
PROMPT_SET_LOCAL_FRESHNESS = "local-freshness"
ContextMode = Literal["none", "fresh", "deep"]
CONTEXT_MODES: tuple[ContextMode, ...] = ("none", "fresh", "deep")
ContextBuilder = Callable[[str], Awaitable[FreshContext]]

_CITATION_RE = re.compile(r"\[S(\d+)\]")


@dataclass(frozen=True)
class LocalContextPrompt:
    """One freshness question and rubric."""

    prompt_id: str
    task_class: str
    query: str
    rubric: str

    def to_dict(self) -> dict[str, str]:
        return {
            "prompt_id": self.prompt_id,
            "task_class": self.task_class,
            "query": self.query,
            "rubric": self.rubric,
        }


@dataclass(frozen=True)
class LocalContextVerdict:
    """Judge score plus deterministic contract adjustments."""

    score: float
    raw_score: float
    reason: str
    raw: str
    adjustments: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "raw_score": self.raw_score,
            "reason": self.reason,
            "raw": self.raw,
            "adjustments": list(self.adjustments),
        }


@dataclass(frozen=True)
class LocalContextModeResult:
    """Answer quality for one prompt under one context mode."""

    prompt_id: str
    task_class: str
    mode: ContextMode
    answer: str
    latency_ms: int
    source_count: int
    retrieved_source_count: int
    citation_count: int
    invalid_citation_labels: tuple[str, ...]
    verdict: LocalContextVerdict
    cost: float = 0.0
    error: str = ""
    context_metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "task_class": self.task_class,
            "mode": self.mode,
            "answer": self.answer,
            "latency_ms": self.latency_ms,
            "source_count": self.source_count,
            "retrieved_source_count": self.retrieved_source_count,
            "citation_count": self.citation_count,
            "invalid_citation_labels": list(self.invalid_citation_labels),
            "verdict": self.verdict.to_dict(),
            "cost": self.cost,
            "error": self.error,
            "context_metadata": self.context_metadata or {},
        }


@dataclass(frozen=True)
class LocalContextEvalReport:
    """Full local context-mode evaluation."""

    model: str
    judge_model: str
    prompt_set: str
    prompts: tuple[LocalContextPrompt, ...]
    results: tuple[LocalContextModeResult, ...]
    methodology_version: str = METHODOLOGY_VERSION
    generated_at: datetime | None = None

    @property
    def cost(self) -> float:
        return 0.0

    @property
    def mode_scores(self) -> dict[str, float]:
        scores: dict[str, list[float]] = {mode: [] for mode in CONTEXT_MODES}
        for result in self.results:
            scores[result.mode].append(result.verdict.score)
        return {mode: _average(values) for mode, values in scores.items()}

    @property
    def winner_mode(self) -> str:
        scores = self.mode_scores
        if not scores:
            return ""
        return max(scores, key=lambda mode: (scores[mode], -CONTEXT_MODES.index(mode)))

    def to_dict(self) -> dict[str, Any]:
        generated_at = self.generated_at or datetime.now(UTC)
        return {
            "methodology_version": self.methodology_version,
            "generated_at": generated_at.isoformat(),
            "model": self.model,
            "judge_model": self.judge_model,
            "prompt_set": self.prompt_set,
            "winner_mode": self.winner_mode,
            "mode_scores": self.mode_scores,
            "cost": self.cost,
            "prompts": [prompt.to_dict() for prompt in self.prompts],
            "results": [result.to_dict() for result in self.results],
        }


def default_context_prompts(prompt_set: str = PROMPT_SET_LOCAL_FRESHNESS) -> tuple[LocalContextPrompt, ...]:
    """Return built-in local context eval prompts."""
    if prompt_set != PROMPT_SET_LOCAL_FRESHNESS:
        raise ValueError(f"unknown local context prompt set: {prompt_set}")
    return (
        LocalContextPrompt(
            prompt_id="openai-web-search-tool",
            task_class="freshness",
            query=(
                "Using https://developers.openai.com/api/docs/guides/tools-web-search, "
                "summarize how web search is exposed to model calls and name one practical integration detail. "
                "Cite source labels when sources are available."
            ),
            rubric=(
                "High scores require source-grounded current details, clear citation behavior, "
                "and honest uncertainty when no fresh source context is available."
            ),
        ),
        LocalContextPrompt(
            prompt_id="local-deep-research-loop",
            task_class="deep_context",
            query=(
                "Using https://github.com/langchain-ai/local-deep-researcher, describe the local deep research "
                "loop and the search options it supports. Cite source labels when sources are available."
            ),
            rubric=(
                "High scores require an accurate loop description, search-tool awareness, citations when "
                "sources are present, and no unsupported current claims."
            ),
        ),
    )


async def run_local_context_eval(
    model: str,
    *,
    judge_model: str,
    prompts: Sequence[LocalContextPrompt] | None = None,
    prompt_set: str = PROMPT_SET_LOCAL_FRESHNESS,
    modes: Sequence[ContextMode] = CONTEXT_MODES,
    base_url: str | None = None,
    client: Any | None = None,
    context_builders: Mapping[ContextMode, ContextBuilder] | None = None,
) -> LocalContextEvalReport:
    """Run one local model through no/fresh/deep context modes."""
    if not model:
        raise ValueError("model is required")
    if not judge_model:
        raise ValueError("judge_model is required")

    prompt_tuple = tuple(prompts) if prompts is not None else default_context_prompts(prompt_set)
    if not prompt_tuple:
        raise ValueError("at least one prompt is required")

    mode_tuple = tuple(modes)
    if not mode_tuple:
        raise ValueError("at least one context mode is required")

    chat = client if client is not None else ollama_chat_client(base_url)
    builders = context_builders or _default_context_builders()
    results: list[LocalContextModeResult] = []
    for prompt in prompt_tuple:
        for mode in mode_tuple:
            results.append(await _run_context_mode(chat, model, judge_model, prompt, mode, builders))

    return LocalContextEvalReport(
        model=model,
        judge_model=judge_model,
        prompt_set=prompt_set,
        prompts=prompt_tuple,
        results=tuple(results),
    )


def write_context_report(report: LocalContextEvalReport, *, output_dir: Path | None = None) -> Path:
    """Write a local context eval artifact under ``data/benchmarks``."""
    root = output_dir or Path("data/benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = root / f"local_context_{timestamp}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _default_context_builders() -> dict[ContextMode, ContextBuilder]:
    small = FreshContextConfig(max_search_results=4, max_fetches=3, max_total_chars=6000)
    deep = FreshContextConfig(
        max_search_results=5,
        max_fetches=6,
        max_chars_per_source=1400,
        max_total_chars=11000,
        max_search_queries=3,
    )
    return {
        "fresh": make_free_fresh_context_builder(config=small),
        "deep": make_free_deep_context_builder(config=deep),
    }


async def _run_context_mode(
    chat: Any,
    model: str,
    judge_model: str,
    prompt: LocalContextPrompt,
    mode: ContextMode,
    context_builders: Mapping[ContextMode, ContextBuilder],
) -> LocalContextModeResult:
    start = time.perf_counter()
    try:
        context = await _build_context(prompt.query, mode, context_builders)
        answer = await _answer(chat, model=model, query=prompt.query, mode=mode, context=context)
        latency_ms = int((time.perf_counter() - start) * 1000)
        metadata = _context_metadata(context)
        verdict = await _judge_context_answer(
            chat,
            judge_model=judge_model,
            prompt=prompt,
            mode=mode,
            answer=answer,
            context=context,
            metadata=metadata,
        )
        labels = _citation_labels(answer)
        invalid = _invalid_citation_labels(labels, int(metadata.get("source_count", 0)))
        adjusted = _apply_contract_adjustments(verdict, labels=labels, invalid_labels=invalid, metadata=metadata)
        return LocalContextModeResult(
            prompt_id=prompt.prompt_id,
            task_class=prompt.task_class,
            mode=mode,
            answer=answer,
            latency_ms=latency_ms,
            source_count=int(metadata.get("source_count", 0)),
            retrieved_source_count=int(metadata.get("retrieved_source_count", 0)),
            citation_count=len(labels),
            invalid_citation_labels=invalid,
            verdict=adjusted,
            context_metadata=metadata,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _failed_result(prompt, mode, latency_ms, str(exc))


async def _build_context(
    query: str,
    mode: ContextMode,
    context_builders: Mapping[ContextMode, ContextBuilder],
) -> FreshContext | None:
    if mode == "none":
        return None
    builder = context_builders.get(mode)
    if builder is None:
        raise ValueError(f"no context builder configured for mode {mode!r}")
    return await builder(query)


async def _answer(
    chat: Any,
    *,
    model: str,
    query: str,
    mode: ContextMode,
    context: FreshContext | None,
) -> str:
    if context is None:
        user_prompt = (
            "No fresh retrieval context is provided for this eval mode.\n\n"
            f"User query:\n{query}\n\n"
            "Answer only if the question can be handled without current source context. "
            "If current facts are required, say that fresh context is unavailable."
        )
    else:
        user_prompt = (
            f"{context.to_prompt_context()}\n\n## User query\n{query}\n\n"
            "Answer using the retrieval context when it is relevant. Cite source labels for current factual claims. "
            "Name meaningful gaps instead of inventing unsupported details."
        )
    response = await chat.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Answer directly and concretely. Keep the answer under 180 words. This eval mode is {mode}."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=360,
    )
    return response.choices[0].message.content or ""


async def _judge_context_answer(
    chat: Any,
    *,
    judge_model: str,
    prompt: LocalContextPrompt,
    mode: ContextMode,
    answer: str,
    context: FreshContext | None,
    metadata: dict[str, Any],
) -> LocalContextVerdict:
    raw = await _judge_completion(
        chat,
        judge_model=judge_model,
        judge_prompt=_judge_prompt(prompt, mode=mode, answer=answer, context=context, metadata=metadata),
    )
    parsed = parse_judge_verdict(raw)
    return LocalContextVerdict(score=parsed.score, raw_score=parsed.score, reason=parsed.reason, raw=parsed.raw)


async def _judge_completion(chat: Any, *, judge_model: str, judge_prompt: str) -> str:
    response = await chat.chat.completions.create(
        model=judge_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict evaluator. Return only JSON with keys score and reason. "
                    "score must be a number from 0 to 1."
                ),
            },
            {"role": "user", "content": judge_prompt},
        ],
        max_tokens=260,
    )
    return response.choices[0].message.content or ""


def _judge_prompt(
    prompt: LocalContextPrompt,
    *,
    mode: ContextMode,
    answer: str,
    context: FreshContext | None,
    metadata: dict[str, Any],
) -> str:
    context_text = context.to_prompt_context() if context is not None else "No retrieval context was provided."
    return (
        f"QUESTION:\n{prompt.query}\n\n"
        f"MODE: {mode}\n"
        f"SOURCE_COUNT: {metadata.get('source_count', 0)}\n"
        f"RUBRIC:\n{prompt.rubric}\n\n"
        f"RETRIEVAL_CONTEXT:\n{context_text[:5000]}\n\n"
        f"ANSWER:\n{answer}\n\n"
        "Score answer relevance, grounding in the provided context, citation behavior, and honesty about missing "
        "fresh context. Return JSON only."
    )


def _context_metadata(context: FreshContext | None) -> dict[str, Any]:
    if context is None:
        return {
            "mode": "none",
            "source_count": 0,
            "retrieved_source_count": 0,
            "sources": [],
            "errors": [],
        }
    return dict(context.to_metadata())


def _citation_labels(answer: str) -> tuple[int, ...]:
    return tuple(int(match) for match in _CITATION_RE.findall(answer))


def _invalid_citation_labels(labels: tuple[int, ...], source_count: int) -> tuple[str, ...]:
    return tuple(f"S{label}" for label in labels if label < 1 or label > source_count)


def _apply_contract_adjustments(
    verdict: LocalContextVerdict,
    *,
    labels: tuple[int, ...],
    invalid_labels: tuple[str, ...],
    metadata: dict[str, Any],
) -> LocalContextVerdict:
    score = verdict.score
    adjustments: list[str] = []
    source_count = int(metadata.get("source_count", 0))
    mode = str(metadata.get("mode", "none"))
    if invalid_labels:
        score = min(score, 0.2)
        adjustments.append("invalid source label")
    if mode in {"fresh", "deep"} and source_count > 0 and not labels:
        score = min(score, 0.75)
        adjustments.append("missing source label")
    return LocalContextVerdict(
        score=score,
        raw_score=verdict.raw_score,
        reason=verdict.reason,
        raw=verdict.raw,
        adjustments=tuple(adjustments),
    )


def _failed_result(
    prompt: LocalContextPrompt, mode: ContextMode, latency_ms: int, error: str
) -> LocalContextModeResult:
    return LocalContextModeResult(
        prompt_id=prompt.prompt_id,
        task_class=prompt.task_class,
        mode=mode,
        answer="",
        latency_ms=latency_ms,
        source_count=0,
        retrieved_source_count=0,
        citation_count=0,
        invalid_citation_labels=(),
        verdict=LocalContextVerdict(score=0.0, raw_score=0.0, reason="context eval failed", raw=""),
        error=error,
        context_metadata={"mode": mode, "source_count": 0, "retrieved_source_count": 0, "sources": [], "errors": []},
    )


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
