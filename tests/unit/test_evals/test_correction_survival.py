"""Correction-survival diagnostic: frozen cases, stage receipts, complete accounting."""

import asyncio
import json

import pytest

from deepr.evals import correction_survival as cs
from deepr.evals.correction_survival_cases import (
    CASES,
    REVIEW_LABELS,
    WORLDS,
    Case,
    Obligation,
    case_set_sha256,
    world,
)


@pytest.fixture(scope="module")
def mock_run(tmp_path_factory):
    run_dir = tmp_path_factory.mktemp("cs") / "run"
    return run_dir, asyncio.run(cs.run_diagnostic(run_dir))


def _normalized(text):
    return " ".join(text.split()).casefold()


def test_case_set_is_internally_consistent_and_hash_is_stable():
    assert case_set_sha256() == case_set_sha256()
    for item in WORLDS:
        texts = {source.source_id: source.text for source in item.sources}
        for finding in item.findings:
            assert _normalized(finding.anchor) in _normalized(texts[finding.source_id]), finding.finding_id
        ids = {finding.finding_id for finding in item.findings}
        for position in item.positions:
            assert set(position.supported_by) <= ids
    for case in CASES:
        case_world = world(case.world_id)
        source_ids = {source.source_id for source in case_world.sources}
        finding_ids = {finding.finding_id for finding in case_world.findings}
        assert not set(case.forbidden_sources) & source_ids
        for obligation in case.obligations:
            assert not obligation.source_id or obligation.source_id in source_ids
            assert not obligation.finding_id or obligation.finding_id in finding_ids
    classes = {case.case_class for case in CASES}
    assert {"warranted_correction", "false_premise", "sound_premise_control", "answerable_control"} <= classes


def test_every_scheduled_attempt_is_recorded_with_zero_paid_calls(mock_run):
    run_dir, run = mock_run
    assert run["scheduled_attempts"] == len(run["attempts"]) == 36
    assert {attempt["status"] for attempt in run["attempts"]} == {"completed"}
    assert run["paid_calls"] == 0
    assert all(attempt["answer_calls"] == 1 for attempt in run["attempts"])
    assert cs.load_run(run_dir)["attempts"] == run["attempts"]
    prompt = json.loads((run_dir / "attempts" / "historical.production.c1" / "prompt.json").read_text())["prompt"]
    attempt = next(a for a in run["attempts"] if a["attempt_id"] == "historical.production.c1")
    assert attempt["prompt_sha256"] == cs._sha(prompt)


def test_receipts_are_mechanical_and_answers_stay_unreviewed(mock_run):
    _, run = mock_run
    production = [a for a in run["attempts"] if a["arm"] == "production"]
    for attempt in production:
        assert attempt["brief_synthesis_input"]["policy"]
        for receipt in attempt["stage_receipts"].values():
            assert receipt["answer"] == "unreviewed"
            if receipt["retrieval"] == "missed":
                assert receipt["delivery"] == "not_assembled"
    warranted = next(a for a in production if a["case_id"] == "warranted-correction")
    assert warranted["stage_receipts"]["use-correction"] == {
        "source": "present",
        "study": "represented",
        "briefing": "presented",
        "retrieval": "selected",
        "delivery": "delivered",
        "answer": "unreviewed",
    }
    fresh = next(a for a in run["attempts"] if a["case_id"] == "warranted-correction" and a["arm"] == "fresh_sources")
    assert fresh["stage_receipts"]["use-correction"]["study"] == "not_used_by_arm"
    assert fresh["stage_receipts"]["use-correction"]["retrieval"] == "provided"


def test_historical_question_never_receives_later_sources(mock_run):
    _, run = mock_run
    rows = [a["isolation"] for a in run["attempts"] if a["case_id"] == "historical"]
    assert len(rows) == 3
    assert all(row["status"] == "isolated" and row["leaked"] == [] for row in rows)


