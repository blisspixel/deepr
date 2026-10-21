"""Regressions for evidence lost between context assembly and synthesis."""

import hashlib
from types import SimpleNamespace

import pytest

from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.chat_backends import ExpertChatResult
from deepr.experts.consult import build_consult_payload
from deepr.experts.consult_context import ConsultContext, render_consult_packet
from deepr.experts.consult_prompt import MAX_SYNTHESIS_PROMPT_CHARS, brief_synthesis_blocks, build_synthesis_prompt
from deepr.experts.consult_support import study_fingerprint, support_for_positions
from deepr.experts.council import ExpertCouncil, ExpertPerspective
from deepr.experts.council_synthesis_runtime import LOCAL_SYNTHESIS_CONTEXT_TOKENS
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


def _native_local(handler):
    class Backend:
        async def complete(self, request):
            return await handler(request)

    return _mark_zero_dollar_client(Backend(), capacity_source="local")


def _perspective():
    finding = StudyFinding(
        lens="mechanism",
        axis="interrogation",
        kind="concepts",
        title="Coordination",
        finding_id="f1",
        grounded_anchor_count=1,
        corpus_shas=["source-sha"],
        anchors=["RETAINED_EVIDENCE: separate operations require coordination."],
    )
    study = StudyResult(
        expert_name="Runtime",
        outcomes=[LensOutcome(lens="mechanism", axis="interrogation", status="ok", findings=[finding])],
    )
    context = ConsultContext(
        expert_name="Runtime",
        orientation="General orientation. " * 100,
        positions=[
            Position(
                question="When is it safe?",
                stance="Only with coordination.",
                reasoning="A compound operation is not one atomic operation.",
                unresolved_dissent="The extension's behavior remains unmeasured.",
                would_change_my_mind="A documented transaction guarantee.",
                supported_by=["f1"],
            )
        ],
        findings=[finding],
        sources=[("source-sha", "reference.example", "RETAINED_EVIDENCE: separate operations require coordination.")],
        finding_sources={
            "f1": ("source-sha", "reference.example", "RETAINED_EVIDENCE: separate operations require coordination.")
        },
    )
    context.support = support_for_positions(
        context.positions,
        brief=ExpertBrief(expert_name="Runtime", study_fingerprint=study_fingerprint(study)),
        result=study,
        passages=context.finding_sources,
    )
    return ExpertPerspective(
        expert_name="Runtime",
        domain="runtime",
        response=render_consult_packet(context),
        synthesis_blocks=brief_synthesis_blocks(context),
    )


@pytest.mark.asyncio
async def test_actual_synthesis_dispatch_receives_reasoning_and_source_beyond_old_prefix():
    perspective = _perspective()
    assert "RETAINED_EVIDENCE" not in perspective.response[:1000]

    delivered = {}

    async def complete(request):
        assert request.model == "profile:32b"
        assert request.extra["num_ctx"] == LOCAL_SYNTHESIS_CONTEXT_TOKENS
        assert request.extra["max_tokens"] == 8000
        assert request.extra["think"] is False
        delivered.update(system_prompt=request.messages[0]["content"], user_prompt=request.messages[1]["content"])
        prompt = request.messages[1]["content"]
        assert "RETAINED_EVIDENCE" in prompt
        assert "source-sha" in prompt
        assert "compound operation is not one atomic operation" in prompt
        assert "extension's behavior remains unmeasured" in prompt
        assert "documented transaction guarantee" in prompt
        assert "Contributors: 1" in prompt
        assert len(prompt) <= MAX_SYNTHESIS_PROMPT_CHARS
        return ExpertChatResult(message=SimpleNamespace(content="Answer."), stop_reason="stop")

    result = await ExpertCouncil(
        synthesis_client=_native_local(complete),
        synthesis_model="profile:32b",
        synthesis_provider="local",
    )._synthesise(
        "What should we do?",
        [perspective],
        budget=0,
    )
    assert result["synthesis_status"] == "completed"
    artifact = build_consult_payload(
        "What should we do?", ExpertCouncil._consult_result("What should we do?", 0, [perspective], result, 0)
    )
    receipt = artifact["context_delivery"]
    assert receipt["user_prompt"] == delivered["user_prompt"]
    assert receipt["system_prompt"] == delivered["system_prompt"]
    assert receipt["user_prompt_sha256"] == hashlib.sha256(delivered["user_prompt"].encode()).hexdigest()
    assert receipt["freshness"] == "stored_context_only"


