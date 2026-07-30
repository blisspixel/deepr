"""Structural and fake-client tests for the eval-only local consult graph."""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from deepr.evals.consult_graph import (
    _execute_structured_consult_brief,
    _LocalTransportError,
    _OwnedOllamaConsultTransport,
    _record_local_dispatch,
    _record_local_run_terminal,
    run_local_structured_consult_graph,
    write_structured_consult_run,
)
from deepr.evals.consult_graph_contract import (
    StructuredConsultContractError,
    build_structured_consult_brief,
    default_structured_consult_limits,
    position_model_output_schema,
    stable_json_hash,
    validate_structured_consult_brief,
)
from deepr.evals.consult_graph_transport import LocalTransportResponse as _LocalTransportResponse


def _perspectives(count: int = 2) -> list[dict[str, object]]:
    return [
        {
            "expert_name": f"Expert {index}",
            "domain": f"domain {index}",
            "response": f"Stored belief packet {index}",
            "context": {"source": "belief_store", "belief_ids": [f"belief-{index}"]},
        }
        for index in range(1, count + 1)
    ]


def _provenance(model: str = "fixture-local-model") -> dict[str, object]:
    evidence: dict[str, object] = {
        "attestation_kind": "ollama-owned-local-v1",
        "cloud_disabled": True,
        "cloud_status_source": "config",
        "model": model,
        "digest": "a" * 64,
        "size_bytes": 1_000_000,
        "format": "gguf",
        "observed_at": "2026-07-29T12:00:00+00:00",
    }
    evidence["attestation_hash"] = stable_json_hash(evidence)
    return evidence


def _inventory_entry(name: str = "fixture-local-model") -> dict[str, object]:
    return {
        "name": name,
        "model": name,
        "modified_at": "2026-07-29T12:00:00+00:00",
        "size": 1_000_000,
        "digest": "a" * 64,
        "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "fixture",
            "families": ["fixture"],
            "parameter_size": "1B",
            "quantization_level": "Q4_K_M",
        },
    }


