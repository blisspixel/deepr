"""Tests for the ground-truth grounding-correctness eval."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.evals.grounding_correctness import (
    DEFAULT_GROUNDING_CASES,
    GROUNDING_CORRECTNESS_SCHEMA_VERSION,
    HARD_GROUNDING_CASES,
    GroundingCase,
    build_grounding_correctness_report,
    load_grounding_cases,
    run_grounding_correctness_eval,
)


def _verdict(supported):
    return SimpleNamespace(supported=supported)


_CASES = [
    GroundingCase("s1", "claim a", "evidence entails a", "supported"),
    GroundingCase("s2", "claim b", "evidence entails b", "supported"),
    GroundingCase("c1", "claim c", "evidence refutes c", "contradicted"),
    GroundingCase("u1", "claim d", "unrelated evidence", "unrelated"),
]


def test_case_validation_rejects_bad_label_and_empty():
    with pytest.raises(ValueError, match="label must be one of"):
        GroundingCase("x", "c", "e", "maybe")
    with pytest.raises(ValueError, match="non-empty"):
        GroundingCase("x", "  ", "e", "supported")


def test_default_golden_set_is_balanced_and_valid():
    labels = [c.label for c in DEFAULT_GROUNDING_CASES]
    assert len(DEFAULT_GROUNDING_CASES) == 30
    assert labels.count("supported") == 10
    assert labels.count("contradicted") == 10
    assert labels.count("unrelated") == 10
    # Case ids are unique.
    assert len({c.case_id for c in DEFAULT_GROUNDING_CASES}) == 30


def test_hard_golden_set_is_balanced_and_valid():
    labels = [c.label for c in HARD_GROUNDING_CASES]
    assert len(HARD_GROUNDING_CASES) == 20
    assert labels.count("supported") == 5
    assert labels.count("contradicted") == 5
    assert labels.count("unrelated") == 5
    assert labels.count("partial") == 5
    # Unique ids, and ids are distinct from the baseline set (so --set all has no clashes).
    hard_ids = {c.case_id for c in HARD_GROUNDING_CASES}
    assert len(hard_ids) == 20
    assert hard_ids.isdisjoint({c.case_id for c in DEFAULT_GROUNDING_CASES})


def test_partial_label_scores_as_not_entailed():
    # A "partial" claim (conjunction with only one conjunct supported) must NOT be
    # supported: a True verdict is a false support, a False verdict is a correct reject.
    partial = [GroundingCase("p1", "A and B", "evidence for A only", "partial")]
    false_support = build_grounding_correctness_report(partial, [SimpleNamespace(supported=True)])
    assert false_support["false_support_rate"] == 1.0
    assert false_support["cases"][0]["category"] == "false_support"

    correct_reject = build_grounding_correctness_report(partial, [SimpleNamespace(supported=False)])
    assert correct_reject["false_support_rate"] == 0.0
    assert correct_reject["cases"][0]["category"] == "correct_reject"
    assert correct_reject["overall_accuracy"] == 1.0


def test_report_groups_only_present_labels():
    # The baseline set has no "partial" cases, so the report must not emit an empty row.
    report = build_grounding_correctness_report(
        list(DEFAULT_GROUNDING_CASES),
        [SimpleNamespace(supported=(c.label == "supported")) for c in DEFAULT_GROUNDING_CASES],
    )
    assert "partial" not in report["label_counts"]
    assert set(report["label_counts"]) == {"supported", "contradicted", "unrelated"}


def test_perfect_checker_scores_ideal():
    # supported->True, everything else->False: a perfect checker.
    verdicts = [_verdict(c.label == "supported") for c in _CASES]
    report = build_grounding_correctness_report(_CASES, verdicts)

    assert report["schema_version"] == GROUNDING_CORRECTNESS_SCHEMA_VERSION
    assert report["support_precision"] == 1.0
    assert report["support_recall"] == 1.0
    assert report["false_support_rate"] == 0.0
    assert report["abstention_rate"] == 0.0
    assert report["overall_accuracy"] == 1.0
    # The honesty disclosure is load-bearing (AGENTIC_BALANCE): it must not silently regress.
    assert report["contract"]["read_only"] is True
    assert "world-truth" in report["contract"]["caveat"].lower()


def test_credulous_checker_flags_false_support():
    # Always says supported: precision collapses, false-support is total.
    verdicts = [_verdict(True) for _ in _CASES]
    report = build_grounding_correctness_report(_CASES, verdicts)

    # 2 of 4 verdicts are on genuinely-supported cases -> precision 0.5 here.
    assert report["support_precision"] == 0.5
    # Both non-entailed cases (1 contradicted + 1 unrelated) got a wrong SUPPORTED.
    assert report["false_support_rate"] == 1.0
    assert report["overall_accuracy"] == 0.5


def test_abstaining_checker_never_supports():
    verdicts = [_verdict(None) for _ in _CASES]
    report = build_grounding_correctness_report(_CASES, verdicts)

    assert report["abstention_rate"] == 1.0
    assert report["support_precision"] == 0.0  # no SUPPORTED verdicts at all
    assert report["false_support_rate"] == 0.0  # abstaining is not a false support
    assert report["overall_accuracy"] == 0.0


def test_confusion_matrix_and_per_case():
    verdicts = [_verdict(True), _verdict(None), _verdict(False), _verdict(True)]
    report = build_grounding_correctness_report(_CASES, verdicts)

    # 1 true_support of 2 supported cases -> recall 0.5 (the abstained s2 counts against it).
    assert report["support_recall"] == 0.5
    cm = report["confusion_matrix"]
    assert cm["supported->supported"] == 1  # s1 correct
    assert cm["supported->could_not_verify"] == 1  # s2 abstained
    assert cm["contradicted->not_supported"] == 1  # c1 correct reject
    assert cm["unrelated->supported"] == 1  # u1 false support
    cats = {c["case_id"]: c["category"] for c in report["cases"]}
    assert cats == {"s1": "true_support", "s2": "abstained", "c1": "correct_reject", "u1": "false_support"}


def test_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        build_grounding_correctness_report(_CASES, [_verdict(True)])


def test_load_grounding_cases_parses_and_validates():
    payload = [{"case_id": "a", "claim": "c", "evidence": "e", "label": "supported"}]
    cases = load_grounding_cases(payload)
    assert cases[0].case_id == "a" and cases[0].label == "supported"

    with pytest.raises(ValueError, match="must be a JSON array"):
        load_grounding_cases({"not": "a list"})
    with pytest.raises(ValueError, match="no grounding cases"):
        load_grounding_cases([])


async def test_run_eval_calls_checker_per_case():
    seen = []

    async def fake_checker(claim, evidence):
        seen.append((claim, evidence))
        return _verdict(True)

    report = await run_grounding_correctness_eval(_CASES, fake_checker)
    assert len(seen) == len(_CASES)
    assert report["case_count"] == len(_CASES)
