"""Multi-document findings keep every selected window, or name the one that missed.

Resolved still means one anchored passage was read. Source-bundle coverage is
a separate delivery record and does not claim the relationship holds.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

import pytest

from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.consult_context import ConsultContext, _tokens, build_consult_context
from deepr.experts.consult_prompt import (
    _OMISSION_RESERVE,
    MAX_SYNTHESIS_PROMPT_CHARS,
    PacketBlock,
    brief_synthesis_blocks,
    build_synthesis_packet,
    pack_blocks,
)
from deepr.experts.consult_support import study_fingerprint
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.council import ExpertPerspective
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult

QUESTION = "When does the permit rule apply?"
FINDING_ID = "permit-1"
RULE = "Weekday constraint holds for ordinary operations. Applicable version 2024.1 remains in force."
CONDITION = "Holiday exception suspends that weekday constraint."
LATER = "LATER_BULLETIN_SCHEDULE supersedes nothing stored here."
DISSENT = "A later bulletin is not higher authority."
TODAY = date(2026, 11, 17)


def _overlap_guard(*texts: str) -> None:
    question = _tokens(QUESTION)
    for text in texts:
        assert not question & _tokens(text)


def _store(tmp_path, texts: list[tuple[str, str, str, str]], name: str = "corpus") -> CorpusStore:
    store = CorpusStore("Permit", storage_dir=tmp_path / name)
    for text, origin, publisher, fetched_at in texts:
        store.add(text, origin_key=origin, publisher=publisher, fetched_at=fetched_at)
    return store


def _context(
    tmp_path,
    *,
    sha_order: str = "ab",
    insert_order: str = "ab",
    condition: str = CONDITION,
    extra: tuple[str, str, str, str] | None = None,
    missing: bool = False,
    cap: int = 0,
) -> tuple[ConsultContext, dict[str, str]]:
    rule = (RULE, "weekday.example", "Weekday Press", "2024-01-15T00:00:00+00:00")
    other = (condition, "holiday.example", "Holiday Press", "2026-06-01T00:00:00+00:00")
    pieces = {"a": rule, "b": other}
    order = ["a", "b"] if insert_order == "ab" else ["b", "a"]
    rows = [pieces[name] for name in order]
    if extra is not None:
        rows.append(extra)
    if cap:
        rows.extend(
            (f"cap-body-{index} neutral filler", f"cap-{index}.example", f"Cap {index}", "2020-01-01T00:00:00+00:00")
            for index in range(cap)
        )
    _overlap_guard(*(text for text, _, _, _ in rows))
    corpus = _store(tmp_path, rows)
    by_origin = {entry.origin_key: entry.sha256 for entry in corpus.active_entries()}
    sha_a = by_origin["weekday.example"]
    sha_b = by_origin["holiday.example"]
    cited = [sha_a, sha_b] if sha_order == "ab" else [sha_b, sha_a]
    if missing:
        cited.append("ab" * 32)
    if cap:
        cited.extend(by_origin[f"cap-{index}.example"] for index in range(cap))
    finding = StudyFinding(
        lens="mechanism",
        axis="interrogation",
        kind="concepts",
        title="Cited relationship",
        finding_id=FINDING_ID,
        payload={"note": "Stored interpretation of the relationship."},
        anchors=[RULE, condition],
        grounded_anchor_count=1,
        corpus_shas=cited,
    )
    result = StudyResult(
        expert_name="Permit",
        outcomes=[LensOutcome(lens="mechanism", axis="interrogation", status="ok", findings=[finding])],
    )
    brief = ExpertBrief(expert_name="Permit", study_fingerprint=study_fingerprint(result))
    brief.positions = [
        Position(
            question=QUESTION,
            stance="The permit rule applies only when both retained conditions are inspected.",
            reasoning="Neither retained condition is sufficient on its own.",
            would_change_my_mind="A retained passage that states both conditions together.",
            unresolved_dissent=DISSENT,
            supported_by=[FINDING_ID],
        )
    ]
    context = build_consult_context(expert_name="Permit", question=QUESTION, brief=brief, result=result, corpus=corpus)
    return context, {"a": sha_a, "b": sha_b}


def _packet(context: ConsultContext, *, limit: int | None = None, monkeypatch=None):
    if limit is not None:
        assert monkeypatch is not None
        monkeypatch.setattr("deepr.experts.consult_prompt.MAX_SYNTHESIS_PROMPT_CHARS", limit)
    perspective = ExpertPerspective(
        expert_name="Permit",
        domain="permits",
        response="packet",
        confidence=0.4,
        synthesis_blocks=brief_synthesis_blocks(context),
        context={"source": "brief", "coverage": context.coverage, "study_binding": context.study_binding},
    )
    return build_synthesis_packet(QUESTION, [perspective], today=TODAY)


def _bundle(manifest: dict, finding_id: str = FINDING_ID) -> dict:
    return next(row for row in manifest["experts"][0]["source_bundles"] if row["finding_id"] == finding_id)


def _position_status(manifest: dict) -> str:
    return manifest["experts"][0]["positions"][0]["status"]


@pytest.mark.parametrize("sha_order", ["ab", "ba"])
@pytest.mark.parametrize("insert_order", ["ab", "ba"])
def test_both_sides_survive_order_and_the_resolution_label_stays_narrow(tmp_path, sha_order, insert_order):
    context, shas = _context(
        tmp_path,
        sha_order=sha_order,
        insert_order=insert_order,
        extra=(LATER, "later.example", "Later Press", "2026-11-01T00:00:00+00:00"),
    )
    assert context.reference_passages == []
    assert context.finding_sources[FINDING_ID][0] == context.source_bundles[FINDING_ID]["windows"][0]
    assert context.support[0]["resolved"] is True
    ordered = [shas["a"], shas["b"]] if sha_order == "ab" else [shas["b"], shas["a"]]
    assert context.source_bundles[FINDING_ID]["windows"] == ordered
    assert context.source_bundles[FINDING_ID]["missing_bytes"] == []
    assert context.source_bundles[FINDING_ID]["not_selected"] == []

    prompt, manifest = _packet(context)
    expert = manifest["experts"][0]
    assert RULE in prompt and CONDITION in prompt
    assert LATER not in prompt
    assert DISSENT in prompt
    assert "Weekday Press" in prompt and "Holiday Press" in prompt
    assert "retained copy fetched 2024-01-15T00:00:00+00:00" in prompt
    assert "retained copy fetched 2026-06-01T00:00:00+00:00" in prompt
    assert prompt.index(RULE) != prompt.index(CONDITION)
    first, second = (RULE, CONDITION) if sha_order == "ab" else (CONDITION, RULE)
    assert prompt.index(first) < prompt.index(second)
    assert expert["passages_delivered"] == sorted(ordered)
    row = _bundle(manifest)
    assert row["status"] == "complete"
    assert row["windows_delivered"] == ordered
    assert row["windows_omitted"] == []
    assert _position_status(manifest) == "complete"
    assert manifest["note"] == (
        "Delivery records what reached the prompt; it does not establish entailment or answer quality."
    )
    finding = next(block for block in brief_synthesis_blocks(context) if block.key == f"finding:{FINDING_ID}")
    assert RULE not in finding.text and CONDITION not in finding.text
    assert shas["a"] in finding.text and shas["b"] in finding.text


def test_one_sufficient_passage_has_no_multi_source_obligation(tmp_path):
    text = f"{RULE} {CONDITION}"
    _overlap_guard(text)
    corpus = _store(tmp_path, [(text, "weekday.example", "Weekday Press", "2024-01-15T00:00:00+00:00")])
    sha = next(entry.sha256 for entry in corpus.active_entries())
    finding = StudyFinding(
        lens="mechanism",
        axis="interrogation",
        kind="concepts",
        title="Cited relationship",
        finding_id=FINDING_ID,
        payload={"note": "Stored interpretation of the relationship."},
        anchors=[text],
        grounded_anchor_count=1,
        corpus_shas=[sha],
    )
    result = StudyResult(
        expert_name="Permit",
        outcomes=[LensOutcome(lens="mechanism", axis="interrogation", status="ok", findings=[finding])],
    )
    brief = ExpertBrief(expert_name="Permit", study_fingerprint=study_fingerprint(result))
    brief.positions = [
        Position(
            question=QUESTION,
            stance="The retained passage states the whole rule.",
            reasoning="One original passage is sufficient.",
            would_change_my_mind="A retained passage that withdraws the rule.",
            unresolved_dissent="",
            supported_by=[FINDING_ID],
        )
    ]
    context = build_consult_context(expert_name="Permit", question=QUESTION, brief=brief, result=result, corpus=corpus)
    assert context.reference_passages == []
    assert context.source_bundles[FINDING_ID]["windows"] == [sha]
    prompt, manifest = _packet(context)
    assert text in prompt
    assert "Source-bundle coverage" not in prompt
    assert manifest["experts"][0]["source_bundles"] == []
    assert manifest["experts"][0]["passages_delivered"] == [sha]
    assert _position_status(manifest) == "complete"
    assert context.support[0]["resolved"] is True
    assert not any(block.key.startswith("window:") for block in brief_synthesis_blocks(context))


def test_missing_bytes_are_named_and_do_not_become_silence(tmp_path):
    context, shas = _context(tmp_path, missing=True)
    missing = context.source_bundles[FINDING_ID]["missing_bytes"]
    assert missing == ["ab" * 32]
    prompt, manifest = _packet(context)
    assert RULE in prompt
    assert f"retained bytes missing {missing[0]}" in prompt
    assert "Missing retained bytes are not proof the source is silent." in prompt
    assert "does not disclose" not in prompt
    row = _bundle(manifest)
    assert row["status"] == "partial"
    assert row["windows_delivered"] == [shas["a"], shas["b"]]
    assert row["missing_bytes"] == missing
    assert context.support[0]["resolved"] is True
    assert _position_status(manifest) == "complete"


def test_a_source_past_the_cap_is_named_instead_of_pretending_it_was_read(tmp_path):
    context, shas = _context(tmp_path, cap=7)
    bundle = context.source_bundles[FINDING_ID]
    assert len(bundle["windows"]) == 8
    assert len(bundle["not_selected"]) == 1
    parked = bundle["not_selected"][0]
    prompt, manifest = _packet(context)
    assert "cap-body-6" not in prompt
    assert f"not selected within the source cap {parked}" in prompt
    assert "does not disclose" not in prompt
    row = _bundle(manifest)
    assert row["status"] == "partial"
    assert len(row["windows_delivered"]) == 8
    assert "cap-body-0" in prompt
    assert parked in row["not_selected"]
    assert parked not in row["windows_delivered"]
    assert shas["a"] in row["windows_delivered"] and shas["b"] in row["windows_delivered"]
    assert context.support[0]["resolved"] is True


def test_a_tight_prompt_names_the_omitted_window_without_changing_resolution(tmp_path, monkeypatch):
    padded = CONDITION + " " + ("zzzz " * 400)
    context, shas = _context(tmp_path, condition=padded)
    blocks = brief_synthesis_blocks(context)
    window_b = f"window:{FINDING_ID}:{shas['b']}"
    budget = _budget_omitting(blocks, window_b)
    text, packed = pack_blocks(blocks, budget)
    row = next(item for item in packed["source_bundles"] if item["finding_id"] == FINDING_ID)
    assert row["status"] == "partial"
    assert row["windows_delivered"] == [shas["a"]]
    assert row["windows_omitted"] == [shas["b"]]
    assert RULE in text and CONDITION not in text
    assert shas["b"] in text
    assert f"Window {FINDING_ID} {shas['b'][:16]}" in text
    assert packed["positions"][0]["status"] == "complete"
    assert context.support[0]["resolved"] is True
    assert "does not disclose" not in text

    roomy, roomy_manifest = _packet(context)
    assert CONDITION in roomy
    overhead = MAX_SYNTHESIS_PROMPT_CHARS - roomy_manifest["experts"][0]["budget_chars"]
    prompt, manifest = _packet(context, limit=overhead + budget, monkeypatch=monkeypatch)
    delivered = _bundle(manifest)
    assert delivered["status"] == "partial"
    assert delivered["windows_omitted"] == [shas["b"]]
    assert RULE in prompt and CONDITION not in prompt
    assert shas["b"] in prompt
    assert len(prompt) <= overhead + budget


def test_legacy_capture_without_bundles_still_embeds_the_first_window(tmp_path):
    context, shas = _context(tmp_path)
    legacy = asdict(context)
    legacy.pop("source_bundles")
    legacy["positions"] = context.positions
    legacy["findings"] = context.findings
    legacy["sources"] = [tuple(item) for item in legacy["sources"]]
    legacy["reference_passages"] = [tuple(item) for item in legacy["reference_passages"]]
    legacy["finding_sources"] = {key: tuple(item) for key, item in legacy["finding_sources"].items()}
    restored = ConsultContext(**legacy)
    assert restored.source_bundles == {}
    blocks = {block.key: block.text for block in brief_synthesis_blocks(restored)}
    assert f"window:{FINDING_ID}:{shas['a']}" not in blocks
    assert RULE in blocks[f"finding:{FINDING_ID}"]
    assert CONDITION not in blocks[f"finding:{FINDING_ID}"]
    assert "Source-bundle coverage" not in blocks[f"finding:{FINDING_ID}"]


def test_adding_a_second_source_does_not_rewrite_the_first_passage(tmp_path):
    alone_text = f"{RULE} {CONDITION}"
    corpus = _store(
        tmp_path, [(alone_text, "weekday.example", "Weekday Press", "2024-01-15T00:00:00+00:00")], name="alone"
    )
    sha = next(entry.sha256 for entry in corpus.active_entries())
    finding = StudyFinding(
        lens="mechanism",
        axis="interrogation",
        kind="concepts",
        title="Cited relationship",
        finding_id=FINDING_ID,
        anchors=[alone_text],
        grounded_anchor_count=1,
        corpus_shas=[sha],
    )
    result = StudyResult(
        expert_name="Permit",
        outcomes=[LensOutcome(lens="mechanism", axis="interrogation", status="ok", findings=[finding])],
    )
    brief = ExpertBrief(expert_name="Permit", study_fingerprint=study_fingerprint(result))
    brief.positions = [
        Position(
            question=QUESTION,
            stance="The retained passage states the whole rule.",
            reasoning="One original passage is sufficient.",
            would_change_my_mind="A retained passage that withdraws the rule.",
            supported_by=[FINDING_ID],
        )
    ]
    alone = build_consult_context(expert_name="Permit", question=QUESTION, brief=brief, result=result, corpus=corpus)
    alone_blocks = {block.key: block.text for block in brief_synthesis_blocks(alone)}
    assert alone_text in alone_blocks[f"finding:{FINDING_ID}"]

    both, shas = _context(tmp_path)
    both_blocks = {block.key: block.text for block in brief_synthesis_blocks(both)}
    assert RULE in both_blocks[f"window:{FINDING_ID}:{shas['a']}"]
    assert "Applicable version 2024.1 remains in force." in both_blocks[f"window:{FINDING_ID}:{shas['a']}"]
    assert CONDITION not in both_blocks[f"window:{FINDING_ID}:{shas['a']}"]
    assert RULE not in both_blocks[f"window:{FINDING_ID}:{shas['b']}"]


def _budget_omitting(blocks: list[PacketBlock], omit_key: str) -> int:
    """Largest budget that still drops omit_key while keeping the block before it."""
    index = next(i for i, block in enumerate(blocks) if block.key == omit_key)
    previous = blocks[index - 1].key
    upper = _OMISSION_RESERVE + sum(len(block.text) + 2 for block in blocks) + 400
    chosen = None
    for budget in range(upper, _OMISSION_RESERVE, -1):
        _, manifest = pack_blocks(blocks, budget)
        omitted = set(manifest["omitted_keys"])
        if omit_key in omitted and previous not in omitted:
            chosen = budget
            break
    if chosen is None:
        raise AssertionError(f"no budget omitted {omit_key} while keeping {previous}")
    return chosen
