"""Stage-resolved correction-survival diagnostic (#259).

The question is whether an expert's later advice uses a credible correction
while keeping what stayed valid, and when it does not, where the evidence was
lost: in the source world, the study, the brief synthesis input, consult
retrieval, the final prompt boundary, or the answer itself.

Each frozen case runs in three arms with the same answer completion and the
same prompt allowance:

- ``production``: the shipped path. Study findings, ``build_brief`` with the
  world's fixture synthesis, ``build_consult_context``, then
  ``build_synthesis_packet``.
- ``oracle_packet``: the obligation evidence handed over directly through the
  same packer. Related qualifications outside those targeted obligations can
  still be absent; inspect the actual prompt before locating a failure.
- ``fresh_sources``: no memory, the world's original sources as reference
  passages for a descriptive fresh-read comparison.

For every obligation the run records mechanical stage receipts: ids, hashes
and selection membership. Whether an answer used the evidence well is never
computed here. It stays ``unreviewed`` until an accountable reviewer's label
is bound to the exact answer hash. Word overlap and citation strings are not
verdicts (``docs/plans/AGENTIC_BALANCE.md``).

The first increment answers with an injected completion; the CLI uses a fixed
mock that makes no call. It establishes transport and accounting only. A
later local semantic run needs its own approved limits and is out of scope.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from deepr.evals.correction_survival_cases import (
    CASE_SET_VERSION,
    CASES,
    RUBRIC,
    Case,
    Obligation,
    World,
    case_set_sha256,
    source_inventory,
    source_inventory_sha256,
    world,
)
from deepr.evals.correction_survival_cases import (
    distractor_sources as distractor_sources,
)
from deepr.evals.correction_survival_review import bind_review_labels as bind_review_labels
from deepr.evals.correction_survival_review import blinded_review_packet as blinded_review_packet

RUN_SCHEMA = "deepr.eval.correction-survival-run.v1"
REPORT_SCHEMA = "deepr.eval.correction-survival-report.v1"
ARMS: tuple[str, ...] = ("production", "oracle_packet", "fresh_sources")
STAGES: tuple[str, ...] = ("source", "study", "briefing", "retrieval", "delivery", "answer")
COMPLETE_MARKER = "COMPLETE.json"
MOCK_ANSWER = "MOCK ANSWER: no model was called; this attempt proves transport and accounting only."

AnswerCompletion = Callable[[str], Awaitable[str]]

_RECIPE_MODULES = (
    "deepr/experts/brief.py",
    "deepr/experts/brief_attribution.py",
    "deepr/experts/brief_contracts.py",
    "deepr/experts/brief_selection.py",
    "deepr/experts/consult_support.py",
    "deepr/experts/study_contracts.py",
    "deepr/experts/consult_context.py",
    "deepr/experts/consult_prompt.py",
    "deepr/experts/consult_response.py",
    "deepr/experts/council.py",
    "deepr/experts/council_synthesis_runtime.py",
    "deepr/experts/consult_routing.py",
    "deepr/backends/local.py",
    "deepr/backends/embedding_profiles.py",
    "deepr/experts/investigation/ollama_backend.py",
    "deepr/observability/local_attempts.py",
    "deepr/evals/correction_survival.py",
    "deepr/evals/correction_survival_cases.py",
    "deepr/evals/correction_survival_local.py",
    "deepr/evals/correction_survival_review.py",
)


class RunNotReusableError(RuntimeError):
    """A run directory is incomplete, altered, or bound to a different case set or recipe."""


def _sha(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def recipe_sha256() -> str:
    """Identity of the code bytes that shape briefing, selection, packing and receipts."""
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for relative in _RECIPE_MODULES:
        digest.update(relative.encode("utf-8"))
        digest.update((root / relative).read_bytes())
    return digest.hexdigest()


async def mock_completion(prompt: str) -> str:
    """The CLI's answer stand-in. It reads nothing and calls nothing."""
    del prompt
    return MOCK_ANSWER


