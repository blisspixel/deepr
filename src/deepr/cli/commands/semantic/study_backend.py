"""Capacity selection for ``deepr expert study`` ($0 local or prepaid plan).

A study pass is several model calls over a whole corpus, so it is exactly the
work that must not land on a metered API by accident. This module resolves one
completion callable and states plainly what it costs:

- **local**: Ollama, $0, the default and the recommended path.
- **plan**: a prepaid plan CLI, $0 at the margin, only where the adapter is not
  metered at the margin.
- **metered**: refused. There is no ``--api`` flag here. Study is the highest
  call-count surface in the expert loop, and paid dispatch is frozen.

Mirrors the backend selection in ``expert_absorb_support`` rather than inventing
a second capacity story, so the same adapters, the same block reasons, and the
same terms-of-service notes apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepr.experts.study import StudyCompletion


class StudyBackendError(ValueError):
    """Setup failure that must exit non-zero before any model call."""


@dataclass(frozen=True)
class StudyBackend:
    """A resolved completion callable plus what it costs and where it runs."""

    completion: StudyCompletion
    capacity_source: str
    cost_note: str


def _completion_from_chat_client(
    client: Any, model: str, *, max_tokens: int, context_tokens: int = 0
) -> StudyCompletion:
    """Adapt an OpenAI-style chat client to the study pass's callable.

    ``context_tokens`` is passed through to Ollama as ``num_ctx``. Without it the
    server allocates KV cache for the model's own configured context - commonly
    32K - regardless of how much is actually needed, which silently invalidates
    any VRAM sizing done beforehand and pushes the model onto CPU. Providers
    that do not understand the field ignore it.
    """
    extra_body: dict[str, Any] = {"keep_alive": "10m"}
    if context_tokens > 0:
        extra_body["num_ctx"] = context_tokens

    async def _completion(prompt: str) -> str:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        text = getattr(choices[0].message, "content", "") or ""
        if getattr(choices[0], "finish_reason", "") == "length":
            # A lens that produced 90% of its JSON and hit the ceiling is a
            # truncation, not a model that cannot follow the format. Saying
            # "no JSON object in response" sends the reader after the wrong
            # problem; the actual fix is a larger budget or fewer sources.
            raise StudyBackendError(
                f"response hit the {max_tokens}-token output limit and was cut off "
                "mid-structure. Raise --max-output-tokens or lower --max-corpus-chars."
            )
        return text

    return _completion


def build_study_backend(
    *,
    profile: Any,
    local: bool = False,
    plan: str | None = None,
    plan_model: str | None = None,
    model: str | None = None,
    max_tokens: int = 16000,
) -> StudyBackend:
    """Resolve the completion callable for one study pass.

    Local is the default when nothing is specified: a study pass is many calls,
    and the safe default for many calls is the one that cannot bill.
    """
    if plan:
        return _build_plan_backend(plan=plan, plan_model=plan_model, max_tokens=max_tokens)
    if local:
        return _build_local_backend(profile=profile, model=model, max_tokens=max_tokens)

    # Neither was asked for: prefer prepaid plan quota, then local.
    #
    # Both are $0 at the margin, so the tie-breakers are quality and machine
    # cost. A plan CLI runs a frontier-class model and leaves the GPU alone; the
    # local path runs whatever fits in free VRAM and holds the card for the
    # duration. Preferring plan is therefore better work at no extra money, and
    # local remains the guaranteed floor when no plan capacity is usable.
    for backend in _preferred_plan_backends():
        try:
            return _build_plan_backend(plan=backend, plan_model=plan_model, max_tokens=max_tokens)
        except StudyBackendError:
            continue
    return _build_local_backend(profile=profile, model=model, max_tokens=max_tokens)


def _preferred_plan_backends() -> list[str]:
    """Plan backends Deepr may auto-route to, best first.

    Only adapters that are genuinely $0 at the margin with verified plan auth
    and no execution block. Several installed CLIs (Codex, Grok, Antigravity,
    Kiro) are excluded here not because their quota is spent but because their
    native tool permissions cannot be confined before dispatch, which is a
    separate gate from cost.
    """
    try:
        from deepr.backends.plan_quota import auto_routable_adapters

        return [adapter.backend_id for adapter in auto_routable_adapters()]
    except Exception:
        return []


def _build_local_backend(
    *, profile: Any, model: str | None, max_tokens: int, context_tokens: int = 16384
) -> StudyBackend:
    from deepr.backends.local import ollama_chat_client, resolve_local_maintenance_model

    local_model = resolve_local_maintenance_model(profile, explicit_model=model)
    fit_note = ""
    if not model:
        # Prefer a model that runs entirely on GPU. The largest available model
        # is usually the wrong pick: a spill to CPU is silent and turns a
        # minutes-long study pass into an hours-long one.
        fitted, fit_note = _select_fitting_model(local_model, context_tokens)
        if fitted:
            local_model = fitted
    if not local_model:
        raise StudyBackendError("No local model available. Is Ollama running? Check: deepr capacity --probe")
    client = ollama_chat_client()
    return StudyBackend(
        completion=_completion_from_chat_client(
            client, local_model, max_tokens=max_tokens, context_tokens=context_tokens
        ),
        capacity_source=f"local:{local_model}",
        cost_note=f"$0 (local model {local_model} @ {context_tokens} ctx){fit_note}",
    )


def _select_fitting_model(current: str | None, context_tokens: int) -> tuple[str | None, str]:
    """Choose a locally-installed model that fits in free VRAM. Best effort.

    Returns (model or None, note). Any failure leaves the caller's existing
    choice alone: declining to switch is always safe, and guessing is not.
    """
    try:
        import httpx

        from deepr.backends.local import _base_url
        from deepr.backends.local_fit import choose_fitting_model, detect_vram_bytes

        base = _base_url(None)
        with httpx.Client(timeout=5.0, trust_env=False, follow_redirects=False) as client:
            response = client.get(f"{base}/api/tags")
            response.raise_for_status()
            # VRAM held by an already-resident model is reclaimable: Ollama
            # evicts it to load ours. Counting it as taken makes everything look
            # too big and falls back to the largest model.
            resident = client.get(f"{base}/api/ps")
            reclaimable = sum(int(entry.get("size_vram") or 0) for entry in (resident.json() or {}).get("models") or [])
        candidates = [
            (
                str(entry.get("name") or ""),
                int(entry.get("size") or 0),
                str((entry.get("details") or {}).get("parameter_size") or ""),
            )
            for entry in (response.json() or {}).get("models") or []
            if entry.get("name")
        ]
        chosen, _ = choose_fitting_model(
            candidates,
            context_tokens=context_tokens,
            vram_bytes=detect_vram_bytes(reclaimable_bytes=reclaimable),
        )
    except Exception:
        return None, ""

    if not chosen or chosen == current:
        return None, ""
    return chosen, f"; chose {chosen} over {current} to stay on GPU at {context_tokens} ctx"


def _build_plan_backend(*, plan: str, plan_model: str | None, max_tokens: int) -> StudyBackend:
    from deepr.backends.plan_quota import (
        PlanQuotaChatClient,
        get_adapter,
        metered_plan_execution_block_reason,
    )

    adapter = get_adapter(plan or "")
    if adapter is None:
        raise StudyBackendError(f"unknown plan-quota backend {plan!r}")
    if adapter.metered_at_margin:
        # A study pass is many calls. An adapter that bills per call is a
        # metered API wearing a plan label, and is refused here for the same
        # reason the metered path is.
        raise StudyBackendError(metered_plan_execution_block_reason(adapter))

    resolved_model = plan_model or adapter.backend_id
    client = PlanQuotaChatClient(adapter, model=plan_model)
    return StudyBackend(
        completion=_completion_from_chat_client(client, resolved_model, max_tokens=max_tokens),
        capacity_source=f"plan:{adapter.backend_id}",
        cost_note="$0 at the margin (prepaid plan)",
    )


__all__ = ["StudyBackend", "StudyBackendError", "build_study_backend"]
