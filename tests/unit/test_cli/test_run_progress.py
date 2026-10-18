"""Regressions for silent long local runs (ROADMAP live finding 2026-07-12)."""

from __future__ import annotations

import io
import json
import threading
import time

import pytest
from click.testing import CliRunner

import deepr.cli.commands.semantic.expert_consult as consult_mod
from deepr.cli.run_progress import format_elapsed, run_progress


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0s"), (45.9, "45s"), (125, "2m 05s"), (3720, "1h 02m"), (-3, "0s")],
)
def test_format_elapsed(seconds, expected):
    assert format_elapsed(seconds) == expected


def test_short_run_prints_nothing():
    stream = io.StringIO()
    with run_progress("Consult", interval=60, stream=stream):
        pass
    assert stream.getvalue() == ""


def test_long_run_reports_phase_elapsed_trace_and_cancel_hint():
    stream = io.StringIO()
    clock = _Clock()
    beat = threading.Event()

    class Stream(io.StringIO):
        def write(self, text):
            beat.set()
            return stream.write(text)

    with run_progress("Sync", phase="syncing due topics", interval=0.01, stream=Stream(), clock=clock) as progress:
        clock.now += 150
        progress.set_trace("run_abc")
        progress.set_phase("waiting for model generation")
        assert beat.wait(2)
    lines = stream.getvalue().splitlines()
    assert lines[0] == "Sync: waiting for model generation, 2m 30s elapsed; trace run_abc. Ctrl+C cancels."
    assert lines[-1] == "Sync: finished after 2m 30s; trace run_abc."


def test_interrupt_reports_cancellation_even_when_short():
    stream = io.StringIO()
    clock = _Clock()
    with pytest.raises(KeyboardInterrupt):
        with run_progress("Absorb", trace="t1", interval=60, stream=stream, clock=clock):
            clock.now += 7
            raise KeyboardInterrupt
    assert stream.getvalue() == "Absorb: cancelled after 7s; trace t1.\n"


def test_fast_failure_is_silent_and_long_failure_reports_stop():
    stream = io.StringIO()
    with pytest.raises(RuntimeError):
        with run_progress("Consult", interval=60, stream=stream, clock=_Clock()):
            raise RuntimeError("refused before dispatch")
    assert stream.getvalue() == ""
    long_stream = io.StringIO()
    with pytest.raises(RuntimeError):
        with run_progress("Consult", interval=0.01, stream=long_stream):
            time.sleep(0.05)
            raise RuntimeError("model call failed")
    assert long_stream.getvalue().splitlines()[-1].startswith("Consult: stopped after ")


def test_disabled_is_silent():
    quiet = io.StringIO()
    with pytest.raises(KeyboardInterrupt):
        with run_progress("Consult", enabled=False, interval=0.001, stream=quiet):
            time.sleep(0.02)
            raise KeyboardInterrupt
    assert quiet.getvalue() == ""


def test_slow_consult_reports_progress_on_stderr_and_keeps_json_stdout(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(tmp_path / "consult_traces.jsonl"))

    async def resolve_local_model():
        return "fixture-local"

    monkeypatch.setattr("deepr.backends.local.default_local_model_async", resolve_local_model)
    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: object())
    monkeypatch.setattr("deepr.cli.run_progress.DEFAULT_INTERVAL_SECONDS", 0.02)

    async def slow(question, experts, max_experts, budget, **_kwargs):
        import asyncio

        await asyncio.sleep(0.2)
        return {
            "query": question,
            "perspectives": [{"expert_name": "A", "domain": "a", "response": "r", "confidence": 0.9, "cost": 0.0}],
            "synthesis": "answer",
            "agreements": [],
            "disagreements": [],
            "total_cost": 0.0,
        }

    monkeypatch.setattr(consult_mod, "run_consult", slow)
    result = CliRunner().invoke(consult_mod.expert_consult, ["q", "--json"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.stdout)
    trace_id = parsed["trace"]["trace_id"]
    beats = [line for line in result.stderr.splitlines() if line.startswith("Consult: ")]
    assert any("waiting for model generation" in line and "Ctrl+C cancels." in line for line in beats)
    assert any(f"trace {trace_id}" in line for line in beats)
    assert beats[-1].startswith("Consult: finished after ")