@dataclass
class _Materialized:
    world: World
    corpus: Any
    study: Any
    shas: dict[str, str]
    briefs: list[Any]
    source_inventory_sha256: str = ""


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _study_for(item: World, shas: dict[str, str], texts: dict[str, str]) -> Any:
    """Fixture findings, grounded only where the anchor really occurs in its source."""
    from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult

    outcomes: dict[str, Any] = {}
    for finding in item.findings:
        grounded = _normalized(finding.anchor) in _normalized(texts[finding.source_id])
        outcome = outcomes.setdefault(
            finding.lens, LensOutcome(lens=finding.lens, axis="interrogation", status="ok", findings=[])
        )
        outcome.findings.append(
            StudyFinding(
                lens=finding.lens,
                axis="interrogation",
                kind="fixture",
                title=finding.title,
                payload=dict(finding.payload),
                anchors=[finding.anchor],
                grounded_anchor_count=1 if grounded else 0,
                ungrounded_anchor_count=0 if grounded else 1,
                corpus_shas=[shas[finding.source_id]] if grounded else [],
                finding_id=finding.finding_id,
            )
        )
    return StudyResult(expert_name=f"correction-survival-{item.world_id}", outcomes=list(outcomes.values()))


def _synthesis_json(item: World) -> str:
    """The world's frozen brief synthesis, standing in for a model's output."""
    return json.dumps(
        {
            "orientation": "Tern retry guidance is scoped by platform, version, job type and the supplied source world.",
            "positions": [
                {
                    "question": position.question,
                    "stance": position.stance,
                    "reasoning": position.reasoning,
                    "would_change_my_mind": position.would_change_my_mind,
                    "supported_by": list(position.supported_by),
                    "unresolved_dissent": position.unresolved_dissent,
                    "resolution": position.resolution,
                }
                for position in item.positions
            ],
            "state": {"settled": [], "live": list(item.live), "unknown": list(item.unknown)},
        }
    )


async def _materialize(item: World, root: Path, cycles: int, distractors: int = 0) -> _Materialized:
    from deepr.experts.brief import build_brief
    from deepr.experts.corpus_store import CorpusStore
    from deepr.experts.study_contracts import LensOutcome, StudyFinding

    corpus = CorpusStore(f"correction-survival-{item.world_id}", storage_dir=root / item.world_id / "corpus")
    shas: dict[str, str] = {}
    texts: dict[str, str] = {}
    for source in item.sources:
        entry, _ = corpus.add(
            source.text,
            origin_key=source.origin,
            trust_class=source.trust_class,
            fetched_at=source.observed_at,
        )
        shas[source.source_id] = entry.sha256
        texts[source.source_id] = source.text
    sources = source_inventory(item, distractors)
    study = _study_for(item, shas, texts)
    filler: list[Any] = []
    for source in sources[len(item.sources) :]:
        source_id, text = source.source_id, source.text
        entry, _ = corpus.add(
            text, origin_key=source.origin, trust_class=source.trust_class, fetched_at=source.observed_at
        )
        filler.append(
            StudyFinding(
                lens="synopsis",
                axis="interrogation",
                kind="fixture",
                title=f"Tern retries, backoff and agents: general note {source_id}",
                payload={"note": text[:240]},
                anchors=[text[:60]],
                grounded_anchor_count=1,
                corpus_shas=[entry.sha256],
                finding_id=f"synopsis-{source_id}",
            )
        )
    if filler:
        study.outcomes.insert(
            0, LensOutcome(lens="synopsis-filler", axis="interrogation", status="ok", findings=filler)
        )
    synthesis = _synthesis_json(item)

    async def fixture_synthesis(prompt: str) -> str:
        del prompt
        return synthesis

    briefs: list[Any] = []
    for _ in range(cycles):
        briefs.append(
            await build_brief(
                expert_name=study.expert_name,
                result=study,
                corpus=corpus,
                completion=fixture_synthesis,
                prior_positions=list(briefs[-1].positions) if briefs else None,
                as_of_date=date.fromisoformat(item.cutoff),
            )
        )
    return _Materialized(item, corpus, study, shas, briefs, source_inventory_sha256(sources))


def _perspective(name: str, blocks: list[Any], context: dict[str, Any]) -> Any:
    from deepr.experts.council import ExpertPerspective

    return ExpertPerspective(expert_name=name, domain="tern", response="", synthesis_blocks=blocks, context=context)


