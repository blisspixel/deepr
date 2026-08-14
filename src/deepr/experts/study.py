"""The study pass: read a retained corpus through several lenses.

This is the stage Deepr was missing. Acquisition brings material in and
extraction turns it into atomic claims, but nothing read the corpus *as a body*
and produced the things that make an expert worth consulting: how it works, what
breaks, where good sources disagree, what a practitioner would expect and does
not find.

Shape:

    corpus (retained) -> N independent lens calls -> typed findings -> anchored

Lenses are independent and are never asked to agree. Disagreement between two
lenses is a result, not an error to reconcile.

Boundaries, which are the whole reason this can be trusted:

- **Reads the corpus, never the belief store.** A pass that reasons over the
  expert's own prior conclusions is an echo chamber with extra steps.
- **Proposes, never writes.** This module returns findings. Admission is the
  caller's job, through the existing verifier and commit gates.
- **Anchors are checked mechanically.** Whether a quoted phrase appears in the
  retained text is form. Whether a finding is *good* is meaning, and this module
  does not decide it - an ungrounded finding is labeled, not deleted.
- **Model-agnostic.** The completion callable is injected, so the whole pass is
  unit-testable at $0 with no provider.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from deepr.experts.corpus_independence import measure_independence
from deepr.experts.corpus_store import CorpusEntry, CorpusStore
from deepr.experts.record_identity import finding_thread_id
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult
from deepr.experts.study_coverage import build_coverage_report
from deepr.experts.study_lenses import StudyLens, resolve_lenses
from deepr.utils.prompt_security import sanitize_untrusted_content

StudyCompletion = Callable[[str], Awaitable[str]]
"""prompt -> raw model text. Injected so this module owns no provider."""

ProgressCallback = Callable[[str], None]
"""Called before each model call, so a long run is not a silent one."""

CheckpointCallback = Callable[[StudyResult], None]
"""Called after each lens, so work already paid for survives an interruption."""


_CAPACITY_MARKERS = (
    "quota",
    "usage balance exhausted",
    "payment required",
    "402",
    "insufficient credit",
    "rate limit",
    "429",
)
"""Text that means the backend cannot be asked, rather than would not answer.

A string check because the completion callable is injected and the study pass
deliberately owns no provider - it cannot import a backend exception type
without acquiring the dependency the injection exists to avoid. The typed check
below is the real one; this catches the same condition arriving as a wrapped or
stringified error from a plan CLI's stderr.
"""


def _note_capacity_stop(
    result: StudyResult,
    exc: BaseException,
    *,
    lens: StudyLens,
    index: int,
    total: int,
    on_progress: ProgressCallback | None,
) -> None:
    """Record that the pass stopped short, and why, where a machine can see it.

    The outcomes already gathered are real - they were read before capacity ran
    out. What must not happen is the result reading as though the remaining
    lenses were asked and found nothing.
    """
    remaining = total - index + 1
    result.limitations.append(
        f"Capacity ran out during lens {index}/{total} ({lens.key}): {str(exc)[:160]}. "
        f"{remaining} lens(es) were never read, so this study is incomplete rather than thin. "
        "Resume once capacity returns; completed lenses will be reused."
    )
    if on_progress:
        on_progress(f"lens {index}/{total} {lens.key}: capacity exhausted, stopping")


def _is_capacity_failure(exc: BaseException) -> bool:
    """Whether this failure means the backend is unavailable, not unhelpful.

    The distinction decides whether a pass may continue. A model that answered
    in prose produced a genuinely partial result and the pass should carry on;
    a backend that has run out of quota will fail identically for every
    remaining call, and continuing only buys a thinner artifact that looks
    complete.
    """
    try:
        from deepr.backends.plan_quota.errors import PlanQuotaError

        if isinstance(exc, PlanQuotaError):
            return True
    except ImportError:
        pass
    text = str(exc).lower()
    return any(marker in text for marker in _CAPACITY_MARKERS)


def corpus_fingerprint(material: list[tuple[CorpusEntry, str]]) -> str:
    """A stable id for exactly the sources a pass read.

    Sorted shas, hashed. Adding a source changes it, so a lens outcome from
    before that source arrived can be recognized as stale rather than reused.
    """
    import hashlib

    shas = sorted(entry.sha256 for entry, _ in material)
    return hashlib.sha256("|".join(shas).encode("utf-8")).hexdigest()[:16]


def _lens_progress(
    on_progress: ProgressCallback | None,
    lens_key: str,
    index: int,
    total: int,
) -> ProgressCallback | None:
    """Label a lens's chunk progress with where the whole run has got to."""
    if on_progress is None:
        return None
    return lambda note: on_progress(f"lens {index}/{total} {lens_key}: {note}")