def test_bounded_allocation_keeps_each_contributor_and_reports_omissions():
    perspectives = [
        ExpertPerspective(
            expert_name=f"Expert {i}",
            domain="d",
            response="",
            synthesis_blocks=[f"Evidence {i}.", "Long complete judgment. " * 1000],
        )
        for i in range(10)
    ]
    prompt = build_synthesis_prompt("Compare the evidence.", perspectives)
    assert len(prompt) <= MAX_SYNTHESIS_PROMPT_CHARS
    for i in range(10):
        assert f"Expert: Expert {i}\n" in prompt
        assert f"Evidence {i}." in prompt
    assert prompt.count("context block(s) omitted") == 10
    for chunk in prompt.split("Expert: ")[1:]:
        body, marker, notice = chunk.partition("omitted by the prompt limit")
        assert marker
        assert "Long complete judgment." not in body
        assert "Long complete judgment." in notice


def test_legacy_packet_keeps_later_complete_evidence_when_earlier_block_does_not_fit():
    perspective = ExpertPerspective(
        expert_name="Legacy", domain="d", response="Long introduction. " * 1000 + "\n\nSOURCE: retained evidence."
    )
    prompt = build_synthesis_prompt("Question", [perspective])
    body, marker, notice = prompt.partition("omitted by the prompt limit")
    assert "SOURCE: retained evidence." in body
    assert marker
    assert "Long introduction." not in body
    assert "Long introduction." in notice


@pytest.mark.asyncio
async def test_oversized_question_fails_before_dispatch_without_silent_shortening():
    async def complete(_request):
        pytest.fail("oversized request dispatched")

    result = await ExpertCouncil(
        synthesis_client=_native_local(complete),
        synthesis_model="explicit:70b",
        synthesis_provider="local",
    )._synthesise(
        "q" * MAX_SYNTHESIS_PROMPT_CHARS,
        [_perspective()],
        budget=0,
    )
    assert result["synthesis_status"] == "failed"
    assert result["cost"] == 0


def test_requested_length_outranks_default_and_follows_the_evidence():
    """Regression (2026-10-17/18): a 100-word request competed with a fixed 700-word cap."""
    perspective = ExpertPerspective(
        expert_name="Reader",
        domain="d",
        response="",
        synthesis_blocks=["Evidence block. " * 50],
    )
    prompt = build_synthesis_prompt("In under 100 words, can I reuse this checkpoint?", [perspective])
    assert len(prompt) <= MAX_SYNTHESIS_PROMPT_CHARS
    assert "context block(s) omitted" not in prompt
    assert "Keep the complete answer under 700 words.\n" not in prompt
    assert "Without a requested length" in prompt
    assert "takes precedence over that default" in prompt
    assert "including verification, omissions, and uncertainty, fits inside it" in prompt
    closing = "Any length, format, or scope it requests governs the entire answer, including caveats."
    assert prompt.rindex("Evidence block.") < prompt.rindex("Answer this question: In under 100 words, can I reuse")
    assert prompt.rindex("Evidence block.") < prompt.rindex(closing)
    assert prompt.endswith(closing)


def test_long_question_is_referenced_not_restated():
    perspective = ExpertPerspective(expert_name="Reader", domain="d", response="", synthesis_blocks=["Evidence."])
    question = "Explain the checkpoint rule. " + "context " * 400
    prompt = build_synthesis_prompt(question, [perspective])
    assert prompt.count(question) == 1
    assert "Answer this question: the question stated above" in prompt


async def test_overlong_completed_synthesis_is_retained_as_form_failure_without_retry():
    calls = []
    draft = " ".join(["answer"] * 235)

    async def complete(request):
        calls.append(request)
        return ExpertChatResult(message=SimpleNamespace(content=draft), stop_reason="stop")

    council = ExpertCouncil(
        synthesis_client=_native_local(complete), synthesis_model="qwen-local", synthesis_provider="local"
    )
    result = await council._synthesise("What is safe? Answer in at most 180 words.", [_perspective()], budget=0)
    assert len(calls) == 1
    assert result["text"] == draft
    assert result["synthesis_status"] == "failed"
    assert result["synthesis_error_type"] == "ResponseWordLimit"
    assert result["response_form"]["actual_words"] == 235
    assert result["response_form"]["max_words"] == 180


