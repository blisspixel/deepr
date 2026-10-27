"""Build a council perspective from what the expert studied.

A briefed expert leads with its brief. The belief store is a ledger of atomic
claims and remains the fallback for experts that were never studied, but where
a brief exists it is the better answer: it carries where the expert landed,
what would overturn that, what it could not resolve, and behind each position
the findings and the retained passage the claim can be checked against.

Kept out of ``council`` so the consult path can grow without that module
becoming the place everything lands.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepr.experts.preparation_context import PreparedConsultation

logger = logging.getLogger(__name__)

COVERAGE_CONFIDENCE = {"grounded": 0.75, "partial": 0.4, "uncovered": 0.0}
"""Confidence in the packet, not in the answer.

``grounded`` means a position exists and its support resolves to a retained
passage. ``uncovered`` is zero deliberately: a perspective assembled from
nothing must not be weighted as though it were evidence, which is what the
old confidence-fallback path did by returning top-confidence beliefs
regardless of whether they bore on the question.
"""


def confidence_for_coverage(coverage: str) -> float:
    return COVERAGE_CONFIDENCE.get(coverage, 0.0)


def load_consult_context(
    query: str, name: str, semantic_ranking: list[str] | None = None, routing_note: str = ""
) -> Any:
    """Assemble the studied layers for this question, or None if unbriefed."""
    from deepr.experts.consult_context import build_consult_context, load_brief, load_study
    from deepr.experts.corpus_store import CorpusStore
    from deepr.experts.expert_layout import part_in
    from deepr.experts.paths import canonical_expert_dir

    expert_dir = canonical_expert_dir(name)
    brief = load_brief(part_in(expert_dir, "hold_current"))
    if brief is None:
        return None
    try:
        corpus: Any = CorpusStore(name)
    except Exception:  # pragma: no cover - a missing corpus is not a consult failure
        corpus = None
    return build_consult_context(
        expert_name=name,
        question=query,
        brief=brief,
        result=load_study(part_in(expert_dir, "noticed")),
        corpus=corpus,
        semantic_ranking=semantic_ranking,
        routing_note=routing_note,
    )


def build_briefed_perspective(
    query: str,
    name: str,
    domain: str,
    perspective_cls: Any,
    semantic_ranking: list[str] | None = None,
    routing_note: str = "",
    *,
    prepared: PreparedConsultation | None = None,
) -> Any:
    """A perspective built from the study, or None to fall back to beliefs.

    Never raises. A malformed artifact on disk must degrade to the belief
    path rather than take the consult down with it.
    """
    if prepared is not None:
        from deepr.experts.consult_context import build_consult_context

        context = build_consult_context(
            expert_name=name, question=query, brief=None, result=None, corpus=None, prepared=prepared
        )
    else:
        return _build_loaded_perspective(query, name, domain, perspective_cls, semantic_ranking, routing_note)
    return _perspective_from_context(context, name, domain, perspective_cls)


def _build_loaded_perspective(
    query: str, name: str, domain: str, perspective_cls: Any, semantic_ranking: list[str] | None, routing_note: str
) -> Any:
    try:
        context = load_consult_context(query, name, semantic_ranking, routing_note)
    except Exception:  # pragma: no cover - defensive around on-disk artifacts
        logger.debug("consult context unavailable for %s", name, exc_info=True)
        return None
    if context is None:
        return None

    return _perspective_from_context(context, name, domain, perspective_cls, semantic_ranking)


def _perspective_from_context(
    context: Any, name: str, domain: str, perspective_cls: Any, semantic_ranking: list[str] | None = None
) -> Any:
    from deepr.experts.consult_context import render_consult_packet
    from deepr.experts.consult_prompt import brief_synthesis_blocks
    from deepr.experts.consult_support import recorded_statement

    return perspective_cls(
        expert_name=name,
        domain=domain,
        response=render_consult_packet(context),
        confidence=confidence_for_coverage(context.coverage),
        synthesis_blocks=brief_synthesis_blocks(context),
        context={
            "source": "brief",
            "finding_routing": "lexical+local-embedding" if semantic_ranking is not None else "lexical",
            "coverage": context.coverage,
            "study_fingerprint": context.study_fingerprint,
            "study_binding": context.study_binding,
            "studied_at": context.studied_at,
            "orientation": context.orientation,
            "positions": [position.to_dict() for position in context.positions],
            "passages": [
                {"sha256": sha, "origin": origin, "text": text, **context.source_observed.get(sha, {})}
                for sha, origin, text in context.sources
            ],
            "findings_anchored": sum(finding.is_grounded for finding in context.findings),
            "positions_included": len(context.positions),
            "findings_included": len(context.findings),
            "source_passages": len(context.sources),
            "evidence_chars": context.evidence_chars(),
            "support": list(context.support),
            "live": list(context.live),
            "unknown": list(context.unknown),
            "recorded_dissent": [
                text
                for text in (recorded_statement(position.unresolved_dissent) for position in context.positions)
                if text
            ],
        },
    )


def briefed_perspective_without_beliefs(
    query: str,
    name: str,
    domain: str,
    perspective_cls: Any,
    semantic_ranking: list[str] | None = None,
    routing_note: str = "",
) -> Any:
    """A perspective for an expert that has a brief and no belief ledger.

    acquire -> study -> brief never writes the claim ledger, because admission
    is a separate decision from reading. Consult gated its whole path on
    ``beliefs.json`` existing, so exactly that expert - corpus, findings and
    positions all on disk - answered "no stored belief context is available".
    """
    from deepr.experts.expert_layout import hold_current_path

    if not hold_current_path(name).exists():
        return None
    return build_briefed_perspective(query, name, domain, perspective_cls, semantic_ranking, routing_note)