_MAX_ANCHOR_PROBE = 400
"""Anchors longer than this are prefix-matched: models paraphrase tails."""

_MIN_ANCHOR_LEN = 12
"""Shorter phrases match by coincidence and would make grounding meaningless."""

_DEFAULT_MAX_CORPUS_CHARS = 400_000

_DEFAULT_CHUNK_CHARS = 14_000
"""Corpus chars per model call.

Measured: at ~163k prompt chars both a 14B and a 24B abandoned their JSON output
contract and returned a prose summary; at ~43k prompt chars the same 24B
returned valid structured output in 27 seconds. The limit that matters is
instruction-following under prompt length, not the model's context window, and
it binds well below the window."""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize(text: str) -> str:
    """Collapse whitespace so anchor matching survives reflowing."""
    return re.sub(r"\s+", " ", text).strip().lower()


def build_study_prompt(lens: StudyLens, material: list[tuple[CorpusEntry, str]]) -> str:
    """Assemble one lens prompt over the corpus.

    Source text is sanitized: a corpus is untrusted input and may contain
    instructions aimed at the reader.
    """
    blocks: list[str] = []
    for entry, text in material:
        header = f"===== SOURCE {entry.sha256[:12]} | origin={entry.origin_key}"
        if entry.publisher:
            header += f" | publisher={entry.publisher}"
        if entry.title:
            header += f" | title={entry.title}"
        header += " ====="
        blocks.append(f"{header}\n{sanitize_untrusted_content(text)}")

    return (
        f"{lens.prompt}\n\n"
        "Every item you report must include an `anchors` array holding exact phrases "
        "copied verbatim from the corpus. Do not paraphrase an anchor. An item you "
        "cannot anchor should not be reported.\n\n"
        f'Return JSON only, with a single top-level key "{lens.output_field}" '
        "holding an array of objects. No prose before or after. No code fence.\n\n"
        "===== CORPUS BEGINS =====\n" + "\n\n".join(blocks) + "\n===== CORPUS ENDS =====\n"
    )


def extract_json_object(raw: str) -> tuple[dict[str, Any] | None, str]:
    """Unwrap a JSON object from model text.

    Deterministic string handling only. Reasoning-model think blocks and code
    fences are stripped; nothing here judges content.
    """
    text = (raw or "").strip()
    if not text:
        return None, "empty response"
    if "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()
    if "```" in text:
        for segment in text.split("```"):
            candidate = segment.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                text = candidate
                break
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None, "no JSON object in response"
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, "top-level JSON was not an object"
    return parsed, ""


def _anchor_matches(anchor: str, haystacks: list[tuple[str, str]]) -> str | None:
    """Return the sha of a source containing this anchor, or None.

    Exact-ish containment after whitespace normalization. This is deliberately
    strict: a loose match would let a plausible-sounding invention count as
    grounded, which is the failure this check exists to prevent.
    """
    probe = _normalize(anchor)
    if len(probe) < _MIN_ANCHOR_LEN:
        return None
    if len(probe) > _MAX_ANCHOR_PROBE:
        probe = probe[:_MAX_ANCHOR_PROBE]
    for sha, normalized_text in haystacks:
        if probe in normalized_text:
            return sha
    return None


