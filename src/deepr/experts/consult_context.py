"""What an expert brings to a conversation.

The consult path used to assemble its evidence from eight claim strings with
three source references each, truncated at 140 characters. That budget was set
when a claim ledger was all an expert had and context windows were small. It
was never revisited, so an expert with a retained corpus, a studied set of
findings and a formed brief walked into every conversation carrying under four
kilobytes of them.

This module assembles the real thing, in four layers:

    orientation   always present, never retrieved - where the field stands,
                  what is settled so the reader can skip it
    positions     where the expert landed, with the falsifier and the dissent
                  it did not resolve
    findings      the specifics a position compresses away
    sources       the retained passage, quoted rather than paraphrased

Two rules that shape the retrieval.

**Orientation is not retrieved.** It is small, it is always relevant, and it
is the move that makes a consultation worth more than a search: telling
someone which part of their question is already closed. Ranking it against a
query would sometimes drop it, which is the one thing it must never do.

**Positions pull their own support.** When a position ranks, its findings and
their corpus passages come with it whether or not they ranked separately.
That is what makes "why do you think that" answerable in the same turn
instead of the next one.

Scoring is deterministic token overlap. No embeddings, no model, no network,
so assembling context costs nothing and a consult that never reaches a model
still says something true about what the expert holds.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study_contracts import StudyFinding, StudyResult

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i if in is it its of on or "
    "should so than that the their them then there these they this to was were what when where "
    "which who why will with would you your".split()
)

_MAX_POSITIONS = 6
_MAX_FINDINGS = 24
_MAX_SOURCES = 8
_SOURCE_SPAN_CHARS = 2_000


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOPWORDS and len(w) > 2}


def _overlap(query: set[str], text: str) -> int:
    return len(query & _tokens(text))


@dataclass
class ConsultContext:
    """Everything the expert carries into one turn, with its provenance."""

    expert_name: str
    orientation: str = ""
    settled: list[str] = field(default_factory=list)
    live: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    findings: list[StudyFinding] = field(default_factory=list)
    sources: list[tuple[str, str, str]] = field(default_factory=list)
    """(sha, origin_key, passage) so a claim can be checked, not just asserted."""
    integrity_warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> str:
        """grounded, partial, or uncovered.

        A three-way answer rather than a yes/no, because "I have no position
        but here is what bears on it" is the useful thing an expert says when
        it cannot answer, and a binary gate cannot express it.
        """
        if any(p.is_grounded for p in self.positions):
            return "grounded"
        if self.findings or self.sources:
            return "partial"
        return "uncovered"

    @property
    def straddled_positions(self) -> list[Position]:
        """Ranked positions whose stances differ enough to be worth separating.

        When a question matches more than one position, answering the merged
        version is how a real distinction gets averaged into mush. Naming both
        and asking which one they are deciding is the reframe.
        """
        return self.positions[:2] if len(self.positions) > 1 else []

    def evidence_chars(self) -> int:
        """How much the expert is actually bringing. Reported, not guessed."""
        return (
            len(self.orientation)
            + sum(len(p.stance) + len(p.reasoning) for p in self.positions)
            + sum(len(f.title) for f in self.findings)
            + sum(len(passage) for _, _, passage in self.sources)
        )


def load_brief(path: Path) -> ExpertBrief | None:
    """Load a persisted brief, or None when the expert has never been briefed."""
    if not path.exists():
        return None
    try:
        return ExpertBrief.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def load_study(path: Path) -> StudyResult | None:
    if not path.exists():
        return None
    try:
        return StudyResult.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def rank_positions(question: str, brief: ExpertBrief) -> list[Position]:
    """Positions this question actually touches, best first.

    Unmatched positions are dropped rather than backfilled. Falling back to
    the highest-confidence positions regardless of relevance is how a system
    answers a question it has nothing to say about.
    """
    query = _tokens(question)
    if not query:
        return []
    scored = [
        (_overlap(query, f"{p.question} {p.stance} {p.reasoning}"), index, p) for index, p in enumerate(brief.positions)
    ]
    matched = [(score, index, p) for score, index, p in scored if score > 0]
    matched.sort(key=lambda item: (-item[0], item[1]))
    return [p for _, _, p in matched[:_MAX_POSITIONS]]


def _finding_text(finding: StudyFinding) -> str:
    payload = " ".join(str(v) for v in finding.payload.values() if isinstance(v, str))
    return f"{finding.title} {payload}"


def gather_findings(question: str, result: StudyResult, positions: list[Position]) -> list[StudyFinding]:
    """Findings the question matches, plus every finding the positions rest on.

    The second half is the point: support arrives with the position it
    supports, so the expert can show its work in the same breath.
    """
    cited = {fid for p in positions for fid in p.supported_by}
    by_id = {f.finding_id: f for f in result.findings if f.finding_id}
    carried = [by_id[fid] for fid in sorted(cited) if fid in by_id]

    query = _tokens(question)
    already = {f.finding_id for f in carried}
    scored = [
        (_overlap(query, _finding_text(f)), index, f)
        for index, f in enumerate(result.findings)
        if f.finding_id not in already
    ]
    matched = sorted((s for s in scored if s[0] > 0), key=lambda item: (-item[0], item[1]))
    room = max(0, _MAX_FINDINGS - len(carried))
    return carried + [f for _, _, f in matched[:room]]


def gather_sources(findings: list[StudyFinding], corpus: CorpusStore) -> list[tuple[str, str, str]]:
    """The retained passages behind these findings.

    Quoted rather than summarized. Any number, date or direct quotation in an
    answer should come from here, because the derived layers are where detail
    goes to get lost.
    """
    seen: list[tuple[str, str, str]] = []
    used: set[str] = set()
    for finding in findings:
        for sha in finding.corpus_shas:
            if sha in used or len(seen) >= _MAX_SOURCES:
                continue
            entry = corpus.entries.get(sha)
            text = corpus.read(sha)
            if entry is None or not text:
                continue
            used.add(sha)
            seen.append((sha, entry.origin_key, text[:_SOURCE_SPAN_CHARS]))
    return seen


def build_consult_context(
    *,
    expert_name: str,
    question: str,
    brief: ExpertBrief | None,
    result: StudyResult | None,
    corpus: CorpusStore | None,
) -> ConsultContext:
    """Assemble one turn's evidence. $0, deterministic, no model call."""
    context = ConsultContext(expert_name=expert_name)
    if brief is not None:
        context.orientation = brief.orientation
        context.settled = list(brief.state.settled)
        context.live = list(brief.state.live)
        context.unknown = list(brief.state.unknown)
        context.integrity_warnings = brief.integrity_warnings()
        context.limitations = list(brief.limitations)
        context.positions = rank_positions(question, brief)

    if result is not None:
        context.findings = gather_findings(question, result, context.positions)
        if corpus is not None:
            context.sources = gather_sources(context.findings, corpus)
    return context


def render_standing_header(context: ConsultContext) -> str:
    """The part that is always present, whatever was asked.

    Leads with what is settled. Telling someone which half of their question
    is already closed is the cheapest useful thing an expert does, and it
    cannot happen if this has to win a relevance ranking first.
    """
    lines: list[str] = []
    if context.orientation:
        lines += [f"Where {context.expert_name} stands, in brief:", context.orientation, ""]
    if context.settled:
        lines.append("Settled - do not spend the conversation here:")
        lines += [f"- {item}" for item in context.settled]
        lines.append("")
    if context.live:
        lines.append("Genuinely live, where an answer is a judgment and not a lookup:")
        lines += [f"- {item}" for item in context.live]
        lines.append("")
    if context.unknown:
        lines.append("Not known, by me or by the sources I hold:")
        lines += [f"- {item}" for item in context.unknown]
        lines.append("")
    if context.integrity_warnings:
        lines.append("Read anything I say knowing:")
        lines += [f"- {w}" for w in context.integrity_warnings]
        lines.append("")
    return "\n".join(lines).strip()