def test_a_leaking_world_is_reported(tmp_path):
    leaky = Case(
        "leak",
        "historical",
        "w2",
        "What did the documentation say before release 3?",
        (Obligation("no-later", "isolate", "No 3.0 source."),),
        forbidden_sources=("release-v3",),
    )
    run = asyncio.run(cs.run_diagnostic(tmp_path / "run", cases=(leaky,)))
    assert {a["isolation"]["status"] for a in run["attempts"]} == {"leaked"}
    assert all("release-v3" in a["isolation"]["leaked"] for a in run["attempts"])


def test_repetition_is_not_counted_as_new_evidence(mock_run):
    _, run = mock_run
    cycles = run["repeated_compression"]["w3.c2"]
    assert [row["cycle"] for row in cycles] == [1, 2]
    assert cycles[0]["study_fingerprint"] == cycles[1]["study_fingerprint"]
    assert cycles[0]["positions"] == cycles[1]["positions"]


def test_failed_answers_stay_in_the_denominator(tmp_path):
    async def failing(prompt):
        raise TimeoutError("local model stalled")

    run = asyncio.run(cs.run_diagnostic(tmp_path / "run", completion=failing, cases=CASES[:2]))
    report = cs.build_report(run)
    assert report["scheduled_attempts"] == report["recorded_attempts"] == 6
    assert all(a["status"] == "failed" and a["error_type"] == "TimeoutError" for a in run["attempts"])
    assert all(a["answer_sha256"] == "" for a in run["attempts"])
    assert report["arms"]["production"]["failed"] == 2


def test_distractors_make_retrieval_and_packing_observable(tmp_path):
    run = asyncio.run(cs.run_diagnostic(tmp_path / "run", distractors=60, cases=CASES[:3]))
    assert run["distractors_per_world"] == 60
    fresh = next(a for a in run["attempts"] if a["arm"] == "fresh_sources")
    assert fresh["delivery_manifest"]["experts"][0]["blocks_omitted"] > 0
    for attempt in run["attempts"]:
        assert attempt["prompt_chars"] <= 16000