@pytest.fixture(autouse=True)
def _isolate_dispatch_ledger(monkeypatch) -> None:
    monkeypatch.setattr("deepr.evals.consult_graph._record_local_dispatch", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("deepr.evals.consult_graph._record_local_run_terminal", lambda *_args, **_kwargs: None)


def _position_json(*, answer: str = "Test the deterministic gate first.") -> str:
    return json.dumps(
        {
            "answer": answer,
            "abstained": False,
            "evidence_claims": [{"claim": "The packet identifies a bounded gate.", "source_refs": ["belief-1"]}],
            "assumptions": ["The packet is current enough for this eval."],
            "unknowns": ["No outcome data was supplied."],
            "uncertainty": "The semantic quality has not been reviewed.",
            "alternative": "Test recovery before admission.",
            "disconfirming_test": "A failing recovery replay would change this recommendation.",
            "decision_implications": ["Keep the feature eval-only."],
        }
    )


def _synthesis_json() -> str:
    return json.dumps(
        {
            "answer": "Test admission and recovery under the same frozen envelope.",
            "agreements": ["The graph must remain bounded."],
            "disagreements": ["Which control should be tested first."],
            "uncertainty": "No human semantic review has occurred.",
            "next_tests": ["Run the held-out matched-resource comparison."],
        }
    )


class FakeCompletions:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []
        self.active = 0
        self.peak = 0

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        index = len(self.calls) - 1
        response = self.responses[index]
        delay = 0.0
        if isinstance(response, tuple):
            delay, response = response
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if delay:
                await asyncio.sleep(delay)
            if isinstance(response, BaseException):
                raise response
            return _LocalTransportResponse(
                content=response,
                request_id=f"local-{index}",
                stop_reason="stop",
                reported_input_tokens=100 + index,
                reported_output_tokens=20 + index,
            )
        finally:
            self.active -= 1


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.completions = FakeCompletions(responses)

    async def complete(self, **kwargs):
        return await self.completions.create(**kwargs)

    async def close(self) -> None:
        return None


async def _execute_fake(
    client: FakeClient,
    *,
    count: int = 2,
    limits=None,
) -> dict[str, object]:
    brief = build_structured_consult_brief(
        question="Which reliability control should be tested first?",
        perspectives=_perspectives(count),
        model="fixture-local-model",
        model_provenance=_provenance(),
        owned_endpoint="http://127.0.0.1:11434",
        limits=limits,
    )
    return await _execute_structured_consult_brief(brief, transport=client)


def _brief(count: int = 2, **limit_kwargs) -> dict[str, object]:
    limits = default_structured_consult_limits(count)
    if limit_kwargs:
        limits = replace(limits, **limit_kwargs)
    return build_structured_consult_brief(
        question="Which reliability control should be tested first?",
        perspectives=_perspectives(count),
        model="fixture-local-model",
        model_provenance=_provenance(),
        owned_endpoint="http://127.0.0.1:11434",
        limits=limits,
    )


def _schema(name: str) -> dict[str, object]:
    root = Path(__file__).resolve().parents[3]
    return json.loads((root / "docs" / "schemas" / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_native_transport_ignores_ambient_credentials_and_records_local_proof(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "paid-secret")
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "Authorization: Bearer paid-secret")
    monkeypatch.setenv("OPENAI_ORG_ID", "paid-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "paid-project")
    monkeypatch.setenv("HTTP_PROXY", "http://metered.example:8080")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True, "source": "config"}})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [_inventory_entry()]})
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": _position_json()},
                "done_reason": "stop",
                "prompt_eval_count": 101,
                "eval_count": 22,
            },
            headers={"x-request-id": "local-request"},
        )

    transport = _OwnedOllamaConsultTransport(
        "http://127.0.0.1:11434",
        timeout=1.0,
        http_transport=httpx.MockTransport(handler),
    )
    try:
        model, evidence = await transport.attest_model("fixture-local-model")
        response = await transport.complete(
            model=model,
            messages=[{"role": "user", "content": "bounded"}],
            max_tokens=64,
            output_schema=position_model_output_schema(),
        )
    finally:
        await transport.close()

    assert [request.url.path for request in requests] == ["/api/status", "/api/tags", "/api/chat"]
    assert all(request.url.host == "127.0.0.1" for request in requests)
    assert all("authorization" not in request.headers for request in requests)
    assert all(request.headers["user-agent"] == "deepr-local-consult/1" for request in requests)
    assert evidence["cloud_disabled"] is True
    assert evidence["cloud_status_source"] == "config"
    assert evidence["digest"] == "a" * 64
    assert response.request_id == "local-request"
    assert response.reported_input_tokens == 101
    assert response.reported_output_tokens == 22
    payload = json.loads(requests[-1].content)
    assert payload["keep_alive"] == "5m"
    assert payload["options"]["num_predict"] == 64
    assert payload["format"] == position_model_output_schema()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        {},
        {"cloud": {"disabled": False, "source": "config"}},
        {"cloud": {"disabled": True, "source": "runtime"}},
    ],
)
async def test_native_transport_requires_stable_cloud_disable(status: dict[str, object]) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=status)

    transport = _OwnedOllamaConsultTransport(
        "http://127.0.0.1:11434",
        timeout=1.0,
        http_transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(StructuredConsultContractError):
            await transport.attest_model("fixture-local-model")
    finally:
        await transport.close()
    assert [request.url.path for request in requests] == ["/api/status"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"name": "fixture:cloud", "model": "fixture:cloud"}),
        lambda value: value.__setitem__("size", 0),
        lambda value: value.__setitem__("digest", "unknown"),
        lambda value: value["details"].__setitem__("format", "remote"),
        lambda value: value.__setitem__("remote", {"provider": "metered"}),
    ],
)
async def test_native_transport_rejects_unmaterialized_inventory(mutate) -> None:
    entry = _inventory_entry()
    mutate(entry)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True, "source": "config"}})
        return httpx.Response(200, json={"models": [entry]})

    transport = _OwnedOllamaConsultTransport(
        "http://127.0.0.1:11434",
        timeout=1.0,
        http_transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(StructuredConsultContractError) as caught:
            await transport.attest_model(str(entry["name"]))
    finally:
        await transport.close()
    assert caught.value.code == "LOCAL_MODEL_PROVENANCE"


@pytest.mark.asyncio
async def test_native_transport_default_selection_skips_cloud_inventory() -> None:
    cloud = _inventory_entry("fixture:cloud")
    local = _inventory_entry("fixture-local-model")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True, "source": "config"}})
        return httpx.Response(200, json={"models": [cloud, local]})

    transport = _OwnedOllamaConsultTransport(
        "http://127.0.0.1:11434",
        timeout=1.0,
        http_transport=httpx.MockTransport(handler),
    )
    try:
        model, _evidence = await transport.attest_model(None)
    finally:
        await transport.close()
    assert model == "fixture-local-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [302, 500])