_TITLE_KEYS: tuple[str, ...] = (
    "name",
    "title",
    "thread",
    "topic",
    "term",
    "landmark",
    "about",
    "concept",
    "claim",
    "tension",
    "description",
    "observation",
    "expected",
)
"""Keys a lens might use to name its subject, best first.

``source`` is deliberately absent. Lens prompts do not dictate key names, so
the model picks them, and at least one lens uses ``source`` for provenance
rather than subject. Titling from it produced forty findings all named after
the same corpus hash.
"""


def _is_provenance(value: str, corpus_shas: list[str]) -> bool:
    """True when a candidate title is really a source identifier.

    Titles are how the brief cites findings, so a title that is a hash makes
    every citation match every finding and citation checking stops meaning
    anything. Cheap to check, and it catches the general case rather than the
    one key that happened to collide.
    """
    candidate = value.strip().lower()
    return any(sha.startswith(candidate) or candidate.startswith(sha) for sha in corpus_shas if sha)


def _title_for(item: dict[str, Any], lens: StudyLens, corpus_shas: list[str] | None = None) -> str:
    """Best title for one finding.

    Each lens names its subject with whatever noun fits its question: a failure
    mode has a ``name``, an orientation thread has a ``thread``, a tension has a
    ``description``. Checking only for ``name`` renders a titleless stub, which
    is how a lens that worked perfectly can look broken in the notebook.
    """
    shas = corpus_shas or []
    for key in _TITLE_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip() and not _is_provenance(value, shas):
            return value.strip()[:200]
    return f"{lens.key} finding"


def _lens_items(lens: StudyLens, parsed: dict[str, Any]) -> list[Any]:
    """Pull the item array out of a lens response.

    Falls back to the first array under any key: a model that used a synonym for
    the contracted field still did the work, and discarding it would waste a
    call for a naming difference.
    """
    items = parsed.get(lens.output_field)
    if isinstance(items, list):
        return items
    for value in parsed.values():
        if isinstance(value, list):
            return value
    return []


def _read_anchors(item: dict[str, Any]) -> list[str]:
    raw = item.get("anchors") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(a) for a in raw if str(a).strip()]


def _ground_anchors(anchors: list[str], haystacks: list[tuple[str, str]]) -> tuple[int, int, list[str]]:
    """Count anchors that verifiably appear in the corpus. Returns (ok, missing, shas)."""
    grounded = 0
    ungrounded = 0
    shas: list[str] = []
    for anchor in anchors:
        sha = _anchor_matches(anchor, haystacks)
        if sha is None:
            ungrounded += 1
            continue
        grounded += 1
        if sha not in shas:
            shas.append(sha)
    return grounded, ungrounded, shas


def _absorb(findings: list[StudyFinding], fresh: list[StudyFinding]) -> None:
    """Add each fresh finding, merging it into an existing one of the same id.

    Content-derived ids make a re-sighting recognisable, which positional ids
    could not: the same finding surfacing in two chunks used to become two
    findings with two ordinals. Now it is one finding corroborated by two
    passages, and its ``corpus_shas`` accumulate.

    That accumulation is the point. A finding anchored in one source and a
    finding anchored in two are different evidential claims, and the second is
    what a lens genuinely comparing sources produces. Appending a duplicate
    would also put two records with one id in the same list, which every
    downstream lookup keyed by ``finding_id`` would then resolve arbitrarily.
    """
    by_id = {f.finding_id: f for f in findings}
    for candidate in fresh:
        existing = by_id.get(candidate.finding_id)
        if existing is None:
            findings.append(candidate)
            by_id[candidate.finding_id] = candidate
            continue
        for sha in candidate.corpus_shas:
            if sha not in existing.corpus_shas:
                existing.corpus_shas.append(sha)
        for anchor in candidate.anchors:
            if anchor not in existing.anchors:
                existing.anchors.append(anchor)
        if existing.payload != candidate.payload:
            # Same derived id, different content. Identity should have
            # prevented this; keep both so a collision cannot drop a finding.
            suffix = 2
            new_id = f"{candidate.finding_id}-{suffix}"
            while new_id in by_id:
                suffix += 1
                new_id = f"{candidate.finding_id}-{suffix}"
            candidate.finding_id = new_id
            findings.append(candidate)
            by_id[new_id] = candidate
            continue
        existing.grounded_anchor_count += candidate.grounded_anchor_count
        existing.ungrounded_anchor_count += candidate.ungrounded_anchor_count


