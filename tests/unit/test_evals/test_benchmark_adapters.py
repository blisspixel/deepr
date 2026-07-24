"""Tests for the public-benchmark adapters used by proof-by-benchmark grounding.

These use small synthetic fixtures in each benchmark's native shape; the real
datasets are large and separately licensed and are never vendored or downloaded.
"""

import json
from pathlib import Path

import pytest

from deepr.evals.benchmark_adapters import (
    BENCHMARK_ADAPTERS,
    adapt_halubench,
    load_benchmark_cases,
)


def test_adapt_halubench_maps_pass_and_fail_to_entailment_labels() -> None:
    rows = [
        {
            "id": "q1",
            "passage": "The Eiffel Tower is in Paris.",
            "question": "Where is it?",
            "answer": "It is in Paris.",
            "label": "PASS",
        },
        {
            "id": "q2",
            "passage": "The Eiffel Tower is in Paris.",
            "question": "Where is it?",
            "answer": "It is in Berlin.",
            "label": "FAIL",
        },
    ]

    cases = adapt_halubench(rows)

    assert [c.label for c in cases] == ["supported", "unrelated"]
    # The answer is the claim to check; the passage is the grounding evidence.
    assert cases[0].claim == "It is in Paris."
    assert cases[0].evidence == "The Eiffel Tower is in Paris."
    assert cases[0].case_id == "halubench-q1"
    assert cases[1].case_id == "halubench-q2"


def test_adapt_halubench_is_case_insensitive_on_label() -> None:
    cases = adapt_halubench([{"passage": "p", "answer": "a", "label": "pass"}])
    assert cases[0].label == "supported"


def test_adapt_halubench_rejects_unknown_label() -> None:
    with pytest.raises(ValueError, match="expected"):
        adapt_halubench([{"passage": "p", "answer": "a", "label": "MAYBE"}])


def test_adapt_halubench_rejects_empty_fields() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        adapt_halubench([{"passage": "", "answer": "a", "label": "PASS"}])


def test_adapt_halubench_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="no HaluBench rows"):
        adapt_halubench([])


def test_load_benchmark_cases_reads_json_lines(tmp_path: Path) -> None:
    path = tmp_path / "halu.jsonl"
    path.write_text(
        '{"id": "a", "passage": "Sky is blue.", "answer": "The sky is blue.", "label": "PASS"}\n'
        "\n"  # blank lines are skipped
        '{"id": "b", "passage": "Sky is blue.", "answer": "The sky is green.", "label": "FAIL"}\n',
        encoding="utf-8",
    )

    cases = load_benchmark_cases(path, "halubench")

    assert len(cases) == 2
    assert cases[0].label == "supported"
    assert cases[1].label == "unrelated"


def test_load_benchmark_cases_reads_json_array(tmp_path: Path) -> None:
    path = tmp_path / "halu.json"
    path.write_text(
        json.dumps([{"id": "a", "passage": "p", "answer": "a", "label": "FAIL"}]),
        encoding="utf-8",
    )

    cases = load_benchmark_cases(path, "halubench")

    assert len(cases) == 1
    assert cases[0].label == "unrelated"


def test_load_benchmark_cases_rejects_unknown_format(tmp_path: Path) -> None:
    path = tmp_path / "x.jsonl"
    path.write_text('{"passage": "p", "answer": "a", "label": "PASS"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown benchmark format"):
        load_benchmark_cases(path, "nope")


def test_load_benchmark_cases_reports_bad_json_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"passage": "p", "answer": "a", "label": "PASS"}\n{not json}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        load_benchmark_cases(path, "halubench")


def test_halubench_registered() -> None:
    assert "halubench" in BENCHMARK_ADAPTERS