async def test_native_transport_never_follows_preflight_redirects(status_code: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, headers={"location": "https://metered.example/v1"})

    transport = _OwnedOllamaConsultTransport(
        "http://127.0.0.1:11434",
        timeout=1.0,
        http_transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(StructuredConsultContractError):
            await transport.attest_model("fixture-local-model")
    finally:
        await transport.close()
    assert len(requests) == 1
    assert requests[0].url.host == "127.0.0.1"


@pytest.mark.asyncio
async def test_native_transport_http_failure_is_one_attempt_and_keeps_request_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True, "source": "config"}})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [_inventory_entry()]})
        return httpx.Response(500, headers={"x-request-id": "failed-local-request"})

    transport = _OwnedOllamaConsultTransport(
        "http://127.0.0.1:11434",
        timeout=1.0,
        http_transport=httpx.MockTransport(handler),
    )
    try:
        model, _evidence = await transport.attest_model("fixture-local-model")
        with pytest.raises(_LocalTransportError) as caught:
            await transport.complete(
                model=model,
                messages=[{"role": "user", "content": "bounded"}],
                max_tokens=64,
                output_schema=position_model_output_schema(),
            )
    finally:
        await transport.close()
    assert caught.value.request_id == "failed-local-request"
    assert [request.url.path for request in requests].count("/api/chat") == 1


@pytest.mark.asyncio
async def test_native_transport_refuses_model_drift_after_attestation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True, "source": "config"}})
        return httpx.Response(200, json={"models": [_inventory_entry()]})

    transport = _OwnedOllamaConsultTransport(
        "http://127.0.0.1:11434",
        timeout=1.0,
        http_transport=httpx.MockTransport(handler),
    )
    try:
        await transport.attest_model("fixture-local-model")
        with pytest.raises(StructuredConsultContractError) as caught:
            await transport.complete(
                model="different-model",
                messages=[{"role": "user", "content": "bounded"}],
                max_tokens=64,
                output_schema=position_model_output_schema(),
            )
    finally:
        await transport.close()
    assert caught.value.code == "LOCAL_MODEL_PROVENANCE"
    assert all(request.url.path != "/api/chat" for request in requests)


def test_public_structured_runner_has_no_transport_injection() -> None:
    assert "client" not in inspect.signature(run_local_structured_consult_graph).parameters
    assert "transport" not in inspect.signature(run_local_structured_consult_graph).parameters


@pytest.mark.asyncio
async def test_whole_run_ceiling_includes_snapshot_loading(monkeypatch) -> None:
    async def slow_loader(**_kwargs):
        await asyncio.sleep(1.0)
        return _perspectives(1)

    monkeypatch.setattr("deepr.evals.consult_graph._load_perspectives", slow_loader)
    started = asyncio.get_running_loop().time()
    with pytest.raises(StructuredConsultContractError) as caught:
        await run_local_structured_consult_graph(
            question="q",
            model="fixture-local-model",
            max_elapsed_seconds=0.01,
        )
    assert caught.value.code == "RUN_PREFLIGHT_TIMEOUT"
    assert asyncio.get_running_loop().time() - started < 0.2