def build_findings(
    lens: StudyLens,
    parsed: dict[str, Any],
    material: list[tuple[CorpusEntry, str]],
) -> list[StudyFinding]:
    """Turn one lens's parsed output into anchored findings."""
    haystacks = [(entry.sha256, _normalize(text)) for entry, text in material]
    findings: list[StudyFinding] = []
    for item in _lens_items(lens, parsed):
        if not isinstance(item, dict):
            continue
        anchors = _read_anchors(item)
        grounded, ungrounded, shas = _ground_anchors(anchors, haystacks)
        title = _title_for(item, lens, shas)
        payload = {k: v for k, v in item.items() if k != "anchors"}
        findings.append(
            StudyFinding(
                lens=lens.key,
                axis=lens.axis,
                kind=lens.output_field,
                # Derived from content, not from position in this list. The
                # positional form renumbered whenever a partial resume re-ran
                # one lens, so a brief citing `failure-30` silently repointed at
                # a different finding - and the citation still validated against
                # the id set, which is worse than failing.
                finding_id=finding_thread_id(
                    lens=lens.key,
                    title=title,
                    anchors=anchors,
                    payload=json.dumps(payload, sort_keys=True, default=str),
                ),
                title=title,
                payload=payload,
                anchors=anchors,
                grounded_anchor_count=grounded,
                ungrounded_anchor_count=ungrounded,
                corpus_shas=shas,
            )
        )
    return findings


async def _run_lenses(
    result: StudyResult,
    *,
    lenses: Any,
    chunks: list[list[tuple[CorpusEntry, str]]],
    material: list[tuple[CorpusEntry, str]],
    completion: StudyCompletion,
    resume_from: list[LensOutcome] | None,
    on_progress: ProgressCallback | None,
    checkpoint: CheckpointCallback | None,
) -> None:
    """Run each lens, reusing any an earlier pass already completed.

    Only ``ok`` and ``partial`` outcomes are reused. Reusing a parse failure
    would make one bad interruption permanent, which is the opposite of what
    resuming is for.
    """
    fingerprint = corpus_fingerprint(material)
    reusable = [o for o in (resume_from or []) if o.status in {"ok", "partial"}]
    # Fail closed. An outcome that cannot say which corpus it read is stale by
    # definition: trusting it was the fail-open branch of this guard, and it
    # defeated exactly what the fingerprint exists for. Measured on a live
    # expert - every outcome on disk carried an empty fingerprint, so every
    # lens was reused unconditionally however much the corpus had grown.
    stale = [o for o in reusable if o.corpus_fingerprint != fingerprint]
    done = {o.lens: o for o in reusable if o.corpus_fingerprint == fingerprint}
    if done:
        result.limitations.append(f"Resumed: {len(done)} lens(es) reused from an earlier run and not re-read.")
    if stale:
        result.limitations.append(
            f"{len(stale)} lens(es) from an earlier run were re-read because they could not be "
            "shown to have read this corpus. Reusing them would have carried findings that never "
            "saw the new sources."
        )

    for index, lens in enumerate(lenses, 1):
        if (earlier := done.get(lens.key)) is not None:
            result.outcomes.append(earlier)
            if on_progress:
                on_progress(f"lens {index}/{len(lenses)} {lens.key}: reused from an earlier run")
            continue

        started = time.monotonic()
        try:
            outcome = await _run_lens_over_chunks(
                lens,
                chunks,
                material,
                completion,
                on_progress=_lens_progress(on_progress, lens.key, index, len(lenses)),
            )
        except Exception as exc:
            if not _is_capacity_failure(exc):
                raise
            _note_capacity_stop(result, exc, lens=lens, index=index, total=len(lenses), on_progress=on_progress)
            break
        outcome.elapsed_s = time.monotonic() - started
        outcome.corpus_fingerprint = fingerprint
        result.outcomes.append(outcome)
        if on_progress:
            grounded = sum(1 for f in outcome.findings if f.is_grounded)
            on_progress(
                f"lens {index}/{len(lenses)} {lens.key}: {len(outcome.findings)} finding(s), "
                f"{grounded} anchored, {outcome.elapsed_s:.0f}s"
            )
        if checkpoint is not None:
            # Per lens rather than at the end, so an interruption costs one
            # lens instead of the whole pass.
            checkpoint(result)


