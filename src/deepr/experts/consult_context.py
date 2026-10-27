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
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepr.experts.preparation_context import PreparedConsultation

from deepr.experts.brief_attribution import orientation_statements, render_orientation
from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.consult_support import bind_study, recorded_statement, support_for_positions
from deepr.experts.corpus_store import CorpusStore, observation_text
from deepr.experts.study_contracts import StudyFinding, StudyResult

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i if in is it its of on or "
    "should so than that the their them then there these they this to was were what when where "
    "which who why will with would you your".split()
)

_MAX_POSITIONS = 6
_MAX_FINDINGS = 24
_MAX_SEMANTIC_CANDIDATES = 24
_RRF_K = 60
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
    finding_sources: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    """Per-finding source windows, before shared-source condensation loses them."""
    reference_passages: list[tuple[str, str, str]] = field(default_factory=list)
    """Question-routed original passages, including details absent from study notes."""
    integrity_warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    support: list[dict[str, object]] = field(default_factory=list)
    """Per-position citation resolution. Empty until build_consult_context runs."""
    source_observed: dict[str, dict[str, str]] = field(default_factory=dict)
    """sha -> {"fetched_at", "publisher"} copied from the corpus index.

    Empty strings mean the index recorded nothing; they are never filled in.
    Contexts captured before this field existed restore with an empty mapping
    and keep their original rendering.
    """

    studied_at: str = ""
    study_fingerprint: str = ""
    """The brief's study identity; finding ids are only meaningful within it."""
    preparation_notice: str = ""
    study_binding: str = ""
    """matched, unbound, mismatch, or no_study, as resolved for this turn."""

    @property
    def coverage(self) -> str:
        """grounded, partial, or uncovered.

        Grounded means every selected position's cited findings belong to
        this study and a retained passage for each of them was read. A
        citation id alone is not that. One unresolved citation keeps the
        packet partial. Partial also covers a finding or passage with no
        resolved position.
        """
        if self.support and all(item.get("resolved") for item in self.support):
            return "grounded"
        if self.positions or self.findings or self.sources or self.reference_passages:
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
            + sum(len(passage) for _, _, passage in self.reference_passages)
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


