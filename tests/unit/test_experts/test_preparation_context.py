"""Synthetic captured-context and mandatory preparation delivery regressions."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.briefed_perspective import build_briefed_perspective
from deepr.experts.consult_context import build_consult_context
from deepr.experts.consult_prompt import MAX_SYNTHESIS_PROMPT_CHARS, build_synthesis_packet
from deepr.experts.consult_support import study_fingerprint
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.council import ExpertCouncil, ExpertPerspective
from deepr.experts.preparation_context import (
    PreparedConsultation,
    PreparedDelivery,
    capture_formed_context,
    preparation_delivery,
)
from deepr.experts.preparation_contracts import (
    Assumption,
    CallerScope,
    PreparationEnvelope,
    PreparationPacket,
    PreparationRequest,
    freeze_packet,
    sha256,
)
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


@pytest.fixture
def captured(tmp_path, monkeypatch):
    root = tmp_path / "formed"
    root.mkdir()
    monkeypatch.setattr("deepr.experts.paths.canonical_expert_dir", lambda name: root)
    (root / "profile.json").write_text(json.dumps({"name": "E", "domain": "synthetic"}), encoding="utf-8")
    corpus = CorpusStore("E", storage_dir=root / "corpus")
    entry, _ = corpus.add("Fixture latency is unknown outside the measured partition.", origin_key="fixture:source")
    finding = StudyFinding(
        lens="synopsis",
        axis="interrogation",
        kind="notes",
        title="Fixture latency",
        finding_id="f1",
        grounded_anchor_count=1,
        corpus_shas=[entry.sha256],
        anchors=["latency is unknown"],
    )
    study = StudyResult(
        expert_name="E", outcomes=[LensOutcome(lens="synopsis", axis="interrogation", status="ok", findings=[finding])]
    )
    brief = ExpertBrief(
        expert_name="E",
        orientation="Synthetic fixture scope.",
        positions=[
            Position(
                question="What is fixture latency?",
                stance="Unknown outside measured partition.",
                reasoning="The fixture limits its scope.",
                would_change_my_mind="A matched broader qualification.",
                supported_by=["f1"],
            )
        ],
        study_fingerprint=study_fingerprint(study),
    )
    (root / "hold").mkdir()
    (root / "noticed").mkdir()
    (root / "hold/current.json").write_text(json.dumps(brief.to_dict()), encoding="utf-8")
    (root / "noticed/current.json").write_text(json.dumps(study.to_dict()), encoding="utf-8")
    return capture_formed_context("What is fixture latency?", "E"), root


def prepared_from(capture, *, large=False):
    request = PreparationRequest.from_json(
        json.dumps(
            {
                "schema_version": "deepr-python-preparation-request-v1",
                "enabled": True,
                "request_id": "synthetic_request_001",
                "environment": {"interpreter_version": "3.12", "platform": "fixture"},
                "packages": [{"name": "fixture", "version": "1.0"}],
            }
        ).encode()
    )
    assumptions = ()
    if large:
        assumptions = tuple(
            Assumption(
                assumption_id=f"a{index}",
                coordinate_ids=(request.packages[0].coordinate_id,),
                text="x" * 4000,
                status="unchecked",
                reason="Synthetic context bound.",
            )
            for index in range(6)
        )
    packet = PreparationPacket(
        envelope=PreparationEnvelope(
            operation_id="operation1",
            owner=CallerScope(namespace_sha256="a" * 64),
            request=request,
            question=capture.question,
            expert_revision=capture.expert_revision,
            stored_position_ids=capture.stored_position_ids,
        ),
        assumptions=assumptions,
        stop_reason="offline",
    )
    return PreparedConsultation(capture, freeze_packet(packet))


def test_capture_retains_exact_loaded_bytes_and_no_recapture_after_changes(captured, monkeypatch):
    capture, root = captured
    assert capture.expert_revision == sha256(
        json.dumps({item.label: item.sha256 for item in capture.inputs}, sort_keys=True, separators=(",", ":")).encode()
    )
    before = capture.stored_context_text
    (root / "hold/current.json").write_text("corrupted after capture", encoding="utf-8")
    for path in (root / "corpus/sources").rglob("*.md"):
        path.write_text("different bytes", encoding="utf-8")
    prepared = prepared_from(capture)
    monkeypatch.setattr(
        "deepr.experts.briefed_perspective.load_consult_context",
        lambda *args, **kwargs: pytest.fail("canonical reread"),
    )
    perspective = build_briefed_perspective(capture.question, "E", capture.domain, ExpertPerspective, prepared=prepared)
    assert "outside the measured partition" in perspective.response
    assert capture.stored_context_text == before
    assert perspective.context["finding_routing"] == "lexical"
    assert "no live check" not in perspective.synthesis_blocks[0].text
    restored = build_consult_context(
        expert_name="E", question=capture.question, brief=None, result=None, corpus=None, prepared=prepared
    )
    assert restored.preparation_notice == prepared.notice


def test_capture_hash_tamper_and_wrong_question_are_refused(captured):
    capture, _ = captured
    with pytest.raises(ValueError, match="identity"):
        replace(capture, context_bytes=b"{}")
    with pytest.raises(ValueError, match="identity"):
        build_consult_context(
            expert_name="E", question="different", brief=None, result=None, corpus=None, prepared=prepared_from(capture)
        )


def test_mandatory_whole_packet_survives_zero_eligible_contributors(captured):
    capture, _ = captured
    prepared = prepared_from(capture)
    prompt, manifest = build_synthesis_packet(
        capture.question,
        [ExpertPerspective(expert_name="E", domain="fixture", response="No relevant stored evidence", confidence=0)],
        prepared=prepared,
    )
    assert prepared.frozen.content.decode() in prompt
    assert "Contributors: 0" in prompt
    assert manifest["preparation"]["delivery"] == "included_whole"
    assert len(prompt) <= MAX_SYNTHESIS_PROMPT_CHARS


@pytest.mark.asyncio
async def test_mandatory_overflow_refuses_before_provider_and_records_not_delivered(captured, monkeypatch):
    capture, _ = captured
    prepared = prepared_from(capture, large=True)
    dispatch = AsyncMock(side_effect=AssertionError("oversized mandatory layer must not dispatch"))
    monkeypatch.setattr("deepr.experts.council.dispatch_synthesis", dispatch)
    receipts = []

    async def record(receipt):
        receipts.append(receipt)

    council = ExpertCouncil(
        synthesis_client=_mark_zero_dollar_client(SimpleNamespace(), capacity_source="local"),
        synthesis_provider="local",
        prepared=prepared,
        preparation_delivery_callback=record,
    )
    result = await council._synthesise(capture.question, [], 0)
    dispatch.assert_not_awaited()
    assert result["synthesis_status"] == "failed"
    assert receipts[0]["status"] == "not_delivered"
    assert receipts[0]["messages_sha256"] is None


@pytest.mark.asyncio
async def test_prepared_query_does_not_dispatch_router_or_read_stores(captured, monkeypatch):
    capture, _ = captured
    prepared = prepared_from(capture)
    monkeypatch.setattr(
        "deepr.experts.consult_routing.route_expert_findings", AsyncMock(side_effect=AssertionError("no reroute"))
    )
    council = ExpertCouncil(prepared=prepared)
    monkeypatch.setattr(council, "_load_stored_perspective", lambda *args: pytest.fail("no canonical reread"))
    monkeypatch.setattr(council, "_attach_self_model_context", lambda *args: pytest.fail("no self-model reread"))
    result = await council._query_expert(capture.question, {"name": "E", "domain": capture.domain}, 0, None, None)
    assert result.context["source"] == "brief"


def test_final_receipt_is_non_circular_and_exact_message_bound(captured):
    capture, _ = captured
    prepared = prepared_from(capture)
    before = prepared.frozen.content
    first = preparation_delivery(prepared, "system", "user", "answer", status="completed")
    second = preparation_delivery(prepared, "system", "different", "answer", status="completed")
    assert first["messages_sha256"] != second["messages_sha256"]
    assert first["answer_sha256"] == sha256(b"answer")
    assert first["packet_sha256"] == prepared.frozen.manifest.content_sha256
    assert prepared.frozen.content == before


@pytest.mark.asyncio
async def test_preparation_only_dispatch_binds_exact_messages_before_call_and_answer_after(captured, monkeypatch):
    from deepr.experts.council_synthesis_runtime import SynthesisProviderResponse

    capture, _ = captured
    prepared = prepared_from(capture)
    receipts = []
    sent = []

    async def record(receipt):
        receipts.append(receipt)

    async def dispatch(**kwargs):
        await kwargs["pre_dispatch_callback"]()
        assert len(receipts) == 1 and receipts[0]["status"] == "dispatch_intent"
        sent.append((kwargs["system_prompt"], kwargs["user_prompt"]))
        return SynthesisProviderResponse(
            text="The fixture remains uncertain.",
            usage={"cost": 0},
            provider_request_id="synthetic",
            stop_reason="stop",
        )

    monkeypatch.setattr("deepr.experts.council.dispatch_synthesis", dispatch)
    council = ExpertCouncil(
        synthesis_client=_mark_zero_dollar_client(SimpleNamespace(), capacity_source="local"),
        synthesis_provider="local",
        prepared=prepared,
        preparation_delivery_callback=record,
    )
    result = await council._synthesise(capture.question, [], 0)
    assert result["synthesis_status"] == "completed"
    assert len(sent) == 1 and len(receipts) == 2
    assert prepared.frozen.content.decode() in sent[0][1]
    assert receipts[0]["messages"] == [
        {"role": "system", "content": sent[0][0]},
        {"role": "user", "content": sent[0][1]},
    ]
    assert receipts[1]["answer_sha256"] == sha256(b"The fixture remains uncertain.")
    assert "messages" not in result["preparation_delivery"]
    assert result["context_delivery"]["user_prompt"] == sent[0][1]
    assert result["context_delivery"]["freshness"] != "stored_context_only"


def test_capture_refuses_unformed_or_mismatched_profile(captured):
    capture, root = captured
    (root / "profile.json").write_text(json.dumps({"name": "other"}), encoding="utf-8")
    with pytest.raises(ValueError, match="profile identity"):
        capture_formed_context(capture.question, "E")
    (root / "profile.json").write_text(json.dumps({"name": "E"}), encoding="utf-8")
    (root / "hold/current.json").write_text(json.dumps(ExpertBrief(expert_name="E").to_dict()), encoding="utf-8")
    with pytest.raises(ValueError, match="formed brief"):
        capture_formed_context(capture.question, "E")


def test_question_binding_cannot_be_relabelled_after_capture(captured):
    capture, _ = captured
    with pytest.raises(ValueError, match="binding"):
        replace(capture, question="A different question")


@pytest.mark.asyncio
async def test_prepared_provider_exception_does_not_log_private_exception_text(captured, monkeypatch, caplog):
    capture, _ = captured
    secret = "private synthetic question/source marker"

    async def dispatch(**kwargs):
        await kwargs["pre_dispatch_callback"]()
        raise RuntimeError(secret)

    monkeypatch.setattr("deepr.experts.council.dispatch_synthesis", dispatch)
    council = ExpertCouncil(
        synthesis_client=_mark_zero_dollar_client(SimpleNamespace(), capacity_source="local"),
        synthesis_provider="local",
        prepared=prepared_from(capture),
    )
    result = await council._synthesise(capture.question, [], 0)
    assert result["synthesis_status"] == "failed"
    assert secret not in caplog.text
    assert secret not in result["text"]


def test_capture_reads_each_canonical_input_once(captured, monkeypatch):
    from deepr.experts import preparation_context

    original, _ = captured
    reads = []
    read = preparation_context._read_capture

    def observed(path, root, remaining):
        reads.append(path)
        return read(path, root, remaining)

    monkeypatch.setattr(preparation_context, "_read_capture", observed)
    snapshot = capture_formed_context(original.question, original.expert_name)
    assert len(reads) == len(set(reads)) == len(snapshot.inputs)
    assert snapshot.expert_revision == original.expert_revision


@pytest.mark.parametrize(
    "relative", ["beliefs/events.jsonl", "graph/evidence.json", "hold/history.json", "revisions/new.json"]
)
def test_canonical_inventory_records_absences_and_refuses_new_authority(captured, relative):
    from deepr.experts.preparation_context import CanonicalPreparationDrift

    capture, root = captured
    assert dict(capture.canonical_inventory)["beliefs"] is None
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"fixture":true}', encoding="utf-8")
    with pytest.raises(CanonicalPreparationDrift, match="changed"):
        capture.verify_canonical()


def test_capture_rejects_mismatched_study_binding(captured):
    capture, root = captured
    path = root / "hold/current.json"
    data = json.loads(path.read_bytes())
    data["study_fingerprint"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="matched formed study"):
        capture_formed_context(capture.question, capture.expert_name)


@pytest.mark.asyncio
async def test_drift_after_protected_finalization_refuses_but_retains_exact_answer_receipt(captured):
    from deepr.experts.preparation_context import CanonicalPreparationDrift

    capture, root = captured
    journal = []

    async def record(receipt):
        journal.append(receipt)
        if receipt["status"] == "completed":
            (root / "profile.json").write_text('{"name":"changed"}', encoding="utf-8")

    delivery = PreparedDelivery(prepared_from(capture), record)

    async def core(*args, **kwargs):
        await delivery.before_dispatch("system", "user")
        return {"text": "actual answer", "stop_reason": "stop", "synthesis_status": "completed"}

    with pytest.raises(CanonicalPreparationDrift):
        await delivery.run(core, capture.question, [], 0, None)
    assert journal[-1]["answer"] == "actual answer"
    assert journal[-1]["answer_sha256"] == sha256(b"actual answer")


@pytest.mark.asyncio
async def test_terminal_receipt_write_failure_retains_only_safe_known_answer_binding(captured, monkeypatch):
    from deepr.experts.council_synthesis_runtime import SynthesisProviderResponse

    capture, _ = captured

    async def dispatch(**kwargs):
        await kwargs["pre_dispatch_callback"]()
        return SynthesisProviderResponse(
            text="private synthetic answer", usage={"cost": 0}, provider_request_id="fixture", stop_reason="stop"
        )

    async def record(receipt):
        if receipt["status"] != "dispatch_intent":
            raise OSError("synthetic private store failure")

    monkeypatch.setattr("deepr.experts.council.dispatch_synthesis", dispatch)
    council = ExpertCouncil(
        synthesis_client=_mark_zero_dollar_client(SimpleNamespace(), capacity_source="local"),
        synthesis_provider="local",
        prepared=prepared_from(capture),
        preparation_delivery_callback=record,
    )
    with pytest.raises(OSError) as caught:
        await council._synthesise(capture.question, [], 0)
    binding = caught.value.preparation_delivery
    assert binding["answer_sha256"] == sha256(b"private synthetic answer")
    assert "messages" not in binding and "answer" not in binding


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_failure", [False, True])
async def test_core_failure_persists_terminal_without_replacing_original(captured, callback_failure):
    capture, _ = captured
    journal = []
    original = ValueError("private core failure")

    async def record(receipt):
        if receipt["status"] == "cancelled_or_failed" and callback_failure:
            raise OSError("private storage failure")
        journal.append(receipt)

    delivery = PreparedDelivery(prepared_from(capture), record)

    async def core(*args, **kwargs):
        await delivery.before_dispatch("private system", "private user")
        raise original

    with pytest.raises(ValueError) as caught:
        await delivery.run(core, capture.question, [], 0, None)
    assert caught.value is original
    safe = original.preparation_delivery
    assert safe["answer_sha256"] is None
    assert "messages" not in safe and "answer" not in safe
    assert safe["terminal_persistence"] == ("unsettled" if callback_failure else "recorded")
    if not callback_failure:
        assert journal[-1]["status"] == "cancelled_or_failed"
        assert journal[-1]["messages"][1]["content"] == "private user"
        assert journal[-1]["answer"] is None


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_actual_terminal_journal(captured):
    capture, _ = captured
    dispatched = asyncio.Event()
    writing = asyncio.Event()
    release = asyncio.Event()
    journal = []

    async def record(receipt):
        if receipt["status"] == "cancelled_or_failed":
            writing.set()
            await release.wait()
        journal.append(receipt)

    delivery = PreparedDelivery(prepared_from(capture), record)

    async def core(*args, **kwargs):
        await delivery.before_dispatch("system", "user")
        dispatched.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(delivery.run(core, capture.question, [], 0, None))
    await dispatched.wait()
    task.cancel("original cancellation")
    await writing.wait()
    task.cancel("repeated cancellation")
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError, match="original cancellation") as caught:
        await task
    assert journal[-1]["status"] == "cancelled_or_failed"
    assert journal[-1]["answer_sha256"] is None
    assert caught.value.preparation_delivery["terminal_persistence"] == "recorded"


@pytest.mark.asyncio
async def test_terminal_callback_timeout_is_joined_and_original_failure_preserved(captured, monkeypatch):
    monkeypatch.setattr("deepr.experts.preparation_context._TERMINAL_RECEIPT_SECONDS", 0.01)
    capture, _ = captured
    closed = asyncio.Event()
    original = RuntimeError("core failed")

    async def record(receipt):
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def core(*args, **kwargs):
        raise original

    delivery = PreparedDelivery(prepared_from(capture), record)
    with pytest.raises(RuntimeError) as caught:
        await delivery.run(core, capture.question, [], 0, None)
    assert caught.value is original and closed.is_set()
    assert original.preparation_delivery["terminal_persistence"] == "unsettled"
    assert original.preparation_delivery["terminal_persistence_failure"] == "TimeoutError"