async def run_study(
    *,
    expert_name: str,
    corpus: CorpusStore,
    completion: StudyCompletion,
    lens_keys: list[str] | tuple[str, ...] | None = None,
    max_corpus_chars: int = _DEFAULT_MAX_CORPUS_CHARS,
    chunk_chars: int = _DEFAULT_CHUNK_CHARS,
    capacity_source: str = "",
    model: str = "",
    on_progress: ProgressCallback | None = None,
    checkpoint: CheckpointCallback | None = None,
    resume_from: list[LensOutcome] | None = None,
) -> StudyResult:
    """Run every requested lens over the retained corpus.

    A lens that fails is recorded and the pass continues: one bad parse should
    not discard the work of five other lenses.

    Recovery is structural, not conversational. ``checkpoint`` is called after
    each lens with the result so far, and ``resume_from`` carries completed
    lenses back in, so a pass killed at lens seven of eight resumes rather than
    restarting. Without it every interruption costs the whole run again, which
    on a real corpus is tens of model calls that already succeeded.

    ``on_progress`` is called before each model call. A chunked study over a
    real corpus is tens of calls and runs for many minutes; without it the run
    is silent, and a silent run is indistinguishable from a hung one.
    """
    lenses = resolve_lenses(lens_keys)
    material = corpus.load_study_material(max_chars=max_corpus_chars)
    stats = corpus.stats()
    started = time.monotonic()

    result = StudyResult(
        expert_name=expert_name,
        corpus_sources=len(material),
        corpus_origins=stats.distinct_origins,
        corpus_chars=sum(len(text) for _, text in material),
        capacity_source=capacity_source,
        model=model,
        started_at=_utc_now_iso(),
    )

    if not material:
        result.limitations.append(
            "Corpus is empty. Retain sources with `expert absorb` before studying; "
            "a study pass over nothing produces nothing."
        )
        result.elapsed_s = time.monotonic() - started
        return result

    if stats.active_count > len(material):
        result.limitations.append(
            f"Studied {len(material)} of {stats.active_count} retained sources "
            f"(corpus budget {max_corpus_chars} chars). Findings may miss material."
        )
    # Counted by origin rather than by document, because a document count is
    # not an evidence count and every downstream corroboration number is built
    # on this one.
    result.independence = measure_independence(corpus.active_entries())
    result.limitations.extend(result.independence.concerns())

    # One call per lens per chunk. A lens handed a whole corpus stops following
    # its output contract - measured, a 163k-char prompt produced a prose
    # summary where a 43k-char prompt produced valid structured output from the
    # same model - so the corpus is sliced and findings are merged.
    chunks = corpus.iter_study_chunks(chunk_chars=chunk_chars, max_chars=max_corpus_chars) or [material]
    if len(chunks) > 1:
        result.limitations.append(
            f"Corpus was read in {len(chunks)} chunk(s) of up to {chunk_chars} chars. "
            "Each lens saw one chunk at a time, so cross-chunk connections may be missed."
        )

    await _run_lenses(
        result,
        lenses=lenses,
        chunks=chunks,
        material=material,
        completion=completion,
        resume_from=resume_from,
        on_progress=on_progress,
        checkpoint=checkpoint,
    )

    result.elapsed_s = time.monotonic() - started
    ungrounded = sum(f.ungrounded_anchor_count for f in result.findings)
    if ungrounded:
        result.limitations.append(
            f"{ungrounded} quoted anchor(s) were not found in the retained corpus. "
            "Those findings are labeled ungrounded, not removed; review before use."
        )
    # A finding with no anchors at all contributes zero to the count above, so
    # the warning could not fire for the worst case: a pass that ignored the
    # anchor contract entirely. Nothing verifiable came back, and that has to
    # be louder than silence.
    if result.findings and not result.grounded_findings:
        result.limitations.append(
            f"None of the {len(result.findings)} finding(s) could be verified against the "
            "retained corpus. Treat this pass as unusable rather than partial."
        )
    if len(result.findings) > 1 and not result.cross_source_findings:
        result.limitations.append(
            "No finding draws on more than one source, so nothing here compares sources. "
            "Disagreement reported by this pass is disagreement within a single document."
        )

    # Coverage, not just output volume. Relevance-driven reading reproduces
    # shared-information bias: what many sources say gets surfaced, and the lone
    # source that would change the conclusion gets buried. Report what was
    # consulted and what was not.
    result.coverage = build_coverage_report(
        studied=material,
        findings=result.findings,
        stats=stats,
        all_active=corpus.active_entries(),
    )
    result.limitations.extend(result.coverage.concerns())
    return result