def _fused_ranks(lexical: list[str], semantic: list[str]) -> dict[str, float]:
    """Reciprocal-rank fusion of two candidate orders. Ranks route; they decide nothing."""
    fused: dict[str, float] = {}
    for ranking in (lexical, semantic):
        for rank, finding_id in enumerate(ranking):
            fused[finding_id] = fused.get(finding_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    return fused


def gather_findings(
    question: str,
    result: StudyResult,
    positions: list[Position],
    *,
    additional_citations: list[str] | None = None,
    semantic_ranking: list[str] | None = None,
) -> list[StudyFinding]:
    """Findings the question matches, plus every finding the positions rest on.

    The second half is the point: support arrives with the position it
    supports, so the expert can show its work in the same breath.

    ``semantic_ranking`` is an optional order of finding ids by embedding
    similarity to the question. It is fused with the lexical order, so a
    finding phrased differently from the question can still be offered. It
    only chooses candidates; whether a finding is relevant stays with the
    answering model and review.
    """
    cited = {fid for p in positions for fid in p.supported_by}
    cited.update(additional_citations or [])
    by_id = {f.finding_id: f for f in result.findings if f.finding_id}
    query = _tokens(question)
    carried = [by_id[fid] for fid in sorted(cited) if fid in by_id]
    already = {f.finding_id for f in carried}
    scored = [
        (_overlap(query, _finding_text(f)), index, f)
        for index, f in enumerate(result.findings)
        if f.finding_id not in already
    ]
    matched = sorted((s for s in scored if s[0] > 0), key=lambda item: (-item[0], item[1]))
    room = max(0, _MAX_FINDINGS - len(carried))
    if semantic_ranking is None:
        selected = carried + [f for _, _, f in matched[:room]]
        # Support remains present, but alphabetical finding IDs must not put a
        # tangential position's bibliography ahead of the question's direct evidence.
        return sorted(selected, key=lambda finding: -_overlap(query, _finding_text(finding)))
    lexical = [f.finding_id for _, _, f in matched]
    semantic = [fid for fid in semantic_ranking if fid in by_id][:_MAX_SEMANTIC_CANDIDATES]
    fused = _fused_ranks(lexical, semantic)
    pool = sorted((fid for fid in fused if fid not in already), key=lambda fid: (-fused[fid], fid))
    selected = carried + [by_id[fid] for fid in pool[:room]]
    return sorted(selected, key=lambda finding: -fused.get(finding.finding_id, 0.0))


def _source_passage(text: str, anchors: list[str], max_chars: int) -> str:
    """Select literal anchor windows; matching locates bytes, not meaning."""
    if len(text) <= max_chars:
        return text
    spans: list[tuple[int, int]] = []
    remaining = max_chars
    separator = "\n[...]\n"
    for anchor in anchors:
        if not isinstance(anchor, str) or not anchor:
            continue
        pattern = r"\s+".join(re.escape(word) for word in anchor.split())
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is None:
            continue
        index, end = match.span()
        if any(start <= index and end <= stop for start, stop in spans):
            continue
        allowance = remaining - (len(separator) if spans else 0)
        if end - index > allowance:
            continue
        padding = min(120, (allowance - (end - index)) // 2)
        start, stop = max(0, index - padding), min(len(text), end + padding)
        remaining = allowance - (stop - start)
        spans.append((start, stop))
    return separator.join(text[start:stop] for start, stop in spans) if spans else text[:max_chars]


def gather_sources(findings: list[StudyFinding], corpus: CorpusStore) -> list[tuple[str, str, str]]:
    """The retained passages behind these findings.

    Quoted rather than summarized. Any number, date or direct quotation in an
    answer should come from here, because the derived layers are where detail
    goes to get lost.
    """
    seen: list[tuple[str, str, str]] = []
    anchors_by_sha: dict[str, list[str]] = {}
    for finding in findings:
        for sha in finding.corpus_shas:
            anchors_by_sha.setdefault(sha, []).extend(finding.anchors)
    for sha, anchors in anchors_by_sha.items():
        if len(seen) >= _MAX_SOURCES:
            break
        entry = corpus.entries.get(sha)
        text = corpus.read(sha)
        if entry is None or not text:
            continue
        seen.append((sha, entry.origin_key, _source_passage(text, anchors, _SOURCE_SPAN_CHARS)))
    return seen


def gather_finding_sources(context: ConsultContext, corpus: CorpusStore) -> dict[str, tuple[str, str, str]]:
    """Keep the actual supporting window for each finding in the selected sources."""
    retained = {sha: (origin, corpus.read(sha) or "") for sha, origin, _ in context.sources}
    windows = {}
    for finding in context.findings:
        for sha in finding.corpus_shas:
            if sha in retained:
                origin, text = retained[sha]
                windows[finding.finding_id] = (sha, origin, _source_passage(text, finding.anchors, 1200))
                break
    return windows


def gather_reference_passages(question: str, corpus: CorpusStore) -> list[tuple[str, str, str]]:
    """Route into a bounded reference library by overlap, never assert entailment."""
    query = _tokens(question)
    if not query:
        return []
    candidates = []
    for entry, text in corpus.load_study_material(max_chars=240_000):
        windows = [(_overlap(query, text[start : start + 1400]), start) for start in range(0, len(text), 800)]
        if windows:
            score, start = max(windows, key=lambda item: (item[0], -item[1]))
            if score:
                candidates.append((score, entry.sha256, entry.origin_key, text[start : start + 1400]))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [(sha, origin, passage) for _, sha, origin, passage in candidates[:4]]


def gather_source_observations(context: ConsultContext, corpus: CorpusStore) -> dict[str, dict[str, str]]:
    """Recorded fetch time and publisher for every delivered passage, verbatim.

    This copies index metadata. It does not infer a date from source text or
    a publisher from an origin key, and it says nothing about currentness.
    """
    shas = [sha for sha, _, _ in (*context.sources, *context.reference_passages, *context.finding_sources.values())]
    observed: dict[str, dict[str, str]] = {}
    for sha in shas:
        entry = corpus.entries.get(sha)
        observed[sha] = {
            "fetched_at": str(getattr(entry, "fetched_at", "") or "").strip(),
            "publisher": str(getattr(entry, "publisher", "") or "").strip(),
        }
    return observed


def observation_label(context: ConsultContext, sha: str) -> str:
    """Publisher and fetch time for one passage, or an explicit unrecorded marker."""
    if not context.source_observed:
        return ""
    observed = context.source_observed.get(sha) or {}
    return observation_text(observed.get("publisher", ""), observed.get("fetched_at", ""))


def passage_heading(context: ConsultContext, sha: str, origin: str) -> str:
    """``origin; publisher; fetched ...`` once observations were captured, else ``origin``."""
    label = observation_label(context, sha)
    return f"{origin}; {label}" if label else origin


def _fetch_day(value: str) -> str:
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return ""


def observation_window(context: ConsultContext) -> str:
    """The span of recorded fetch dates of the stored expert sources delivered.

    Scoped to stored copies: a recorded fetch time is when bytes were
    retained, not when the subject was last true, and it says nothing about
    observations made elsewhere in the same operation. Unrecorded or
    unparseable times are counted, never guessed.
    """
    if not context.source_observed:
        return ""
    days = sorted(day for item in context.source_observed.values() if (day := _fetch_day(item.get("fetched_at", ""))))
    total = len(context.source_observed)
    missing = total - len(days)
    if not days:
        span = f"retained-copy fetch time unrecorded for all {total}"
    else:
        span = f"retained copies fetched {days[0]}" + (f" to {days[-1]}" if days[-1] != days[0] else "")
        span += f" (unrecorded for {missing} of {total})" if missing else ""
    return f"Stored expert sources: {span}; stored research was not re-checked."


def build_consult_context(
    *,
    expert_name: str,
    question: str,
    brief: ExpertBrief | None,
    result: StudyResult | None,
    corpus: CorpusStore | None,
    prepared: PreparedConsultation | None = None,
    semantic_ranking: list[str] | None = None,
    routing_note: str = "",
) -> ConsultContext:
    """Assemble one turn's evidence. $0 and deterministic for the inputs given.

    No model is called here. A caller that ran a local embedding router passes
    its finding order as ``semantic_ranking`` and says so in ``routing_note``.
    """
    if prepared is not None:
        if prepared.capture.expert_name != expert_name or prepared.capture.question != question:
            raise ValueError("prepared context identity mismatch")
        context = prepared.capture.restore()
        context.preparation_notice = prepared.notice
        return context
    context = ConsultContext(expert_name=expert_name)
    if brief is not None:
        context.orientation = render_orientation(
            brief.orientation,
            brief.orientation_statements,
            binding=bind_study(brief, result),
            findings={f.finding_id: f.is_grounded for f in result.findings} if result else {},
        )
        context.settled = list(brief.state.settled)
        context.live = list(brief.state.live)
        context.unknown = list(brief.state.unknown)
        context.integrity_warnings = brief.integrity_warnings()
        context.limitations = list(brief.limitations)
        context.positions = rank_positions(question, brief)

    if result is not None:
        context.studied_at = result.started_at
        orientation_ids = (
            [
                fid
                for statement in orientation_statements(brief.orientation, brief.orientation_statements)
                for fid in statement.supported_by
            ]
            if brief and bind_study(brief, result) == "matched"
            else []
        )
        context.findings = gather_findings(
            question,
            result,
            context.positions,
            additional_citations=orientation_ids,
            semantic_ranking=semantic_ranking,
        )
        if corpus is not None:
            context.sources = gather_sources(context.findings, corpus)
            context.finding_sources = gather_finding_sources(context, corpus)
    if corpus is not None:
        context.reference_passages = gather_reference_passages(question, corpus)
        context.source_observed = gather_source_observations(context, corpus)
        context.limitations.append(
            "Local reference lookup searched at most 240,000 retained characters and selected at most four passages by text overlap; this is not a relevance or currentness verdict."
        )
    if routing_note:
        context.limitations.append(routing_note)
    context.study_fingerprint = brief.study_fingerprint if brief is not None else ""
    context.study_binding = bind_study(brief, result)
    context.support = support_for_positions(
        context.positions,
        brief=brief,
        result=result,
        passages=context.finding_sources,
    )
    return context


def _render_position_block(index: int, position: Position) -> list[str]:
    """One position, with the two things that make it a judgment not a claim."""
    band = position.likelihood_band
    lines = [f"{index}. {position.question or 'Position'}", f"   Stance: {position.stance}"]
    if position.reasoning:
        lines.append(f"   Because: {position.reasoning}")
    if band:
        lines.append(f"   Likelihood it holds: {position.likelihood} ({band[0]}-{band[1]}%)")
    if position.confidence:
        lines.append(f"   Confidence in that basis: {position.confidence}")
    dissent = recorded_statement(position.unresolved_dissent)
    if dissent:
        lines.append(f"   Does not resolve: {dissent}")
    revision = recorded_statement(position.would_change_my_mind)
    if revision:
        lines.append(f"   Would change my mind: {revision}")
        if position.is_registered_prediction:
            lines.append(
                f"   Scheduled check {position.falsifier_resolution_date}: {position.falsifier_resolution_criterion}"
            )
    else:
        lines.append("   No falsifier stated: treat as assertion, not judgment.")
    if position.is_single_origin:
        lines.append(
            f"   Rests on {position.supporting_documents} source(s) from one origin record, "
            "which reads as corroboration and is not."
        )
    return lines


def render_consult_packet(context: ConsultContext) -> str:
    """Everything the expert brings to this turn, in reading order.

    Orientation first, then where it landed, then the specifics, then the
    passages. A reader who stops after the first section still has the part
    that matters most, which is what is settled and therefore skippable.
    """
    blocks = [render_standing_header(context)]
    if context.reference_passages:
        blocks.append(
            "Reference library lookup (bounded original excerpts, not newly verified):\n\n"
            + "\n\n".join(
                f"--- {passage_heading(context, sha, origin)} ({sha}) ---\n{passage}"
                for sha, origin, passage in context.reference_passages
            )
        )

    if context.positions:
        lines = ["Where I land on what you asked:", ""]
        for index, position in enumerate(context.positions, 1):
            lines += _render_position_block(index, position)
            lines.append("")
        blocks.append("\n".join(lines).strip())
    elif context.coverage == "partial":
        blocks.append(
            "I have not formed a position on this, so take what follows as material rather than a "
            "view. It bears on your question and I have not reconciled it. If it is close enough "
            "to be worth settling, say so and I will read further and come back with a position."
        )
    else:
        blocks.append(_render_uncovered(context))

    if context.findings:
        lines = ["What my sources actually say:", ""]
        lines += [f"- [{f.finding_id}] {f.title}" for f in context.findings[:12]]
        blocks.append("\n".join(lines))

    if context.sources:
        window = observation_window(context)
        lines = ["Passages, so you can check rather than take my word:", *([window] if window else []), ""]
        for sha, origin, passage in context.sources[:4]:
            anchors = [
                anchor for finding in context.findings if sha in finding.corpus_shas for anchor in finding.anchors
            ]
            lines.append(f"--- {passage_heading(context, sha, origin)} ({sha[:12]}) ---")
            lines.append(_source_passage(passage, anchors, 1200))
            lines.append("")
        blocks.append("\n".join(lines).strip())

    return "\n\n".join(block for block in blocks if block)


def _render_uncovered(context: ConsultContext) -> str:
    """Say no, and then say what would turn it into a yes.

    Honest refusal that stops there leaves the asker where they started. What
    an expert who is glad to be asked adds is the route: what it would take to
    answer, and what nearby thing it does hold. Refusing usefully is still
    helping, and it is also the only way a refusal becomes work the expert can
    go and do.
    """
    lines = [
        "I do not hold a position on this. Inventing one from adjacent material would be worse "
        "than saying so, but I would like to be able to answer it."
    ]
    if context.live:
        lines.append("")
        lines.append("Nearest things I am already working on:")
        lines += [f"- {item}" for item in context.live[:3]]
    if context.unknown:
        lines.append("")
        lines.append("Already on my list of what I do not know:")
        lines += [f"- {item}" for item in context.unknown[:3]]
    lines.append("")
    lines.append(
        "What would let me answer: sources on this specific question, which is an acquire and "
        "re-study rather than a guess. Point me at material or ask me to go looking, and this "
        "becomes something I hold rather than something I decline."
    )
    return "\n".join(lines)


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
