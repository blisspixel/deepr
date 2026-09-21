"""Regressions for evidence lost between context assembly and synthesis."""

import hashlib
from types import SimpleNamespace

import pytest

from deepr.experts.brief_contracts import Position
from deepr.experts.consult import build_consult_payload
from deepr.experts.consult_context import ConsultContext, render_consult_packet
from deepr.experts.consult_prompt import MAX_SYNTHESIS_PROMPT_CHARS, brief_synthesis_blocks, build_synthesis_prompt
from deepr.experts.council import ExpertCouncil, ExpertPerspective
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client
from deepr.experts.study_contracts import StudyFinding


def _perspective():
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
        findings=[
            StudyFinding(
                lens="mechanism",
                axis="interrogation",
                kind="concepts",
                title="Coordination",
                finding_id="f1",
                grounded_anchor_count=1,
                corpus_shas=["source-sha"],
                anchors=["RETAINED_EVIDENCE: separate operations require coordination."],
            )
        ],
        sources=[("source-sha", "reference.example", "RETAINED_EVIDENCE: separate operations require coordination.")],
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

    async def create(**kwargs):
        delivered.update(system_prompt=kwargs["messages"][0]["content"], user_prompt=kwargs["messages"][1]["content"])
        prompt = kwargs["messages"][1]["content"]
        assert "RETAINED_EVIDENCE" in prompt
        assert "source-sha" in prompt
        assert "compound operation is not one atomic operation" in prompt
        assert "extension's behavior remains unmeasured" in prompt
        assert "documented transaction guarantee" in prompt
        assert "Contributors: 1" in prompt
        assert len(prompt) <= MAX_SYNTHESIS_PROMPT_CHARS
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Answer."), finish_reason="stop")]
        )

    client = _mark_zero_dollar_client(
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), capacity_source="local"
    )
    result = await ExpertCouncil(
        synthesis_client=client, synthesis_model="fixture", synthesis_provider="local"
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
    assert "Long complete judgment." not in prompt


def test_legacy_packet_keeps_later_complete_evidence_when_earlier_block_does_not_fit():
    perspective = ExpertPerspective(
        expert_name="Legacy", domain="d", response="Long introduction. " * 1000 + "\n\nSOURCE: retained evidence."
    )
    prompt = build_synthesis_prompt("Question", [perspective])
    assert "SOURCE: retained evidence." in prompt
    assert "context block(s) omitted" in prompt
    assert "Long introduction." not in prompt


@pytest.mark.asyncio
async def test_oversized_question_fails_before_dispatch_without_silent_shortening():
    async def create(**kwargs):
        pytest.fail("oversized request dispatched")

    client = _mark_zero_dollar_client(
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), capacity_source="local"
    )
    result = await ExpertCouncil(
        synthesis_client=client, synthesis_model="fixture", synthesis_provider="local"
    )._synthesise(
        "q" * MAX_SYNTHESIS_PROMPT_CHARS,
        [_perspective()],
        budget=0,
    )
    assert result["synthesis_status"] == "failed"
    assert result["cost"] == 0
