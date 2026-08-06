"""Build a consultable brief from study findings.

Study produces findings about material. A brief is what an expert carries into a
conversation: where the field stands, what is settled so you can skip it, where
they land and why, and what would change their mind.

This is the one stage that is allowed to form a view. Everything before it
reports; this synthesizes. That makes it the stage most able to mislead, so it
runs under three constraints:

**It runs after independent lenses, never between them.** Lenses that see each
other's output converge, and the convergence is not agreement - social influence
collapses estimate diversity without improving accuracy, and consensus-seeking
deliberation lands near the average rather than the best. Independence first,
synthesis strictly afterwards.

**It must preserve what it cannot resolve.** Every intelligence post-mortem
examined found the correct answer already present in the system and smoothed
away in aggregation. A position that resolves a genuine disagreement by not
mentioning it is the documented failure, not a cleaner product.

**Every position carries a falsifier and its supporting findings.** A stance
with nothing that would overturn it is an assertion. A stance that cannot name
what it rests on cannot answer "why do you think that", which is the second
question anyone asks an expert.

The model call is injected, so the whole builder is unit-testable at $0.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from deepr.experts.brief_contracts import (
    AnticipatedQuestion,
    ExpertBrief,
    Position,
    SettledState,
    SourceCredibility,
)
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study_contracts import StudyFinding, StudyResult

BriefCompletion = Callable[[str], Awaitable[str]]

_MAX_FINDINGS_IN_PROMPT = 120
_MAX_FIELD_CHARS = 600


def _render_finding(finding: StudyFinding) -> str:
    """One finding as a compact line the synthesis can cite by title."""
    parts = [f"[{finding.lens}] {finding.title}"]
    for key, value in finding.payload.items():
        if key in {"anchors", "name", "title", "thread"}:
            continue
        text = "; ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        text = " ".join(text.split())[:_MAX_FIELD_CHARS]
        if text:
            parts.append(f"  {key}: {text}")
    if not finding.is_grounded:
        parts.append("  (UNVERIFIED: quoted support not found in the corpus)")
    return "\n".join(parts)


def build_brief_prompt(result: StudyResult, *, expert_name: str, domain: str = "") -> str:
    """Assemble the synthesis prompt from independent findings."""
    findings = result.findings[:_MAX_FINDINGS_IN_PROMPT]
    rendered = "\n".join(_render_finding(f) for f in findings)
    contested = [f for f in result.findings if f.lens == "contention"]

    dissent_note = (
        f"\n{len(contested)} finding(s) came from the contention lens, which looks for disagreement "
        "between sources. Any position touching those must state what it does not resolve.\n"
        if contested
        else "\nNo contention findings were produced. Do not manufacture disagreement to fill the field.\n"
    )

    return f"""You are preparing a briefing on "{expert_name}"{f" ({domain})" if domain else ""}.

Below are findings produced by several independent analytical passes over a source corpus. Your
job is not to summarize them. It is to produce what an expert carries into a conversation: where
things stand, what is settled so a reader can skip it, where you land and why, and what would
change your mind.

Rules that make this honest rather than confident-sounding:

- Every position must cite the finding titles it rests on, so "why do you think that" is
  answerable. Cite titles exactly as written below.
- Every position must state an observation that would overturn it. A position with no falsifier
  is an assertion; do not report one.
- Where the findings disagree, say what you did not resolve. Do not average disagreement into a
  middle position. Unresolved disagreement is a legitimate and useful output.
- Separate what is settled, what is live, and what is genuinely unknown. Refusing to spend a
  reader's time on resolved questions is most of the value here.
- Do not introduce claims that are not supported by the findings below.
{dissent_note}
Return JSON only, no prose outside it, with this shape:

{{
  "orientation": "the sixty-second version a newcomer needs before asking anything",
  "positions": [
    {{"question": "", "stance": "", "reasoning": "",
      "would_change_my_mind": "", "supported_by": ["exact finding title"],
      "unresolved_dissent": "", "confidence_basis": ""}}
  ],
  "state": {{"settled": [""], "live": [""], "unknown": [""]}},
  "key_quantities": ["the numbers that anchor discussion here"],
  "anticipated_questions": [
    {{"question": "", "answer": "", "why_asked": "", "supported_by": [""]}}
  ],
  "common_failures": ["what people try first that does not work, and why"]
}}