def test_incomplete_altered_or_stale_runs_are_not_reusable(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    asyncio.run(cs.run_diagnostic(run_dir, cases=CASES[:1]))
    cs.load_run(run_dir)

    answer = run_dir / "attempts" / "warranted-correction.production.c1" / "answer.json"
    original = answer.read_text()
    answer.write_text(original.replace("MOCK", "EDITED"))
    with pytest.raises(cs.RunNotReusableError, match="altered"):
        cs.load_run(run_dir)
    answer.write_text(original)

    monkeypatch.setattr(cs, "case_set_sha256", lambda *_: "0" * 64)
    with pytest.raises(cs.RunNotReusableError, match="different case set"):
        cs.load_run(run_dir)
    monkeypatch.undo()

    (run_dir / cs.COMPLETE_MARKER).unlink()
    with pytest.raises(cs.RunNotReusableError, match="no completion marker"):
        cs.load_run(run_dir)


def test_blinded_labels_bind_to_exact_answers_before_the_key(mock_run):
    _, run = mock_run
    items, key = cs.blinded_review_packet(run, salt="s1")
    assert len(items) == 36
    flat = json.dumps(items)
    for arm in cs.ARMS:
        assert arm not in flat
    item = next(i for i in items if key[i["item_id"]] == "warranted-correction.production.c1")
    good = {
        "item_id": item["item_id"],
        "answer_sha256": item["answer_sha256"],
        "obligation_id": "use-correction",
        "label": REVIEW_LABELS[0],
        "reviewer": "reviewer-a",
    }
    bound = cs.bind_review_labels(run, key, [good])
    assert bound == {("warranted-correction.production.c1", "use-correction"): "used_correctly"}
    report = cs.build_report(run, bound)
    assert report["arms"]["production"]["stages"]["answer"]["used_correctly"] == 1
    assert report["reviewed_obligations"] == 1

    for broken, message in (
        ({**good, "answer_sha256": "f" * 64}, "different answer"),
        ({**good, "label": "pretty good"}, "label must be one of"),
        ({**good, "reviewer": " "}, "accountable reviewer"),
        ({**good, "obligation_id": "nope"}, "unknown obligation"),
        ({**good, "item_id": "missing"}, "unknown review item"),
    ):
        with pytest.raises(ValueError, match=message):
            cs.bind_review_labels(run, key, [broken])
    with pytest.raises(ValueError, match="duplicate"):
        cs.bind_review_labels(run, key, [good, good])


def test_report_renders_without_quality_claims(mock_run):
    _, run = mock_run
    text = cs.render_report(cs.build_report(run))
    assert "36 of 36 scheduled" in text
    assert "not answer quality" in text
    assert "Historical isolation: 3 isolated, 0 leaked." in text


def test_a_subset_run_is_labelled_and_never_passes_as_the_full_set(tmp_path):
    """Review finding: a one-case run carried the full set's hash and passed load_run as complete."""
    run_dir = tmp_path / "run"
    run = asyncio.run(cs.run_diagnostic(run_dir, cases=CASES[:1]))
    assert run["case_set_sha256"] != case_set_sha256()
    assert run["complete_case_set"] is False
    assert run["case_ids"] == [CASES[0].case_id]
    assert cs.load_run(run_dir)["complete_case_set"] is False
    assert "SUBSET of the case set" in cs.render_report(cs.build_report(run))

    marker = run_dir / cs.COMPLETE_MARKER
    payload = json.loads(marker.read_text())
    run_json = json.loads((run_dir / "run.json").read_text())
    run_json["attempts"] = run_json["attempts"][:-1]
    text = json.dumps(run_json, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    (run_dir / "run.json").write_text(text)
    marker.write_text(json.dumps({**payload, "run_sha256": cs._sha((run_dir / "run.json").read_bytes())}))
    with pytest.raises(cs.RunNotReusableError, match="every scheduled attempt"):
        cs.load_run(run_dir)


def test_isolation_catches_a_mid_source_sentence_in_the_prompt():
    case = next(case for case in CASES if case.forbidden_sources)
    built = cs._Materialized(world(case.world_id), None, None, {}, [])
    later = next(s for w in WORLDS for s in w.sources if s.source_id == "release-v3")
    middle = later.text.split(". ")[2]
    leaked = cs._isolation(case, built, f"Some prompt. {middle}. More.", {"experts": []})
    assert leaked["status"] == "leaked"
    assert leaked["leaked"] == ["release-v3"]
    assert cs._isolation(case, built, "Clean prompt.", {"experts": []})["status"] == "isolated"


def test_briefing_state_distinguishes_absent_findings():
    from types import SimpleNamespace

    brief = SimpleNamespace(synthesis_input={"presented_ids": ["a"], "omitted_ids": ["b"], "shortened": []})
    assert cs._briefing_state("a", brief) == "presented"
    assert cs._briefing_state("b", brief) == "omitted"
    assert cs._briefing_state("zzz", brief) == "not_in_study"
    assert cs._briefing_state("a", SimpleNamespace(synthesis_input={})) == "unrecorded"


def test_a_label_cannot_be_rebound_in_a_later_call(mock_run):
    _, run = mock_run
    items, key = cs.blinded_review_packet(run, salt="s2")
    item = items[0]
    obligation = item["obligations"][0]
    first = {
        "item_id": item["item_id"],
        "answer_sha256": item["answer_sha256"],
        "obligation_id": obligation,
        "label": "ignored",
        "reviewer": "reviewer-a",
    }
    bound = cs.bind_review_labels(run, key, [first])
    with pytest.raises(ValueError, match="duplicate"):
        cs.bind_review_labels(run, key, [{**first, "label": "used_correctly"}], existing=bound)


def test_legacy_answer_timing_is_never_relabelled_as_total_attempt_time(mock_run):
    from copy import deepcopy

    _, original = mock_run
    run = deepcopy(original)
    for attempt in run["attempts"]:
        for key in ("answer_elapsed_ms", "routing_elapsed_ms", "total_elapsed_ms", "finding_routing"):
            attempt.pop(key)
    report = cs.build_report(run)
    for arm in report["arms"].values():
        assert arm["answer_elapsed_ms"] == arm["elapsed_ms"]
        assert arm["routing_elapsed_ms"] is None and arm["total_elapsed_ms"] is None
        assert arm["routing"]["unknown_attempts"] == arm["attempts"]
        assert arm["routing"]["effective_counts"] == {}
    assert "None means unknown" in cs.render_report(report)
