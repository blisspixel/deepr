"""Ground expert chat in the maintained belief graph rather than a flat snapshot.

Chat historically grounded its system message on ``worldview.json`` - a synthesis
snapshot whose ``confidence`` is whatever it was when the synthesis ran. The
``BeliefStore`` is the maintained state: its confidences decay, are capped by
trust floors, carry a grounding assurance stamp, and know which beliefs are
contested. Grounding chat on the store means the expert answers from what it
currently believes, not from what it believed at the last synthesis.

Wiring this also closes a dormant lifecycle gap. ``BeliefStore.record_retrieval``
had no production caller, so ``last_retrieved_at`` was always unset and the
"usage protects a belief from archival" gate in ``archive_candidates`` could
never fire. Recording retrieval here restores that protection for beliefs that
are actually load-bearing in answers.

The read-only contract is preserved. Building the summary opens the store
read-only and writes nothing; recording usage is a separate, explicit call that
the caller makes only from an already-mutating chat turn. The pure read-side
query surface (validate, why, digest, contested, what-changed) is untouched, so
MCP READ_ONLY mode keeps its guarantee.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Kept small on purpose: the system message is a standing context header, not a
# retrieval surface. Five is what the worldview path showed, so the swap changes
# the source of truth without changing how much context the model receives.
DEFAULT_BELIEF_LIMIT = 5


@dataclass(frozen=True)
class StoredBeliefGrounding:
    """A system-message summary plus the belief ids it was built from."""

    summary: str
    belief_ids: list[str] = field(default_factory=list)


def _beliefs_path(expert_name: str) -> Path:
    from deepr.experts.paths import canonical_expert_dir

    return canonical_expert_dir(expert_name) / "beliefs" / "beliefs.json"


def _belief_line(belief: Any) -> str:
    """One disclosure line: claim, current confidence, and trust signals.

    Current confidence is the decayed, trust-capped value, so a stale belief
    reads as stale here even when the stored number was once high.
    """
    from deepr.experts.maker_checker import is_verified_assurance

    confidence = float(belief.get_current_confidence())
    line = f"  - {belief.claim} (confidence: {confidence:.0%}"
    if is_verified_assurance(getattr(belief, "grounding_assurance", "")):
        line += ", verified"
    if getattr(belief, "contradictions_with", None):
        line += ", contested"
    return line + ")"


def build_stored_belief_grounding(
    expert_name: str,
    *,
    limit: int = DEFAULT_BELIEF_LIMIT,
) -> StoredBeliefGrounding | None:
    """Summarize the expert's strongest current beliefs for a system message.

    Returns ``None`` when the expert has no belief store or no beliefs, so the
    caller can fall back to the worldview snapshot. Opens the store read-only
    and never writes.
    """
    beliefs_path = _beliefs_path(expert_name)
    if not beliefs_path.exists():
        return None

    try:
        from deepr.experts.beliefs import BeliefStore

        store = BeliefStore(expert_name, read_only=True, read_path=beliefs_path)
        ranked = sorted(
            store.beliefs.values(),
            key=lambda belief: (-belief.get_current_confidence(), belief.claim),
        )[:limit]
    except Exception as exc:  # pragma: no cover - defensive: never break chat on a bad store
        logger.debug("Stored belief grounding unavailable for %s: %s", expert_name, exc)
        return None

    if not ranked:
        return None

    lines = [
        "YOUR CURRENT BELIEFS (from your maintained belief graph):",
        "",
        "What you believe now, with confidence after decay and trust limits:",
    ]
    lines.extend(_belief_line(belief) for belief in ranked)
    lines.append("")
    lines.append(
        "These are your maintained beliefs, not a past snapshot. A contested belief "
        "has a recorded counter-belief; say so rather than presenting it as settled."
    )
    return StoredBeliefGrounding(summary="\n".join(lines) + "\n", belief_ids=[b.id for b in ranked])


def record_grounded_retrieval(expert_name: str, belief_ids: list[str]) -> int:
    """Record that these beliefs were load-bearing in an answer.

    Call only from an already-mutating chat turn - never from a read-only or
    MCP READ_ONLY surface. Failures are swallowed: usage salience is telemetry
    for the archival lifecycle, and losing a tally must never fail a chat turn.

    Returns the number of beliefs whose counters were updated.
    """
    if not belief_ids:
        return 0
    beliefs_path = _beliefs_path(expert_name)
    if not beliefs_path.exists():
        return 0
    try:
        from deepr.experts.beliefs import BeliefStore

        # A writable store resolves the same canonical beliefs directory itself;
        # read_path is read-only-only by contract.
        store = BeliefStore(expert_name)
        return store.record_retrieval(belief_ids, context="chat grounding")
    except Exception as exc:  # pragma: no cover - defensive: telemetry must not break chat
        logger.debug("Could not record belief retrieval for %s: %s", expert_name, exc)
        return 0