===== FINDINGS BEGIN =====
{rendered}
===== FINDINGS END =====
"""


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [" ".join(str(v).split()) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [" ".join(value.split())]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def build_credibility(corpus: CorpusStore) -> list[SourceCredibility]:
    """Report evidential depth per origin, not citation count.

    Several sources from one publisher are one publisher's authority, however
    many pages they came from.
    """
    rows: list[SourceCredibility] = []
    for origin in sorted(corpus.distinct_origins()):
        entries = [e for e in corpus.entries_for_origin(origin) if e.is_active]
        if not entries:
            continue
        rows.append(
            SourceCredibility(
                origin=origin,
                source_count=len(entries),
                trust_class=entries[0].trust_class,
                is_sole_root=len(entries) > 1,
                note=(
                    f"{len(entries)} sources from one publisher; repetition here is not independent corroboration."
                    if len(entries) > 1
                    else ""
                ),
            )
        )
    return rows


def _positions_from(raw_positions: Any, known_titles: set[str]) -> list[Position]:
    """Build positions, keeping only citations that name a real finding.

    A position citing something that does not exist cannot answer "why do you
    think that", and keeping the citation would make it look like it could.
    """
    positions: list[Position] = []
    for raw in raw_positions or []:
        if not isinstance(raw, dict):
            continue
        positions.append(
            Position(
                question=_text(raw.get("question")),
                stance=_text(raw.get("stance")),
                reasoning=_text(raw.get("reasoning")),
                would_change_my_mind=_text(raw.get("would_change_my_mind")),
                supported_by=[t for t in _as_list(raw.get("supported_by")) if t in known_titles],
                unresolved_dissent=_text(raw.get("unresolved_dissent")),
                confidence_basis=_text(raw.get("confidence_basis")),
            )
        )
    return positions


def assemble_brief(
    parsed: dict[str, Any],
    *,
    expert_name: str,
    result: StudyResult,
    corpus: CorpusStore,
) -> ExpertBrief:
    """Turn a parsed synthesis into a brief, keeping only verifiable citations."""
    known_titles = {f.title for f in result.findings}

    positions = _positions_from(parsed.get("positions"), known_titles)

    questions = [
        AnticipatedQuestion(
            question=_text(raw.get("question")),
            answer=_text(raw.get("answer")),
            why_asked=_text(raw.get("why_asked")),
            supported_by=[t for t in _as_list(raw.get("supported_by")) if t in known_titles],
        )
        for raw in (parsed.get("anticipated_questions") or [])
        if isinstance(raw, dict) and _text(raw.get("question"))
    ]

    raw_state = parsed.get("state") or {}
    state = SettledState(
        settled=_as_list(raw_state.get("settled")) if isinstance(raw_state, dict) else [],
        live=_as_list(raw_state.get("live")) if isinstance(raw_state, dict) else [],
        unknown=_as_list(raw_state.get("unknown")) if isinstance(raw_state, dict) else [],
    )

    brief = ExpertBrief(
        expert_name=expert_name,
        orientation=_text(parsed.get("orientation")),
        positions=[p for p in positions if p.stance],
        state=state,
        key_quantities=_as_list(parsed.get("key_quantities")),
        anticipated_questions=questions,
        common_failures=_as_list(parsed.get("common_failures")),
        credibility=build_credibility(corpus),
        generated_from_findings=len(result.findings),
    )

    ungrounded = [f for f in result.findings if not f.is_grounded]
    if ungrounded:
        brief.limitations.append(
            f"{len(ungrounded)} of {len(result.findings)} findings were not verifiable against the "
            "retained corpus. Positions resting on them inherit that."
        )
    brief.limitations.extend(result.limitations)
    return brief


async def build_brief(
    *,
    expert_name: str,
    result: StudyResult,
    corpus: CorpusStore,
    completion: BriefCompletion,
    domain: str = "",
) -> ExpertBrief:
    """Synthesize one brief. Returns an empty brief rather than raising."""
    from deepr.experts.study import extract_json_object

    if not result.findings:
        brief = ExpertBrief(expert_name=expert_name)
        brief.limitations.append(
            "No study findings to brief from. Run `expert study` first; a brief over nothing "
            "would be invention rather than synthesis."
        )
        return brief

    prompt = build_brief_prompt(result, expert_name=expert_name, domain=domain)
    try:
        raw = await completion(prompt)
    except Exception as exc:
        brief = ExpertBrief(expert_name=expert_name, generated_from_findings=len(result.findings))
        brief.limitations.append(f"Synthesis call failed: {str(exc)[:200]}")
        return brief

    parsed, error = extract_json_object(raw)
    if parsed is None:
        brief = ExpertBrief(expert_name=expert_name, generated_from_findings=len(result.findings))
        snippet = " ".join((raw or "").split())[:200]
        brief.limitations.append(f"Synthesis did not return usable JSON ({error}). Began: {snippet!r}")
        return brief

    return assemble_brief(parsed, expert_name=expert_name, result=result, corpus=corpus)


def _render_positions(brief: ExpertBrief) -> list[str]:
    """Render each position with what it rests on and what would overturn it."""
    if not brief.positions:
        return []
    lines = ["## Where I land, and why", ""]
    for index, position in enumerate(brief.positions, 1):
        lines.append(f"{index}. **{position.question or 'Position'}**")
        lines.append(f"   - Stance: {position.stance}")
        if position.reasoning:
            lines.append(f"   - Because: {position.reasoning}")
        if position.confidence_basis:
            lines.append(f"   - Confidence rests on: {position.confidence_basis}")
        if position.unresolved_dissent:
            lines.append(f"   - **Does not resolve**: {position.unresolved_dissent}")
        if position.would_change_my_mind:
            lines.append(f"   - Would change my mind: {position.would_change_my_mind}")
        else:
            lines.append("   - **No falsifier stated**: treat as assertion, not judgment.")
        if position.supported_by:
            lines.append(f"   - Rests on: {'; '.join(position.supported_by[:4])}")
        lines.append("")
    return lines


def _render_state(brief: ExpertBrief) -> list[str]:
    """Settled / live / unknown. Telling a reader what to skip is most of the value."""
    if not (brief.state.settled or brief.state.live or brief.state.unknown):
        return []
    lines = ["## Settled, live, unknown", ""]
    for label, items in (
        ("Settled (skip these)", brief.state.settled),
        ("Live", brief.state.live),
        ("Genuinely unknown", brief.state.unknown),
    ):
        if items:
            lines.append(f"**{label}**")
            lines.extend(f"- {item}" for item in items)
            lines.append("")
    return lines


def _render_lists(brief: ExpertBrief) -> list[str]:
    lines: list[str] = []
    for heading, items in (
        ("## The numbers that matter", brief.key_quantities),
        ("## What people try that does not work", brief.common_failures),
    ):
        if items:
            lines.extend([heading, ""])
            lines.extend(f"- {item}" for item in items)
            lines.append("")
    return lines


def _render_questions(brief: ExpertBrief) -> list[str]:
    if not brief.anticipated_questions:
        return []
    lines = ["## Questions I expect", ""]
    for question in brief.anticipated_questions:
        lines.append(f"**{question.question}**")
        lines.append(question.answer)
        if question.why_asked:
            lines.append(f"_Asked because: {question.why_asked}_")
        lines.append("")
    return lines


def _render_credibility(brief: ExpertBrief) -> list[str]:
    """Evidential depth per origin, not citation count."""
    if not brief.credibility:
        return []
    lines = ["## Who this rests on", "", "| Origin | Sources | Trust | Note |", "|---|---|---|---|"]
    lines.extend(
        f"| {row.origin} | {row.source_count} | {row.trust_class} | {row.note or '-'} |" for row in brief.credibility
    )
    lines.append("")
    return lines


def render_brief(brief: ExpertBrief) -> str:
    """Render the brief for reading. Bottom line first."""
    lines = [f"# {brief.expert_name}: brief", ""]
    if brief.orientation:
        lines.extend(["## In sixty seconds", "", brief.orientation, ""])

    lines.extend(_render_positions(brief))

    lines.extend(_render_state(brief))
    lines.extend(_render_lists(brief))
    lines.extend(_render_questions(brief))
    lines.extend(_render_credibility(brief))

    warnings = brief.integrity_warnings()
    if warnings:
        lines.extend(["## Read this brief knowing", ""])
        lines.extend(f"- {w}" for w in warnings)
        lines.append("")

    if brief.limitations:
        lines.extend(["## Limitations", ""])
        lines.extend(f"- {item}" for item in brief.limitations)
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "Derived from study findings over a retained corpus. Positions are the expert's "
            "reading of that evidence, not verified fact; each states what would overturn it.",
            "",
        ]
    )
    return "\n".join(lines)
