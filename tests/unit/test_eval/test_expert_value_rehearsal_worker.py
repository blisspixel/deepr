"""One rehearsal worker phase, in process, against a fake owned-local backend."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deepr.evals import expert_value_rehearsal_worker as worker
from deepr.evals.expert_value_materialize import materialize_source_world_copy
from deepr.experts.investigation import ollama_backend
from tests.unit.test_eval.test_expert_value_sources import Bundle

DIGEST = "b" * 64
ANCHOR = "Synthetic source version 1."


class FakeBackend:
    """Answers each prompt kind with the smallest contract-shaped payload."""

    prompts: list[str] = []
    digest = DIGEST
    fail_on: str | None = None

    def __init__(self, **_kwargs: Any) -> None:
        self.last_attested_digest = ""

    async def complete(self, request: Any) -> Any:
        prompt = request.messages[0]["content"]
        FakeBackend.prompts.append(prompt)
        self.last_attested_digest = FakeBackend.digest
        if FakeBackend.fail_on and FakeBackend.fail_on in prompt:
            raise RuntimeError("fake local failure")
        if "Question:" in prompt:
            text = "Grounded answer citing [S-abc]."
        elif '"orientation"' in prompt:
            ids = sorted(set(re.findall(r"(?:synopsis|change)-[0-9a-f]{16}", prompt)))
            text = json.dumps(
                {
                    "orientation": "Two synthetic versions.",
                    "positions": [
                        {"question": "Which version applies?", "stance": "The later one.", "supported_by": ids}
                    ],
                }
            )
        elif '"changes"' in prompt:
            text = json.dumps({"changes": [{"description": "Version changed", "anchors": [ANCHOR]}]})
        else:
            text = json.dumps({"notes": [{"topic": "Versions", "summary": "Version one exists.", "anchors": [ANCHOR]}]})
        return SimpleNamespace(
            message=SimpleNamespace(content=text),
            raw_response={"prompt_eval_count": 10, "eval_count": 3},
            stop_reason="stop",
        )


def _policy() -> dict[str, Any]:
    return {
        "model": "fixture:14b",
        "model_digest": DIGEST,
        "ollama_base_url": "http://127.0.0.1:11434",
        "num_ctx": 8192,
        "max_output_tokens": 512,
        "temperature": 0.0,
        "seed": 1,
        "think": False,
        "lenses": ["synopsis", "change"],
        "study_max_corpus_chars": 20000,
        "study_chunk_chars": 20000,
        "memory_prefix_max_chars": 40,
        "max_calls_per_phase": 6,
        "call_timeout_seconds": 60,
    }


@pytest.fixture
def phase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in list(__import__("os").environ):
        if worker._CREDENTIAL_NAME.search(name):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
    monkeypatch.setattr(ollama_backend, "NativeOllamaInvestigationBackend", FakeBackend)
    FakeBackend.prompts, FakeBackend.digest, FakeBackend.fail_on = [], DIGEST, None
    bundle = Bundle(tmp_path / "organizer")

    def run(name: str, phase_name: str, world: str = "world-2", **extra: Any) -> dict[str, Any]:
        copy = tmp_path / f"{name}-input"
        materialize_source_world_copy(bundle.index_path, bundle.root, world_id=world, output_root=copy)
        out = tmp_path / f"{name}-out"
        out.mkdir()
        spec = {
            "run_id": "r1",
            "worker_id": name,
            "phase": phase_name,
            "input_copy": str(copy),
            "information_cutoff": "2026-02-20T00:00:00+00:00",
            "output_dir": str(out),
            "policy": _policy(),
            **extra,
        }
        (tmp_path / f"{name}.json").write_text(json.dumps(spec), encoding="utf-8")
        code = worker.run_worker(tmp_path / f"{name}.json")
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        result["exit_code"] = code
        result["out"] = out
        return result

    return run


def test_construct_then_maintain_then_answer_with_memory(phase) -> None:
    built = phase("construct", "construct")
    assert built["status"] == "completed", built
    assert built["exit_code"] == 0
    checkpoint = built["out"] / "checkpoint"
    assert {p.name for p in checkpoint.iterdir()} == {"brief.json", "brief.md", "position_history.json"}
    assert not any("Question:" in prompt for prompt in FakeBackend.prompts)

    maintained = phase("maintain", "maintain", prior_checkpoint=str(checkpoint))
    assert maintained["status"] == "completed", maintained
    history = json.loads((maintained["out"] / "checkpoint" / "position_history.json").read_text(encoding="utf-8"))
    assert len(history) == 2
    assert "QUESTIONS YOU ALREADY TAKE A POSITION ON" in FakeBackend.prompts[-1]

    answered = phase(
        "answer", "answer", prior_checkpoint=str(maintained["out"] / "checkpoint"), question="Which version applies?"
    )
    assert answered["status"] == "completed"
    assert answered["memory_truncated"] is True
    assert answered["source_count"] == 2
    prompt = FakeBackend.prompts[-1]
    assert "[memory truncated at the frozen limit]" in prompt
    assert prompt.index("EXPERT MEMORY") < prompt.index("SOURCE PACKET") < prompt.index("Question:")
    assert (answered["out"] / "answer.md").read_text(encoding="utf-8") == "Grounded answer citing [S-abc]."
    calls = [json.loads(line) for line in (answered["out"] / "calls.jsonl").read_text().splitlines()]
    assert calls[0]["options"]["seed"] == 1 and calls[0]["observed_digest"] == DIGEST
    ledger = (Path(__import__("os").environ["DEEPR_COST_DATA_DIR"]) / "cost_ledger.jsonl").read_text()
    assert '"cost_usd": 0.0' in ledger and "r1:answer:1" in ledger


def test_answer_without_memory_has_no_memory_block(phase) -> None:
    answered = phase("static", "answer", question="Which version applies?")
    assert answered["status"] == "completed"
    assert answered["memory_prefix_sha256"] is None
    assert "EXPERT MEMORY" not in FakeBackend.prompts[-1]


def test_construction_refuses_a_question(phase) -> None:
    result = phase("leak", "construct", question="Should not be here")
    assert result["status"] == "failed"
    assert "must not receive a case question" in result["error"]
    assert FakeBackend.prompts == []


def test_digest_drift_fails_the_phase(phase) -> None:
    FakeBackend.digest = "c" * 64
    result = phase("drift", "answer", question="q")
    assert result["status"] == "failed"
    assert "digest" in result["error"]
    call = json.loads((result["out"] / "calls.jsonl").read_text().splitlines()[0])
    assert call["status"] == "failed"


def test_incomplete_study_fails_construction(phase) -> None:
    FakeBackend.fail_on = '"changes"'
    result = phase("partial", "construct")
    assert result["status"] == "failed"
    assert "usable/complete" in result["error"]


def test_environment_guard_refuses_dotenv_and_credentials() -> None:
    base = {"PYTHON_DOTENV_DISABLED": "1", "DEEPR_DATA_DIR": "d", "DEEPR_COST_DATA_DIR": "c"}
    worker.check_worker_environment(base)
    with pytest.raises(RuntimeError, match="PYTHON_DOTENV_DISABLED"):
        worker.check_worker_environment({**base, "PYTHON_DOTENV_DISABLED": "0"})
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        worker.check_worker_environment({**base, "OPENROUTER_API_KEY": "x"})
    with pytest.raises(RuntimeError, match="DEEPR_COST_DATA_DIR"):
        worker.check_worker_environment({"PYTHON_DOTENV_DISABLED": "1", "DEEPR_DATA_DIR": "d"})


def test_unknown_phase_is_a_terminal_failure(phase) -> None:
    result = phase("odd", "judge")
    assert result["status"] == "failed" and result["model_calls"] == 0