def _arm_packet(
    arm: str, case: Case, built: _Materialized, brief: Any, ranking: list[str] | None = None, note: str = ""
) -> tuple[str, dict[str, Any], Any]:
    """Return (prompt, delivery manifest, consult context or None) for one arm."""
    from deepr.experts.consult_context import ConsultContext, build_consult_context
    from deepr.experts.consult_prompt import brief_synthesis_blocks, build_synthesis_packet

    if arm == "production":
        context = build_consult_context(
            expert_name=built.study.expert_name,
            question=case.question,
            brief=brief,
            result=built.study,
            corpus=built.corpus,
            semantic_ranking=ranking,
            routing_note=note,
        )
        meta = {
            "source": "brief",
            "coverage": context.coverage,
            "study_fingerprint": context.study_fingerprint,
            "study_binding": context.study_binding,
        }
    elif arm == "oracle_packet":
        wanted = {item.finding_id for item in case.obligations if item.finding_id}
        findings = [finding for finding in built.study.findings if finding.finding_id in wanted]
        context = ConsultContext(
            expert_name="oracle",
            findings=findings,
            finding_sources={
                finding.finding_id: (sha, built.corpus.entries[sha].origin_key, built.corpus.read(sha) or "")
                for finding in findings
                for sha in finding.corpus_shas[:1]
            },
        )
        meta = {"source": "oracle_packet"}
    else:
        context = ConsultContext(
            expert_name="fresh",
            reference_passages=[
                (entry.sha256, entry.origin_key, text) for entry, text in built.corpus.load_study_material()
            ],
        )
        meta = {"source": "fresh_sources"}
    prompt, manifest = build_synthesis_packet(
        case.question, [_perspective(context.expert_name, brief_synthesis_blocks(context), meta)]
    )
    return prompt, manifest, context


def _selection(brief: Any) -> dict[str, Any]:
    return dict(getattr(brief, "synthesis_input", {}) or {})


def _study_state(finding: Any, sha: str) -> str:
    if finding is None:
        return "absent"
    return "represented" if sha in finding.corpus_shas else "unanchored"


def _briefing_state(finding_id: str, brief: Any) -> str:
    """Presented, shortened or omitted at brief synthesis, from the brief's own receipt."""
    selection = _selection(brief)
    if not selection:
        return "unrecorded"
    if finding_id in selection.get("omitted_ids", []):
        return "omitted"
    if finding_id not in selection.get("presented_ids", []):
        return "not_in_study"
    if finding_id in {item.get("finding_id") for item in selection.get("shortened") or []}:
        return "shortened"
    return "presented"


def _delivery_state(finding_id: str, expert: dict[str, Any]) -> str:
    if finding_id in (expert.get("findings_delivered") or []):
        return "delivered"
    if finding_id in (expert.get("findings_omitted") or []):
        return "omitted_by_limit"
    return "not_assembled"


def _receipt(
    obligation: Obligation, arm: str, built: _Materialized, brief: Any, context: Any, manifest: dict[str, Any]
) -> dict[str, str]:
    """Mechanical stage states for one obligation in one arm. No meaning is judged."""
    receipt = dict.fromkeys(STAGES, "not_applicable")
    receipt["answer"] = "unreviewed"
    if obligation.expectation == "isolate" or not obligation.source_id:
        return receipt
    expert = (manifest.get("experts") or [{}])[0]
    sha = built.shas.get(obligation.source_id, "")
    receipt["source"] = "present" if sha and built.corpus.read(sha) else "absent"
    if arm == "fresh_sources":
        provided = any(item[0] == sha for item in context.reference_passages)
        receipt["study"] = receipt["briefing"] = "not_used_by_arm"
        receipt["retrieval"] = "provided" if provided else "missed"
        if not provided:
            receipt["delivery"] = "not_assembled"
        else:
            delivered = sha in (expert.get("passages_delivered") or [])
            receipt["delivery"] = "delivered" if delivered else "omitted_by_limit"
        return receipt
    finding = next((f for f in built.study.findings if f.finding_id == obligation.finding_id), None)
    receipt["study"] = _study_state(finding, sha)
    if arm == "oracle_packet":
        receipt["briefing"] = "not_used_by_arm"
        receipt["retrieval"] = "oracle_selected" if finding is not None else "missed"
    else:
        receipt["briefing"] = _briefing_state(obligation.finding_id, brief)
        selected = {f.finding_id for f in context.findings}
        receipt["retrieval"] = "selected" if obligation.finding_id in selected else "missed"
    receipt["delivery"] = _delivery_state(obligation.finding_id, expert)
    return receipt


