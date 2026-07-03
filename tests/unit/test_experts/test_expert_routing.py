"""Tests for the deterministic keyword-overlap expert router."""

from __future__ import annotations

from types import SimpleNamespace

from deepr.experts.expert_routing import (
    MAX_ROUTED_EXPERTS,
    ExpertRouteScore,
    route_terms,
    score_experts_for_query,
    select_top_experts,
)


def _expert(name: str, domain: str = "", description: str = "") -> SimpleNamespace:
    return SimpleNamespace(name=name, domain=domain, description=description)


def test_route_terms_drops_stopwords_and_short_tokens():
    terms = route_terms("What is the cloud security model")
    # stopwords (what/is/the) and <=2-char tokens are dropped; content words kept.
    assert "cloud" in terms
    assert "security" in terms
    assert "model" in terms
    assert "the" not in terms
    assert "is" not in terms


def test_route_terms_stems_plurals_and_agentic():
    terms = route_terms("agentic pipelines")
    # plural stem for len>4, and the agentic->agent alias.
    assert "pipelines" in terms and "pipeline" in terms
    assert "agentic" in terms and "agent" in terms


def test_score_ranks_by_overlap_descending_with_matched_terms():
    experts = [
        _expert("Cloud Security Expert", domain="cloud security and iam"),
        _expert("Baking Expert", domain="sourdough and pastry"),
        _expert("Network Security Expert", domain="security and firewalls"),
    ]
    scored = score_experts_for_query("cloud security", experts)

    assert [s.name for s in scored] == [
        "Cloud Security Expert",
        "Network Security Expert",
        "Baking Expert",
    ]
    assert scored[0].score == 2 and set(scored[0].matched_terms) == {"cloud", "security"}
    assert scored[1].score == 1 and scored[1].matched_terms == ("security",)
    assert scored[2].score == 0 and scored[2].matched_terms == ()
    assert isinstance(scored[0], ExpertRouteScore)


def test_score_excludes_named_experts():
    experts = [_expert("A", domain="cloud"), _expert("B", domain="cloud")]
    scored = score_experts_for_query("cloud", experts, exclude={"A"})
    assert [s.name for s in scored] == ["B"]


def test_select_top_prefers_overlap_then_caps():
    scored = [
        ExpertRouteScore("A", "", 2, ("x", "y")),
        ExpertRouteScore("B", "", 1, ("x",)),
        ExpertRouteScore("C", "", 0, ()),
    ]
    chosen = select_top_experts(scored, max_experts=5)
    # Only the two with overlap are chosen (zero-overlap C excluded), capped by max.
    assert [c["name"] for c in chosen] == ["A", "B"]


def test_select_top_falls_back_when_no_overlap():
    scored = [ExpertRouteScore("A", "", 0, ()), ExpertRouteScore("B", "", 0, ())]
    chosen = select_top_experts(scored, max_experts=1)
    # No overlap anywhere: fall back to the top scorer so consult is never starved.
    assert [c["name"] for c in chosen] == ["A"]


def test_select_top_respects_global_cap():
    scored = [ExpertRouteScore(f"E{i}", "", 1, ("x",)) for i in range(20)]
    chosen = select_top_experts(scored, max_experts=99)
    assert len(chosen) == MAX_ROUTED_EXPERTS