@pytest.mark.asyncio
async def test_whole_run_ceiling_includes_capacity_attestation(monkeypatch) -> None:
    class SlowTransport:
        complete_calls = 0

        def __init__(self, _endpoint: str, *, timeout: float) -> None:
            self.timeout = timeout

        async def attest_model(self, _model: str | None):
            await asyncio.sleep(1.0)
            return "fixture-local-model", _provenance()

        async def complete(self, **_kwargs):
            self.complete_calls += 1

        async def close(self) -> None:
            return None

    transport = SlowTransport("http://127.0.0.1:11434", timeout=1.0)
    monkeypatch.setattr(
        "deepr.evals.consult_graph._OwnedOllamaConsultTransport",
        lambda _endpoint, timeout: transport,
    )
    started = asyncio.get_running_loop().time()
    with pytest.raises(StructuredConsultContractError) as caught:
        await run_local_structured_consult_graph(
            question="q",
            perspectives=_perspectives(1),
            model="fixture-local-model",
            max_elapsed_seconds=0.01,
        )
    assert caught.value.code == "RUN_PREFLIGHT_TIMEOUT"
    assert transport.complete_calls == 0
    assert asyncio.get_running_loop().time() - started < 0.2


@pytest.mark.asyncio
async def test_execution_receives_only_remaining_whole_run_budget(monkeypatch) -> None:
    captured: dict[str, float] = {}

    class DelayedTransport:
        def __init__(self, _endpoint: str, *, timeout: float) -> None:
            self.timeout = timeout

        async def attest_model(self, _model: str | None):
            await asyncio.sleep(0.02)
            return "fixture-local-model", _provenance()

        async def close(self) -> None:
            return None

    async def fake_execute(_brief, **kwargs):
        captured["execution_timeout"] = kwargs["execution_timeout"]
        return {"status": "completed"}

    monkeypatch.setattr("deepr.evals.consult_graph._OwnedOllamaConsultTransport", DelayedTransport)
    monkeypatch.setattr("deepr.evals.consult_graph._execute_structured_consult_brief", fake_execute)

    result = await run_local_structured_consult_graph(
        question="q",
        perspectives=_perspectives(1),
        model="fixture-local-model",
        max_elapsed_seconds=0.2,
    )

    assert result == {"status": "completed"}
    assert 0.0 < captured["execution_timeout"] < 0.19


@pytest.mark.asyncio
async def test_empty_response_retains_dispatch_and_reserved_usage() -> None:
    client = FakeClient([None])

    run = await _execute_fake(client, count=1)

    node = run["nodes"][0]
    assert node["status"] == "failed"
    assert node["usage"]["dispatched"] is True
    assert node["usage"]["transport_attempts"] == 1
    assert node["usage"]["input_tokens_reserved"] > 0
    assert node["usage"]["output_tokens_reserved"] == 700
    assert node["usage"]["request_id"] == "local-0"
    assert run["usage"]["model_calls"] == 1
    assert run["usage"]["transport_attempts"] == 1


def test_dispatch_marker_is_durable_content_free_and_idempotent(monkeypatch, tmp_path: Path) -> None:
    from deepr.observability import cost_ledger as cost_ledger_module

    ledger = cost_ledger_module.CostLedger(ledger_path=tmp_path / "ledger.jsonl")
    monkeypatch.setattr(cost_ledger_module, "CostLedger", lambda: ledger)
    brief = _brief(1)
    node = brief["nodes"][0]
    usage = {
        "input_tokens_reserved": 100,
        "output_tokens_reserved": 700,
    }

    _record_local_dispatch(brief, node, usage, "run_" + ("1" * 32))
    _record_local_dispatch(brief, node, usage, "run_" + ("1" * 32))

    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["operation"] == "structured_consult_local_dispatch"
    assert event["provider"] == "ollama_local"
    assert event["cost_usd"] == 0.0
    assert event["metadata"]["transport_attempts_ceiling"] == 1
    assert event["metadata"]["usage_ambiguous_until_completion"] is True
    assert "Which reliability" not in lines[0]
    assert "Stored belief" not in lines[0]

    _record_local_dispatch(brief, node, usage, "run_" + ("2" * 32))
    repeated_lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(repeated_lines) == 2
    assert {json.loads(line)["metadata"]["run_id"] for line in repeated_lines} == {
        "run_" + ("1" * 32),
        "run_" + ("2" * 32),
    }


