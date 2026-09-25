"""Local four-arm operational rehearsal over prepared source worlds.

Implements the arm policy in ``docs/design/local-four-arm-rehearsal.md``:

- fresh research: a new study and brief for every case, then an answer;
- static history: the raw current source packet only;
- compiled expert: one world-1 checkpoint, frozen;
- maintained expert: the same world-1 checkpoint, updated before each later
  world; a failed update keeps the last completed checkpoint and says so.

Every phase runs in a separate worker process with a new verified source
copy, an explicit credential-free environment and its own data root.
Construction and maintenance never receive a question. Consultation reads a
fresh copy of a frozen checkpoint, hashed before and after. Every cell ends as
answered, failed or blocked; nothing is retried over an earlier attempt.

This produces unreviewed operational evidence only. It assigns no scores,
attests no review, selects no winner, and does not confine the network
beyond the owned-local model endpoint check.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from deepr.evals.expert_value import ARM_ORDER
from deepr.evals.expert_value_materialize import materialize_source_world_copy
from deepr.evals.expert_value_sources import load_source_world_preparation

POLICY_SCHEMA: Final = "deepr-expert-value-rehearsal-policy-v1"
PLAN_SCHEMA: Final = "deepr-expert-value-rehearsal-plan-v1"
SUMMARY_SCHEMA: Final = "deepr-expert-value-rehearsal-summary-v1"
CELL_SCHEMA: Final = "deepr-expert-value-rehearsal-cell-v1"
Digest = Annotated[str, Field(pattern=r"^(sha256:)?[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")]
WORKER_MODULE = "deepr.evals.expert_value_rehearsal_worker"
_PASSTHROUGH_ENV = (
    "SystemRoot",
    "SYSTEMROOT",
    "SystemDrive",
    "SYSTEMDRIVE",
    "WINDIR",
    "PATHEXT",
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "LANG",
    "LC_ALL",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class RehearsalPolicy(_Strict):
    """Frozen execution policy; its status never claims operator review."""

    schema_version: Literal["deepr-expert-value-rehearsal-policy-v1"]
    status: Literal["unreviewed_operational_rehearsal"]
    model: str = Field(min_length=1, max_length=200)
    model_digest: Digest
    ollama_base_url: str = Field(min_length=1, max_length=200)
    num_ctx: int = Field(ge=2048, le=262144)
    max_output_tokens: int = Field(ge=64, le=32768)
    temperature: float = Field(ge=0, le=2)
    seed: int
    think: bool
    lenses: list[str] = Field(min_length=1, max_length=8)
    study_max_corpus_chars: int = Field(ge=1000, le=2_000_000)
    study_chunk_chars: int = Field(ge=1000, le=500_000)
    memory_prefix_max_chars: int = Field(ge=500, le=200_000)
    max_calls_per_phase: int = Field(ge=1, le=200)
    call_timeout_seconds: float = Field(gt=0, le=7200)
    worker_timeout_seconds: float = Field(gt=0, le=86400)


class RehearsalCase(_Strict):
    case_id: Identifier
    source_world_id: Identifier
    question: str = Field(min_length=1, max_length=4000)


class RehearsalPlan(_Strict):
    """Question-only case inventory; criteria and roles stay with organizers."""

    schema_version: Literal["deepr-expert-value-rehearsal-plan-v1"]
    cases: list[RehearsalCase] = Field(min_length=1, max_length=64)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def tree_digest(root: Path) -> str:
    """Digest of relative paths and bytes; detects any consultation write."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(_sha(path.read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


_IDENTITY_MODULES = (
    "evals/expert_value_rehearsal.py",
    "evals/expert_value_rehearsal_worker.py",
    "evals/expert_value_materialize.py",
    "evals/expert_value_source_copy.py",
    "evals/expert_value_sources.py",
    "experts/investigation/ollama_backend.py",
    "experts/study.py",
    "experts/brief.py",
)


def module_hashes() -> dict[str, str]:
    """Hashes of the runtime sources a rehearsal phase depends on, as imported now."""
    package = Path(__file__).resolve().parents[1]
    return {name: _sha((package / name).read_bytes()) for name in _IDENTITY_MODULES}


