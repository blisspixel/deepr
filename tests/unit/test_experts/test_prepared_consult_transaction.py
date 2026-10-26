"""Prepared transaction boundaries with fake service dispatch and real audit files."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deepr.experts import consult_traces
from deepr.experts.consult_lifecycle import load_consult_lifecycle_events
from deepr.experts.consult_transaction import (
    ConsultElapsedLimitError,
    ConsultStorageIOError,
    execute_consult_transaction,
    requested_consult_capacity,
)
from deepr.experts.preparation_contracts import CallerScope, PreparationRequest
from deepr.experts.preparation_service import PreparationAdmission, PreparationRefused, PreparedTransaction

SENTINELS = tuple(
    f"PRIVATE_{name}_54179" for name in ("QUESTION", "MODEL", "PERSPECTIVE", "CONTEXT", "SOURCE_ERROR", "ANSWER")
)
REFERENCE = {"owner_sha256": "a" * 64, "operation_id": "op_" + "b" * 32, "packet_sha256": "c" * 64}


@pytest.fixture
def transaction(tmp_path):
    request = PreparationRequest.from_json(
        json.dumps(
            {
                "schema_version": "deepr-python-preparation-request-v1",
                "enabled": True,
                "request_id": "transaction_fixture",
                "environment": {"interpreter_version": "3.12", "platform": "fixture"},
                "packages": [{"name": "fixture", "version": "1.0"}],
            }
        ).encode()
    )
    backend = SimpleNamespace(client=object(), model=SENTINELS[1], provider="local", allow_live_fallback=False)
    return dict(
        question=SENTINELS[0],
        requested_experts=["Fixture Expert"],
        max_experts=1,
        budget=0.0,
        backend_mode="local",
        backend_factory=lambda: backend,
        requested_capacity=requested_consult_capacity(backend_mode="local", provider="local", model=SENTINELS[1]),
        lifecycle_path=tmp_path / "lifecycle.jsonl",
        trace_path=tmp_path / "trace.jsonl",
        preparation=PreparationAdmission(request, CallerScope(namespace_sha256="a" * 64), tmp_path / "private"),
        heartbeat_interval_seconds=0.01,
    )


def payload():
    return {
        "query": SENTINELS[0],
        "perspectives": [
            {
                "expert_name": "Fixture Expert",
                "domain": "fixture",
                "response": SENTINELS[2],
                "confidence": 0.8,
                "cost": 0.0,
                "context": {"source": SENTINELS[3]},
            }
        ],
        "synthesis": SENTINELS[5],
        "synthesis_status": "completed",
        "agreements": [],
        "disagreements": [],
        "requested_budget_usd": 0.0,
        "total_cost": 0.0,
    }


def assert_private(transaction, caplog):
    text = caplog.text + "".join(
        path.read_text() for path in (transaction["lifecycle_path"], transaction["trace_path"]) if path.exists()
    )
    assert all(secret not in text for secret in SENTINELS)
    assert not transaction["preparation"].root.exists()


@pytest.mark.asyncio
async def test_prepared_success_preserves_mandatory_kwargs_and_private_audit(transaction, monkeypatch, caplog):
    prepared = SimpleNamespace(capture=SimpleNamespace(verify_canonical=lambda: None))
    callback = AsyncMock()
    observed = {}

    async def adapter(admission, **kwargs):
        events = load_consult_lifecycle_events(path=transaction["lifecycle_path"])
        assert events[0]["bounds"]["max_dispatches"] == 4
        assert SENTINELS[0] not in json.dumps(events)
        assert kwargs["deadline"] > asyncio.get_running_loop().time()
        await kwargs["on_irreversible_work"]("__preparation_assumptions__")
        return PreparedTransaction(SimpleNamespace(reference=REFERENCE, answer_allowed=True), prepared, callback)

    async def run(*args, **kwargs):
        observed.update(kwargs)
        return payload()

    monkeypatch.setattr("deepr.experts.preparation_service.prepare_for_transaction", adapter)
    result = await execute_consult_transaction(**transaction, run_consult_fn=run)
    assert result["answer"] == SENTINELS[5]
    assert observed["prepared"] is prepared and observed["preparation_delivery_callback"] is callback
    assert REFERENCE.items() <= json.loads(transaction["trace_path"].read_text())["preparation"].items()
    assert_private(transaction, caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["backend", "blocked", "duplicate", "timeout", "cancel", "trace"])
async def test_prepared_failure_paths_do_not_publish_content(transaction, monkeypatch, caplog, mode):
    async def adapter(*args, **kwargs):
        if mode in {"timeout", "cancel"}:
            await kwargs["on_irreversible_work"]("__preparation_assumptions__")
            if mode == "cancel":
                raise asyncio.CancelledError(SENTINELS[4])
            await asyncio.sleep(5)
        return (
            PreparedTransaction(
                SimpleNamespace(
                    reference=REFERENCE, answer_allowed=False, claim=SimpleNamespace(duplicate=mode == "duplicate")
                ),
                None,
                None,
            )
            if mode in {"blocked", "duplicate"}
            else SimpleNamespace(
                reference=REFERENCE,
                consult_kwargs={
                    "prepared": SimpleNamespace(capture=SimpleNamespace(verify_canonical=lambda: None)),
                    "preparation_delivery_callback": AsyncMock(),
                },
            )
        )

    def backend():
        if mode == "backend":
            raise RuntimeError(SENTINELS[4])
        return SimpleNamespace(client=object(), model=SENTINELS[1], provider="local", allow_live_fallback=False)

    async def run(*args, **kwargs):
        assert mode == "trace"
        return payload()

    if mode == "trace":

        def fail(*args, **kwargs):
            raise OSError(SENTINELS[4])

        monkeypatch.setattr(consult_traces, "append_jsonl_durable", fail)
    monkeypatch.setattr("deepr.experts.preparation_service.prepare_for_transaction", adapter)
    transaction["backend_factory"] = backend
    expected = {
        "backend": RuntimeError,
        "blocked": PreparationRefused,
        "duplicate": PreparationRefused,
        "timeout": ConsultElapsedLimitError,
        "cancel": asyncio.CancelledError,
        "trace": ConsultStorageIOError,
    }[mode]
    with pytest.raises(expected):
        await execute_consult_transaction(
            **transaction, run_consult_fn=run, max_elapsed_seconds=0.15 if mode == "timeout" else 5
        )
    assert load_consult_lifecycle_events(path=transaction["lifecycle_path"])[-1]["state"] in {"failed", "cancelled"}
    assert_private(transaction, caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize("updates", [{"backend_mode": "api"}, {"requested_experts": ["a", "b"]}, {"budget": 1.0}])
async def test_invalid_prepared_admission_denied_before_side_effects(transaction, updates):
    factory = AsyncMock(side_effect=AssertionError("factory must not run"))
    transaction.update(updates, backend_factory=factory)
    with pytest.raises(ValueError):
        await execute_consult_transaction(**transaction)
    factory.assert_not_called()
    assert not transaction["lifecycle_path"].exists()


@pytest.mark.asyncio
async def test_late_inventory_drift_refuses_caller_and_keeps_actual_completed_terminal(transaction, monkeypatch):
    from unittest.mock import Mock

    from deepr.experts.preparation_context import CanonicalPreparationDrift

    verify = Mock(side_effect=[None, CanonicalPreparationDrift("Prepared canonical inventory changed")])
    prepared = SimpleNamespace(capture=SimpleNamespace(verify_canonical=verify))

    async def adapter(*args, **kwargs):
        return PreparedTransaction(SimpleNamespace(reference=REFERENCE, answer_allowed=True), prepared, AsyncMock())

    async def run(*args, **kwargs):
        return payload()

    monkeypatch.setattr("deepr.experts.preparation_service.prepare_for_transaction", adapter)
    with pytest.raises(CanonicalPreparationDrift) as caught:
        await execute_consult_transaction(**transaction, run_consult_fn=run)
    assert verify.call_count == 2
    events = load_consult_lifecycle_events(path=transaction["lifecycle_path"])
    assert events[-1]["state"] == "completed"
    assert sum(event["state"] == "completed" for event in events) == 1
    assert caught.value.consult_lifecycle_terminal == "completed"
    assert caught.value.canonical_inventory_status == "drift_observed_after_terminal"
    assert caught.value.preparation_reference == REFERENCE
    assert SENTINELS[0] not in str(caught.value.preparation_reference)


@pytest.mark.asyncio
async def test_default_transaction_kwargs_do_not_gain_preparation(transaction):
    transaction.pop("preparation")

    async def run(*args, **kwargs):
        assert "prepared" not in kwargs and "preparation_delivery_callback" not in kwargs
        return payload()

    await execute_consult_transaction(**transaction, run_consult_fn=run)