@pytest.mark.asyncio
async def test_cancellation_after_dispatch_leaves_durable_zero_cost_marker(monkeypatch, tmp_path: Path) -> None:
    from deepr.observability import cost_ledger as cost_ledger_module

    ledger = cost_ledger_module.CostLedger(ledger_path=tmp_path / "ledger.jsonl")
    monkeypatch.setattr(cost_ledger_module, "CostLedger", lambda: ledger)
    monkeypatch.setattr("deepr.evals.consult_graph._record_local_dispatch", _record_local_dispatch)
    monkeypatch.setattr("deepr.evals.consult_graph._record_local_run_terminal", _record_local_run_terminal)
    client = FakeClient([(1.0, _position_json())])
    task = asyncio.create_task(_execute_fake(client, count=1))
    for _ in range(100):
        if client.completions.active:
            break
        await asyncio.sleep(0.001)

    task.cancel()
    with pytest.raises(asyncio.CancelledError) as caught:
        await task

    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    events = [json.loads(line) for line in lines]
    dispatch = next(event for event in events if event["operation"] == "structured_consult_local_dispatch")
    terminal = next(event for event in events if event["operation"] == "structured_consult_local_run_terminal")
    assert dispatch["cost_usd"] == 0.0
    assert dispatch["metadata"]["node_id"] == "position_001"
    assert dispatch["metadata"]["usage_ambiguous_until_completion"] is True
    assert terminal["metadata"]["transport_attempts"] == 1
    assert terminal["metadata"]["usage_ambiguous_nodes"] == 1
    partial = caught.value.__dict__["structured_consult_partial_run"]
    assert caught.value.__dict__["structured_consult_terminal_recorded"] is True
    assert partial["status"] == "incomplete"
    assert partial["stop_reason"] == "run_cancelled"
    assert partial["node_counts"] == {
        "expected": 2,
        "terminal": 2,
        "missing": 0,
        "cancelled": 2,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "timed_out": 0,
    }
    assert partial["usage"]["transport_attempts"] == 1
    assert len(client.completions.calls) == 1


@pytest.mark.asyncio
async def test_cancellation_waits_for_blocked_marker_before_terminal_accounting(monkeypatch, tmp_path: Path) -> None:
    from deepr.observability import cost_ledger as cost_ledger_module

    ledger_path = tmp_path / "ledger.jsonl"
    ledger = cost_ledger_module.CostLedger(ledger_path=ledger_path)
    monkeypatch.setattr(cost_ledger_module, "CostLedger", lambda: ledger)
    marker_started = threading.Event()
    marker_release = threading.Event()

    def blocking_dispatch(*args, **kwargs) -> None:
        marker_started.set()
        if not marker_release.wait(timeout=5):
            raise AssertionError("dispatch marker was not released")
        _record_local_dispatch(*args, **kwargs)

    monkeypatch.setattr("deepr.evals.consult_graph._record_local_dispatch", blocking_dispatch)
    monkeypatch.setattr("deepr.evals.consult_graph._record_local_run_terminal", _record_local_run_terminal)
    client = FakeClient([_position_json(), _synthesis_json()])
    task = asyncio.create_task(_execute_fake(client, count=1))
    try:
        for _ in range(1_000):
            if marker_started.is_set():
                break
            await asyncio.sleep(0.001)
        assert marker_started.is_set()

        task.cancel()
        await asyncio.sleep(0.01)

        assert not task.done()
        assert client.completions.calls == []
        assert not ledger_path.exists()
    finally:
        marker_release.set()

    with pytest.raises(asyncio.CancelledError) as caught:
        await task

    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert [event["operation"] for event in events] == [
        "structured_consult_local_dispatch",
        "structured_consult_local_run_terminal",
    ]
    assert events[1]["metadata"]["transport_attempts"] == 0
    assert client.completions.calls == []
    partial = caught.value.__dict__["structured_consult_partial_run"]
    assert partial["usage"]["transport_attempts"] == 0


