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


def _completion_from_chat_client(client: Any, model: str, *, max_tokens: int) -> StudyCompletion:
    """Adapt an OpenAI-style chat client to the study pass's callable."""

    async def _completion(prompt: str) -> str:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        return getattr(choices[0].message, "content", "") or ""

    return _completion


def build_study_backend(
    *,
    profile: Any,
    local: bool = False,
    plan: str | None = None,
    plan_model: str | None = None,
    model: str | None = None,
    max_tokens: int = 4000,
) -> StudyBackend:
    """Resolve the completion callable for one study pass.

    Local is the default when nothing is specified: a study pass is many calls,
    and the safe default for many calls is the one that cannot bill.
    """
    if plan:
        return _build_plan_backend(plan=plan, plan_model=plan_model, max_tokens=max_tokens)
    if local or not plan:
        return _build_local_backend(profile=profile, model=model, max_tokens=max_tokens)
    raise StudyBackendError("no capacity selected: pass --local or --plan <backend>")


def _build_local_backend(*, profile: Any, model: str | None, max_tokens: int) -> StudyBackend:
    from deepr.backends.local import ollama_chat_client, resolve_local_maintenance_model

    local_model = resolve_local_maintenance_model(profile, explicit_model=model)
    if not local_model:
        raise StudyBackendError("No local model available. Is Ollama running? Check: deepr capacity --probe")
    client = ollama_chat_client()
    return StudyBackend(
        completion=_completion_from_chat_client(client, local_model, max_tokens=max_tokens),
        capacity_source=f"local:{local_model}",
        cost_note=f"$0 (local model {local_model})",
    )


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
