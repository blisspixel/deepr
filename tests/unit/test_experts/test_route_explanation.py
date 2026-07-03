"""Tests for the deterministic, $0 route explanation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.route_explanation import (
    BACKEND_FALLBACK_ORDER,
    ROUTE_EXPLANATION_SCHEMA_VERSION,
    build_route_explanation,
)


def _expert(name: str, domain: str = "") -> SimpleNamespace:
    return SimpleNamespace(name=name, domain=domain, description="")


def _patch_experts(monkeypatch, experts):
    class _FakeStore:
        def list_all(self):
            return list(experts)

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", _FakeStore)


def test_build_route_explanation_shape_and_routing(monkeypatch, tmp_path):
    _patch_experts(
        monkeypatch,
        [
            _expert("Cloud Security Expert", domain="cloud security and iam"),
            _expert("Network Expert", domain="security and firewalls"),
            _expert("Baking Expert", domain="sourdough"),
        ],
    )
    # A missing admissions ledger -> empty (all-metered) capacity outlook, deterministic.
    payload = build_route_explanation("cloud security", max_experts=2, top_n=3, admissions_path=tmp_path / "none.jsonl")

    assert payload["schema_version"] == ROUTE_EXPLANATION_SCHEMA_VERSION
    assert payload["kind"] == "deepr.route.explanation"
    assert payload["contract"]["no_model_call"] is True
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["contract"]["routing_only"] is True
    assert payload["query"] == "cloud security"

    routing = payload["expert_routing"]
    assert routing["method"] == "keyword_overlap"
    assert routing["expert_count"] == 3
    assert routing["max_experts"] == 2
    # Top-2 by overlap are consulted; the zero-overlap baking expert is not.
    assert routing["would_consult"] == ["Cloud Security Expert", "Network Expert"]

    candidates = routing["candidates"]
    assert [c["name"] for c in candidates] == ["Cloud Security Expert", "Network Expert", "Baking Expert"]
    assert candidates[0]["overlap_score"] == 2
    assert set(candidates[0]["matched_terms"]) == {"cloud", "security"}
    assert candidates[0]["would_consult"] is True
    assert candidates[2]["overlap_score"] == 0
    assert candidates[2]["would_consult"] is False


def test_capacity_outlook_and_backend_order_present(monkeypatch, tmp_path):
    _patch_experts(monkeypatch, [_expert("A", domain="cloud")])
    payload = build_route_explanation("cloud", admissions_path=tmp_path / "none.jsonl")

    outlook = payload["capacity_outlook"]
    # Empty ledger -> nothing admitted -> next runs fall to metered.
    assert outlook["any_cheap_capacity_admitted"] is False
    assert payload["backend_fallback_order"] == list(BACKEND_FALLBACK_ORDER)


def test_no_experts_yields_empty_consult(monkeypatch, tmp_path):
    _patch_experts(monkeypatch, [])
    payload = build_route_explanation("anything", admissions_path=tmp_path / "none.jsonl")
    assert payload["expert_routing"]["would_consult"] == []
    assert payload["expert_routing"]["candidates"] == []
    assert payload["expert_routing"]["expert_count"] == 0


def test_invalid_bounds_raise(monkeypatch, tmp_path):
    _patch_experts(monkeypatch, [_expert("A")])
    with pytest.raises(ValueError, match="max_experts"):
        build_route_explanation("q", max_experts=0, admissions_path=tmp_path / "none.jsonl")
    with pytest.raises(ValueError, match="top_n"):
        build_route_explanation("q", top_n=0, admissions_path=tmp_path / "none.jsonl")