@pytest.mark.asyncio
async def test_same_immutable_brief_uses_independent_run_ids_and_idempotency_keys(monkeypatch, tmp_path: Path) -> None:
    from deepr.observability import cost_ledger as cost_ledger_module

    ledger_path = tmp_path / "ledger.jsonl"
    ledger = cost_ledger_module.CostLedger(ledger_path=ledger_path)
    monkeypatch.setattr(cost_ledger_module, "CostLedger", lambda: ledger)
    monkeypatch.setattr("deepr.evals.consult_graph._record_local_dispatch", _record_local_dispatch)
    monkeypatch.setattr("deepr.evals.consult_graph._record_local_run_terminal", _record_local_run_terminal)
    brief = _brief(1)

    first = await _execute_structured_consult_brief(
        brief,
        transport=FakeClient([_position_json(), _synthesis_json()]),
    )
    second = await _execute_structured_consult_brief(
        brief,
        transport=FakeClient([_position_json(), _synthesis_json()]),
    )

    assert first["brief_hash"] == second["brief_hash"] == brief["brief_hash"]
    assert first["run_id"] != second["run_id"]
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 6
    assert {event["task_id"] for event in events} == {first["run_id"], second["run_id"]}
    assert len({event["idempotency_key"] for event in events}) == 6
    for run_id in (first["run_id"], second["run_id"]):
        run_events = [event for event in events if event["task_id"] == run_id]
        assert [event["operation"] for event in run_events] == [
            "structured_consult_local_dispatch",
            "structured_consult_local_dispatch",
            "structured_consult_local_run_terminal",
        ]


def test_brief_is_fixed_local_read_only_graph() -> None:
    brief = _brief()

    validate_structured_consult_brief(brief)
    positions = [node for node in brief["nodes"] if node["node_kind"] == "position"]
    synthesis = next(node for node in brief["nodes"] if node["node_kind"] == "synthesis")

    assert all(node["depends_on"] == [] for node in positions)
    assert set(synthesis["depends_on"]) == {node["node_id"] for node in positions}
    assert brief["capacity"] == {
        "capacity_kind": "owned_hardware",
        "provider": "local",
        "model": "fixture-local-model",
        "model_provenance": _provenance(),
        "endpoint": "http://127.0.0.1:11434",
        "endpoint_class": "literal_loopback",
        "transport": "ollama_native_http",
        "credential_headers": False,
        "trust_env": False,
        "follow_redirects": False,
        "model_keep_alive": "5m",
        "preflight_http_requests": 2,
        "live_metered_fallback": False,
        "plan_quota_fallback": False,
        "sdk_retries": 0,
        "cost_usd": 0.0,
    }
    assert brief["limits"]["max_cost_usd"] == 0.0
    assert brief["limits"]["max_retries"] == 0
    assert brief["authority"]["writes_state"] is False
    Draft202012Validator(_schema("structured-consult-brief-v1.json")).validate(brief)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda value: value["nodes"].__setitem__(1, deepcopy(value["nodes"][0])), "DUPLICATE_NODE"),
        (lambda value: value["nodes"][0].__setitem__("depends_on", ["missing"]), "MISSING_DEPENDENCY"),
        (lambda value: value["nodes"][0].__setitem__("depends_on", ["position_001"]), "SELF_DEPENDENCY"),
        (lambda value: value["nodes"][0].__setitem__("node_kind", "planner"), "NODE_KIND"),
        (lambda value: value["nodes"][0].__setitem__("mutable_resources", ["beliefs.json"]), "MUTABLE_RESOURCE"),
        (lambda value: value["capacity"].__setitem__("provider", "openai"), "LOCAL_AUTHORITY"),
        (lambda value: value["capacity"].__setitem__("cost_usd", 0.01), "LOCAL_AUTHORITY"),
        (lambda value: value["authority"].__setitem__("tools", True), "EXTERNAL_AUTHORITY"),
    ],
)
def test_brief_rejects_contract_drift(mutate, code: str) -> None:
    brief = _brief()
    mutate(brief)

    with pytest.raises(StructuredConsultContractError) as caught:
        validate_structured_consult_brief(brief)

    assert caught.value.code == code


def test_brief_rejects_cycle_before_dispatch() -> None:
    brief = _brief()
    brief["nodes"][0]["depends_on"] = ["synthesis_001"]

    with pytest.raises(StructuredConsultContractError) as caught:
        validate_structured_consult_brief(brief)

    assert caught.value.code == "CYCLE"


