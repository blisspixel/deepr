"""Local Ollama backend - research on owned hardware at $0 (ROADMAP v2.16).

The capacity release's "local-first validation" step (docs/design/
capacity-waterfall.md): plug a local model into deepr's existing injectable
seams so dev/test and quality-tolerant work run at $0 on owned hardware. Even
when local output quality is below the deep-research floor, the *flow* is fully
real - submit, extract, verify, absorb - so the whole expert lifecycle can be
exercised end to end for free.

Ollama serves an OpenAI-compatible API at ``/v1``, so an ``AsyncOpenAI`` client
pointed there satisfies every chat seam deepr already uses (report_absorber,
reflection, conflict_resolver) with no new client shape. ``make_local_research_fn``
adapts the same to the ``research_fn`` seam (sync, gap-fill).

This is local execution, not deep research. Eval-gated admission for *routing*
quality lands with the waterfall router; this module is the $0 substrate.
"""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from deepr.backends.capacity import _OLLAMA_DEFAULT_URL, ollama_status

# research_fn seam contract (deepr/experts/sync.py): (query, budget) -> result.
ResearchFn = Callable[[str, float], Awaitable[dict[str, Any]]]
ContextBuilder = Callable[[str], Awaitable[Any]]


def _base_url(base_url: str | None) -> str:
    """Resolve the Ollama base URL (arg > env > default), no trailing slash."""
    return (base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL).rstrip("/")


def ollama_chat_client(base_url: str | None = None) -> Any:
    """An AsyncOpenAI client pointed at Ollama's OpenAI-compatible endpoint.

    Usable anywhere deepr injects a chat ``client`` (report_absorber,
    reflection). The api_key is a required-but-ignored placeholder; nothing is
    billed - calls hit the local server.
    """
    from openai import AsyncOpenAI

    return AsyncOpenAI(base_url=f"{_base_url(base_url)}/v1", api_key="ollama")


def default_local_model(base_url: str | None = None) -> str | None:
    """Pick a local model: DEEPR_LOCAL_MODEL if set, else the first one Ollama lists."""
    explicit = os.getenv("DEEPR_LOCAL_MODEL")
    if explicit:
        return explicit
    running, detail = ollama_status(base_url)
    if not running:
        return None
    # ollama_status detail starts "N model(s): a, b, c..." - take the first name.
    if "model(s): " in detail:
        first = detail.split("model(s): ", 1)[1].split(",", 1)[0].strip().rstrip(".")
        return first or None
    return None


def _local_prompt(query: str, context: Any | None) -> tuple[str, dict[str, Any] | None]:
    if context is None:
        return query, None
    if hasattr(context, "to_prompt_context"):
        prompt_context = context.to_prompt_context()
        metadata = context.to_metadata() if hasattr(context, "to_metadata") else None
    else:
        prompt_context = str(context)
        metadata = None
    return (
        f"{prompt_context}\n\n## User query\n{query}\n\n"
        "Answer the query using the fresh retrieval context when it is relevant. "
        "For current factual claims, cite source labels from the context. "
        "For deep-context runs, synthesize across sources, name meaningful gaps, "
        "and avoid unsupported claims. If fresh context is unavailable or "
        "insufficient, say so.",
        metadata,
    )


def make_local_research_fn(
    model: str,
    *,
    base_url: str | None = None,
    client: Any | None = None,
    context_builder: ContextBuilder | None = None,
) -> ResearchFn:
    """Build a ``research_fn`` that answers via a local Ollama model at $0.

    Satisfies the sync/gap-fill seam: ``(query, budget) -> {"answer", "cost"}``.
    Cost is always 0.0 (owned hardware); ``budget`` is ignored. Errors are
    returned in the result, never raised, matching the seam's contract.
    """
    chat = client if client is not None else ollama_chat_client(base_url)

    async def research_fn(query: str, budget: float) -> dict[str, Any]:
        try:
            context = await context_builder(query) if context_builder is not None else None
            prompt, metadata = _local_prompt(query, context)
            response = await chat.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.choices[0].message.content or ""
            result: dict[str, Any] = {"answer": answer, "cost": 0.0}
            if metadata is not None:
                result["fresh_context"] = metadata
            if hasattr(context, "to_source_pack"):
                result["source_pack"] = context.to_source_pack()
            return result
        except Exception as e:  # seam contract: report, do not raise
            return {"answer": "", "cost": 0.0, "error": f"local model error: {e}"}

    return research_fn


async def probe_local(
    model: str | None = None, *, base_url: str | None = None, client: Any | None = None
) -> dict[str, Any]:
    """A $0 round-trip to the local model to prove the backend actually works.

    Returns ``{ok, model, reply, latency_ms, error}``. Never raises.
    """
    chosen = model or default_local_model(base_url)
    if not chosen:
        return {"ok": False, "model": None, "reply": "", "latency_ms": 0, "error": "no local model available"}

    chat = client if client is not None else ollama_chat_client(base_url)
    start = time.perf_counter()
    try:
        response = await chat.chat.completions.create(
            model=chosen,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=16,
        )
        reply = (response.choices[0].message.content or "").strip()
        return {
            "ok": True,
            "model": chosen,
            "reply": reply,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": "",
        }
    except Exception as e:
        return {
            "ok": False,
            "model": chosen,
            "reply": "",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(e),
        }
