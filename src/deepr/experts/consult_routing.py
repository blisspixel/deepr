"""Optional local embedding routing for consult findings (#264).

Consult picks findings by literal token overlap. On-topic material that shares
more words with a question can crowd out the finding that answers it, and a
finding phrased differently from the question is never offered. Measured on
the correction-survival worlds with 60 distractors, local embeddings recovered
more obligation findings than overlap alone.

This router only proposes an order of candidates. ``build_consult_context``
fuses it with the lexical order, and positions still carry their own cited
support. Similarity is not relevance: the answering model and review decide
what a finding means (``docs/plans/AGENTIC_BALANCE.md``).

It is off unless ``consult.embedding_model`` (``DEEPR_CONSULT_EMBEDDING_MODEL``)
names an installed local Ollama embedding model. Every embedding call is owned
local capacity with durable `$0` receipts. Any failure falls back to lexical
routing and says so.
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

logger = logging.getLogger(__name__)

EmbedFn = Callable[[list[str]], Awaitable[list[tuple[float, ...]]]]
CONSULT_EMBEDDING_MODEL_ENV = "DEEPR_CONSULT_EMBEDDING_MODEL"


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(y * y for y in right))
    return sum(x * y for x, y in zip(left, right, strict=True)) / norm if norm else 0.0


class FindingRouter:
    """Order study findings by embedding similarity to a question."""

    def __init__(self, model: str, *, embed_query: EmbedFn, embed_documents: EmbedFn) -> None:
        self.model = model
        self._embed_query = embed_query
        self._embed_documents = embed_documents

    async def rank(self, question: str, findings: Sequence[Any]) -> list[str]:
        from deepr.experts.consult_context import _finding_text

        candidates = [finding for finding in findings if finding.finding_id]
        if not candidates or not question.strip():
            return []
        (query,) = await self._embed_query([question])
        vectors = await self._embed_documents([_finding_text(finding) for finding in candidates])
        scored = sorted(
            ((_cosine(query, vector), index) for index, vector in enumerate(vectors)),
            key=lambda item: (-item[0], item[1]),
        )
        return [candidates[index].finding_id for _, index in scored]

    @property
    def note(self) -> str:
        return (
            f"Findings were offered by lexical overlap fused with local embedding similarity ({self.model}); "
            "similarity chose candidates and did not establish relevance."
        )


def local_finding_router(model: str) -> FindingRouter:
    """A router over an installed local embedding model with its known profile."""
    from deepr.backends.local import make_local_embedder

    return FindingRouter(
        model,
        embed_query=make_local_embedder(model, profile="auto", role="query"),
        embed_documents=make_local_embedder(model, profile="auto", role="document"),
    )


def configured_finding_router() -> FindingRouter | None:
    """The router named by configuration, or None when routing stays lexical."""
    model = os.getenv(CONSULT_EMBEDDING_MODEL_ENV, "").strip()
    if not model:
        return None
    return local_finding_router(model)


async def route_findings(router: FindingRouter, question: str, findings: Sequence[Any]) -> tuple[list[str] | None, str]:
    """Rank findings, or fall back to lexical routing with a note saying why."""
    try:
        return await router.rank(question, findings), router.note
    except Exception as error:  # routing must never take the consult down
        logger.debug("consult embedding routing unavailable", exc_info=True)
        return None, (
            f"Local embedding routing ({router.model}) was unavailable ({type(error).__name__}); "
            "findings were offered by lexical overlap only."
        )


async def route_expert_findings(
    router: FindingRouter | None, question: str, expert_name: str
) -> tuple[list[str] | None, str]:
    """Rank one expert's study findings, or fall back to lexical routing with a note."""
    if router is None:
        return None, ""
    from deepr.experts.consult_context import load_study
    from deepr.experts.expert_layout import part_in
    from deepr.experts.paths import canonical_expert_dir

    try:
        study = load_study(part_in(canonical_expert_dir(expert_name), "noticed"))
    except Exception:  # an unreadable study is handled by the consult path itself
        logger.debug("study unavailable for consult routing of %s", expert_name, exc_info=True)
        return None, ""
    if study is None or not study.findings:
        return None, ""
    return await route_findings(router, question, study.findings)
