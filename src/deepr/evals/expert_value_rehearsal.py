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


def application_identity() -> dict[str, Any]:
    """Commit and runtime source hashes, so software changes are separable from memory effects."""
    package = Path(__file__).resolve().parents[1]
    identity: dict[str, Any] = {
        "package_root": str(package),
        "module_sha256": {name: _sha((package / name).read_bytes()) for name in _IDENTITY_MODULES},
    }
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
    policy: RehearsalPolicy, *, min_tokens_per_second: float, post: Callable[..., Any] | None = None
) -> dict[str, Any]:
    """One short $0 local generation; refuse a run the machine cannot currently sustain.

    A shared or saturated GPU can slow generation by orders of magnitude, and
    every later call would then end as a timeout that measures contention, not
    the protocol. The warm-up is recorded in the canonical ledger like any call.
    """
    import httpx

    from deepr.observability.cost_ledger import CostLedger

    request_id = f"rehearsal-warmup:{secrets.token_hex(8)}"
    payload = {
        "model": policy.model,
        "messages": [{"role": "user", "content": "List the integers from 1 to 40, separated by spaces."}],
        "stream": False,
        "think": policy.think,
        "options": {"num_ctx": policy.num_ctx, "num_predict": 96, "temperature": 0.0, "seed": policy.seed},
    }
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
    if post is None:
        with httpx.Client(timeout=min(policy.call_timeout_seconds, 600.0), trust_env=False) as client:
            data = client.post(f"{policy.ollama_base_url}/api/chat", json=payload).json()
    else:
        data = post(payload)
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
    try:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and module
            [sys.executable, "-m", WORKER_MODULE, str(spec_path)],
            env=env,
            cwd=cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            stdout=(cwd / "stdout.log").open("wb"),
            stderr=(cwd / "stderr.log").open("wb"),
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
    ) -> None:
        self.policy, self.plan, self.launcher = policy, plan, launcher
        self.index_path, self.artifact_root = index_path, artifact_root.resolve(strict=True)
        _, _, worlds, _, _ = load_source_world_preparation(index_path, self.artifact_root)
        self.worlds = worlds
        world_ids = [w.source_world_id for w in worlds]
        unknown = {c.source_world_id for c in plan.cases} - set(world_ids)
        if unknown:
            raise ValueError("plan cases reference worlds outside the preparation index")
        if len({c.case_id for c in plan.cases}) != len(plan.cases):
            raise ValueError("plan case ids must be unique")
        target = run_root.absolute()
        if target.exists():
            raise FileExistsError("rehearsal run root must be new")
        if target.resolve().is_relative_to(self.artifact_root):
            raise ValueError("rehearsal run root must be outside the preparation artifact root")
        target.mkdir(parents=True)
        self.root = target
        self.run_id = secrets.token_hex(8)
        self.events = target / "events.jsonl"
        self.cells: list[dict[str, Any]] = []
        self.workers: list[dict[str, Any]] = []
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

    def _write(self, relative: str, payload: Any) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def event(self, kind: str, **fields: Any) -> None:
        with open(self.events, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": _now(), "event": kind, **fields}, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _worker(
        self,
        worker_id: str,
        phase: str,
        world_id: str,
        *,
        checkpoint: Path | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        worker_dir = self.root / "workers" / worker_id
        worker_dir.mkdir(parents=True)
        (worker_dir / "out").mkdir()
        world = next(w for w in self.worlds if w.source_world_id == world_id)
        copy = materialize_source_world_copy(
            self.index_path, self.artifact_root, world_id=world_id, output_root=worker_dir / "input"
        )
        spec: dict[str, Any] = {
            "run_id": self.run_id,
            "worker_id": worker_id,
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
            if phase != "answer":
                raise ValueError("only answer workers receive a question")
            spec["question"] = question
        spec_path = worker_dir / "spec.json"
        spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
        self.event("worker_started", worker_id=worker_id, phase=phase, world=world_id)
        started = time.monotonic()
        code = self.launcher(
            spec_path, worker_environment(worker_dir, self.policy), worker_dir, self.policy.worker_timeout_seconds
        )
        result_path = worker_dir / "out" / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
        if code == -1:
            result.update(status="failed", error_type="WorkerTimeout")
        elif not result:
            result.update(status="failed", error_type="WorkerExited", exit_code=code)
        result.update(
            worker_id=worker_id,
            phase=phase,
            source_world_id=world_id,
            exit_code=code,
            wall_seconds=round(time.monotonic() - started, 3),
            input_copy_manifest_sha256=copy["copy_manifest_sha256"],
            usage=_call_usage(worker_dir / "out" / "calls.jsonl"),
        )
        if memory_before is not None:
            result["memory_before_sha256"] = memory_before
            result["memory_after_sha256"] = tree_digest(worker_dir / "memory")
        result["canonical_ledger_events"] = self._mirror_ledger(worker_dir / "out" / "calls.jsonl")
        self.workers.append(result)
        self.event("worker_finished", worker_id=worker_id, status=result.get("status"), exit_code=code)
        return result

    def _mirror_ledger(self, calls_path: Path) -> int:
        """Record every dispatched worker call in the operator's canonical ledger at $0."""
        from deepr.observability.cost_ledger import CostLedger

        if not calls_path.is_file():
            return 0
        ledger = CostLedger()
        count = 0
        for line in calls_path.read_text(encoding="utf-8").splitlines():
            call = json.loads(line)
            raw = call.get("raw_response") or {}
            ledger.record_event(
                operation="expert_value_rehearsal",
                provider="local",
                cost_usd=0,
                model=self.policy.model,
                tokens_input=int(raw.get("prompt_eval_count", 0) or 0),
                tokens_output=int(raw.get("eval_count", 0) or 0),
                request_id=call["request_id"],
                source="local_value_rehearsal",
                idempotency_key=f"rehearsal:{call['request_id']}",
                metadata={"status": call.get("status", "unknown"), "prompt_sha256": call.get("prompt_sha256", "")},
                require_fsync=True,
            )
            count += 1
        return count

    def _accept_checkpoint(self, name: str, worker: dict[str, Any]) -> Path | None:
        source = self.root / "workers" / worker["worker_id"] / "out" / "checkpoint"
        if worker.get("status") != "completed" or not source.is_dir():
            return None
        target = self.root / "checkpoints" / name
        shutil.copytree(source, target)
        return target

    def _cell(self, case: RehearsalCase, arm: str, **fields: Any) -> None:
        record = {
            "schema_version": CELL_SCHEMA,
            "acceptance_case_id": case.case_id,
            "source_world_id": case.source_world_id,
            "arm": arm,
            **fields,
        }
        self.cells.append(record)
        self._write(f"cells/{case.source_world_id}/{case.case_id}/{arm}.json", record)
        self.event("cell_terminal", case=case.case_id, arm=arm, status=record["status"])

    def _answer_cell(self, case: RehearsalCase, arm: str, checkpoint: Path | None, **extra: Any) -> None:
        worker_id = f"answer-{case.case_id}-{arm}"
        worker = self._worker(worker_id, "answer", case.source_world_id, checkpoint=checkpoint, question=case.question)
        answer = self.root / "workers" / worker_id / "out" / "answer.md"
        status = "answered" if worker.get("status") == "completed" and answer.is_file() else "failed"
        fields: dict[str, Any] = {
            "status": status,
            "worker_id": worker_id,
            "memory_checkpoint": checkpoint.name if checkpoint else None,
            "memory_unchanged": worker.get("memory_before_sha256") == worker.get("memory_after_sha256"),
            "input_copy_manifest_sha256": worker["input_copy_manifest_sha256"],
            **extra,
        }
        if status == "answered":
            fields["answer_ref"] = answer.relative_to(self.root).as_posix()
            fields["answer_sha256"] = _sha(answer.read_bytes())
        else:
            fields["reason"] = worker.get("error_type") or "answer_missing"
        self._cell(case, arm, **fields)

    def execute(self) -> dict[str, Any]:
        self.event("run_started")
        started = time.monotonic()
        checkpoint_hashes: dict[str, str] = {}
        try:
            first = self.worlds[0].source_world_id
            compiled = self._accept_checkpoint("compiled-w1", self._worker("construct-compiled", "construct", first))
            if compiled is not None:
                checkpoint_hashes[compiled.name] = tree_digest(compiled)
            maintained: Path | None = compiled
            for index, world in enumerate(self.worlds):
                world_id = world.source_world_id
                maintenance: dict[str, Any] = {"maintenance_status": "not_applicable"}
                if index > 0 and maintained is not None:
                    update = self._worker(f"maintain-{world_id}", "maintain", world_id, checkpoint=maintained)
                    accepted = self._accept_checkpoint(f"maintained-{world_id}", update)
                    if accepted is None:
                        maintenance = {
                            "maintenance_status": "failed_kept_last_checkpoint",
                            "maintenance_error": update.get("error_type"),
                        }
                    else:
                        maintained = accepted
                        checkpoint_hashes[accepted.name] = tree_digest(accepted)
                        maintenance = {"maintenance_status": "completed"}
                for case in (c for c in self.plan.cases if c.source_world_id == world_id):
                    arms = list(ARM_ORDER)
                    secrets.SystemRandom().shuffle(arms)
                    self.event("case_arm_order", case=case.case_id, order=arms)
                    for arm in arms:
                        self._run_arm(case, arm, compiled, maintained, maintenance)
        except KeyboardInterrupt:
            self.event("run_interrupted")
            raise
        finally:
            summary = self.summary(checkpoint_hashes, time.monotonic() - started)
            self._write("summary.json", summary)
            self.event("run_finished", status=summary["status"])
        return summary

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

    def summary(self, checkpoint_hashes: dict[str, str], elapsed: float) -> dict[str, Any]:
        planned = len(self.plan.cases) * len(ARM_ORDER)
        statuses = [c["status"] for c in self.cells]
        by_world: dict[str, set[str]] = {}
        for cell in self.cells:
            if "input_copy_manifest_sha256" in cell:
                by_world.setdefault(cell["source_world_id"], set()).add(cell["input_copy_manifest_sha256"])
        checkpoints_unchanged = all(
            tree_digest(self.root / "checkpoints" / name) == digest for name, digest in checkpoint_hashes.items()
        )
        calls = sum(w["usage"]["calls"] for w in self.workers)
        ledgers = sum(_ledger_events(self.root / "workers" / w["worker_id"] / "costs") for w in self.workers)
        mirrored = sum(w.get("canonical_ledger_events", 0) for w in self.workers)
        return {
            "schema_version": SUMMARY_SCHEMA,
            "status": "operationally_complete" if len(self.cells) == planned else "incomplete",
            "planned_cells": planned,
            "terminal_cells": len(self.cells),
            "answered": statuses.count("answered"),
            "failed": statuses.count("failed"),
            "blocked": statuses.count("blocked"),
            "equal_source_inventory_per_world": all(len(v) == 1 for v in by_world.values()),
            "worker_code_matches_orchestrator": all(
                w.get("deepr_package") == str(Path(__file__).resolve().parents[1]) for w in self.workers
            ),
            "consultation_memory_unchanged": all(c.get("memory_unchanged", True) for c in self.cells),
            "frozen_checkpoints_unchanged": checkpoints_unchanged,
            "model_calls": calls,
            "worker_ledger_events": ledgers,
            "canonical_ledger_events": mirrored,
            "ledger_reconciled": calls == ledgers == mirrored,
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
    if not calls_path.is_file():
        return usage
    for line in calls_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        usage["calls"] += 1
        raw = record.get("raw_response") or {}
        if record.get("status") == "returned":
            usage["returned"] += 1
        usage["prompt_tokens"] += int(raw.get("prompt_eval_count", 0) or 0)
        usage["output_tokens"] += int(raw.get("eval_count", 0) or 0)
    return usage


def _ledger_events(cost_dir: Path) -> int:
    ledger = cost_dir / "cost_ledger.jsonl"
    if not ledger.is_file():
        return 0
    return sum(1 for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())


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
