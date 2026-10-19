"""A position travels with the evidence it cites, and delivery is reported per position."""

from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.experts.brief_contracts import Position
from deepr.experts.chat_backends import ExpertChatResult
from deepr.experts.consult_context import ConsultContext
from deepr.experts.consult_prompt import (
    _OMISSION_RESERVE,
    MAX_SYNTHESIS_PROMPT_CHARS,
    PacketBlock,
    _omission_notice,
    brief_synthesis_blocks,
    build_synthesis_packet,
    pack_blocks,
)
from deepr.experts.council import ExpertCouncil, ExpertPerspective
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client
from deepr.experts.study_contracts import StudyFinding


def _finding(fid: str, body: str = "detail") -> StudyFinding:
    return StudyFinding(
        lens="mechanism",
        axis="interrogation",
        kind="concepts",
        title=f"Title {fid}",
        finding_id=fid,
        payload={"note": f"{fid.upper()}_EVIDENCE {body}"},
        grounded_anchor_count=1,
        corpus_shas=[f"sha-{fid}"],
    )


def _position(question: str, cites: list[str], stance: str = "Stance.") -> Position:
    return Position(question=question, stance=stance, reasoning="Because.", would_change_my_mind="", supported_by=cites)


def _context(positions: list[Position], findings: list[StudyFinding]) -> ConsultContext:
    return ConsultContext(
        expert_name="E",
        positions=positions,
        findings=findings,
        finding_sources={
            f.finding_id: (f"sha-{f.finding_id}", "origin", f"passage for {f.finding_id}") for f in findings
        },
    )


def _by_key(manifest: dict, key: str) -> dict:
    return next(item for item in manifest["positions"] if item["key"] == key)


def test_each_position_is_followed_by_its_own_cited_evidence_not_the_adjacent_block():
    """zip_longest used to pair position A with whatever finding sat at index 0."""
    context = _context(
        [_position("A?", ["f2", "f3"]), _position("B?", ["f1"])],
        [_finding("f1"), _finding("f3"), _finding("f2")],
    )
    keys = [block.key for block in brief_synthesis_blocks(context)]
    assert keys == ["notice", "position:1", "finding:f2", "finding:f3", "position:2", "finding:f1"]

    text, manifest = pack_blocks(brief_synthesis_blocks(context), MAX_SYNTHESIS_PROMPT_CHARS)
    assert text.index("Position: A?") < text.index("F2_EVIDENCE") < text.index("F3_EVIDENCE")
    assert text.index("F3_EVIDENCE") < text.index("Position: B?") < text.index("F1_EVIDENCE")
    assert _by_key(manifest, "position:1")["status"] == "complete"
    assert _by_key(manifest, "position:1")["delivered"] == ["f2", "f3"]
    assert _by_key(manifest, "position:2")["delivered"] == ["f1"]
    assert manifest["passages_delivered"] == ["sha-f1", "sha-f2", "sha-f3"]
    assert "Delivered support: partial" not in text


def test_stance_that_fits_without_its_qualifying_source_is_flagged_for_that_position():
    big = "qualification " * 400
    context = _context(
        [_position("A?", ["f1", "f2"]), _position("B?", ["f3"])],
        [_finding("f1"), _finding("f2", big), _finding("f3")],
    )
    blocks = brief_synthesis_blocks(context)
    budget = sum(len(block.text) + 2 for block in blocks if block.key != "finding:f2") + 600
    text, manifest = pack_blocks(blocks, budget)

    assert len(text) <= budget
    a = _by_key(manifest, "position:1")
    assert a["status"] == "partial"
    assert a["delivered"] == ["f1"]
    assert a["omitted_by_limit"] == ["f2"]
    assert _by_key(manifest, "position:2")["status"] == "complete"
    assert "F2_EVIDENCE" not in text
    a_block = text[text.index("Position: A?") : text.index("Position: B?")]
    assert "Delivered support: partial. Cited evidence not in this prompt: f2." in a_block
    b_block = text[text.index("Position: B?") :]
    assert "Delivered support: partial" not in b_block
    assert manifest["findings_omitted"] == ["f2"]


def test_shared_evidence_is_delivered_once_and_counts_for_both_positions():
    context = _context(
        [_position("A?", ["f1"]), _position("B?", ["f1", "f2"])],
        [_finding("f1"), _finding("f2")],
    )
    text, manifest = pack_blocks(brief_synthesis_blocks(context), MAX_SYNTHESIS_PROMPT_CHARS)
    assert text.count("F1_EVIDENCE") == 1
    assert _by_key(manifest, "position:1")["status"] == "complete"
    assert _by_key(manifest, "position:2")["delivered"] == ["f1", "f2"]


