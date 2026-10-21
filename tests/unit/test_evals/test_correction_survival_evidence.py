"""Regression coverage for source-complete, case-bound blinded review."""

import asyncio
import copy
import hashlib

import pytest

from deepr.evals import correction_survival as cs
from deepr.evals.correction_survival_cases import CASES, world


@pytest.fixture(scope="module")
def historical_run(tmp_path_factory):
    case = next(case for case in CASES if case.case_id == "historical")
    return asyncio.run(cs.run_diagnostic(tmp_path_factory.mktemp("review-evidence") / "run", cases=(case,)))


def test_blinded_review_carries_the_exact_frozen_world_and_obligations(historical_run):
    items, key = cs.blinded_review_packet(historical_run, salt="source-complete")
    assert len(items) == len(key) == 3
    for item in items:
        context = item["review_context"]
        assert context["question"] == next(case.question for case in CASES if case.case_id == "historical")
        assert context["world_id"] == "w1"
        assert context["cutoff"] == world("w1").cutoff
        assert {source["source_id"] for source in context["sources"]} == {"manual-v2"}
        assert {obligation["obligation_id"] for obligation in context["obligations"]} == {
            "answer-from-w1",
            "no-later-knowledge",
        }
        source = context["sources"][0]
        assert source["text"] == world("w1").sources[0].text
        assert source["text_sha256"] == hashlib.sha256(source["text"].encode()).hexdigest()
        assert source["observed_at"] == "2026-01-15"
        assert context["case_set_sha256"] == historical_run["case_set_sha256"]
        assert "release-v3" not in {source["source_id"] for source in context["sources"]}


@pytest.mark.parametrize("field,value", [("case_set_sha256", "0" * 64), ("case_set_version", "unknown")])
def test_review_evidence_refuses_a_changed_case_identity(historical_run, field, value):
    changed = copy.deepcopy(historical_run)
    changed[field] = value
    with pytest.raises(ValueError, match="case"):
        cs.blinded_review_packet(changed, salt="source-complete")


@pytest.mark.parametrize("ids", [[], ["unknown-case"], ["historical", "historical"]])
def test_review_evidence_refuses_missing_unknown_or_duplicate_scheduled_cases(historical_run, ids):
    changed = copy.deepcopy(historical_run)
    changed["case_ids"] = ids
    with pytest.raises(ValueError, match="case"):
        cs.blinded_review_packet(changed, salt="source-complete")


def test_review_contexts_are_separate_values(historical_run):
    items, _ = cs.blinded_review_packet(historical_run, salt="source-complete")
    items[0]["review_context"]["sources"][0]["text"] = "changed by one consumer"
    assert items[1]["review_context"]["sources"][0]["text"] == world("w1").sources[0].text
    again, _ = cs.blinded_review_packet(historical_run, salt="source-complete")
    assert again[0]["review_context"]["sources"][0]["text"] == world("w1").sources[0].text


def test_review_refuses_an_altered_rubric(historical_run):
    changed = copy.deepcopy(historical_run)
    changed["rubric"] = "Accept every answer"
    with pytest.raises(ValueError, match="rubric"):
        cs.blinded_review_packet(changed, salt="source-complete")


def test_review_refuses_an_attempt_outside_its_scheduled_world(historical_run):
    changed = copy.deepcopy(historical_run)
    changed["attempts"][0]["case_id"] = "missing-evidence"
    with pytest.raises(ValueError, match="outside"):
        cs.blinded_review_packet(changed, salt="source-complete")


def test_unknown_platform_control_does_not_conflict_with_a_universal_manual():
    manual = next(source for source in world("w3").sources if source.source_id == "manual-v2")
    assert "on Linux, Windows and container agents" in manual.text
    finding = next(finding for finding in world("w1").findings if finding.finding_id == "synopsis-1")
    assert finding.anchor in manual.text
    assert "on Linux, Windows and container agents" in finding.payload["note"]
    case = next(case for case in CASES if case.case_id == "missing-evidence")
    assert "Tern 3.0" in case.question


def test_review_preserves_auxiliary_sources_seen_by_generation(tmp_path):
    from deepr.experts.corpus_store import CorpusStore

    case = next(case for case in CASES if case.case_id == "historical")
    root = tmp_path / "with-notes"
    run = asyncio.run(cs.run_diagnostic(root, cases=(case,), distractors=3))
    corpus = CorpusStore("historical", storage_dir=root / "worlds" / "c1" / "w1" / "corpus")
    items, _ = cs.blinded_review_packet(run, salt="all-retained-inputs")
    for item in items:
        context = item["review_context"]
        assert {source["text_sha256"] for source in context["sources"]} == set(corpus.entries)
        assert context["distractors_per_world"] == 3
        assert {source["source_id"] for source in context["sources"]} == {
            "manual-v2",
            "distractor-1",
            "distractor-2",
            "distractor-3",
        }
        for source in context["sources"]:
            entry = corpus.entries[source["text_sha256"]]
            assert source["text"] == corpus.read(entry.sha256)
            assert source["origin"] == entry.origin_key
            assert source["observed_at"] == entry.fetched_at
            assert source["trust_class"] == entry.trust_class