def application_identity() -> dict[str, Any]:
    """Commit and runtime source hashes, so software changes are separable from memory effects."""
    package = Path(__file__).resolve().parents[1]
    identity: dict[str, Any] = {"package_root": str(package), "module_sha256": module_hashes()}
    git = shutil.which("git")
    try:
        if git is None:
            raise OSError("git is not installed")
        head = subprocess.run(  # noqa: S603 - resolved git, fixed read-only arguments
            [git, "rev-parse", "HEAD"], cwd=package, capture_output=True, text=True, timeout=10, check=True
        )
        dirty = subprocess.run(  # noqa: S603 - resolved git, fixed read-only arguments
            [git, "status", "--porcelain", "--", "."], cwd=package, capture_output=True, text=True, timeout=10
        )
        identity.update(commit=head.stdout.strip(), worktree_clean=not dirty.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        identity.update(commit=None, worktree_clean=None)
    return identity


def runtime_preflight(policy: RehearsalPolicy) -> dict[str, Any]:
    """Refuse before any worker when the local server or model identity differs."""
    import httpx

    from deepr.backends.capacity import validate_owned_local_ollama_cloud_status, validate_owned_local_ollama_url

    base = validate_owned_local_ollama_url(policy.ollama_base_url)
    with httpx.Client(timeout=5.0, trust_env=False, follow_redirects=False) as client:
        version = client.get(f"{base}/api/version").json()
        status = client.get(f"{base}/api/status").json()
        tags = client.get(f"{base}/api/tags").json()
    validate_owned_local_ollama_cloud_status(status)
    entry = next((m for m in tags.get("models", []) if m.get("name") == policy.model), None)
    if entry is None or entry.get("digest") != policy.model_digest:
        raise ValueError("installed local model digest differs from the frozen policy")
    return {"ollama_version": version.get("version"), "cloud_status": status, "model": entry}


def warmup_throughput(
    policy: RehearsalPolicy, *, min_tokens_per_second: float, backend: Any | None = None
) -> dict[str, Any]:
    """One short $0 local generation; refuse a run the machine cannot currently sustain.

    A shared or saturated GPU can slow generation by orders of magnitude, and
    every later call would then end as a timeout that measures contention, not
    the protocol. The warm-up uses the same attested native backend as workers
    and is recorded in the canonical ledger like any call.
    """
    import asyncio

    from deepr.experts.chat_backends import ExpertChatRequest
    from deepr.experts.investigation.ollama_backend import NativeOllamaInvestigationBackend
    from deepr.observability.cost_ledger import CostLedger

    request_id = f"rehearsal-warmup:{secrets.token_hex(8)}"
    CostLedger().record_event(
        operation="expert_value_rehearsal",
        provider="local",
        cost_usd=0,
        model=policy.model,
        request_id=request_id,
        source="local_value_rehearsal",
        idempotency_key=request_id,
        metadata={"status": "attempted", "purpose": "throughput_warmup"},
        require_fsync=True,
    )
    client = backend or NativeOllamaInvestigationBackend(
        model=policy.model, base_url=policy.ollama_base_url, timeout=min(policy.call_timeout_seconds, 600.0)
    )
    request = ExpertChatRequest(
        model=policy.model,
        messages=[{"role": "user", "content": "List the integers from 1 to 40, separated by spaces."}],
        extra={
            "num_ctx": policy.num_ctx,
            "max_tokens": 96,
            "temperature": 0.0,
            "seed": policy.seed,
            "think": policy.think,
        },
    )
    result = asyncio.run(client.complete(request))
    if client.last_attested_digest != policy.model_digest:
        raise ValueError("warm-up model digest differs from the frozen policy")
    data = result.raw_response or {}
    tokens = int(data.get("eval_count", 0) or 0)
    seconds = int(data.get("eval_duration", 0) or 0) / 1e9
    rate = tokens / seconds if seconds > 0 else 0.0
    if rate < min_tokens_per_second:
        raise ValueError(
            f"local generation is {rate:.2f} tokens/s, below the {min_tokens_per_second:g} floor; "
            "free the GPU and retry"
        )
    return {"warmup_tokens": tokens, "warmup_tokens_per_second": round(rate, 2), "warmup_request_id": request_id}


def worker_environment(worker_dir: Path, policy: RehearsalPolicy) -> dict[str, str]:
    """Explicit allowlisted environment; nothing credential-bearing is inherited."""
    env = {name: os.environ[name] for name in _PASSTHROUGH_ENV if name in os.environ}
    home = worker_dir / "home"
    temp = worker_dir / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    temp.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "PATH": str(Path(sys.executable).parent),
            # Workers import the same source tree as the orchestrator, not an ambient install.
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home),
            "LOCALAPPDATA": str(home),
            "TEMP": str(temp),
            "TMP": str(temp),
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "DEEPR_DATA_DIR": str(worker_dir / "data"),
            "DEEPR_EXPERTS_PATH": str(worker_dir / "data" / "experts"),
            "DEEPR_COST_DATA_DIR": str(worker_dir / "costs"),
            "OLLAMA_HOST": policy.ollama_base_url,
        }
    )
    return env


