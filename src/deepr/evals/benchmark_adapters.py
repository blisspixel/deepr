"""Adapters that map public grounding/hallucination benchmarks onto the
grounding-correctness ``GroundingCase`` contract.

This is the "proof by benchmark" seam: ``deepr eval grounding-correctness`` can
score Deepr's grounding checker against externally comparable ground truth (a
published, third-party-labeled benchmark) instead of only the built-in curated
set. Agreement on a curated 50-case set says the checker is not obviously broken;
agreement on a standard benchmark is what lets a number be compared to the field.

AGENTIC_BALANCE: everything here is deterministic field/label reshaping (form).
The ground-truth labels are the benchmark authors' human judgments; nothing in
this module judges meaning. The datasets are intentionally NOT vendored (they are
large and separately licensed); the operator supplies a local file, and the eval
report discloses the source and case count so a number is never over-read.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from deepr.evals.grounding_correctness import GroundingCase

# HaluBench (PatronusAI/HaluBench) uses PASS for a faithful answer and FAIL for a
# hallucinated one. FAIL maps to a generic not-entailed label ("unrelated")
# because the benchmark does not separate contradiction from fabrication, and the
# grounding-correctness scorer treats every non-"supported" label identically -- a
# SUPPORTED verdict on any of them is the same false support.
_HALUBENCH_FAITHFUL = "PASS"
_HALUBENCH_HALLUCINATED = "FAIL"

BenchmarkAdapter = Callable[[Iterable[Mapping[str, Any]]], list[GroundingCase]]


def adapt_halubench(rows: Iterable[Mapping[str, Any]]) -> list[GroundingCase]:
    """Map HaluBench rows onto grounding cases.

    Each row carries a ``passage`` (the grounding source), a ``question``, an
    ``answer`` (the statement whose grounding is judged), and a binary ``label``
    (``PASS``/``FAIL``). We check answer-against-passage entailment and drop the
    question; that is the faithfulness core the grounding checker actually decides.
    """
    cases: list[GroundingCase] = []
    for i, row in enumerate(rows):
        raw_label = str(row.get("label", "")).strip().upper()
        if raw_label not in (_HALUBENCH_FAITHFUL, _HALUBENCH_HALLUCINATED):
            raise ValueError(
                f"HaluBench row #{i} has label {row.get('label')!r}; expected {_HALUBENCH_FAITHFUL!r} or {_HALUBENCH_HALLUCINATED!r}"
            )
        answer = str(row.get("answer", "")).strip()
        passage = str(row.get("passage", "")).strip()
        if not answer or not passage:
            raise ValueError(f"HaluBench row #{i} needs a non-empty 'answer' and 'passage'")
        label = "supported" if raw_label == _HALUBENCH_FAITHFUL else "unrelated"
        case_id = f"halubench-{row.get('id', i)}"
        cases.append(GroundingCase(case_id=case_id, claim=answer, evidence=passage, label=label))
    if not cases:
        raise ValueError("no HaluBench rows supplied")
    return cases


# Registry of known benchmark formats. Add new adapters here as they are written;
# the CLI's --benchmark-format choices are derived from these keys.
BENCHMARK_ADAPTERS: dict[str, BenchmarkAdapter] = {
    "halubench": adapt_halubench,
}


def _read_rows(path: Path) -> list[Mapping[str, Any]]:
    """Read a benchmark file as either a JSON array or JSON Lines."""
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("a JSON benchmark file must contain an array of row objects")
        rows = data
    else:
        rows = []
        for line_no, line in enumerate(text.splitlines(), 1):
            candidate = line.strip()
            if not candidate:
                continue
            try:
                rows.append(json.loads(candidate))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_no}: {exc}") from exc
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"benchmark row #{i} must be a JSON object")
    return rows


def load_benchmark_cases(path: Path, benchmark_format: str) -> list[GroundingCase]:
    """Load a benchmark file and adapt it to grounding cases.

    Raises ``ValueError`` for an unknown format or a malformed file so the caller
    can surface a clean error rather than a stack trace.
    """
    adapter = BENCHMARK_ADAPTERS.get(benchmark_format)
    if adapter is None:
        known = ", ".join(sorted(BENCHMARK_ADAPTERS))
        raise ValueError(f"unknown benchmark format {benchmark_format!r}; known formats: {known}")
    return adapter(_read_rows(path))