def _sentences(text: str) -> list[str]:
    parts = [" ".join(part.split()).casefold() for part in text.replace("!", ".").replace("?", ".").split(".")]
    return [part for part in parts if len(part) >= 30]


def _isolation(case: Case, built: _Materialized, prompt: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """Historical isolation: no forbidden source in the world, the delivered passages or the prompt.

    The world check holds by construction for the frozen worlds; it is kept so
    a world change that admits a later source is caught. The prompt check
    looks for any sentence of a forbidden source, since delivered passages are
    windows from the middle of a source.
    """
    from deepr.evals.correction_survival_cases import WORLDS
    from deepr.experts.corpus_store import content_hash

    forbidden = {
        source.source_id: source.text
        for other in WORLDS
        for source in other.sources
        if source.source_id in case.forbidden_sources
    }
    passages = {sha for expert in manifest.get("experts") or [] for sha in expert.get("passages_delivered") or []}
    normalized_prompt = _normalized(prompt)
    leaked = sorted(
        sid
        for sid, text in forbidden.items()
        if sid in built.shas
        or content_hash(text) in passages
        or any(sentence in normalized_prompt for sentence in _sentences(text))
    )
    return {"checked_sources": sorted(forbidden), "leaked": leaked, "status": "leaked" if leaked else "isolated"}


def _compression(built: _Materialized) -> list[dict[str, Any]]:
    """Per cycle: study identity and the provenance counts each position claims."""
    rows = []
    for cycle, brief in enumerate(built.briefs, 1):
        rows.append(
            {
                "cycle": cycle,
                "study_fingerprint": brief.study_fingerprint,
                "positions": [
                    {
                        "question": position.question,
                        "supported_by": list(position.supported_by),
                        "supporting_documents": position.supporting_documents,
                        "distinct_roots": position.distinct_roots,
                    }
                    for position in brief.positions
                ],
            }
        )
    return rows


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return _sha(text)


async def _attempt(
    case: Case,
    arm: str,
    cycle: int,
    built: _Materialized,
    completion: AnswerCompletion,
    run_dir: Path,
    router: Any = None,
) -> dict[str, Any]:
    attempt_started = time.perf_counter()
    brief = built.briefs[cycle - 1]
    ranking: list[str] | None = None
    note = ""
    routing: dict[str, Any] = {
        "configured": f"lexical+local-embedding:{router.model}" if router is not None else "lexical",
        "effective": "lexical" if arm == "production" else "not_used_by_arm",
        "status": "not_configured" if arm == "production" else "not_used_by_arm",
        "elapsed_ms": 0.0,
        "calls": [],
    }
    if arm == "production" and router is not None:
        from deepr.experts.consult_routing import route_findings_recorded

        ranking, note, routing = await route_findings_recorded(router, case.question, built.study.findings)
    prompt, manifest, context = _arm_packet(arm, case, built, brief, ranking, note)
    attempt_id = f"{case.case_id}.{arm}.c{cycle}"
    started = time.perf_counter()
    status, error, answer = "completed", "", ""
    try:
        answer = await completion(prompt)
    except Exception as exc:  # every failure stays in the denominator
        status, error = "failed", type(exc).__name__
    answered = time.perf_counter()
    elapsed_ms = round((answered - started) * 1000, 3)
    receipts = {
        obligation.obligation_id: _receipt(obligation, arm, built, brief, context, manifest)
        for obligation in case.obligations
    }
    record: dict[str, Any] = {
        "attempt_id": attempt_id,
        "case_id": case.case_id,
        "case_class": case.case_class,
        "world_id": case.world_id,
        "arm": arm,
        "cycle": cycle,
        "status": status,
        "error_type": error,
        "answer_calls": 1,
        "prompt_sha256": _sha(prompt),
        "prompt_chars": len(prompt),
        "answer_sha256": _sha(answer) if status == "completed" else "",
        "answer_chars": len(answer),
        "elapsed_ms": elapsed_ms,
        "answer_elapsed_ms": elapsed_ms,
        "routing_elapsed_ms": routing["elapsed_ms"],
        "total_elapsed_ms": round((answered - attempt_started) * 1000, 3),
        "finding_routing": routing,
        "delivery_manifest": manifest,
        "brief_synthesis_input": _selection(brief) if arm == "production" else {},
        "stage_receipts": receipts,
    }
    calls = getattr(completion, "calls", None)
    if isinstance(calls, list) and calls:
        record["dispatch"] = dict(calls[-1])
    if case.forbidden_sources:
        record["isolation"] = _isolation(case, built, prompt, manifest)
    record["prompt_file_sha256"] = _write_json(run_dir / "attempts" / attempt_id / "prompt.json", {"prompt": prompt})
    record["answer_file_sha256"] = _write_json(run_dir / "attempts" / attempt_id / "answer.json", {"answer": answer})
    return record


async def run_diagnostic(
    run_dir: Path,
    *,
    completion: AnswerCompletion = mock_completion,
    code_identity: str = "unknown",
    model_identity: str = "mock:no-inference",
    cases: tuple[Case, ...] = CASES,
    distractors: int = 0,
    on_attempt: Callable[[dict[str, Any], int, int], None] | None = None,
    finding_router: Any = None,
) -> dict[str, Any]:
    """Run every scheduled case, arm and cycle, then mark the run complete.

    The completion marker is written last, after every attempt file has been
    re-read and its hash checked. A run without it is never reused.
    """
    run_dir.mkdir(parents=True, exist_ok=False)
    worlds: dict[tuple[str, int], _Materialized] = {}
    attempts: list[dict[str, Any]] = []
    for case in cases:
        key = (case.world_id, case.cycles)
        if key not in worlds:
            worlds[key] = await _materialize(
                world(case.world_id), run_dir / "worlds" / f"c{case.cycles}", case.cycles, distractors
            )
        built = worlds[key]
        for cycle in range(1, case.cycles + 1):
            for arm in ARMS:
                attempts.append(await _attempt(case, arm, cycle, built, completion, run_dir, finding_router))
                if on_attempt is not None:
                    on_attempt(attempts[-1], len(attempts), sum(c.cycles * len(ARMS) for c in cases))
    compression = {
        f"{world_id}.c{cycles}": _compression(built) for (world_id, cycles), built in worlds.items() if cycles > 1
    }
    run = {
        "kind": RUN_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "case_set_version": CASE_SET_VERSION,
        "case_set_sha256": case_set_sha256(cases),
        "case_ids": [case.case_id for case in cases],
        "complete_case_set": cases == CASES,
        "recipe_sha256": recipe_sha256(),
        "code_identity": code_identity,
        "model_identity": model_identity,
        "arms": list(ARMS),
        "distractors_per_world": distractors,
        "source_inventory_sha256": {built.world.world_id: built.source_inventory_sha256 for built in worlds.values()},
        "finding_routing": f"lexical+local-embedding:{finding_router.model}" if finding_router else "lexical",
        "scheduled_attempts": sum(case.cycles * len(ARMS) for case in cases),
        "attempts": attempts,
        "repeated_compression": compression,
        "rubric": RUBRIC,
        "paid_calls": 0,
    }
    run_sha = _write_json(run_dir / "run.json", run)
    _verify_attempt_files(run_dir, attempts)
    _write_json(run_dir / COMPLETE_MARKER, {"run_sha256": run_sha, "attempts": len(attempts)})
    return run


def _verify_attempt_files(run_dir: Path, attempts: list[dict[str, Any]]) -> None:
    for attempt in attempts:
        base = run_dir / "attempts" / attempt["attempt_id"]
        for name, field in (("prompt.json", "prompt_file_sha256"), ("answer.json", "answer_file_sha256")):
            path = base / name
            if not path.is_file() or _sha(path.read_bytes()) != attempt[field]:
                raise RunNotReusableError(f"attempt file {path} is missing or altered")


def load_run(run_dir: Path, *, expected_recipe_sha256: str | None = None) -> dict[str, Any]:
    """Verify completed artifacts against current code or an explicit historical pin.

    A historical pin permits artifact inspection only. Completion, case-set,
    denominator and file checks still apply; this never admits execution reuse.
    """
    if expected_recipe_sha256 is not None and (
        len(expected_recipe_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_recipe_sha256)
    ):
        raise ValueError("recipe SHA-256 must contain exactly 64 lowercase hexadecimal characters")
    marker = run_dir / COMPLETE_MARKER
    run_path = run_dir / "run.json"
    if not marker.is_file() or not run_path.is_file():
        raise RunNotReusableError("run has no completion marker; an answer file alone is not a completed run")
    expected = json.loads(marker.read_text(encoding="utf-8"))
    if _sha(run_path.read_bytes()) != expected.get("run_sha256"):
        raise RunNotReusableError("run.json does not match its completion marker")
    run: dict[str, Any] = json.loads(run_path.read_text(encoding="utf-8"))
    by_id = {case.case_id: case for case in CASES}
    try:
        scheduled = tuple(by_id[case_id] for case_id in run.get("case_ids") or [])
    except KeyError as exc:
        raise RunNotReusableError(f"run names a case not in the current set: {exc}") from exc
    if not scheduled or run.get("case_set_sha256") != case_set_sha256(scheduled):
        raise RunNotReusableError("run was produced from a different case set")
    if not len(run["attempts"]) == run.get("scheduled_attempts") == expected.get("attempts"):
        raise RunNotReusableError("run does not record every scheduled attempt")
    expected_recipe = recipe_sha256() if expected_recipe_sha256 is None else expected_recipe_sha256
    if run.get("recipe_sha256") != expected_recipe:
        message = (
            "run was produced by different selection or packing code"
            if expected_recipe_sha256 is None
            else "run does not match the pinned recipe SHA-256"
        )
        raise RunNotReusableError(message)
    _verify_attempt_files(run_dir, run["attempts"])
    return run


def build_report(run: dict[str, Any], reviews: dict[tuple[str, str], str] | None = None) -> dict[str, Any]:
    """Stage counts per arm with every scheduled attempt in the denominator."""
    reviews = reviews or {}
    arms: dict[str, Any] = {}
    for arm in run["arms"]:
        rows = [attempt for attempt in run["attempts"] if attempt["arm"] == arm]
        stages: dict[str, dict[str, int]] = {stage: {} for stage in STAGES}
        for attempt in rows:
            for obligation, receipt in attempt["stage_receipts"].items():
                for stage in STAGES:
                    state = receipt[stage]
                    if stage == "answer":
                        state = reviews.get((attempt["attempt_id"], obligation), state)
                    stages[stage][state] = stages[stage].get(state, 0) + 1
        arms[arm] = {
            "attempts": len(rows),
            "completed": sum(1 for attempt in rows if attempt["status"] == "completed"),
            "failed": sum(1 for attempt in rows if attempt["status"] == "failed"),
            "prompt_chars": sum(attempt["prompt_chars"] for attempt in rows),
            "elapsed_ms": round(sum(attempt["elapsed_ms"] for attempt in rows), 3),
            **_routing_report(rows),
            "stages": stages,
        }
    isolation = [
        {"attempt_id": attempt["attempt_id"], **attempt["isolation"]}
        for attempt in run["attempts"]
        if "isolation" in attempt
    ]
    current_recipe = recipe_sha256()
    return {
        "kind": REPORT_SCHEMA,
        "case_set_version": run["case_set_version"],
        "case_set_sha256": run["case_set_sha256"],
        "complete_case_set": run["complete_case_set"],
        "recipe_sha256": run["recipe_sha256"],
        "code_identity": run.get("code_identity", "unknown"),
        "current_recipe_sha256": current_recipe,
        "recipe_matches_current": run["recipe_sha256"] == current_recipe,
        "model_identity": run["model_identity"],
        "distractors_per_world": run["distractors_per_world"],
        "finding_routing": run.get("finding_routing", "lexical"),
        "scheduled_attempts": run["scheduled_attempts"],
        "recorded_attempts": len(run["attempts"]),
        "reviewed_obligations": len(reviews),
        "arms": arms,
        "historical_isolation": isolation,
        "repeated_compression": run["repeated_compression"],
        "paid_calls": run["paid_calls"],
        "limits": (
            "Mechanical stage receipts only. Answer use is unreviewed unless a bound label says otherwise. "
            "Mock answers establish transport and accounting, not answer quality. "
            "elapsed_ms is answer-only; total_elapsed_ms includes routing and packet assembly through the answer, "
            "excluding shared world/study/brief setup and artifact writes. Legacy routing/total timing is unknown."
        ),
    }


def _routing_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate recorded routing work without inventing observations for old runs."""
    routes = [row["finding_routing"] for row in rows if "finding_routing" in row]
    calls = [call for route in routes for call in route["calls"]]
    effective: dict[str, int] = {}
    statuses: dict[str, int] = {}
    for route in routes:
        effective[route["effective"]] = effective.get(route["effective"], 0) + 1
        statuses[route["status"]] = statuses.get(route["status"], 0) + 1
    return {
        "answer_elapsed_ms": round(sum(row["elapsed_ms"] for row in rows), 3),
        "routing_elapsed_ms": _timing_total(rows, "routing_elapsed_ms"),
        "total_elapsed_ms": _timing_total(rows, "total_elapsed_ms"),
        "routing": {
            "observed_attempts": len(routes),
            "unknown_attempts": len(rows) - len(routes),
            "effective_counts": effective,
            "status_counts": statuses,
            "embedding_calls": len(calls),
            "embedding_tokens_input_known": sum(call["tokens_input"] or 0 for call in calls),
            "embedding_usage_unknown_calls": sum(call["tokens_input"] is None for call in calls),
            "unsettled_calls": sum(call["accounting"] != "recorded" for call in calls),
        },
    }


def _timing_total(rows: list[dict[str, Any]], key: str) -> float | None:
    return round(sum(row[key] for row in rows), 3) if all(key in row for row in rows) else None


def render_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Correction survival diagnostic ({report['case_set_version']})",
        "",
        f"- Model: {report['model_identity']}; paid calls: {report['paid_calls']}; "
        f"distractor sources per world: {report['distractors_per_world']}; "
        f"configured finding routing: {report['finding_routing']}",
        f"- Cases: {'full set' if report['complete_case_set'] else 'SUBSET of the case set'}; "
        f"attempts: {report['recorded_attempts']} of {report['scheduled_attempts']} scheduled; "
        f"reviewed obligations: {report['reviewed_obligations']}",
        f"- Recorded code: {report.get('code_identity', 'unknown')}; recorded recipe: {report['recipe_sha256']}",
        f"- Current recipe: {report.get('current_recipe_sha256')}; "
        f"recorded/current match: {report.get('recipe_matches_current')} (None means unknown).",
        "",
    ]
    for arm, data in report["arms"].items():
        lines.append(f"## {arm}")
        lines.append(
            f"{data['completed']} completed, {data['failed']} failed, {data['prompt_chars']} prompt characters"
        )
        lines.append(
            f"Elapsed ms: answer {data['answer_elapsed_ms']}, routing {data['routing_elapsed_ms']}, "
            f"total attempt {data['total_elapsed_ms']} (None means unknown)."
        )
        lines.append(
            f"Effective routes: {data['routing']['effective_counts']}; routing states: {data['routing']['status_counts']}; "
            f"embedding calls: {data['routing']['embedding_calls']} "
            f"({data['routing']['embedding_usage_unknown_calls']} with unknown token usage, "
            f"{data['routing']['unsettled_calls']} with unsettled accounting)."
        )
        lines.append("")
        lines.append("| Stage | States |")
        lines.append("|---|---|")
        for stage, states in data["stages"].items():
            lines.append(f"| {stage} | {', '.join(f'{k} {v}' for k, v in sorted(states.items()))} |")
        lines.append("")
    leaked = [row for row in report["historical_isolation"] if row["status"] != "isolated"]
    lines.append(
        f"Historical isolation: {len(report['historical_isolation']) - len(leaked)} isolated, {len(leaked)} leaked."
    )
    lines.append("")
    lines.append(report["limits"])
    return "\n".join(lines) + "\n"
