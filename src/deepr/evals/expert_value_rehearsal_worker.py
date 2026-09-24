"""One isolated phase of the local four-arm rehearsal.

Run as ``python -m deepr.evals.expert_value_rehearsal_worker SPEC.json`` by
the rehearsal orchestrator, never by hand. Construction and maintenance read a
verified source copy and write a memory checkpoint; they never receive a case
question. An answer phase receives the question, the complete current source
packet and an optional frozen memory prefix, and makes exactly one call.

The worker refuses to start with dotenv loading enabled or with any
credential-like environment variable. It uses only the native local Ollama
backend and checks the frozen model digest on every dispatch. It is a separate
process with an explicit environment and data root; it is not an OS sandbox,
and loopback network access to the local model server remains available.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

PHASES = ("construct", "maintain", "answer")
EXPERT_NAME = "rehearsal-expert"
_CREDENTIAL_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)", re.IGNORECASE)
ANSWER_INSTRUCTIONS = (
    "You are answering one question for a decision-maker. Use only the numbered source packet below "
    "and any expert memory provided. The information cutoff is {cutoff}; nothing later is known. "
    "Cite sources by their bracketed labels. If the question rests on a false or outdated premise, "
    "say so and give the grounded answer instead. If the sources cannot settle a point, say what is "
    "missing rather than guessing."
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def check_worker_environment(env: dict[str, str]) -> None:
    """Refuse ambient credentials and dotenv loading before importing Deepr state."""
    if env.get("PYTHON_DOTENV_DISABLED") != "1":
        raise RuntimeError("rehearsal worker requires PYTHON_DOTENV_DISABLED=1")
    leaked = sorted(name for name in env if _CREDENTIAL_NAME.search(name))
    if leaked:
        raise RuntimeError(f"rehearsal worker refuses credential-like environment names: {', '.join(leaked)}")
    for required in ("DEEPR_DATA_DIR", "DEEPR_COST_DATA_DIR"):
        if not env.get(required):
            raise RuntimeError(f"rehearsal worker requires {required}")


def _stage_ok(name: str, payload: dict[str, Any]) -> bool:
    from deepr.experts.stage_contract import get_stage

    stage = get_stage(name)
    return stage is not None and stage.succeeds_when is not None and bool(stage.succeeds_when(payload))


def render_memory_prefix(brief_markdown: str, max_chars: int) -> tuple[str, bool]:
    """Apply the frozen mechanical memory limit and disclose truncation."""
    if len(brief_markdown) <= max_chars:
        return brief_markdown, False
    return brief_markdown[:max_chars] + "\n[memory truncated at the frozen limit]\n", True


def render_answer_prompt(question: str, cutoff: str, sources: list[tuple[str, str]], memory: str | None) -> str:
    """One common answer prompt; arms differ only in the memory block."""
    parts = [ANSWER_INSTRUCTIONS.format(cutoff=cutoff), ""]
    if memory:
        parts += [
            "===== EXPERT MEMORY (prior study, may be outdated) =====",
            memory.strip(),
            "===== END MEMORY =====",
            "",
        ]
    parts.append("===== SOURCE PACKET =====")
    for sha, text in sources:
        parts += [f"[S-{sha[:12]}]", text.strip(), ""]
    parts += ["===== END SOURCES =====", "", f"Question: {question.strip()}"]
    return "\n".join(parts)


class _Dispatcher:
    """Bounded, digest-bound, fully recorded local completions for one phase."""

    def __init__(self, spec: dict[str, Any], output: Path) -> None:
        from deepr.experts.investigation.ollama_backend import NativeOllamaInvestigationBackend
        from deepr.observability.cost_ledger import CostLedger

        self.policy = spec["policy"]
        self.worker_id = f"{spec['run_id']}:{spec['worker_id']}"
        self.output = output
        self.calls_path = output / "calls.jsonl"
        self.count = 0
        self.backend = NativeOllamaInvestigationBackend(
            model=self.policy["model"],
            base_url=self.policy["ollama_base_url"],
            timeout=float(self.policy["call_timeout_seconds"]),
            keep_alive="30m",
        )
        self.ledger = CostLedger(Path(os.environ["DEEPR_COST_DATA_DIR"]) / "cost_ledger.jsonl")

    def _append(self, record: dict[str, Any]) -> None:
        with open(self.calls_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    async def complete(self, prompt: str) -> str:
        from deepr.experts.chat_backends import ExpertChatRequest

        if self.count >= int(self.policy["max_calls_per_phase"]):
            raise RuntimeError("rehearsal phase call limit exhausted")
        self.count += 1
        options = {
            "num_ctx": int(self.policy["num_ctx"]),
            "max_tokens": int(self.policy["max_output_tokens"]),
            "temperature": float(self.policy["temperature"]),
            "seed": int(self.policy["seed"]),
            "think": bool(self.policy["think"]),
        }
        request_id = f"{self.worker_id}:{self.count}"
        record: dict[str, Any] = {
            "call": self.count,
            "request_id": request_id,
            "started_at": _now(),
            "model": self.policy["model"],
            "options": options,
            "prompt": prompt,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        }
        # Every dispatched attempt is recorded before the call, at $0 API cost.
        self.ledger.record_event(
            operation="expert_value_rehearsal",
            provider="local",
            cost_usd=0,
            model=self.policy["model"],
            request_id=request_id,
            source="local_value_rehearsal",
            idempotency_key=f"rehearsal:{request_id}",
            metadata={"status": "attempted", "prompt_sha256": record["prompt_sha256"]},
            require_fsync=True,
        )
        started = time.monotonic()
        try:
            result = await self.backend.complete(
                ExpertChatRequest(
                    model=self.policy["model"], messages=[{"role": "user", "content": prompt}], extra=dict(options)
                )
            )
            if self.backend.last_attested_digest != self.policy["model_digest"]:
                raise RuntimeError("observed local model digest differs from the frozen policy")
        except BaseException as error:
            record.update(status="failed", error_type=type(error).__name__, error=str(error)[:500])
            raise
        else:
            text = str(result.message.content or "")
            record.update(
                status="returned",
                observed_digest=self.backend.last_attested_digest,
                stop_reason=result.stop_reason,
                raw_response=result.raw_response,
                response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
            return text
        finally:
            record.update(finished_at=_now(), elapsed_seconds=round(time.monotonic() - started, 3))
            self._append(record)


async def _build_memory(spec: dict[str, Any], output: Path, dispatcher: _Dispatcher) -> dict[str, Any]:
    from deepr.evals.expert_value_materialize import read_source_world_copy
    from deepr.experts.brief import build_brief, render_brief
    from deepr.experts.brief_contracts import ExpertBrief
    from deepr.experts.corpus_store import CorpusStore
    from deepr.experts.stage_contract import STAGE_BRIEF, STAGE_STUDY
    from deepr.experts.study import run_study

    policy = spec["policy"]
    corpus = CorpusStore(EXPERT_NAME, storage_dir=Path(os.environ["DEEPR_DATA_DIR"]) / "corpus")
    for sha, text in read_source_world_copy(Path(spec["input_copy"])):
        corpus.add(text, origin_key=f"source:{sha[:16]}", title=f"S-{sha[:12]}", kind="rehearsal_source")
    prior_positions: list[Any] = []
    history: list[dict[str, Any]] = []
    if spec["phase"] == "maintain":
        prior = Path(spec["prior_checkpoint"])
        prior_brief = ExpertBrief.from_dict(json.loads((prior / "brief.json").read_text(encoding="utf-8")))
        prior_positions = list(prior_brief.positions)
        history = json.loads((prior / "position_history.json").read_text(encoding="utf-8"))
    study = await run_study(
        expert_name=EXPERT_NAME,
        corpus=corpus,
        completion=dispatcher.complete,
        lens_keys=list(policy["lenses"]),
        max_corpus_chars=int(policy["study_max_corpus_chars"]),
        chunk_chars=int(policy["study_chunk_chars"]),
        capacity_source="local",
        model=policy["model"],
    )
    (output / "study.json").write_text(json.dumps(study.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    lenses_ok = len(study.outcomes) == len(policy["lenses"]) and all(o.status == "ok" for o in study.outcomes)
    if not lenses_ok or not _stage_ok(STAGE_STUDY, study.to_dict()):
        raise RuntimeError("study did not reach its usable/complete status")
    cutoff = date.fromisoformat(spec["information_cutoff"][:10])
    brief = await build_brief(
        expert_name=EXPERT_NAME,
        result=study,
        corpus=corpus,
        completion=dispatcher.complete,
        prior_positions=prior_positions or None,
        as_of_date=cutoff,
    )
    (output / "brief.json").write_text(json.dumps(brief.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    if not brief.orientation.strip() or not _stage_ok(STAGE_BRIEF, brief.to_dict()):
        raise RuntimeError("brief lacks orientation or cited positions")
    checkpoint = output / "checkpoint"
    checkpoint.mkdir()
    history.append(
        {
            "information_cutoff": spec["information_cutoff"],
            "worker_id": spec["worker_id"],
            "positions": [p.to_dict() for p in brief.positions],
        }
    )
    (checkpoint / "brief.json").write_text(json.dumps(brief.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    (checkpoint / "brief.md").write_text(render_brief(brief), encoding="utf-8")
    (checkpoint / "position_history.json").write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
    return {"findings": len(study.findings), "positions": len(brief.positions)}


async def _answer(spec: dict[str, Any], output: Path, dispatcher: _Dispatcher) -> dict[str, Any]:
    from deepr.evals.expert_value_materialize import read_source_world_copy

    memory_full = None
    memory_prefix = None
    truncated = False
    if spec.get("prior_checkpoint"):
        memory_full = (Path(spec["prior_checkpoint"]) / "brief.md").read_text(encoding="utf-8")
        memory_prefix, truncated = render_memory_prefix(memory_full, int(spec["policy"]["memory_prefix_max_chars"]))
    sources = read_source_world_copy(Path(spec["input_copy"]))
    prompt = render_answer_prompt(spec["question"], spec["information_cutoff"], sources, memory_prefix)
    text = await dispatcher.complete(prompt)
    (output / "answer.md").write_bytes(text.encode("utf-8"))
    return {
        "answer_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "memory_full_sha256": hashlib.sha256(memory_full.encode()).hexdigest() if memory_full else None,
        "memory_prefix_sha256": hashlib.sha256(memory_prefix.encode()).hexdigest() if memory_prefix else None,
        "memory_truncated": truncated,
        "source_count": len(sources),
    }


def run_worker(spec_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    output = Path(spec["output_dir"])
    result: dict[str, Any] = {"worker_id": spec.get("worker_id"), "phase": spec.get("phase"), "started_at": _now()}
    try:
        check_worker_environment(dict(os.environ))
        if spec["phase"] not in PHASES:
            raise ValueError("unknown rehearsal phase")
        if spec["phase"] != "answer" and "question" in spec:
            raise ValueError("construction and maintenance must not receive a case question")
        dispatcher = _Dispatcher(spec, output)
        runner = _answer if spec["phase"] == "answer" else _build_memory
        result.update(asyncio.run(runner(spec, output, dispatcher)))
        result["status"] = "completed"
    except BaseException as error:  # the orchestrator needs every terminal cause
        result.update(status="failed", error_type=type(error).__name__, error=str(error)[:1000])
    result["model_calls"] = (
        sum(1 for _ in open(output / "calls.jsonl", encoding="utf-8")) if (output / "calls.jsonl").exists() else 0
    )
    result["finished_at"] = _now()
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests
    sys.exit(run_worker(Path(sys.argv[1])))
