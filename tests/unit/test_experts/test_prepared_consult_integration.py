"""Shared prepared CLI/MCP pipeline with synthetic transport I/O only."""

import asyncio
import json
import re
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_consult import expert_consult
from deepr.experts import preparation_service
from deepr.experts.preparation_contracts import PreparationPacket, canonical_bytes, sha256
from deepr.experts.preparation_store import PreparationStore
from deepr.mcp.consult_tool import consult_experts_tool
from deepr.mcp.request_context import MCPRequestIdentity, bind_mcp_request_identity, reset_mcp_request_identity

from .test_preparation_context import captured as captured
from .test_preparation_service import acquisition_fixture, tree
from .test_preparation_service import service_fixture as service_fixture


@pytest.mark.parametrize("drift", [False, True])
def test_cli_and_trusted_mcp_share_real_preparation_and_private_delivery(service_fixture, monkeypatch, tmp_path, drift):
    common, replies, _, ledger, root = service_fixture
    question = common["question"]
    before = tree(root)
    payloads = []
    operations = []
    operation_calls = [0]
    original_adapter = preparation_service.prepare_for_transaction
    native = common["backend"]

    async def post(url, payload, timeout):
        index = operation_calls[0]
        operation_calls[0] += 1
        payloads.append(payload)
        return {
            "message": {"content": json.dumps(replies[index]) if index < 2 else "Synthetic bounded advice."},
            "done_reason": "stop",
            "prompt_eval_count": 100,
            "eval_count": 30,
        }

    # Exercise the real backend factory and per-dispatch cloud/digest attestation.
    monkeypatch.setattr("deepr.experts.investigation.ollama_backend._get_json", native._get_json)
    monkeypatch.setattr("deepr.experts.investigation.ollama_backend._post_json", post)

    async def select(*args, **kwargs):
        return "fixture:local", "explicit fixture selection"

    monkeypatch.setattr("deepr.experts.consult.resolve_consult_local_model", select)
    monkeypatch.setattr(
        "deepr.experts.profile_store.ExpertStore.load", lambda *args, **kwargs: SimpleNamespace(name="E")
    )
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path / "data"))
    trace = tmp_path / "global-trace.jsonl"
    lifecycle = tmp_path / "global-lifecycle.jsonl"
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(trace))
    monkeypatch.setenv("DEEPR_CONSULT_LIFECYCLE_PATH", str(lifecycle))

    brief_path = root / "hold/current.json"
    brief_bytes = brief_path.read_bytes()

    async def acquired_then_mutated(*args, **kwargs):
        acquired = await acquisition_fixture(*args, **kwargs)
        # This later canonical mutation must never replace the already captured context.
        if drift:
            brief_path.write_text(
                brief_bytes.decode().replace("Unknown outside measured partition.", "POST_CAPTURE_CANONICAL_MUTATION"),
                encoding="utf-8",
            )
        return acquired

    async def adapter(admission, **kwargs):
        operation_calls[0] = 0
        result = await original_adapter(admission, **kwargs, acquirer=acquired_then_mutated)
        operations.append((admission, result))
        return result

    monkeypatch.setattr(preparation_service, "prepare_for_transaction", adapter)
    request = common["request"].model_dump(mode="json")
    request["request_id"] = "combined_cli_request_001"
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    cli = CliRunner().invoke(
        expert_consult, [question, "-e", "E", "--prepare-python", str(path), "--local-model", "fixture:local", "--json"]
    )
    assert cli.exit_code == (1 if drift else 0), cli.output
    assert (b"POST_CAPTURE_CANONICAL_MUTATION" in brief_path.read_bytes()) == drift
    brief_path.write_bytes(brief_bytes)
    cli_result = json.loads(cli.output)
    request["request_id"] = "combined_mcp_request_002"

    async def mcp():
        token = bind_mcp_request_identity(MCPRequestIdentity.local_stdio())
        try:
            return await consult_experts_tool(
                question=question, experts=["E"], preparation=request, local_model="fixture:local"
            )
        finally:
            reset_mcp_request_identity(token)

    mcp_result = asyncio.run(mcp())
    assert (b"POST_CAPTURE_CANONICAL_MUTATION" in brief_path.read_bytes()) == drift
    brief_path.write_bytes(brief_bytes)
    if drift:
        assert cli_result["error"]["code"] == "CONSULT_PREPARATION_FAILED"
        assert mcp_result["error_code"] == "PREPARATION_FAILED"
        assert len(payloads) == 4 and len(operations) == 2
        assert all(payload.get("format") == "json" for payload in payloads)
        events = [
            json.loads(line)
            for file in operations[0][0].root.rglob("*.jsonl")
            for line in file.read_text(encoding="utf-8").splitlines()
        ]
        deliveries = [event for event in events if event.get("kind") == "delivery"]
        assert len(deliveries) == 2
        assert all(event["status"] == "not_delivered" and event["messages"] is None for event in deliveries)
        assert tree(root) == before
        return
    assert mcp_result.get("synthesis_status") == "completed", mcp_result
    assert cli_result["answer"] == mcp_result["answer"] == "Synthetic bounded advice."
    assert len(payloads) == 6 and len(operations) == 2
    assert operations[0][0].owner != operations[1][0].owner
    assert tree(root) == before
    rendered = []
    for index, (admission, transaction) in enumerate(operations):
        prepared = transaction.prepared
        assert prepared is not None
        final = payloads[index * 3 + 2]["messages"]
        final_user = final[-1]["content"]
        delivered = prepared.mandatory_text()
        assert delivered in final_user
        assert "Packet SHA256: " + prepared.frozen.manifest.content_sha256 in final_user
        rendered.append(delivered)
        assert "Release summary fixture reason" in final_user
        assert "Unknown outside measured partition." in final_user
        assert "POST_CAPTURE_CANONICAL_MUTATION" not in final_user
        result = (cli_result, mcp_result)[index]
        binding = result["preparation_delivery"]
        assert binding["messages_sha256"] == sha256(canonical_bytes({"messages": final}))
        assert binding["packet_sha256"] == prepared.frozen.manifest.content_sha256
        assert binding["captured_context_sha256"] == prepared.capture.context_sha256
        assert binding["answer_sha256"] == sha256(b"Synthetic bounded advice.")
        store = PreparationStore(admission.root)
        operation = transaction.outcome.claim.operation_id
        assert store.source_attempt_count(admission.owner, operation) == 2
        packet = PreparationPacket.model_validate_json(prepared.frozen.content)
        assert packet.attempts == 2
        for observation in packet.observations:
            raw = store.read_source(admission.owner, operation, observation.raw_sha256)
            assert sha256(raw) == observation.raw_sha256
            assert (
                sha256(canonical_bytes(json.loads(observation.metadata_projection_json)))
                == observation.metadata_projection_sha256
            )

    # CLI and MCP render through the same PreparedConsultation object: after removing
    # per-operation identities (hashes, operation ids, timestamps) the texts are identical.
    def identity_free(text):
        text = re.sub(r"[0-9a-f]{64}", "<sha256>", text)
        text = re.sub(r"op_[0-9a-f]{32}", "<operation>", text)
        return re.sub(r"\d{4}-\d{2}-\d{2}T[0-9:.+]+", "<time>", text)

    assert identity_free(rendered[0]) == identity_free(rendered[1])
    assert "unreviewed model interpretation, not a source observation" in rendered[0]
    private_events = [
        json.loads(line)
        for file in operations[0][0].root.rglob("*.jsonl")
        for line in file.read_text(encoding="utf-8").splitlines()
    ]
    deliveries = [event for event in private_events if event.get("kind") == "delivery"]
    unique = {(event["packet_sha256"], event["status"]): event for event in deliveries}
    assert len(unique) == 4
    assert all(event["messages"] for event in unique.values())
    assert sum(event["answer"] == "Synthetic bounded advice." for event in unique.values()) == 2
    global_text = trace.read_text() + lifecycle.read_text()
    assert question not in global_text and "Release summary fixture reason" not in global_text
    assert "Synthetic bounded advice." not in global_text
    ledger_events = [json.loads(line) for line in ledger.ledger_path.read_text().splitlines()]
    assert len(ledger_events) == 18
    assert sum(event["operation"] == "native_local_requested" for event in ledger_events) == 6
    assert sum(event.get("kind") == "source_intent" for event in private_events) == 4
    assert sum(event.get("kind") == "source_terminal" for event in private_events) == 4


