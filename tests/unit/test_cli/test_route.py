"""Tests for `deepr route explain`."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.main import cli


def _payload(**over):
    base = {
        "schema_version": "deepr-route-explanation-v1",
        "kind": "deepr.route.explanation",
        "contract": {"read_only": True, "cost_usd": 0.0, "no_model_call": True, "routing_only": True},
        "query": "q",
        "expert_routing": {
            "method": "keyword_overlap",
            "note": "router only",
            "expert_count": 2,
            "max_experts": 3,
            "would_consult": ["Cloud Security Expert"],
            "candidates": [
                {
                    "name": "Cloud Security Expert",
                    "domain": "cloud security",
                    "overlap_score": 2,
                    "matched_terms": ["cloud", "security"],
                    "would_consult": True,
                },
                {
                    "name": "weird[/]tag Expert",
                    "domain": "",
                    "overlap_score": 0,
                    "matched_terms": [],
                    "would_consult": False,
                },
            ],
        },
        "capacity_outlook": {"task_classes": {}, "any_cheap_capacity_admitted": False},
        "backend_fallback_order": ["local ($0)", "plan-quota (prepaid)", "metered API"],
    }
    base.update(over)
    return base


def test_route_explain_help():
    result = CliRunner().invoke(cli, ["route", "explain", "--help"])
    assert result.exit_code == 0
    assert "route" in result.output.lower()


def test_route_explain_renders_routing(monkeypatch):
    monkeypatch.setattr(
        "deepr.experts.route_explanation.build_route_explanation",
        lambda query, **kw: _payload(query=query),
    )
    result = CliRunner().invoke(cli, ["route", "explain", "cloud security"])

    assert result.exit_code == 0, result.output
    assert "Route explanation" in result.output
    assert "Would consult" in result.output
    assert "Cloud Security Expert" in result.output
    # matched terms rendered
    assert "cloud, security" in result.output
    # operator-controlled name with markup chars is escaped, shown literally
    assert "weird[/]tag Expert" in result.output


def test_route_explain_json_emits_schema(monkeypatch):
    monkeypatch.setattr(
        "deepr.experts.route_explanation.build_route_explanation",
        lambda query, **kw: _payload(query=query),
    )
    result = CliRunner().invoke(cli, ["route", "explain", "cloud", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-route-explanation-v1"
    assert payload["contract"]["no_model_call"] is True


def test_route_explain_escapes_markup_in_query(monkeypatch):
    # The query is operator input rendered into a markup-enabled header; a bracketed
    # query must not crash or be swallowed as Rich markup.
    monkeypatch.setattr(
        "deepr.experts.route_explanation.build_route_explanation",
        lambda query, **kw: _payload(query=query),
    )
    result = CliRunner().invoke(cli, ["route", "explain", "parse [json] and weird[/]tag"])

    assert result.exit_code == 0, result.output
    assert "parse [json] and weird[/]tag" in result.output
