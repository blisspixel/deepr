"""One rehearsal worker phase, in process, against a fake owned-local backend."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deepr.evals import expert_value_rehearsal_worker as worker
from deepr.evals.expert_value_materialize import materialize_source_world_copy
from deepr.evals.rehearsal_identity import execution_identity, identity_sha256
from deepr.experts.investigation import ollama_backend
from tests.unit.test_eval.test_expert_value_sources import Bundle

DIGEST = "b" * 64
ANCHOR = "Synthetic source version 1."


class FakeBackend(ollama_backend.NativeOllamaInvestigationBackend):
    """Answers each prompt kind with the smallest contract-shaped payload."""

    prompts: list[str] = []
    payloads: list[dict[str, Any]] = []
    digest = DIGEST
    fail_on: str | None = None
    answer_text = "Grounded answer citing [S-abc]."
    stop_reason = "stop"

    def __init__(self, **kwargs: Any) -> None:
        async def get_json(url: str, _timeout: float) -> dict[str, Any]:
            if url.endswith("/api/status"):
                return {"cloud": {"disabled": True, "source": "both"}}
            return {
                "models": [
                    {
                        "name": kwargs["model"],
                        "model": kwargs["model"],
                        "size": 1000000,
                        "digest": FakeBackend.digest,
                        "details": {"format": "gguf"},
                    }
                ]
            }

        async def post_json(_url: str, payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
            FakeBackend.payloads.append(payload)
            response = await self._respond(SimpleNamespace(messages=payload["messages"]))
            return {
                **response.raw_response,
                "message": {"content": response.message.content},
                "done_reason": response.stop_reason,
            }

        super().__init__(**kwargs, get_json=get_json, post_json=post_json)

    async def _respond(self, request: Any) -> Any:
        prompt = request.messages[0]["content"]
        FakeBackend.prompts.append(prompt)
        self.last_attested_digest = FakeBackend.digest
        if FakeBackend.fail_on and FakeBackend.fail_on in prompt:
            raise RuntimeError("fake local failure")
        if "Question:" in prompt:
            text = FakeBackend.answer_text
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
            stop_reason=FakeBackend.stop_reason,
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
    FakeBackend.payloads = []
    FakeBackend.answer_text, FakeBackend.stop_reason = "Grounded answer citing [S-abc].", "stop"
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
            "execution_identity_sha256": identity_sha256(execution_identity()),
            **extra,
        }
        (tmp_path / f"{name}.json").write_text(json.dumps(spec), encoding="utf-8")
        code = worker.run_worker(tmp_path / f"{name}.json")
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        result["exit_code"] = code
        result["out"] = out
        return result

    return run


@pytest.mark.parametrize("pin", [None, "0" * 64])
def test_worker_identity_refuses_before_backend_or_ledger(phase, pin: str | None) -> None:
    result = phase("wrong-identity", "answer", question="Which version applies?", execution_identity_sha256=pin)
    assert result["status"] == "failed" and result["error_type"] == "RehearsalIdentityError"
    assert "execution identity" in result["error"]
    assert result["model_calls"] == 0 and FakeBackend.prompts == []
    assert not (result["out"].parent / "costs/cost_ledger.jsonl").exists()


def test_construct_passes_the_enforced_output_ceiling_to_shared_study(phase, monkeypatch) -> None:
    from deepr.experts import study

    observed_budgets = []
    original = study.run_study

    async def capture(**kwargs):
        observed_budgets.append(kwargs.get("max_output_tokens"))
        return await original(**kwargs)

    monkeypatch.setattr(study, "run_study", capture)
    built = phase("output-budget", "construct")
    assert built["status"] == "completed", built
    assert observed_budgets == [_policy()["max_output_tokens"]]
    calls = [json.loads(line) for line in (built["out"] / "calls.jsonl").read_text().splitlines()]
    assert calls
    assert all(call["options"]["max_tokens"] == observed_budgets[0] for call in calls)


def test_construct_then_maintain_then_answer_with_memory(phase) -> None:
    built = phase("construct", "construct")
    assert built["status"] == "completed", built
    assert built["exit_code"] == 0
    checkpoint = built["out"] / "checkpoint"
    assert {p.name for p in checkpoint.iterdir()} == {"brief.json", "brief.md", "position_history.json"}
    assert not any("Question:" in prompt for prompt in FakeBackend.prompts)
    assert all(payload["format"] == "json" for payload in FakeBackend.payloads)

    maintained = phase("maintain", "maintain", prior_checkpoint=str(checkpoint))
    assert maintained["status"] == "completed", maintained
    history = json.loads((maintained["out"] / "checkpoint" / "position_history.json").read_text(encoding="utf-8"))
    assert len(history) == 2
    assert "QUESTIONS YOU ALREADY TAKE A POSITION ON" in FakeBackend.prompts[-1]
    assert all(payload["format"] == "json" for payload in FakeBackend.payloads)

    answered = phase(
        "answer", "answer", prior_checkpoint=str(maintained["out"] / "checkpoint"), question="Which version applies?"
    )
    assert answered["status"] == "completed"
    assert answered["memory_truncated"] is True
    assert answered["source_count"] == 2
    prompt = FakeBackend.prompts[-1]
    assert "truncated" not in prompt and "rehearsal-expert" not in prompt
    assert not re.search(r"(synopsis|change)-[0-9a-f]{16}", prompt)
    assert prompt.index("PRIOR NOTES") < prompt.index("SOURCE PACKET") < prompt.index("Question:")
    assert answered["question_sha256"] and len(answered["source_digests"]) == 2
    assert (answered["out"] / "answer.md").read_text(encoding="utf-8") == "Grounded answer citing [S-abc]."
    calls = [json.loads(line) for line in (answered["out"] / "calls.jsonl").read_text().splitlines()]
    assert calls[0]["options"]["seed"] == 1 and calls[0]["observed_digest"] == DIGEST
    assert "format" not in FakeBackend.payloads[-1]
    assert "response_format" not in calls[0]["options"]
    ledger = (Path(__import__("os").environ["DEEPR_COST_DATA_DIR"]) / "cost_ledger.jsonl").read_text()
    assert '"cost_usd": 0.0' in ledger and "r1:answer:1" in ledger


def test_answer_without_memory_has_no_memory_block(phase) -> None:
    answered = phase("static", "answer", question="Which version applies?")
    assert answered["status"] == "completed"
    assert answered["memory_prefix_sha256"] is None
    assert "PRIOR NOTES" not in FakeBackend.prompts[-1]


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


def test_instructions_are_identical_with_and_without_memory() -> None:
    sources = [("a" * 64, "Source text.")]
    with_memory = worker.render_answer_prompt("Q?", "2026-01-01", sources, "notes")
    without = worker.render_answer_prompt("Q?", "2026-01-01", sources, None)
    assert with_memory.splitlines()[0] == without.splitlines()[0]
    assert "memory" not in without.lower()


def test_neutral_memory_and_line_boundary_truncation() -> None:
    brief = "\n".join(
        [
            "# rehearsal-expert: brief",
            "- Rests on: A (synopsis-0123456789abcdef); B (change-fedcba9876543210)",
            "last line",
        ]
    )
    neutral = worker.neutral_memory(brief)
    assert neutral.splitlines() == ["# Prior notes: brief", "- Rests on: A; B", "last line"]
    cut, truncated = worker.render_memory_prefix(neutral, 30)
    assert truncated is True and cut == "# Prior notes: brief"
    assert worker.render_memory_prefix("short", 30) == ("short", False)


def test_empty_answer_fails_and_length_stop_is_flagged(phase) -> None:
    FakeBackend.answer_text = "   "
    empty = phase("empty", "answer", question="q")
    assert empty["status"] == "failed" and "empty answer" in empty["error"]
    assert not (empty["out"] / "answer.md").exists()
    FakeBackend.answer_text, FakeBackend.stop_reason = "Partial answer", "length"
    cut = phase("cut", "answer", question="q")
    assert cut["status"] == "completed" and cut["answer_truncated"] is True and cut["stop_reason"] == "length"


def test_length_stopped_memory_cannot_publish_a_checkpoint(phase) -> None:
    FakeBackend.stop_reason = "length"
    built = phase("length-checkpoint", "construct")
    assert built["status"] == "failed", built
    assert not (built["out"] / "checkpoint").exists()
    calls = [json.loads(line) for line in (built["out"] / "calls.jsonl").read_text().splitlines()]
    assert len(calls) == built["model_calls"] == 2
    assert all(call["status"] == "returned" and call["payload_admission"] == "refused_length" for call in calls)
    assert all(call["raw_response"]["prompt_eval_count"] == 10 for call in calls)
    assert all(call["raw_response"]["eval_count"] == 3 for call in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase_name", ["construct", "maintain"])
async def test_memory_length_stop_refuses_valid_json_without_losing_returned_usage(phase, tmp_path, phase_name):
    from deepr.evals.expert_value_rehearsal import _call_usage

    FakeBackend.stop_reason = "length"
    output = tmp_path / "direct-memory"
    output.mkdir()
    dispatcher = worker._Dispatcher(
        {"run_id": "r1", "worker_id": "memory", "phase": phase_name, "policy": {**_policy(), "max_calls_per_phase": 1}},
        output,
    )

    with pytest.raises(RuntimeError, match="memory generation reached its context or output bound"):
        await dispatcher.complete("Read these sources")

    assert dispatcher.count == len(FakeBackend.payloads) == 1
    call = json.loads((output / "calls.jsonl").read_text())
    assert call["status"] == "returned"
    assert call["payload_admission"] == "refused_length"
    assert call["stop_reason"] == "length" and call["observed_digest"] == DIGEST
    assert call["prompt"] == "Read these sources"
    raw = call["raw_response"]
    assert json.loads(raw["message"]["content"])["notes"]
    assert call["response_sha256"] == hashlib.sha256(raw["message"]["content"].encode()).hexdigest()
    assert call["options"]["response_format"] == {"type": "json_object"}
    assert FakeBackend.payloads[0]["format"] == "json"
    usage = _call_usage(output / "calls.jsonl")
    assert usage["calls"] == usage["returned"] == 1
    assert usage["prompt_tokens"] == 10 and usage["output_tokens"] == 3
    assert usage["unknown_usage_calls"] == 0
    ledger = Path(__import__("os").environ["DEEPR_COST_DATA_DIR"]) / "cost_ledger.jsonl"
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(events) == 3
    assert events[-1]["metadata"]["status"] == "returned"
    assert events[-1]["tokens_input"] == 10 and events[-1]["tokens_output"] == 3
    with pytest.raises(RuntimeError, match="phase call limit exhausted"):
        await dispatcher.complete("Do not retry")
    assert len(FakeBackend.payloads) == 1
    assert len((output / "calls.jsonl").read_text().splitlines()) == 1


@pytest.mark.asyncio
async def test_native_study_adapter_refuses_same_valid_json_length_stop(phase):
    from deepr.cli.commands.semantic.study_backend import StudyBackendError, _completion_from_native_ollama

    FakeBackend.stop_reason = "length"
    completion = _completion_from_native_ollama(
        FakeBackend(model="fixture:14b"), "fixture:14b", max_tokens=512, context_tokens=8192
    )
    with pytest.raises(StudyBackendError, match="No complete result was accepted"):
        await completion("Read these sources")
    assert len(FakeBackend.payloads) == 1
    assert FakeBackend.payloads[0]["format"] == "json"


def test_worker_reports_its_module_hashes(phase) -> None:
    from deepr.evals.expert_value_rehearsal import module_hashes

    result = phase("hashes", "answer", question="q")
    assert result["module_sha256"] == module_hashes()
