"""CLI-level test for `deepr eval grounding-correctness --benchmark-file`.

Exercises the benchmark-loading path end to end with a stub checker so it needs no
local Ollama model and makes no network or metered call.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.commands import eval_grounding_correctness as mod


class _StubVerdict:
    def __init__(self, supported: bool | None) -> None:
        self.supported = supported


def _stub_checker_factory(supported: bool | None):
    async def _check(_claim: str, _evidence: str) -> _StubVerdict:
        return _StubVerdict(supported)

    return _check


def test_grounding_correctness_scores_a_benchmark_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A stub checker that always says "supported" -> it is correct on PASS rows and
    # a false support on FAIL rows, which the report must reflect.
    monkeypatch.setattr(mod, "_build_checker", lambda *_a, **_k: (_stub_checker_factory(True), "stub-local"))

    bench = tmp_path / "halubench.jsonl"
    bench.write_text(
        '{"id": "a", "passage": "The sky is blue.", "answer": "The sky is blue.", "label": "PASS"}\n'
        '{"id": "b", "passage": "The sky is blue.", "answer": "The sky is red.", "label": "FAIL"}\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        mod.grounding_correctness,
        ["--benchmark-file", str(bench), "--benchmark-format", "halubench", "--json"],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["case_count"] == 2
    assert "halubench" in report["case_source"]
    # The report must name its checker: grounding quality varies by capacity path,
    # so an unlabelled number cannot be compared across runs or configurations.
    assert report["checker"] == "stub-local"
    # One PASS row (correctly supported), one FAIL row wrongly supported by the stub.
    assert report["false_support_rate"] == pytest.approx(1.0)


def test_grounding_correctness_rejects_unknown_benchmark_format(tmp_path: Path) -> None:
    bench = tmp_path / "x.jsonl"
    bench.write_text('{"passage": "p", "answer": "a", "label": "PASS"}\n', encoding="utf-8")
    result = CliRunner().invoke(
        mod.grounding_correctness,
        ["--benchmark-file", str(bench), "--benchmark-format", "nope"],
    )
    # click rejects an out-of-choice value before the command body runs.
    assert result.exit_code == 2
