"""Tests for `deepr expert consult` - the first-class team-consultation verb.

The council itself is tested elsewhere; here we exercise the command layer
(artifact shaping, --json, exit codes, arg passing) with the council monkeypatched
so tests stay pure and $0.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

import deepr.cli.commands.semantic.expert_consult as mod
from deepr.cli.commands.semantic.expert_consult import build_consult_payload, expert_consult


def _result(**over):
    base = {
        "query": "q",
        "perspectives": [
            {"expert_name": "A", "domain": "alpha", "response": "answer from A", "confidence": 0.9, "cost": 0.01},
            {"expert_name": "B", "domain": "beta", "response": "answer from B", "confidence": 0.8, "cost": 0.01},
        ],
        "synthesis": "the synthesized answer",
        "agreements": ["both agree X"],
        "disagreements": ["they differ on Y"],
        "total_cost": 0.0123,
    }
    base.update(over)
    return base


def _patch(monkeypatch, result):
    async def fake(question, experts, max_experts, budget):
        return result

    monkeypatch.setattr(mod, "run_consult", fake)


def test_consult_registered_on_expert_group():
    from deepr.cli.commands.semantic.experts import expert

    assert "consult" in expert.commands


def test_build_payload_shape():
    p = build_consult_payload("q", _result())
    assert p["schema_version"] == "deepr-consult-v1"
    assert p["kind"] == "deepr.expert.consult"
    assert p["answer"] == "the synthesized answer"
    assert p["experts_consulted"] == ["A", "B"]
    assert p["perspectives"][0]["confidence"] == 0.9
    assert p["agreements"] == ["both agree X"]
    assert p["cost_usd"] == 0.0123


def test_consult_json_emits_versioned_artifact(monkeypatch):
    _patch(monkeypatch, _result())
    result = CliRunner().invoke(expert_consult, ["q", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["schema_version"] == "deepr-consult-v1"
    assert parsed["answer"] == "the synthesized answer"
    assert parsed["cost_usd"] == 0.0123


def test_consult_human_render(monkeypatch):
    _patch(monkeypatch, _result())
    result = CliRunner().invoke(expert_consult, ["q", "-y"])
    assert result.exit_code == 0
    assert "Synthesis" in result.output
    assert "the synthesized answer" in result.output
    assert "Disagreements" in result.output


def test_consult_no_experts_exits_2(monkeypatch):
    _patch(monkeypatch, _result(perspectives=[], synthesis="No experts available for this query."))
    result = CliRunner().invoke(expert_consult, ["q", "-y"])
    assert result.exit_code == 2


def test_budget_must_be_positive():
    result = CliRunner().invoke(expert_consult, ["q", "--budget", "0", "-y"])
    assert result.exit_code == 2


def test_failure_surfaced_not_silent(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("council down")

    monkeypatch.setattr(mod, "run_consult", boom)
    result = CliRunner().invoke(expert_consult, ["q", "-y"])
    assert result.exit_code == 1
    assert "Consultation failed" in result.output


def test_explicit_experts_and_budget_passed_through(monkeypatch):
    captured = {}

    async def fake(question, experts, max_experts, budget):
        captured["experts"] = experts
        captured["budget"] = budget
        return _result()

    monkeypatch.setattr(mod, "run_consult", fake)
    result = CliRunner().invoke(expert_consult, ["q", "-e", "A", "-e", "B", "-b", "1.5", "--json"])
    assert result.exit_code == 0
    assert captured["experts"] == ["A", "B"]
    assert captured["budget"] == 1.5