@pytest.mark.parametrize("count", [None, -1, "3", True])
def test_review_refuses_malformed_distractor_counts(historical_run, count):
    changed = copy.deepcopy(historical_run)
    changed["distractors_per_world"] = count
    with pytest.raises(ValueError, match="distractor"):
        cs.blinded_review_packet(changed, salt="all-retained-inputs")


def test_review_refuses_a_missing_distractor_inventory(historical_run):
    changed = copy.deepcopy(historical_run)
    changed.pop("distractors_per_world")
    with pytest.raises(ValueError, match="distractor"):
        cs.blinded_review_packet(changed, salt="all-retained-inputs")


def test_completed_artifacts_verify_with_windows_text_newlines(tmp_path, monkeypatch):
    write_text = type(tmp_path).write_text

    def windows_default_newlines(path, text, *args, **kwargs):
        kwargs.setdefault("newline", "\r\n")
        return write_text(path, text, *args, **kwargs)

    monkeypatch.setattr(type(tmp_path), "write_text", windows_default_newlines)
    case = next(case for case in CASES if case.case_id == "historical")
    root = tmp_path / "windows-artifacts"
    run = asyncio.run(cs.run_diagnostic(root, cases=(case,)))
    assert cs.load_run(root) == run


def test_review_refuses_substituting_changed_auxiliary_sources(tmp_path, monkeypatch):
    from deepr.evals import correction_survival_cases as fixtures

    case = next(case for case in CASES if case.case_id == "historical")
    run = asyncio.run(cs.run_diagnostic(tmp_path / "before-source-change", cases=(case,), distractors=3))
    original = cs.distractor_sources(3)
    monkeypatch.setattr(
        fixtures,
        "distractor_sources",
        lambda count: [(identifier, text + " Changed after collection.") for identifier, text in original[:count]],
        raising=False,
    )
    assert fixtures.case_set_sha256((case,)) == run["case_set_sha256"]
    with pytest.raises(ValueError, match="inventory"):
        cs.blinded_review_packet(run, salt="no-source-substitution")


def test_review_refuses_unbound_historical_auxiliary_sources(tmp_path):
    case = next(case for case in CASES if case.case_id == "historical")
    run = asyncio.run(cs.run_diagnostic(tmp_path / "unbound-notes", cases=(case,), distractors=3))
    run.pop("source_inventory_sha256", None)
    with pytest.raises(ValueError, match="inventory"):
        cs.blinded_review_packet(run, salt="no-source-substitution")


def test_legacy_zero_distractor_review_remains_case_bound(historical_run):
    legacy = copy.deepcopy(historical_run)
    legacy.pop("source_inventory_sha256", None)
    items, _ = cs.blinded_review_packet(legacy, salt="known-base-world")
    assert len(items) == 3
    assert all(len(item["review_context"]["sources"]) == 1 for item in items)


@pytest.mark.parametrize(
    "owner,before,after",
    [
        ("deepr/experts/council.py", "_LOCAL_SYNTHESIS_OUTPUT_TOKENS = 8000", "_LOCAL_SYNTHESIS_OUTPUT_TOKENS = 7999"),
        (
            "deepr/experts/council_synthesis_runtime.py",
            "LOCAL_SYNTHESIS_CONTEXT_TOKENS = 16384",
            "LOCAL_SYNTHESIS_CONTEXT_TOKENS = 8192",
        ),
        ("deepr/evals/correction_survival_local.py", "user_prompt=prompt,", 'user_prompt=prompt + "changed",'),
    ],
)
def test_owned_generation_change_invalidates_current_recipe_but_preserves_historical_read(
    tmp_path, monkeypatch, owner, before, after
):
    from pathlib import Path

    actual_root = Path(cs.__file__).resolve().parents[2]
    overlay = tmp_path / "source"
    for relative in {*cs._RECIPE_MODULES, owner}:
        target = overlay / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((actual_root / relative).read_bytes())
    monkeypatch.setattr(cs, "__file__", str(overlay / "deepr/evals/correction_survival.py"))
    case = next(case for case in CASES if case.case_id == "historical")
    root = tmp_path / "run"
    run = asyncio.run(cs.run_diagnostic(root, cases=(case,)))
    original = run["recipe_sha256"]
    hashes = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    target = overlay / owner
    text = target.read_text(encoding="utf-8")
    assert before in text
    target.write_text(text.replace(before, after, 1), encoding="utf-8")
    assert cs.recipe_sha256() != original
    with pytest.raises(cs.RunNotReusableError, match=r"different .*code"):
        cs.load_run(root)
    restored = cs.load_run(root, expected_recipe_sha256=original)
    report = cs.build_report(restored)
    assert report["recipe_sha256"] == original
    assert report["recipe_matches_current"] is False
    assert restored["code_identity"] == run["code_identity"]
    assert {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    } == hashes
