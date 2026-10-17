"""Citation identity, retained passages, and structural dissent delivery."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.briefed_perspective import build_briefed_perspective
from deepr.experts.consult import _dissent_handling, build_consult_payload
from deepr.experts.consult_context import ConsultContext
from deepr.experts.consult_prompt import brief_synthesis_blocks, build_synthesis_prompt
from deepr.experts.consult_support import bind_study, recorded_statement, resolve_position_support, study_fingerprint
from deepr.experts.council import ExpertCouncil, ExpertPerspective
from deepr.experts.knowledge_wiki import _position_page
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult
from deepr.mcp.consult_validation import _dissent_contract_holds


def _finding(**overrides: object) -> StudyFinding:
    finding = StudyFinding(
        lens="failure",
        axis="interrogation",
        kind="fail_patterns",
        title="Latency climbs",
        finding_id="failure-1",
        grounded_anchor_count=1,
        corpus_shas=["abc"],
        anchors=["fifty clusters"],
    )
    for key, value in overrides.items():
        setattr(finding, key, value)
    return finding


def _study(finding: StudyFinding) -> StudyResult:
    return StudyResult(
        expert_name="E",
        outcomes=[LensOutcome(lens=finding.lens, axis=finding.axis, status="ok", findings=[finding])],
    )


def _perspective(context: ConsultContext, **context_fields: object) -> ExpertPerspective:
    return ExpertPerspective(
        expert_name="E",
        domain="latency",
        response="packet",
        confidence=0.4,
        synthesis_blocks=brief_synthesis_blocks(context),
        context={
            "recorded_dissent": [],
            "live": list(context.live),
            "unknown": list(context.unknown),
            **context_fields,
        },
    )


def test_placeholder_tokens_are_empty_and_sentences_stay():
    assert recorded_statement(" false ") == ""
    assert recorded_statement("N/A") == ""
    assert recorded_statement("nil") == ""
    sentence = "No measured deployment shows flat latency."
    assert recorded_statement(sentence) == sentence


def test_fingerprint_changes_when_the_cited_finding_changes():
    original = _study(_finding())
    changed = _study(_finding(title="A different claim under the same id"))
    fingerprint = study_fingerprint(original)
    assert fingerprint == study_fingerprint(original)
    assert fingerprint != study_fingerprint(changed)
    assert bind_study(ExpertBrief(expert_name="E"), original) == "unbound"
    assert bind_study(None, original) == "unbound"
    bound = ExpertBrief(expert_name="E", study_fingerprint=fingerprint)
    assert bind_study(bound, None) == "no_study"
    assert bind_study(bound, changed) == "mismatch"
    assert bind_study(bound, original) == "matched"


def test_resolution_requires_binding_anchor_and_passage():
    finding = _finding()
    position = Position(
        question="q",
        stance="s",
        reasoning="Measured.",
        would_change_my_mind="A flat measurement above fifty clusters.",
        supported_by=["failure-1"],
    )
    passages = {"failure-1": ("abc", "url:a", "fifty clusters were measured")}
    resolved = resolve_position_support(
        position,
        findings={"failure-1": finding},
        passages=passages,
        binding="matched",
    )
    assert resolved["resolved"] is True

    unread = resolve_position_support(
        position,
        findings={"failure-1": finding},
        passages={"failure-1": ("abc", "url:a", "  ")},
        binding="matched",
    )
    assert unread["resolved"] is False
    assert unread["missing_passage_ids"] == ["failure-1"]

    unbound = resolve_position_support(
        position,
        findings={"failure-1": finding},
        passages=passages,
        binding="unbound",
    )
    assert unbound["resolved"] is False
    assert unbound["resolved_finding_ids"] == []


def test_wiki_page_does_not_treat_a_placeholder_as_dissent():
    position = Position(
        question="Does latency climb?",
        stance="Yes.",
        reasoning="Measured.",
        would_change_my_mind="false",
        unresolved_dissent="none",
    )
    page = _position_page(position, {})
    assert "Not recorded." in page
    assert "None recorded; this is not proof of consensus." in page


def test_live_and_unknown_reach_the_prompt_or_are_named_when_omitted():
    context = ConsultContext(
        expert_name="E",
        positions=[
            Position(
                question="Does latency climb?",
                stance="Yes, above fifty clusters.",
                reasoning="The retained measurement says so.",
                would_change_my_mind="A flat measurement above fifty clusters.",
                unresolved_dissent="false",
                supported_by=["failure-1"],
            )
        ],
        live=["The threshold may have moved since the measurement."],
        unknown=["Behaviour above five hundred clusters."],
        support=[
            {
                "question": "Does latency climb?",
                "resolved": False,
                "study_binding": "unbound",
                "missing_finding_ids": [],
                "unanchored_finding_ids": [],
                "missing_passage_ids": [],
            }
        ],
    )
    rendered = "\n\n".join(brief_synthesis_blocks(context))
    assert "Live:\n- The threshold may have moved since the measurement." in rendered
    assert "Unknown:\n- Behaviour above five hundred clusters." in rendered
    assert "Support unresolved (unbound)" in rendered
    assert "Unresolved dissent" not in rendered

    huge = ConsultContext(
        expert_name="E",
        live=["UNIQUE_LIVE_CAVEAT " + ("detail " * 8000)],
        unknown=["UNIQUE_UNKNOWN_CAVEAT"],
    )
    prompt = build_synthesis_prompt("q", [_perspective(huge)])
    assert "UNIQUE_LIVE_CAVEAT" not in prompt
    assert "omitted by the prompt limit: Live:" in prompt
    assert "UNIQUE_UNKNOWN_CAVEAT" in prompt


def test_briefed_perspective_keeps_real_caveats_and_drops_placeholders(monkeypatch):
    context = ConsultContext(
        expert_name="E",
        positions=[
            Position(
                question="Does latency climb?",
                stance="Yes.",
                reasoning="Measured.",
                unresolved_dissent="One publisher reports the opposite load.",
                would_change_my_mind="false",
                supported_by=["failure-1"],
            )
        ],
        live=["Which cluster size was measured?"],
        unknown=["Whether the result replicates."],
        support=[{"question": "Does latency climb?", "resolved": True, "study_binding": "matched"}],
    )
    monkeypatch.setattr("deepr.experts.briefed_perspective.load_consult_context", lambda *_args, **_kwargs: context)
    perspective = build_briefed_perspective("latency clusters", "E", "latency", ExpertPerspective)
    assert perspective is not None
    assert perspective.context["recorded_dissent"] == ["One publisher reports the opposite load."]
    assert perspective.context["live"] == ["Which cluster size was measured?"]
    assert perspective.context["unknown"] == ["Whether the result replicates."]
    prompt = build_synthesis_prompt("latency clusters", [perspective])
    assert "One publisher reports the opposite load." in prompt
    assert "Which cluster size was measured?" in prompt
    assert "Whether the result replicates." in prompt
    assert "Unresolved dissent: false" not in prompt


def test_dissent_preserved_is_structural():
    included = _dissent_handling(
        {
            "synthesis_status": "completed",
            "perspectives": [{"context": {"recorded_dissent": ["A publisher disagrees."], "live": [], "unknown": []}}],
            "context_delivery": {"user_prompt": "Position\nUnresolved dissent: A publisher disagrees."},
        }
    )
    assert included["dissent_preserved"] is True
    assert included["delivered_dissent"]["status"] == "included"
    assert included["reviewed_preservation"] == "unassessed"
    assert included["empty_disagreements_are_not_consensus"] is True
    assert _dissent_contract_holds(included) is True

    omitted = _dissent_handling(
        {
            "synthesis_status": "completed",
            "perspectives": [{"context": {"live": ["The threshold may have moved."]}}],
            "context_delivery": {
                "user_prompt": "Stored research only.\n\n[1 context block(s) omitted by the prompt limit: Live:.]"
            },
        }
    )
    assert omitted["dissent_preserved"] is False
    assert omitted["delivered_dissent"]["status"] == "omitted"
    assert omitted["delivered_dissent"]["omitted"] == ["The threshold may have moved."]
    assert _dissent_contract_holds(omitted) is True

    named_only_in_omission = _dissent_handling(
        {
            "synthesis_status": "truncated",
            "perspectives": [{"context": {"unknown": ["Replication remains open."]}}],
            "context_delivery": {
                "user_prompt": (
                    "Stored research only.\n\n"
                    "[1 context block(s) omitted by the prompt limit: Unknown: Replication remains open.]"
                )
            },
        }
    )
    assert named_only_in_omission["dissent_preserved"] is False
    assert named_only_in_omission["delivered_dissent"]["status"] == "omitted"

    failed = _dissent_handling(
        {
            "synthesis_status": "failed",
            "perspectives": [{"context": {"unknown": ["Replication is unknown."]}}],
            "context_delivery": {},
        }
    )
    assert failed["dissent_preserved"] is False
    assert failed["delivered_dissent"]["status"] == "not_delivered"
    assert _dissent_contract_holds(failed) is True
    assert _dissent_contract_holds({"dissent_preserved": True}) is False


@pytest.mark.asyncio
async def test_completed_local_synthesis_records_delivered_caveats():
    context = ConsultContext(
        expert_name="E",
        positions=[
            Position(
                question="Does latency climb?",
                stance="Yes.",
                reasoning="Measured.",
                would_change_my_mind="A flat measurement above fifty clusters.",
                unresolved_dissent="One publisher reports the opposite load.",
                supported_by=["failure-1"],
            )
        ],
        live=["Which cluster size was measured?"],
        unknown=["Replication remains open."],
        support=[{"resolved": True}],
    )
    perspective = _perspective(
        context,
        recorded_dissent=["One publisher reports the opposite load."],
        source="brief",
    )
    perspective.confidence = 0.75

    class Native:
        async def complete(self, _request):
            return SimpleNamespace(message=SimpleNamespace(content="Answer."), stop_reason="stop")

    council_result = await ExpertCouncil(
        synthesis_client=_mark_zero_dollar_client(Native(), capacity_source="local"),
        synthesis_model="qwen-local",
        synthesis_provider="local",
    )._synthesise("Does latency climb?", [perspective], budget=0)
    payload = build_consult_payload(
        "Does latency climb?",
        ExpertCouncil._consult_result("Does latency climb?", 0, [perspective], council_result, 0),
    )
    prompt = payload["context_delivery"]["user_prompt"]
    dissent = payload["collaboration"]["dissent_handling"]
    assert "One publisher reports the opposite load." in prompt
    assert "Which cluster size was measured?" in prompt
    assert "Replication remains open." in prompt
    assert dissent["dissent_preserved"] is True
    assert dissent["input_dissent"]["recorded_count"] == 3
    assert dissent["delivered_dissent"]["status"] == "included"
    assert _dissent_contract_holds(dissent) is True
