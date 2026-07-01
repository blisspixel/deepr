"""Helpers for optional retrieval-context builders."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

ContextBuilder = Callable[..., Awaitable[Any]]


def accepts_prior_source_pack(context_builder: ContextBuilder) -> bool:
    try:
        parameters = inspect.signature(context_builder).parameters
    except (TypeError, ValueError):
        return False
    return "prior_source_pack" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


async def build_context(
    context_builder: ContextBuilder | None,
    query: str,
    *,
    prior_source_pack: dict[str, Any] | None = None,
) -> Any | None:
    if context_builder is None:
        return None
    if prior_source_pack is not None and accepts_prior_source_pack(context_builder):
        return await context_builder(query, prior_source_pack=prior_source_pack)
    return await context_builder(query)