def test_brief_rejects_snapshot_and_brief_hash_drift() -> None:
    brief = _brief()
    brief["snapshots"][0]["content"] = "changed"
    with pytest.raises(StructuredConsultContractError) as snapshot_error:
        validate_structured_consult_brief(brief)
    assert snapshot_error.value.code == "SNAPSHOT_HASH"

    brief = _brief()
    brief["brief_hash"] = "0" * 64
    with pytest.raises(StructuredConsultContractError) as brief_error:
        validate_structured_consult_brief(brief)
    assert brief_error.value.code == "BRIEF_HASH"


@pytest.mark.parametrize("count", [0, 11])
def test_brief_rejects_roster_outside_bounds(count: int) -> None:
    with pytest.raises(StructuredConsultContractError):
        build_structured_consult_brief(
            question="q",
            perspectives=_perspectives(count),
            model="local",
            model_provenance=_provenance("local"),
            owned_endpoint="http://127.0.0.1:11434",
        )


def test_brief_rejects_duplicate_expert_identity() -> None:
    perspectives = _perspectives()
    perspectives[1]["expert_name"] = "expert 1"

    with pytest.raises(StructuredConsultContractError) as caught:
        build_structured_consult_brief(
            question="q",
            perspectives=perspectives,
            model="local",
            model_provenance=_provenance("local"),
            owned_endpoint="http://127.0.0.1:11434",
        )

    assert caught.value.code == "DUPLICATE_EXPERT"


