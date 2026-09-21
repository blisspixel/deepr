"""Attended local expert formation shared by creation surfaces.

Research completion is a reviewable foundation, never automatic qualification.
Existing formed experts use explicit maintenance rather than being overwritten.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.brief import build_brief, render_brief
from deepr.experts.corpus_acquire import acquire_sources, default_fetch_page
from deepr.experts.corpus_search import interleave_by_arm, run_search_plan
from deepr.experts.corpus_store import CorpusStore, content_hash
from deepr.experts.evidence_graph import build_graph, render_graph
from deepr.experts.expert_layout import part_in
from deepr.experts.knowledge_wiki import write_knowledge_view
from deepr.experts.loop_lock import expert_verb_lock
from deepr.experts.notebook import NOTEBOOK_MARKER, build_notebook
from deepr.experts.paths import canonical_expert_dir
from deepr.experts.position_ledger import load_ledger, record_brief
from deepr.experts.query_proposal import propose_plan
from deepr.experts.stage_contract import STAGE_BRIEF, STAGE_STUDY, get_stage
from deepr.experts.study import run_study
from deepr.experts.study_contracts import StudyResult
from deepr.observability.cost_ledger import CostLedger
from deepr.utils.atomic_io import atomic_write_json, atomic_write_text


@dataclass(frozen=True)
class FormationLimits:
    max_queries: int = 12
    max_urls: int = 12
    max_corpus_chars: int = 120_000
    max_model_calls: int = 40
    max_elapsed_seconds: int = 2700

    def validate(self) -> None:
        ceilings = FormationLimits()
        for key, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= getattr(ceilings, key):
                raise ValueError(f"{key} must be a positive integer no greater than {getattr(ceilings, key)}")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def read_formation_state(name: str) -> dict[str, Any] | None:
    path = canonical_expert_dir(name) / "formation/current.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "deepr-formation-v1":
        raise ValueError("Unreadable formation record")
    if payload.get("status") == "running":
        try:
            started = datetime.fromisoformat(payload["created_at"])
            deadline = payload["limits"]["max_elapsed_seconds"]
            if started.tzinfo is None or isinstance(deadline, bool) or not isinstance(deadline, int) or deadline < 1:
                raise ValueError("Unreadable formation deadline")
        except (KeyError, TypeError) as error:
            raise ValueError("Unreadable formation deadline") from error
        if (datetime.now(UTC) - started).total_seconds() > deadline + 30:
            payload = {
                **payload,
                "status": "interrupted",
                "progress": "Build deadline passed without completion; inspect retained work before retrying.",
            }
    return payload


def _snapshot(directory: Path) -> dict[str, str | None]:
    paths = [part_in(directory, name) for name in ("noticed", "hold_current", "hold_history")]
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        for path in paths
    }


class FormationRun:
    """Durable bounded operation state, including attempts that did not succeed."""

    def __init__(self, profile: Any, backend: Any, limits: FormationLimits, on_progress: Any = None):
        self.profile, self.backend, self.limits = profile, backend, limits
        self.directory = canonical_expert_dir(profile.name)
        self.started = time.monotonic()
        self.on_progress = on_progress
        self.ledger = CostLedger()
        self.state: dict[str, Any] = {
            "schema_version": "deepr-formation-v1",
            "operation_id": uuid.uuid4().hex,
            "expert": profile.name,
            "mission": ": ".join(
                dict.fromkeys(value for value in (profile.name, profile.domain, profile.description) if value)
            ),
            "model": backend.model,
            "capacity_source": backend.capacity_source,
            "created_at": _now(),
            "status": "running",
            "stage": "starting",
            "limits": asdict(limits),
            "model_calls": 0,
            "calls": [],
            "api_cost_usd": 0,
            "qualification": "not_reviewed",
            "limitations": [],
            "prior_artifacts": _snapshot(self.directory),
        }
        self.run_dir = self.directory / "formation/runs" / self.state["operation_id"]
        self.previous = read_formation_state(profile.name)
        for relative, digest in self.state["prior_artifacts"].items():
            if digest:
                atomic_write_text(
                    self.run_dir / "before" / relative, (self.directory / relative).read_text(encoding="utf-8")
                )

    def save(self) -> None:
        self.state.update(updated_at=_now(), elapsed_seconds=round(time.monotonic() - self.started, 2))
        atomic_write_json(self.run_dir / "run.json", self.state, fsync=True)
        atomic_write_json(self.directory / "formation/current.json", self.state, fsync=True)

    def progress(self, note: str) -> None:
        self.state["progress"] = note
        self.save()
        if self.on_progress:
            self.on_progress(note)

    def stage(self, name: str) -> None:
        self.state["stage"] = name
        self.progress(name)

    async def complete(self, prompt: str) -> str:
        if self.state["model_calls"] >= self.limits.max_model_calls:
            raise RuntimeError("Formation model-call limit exhausted")
        self.state["model_calls"] += 1
        call = {
            "number": self.state["model_calls"],
            "started_at": _now(),
            "status": "started",
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        }
        self.state["calls"].append(call)
        self.save()
        request_id = f"{self.state['operation_id']}:{call['number']}"
        self.ledger.record_event(
            operation="expert_formation",
            provider="local",
            cost_usd=0,
            model=self.backend.model,
            request_id=request_id,
            source="attended_local_formation",
            idempotency_key=request_id,
            metadata={"expert": self.profile.name, "status": "attempted", "prompt_sha256": call["prompt_sha256"]},
            require_fsync=True,
        )
        try:
            text = await self.backend.completion(prompt)
            call.update(status="returned", response_sha256=hashlib.sha256(text.encode()).hexdigest())
            return text
        except BaseException as error:
            call.update(
                status="interrupted" if isinstance(error, asyncio.CancelledError) else "failed",
                error_type=type(error).__name__,
            )
            raise
        finally:
            call["finished_at"] = _now()
            self.save()

    def artifact(self, name: str, payload: Any) -> None:
        atomic_write_json(self.run_dir / name, payload, fsync=True)


def _require_stage(name: str, payload: dict[str, Any]) -> None:
    stage = get_stage(name)
    if stage is None or stage.succeeds_when is None or not stage.succeeds_when(payload):
        raise ValueError(f"Formation {name} did not produce its required evidence")


def _retain_seeds(run: FormationRun, corpus: CorpusStore) -> None:
    for source in list(getattr(run.profile, "source_files", []) or [])[: run.limits.max_urls]:
        path = Path(source)
        if path.stat().st_size > 2_000_000:
            run.state["limitations"].append(f"Seed document exceeds the byte limit: {path.name}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            run.state["limitations"].append(f"Seed needs conversion to UTF-8 text: {path.name}")
            continue
        if not text.strip() or len(text) > 400_000:
            run.state["limitations"].append(f"Seed is empty or exceeds the text limit: {path.name}")
            continue
        corpus.add(
            text,
            origin_key="operator:seed",
            title=path.stem,
            publisher="Operator supplied",
            kind="local_document",
            fetched_at=_now(),
            trust_class="secondary",
        )


def _check_corpus(corpus: CorpusStore) -> None:
    for entry in corpus.active_entries():
        if len(entry.sha256) != 64 or any(char not in "0123456789abcdef" for char in entry.sha256):
            raise ValueError("Invalid retained source identity")
        text = corpus.read(entry.sha256)
        if text is None or content_hash(text) != entry.sha256:
            raise ValueError(f"Retained source bytes do not match their identity: {entry.sha256}")


async def _acquire(run: FormationRun, corpus: CorpusStore) -> None:
    run.stage("research")
    plan = await propose_plan(run.state["mission"], completion=run.complete)
    planned = len(plan.queries)
    plan.queries = interleave_by_arm(plan.queries)[: run.limits.max_queries]
    run.artifact("search-plan.json", {**plan.to_dict(), "queries_omitted_by_limit": planned - len(plan.queries)})
    found = await run_search_plan(
        plan, per_query=2, max_urls=run.limits.max_urls, target_hosts=4, on_progress=run.progress
    )
    run.artifact("search-result.json", found.to_dict())
    if not found.hits:
        run.state["limitations"].append("Search returned no usable URLs; this does not establish topic coverage.")
    report = await acquire_sources(
        expert_name=run.profile.name,
        urls=[hit.url for hit in found.hits],
        corpus=corpus,
        fetch_page=default_fetch_page(),
    )
    run.artifact("acquisition.json", report.to_dict())
    run.state["limitations"].extend(report.limitations)
    if not corpus.active_entries():
        raise ValueError("No source material retained; formation cannot proceed")
    run.state["retained_sources"] = len(corpus.active_entries())


async def _study_and_brief(run: FormationRun, corpus: CorpusStore) -> tuple[Any, Any]:
    run.stage("study")
    study = await run_study(
        expert_name=run.profile.name,
        corpus=corpus,
        completion=run.complete,
        lens_keys=["synopsis", "mechanism", "failure"],
        max_corpus_chars=run.limits.max_corpus_chars,
        chunk_chars=run.backend.chunk_chars,
        capacity_source=run.backend.capacity_source,
        model=run.backend.model,
        on_progress=run.progress,
        checkpoint=lambda result: run.artifact("study.json", result.to_dict()),
        resume_from=_resume_outcomes(run),
    )
    run.artifact("study.json", study.to_dict())
    _require_stage(STAGE_STUDY, study.to_dict())
    if len(study.outcomes) != 3 or any(outcome.status != "ok" for outcome in study.outcomes):
        raise ValueError("Study is incomplete; candidate evidence was saved without replacing current knowledge")
    run.state["limitations"].extend(study.limitations)
    run.stage("perspective")
    brief = await build_brief(
        expert_name=run.profile.name, result=study, corpus=corpus, completion=run.complete, domain=run.state["mission"]
    )
    run.artifact("brief.json", brief.to_dict())
    _require_stage(STAGE_BRIEF, brief.to_dict())
    return study, brief


def _resume_outcomes(run: FormationRun) -> list[Any]:
    previous = run.previous or {}
    operation = previous.get("operation_id", "")
    if (
        previous.get("model") != run.backend.model
        or len(operation) != 32
        or any(c not in "0123456789abcdef" for c in operation)
    ):
        return []
    path = run.directory / "formation/runs" / operation / "study.json"
    if not path.is_file():
        return []
    result = StudyResult.from_dict(json.loads(path.read_text(encoding="utf-8")))
    run.state["resume_candidate"] = operation
    # run_study reuses only completed lenses whose current corpus fingerprint matches.
    return result.outcomes


def _publish_foundation(run: FormationRun, corpus: CorpusStore, study: Any, brief: Any) -> None:
    run.stage("knowledge")
    if _snapshot(run.directory) != run.state["prior_artifacts"]:
        raise ValueError("Expert state changed during formation; candidate preserved without overwriting it")
    notebook = run.directory / "notebook.md"
    if notebook.exists() and not notebook.read_text(encoding="utf-8").startswith(NOTEBOOK_MARKER):
        raise ValueError("Refusing to replace an authored notebook")
    ledger = load_ledger(part_in(run.directory, "hold_history"), expert_name=run.profile.name)
    fingerprint = study.outcomes[-1].corpus_fingerprint
    record_brief(ledger, brief.positions, at=_now(), corpus_fingerprint=fingerprint)
    entries = corpus.active_entries()
    graph = build_graph(expert_name=run.profile.name, study=study, brief=brief, corpus_entries=entries, at=_now())
    if not graph.is_formed:
        raise ValueError("No position reaches a retained source; foundation remains unformed")
    knowledge = write_knowledge_view(run.directory, study=study, brief=brief, entries=entries, history=ledger.to_dict())
    atomic_write_json(part_in(run.directory, "hold_history"), ledger.to_dict(), fsync=True)
    atomic_write_json(part_in(run.directory, "noticed"), study.to_dict(), fsync=True)
    atomic_write_text(part_in(run.directory, "hold_rendered"), render_brief(brief))
    atomic_write_text(
        run.directory / "notebook.md",
        build_notebook(study, expert_name=run.profile.name, domain=run.state["mission"], corpus_entries=entries),
    )
    atomic_write_json(run.directory / "graph/evidence.json", graph.to_dict(), fsync=True)
    atomic_write_text(run.directory / "graph/evidence.md", render_graph(graph))
    # Publish the consultable brief last. Interrupted candidates and earlier bytes
    # remain in the operation directory; the file set is not a database transaction.
    atomic_write_json(part_in(run.directory, "hold_current"), brief.to_dict(), fsync=True)
    run.state.update(
        knowledge_index=str(knowledge.relative_to(run.directory)),
        findings=len(study.findings),
        positions=len(brief.positions),
        evidence_graph=graph.stats(),
        final_artifacts=_snapshot(run.directory),
    )


def _write_review(run: FormationRun) -> None:
    lines = [
        "# Expert formation review",
        "",
        f"Expert: {run.profile.name}",
        "",
        f"Operation: `{run.state['operation_id']}`",
        "",
        f"Observed: {run.state['updated_at']}",
        "",
        f"Status: {run.state['status']}",
        "",
        "Qualification: not reviewed.",
        "",
        "Research completion does not certify interpretation, currentness for a question, or guidance quality.",
        "",
        "[Operation record](run.json) | [Search plan](search-plan.json) | [Acquisition](acquisition.json)",
        "",
        "## Required advice review",
        "",
        "- Check the retained source scope and applicable versions.",
        "- Review representative practical answers against sources and executable examples where appropriate.",
        "- Examine fresh transfer questions and preserve failures.",
        "- Check current developments for the actual question before claiming readiness.",
        "",
        "## Recorded limitations",
        "",
        *[f"- {note}" for note in run.state["limitations"]],
        "",
    ]
    atomic_write_text(run.run_dir / "review.md", "\n".join(lines))


async def form_expert(
    profile: Any, backend: Any, *, limits: FormationLimits | None = None, on_progress: Any = None, discover: bool = True
) -> dict[str, Any]:
    """Develop an unformed local profile through one attended bounded operation."""
    limits = limits or FormationLimits()
    limits.validate()
    if not str(backend.capacity_source).startswith("local:"):
        raise ValueError("Initial formation requires owned local capacity; paid and plan execution are not enabled")
    directory = canonical_expert_dir(profile.name)
    if part_in(directory, "hold_current").exists():
        raise ValueError(
            "This expert already has a brief; use explicit maintenance instead of recreating its knowledge"
        )
    with expert_verb_lock(profile.name, "formation") as acquired:
        if not acquired:
            raise ValueError("An expert formation operation is already running")
        if part_in(directory, "hold_current").exists():
            raise ValueError("This expert already has a brief; use explicit maintenance")
        run = FormationRun(profile, backend, limits, on_progress)
        run.save()
        try:
            async with asyncio.timeout(limits.max_elapsed_seconds):
                corpus = CorpusStore(profile.name)
                _retain_seeds(run, corpus)
                if discover:
                    await _acquire(run, corpus)
                else:
                    run.state["limitations"].append(
                        "Web discovery was explicitly disabled; only retained sources were studied."
                    )
                _check_corpus(corpus)
                study, brief = await _study_and_brief(run, corpus)
                _publish_foundation(run, corpus, study, brief)
                run.state.update(
                    status="research_complete", stage="review", progress="Research foundation ready for review"
                )
        except asyncio.CancelledError:
            run.state.update(status="interrupted", progress="Formation interrupted; completed evidence was retained")
            raise
        except Exception as error:
            note = "Formation elapsed-time limit exhausted" if isinstance(error, TimeoutError) else str(error)
            run.state.update(status="incomplete", error_type=type(error).__name__, progress=note[:500])
        finally:
            run.save()
            _write_review(run)
            from deepr.backends.local import release_local_model

            await release_local_model(backend.model)
        return run.state
