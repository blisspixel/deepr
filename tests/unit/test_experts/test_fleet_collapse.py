"""$0 automatic-consult collapse telemetry: load, not quality."""

from __future__ import annotations

from types import SimpleNamespace

from deepr.experts.fleet_collapse import (
    ROUTE_COLLAPSE_KIND,
    ROUTE_COLLAPSE_SCHEMA_VERSION,
    build_route_collapse_report,
    observe_automatic_routing,
    shannon_entropy,
)


def _expert(name: str, domain: str = "", *, flagship: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        domain=domain,
        description="",
        roster_tier="flagship" if flagship else "standard",
    )


def _automatic(question: str, selected: list[str], *, recency: bool | None = None, max_experts: int = 3) -> dict:
    routing = None
    if recency is not None:
        routing = {"method": "keyword_overlap", "recency_fallback": recency, "scores": []}
    return {
        "kind": "deepr.expert.consult_trace",
        "input": {
            "question": question,
            "selection_mode": "automatic",
            "max_experts": max_experts,
            "requested_max_experts": max_experts,
            **({"routing": routing} if routing is not None else {}),
        },
        "context_packet": {"always": {"experts_consulted": selected}},
        "output": {"experts_consulted": selected},
    }


def test_shannon_entropy_uniform_and_collapsed():
    assert shannon_entropy({"a": 1, "b": 1}) == 1.0
    assert shannon_entropy({"a": 8}) == 0.0
    assert shannon_entropy({}) == 0.0


def test_observe_marks_recency_fallback_when_nothing_overlaps():
    snapshot = observe_automatic_routing(
        "unrelated query about pastry",
        selected=["Cloud Security Expert"],
        max_experts=3,
        experts=[_expert("Cloud Security Expert", "cloud security")],
    )
    assert snapshot["method"] == "keyword_overlap"
    assert snapshot["recency_fallback"] is True
    assert snapshot["scores"][0]["selected"] is True
    assert snapshot["scores"][0]["overlap_score"] == 0


def test_observe_records_overlap_when_domain_matches():
    snapshot = observe_automatic_routing(
        "cloud security",
        selected=["Cloud Security Expert"],
        max_experts=2,
        experts=[
            _expert("Cloud Security Expert", "cloud security"),
            _expert("Baking Expert", "sourdough"),
        ],
    )
    assert snapshot["recency_fallback"] is False
    by_name = {row["name"]: row for row in snapshot["scores"]}
    assert by_name["Cloud Security Expert"]["overlap_score"] == 2
    assert by_name["Cloud Security Expert"]["selected"] is True
    assert by_name["Baking Expert"]["selected"] is False


def test_collapse_report_ignores_explicit_rosters_and_labels_flagship():
    traces = [
        {
            "input": {"selection_mode": "explicit", "question": "cloud"},
            "context_packet": {"always": {"experts_consulted": ["Should Ignore"]}},
        },
        _automatic("cloud security", ["Cloud Security Expert"], recency=False),
        _automatic("cloud security", ["Cloud Security Expert", "Network Expert"], recency=False),
        _automatic("pastry", ["Cloud Security Expert"], recency=True),
    ]
    roster = [
        _expert("Cloud Security Expert", "cloud security", flagship=True),
        _expert("Network Expert", "security"),
        _expert("Baking Expert", "sourdough"),
    ]
    report = build_route_collapse_report(traces, roster=roster, replay=False)

    assert report["schema_version"] == ROUTE_COLLAPSE_SCHEMA_VERSION
    assert report["kind"] == ROUTE_COLLAPSE_KIND
    assert report["contract"]["quality_verdict"] is False
    assert report["contract"]["routing_default_unchanged"] is True
    assert report["automatic_consults"] == 3
    assert report["unique_experts_selected"] == 2
    assert report["roster_size"] == 3
    assert report["frequencies"][0]["name"] == "Cloud Security Expert"
    assert report["frequencies"][0]["count"] == 3
    assert report["frequencies"][0]["roster_tier"] == "flagship"
    assert report["flagship_is_label_only"] is True
    assert report["recency_fallback_count"] == 1
    assert report["recency_fallback_known"] == 3
    assert "not a quality" in report["note"]


def test_collapse_replay_disagrees_when_current_router_would_pick_differently():
    traces = [_automatic("cloud security", ["Baking Expert"], max_experts=1)]
    roster = [
        _expert("Cloud Security Expert", "cloud security"),
        _expert("Baking Expert", "sourdough"),
    ]
    report = build_route_collapse_report(traces, roster=roster, replay=True)
    assert report["replayed"] == 1
    assert report["replay_disagreements"] == 1


def test_empty_automatic_window_is_honest():
    report = build_route_collapse_report([], roster=[], replay=False)
    assert report["automatic_consults"] == 0
    assert report["frequencies"] == []
    assert report["top1_share"] == 0.0