@pytest.mark.parametrize(
    "question,limit",
    [
        ("What is safe? Answer in at most 180 words.", 180),
        ("Answer in at most 1 words.", 1),
        ("What is safe?\nAnswer in at most 25 words.", 25),
        ("What is safe? Answer in at least 180 words.", None),
        ("What is safe? Answer in under 180 words.", None),
        ("What is safe? Answer in approximately 180 words.", None),
        ('Discuss "Answer in at most 180 words."', None),
        ("Discuss `Answer in at most 180 words.`", None),
        ("Do not answer in at most 180 words.", None),
        ("Use 200 words. Answer in at most 180 words.", None),
        ("Answer in at most 0 words.", None),
        (" " * 80 + "Use at least 500 words. Answer in at most 180 words.", None),
        ("Explain this code.\n\n    Answer in at most 2 words.", None),
        ("Explain this code.\n\tAnswer in at most 2 words.", None),
        ("Explain this code.\n~~~\nAnswer in at most 2 words.", None),
        ("What is safe? Answer in at most 180 words. Explain fully.", None),
    ],
)
def test_literal_response_form_contract(question, limit):
    from deepr.experts.consult_response import response_form_contract

    contract = response_form_contract(question)
    assert contract["max_words"] == limit
    assert contract["admission"] == ("admitted" if limit else "not_admitted")
    assert contract["semantic_preservation"] == "unassessed"


@pytest.mark.parametrize(
    "status,error", [("completed", ""), ("truncated", "OutputLimit"), ("failed", "TransportFailure")]
)
def test_response_form_never_replaces_existing_failure_or_shortens_output(status, error):
    from deepr.experts.consult_response import admit_response_form

    draft = "Heading:\n\nTwo supported conditions."
    result = admit_response_form(
        "Answer in at most 2 words.",
        {
            "text": draft,
            "synthesis_status": status,
            "synthesis_error_type": error,
            "cost": 0.0,
            "tokens_input": 100,
            "tokens_output": 20,
            "provider_request_id": "retained-attempt",
        },
    )
    assert result["text"] == draft
    assert result["tokens_input"] == 100
    assert result["tokens_output"] == 20
    assert result["provider_request_id"] == "retained-attempt"
    assert result["response_form"]["actual_words"] == 4
    assert result["synthesis_error_type"] == ("ResponseWordLimit" if status == "completed" else error)


async def test_form_compliance_and_failure_propagate_through_consult_artifact_and_a2a_result():
    from deepr.a2a.consult_tasks import build_consult_artifact, build_consult_result

    calls = []

    async def complete(request):
        calls.append(request)
        return ExpertChatResult(message=SimpleNamespace(content="One two three."), stop_reason="stop")

    council = ExpertCouncil(
        synthesis_client=_native_local(complete), synthesis_model="qwen-local", synthesis_provider="local"
    )
    perspective = _perspective()
    perspective.context = {"recorded_dissent": ["The extension's behavior remains unmeasured."]}
    for limit, status in [(3, "completed"), (2, "failed")]:
        question = f"What is safe? Answer in at most {limit} words."
        synthesis = await council._synthesise(question, [perspective], budget=0)
        result = council._consult_result(question, 0, [perspective], synthesis, 0)
        payload = build_consult_payload(question, result)
        assert payload["synthesis_status"] == status
        assert payload["answer"] == "One two three."
        assert payload["response_form"]["max_words"] == limit
        assert payload["contract"]["maximum_synthesis_calls"] == 1
        dissent = payload["collaboration"]["dissent_handling"]
        assert dissent["delivered_dissent"]["status"] == "included"
        assert dissent["reviewed_preservation"] == "unassessed"
        artifact = build_consult_artifact(payload)
        assert artifact["content"]["response_form"] == payload["response_form"]
        task = build_consult_result(payload, artifact_id="test-form")
        assert task["response_form"] == payload["response_form"]
        assert task["status"] == ("completed" if limit == 3 else "incomplete")
    assert len(calls) == 2
