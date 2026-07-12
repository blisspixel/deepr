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
from deepr.backends.context_building import (
    ContextBuilder,
    build_context,
    context_evidence_fields,
    context_generation_readiness,
    context_not_ready_error,
)

# research_fn seam contract (deepr/experts/sync.py): (query, budget) -> result.
ResearchFn = Callable[[str, float], Awaitable[dict[str, Any]]]

# embed_claims seam contract (deepr/experts/belief_embedding_refresh.py):
# ordered claim texts in, one vector per claim out, same order.
EmbedClaimsFn = Callable[[list[str]], Awaitable[list[tuple[float, ...]]]]

# Keep the model resident between calls. Ollama evicts after ~5 min idle by
# default, so a multi-call workload (a sync with several subscriptions, or a
# spaced probe) pays a full cold reload of the weights each time - e.g. ~60s to
# page a 19 GB model back into VRAM on an otherwise-idle GPU. Passing keep_alive
# on every request pins it warm for the window; "-1" would pin indefinitely.
# Ollama reads this from the request body even on its OpenAI-compatible /v1
# endpoint; a server that ignores it simply falls back to the default.
_KEEP_ALIVE = os.getenv("DEEPR_OLLAMA_KEEP_ALIVE", "30m")


def _base_url(base_url: str | None) -> str:
    """Resolve the Ollama base URL (arg > env > default), no trailing slash."""
    return (base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL).rstrip("/")


def ollama_chat_client(base_url: str | None = None, *, timeout: float | None = None) -> Any:
    """An AsyncOpenAI client pointed at Ollama's OpenAI-compatible endpoint.

    Usable anywhere deepr injects a chat ``client`` (report_absorber,
    reflection, local web research). The api_key is a required-but-ignored
    placeholder; nothing is billed - calls hit the local server.

    Local generation is intentionally allowed to be slow - a large model on a
    long context can run at well under 1 token/sec, and that is fine for
    unattended $0 work. The OpenAI SDK's 600s default timeout would abort such a
    legitimate run, so default to a generous timeout (``DEEPR_LOCAL_TIMEOUT``
    seconds, default 3600). Raise ``DEEPR_LOCAL_TIMEOUT`` for very slow runs.
    """
    from openai import AsyncOpenAI

    if timeout is None:
        timeout = float(os.getenv("DEEPR_LOCAL_TIMEOUT", "3600"))
    return AsyncOpenAI(base_url=f"{_base_url(base_url)}/v1", api_key="ollama", timeout=timeout)


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


async def default_local_model_async(base_url: str | None = None, *, timeout: float = 0.5) -> str | None:
    """Resolve the default local model through a cancellable bounded probe."""
    explicit = os.getenv("DEEPR_LOCAL_MODEL")
    if explicit:
        return explicit
    url = _base_url(base_url)
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{url}/api/tags")
            response.raise_for_status()
        payload = response.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        for model in models:
            if not isinstance(model, dict):
                continue
            name = str(model.get("name", "") or "").strip()
            if name:
                return name
    except Exception:
        return None
    return None


def resolve_local_maintenance_model(
    profile: object | None,
    *,
    explicit_model: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Resolve the Ollama model for one expert maintenance operation.

    An explicit command or admitted-capacity model remains authoritative. When
    no operation-level model was selected, a local expert's recorded model is
    the per-expert maintenance preference promised by ``expert make
    --local --local-model``. Non-local profiles and placeholder local profiles
    retain the existing process-wide default behavior.
    """
    selected = (explicit_model or "").strip()
    if selected:
        return selected

    provider = str(getattr(profile, "provider", "") or "").strip().lower()
    recorded = str(getattr(profile, "model", "") or "").strip()
    if provider == "local" and recorded and recorded.lower() != "ollama":
        return recorded
    if base_url is None:
        return default_local_model()
    return default_local_model(base_url)


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


def make_local_embedder(
    model: str,
    *,
    base_url: str | None = None,
    client: Any | None = None,
) -> EmbedClaimsFn:
    """Build an ``embed_claims`` batcher backed by a local Ollama model at $0.

    Ollama serves the OpenAI-compatible ``/v1/embeddings`` endpoint, so the
    same client shape as the chat seams works for embeddings. Vectors are
    reordered by response index because the endpoint does not guarantee input
    order. The batcher raises on transport or shape failures instead of
    degrading silently; callers own the no-fallback policy and user-facing
    error reporting.
    """
    chosen = model.strip()
    if not chosen:
        raise ValueError("embedding model is required")
    embeddings_client = client if client is not None else ollama_chat_client(base_url)

    async def embed_claims(claims: list[str]) -> list[tuple[float, ...]]:
        if not claims:
            return []
        response = await embeddings_client.embeddings.create(
            model=chosen,
            input=list(claims),
            extra_body={"keep_alive": _KEEP_ALIVE},
        )
        rows = sorted(response.data, key=lambda row: row.index)
        vectors = [tuple(float(value) for value in row.embedding) for row in rows]
        if len(vectors) != len(claims):
            raise RuntimeError(
                f"local embedding model {chosen} returned {len(vectors)} vector(s) for {len(claims)} claim(s)"
            )
        return vectors

    return embed_claims


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

    async def research_fn(
        query: str,
        budget: float,
        *,
        prior_source_pack: dict[str, Any] | None = None,
        retrieval_query: str | None = None,
    ) -> dict[str, Any]:
        try:
            context = await build_context(
                context_builder,
                retrieval_query or query,
                prior_source_pack=prior_source_pack,
            )
            evidence_fields = context_evidence_fields(context)
            readiness = context_generation_readiness(context)
            if readiness is not None and not readiness.ready:
                return {
                    "answer": "",
                    "cost": 0.0,
                    "error": context_not_ready_error(readiness),
                    "error_code": "fresh_context_not_ready",
                    "retryable": readiness.retryable,
                    "no_metered_fallback": readiness.no_metered_fallback,
                    "context_preflight": readiness.to_dict(),
                    **evidence_fields,
                }
            prompt, metadata = _local_prompt(query, context)
            response = await chat.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                extra_body={"keep_alive": _KEEP_ALIVE},
            )
            answer = response.choices[0].message.content or ""
            result: dict[str, Any] = {"answer": answer, "cost": 0.0}
            result.update(evidence_fields)
            if metadata is not None and "fresh_context" not in result:
                result["fresh_context"] = metadata
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
            extra_body={"keep_alive": _KEEP_ALIVE},
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
