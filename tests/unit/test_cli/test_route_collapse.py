"""Tests for `deepr route collapse`."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.main import cli


def _report(**over):
    base = {
        "schema_version": "deepr-route-collapse-v1",
        "kind": "deepr.route.collapse",
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "no_model_call": True,
            "routing_only": True,
            "quality_verdict": False,
            "routing_default_unchanged": True,
        },
        "automatic_consults": 2,
        "selection_events": 3,
        "unique_experts_selected": 2,
        "roster_size": 4,
        "unique_share": 0.5,
        "top1_share": 0.67,
        "top3_share": 1.0,
        "entropy_bits": 0.92,
        "max_entropy_bits": 1.0,
        "recency_fallback_known": 2,
        "recency_fallback_count": 1,
        "replayed": 2,
        "replay_disagreements": 0,
        "flagship_selection_share": 0.67,
        "flagship_is_label_only": True,
        "frequencies": [
            {"name": "Cloud Security Expert", "count": 2, "share": 0.67, "roster_tier": "flagship"},
            {"name": "weird[/]tag Expert", "count": 1, "share": 0.33, "roster_tier": "standard"},
        ],
        "note": "Routing-load report. Not a quality or authority verdict.",
    }
    base.update(over)
    return base


def test_route_collapse_help():
    result = CliRunner().invoke(cli, ["route", "collapse", "--help"])
    assert result.exit_code == 0
    assert "quality" in result.output.lower()


def test_route_collapse_renders_load_not_verdict(monkeypatch):
    monkeypatch.setattr("deepr.experts.consult_traces.load_consult_traces", lambda **kw: [])
    monkeypatch.setattr(
        "deepr.experts.fleet_collapse.build_route_collapse_report",
        lambda traces, **kw: _report(),
    )
    result = CliRunner().invoke(cli, ["route", "collapse"])

    assert result.exit_code == 0, result.output
    assert "Automatic consult collapse" in result.output
    assert "Cloud Security Expert" in result.output
    assert "weird[/]tag Expert" in result.output
    assert "Not a quality" in result.output
    assert "presentation label" in result.output


def test_route_collapse_json(monkeypatch):
    monkeypatch.setattr("deepr.experts.consult_traces.load_consult_traces", lambda **kw: [])
    monkeypatch.setattr(
        "deepr.experts.fleet_collapse.build_route_collapse_report",
        lambda traces, **kw: _report(),
    )
    result = CliRunner().invoke(cli, ["route", "collapse", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["kind"] == "deepr.route.collapse"
    assert payload["contract"]["quality_verdict"] is False


def test_route_collapse_empty_window(monkeypatch):
    monkeypatch.setattr("deepr.experts.consult_traces.load_consult_traces", lambda **kw: [])
    monkeypatch.setattr(
        "deepr.experts.fleet_collapse.build_route_collapse_report",
        lambda traces, **kw: _report(automatic_consults=0, frequencies=[]),
    )
    result = CliRunner().invoke(cli, ["route", "collapse"])
    assert result.exit_code == 0, result.output
    assert "No automatic consult traces" in result.output