def test_evidence_an_earlier_position_could_not_fit_is_named_missing_for_a_later_one():
    big = "x" * 3000
    blocks = [
        PacketBlock("Position: A?", key="position:1", cites=("f1",), label="A?"),
        PacketBlock(f"Finding [f1] {big}", key="finding:f1"),
        PacketBlock("Position: B?", key="position:2", cites=("f1",), label="B?"),
    ]
    text, manifest = pack_blocks(blocks, 1000)
    body = text.partition("omitted by the prompt limit")[0]
    assert "Finding [f1]" not in body
    assert _by_key(manifest, "position:1")["status"] == "absent"
    assert _by_key(manifest, "position:2")["status"] == "absent"
    b_block = body[body.index("Position: B?") :]
    assert "Cited evidence not in this prompt: f1." in b_block


def test_position_that_cannot_fit_is_omitted_and_its_evidence_may_still_be_offered():
    blocks = [
        PacketBlock("Position: huge " + "y" * 3000, key="position:1", cites=("f1",), label="huge"),
        PacketBlock("Finding [f1] small", key="finding:f1"),
    ]
    text, manifest = pack_blocks(blocks, 1000)
    assert _by_key(manifest, "position:1")["status"] == "omitted"
    assert "Finding [f1] small" in text
    assert manifest["findings_delivered"] == ["f1"]
    assert "position:1" in manifest["omitted_keys"]


def test_partial_line_never_outgrows_the_room_reserved_for_it():
    """Short ids that fit and long ids that do not must not push the prompt past its bound."""
    short = [f"s{n}" for n in range(6)]
    long = ["L" * 60 + str(n) for n in range(2)]
    blocks = [
        PacketBlock("Notice", key="notice"),
        PacketBlock("Position: A?", key="position:1", cites=(*short, *long), label="A?"),
        *(PacketBlock(f"Finding [{fid}] tiny", key=f"finding:{fid}") for fid in short),
        *(PacketBlock(f"Finding [{fid}] " + "big " * 400, key=f"finding:{fid}") for fid in long),
    ]
    for budget in range(400, 2400, 3):
        text, manifest = pack_blocks(blocks, budget)
        assert len(text) <= budget, budget
        a = _by_key(manifest, "position:1")
        if a["status"] == "partial" and a["omitted_by_limit"] == long:
            assert f"Cited evidence not in this prompt: {long[0]}, {long[1]}." in text


_IDS = st.one_of(
    st.text(alphabet="abc0123", min_size=1, max_size=3),
    st.text(alphabet="xyz789-", min_size=50, max_size=70),
)


@settings(max_examples=300, deadline=None)
@given(
    findings=st.dictionaries(_IDS, st.sampled_from([4, 20, 300, 2500]), min_size=0, max_size=12),
    positions=st.lists(st.tuples(st.integers(1, 900), st.lists(_IDS, max_size=10)), max_size=6),
    extras=st.lists(st.integers(1, 1500), max_size=4),
    budget=st.integers(min_value=260, max_value=9000),
)
def test_packed_text_never_exceeds_its_budget(findings, positions, extras, budget):
    blocks = [PacketBlock("x" * size, key=f"extra:{n}") for n, size in enumerate(extras)]
    cited_ids = list(findings)
    for rank, (size, cites) in enumerate(positions, 1):
        cites = tuple(dict.fromkeys([*cites, *cited_ids[rank - 1 : rank + 1]]))
        blocks.append(PacketBlock("p" * size, key=f"position:{rank}", cites=cites, label=str(rank)))
        blocks.extend(PacketBlock("f" * findings[fid], key=f"finding:{fid}") for fid in cites if fid in findings)
    text, manifest = pack_blocks(blocks, budget)
    assert len(text) <= budget
    for position in manifest["positions"]:
        assert set(position["delivered"]).isdisjoint(position["omitted_by_limit"])


def test_cited_finding_missing_from_the_packet_is_reported_unavailable():
    context = _context([_position("A?", ["f1", "gone-9"])], [_finding("f1")])
    _, manifest = pack_blocks(brief_synthesis_blocks(context), MAX_SYNTHESIS_PROMPT_CHARS)
    a = _by_key(manifest, "position:1")
    assert a["unavailable"] == ["gone-9"]
    assert a["delivered"] == ["f1"]
    assert a["status"] == "partial"


def test_position_without_citations_is_not_reported_as_supported():
    context = _context([_position("A?", [])], [])
    _, manifest = pack_blocks(brief_synthesis_blocks(context), MAX_SYNTHESIS_PROMPT_CHARS)
    assert _by_key(manifest, "position:1")["status"] == "no_cited_support"