@pytest.mark.asyncio
async def test_successful_run_counts_every_node_and_validates_schemas(tmp_path: Path) -> None:
    client = FakeClient([_position_json(answer="Position A"), _position_json(answer="Position B"), _synthesis_json()])

    run = await _execute_fake(client)

    assert run["status"] == "completed"
    assert run["stop_reason"] == "completed"
    assert run["node_counts"] == {
        "expected": 3,
        "terminal": 3,
        "missing": 0,
        "cancelled": 0,
        "completed": 3,
        "failed": 0,
        "skipped": 0,
        "timed_out": 0,
    }
    assert run["usage"]["model_calls"] == 3
    assert run["usage"]["cost_usd"] == 0.0
    assert run["capacity"]["live_metered_fallback"] is False
    assert run["contract"]["runtime_promoted"] is False
    assert len(run["positions"]) == 2
    assert run["synthesis"]["answer"].startswith("Test admission")
    assert [call["max_tokens"] for call in client.completions.calls] == [700, 700, 900]
    assert all(call["model"] == "fixture-local-model" for call in client.completions.calls)
    assert all("tools" not in call and "response_format" not in call for call in client.completions.calls)

    Draft202012Validator(_schema("structured-consult-run-v1.json")).validate(run)
    position_validator = Draft202012Validator(_schema("structured-consult-position-v1.json"))
    for position in run["positions"]:
        position_validator.validate(position)
    Draft202012Validator(_schema("structured-consult-synthesis-v1.json")).validate(run["synthesis"])

    unhashed_run = dict(run)
    run_hash = unhashed_run.pop("run_hash")
    assert run_hash == stable_json_hash(unhashed_run)
    path = write_structured_consult_run(run, output_dir=tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["run_hash"] == run["run_hash"]


@pytest.mark.asyncio
async def test_failed_position_prevents_synthesis_and_exposes_gap() -> None:
    client = FakeClient([_position_json(), "not-json", _synthesis_json()])

    run = await _execute_fake(client)

    assert len(client.completions.calls) == 2
    assert run["status"] == "incomplete"
    assert run["synthesis"] is None
    assert run["node_counts"]["completed"] == 1
    assert run["node_counts"]["failed"] == 1
    assert run["node_counts"]["skipped"] == 1
    assert run["node_counts"]["missing"] == 0
    synthesis = next(node for node in run["nodes"] if node["node_kind"] == "synthesis")
    assert synthesis["error_code"] == "REQUIRE_ALL_NOT_MET"
    assert all("not-json" not in json.dumps(node) for node in run["nodes"])


@pytest.mark.asyncio
async def test_non_loopback_endpoint_fails_before_client_dispatch() -> None:
    client = FakeClient([_position_json(), _synthesis_json()])

    with pytest.raises(ValueError):
        await run_local_structured_consult_graph(
            question="q",
            perspectives=_perspectives(1),
            model="local",
            base_url="https://example.com",
        )

    assert client.completions.calls == []


@pytest.mark.asyncio
async def test_input_envelope_fails_before_client_dispatch() -> None:
    client = FakeClient([_position_json(), _synthesis_json()])
    limits = replace(default_structured_consult_limits(1), max_input_tokens=1)

    with pytest.raises(StructuredConsultContractError) as caught:
        await _execute_fake(client, count=1, limits=limits)

    assert caught.value.code == "INPUT_LIMIT"
    assert client.completions.calls == []


@pytest.mark.asyncio
async def test_per_node_timeout_is_terminal_and_synthesis_is_skipped() -> None:
    client = FakeClient([(0.05, _position_json()), _synthesis_json()])
    limits = replace(
        default_structured_consult_limits(1, max_elapsed_seconds=1.0),
        per_node_elapsed_seconds=0.01,
    )

    run = await _execute_fake(client, count=1, limits=limits)

    assert run["node_counts"]["timed_out"] == 1
    assert run["node_counts"]["skipped"] == 1
    assert run["node_counts"]["terminal"] == run["node_counts"]["expected"]
    assert len(client.completions.calls) == 1


@pytest.mark.asyncio
async def test_parallel_width_stays_within_explicit_concurrency() -> None:
    responses = [
        (0.02, _position_json(answer="A")),
        (0.02, _position_json(answer="B")),
        (0.02, _position_json(answer="C")),
        _synthesis_json(),
    ]
    client = FakeClient(responses)

    limits = default_structured_consult_limits(3, concurrency=2)
    run = await _execute_fake(client, count=3, limits=limits)

    assert run["status"] == "completed"
    assert run["usage"]["peak_concurrency"] == 2
    assert client.completions.peak == 2


@pytest.mark.asyncio
async def test_extra_model_fields_are_rejected_without_leaking_content() -> None:
    payload = json.loads(_position_json())
    payload["chain_of_thought"] = "private"
    client = FakeClient([json.dumps(payload), _synthesis_json()])

    run = await _execute_fake(client, count=1)

    assert run["status"] == "incomplete"
    assert run["nodes"][0]["error_code"] == "POSITION_SCHEMA"
    assert "private" not in json.dumps(run)
    assert len(client.completions.calls) == 1


@pytest.mark.asyncio
async def test_fenced_json_is_accepted_but_no_prose_wrapper_is_accepted() -> None:
    fenced = f"```json\n{_position_json()}\n```"
    client = FakeClient([fenced, _synthesis_json()])
    completed = await _execute_fake(client, count=1)
    assert completed["status"] == "completed"

    client = FakeClient([f"Result: {_position_json()}", _synthesis_json()])
    rejected = await _execute_fake(client, count=1)
    assert rejected["nodes"][0]["error_code"] == "INVALID_MODEL_JSON"


@pytest.mark.asyncio
async def test_missing_or_ambiguous_roster_fails_before_dispatch() -> None:
    client = FakeClient([_position_json(), _synthesis_json()])
    with pytest.raises(StructuredConsultContractError) as empty:
        await run_local_structured_consult_graph(
            question="q",
            perspectives=[],
            model="local",
            base_url="http://127.0.0.1:11434",
        )
    assert empty.value.code == "EMPTY_ROSTER"

    with pytest.raises(StructuredConsultContractError) as ambiguous:
        await run_local_structured_consult_graph(
            question="q",
            experts=["Expert 1"],
            perspectives=_perspectives(1),
            model="local",
            base_url="http://127.0.0.1:11434",
        )
    assert ambiguous.value.code == "AMBIGUOUS_ROSTER"
    assert client.completions.calls == []


@pytest.mark.asyncio
async def test_execute_revalidates_tampered_brief_before_dispatch() -> None:
    brief = _brief(1)
    brief["capacity"]["live_metered_fallback"] = True
    client = FakeClient([_position_json(), _synthesis_json()])

    with pytest.raises(StructuredConsultContractError) as caught:
        await _execute_structured_consult_brief(brief, transport=client)

    assert caught.value.code == "LOCAL_AUTHORITY"
    assert client.completions.calls == []