def subprocess_launcher(spec_path: Path, env: dict[str, str], cwd: Path, timeout: float) -> int:
    """Launch one worker process; timeout is a terminal failure, never a retry."""
    with (cwd / "stdout.log").open("wb") as stdout, (cwd / "stderr.log").open("wb") as stderr:
        try:
            completed = subprocess.run(  # noqa: S603 - fixed interpreter and module
                [sys.executable, "-m", WORKER_MODULE, str(spec_path)],
                env=env,
                cwd=cwd,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return -1
    return completed.returncode


Launcher = Callable[[Path, dict[str, str], Path, float], int]


class RehearsalRun:
    """Durable state and append-only lifecycle events for one run root."""

    def __init__(
        self,
        *,
        policy: RehearsalPolicy,
        plan: RehearsalPlan,
        index_path: Path,
        artifact_root: Path,
        run_root: Path,
        launcher: Launcher = subprocess_launcher,
        runtime: dict[str, Any] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        resume: bool = False,
    ) -> None:
        self.policy, self.plan, self.launcher = policy, plan, launcher
        self.on_event = on_event
        self.index_path, self.artifact_root = index_path, artifact_root.resolve(strict=True)
        _, _, worlds, _, _ = load_source_world_preparation(index_path, self.artifact_root)
        self.worlds = worlds
        world_ids = [w.source_world_id for w in worlds]
        unknown = {c.source_world_id for c in plan.cases} - set(world_ids)
        if unknown:
            raise ValueError("plan cases reference worlds outside the preparation index")
        if len({c.case_id.casefold() for c in plan.cases}) != len(plan.cases):
            raise ValueError("plan case ids must be unique, ignoring letter case")
        target = run_root.absolute()
        if target.resolve().is_relative_to(self.artifact_root):
            raise ValueError("rehearsal run root must be outside the preparation artifact root")
        self.root = target
        self.events = target / "events.jsonl"
        self.cells: list[dict[str, Any]] = []
        self.workers: list[dict[str, Any]] = []
        self.checkpoint_hashes: dict[str, str] = {}
        self.finished_workers: dict[str, dict[str, Any]] = {}
        self.arm_orders: dict[str, list[str]] = {}
        self.experts_baseline: str | None = None
        self.resumed = resume
        if resume:
            if not target.is_dir():
                raise ValueError("resume needs an existing rehearsal run root")
            self._lock = _exclusive_run_lock(target)
            try:
                self._load_existing(runtime)
            except BaseException:
                self._lock.release()
                raise
            return
        if target.exists():
            raise FileExistsError("rehearsal run root must be new; pass resume to continue an interrupted run")
        target.mkdir(parents=True)
        self._lock = _exclusive_run_lock(target)
        self.run_id = secrets.token_hex(8)
        self._write(
            "run.json",
            {
                "run_id": self.run_id,
                "created_at": _now(),
                "index_path": str(index_path),
                "application": application_identity(),
                "runtime": runtime,
            },
        )
        self._write("policy.json", policy.model_dump())
        self._write("plan.json", plan.model_dump())

    def _load_existing(self, runtime: dict[str, Any] | None) -> None:
        """Verify an interrupted run and restore its state; never assume a file is valid.

        Resume requires byte-identical policy, plan and hashed modules, so one
        run never mixes code versions. Finished phases keep their records and
        are not rerun. A worker directory without an orchestrator record was
        interrupted: it is moved aside as abandoned evidence, its recorded
        attempts are mirrored to the ledger, and the phase runs again.
        """
        if not (self.root / "run.json").is_file():
            raise ValueError("resume needs an existing rehearsal run root")
        record = json.loads((self.root / "run.json").read_text(encoding="utf-8"))
        if record["application"]["module_sha256"] != module_hashes():
            raise ValueError("rehearsal code changed since this run started; start a new run root")
        stored_policy = json.loads((self.root / "policy.json").read_text(encoding="utf-8"))
        stored_plan = json.loads((self.root / "plan.json").read_text(encoding="utf-8"))
        if stored_policy != self.policy.model_dump() or stored_plan != self.plan.model_dump():
            raise ValueError("resume needs the run's original policy and plan")
        summary = _json_object(self.root / "summary.json") or {}
        if summary.get("status") == "operationally_complete":
            raise ValueError("this run already finished; nothing to resume")
        self.run_id = record["run_id"]
        events = _jsonl(self.events)
        started = next((e for e in events if e["event"] == "run_started"), {})
        self.experts_baseline = started.get("experts_fingerprint")
        for event in events:
            if event["event"] == "case_arm_order":
                self.arm_orders.setdefault(event["case"], list(event["order"]))
            elif event["event"] == "checkpoint_accepted":
                self.checkpoint_hashes[event["checkpoint"]] = event["sha256"]
        self._verify_checkpoints()
        self._verify_cells()
        self._restore_workers()
        self.event("run_resumed", cells=len(self.cells), finished_workers=len(self.finished_workers), runtime=runtime)

    def _verify_checkpoints(self) -> None:
        for name, digest in self.checkpoint_hashes.items():
            if tree_digest(self.root / "checkpoints" / name) != digest:
                raise ValueError(f"accepted checkpoint {name} changed; start a new run root")
        base = self.root / "checkpoints"
        for path in sorted(base.iterdir()) if base.is_dir() else []:
            if path.is_dir() and path.name not in self.checkpoint_hashes and ".abandoned-" not in path.name:
                path.rename(_abandoned_name(path))

    def _verify_cells(self) -> None:
        questions = {c.case_id: _sha(c.question.encode("utf-8")) for c in self.plan.cases}
        for path in sorted((self.root / "cells").rglob("*.json")) if (self.root / "cells").is_dir() else []:
            cell = json.loads(path.read_text(encoding="utf-8"))
            if cell.get("question_sha256") != questions.get(cell["acceptance_case_id"]):
                raise ValueError(f"recorded cell {path.name} does not match the plan")
            if (
                cell["status"] == "answered"
                and _sha((self.root / cell["answer_ref"]).read_bytes()) != cell["answer_sha256"]
            ):
                raise ValueError(f"answer bytes changed for {cell['acceptance_case_id']}/{cell['arm']}")
            self.cells.append(cell)

    def _restore_workers(self) -> None:
        base = self.root / "workers"
        for path in sorted(base.iterdir()) if base.is_dir() else []:
            if not path.is_dir() or ".abandoned-" in path.name:
                continue
            finished = _json_object(path / "orchestrator.json")
            if finished is not None and finished.get("status") != "interrupted":
                self.finished_workers[path.name] = finished
                self.workers.append(finished)
                continue
            moved = path.rename(_abandoned_name(path))
            spec = _json_object(moved / "spec.json") or {}
            record = {
                "worker_id": moved.name,
                "phase": spec.get("phase", "unknown"),
                "status": "abandoned",
                "usage": _call_usage(moved / "out" / "calls.jsonl"),
                "wall_seconds": 0.0,
                "module_sha256": module_hashes(),
                "worker_ledger_events": len(_jsonl(moved / "costs" / "cost_ledger.jsonl")),
                "canonical_ledger_events": self._mirror_ledger(moved),
            }
            (moved / "orchestrator.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
            self.workers.append(record)
            self.event("worker_abandoned", worker_id=path.name, moved_to=moved.name)

    def _write(self, relative: str, payload: Any) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def event(self, kind: str, **fields: Any) -> None:
        record = {"at": _now(), "event": kind, **fields}
        with open(self.events, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if self.on_event is not None:
            self.on_event(record)

    def _prepare(
        self, worker_dir: Path, worker_id: str, phase: str, world_id: str, checkpoint: Path | None, question: str | None
    ) -> tuple[Path, str, str | None]:
        """Materialize inputs and write the spec; returns spec path, input digest and memory digest."""
        if question is not None and phase != "answer":
            raise ValueError("only answer workers receive a question")
        (worker_dir / "out").mkdir(parents=True)
        world = next(w for w in self.worlds if w.source_world_id == world_id)
        copy = materialize_source_world_copy(
            self.index_path, self.artifact_root, world_id=world_id, output_root=worker_dir / "input"
        )
        spec: dict[str, Any] = {
            "run_id": self.run_id,
            "worker_id": worker_id,
            # Unique per launch, so a phase rerun after an interruption never reuses a request id.
            "attempt_id": secrets.token_hex(4),
            "phase": phase,
            "input_copy": str(worker_dir / "input"),
            "information_cutoff": world.information_cutoff,
            "output_dir": str(worker_dir / "out"),
            "policy": self.policy.model_dump(),
        }
        memory_before = None
        if checkpoint is not None:
            # A private copy per worker; the frozen checkpoint itself is never opened for writing.
            shutil.copytree(checkpoint, worker_dir / "memory")
            spec["prior_checkpoint"] = str(worker_dir / "memory")
            memory_before = tree_digest(worker_dir / "memory")
        if question is not None:
            spec["question"] = question
        spec_path = worker_dir / "spec.json"
        spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
        return spec_path, str(copy["copy_manifest_sha256"]), memory_before

    def _worker(
        self,
        worker_id: str,
        phase: str,
        world_id: str,
        *,
        checkpoint: Path | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        """Run one phase; every outcome, including orchestrator errors, becomes a record."""
        if worker_id in self.finished_workers:
            return self.finished_workers[worker_id]
        worker_dir = self.root / "workers" / worker_id
        result: dict[str, Any] = {"status": "failed", "error_type": "OrchestratorError"}
        started = time.monotonic()
        code: int | None = None
        memory_before: str | None = None
        try:
            spec_path, input_sha, memory_before = self._prepare(
                worker_dir, worker_id, phase, world_id, checkpoint, question
            )
            result["input_copy_manifest_sha256"] = input_sha
            self.event("worker_started", worker_id=worker_id, phase=phase, world=world_id)
            code = self.launcher(
                spec_path, worker_environment(worker_dir, self.policy), worker_dir, self.policy.worker_timeout_seconds
            )
            result = _reported_outcome(code, _json_object(worker_dir / "out" / "result.json"), result)
        # Any failure preparing or launching becomes this phase's recorded terminal cause.
        except Exception as error:
            result.update(status="failed", error_type=type(error).__name__, error=str(error)[:500])
        except BaseException:
            # Marked so a resume reruns this phase instead of trusting a half-finished record.
            result.update(status="interrupted", error_type="Interrupted")
            raise
        finally:
            self._finish(worker_dir, result, worker_id, phase, world_id, code, started, memory_before)
        return result

    def _finish(
        self,
        worker_dir: Path,
        result: dict[str, Any],
        worker_id: str,
        phase: str,
        world_id: str,
        code: int | None,
        started: float,
        memory_before: str | None,
    ) -> None:
        """Record timing, memory digests and ledger mirroring even when interrupted."""
        result.update(
            worker_id=worker_id,
            phase=phase,
            source_world_id=world_id,
            exit_code=code,
            wall_seconds=round(time.monotonic() - started, 3),
            usage=_call_usage(worker_dir / "out" / "calls.jsonl"),
        )
        if memory_before is not None:
            result["memory_before_sha256"] = memory_before
            result["memory_after_sha256"] = tree_digest(worker_dir / "memory")
        result["worker_ledger_events"] = len(_jsonl(worker_dir / "costs" / "cost_ledger.jsonl"))
        try:
            result["canonical_ledger_events"] = self._mirror_ledger(worker_dir)
        # A mirroring failure is surfaced as an unreconciled ledger, never swallowed.
        except Exception as error:
            result.update(canonical_ledger_events=0, ledger_mirror_error=type(error).__name__)
        if worker_dir.is_dir():
            (worker_dir / "orchestrator.json").write_text(
                json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
            )
        self.workers.append(result)
        self.event("worker_finished", worker_id=worker_id, status=result.get("status"), exit_code=code)

    def _mirror_ledger(self, worker_dir: Path) -> int:
        """Mirror every attempt the worker recorded before dispatch into the canonical ledger.

        The worker ledger is written before each call, so an attempt killed
        mid-call is still mirrored; completion details are joined when present.
        """
        from deepr.observability.cost_ledger import CostLedger

        attempts = _jsonl(worker_dir / "costs" / "cost_ledger.jsonl")
        if not attempts:
            return 0
        completions = {call.get("request_id"): call for call in _jsonl(worker_dir / "out" / "calls.jsonl")}
        ledger = CostLedger()
        for attempt in attempts:
            request_id = str(attempt.get("request_id", ""))
            call = completions.get(request_id, {})
            raw = call.get("raw_response") or {}
            ledger.record_event(
                operation="expert_value_rehearsal",
                provider="local",
                cost_usd=0,
                model=self.policy.model,
                tokens_input=int(raw.get("prompt_eval_count", 0) or 0),
                tokens_output=int(raw.get("eval_count", 0) or 0),
                request_id=request_id,
                source="local_value_rehearsal",
                idempotency_key=f"rehearsal:{request_id}",
                metadata={
                    "status": call.get("status", "no_completion_record"),
                    "prompt_sha256": (attempt.get("metadata") or {}).get("prompt_sha256", ""),
                },
                require_fsync=True,
            )
        return len(attempts)

    def _accept_checkpoint(self, name: str, worker: dict[str, Any]) -> Path | None:
        source = self.root / "workers" / worker["worker_id"] / "out" / "checkpoint"
        if worker.get("status") != "completed" or not source.is_dir():
            return None
        target = self.root / "checkpoints" / name
        if name in self.checkpoint_hashes and target.is_dir():
            return target
        try:
            shutil.copytree(source, target)
        except OSError as error:
            self.event("checkpoint_rejected", checkpoint=name, error_type=type(error).__name__)
            return None
        self.checkpoint_hashes[name] = tree_digest(target)
        self.event("checkpoint_accepted", checkpoint=name, sha256=self.checkpoint_hashes[name])
        return target

    def _cell(self, case: RehearsalCase, arm: str, **fields: Any) -> None:
        record = {
            "schema_version": CELL_SCHEMA,
            "acceptance_case_id": case.case_id,
            "source_world_id": case.source_world_id,
            "arm": arm,
            "question_sha256": _sha(case.question.encode("utf-8")),
            **fields,
        }
        self.cells.append(record)
        self._write(f"cells/{case.source_world_id}/{case.case_id}/{arm}.json", record)
        self.event("cell_terminal", case=case.case_id, arm=arm, status=record["status"])

    def _answer_cell(self, case: RehearsalCase, arm: str, checkpoint: Path | None, **extra: Any) -> None:
        worker_id = f"answer-{case.case_id}-{arm}"
        worker = self._worker(worker_id, "answer", case.source_world_id, checkpoint=checkpoint, question=case.question)
        answer = self.root / "workers" / worker_id / "out" / "answer.md"
        answered = worker.get("status") == "completed" and answer.is_file()
        if answered and worker.get("question_sha256") != _sha(case.question.encode("utf-8")):
            answered = False
            worker["error_type"] = "QuestionMismatch"
        before, after = worker.get("memory_before_sha256"), worker.get("memory_after_sha256")
        digests = worker.get("source_digests")
        fields: dict[str, Any] = {
            "status": "answered" if answered else "failed",
            "worker_id": worker_id,
            "memory_checkpoint": checkpoint.name if checkpoint else None,
            "memory_unchanged": None if checkpoint is None else before is not None and before == after,
            "input_copy_manifest_sha256": worker.get("input_copy_manifest_sha256"),
            "source_digests_sha256": _sha(json.dumps(digests).encode("utf-8")) if digests else None,
            "stop_reason": worker.get("stop_reason"),
            "answer_truncated": worker.get("answer_truncated"),
            **extra,
        }
        if answered:
            fields["answer_ref"] = answer.relative_to(self.root).as_posix()
            fields["answer_sha256"] = _sha(answer.read_bytes())
        else:
            fields["reason"] = worker.get("error_type") or "answer_missing"
        self._cell(case, arm, **fields)

    def execute(self) -> dict[str, Any]:
        started = time.monotonic()
        if self.resumed:
            experts_before = self.experts_baseline
        else:
            experts_before = _experts_fingerprint()
            self.event("run_started", experts_fingerprint=experts_before)
        try:
            first = self.worlds[0].source_world_id
            compiled = self._accept_checkpoint("compiled-w1", self._worker("construct-compiled", "construct", first))
            maintained: Path | None = compiled
            for index, world in enumerate(self.worlds):
                maintained, maintenance = self._maintain(index, world.source_world_id, maintained)
                for case in (c for c in self.plan.cases if c.source_world_id == world.source_world_id):
                    self._run_case(case, compiled, maintained, maintenance)
        except KeyboardInterrupt:
            self.event("run_interrupted")
            raise
        finally:
            try:
                summary = self.summary(time.monotonic() - started, experts_before)
                self._write("summary.json", summary)
                self.event("run_finished", status=summary["status"])
            finally:
                self._lock.release()
        return summary

    def _maintain(self, index: int, world_id: str, maintained: Path | None) -> tuple[Path | None, dict[str, Any]]:
        """Update the maintained checkpoint before a later world; a failure keeps the last one."""
        if index == 0 or maintained is None:
            return maintained, {"maintenance_status": "not_applicable"}
        update = self._worker(f"maintain-{world_id}", "maintain", world_id, checkpoint=maintained)
        accepted = self._accept_checkpoint(f"maintained-{world_id}", update)
        if accepted is None:
            return maintained, {
                "maintenance_status": "failed_kept_last_checkpoint",
                "maintenance_error": update.get("error_type"),
            }
        return accepted, {"maintenance_status": "completed"}

    def _run_case(
        self, case: RehearsalCase, compiled: Path | None, maintained: Path | None, maintenance: dict[str, Any]
    ) -> None:
        """Every arm of one case, in its recorded or newly drawn order; recorded cells are skipped."""
        arms = self.arm_orders.get(case.case_id)
        if arms is None:
            arms = list(ARM_ORDER)
            secrets.SystemRandom().shuffle(arms)
            self.arm_orders[case.case_id] = arms
            self.event("case_arm_order", case=case.case_id, order=arms)
        done = {(c["acceptance_case_id"], c["arm"]) for c in self.cells}
        for arm in arms:
            if (case.case_id, arm) in done:
                continue
            recorded = len(self.cells)
            try:
                self._run_arm(case, arm, compiled, maintained, maintenance)
            # One broken cell must not end the run; it is recorded as failed.
            except Exception as error:
                if len(self.cells) == recorded:
                    self._cell(case, arm, status="failed", reason=f"OrchestratorError:{type(error).__name__}")

    def _run_arm(
        self,
        case: RehearsalCase,
        arm: str,
        compiled: Path | None,
        maintained: Path | None,
        maintenance: dict[str, Any],
    ) -> None:
        if arm == "static_history":
            self._answer_cell(case, arm, None)
        elif arm == "fresh_research":
            built = self._worker(f"construct-fresh-{case.case_id}", "construct", case.source_world_id)
            checkpoint = self._accept_checkpoint(f"fresh-{case.case_id}", built)
            if checkpoint is None:
                self._cell(case, arm, status="blocked", reason="fresh_construction_failed")
            else:
                self._answer_cell(case, arm, checkpoint)
        elif compiled is None:
            self._cell(case, arm, status="blocked", reason="compiled_construction_failed")
        elif arm == "compiled_expert":
            self._answer_cell(case, arm, compiled)
        else:
            self._answer_cell(case, arm, maintained, **maintenance)

    def _checks(self, experts_before: str | None) -> dict[str, bool | None]:
        """Integrity checks; ``None`` means no applicable evidence, never a vacuous pass."""
        answered = [c for c in self.cells if c["status"] == "answered"]
        by_world: dict[str, set[Any]] = {}
        for cell in answered:
            key = (cell.get("input_copy_manifest_sha256"), cell.get("source_digests_sha256"))
            by_world.setdefault(cell["source_world_id"], set()).add(key)
        with_memory = [c for c in self.cells if c.get("memory_unchanged") is not None]
        expected_modules = module_hashes()
        # Only workers that ran far enough to report their imported code can be compared.
        reported = [w for w in self.workers if "module_sha256" in w]
        calls = sum(w["usage"]["calls"] for w in self.workers)
        ledgers = sum(w.get("worker_ledger_events", 0) for w in self.workers)
        mirrored = sum(w.get("canonical_ledger_events", 0) for w in self.workers)
        checkpoints = self.checkpoint_hashes.items()
        return {
            "equal_source_inventory_per_world": all(len(v) == 1 for v in by_world.values()) if answered else None,
            "worker_code_matches_orchestrator": (
                all(w["module_sha256"] == expected_modules for w in reported) if reported else None
            ),
            "consultation_memory_unchanged": all(c["memory_unchanged"] for c in with_memory) if with_memory else None,
            "frozen_checkpoints_unchanged": (
                all(tree_digest(self.root / "checkpoints" / n) == d for n, d in checkpoints) if checkpoints else None
            ),
            "canonical_experts_unchanged": None if experts_before is None else _experts_fingerprint() == experts_before,
            "ledger_reconciled": ledgers == mirrored and calls <= ledgers,
        }

    def summary(self, elapsed: float, experts_before: str | None = None) -> dict[str, Any]:
        """Operational completeness requires every cell and no failed integrity check."""
        planned = len(self.plan.cases) * len(ARM_ORDER)
        statuses = [c["status"] for c in self.cells]
        checks = self._checks(experts_before)
        failed_checks = sorted(name for name, value in checks.items() if value is False)
        calls = sum(w["usage"]["calls"] for w in self.workers)
        ledgers = sum(w.get("worker_ledger_events", 0) for w in self.workers)
        complete = len(self.cells) == planned and not failed_checks
        return {
            "schema_version": SUMMARY_SCHEMA,
            "status": "operationally_complete" if complete else "incomplete",
            "planned_cells": planned,
            "terminal_cells": len(self.cells),
            "answered": statuses.count("answered"),
            "failed": statuses.count("failed"),
            "blocked": statuses.count("blocked"),
            "truncated_answers": sum(1 for c in self.cells if c.get("answer_truncated")),
            **checks,
            "failed_checks": failed_checks,
            "checkpoint_sha256": dict(sorted(self.checkpoint_hashes.items())),
            "model_calls": calls,
            "worker_ledger_events": ledgers,
            "canonical_ledger_events": sum(w.get("canonical_ledger_events", 0) for w in self.workers),
            "attempts_without_completion_record": ledgers - calls,
            "resources_by_phase": _resources(self.workers),
            "elapsed_seconds": round(elapsed, 3),
            "api_cost_usd": 0,
            "semantic_review_performed": False,
            "review_blinding_verified": False,
            "process_network_confined": False,
            "value_claim": None,
        }


def _call_usage(calls_path: Path) -> dict[str, int]:
    usage = {"calls": 0, "returned": 0, "prompt_tokens": 0, "output_tokens": 0}
    for record in _jsonl(calls_path):
        raw = record.get("raw_response") or {}
        usage["calls"] += 1
        usage["returned"] += record.get("status") == "returned"
        usage["prompt_tokens"] += int(raw.get("prompt_eval_count", 0) or 0)
        usage["output_tokens"] += int(raw.get("eval_count", 0) or 0)
    return usage


def _reported_outcome(code: int, reported: dict[str, Any] | None, pending: dict[str, Any]) -> dict[str, Any]:
    """Combine the launcher's exit with the worker's own record; the worker never overrides a timeout."""
    if code == -1:
        return {**pending, "error_type": "WorkerTimeout"}
    if reported is None:
        return {**pending, "error_type": "WorkerResultMissing"}
    merged = {**pending, **reported}
    if reported.get("status") == "completed":
        merged.pop("error_type", None)
    return merged


def _exclusive_run_lock(root: Path) -> Any:
    """Hold the run root for one writer; the OS releases it if the holder dies."""
    from filelock import FileLock, Timeout

    lock = FileLock(str(root / ".run.lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout as error:
        raise ValueError("another process is running this rehearsal run root") from error
    return lock


def _abandoned_name(path: Path) -> Path:
    """A new sibling name that preserves an interrupted directory as evidence."""
    index = 1
    while (candidate := path.with_name(f"{path.name}.abandoned-{index}")).exists():
        index += 1
    return candidate


def _json_object(path: Path) -> dict[str, Any] | None:
    """A worker's result record, or None when missing or unreadable."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _experts_fingerprint() -> str | None:
    """Cheap path, size and mtime digest of the operator's canonical experts root."""
    from deepr.config import experts_root

    root = experts_root()
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        info = path.stat()
        line = f"{path.relative_to(root).as_posix()}|{info.st_size}|{info.st_mtime_ns}"
        digest.update(line.encode("utf-8") + b"\n")
    return digest.hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    """Complete JSON lines of an append-only record; a torn final line is ignored."""
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _resources(workers: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Construction, maintenance and consultation work reported separately."""
    totals: dict[str, dict[str, float]] = {}
    for worker in workers:
        bucket = totals.setdefault(
            worker["phase"], {"workers": 0, "calls": 0, "prompt_tokens": 0, "output_tokens": 0, "wall_seconds": 0.0}
        )
        bucket["workers"] += 1
        bucket["calls"] += worker["usage"]["calls"]
        bucket["prompt_tokens"] += worker["usage"]["prompt_tokens"]
        bucket["output_tokens"] += worker["usage"]["output_tokens"]
        bucket["wall_seconds"] = round(bucket["wall_seconds"] + worker["wall_seconds"], 3)
    return totals


def plan_from_blueprint(blueprint: dict[str, Any], placement: dict[str, Any]) -> RehearsalPlan:
    """Extract question-only cases; criteria, roles and notes are not copied."""
    worlds = {c["acceptance_case_id"]: c["source_world_id"] for c in placement["cases"]}
    cases = [
        RehearsalCase(case_id=c["id"], source_world_id=worlds[c["id"]], question=c["question"])
        for c in blueprint["acceptance_cases"]
    ]
    return RehearsalPlan(schema_version=PLAN_SCHEMA, cases=cases)


__all__ = [
    "RehearsalCase",
    "RehearsalPlan",
    "RehearsalPolicy",
    "RehearsalRun",
    "plan_from_blueprint",
    "subprocess_launcher",
    "tree_digest",
    "worker_environment",
]