def test_hundreds_of_long_omitted_blocks_keep_the_notice_and_prompt_in_bounds():
    blocks = [PacketBlock(("Omitted heading " * 20) + str(i) + "\n" + "z" * 400, key=f"x:{i}") for i in range(400)]
    notice = _omission_notice(blocks)
    assert len(notice) <= _OMISSION_RESERVE
    assert notice.startswith("[400 context block(s) omitted by the prompt limit: ")
    assert "more. Coverage is incomplete" in notice

    perspectives = [
        ExpertPerspective(expert_name=f"Expert {n} " + "n" * 200, domain="d", response="", synthesis_blocks=blocks)
        for n in range(3)
    ]
    prompt, manifest = build_synthesis_packet("Compare. " * 50, perspectives)
    assert len(prompt) <= MAX_SYNTHESIS_PROMPT_CHARS
    assert [item["expert"] for item in manifest["experts"]] == [p.expert_name for p in perspectives]
    for item in manifest["experts"]:
        assert item["delivered_chars"] <= item["budget_chars"]
        assert item["blocks_omitted"] > 0


def test_notice_reserve_pays_for_its_own_separator():
    """Found by the property test: a full-size notice plus its separator overran by two characters."""
    blocks = [PacketBlock("f" * 20, key="first"), *(PacketBlock("g" * 70 + str(n), key=f"x:{n}") for n in range(10))]
    text, _ = pack_blocks(blocks, 260)
    assert len(text) <= 260
    assert len(_omission_notice(blocks[1:])) <= _OMISSION_RESERVE - 2


def test_plain_string_blocks_remain_supported():
    text, manifest = pack_blocks(["Evidence one.", "Evidence two."], 1000)
    assert text == "Evidence one.\n\nEvidence two."
    assert manifest["positions"] == []
    assert manifest["blocks_omitted"] == 0


@pytest.mark.asyncio
async def test_dispatch_receipt_carries_the_manifest_with_one_call():
    context = _context([_position("A?", ["f1"])], [_finding("f1")])
    perspective = ExpertPerspective(
        expert_name="E",
        domain="d",
        response="packet",
        synthesis_blocks=brief_synthesis_blocks(context),
        context={"source": "brief", "coverage": "partial", "study_fingerprint": "fp", "study_binding": "matched"},
    )
    calls = []

    class Backend:
        async def complete(self, request):
            calls.append(request.messages[1]["content"])
            return ExpertChatResult(message=SimpleNamespace(content="Answer."), stop_reason="stop")

    result = await ExpertCouncil(
        synthesis_client=_mark_zero_dollar_client(Backend(), capacity_source="local"),
        synthesis_model="profile:32b",
        synthesis_provider="local",
    )._synthesise("A?", [perspective], budget=0)

    assert len(calls) == 1
    delivery = result["context_delivery"]
    assert delivery["user_prompt"] == calls[0]
    manifest = delivery["delivery_manifest"]
    expert = manifest["experts"][0]
    assert expert["study_fingerprint"] == "fp"
    assert expert["study_binding"] == "matched"
    assert expert["assembly_coverage"] == "partial"
    assert _by_key(expert, "position:1")["status"] == "complete"
    assert result["cost"] == 0


def test_delivered_block_from_a_mismatched_study_is_not_complete_support():
    """Review finding: a reused id from another study reached the prompt and was reported complete."""
    context = _context([_position("A?", ["f1"])], [_finding("f1")])
    context.support = [
        {"question": "A?", "study_binding": "mismatch", "resolved_finding_ids": [], "resolved": False},
    ]
    text, manifest = pack_blocks(brief_synthesis_blocks(context), MAX_SYNTHESIS_PROMPT_CHARS)
    a = _by_key(manifest, "position:1")
    assert "F1_EVIDENCE" in text
    assert a["delivered"] == ["f1"]
    assert a["unresolved_support"] == ["f1"]
    assert a["status"] == "absent"

    context.support = [
        {"question": "A?", "study_binding": "matched", "resolved_finding_ids": ["f1"], "resolved": True},
    ]
    _, manifest = pack_blocks(brief_synthesis_blocks(context), MAX_SYNTHESIS_PROMPT_CHARS)
    assert _by_key(manifest, "position:1")["status"] == "complete"


def test_omitted_position_reports_evidence_that_was_delivered_alone():
    """Review finding: an omitted stance listed its standalone-delivered evidence as missing."""
    blocks = [
        PacketBlock("Position: small", key="position:1", cites=(), label="small"),
        PacketBlock("Position: huge " + "y" * 2000, key="position:2", cites=("b",), label="huge"),
        PacketBlock("Finding [b] short", key="finding:b"),
    ]
    _, manifest = pack_blocks(blocks, 1200)
    huge = _by_key(manifest, "position:2")
    assert huge["status"] == "omitted"
    assert huge["delivered"] == ["b"]
    assert huge["omitted_by_limit"] == []
    assert [item["key"] for item in manifest["positions"]] == ["position:1", "position:2"]