def test_cli_and_mcp_report_refused_interpretation_reference_without_answer(service_fixture, monkeypatch, tmp_path):
    """A model-cited unknown stored position fails closed with a retained terminal packet."""
    common, replies, _, _, root = service_fixture
    replies[1]["interpretation"]["conflicts"] = [
        {"stored_position_id": "f" * 64, "observation_ids": ["observation_1"], "note": "Model-cited id."}
    ]
    before = tree(root)
    payloads, operations, calls = [], [], [0]
    original_adapter = preparation_service.prepare_for_transaction

    async def post(url, payload, timeout):
        index = calls[0]
        calls[0] += 1
        payloads.append(payload)
        return {
            "message": {"content": json.dumps(replies[index]) if index < 2 else "Must not be dispatched."},
            "done_reason": "stop",
            "prompt_eval_count": 100,
            "eval_count": 30,
        }

    monkeypatch.setattr("deepr.experts.investigation.ollama_backend._get_json", common["backend"]._get_json)
    monkeypatch.setattr("deepr.experts.investigation.ollama_backend._post_json", post)

    async def select(*args, **kwargs):
        return "fixture:local", "explicit fixture selection"

    monkeypatch.setattr("deepr.experts.consult.resolve_consult_local_model", select)
    monkeypatch.setattr(
        "deepr.experts.profile_store.ExpertStore.load", lambda *args, **kwargs: SimpleNamespace(name="E")
    )
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(tmp_path / "trace.jsonl"))
    monkeypatch.setenv("DEEPR_CONSULT_LIFECYCLE_PATH", str(tmp_path / "lifecycle.jsonl"))

    async def adapter(admission, **kwargs):
        calls[0] = 0
        result = await original_adapter(admission, **kwargs, acquirer=acquisition_fixture)
        operations.append((admission, result))
        return result

    monkeypatch.setattr(preparation_service, "prepare_for_transaction", adapter)
    request = common["request"].model_dump(mode="json")
    request["request_id"] = "refused_cli_request_001"
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    cli = CliRunner().invoke(
        expert_consult,
        [common["question"], "-e", "E", "--prepare-python", str(path), "--local-model", "fixture:local", "--json"],
    )
    assert cli.exit_code == 1, cli.output
    assert json.loads(cli.output)["error"]["code"] == "CONSULT_PREPARATION_FAILED"
    request["request_id"] = "refused_mcp_request_002"

    async def mcp():
        token = bind_mcp_request_identity(MCPRequestIdentity.local_stdio())
        try:
            return await consult_experts_tool(
                question=common["question"], experts=["E"], preparation=request, local_model="fixture:local"
            )
        finally:
            reset_mcp_request_identity(token)

    mcp_result = asyncio.run(mcp())
    assert mcp_result["error_code"] == "PREPARATION_FAILED"
    # Two preparation calls per transport; no final synthesis was dispatched.
    assert len(payloads) == 4 and len(operations) == 2
    assert all("Must not be dispatched." not in json.dumps(payload) for payload in payloads)
    for admission, transaction in operations:
        assert transaction.prepared is None and transaction.failure_code == "preparation_failed"
        frozen = PreparationStore(admission.root).load(admission.owner, transaction.outcome.claim.operation_id)
        packet = PreparationPacket.model_validate_json(frozen.content)
        assert packet.stop_reason == "failed" and packet.interpretation.conflicts == ()
        assert "interpretation_invalid_references" in packet.omissions[-1].reason
    assert tree(root) == before