async def _run_lens_over_chunks(
    lens: StudyLens,
    chunks: list[list[tuple[CorpusEntry, str]]],
    material: list[tuple[CorpusEntry, str]],
    completion: StudyCompletion,
    on_progress: ProgressCallback | None = None,
) -> LensOutcome:
    """Run one lens across every chunk, merging findings.

    A chunk that fails does not discard the chunks that succeeded: partial
    findings from a large corpus beat none. The outcome is ``ok`` when any chunk
    parsed, and carries a note about the ones that did not.
    """
    findings: list[StudyFinding] = []
    failures: list[str] = []

    for index, chunk in enumerate(chunks, 1):
        if on_progress:
            on_progress(f"chunk {index}/{len(chunks)}")
        prompt = build_study_prompt(lens, chunk)
        try:
            raw = await completion(prompt)
        except Exception as exc:
            if _is_capacity_failure(exc):
                # Stop the whole pass. Catching this as a per-chunk failure kept
                # calling a dead backend for every remaining chunk and lens and
                # then wrote a complete-looking study.json whose findings were
                # thin, with the reason recorded only as prose in `limitations`
                # that no downstream code reads. `brief` then read it as truth.
                #
                # Measured: a study "completed" with 44 findings from two of
                # eight lenses after the backend exhausted mid-run, and nothing
                # in the artifact said so in a way a machine could act on.
                #
                # "The corpus had nothing to say" and "I could not ask" are
                # different results, and the difference has to survive into the
                # artifact rather than being flattened into a failure count.
                raise
            failures.append(f"chunk {index}: {str(exc)[:160]}")
            continue

        parsed, error = extract_json_object(raw)
        if parsed is None:
            # Include what actually came back. "no JSON object in response" is
            # true and useless: it does not distinguish a model that answered in
            # prose, one that was cut off mid-structure, and one that returned
            # nothing at all, and those need different fixes.
            snippet = " ".join((raw or "").split())[:160]
            failures.append(f"chunk {index}: {error}. Began: {snippet!r}" if snippet else f"chunk {index}: {error}")
            continue

        # Ground against the chunk the lens was actually shown, not the whole
        # corpus. Grounding against `material` let an anchor resolve to
        # whichever source sorted first among those containing the phrase, so
        # a finding could be credited to a document the lens never read. Shared
        # boilerplate makes that the common case, not an edge case, and the
        # coverage report then reports the true source as untouched.
        _absorb(findings, build_findings(lens, parsed, chunk))

    if findings or not failures:
        detail = f"{len(failures)} of {len(chunks)} chunk(s) failed: " + "; ".join(failures[:2]) if failures else ""
        # "ok" with nine of ten chunks failed is what a scheduler reads as a
        # clean run. Partial is its own status so the exit code can say so.
        status = "partial" if failures else "ok"
        return LensOutcome(
            lens=lens.key,
            axis=lens.axis,
            status=status,
            findings=findings,
            detail=detail,
            chunks_total=len(chunks),
            chunks_failed=len(failures),
        )
    return LensOutcome(
        lens=lens.key,
        axis=lens.axis,
        status="parse_failed",
        detail="; ".join(failures[:3]),
    )
