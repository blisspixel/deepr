"""Helpers for optional retrieval-context builders."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

ContextBuilder = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ContextGenerationReadiness:
    """Structural evidence readiness before a model generation call.

    This contract counts replayable provenance only. It must not encode a
    topical relevance, truth, source-quality, or claim-support verdict.
    """

    ready: bool
    mode: str
    ready_source_count: int
    required_source_count: int
    retrieved_source_count: int
    explicit_url_count: int = 0
    retryable: bool = True
    no_metered_fallback: bool = True

    @property
    def detail(self) -> str:
        if self.ready:
            return "context evidence is ready for generation"
        return (
            f"{self.mode} context has {self.ready_source_count} content-addressed source(s); "
            f"{self.required_source_count} required before generation"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "mode": self.mode,
            "ready_source_count": self.ready_source_count,
            "required_source_count": self.required_source_count,
            "retrieved_source_count": self.retrieved_source_count,
            "explicit_url_count": self.explicit_url_count,
            "retryable": self.retryable,
            "no_metered_fallback": self.no_metered_fallback,
            "detail": self.detail,
        }


def accepts_prior_source_pack(context_builder: ContextBuilder) -> bool:
    return accepts_keyword_argument(context_builder, "prior_source_pack")


def accepts_keyword_argument(callable_obj: Callable[..., Any], argument: str) -> bool:
    """Whether a callable accepts one named keyword or arbitrary keywords."""
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False
    return argument in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


def context_generation_readiness(context: Any | None) -> ContextGenerationReadiness | None:
    """Read an optional structural readiness contract from built context."""
    if context is None:
        return None
    readiness_fn = getattr(context, "generation_readiness", None)
    if not callable(readiness_fn):
        return None
    readiness = readiness_fn()
    if not isinstance(readiness, ContextGenerationReadiness):
        raise TypeError("context generation_readiness() returned an invalid contract")
    return readiness


def context_not_ready_error(readiness: ContextGenerationReadiness) -> str:
    """Stable retry guidance for a provenance-under-ready context pack."""
    return (
        f"fresh context not ready: {readiness.detail}. No generation backend was called and no metered "
        "fallback was used. Retry later or provide explicit URLs."
    )


def context_evidence_fields(context: Any | None) -> dict[str, Any]:
    """Serialize optional context metadata and its durable source-pack input."""
    if context is None:
        return {}
    fields: dict[str, Any] = {}
    metadata_fn = getattr(context, "to_metadata", None)
    if callable(metadata_fn):
        fields["fresh_context"] = metadata_fn()
    source_pack_fn = getattr(context, "to_source_pack", None)
    if callable(source_pack_fn):
        # Full text is transient transport for the sync snapshot writer. The
        # writer strips it before persisting the bounded source-pack artifact.
        fields["source_pack"] = source_pack_fn(include_content=True)
    return fields


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
