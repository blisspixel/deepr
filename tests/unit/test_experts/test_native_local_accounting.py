"""Actual native transport accounting with offline daemon responses."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from deepr.experts.chat_backends import ExpertChatRequest
from deepr.experts.investigation.ollama_backend import NativeOllamaInvestigationBackend

DIGEST = "a" * 64


def events() -> list[dict[str, Any]]:
    path = Path(os.environ["DEEPR_COST_DATA_DIR"]) / "cost_ledger.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


async def proof(url: str, _timeout: float) -> dict[str, Any]:
    if url.endswith("/api/status"):
        return {"cloud": {"disabled": True, "source": "both"}}
    return {
        "models": [
            {"name": "fixture", "model": "fixture", "size": 1000000, "digest": DIGEST, "details": {"format": "gguf"}}
        ]
    }


def request() -> ExpertChatRequest:
    return ExpertChatRequest(
        model="fixture", messages=[{"role": "user", "content": "PRIVATE PROMPT"}], extra={"num_ctx": 4096}
    )


@pytest.mark.asyncio
async def test_native_completion_has_durable_dispatch_and_terminal_receipts() -> None:
    async def post(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        recorded = events()
        assert [event["metadata"]["status"] for event in recorded] == ["requested", "dispatching"]
        assert recorded[-1]["metadata"]["model_digest"] == DIGEST
        return {"message": {"content": "PRIVATE ANSWER"}, "prompt_eval_count": 7, "eval_count": 3}

    backend = NativeOllamaInvestigationBackend(model="fixture", get_json=proof, post_json=post)
    result = await backend.complete(request())
    assert result.text == "PRIVATE ANSWER"
    recorded = events()
    assert [event["metadata"]["status"] for event in recorded] == ["requested", "dispatching", "returned"]
    assert len({event["metadata"]["attempt_id"] for event in recorded}) == 1
    assert all(event["cost_usd"] == 0 for event in recorded)
    assert sum(event["tokens_input"] for event in recorded) == 7
    assert sum(event["tokens_output"] for event in recorded) == 3
    assert "PRIVATE" not in json.dumps(recorded)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["proof", "options", "transport", "message", "tokens", "cancel"])
async def test_failed_native_attempts_retain_terminal_status_without_content(failure: str) -> None:
    import asyncio

    async def get(url: str, timeout: float) -> dict[str, Any]:
        if failure == "proof":
            return {"cloud": {"disabled": False}}
        return await proof(url, timeout)

    async def post(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        if failure == "transport":
            raise OSError("PRIVATE ERROR")
        if failure == "cancel":
            raise asyncio.CancelledError("PRIVATE ERROR")
        if failure == "message":
            return {}
        return {"message": {"content": "PRIVATE ANSWER"}, "eval_count": "PRIVATE BAD TOKEN"}

    backend = NativeOllamaInvestigationBackend(model="fixture", get_json=get, post_json=post)
    req = request()
    if failure == "options":
        req.extra["unrecognized"] = "PRIVATE OPTION"
    with pytest.raises(BaseException):
        await backend.complete(req)
    recorded = events()
    started = failure not in {"proof", "options"}
    assert len(recorded) == (3 if started else 2)
    assert recorded[-1]["metadata"]["status"] == (
        "cancelled" if failure == "cancel" else "failed" if started else "refused"
    )
    assert recorded[-1]["metadata"]["transport_may_have_started"] is started
    assert recorded[-1]["metadata"]["error_type"]
    assert "PRIVATE" not in json.dumps(recorded)
    assert all(event["cost_usd"] == 0 for event in recorded)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["requested", "dispatching", "terminal"])
async def test_persistence_failure_cannot_report_success_or_dispatch_without_marker(monkeypatch, phase: str) -> None:
    from deepr.observability.cost_ledger import CostLedger
    from deepr.observability.local_attempts import LocalAttemptAccountingError

    original = CostLedger.record_event
    calls = []

    def record(self, **kwargs):
        assert kwargs["require_fsync"] is True and kwargs["lock_timeout_seconds"] == 5.0
        if kwargs["operation"] == f"native_local_{phase}":
            raise OSError("PRIVATE FILE PATH")
        return original(self, **kwargs)

    monkeypatch.setattr(CostLedger, "record_event", record)

    async def get(url: str, timeout: float) -> dict[str, Any]:
        calls.append("get")
        return await proof(url, timeout)

    async def post(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        calls.append("post")
        return {"message": {"content": "PRIVATE ANSWER"}}

    backend = NativeOllamaInvestigationBackend(model="fixture", get_json=get, post_json=post)
    with pytest.raises(LocalAttemptAccountingError) as caught:
        await backend.complete(request())
    assert "PRIVATE" not in str(caught.value)
    assert calls.count("post") == (1 if phase == "terminal" else 0)
    assert calls.count("get") == (0 if phase == "requested" else 2)
    if phase == "terminal":
        assert [event["metadata"]["status"] for event in events()] == ["requested", "dispatching"]


@pytest.mark.asyncio
async def test_preflight_is_read_only_and_refusal_cannot_reuse_an_old_digest() -> None:
    good = True

    async def get(url: str, timeout: float) -> dict[str, Any]:
        return await proof(url, timeout) if good else {}

    async def post(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        return {"message": {"content": "ok"}}

    backend = NativeOllamaInvestigationBackend(model="fixture", get_json=get, post_json=post)
    await backend.preflight()
    assert events() == []
    await backend.complete(request(), correlation_id="same-call")
    await backend.complete(request(), correlation_id="same-call")
    assert len({event["metadata"]["attempt_id"] for event in events()}) == 2
    good = False
    with pytest.raises(ValueError):
        await backend.complete(request())
    assert backend.last_attested_digest == ""
    assert events()[-1]["metadata"]["model_digest"] == ""


@pytest.mark.asyncio
async def test_cancellation_during_proof_never_marks_transport_started() -> None:
    import asyncio

    async def get(_url: str, _timeout: float) -> dict[str, Any]:
        raise asyncio.CancelledError()

    backend = NativeOllamaInvestigationBackend(model="fixture", get_json=get)
    with pytest.raises(asyncio.CancelledError):
        await backend.complete(request())
    assert [event["metadata"]["status"] for event in events()] == ["requested", "cancelled"]
    assert events()[-1]["metadata"]["transport_may_have_started"] is False


@pytest.mark.asyncio
async def test_native_worker_events_mirror_idempotently_without_extra_attempts(tmp_path, monkeypatch) -> None:
    from deepr.evals.expert_value_rehearsal import RehearsalRun
    from deepr.observability.cost_ledger import CostLedger

    worker_dir = tmp_path / "worker"
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(worker_dir / "costs"))

    async def post(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        return {"message": {"content": "PRIVATE ANSWER"}, "prompt_eval_count": 7, "eval_count": 3}

    backend = NativeOllamaInvestigationBackend(model="fixture", get_json=proof, post_json=post)
    await backend.complete(request(), correlation_id="worker:answer:1")
    original = events()
    assert len(original) == 3
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "canonical"))
    run = object.__new__(RehearsalRun)
    assert run._mirror_ledger(worker_dir) == 3
    assert run._mirror_ledger(worker_dir) == 3
    mirrored = [json.loads(line) for line in CostLedger().ledger_path.read_text().splitlines()]
    assert len(mirrored) == 3
    assert [event["metadata"] for event in mirrored] == [event["metadata"] for event in original]
    assert len({event["metadata"]["attempt_id"] for event in mirrored}) == 1
    assert sum(event["tokens_input"] for event in mirrored) == 7
    assert all(event["cost_usd"] == 0 for event in mirrored)
    assert "PRIVATE" not in json.dumps(mirrored)


@pytest.mark.asyncio
async def test_unavailable_ledger_stops_before_proof(monkeypatch) -> None:
    from deepr.observability import local_attempts

    def unavailable(**_kwargs):
        raise OSError("PRIVATE PATH")

    async def never(_url: str, _timeout: float) -> dict[str, Any]:
        raise AssertionError("must not probe")

    monkeypatch.setattr(local_attempts, "CostLedger", unavailable)
    backend = NativeOllamaInvestigationBackend(model="fixture", get_json=never)
    with pytest.raises(local_attempts.LocalAttemptAccountingError, match="no generation was dispatched"):
        await backend.complete(request())
    assert events() == []


def test_attempt_count_preserves_legacy_and_groups_native_lifecycle() -> None:
    from deepr.observability.local_attempts import SCHEMA, count_local_attempts

    records = [
        {"request_id": "legacy", "metadata": {}},
        *[{"metadata": {"schema": SCHEMA, "attempt_id": "one"}} for _ in range(3)],
        {"metadata": {"schema": SCHEMA, "attempt_id": "interrupted"}},
    ]
    assert count_local_attempts(records) == 3
    with pytest.raises(ValueError, match="attempt identity"):
        count_local_attempts([{"metadata": {"schema": SCHEMA}}])
