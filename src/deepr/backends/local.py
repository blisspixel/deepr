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

from deepr.backends.capacity import (
    _OLLAMA_DEFAULT_URL,
    ollama_status,
    validate_owned_local_ollama_cloud_status,
    validate_owned_local_ollama_url,
)
from deepr.backends.context_building import (
    ContextBuilder,
    build_context,
    context_evidence_fields,
    context_generation_readiness,
    context_not_ready_error,
)
from deepr.experts.semantic_model_gate import require_zero_dollar_client

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


async def _guard_and_sanitize_ollama_request(request: Any) -> None:
    """Prove server cloud is disabled and strip ambient provider headers."""
    import httpx

    netloc = request.url.netloc
    rendered_netloc = netloc.decode("ascii") if isinstance(netloc, bytes) else str(netloc)
    endpoint = validate_owned_local_ollama_url(f"{request.url.scheme}://{rendered_netloc}")
    async with httpx.AsyncClient(
        timeout=5.0,
        trust_env=False,
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": "deepr-local-capacity-guard/1"},
    ) as guard:
        response = await guard.get(f"{endpoint}/api/status")
    if response.status_code != 200:
        raise ValueError(f"Owned local Ollama cloud-disable proof returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Owned local Ollama cloud-disable proof was not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Owned local Ollama cloud-disable proof must be an object")
    validate_owned_local_ollama_cloud_status(payload)

    content_length = request.headers.get("content-length")
    request.headers.clear()
    request.headers.update(
        {
            "Accept": "application/json",
            "Authorization": "Bearer ollama",
            "Content-Type": "application/json",
            "Host": rendered_netloc,
            "User-Agent": "deepr-local-ollama/1",
        }
    )
    if content_length:
        request.headers["Content-Length"] = content_length


def _base_url(base_url: str | None) -> str:
    """Resolve and validate the owned Ollama URL (arg > env > default)."""
    return validate_owned_local_ollama_url(base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL)


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
    import httpx
    from openai import AsyncOpenAI

    if timeout is None:
        timeout = float(os.getenv("DEEPR_LOCAL_TIMEOUT", "3600"))
    http_client = httpx.AsyncClient(
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [_guard_and_sanitize_ollama_request]},
    )
    client = AsyncOpenAI(
        base_url=f"{_base_url(base_url)}/v1",
        api_key="ollama",
        timeout=timeout,
        max_retries=0,
        http_client=http_client,
        organization="",
        project="",
        default_headers={"Authorization": "Bearer ollama"},
    )
    from deepr.experts.semantic_model_gate import _mark_zero_dollar_client

    return _mark_zero_dollar_client(client, capacity_source="local")


async def release_local_model(model: str, base_url: str | None = None) -> bool:
    """Ask Ollama to unload ``model`` now, freeing VRAM.

    ``_KEEP_ALIVE`` pins weights warm so a multi-call workload does not pay a
    cold reload between calls. That is right during a run and rude after it: a
    19 GB model sitting in VRAM for the rest of the keep-alive window blocks
    every other GPU user on the machine, including a short probe that needed the
    model for one second.

    So the contract is: pin during the workload, release at the end. Callers that
    finish a bounded run should call this in a ``finally``. Best effort - if the
    server is gone or ignores the field, the keep-alive window simply expires as
    before, so failing here is never worth surfacing as an error.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False, follow_redirects=False) as client:
            response = await client.post(
                f"{_base_url(base_url)}/api/generate",
                json={"model": model, "keep_alive": 0, "prompt": ""},
            )
        return response.status_code < 400
    except Exception:
        return False


async def local_model_runs_on_gpu(model: str, base_url: str | None = None) -> tuple[bool, str]:
    """Report whether a loaded model is resident on GPU. Returns (on_gpu, detail).

    A model whose weights plus context exceed available VRAM is silently placed
    on CPU by Ollama, where a study pass that would take minutes instead takes
    many hours. "$0 local" stays literally true and becomes practically
    unusable, and the operator has no way to tell from Deepr's output. This makes
    it visible so a run can be redirected to a smaller model or a shorter
    context rather than appearing to hang.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False, follow_redirects=False) as client:
            response = await client.get(f"{_base_url(base_url)}/api/ps")
        if response.status_code >= 400:
            return True, ""
        for entry in (response.json() or {}).get("models") or []:
            if entry.get("name") != model and entry.get("model") != model:
                continue
            total = int(entry.get("size") or 0)
            on_gpu = int(entry.get("size_vram") or 0)
            if total <= 0:
                return True, ""
            gpu_share = on_gpu / total
            if gpu_share >= 0.99:
                return True, ""
            return False, (
                f"{model} is {(1 - gpu_share) * 100:.0f}% on CPU "
                f"({on_gpu / 1e9:.1f} GB of {total / 1e9:.1f} GB in VRAM). "
                "Expect it to be many times slower than a GPU-resident run; "
                "consider a smaller model or a shorter --max-corpus-chars."
            )
    except Exception:
        return True, ""
    return True, ""


def default_local_model(base_url: str | None = None) -> str | None:
    """Pick a local model: DEEPR_LOCAL_MODEL if set, else the first one Ollama lists."""
    url = _base_url(base_url)
    explicit = os.getenv("DEEPR_LOCAL_MODEL")
    if explicit:
        return explicit
    running, detail = ollama_status(url)
    if not running:
        return None
    # ollama_status detail starts "N model(s): a, b, c..." - take the first name.
    if "model(s): " in detail:
        first = detail.split("model(s): ", 1)[1].split(",", 1)[0].strip().rstrip(".")
        return first or None
    return None


async def default_local_model_async(base_url: str | None = None, *, timeout: float = 0.5) -> str | None:
    """Resolve the default local model through a cancellable bounded probe."""
    url = _base_url(base_url)
    explicit = os.getenv("DEEPR_LOCAL_MODEL")
    if explicit:
        return explicit
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
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
    owned_base_url = _base_url(base_url)
    selected = (explicit_model or "").strip()
    if selected:
        return selected

    provider = str(getattr(profile, "provider", "") or "").strip().lower()
    recorded = str(getattr(profile, "model", "") or "").strip()
    if provider == "local" and recorded and recorded.lower() != "ollama":
        return recorded
    # Preserve the long-standing no-argument probe seam used by callers and
    # tests when no operation-specific URL was supplied. The endpoint was
    # already validated above, and default_local_model() resolves the same
    # environment/default URL again before probing it.
    if base_url is None:
        return default_local_model()
    return default_local_model(owned_base_url)


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
    owned_base_url = _base_url(base_url)
    embeddings_client = client if client is not None else ollama_chat_client(owned_base_url)
    require_zero_dollar_client(embeddings_client, capacity_source="local")

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
    owned_base_url = _base_url(base_url)
    chat = client if client is not None else ollama_chat_client(owned_base_url)
    require_zero_dollar_client(chat, capacity_source="local")

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
    try:
        owned_base_url = _base_url(base_url)
    except ValueError as error:
        return {"ok": False, "model": model, "reply": "", "latency_ms": 0, "error": str(error)}
    chosen = model or default_local_model(owned_base_url)
    if not chosen:
        return {"ok": False, "model": None, "reply": "", "latency_ms": 0, "error": "no local model available"}

    chat = client if client is not None else ollama_chat_client(owned_base_url)
    start = time.perf_counter()
    try:
        require_zero_dollar_client(chat, capacity_source="local")
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
