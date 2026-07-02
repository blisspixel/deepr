"""Tests for structured expert dashboard telemetry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from deepr.core.contracts import Claim, ExpertManifest, Gap
from deepr.experts.beliefs import Belief, Edge
from deepr.experts.dashboard_telemetry import build_expert_dashboard_telemetry

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


class FakeProfile:
    name = "Platform Expert"

    def __init__(self, manifest: ExpertManifest):
        self._manifest = manifest

    def get_staleness_details(self):
        return {
            "is_stale": True,
            "freshness_status": "stale",
            "age_days": 45,
            "threshold_days": 30,
            "days_until_stale": 0,
            "domain_velocity": "fast",
            "urgency": "high",
            "urgency_score": 1.0,
            "estimated_refresh_cost": 1.0,
            "last_refresh": "2026-05-01T00:00:00+00:00",
            "knowledge_cutoff": "2026-05-05T00:00:00+00:00",
            "message": "Refresh needed",
            "action_required": "Refresh",
            "refresh_command": "deepr expert learn 'Platform Expert' --budget 1.00",
        }

    def get_manifest(self) -> ExpertManifest:
        return self._manifest


def test_dashboard_telemetry_summarizes_structured_state():
    open_gap = Gap.create(
        "Fresh open gap",
        priority=5,
        ev_cost_ratio=12.0,
        times_asked=3,
        identified_at=NOW - timedelta(days=3),
    )
    old_open_gap = Gap.create(
        "Old open gap",
        priority=2,
        ev_cost_ratio=1.0,
        identified_at=NOW - timedelta(days=90),
    )
    closed_gap = Gap.create(
        "Closed gap",
        identified_at=NOW - timedelta(days=20),
        filled=True,
        filled_at=NOW - timedelta(days=2),
    )
    old_closed_gap = Gap.create(
        "Old closed gap",
        identified_at=NOW - timedelta(days=90),
        filled=True,
        filled_at=NOW - timedelta(days=40),
    )
    contested_claim = Claim.create("A claim", "platform", 0.8, contradicts=["claim_b"])
    manifest = ExpertManifest(
        expert_name="Platform Expert",
        domain="platform",
        claims=[contested_claim, Claim.create("Stable claim", "platform", 0.9)],
        gaps=[old_open_gap, open_gap, closed_gap, old_closed_gap],
    )

    belief_a = Belief(
        id="belief_a",
        claim="A",
        confidence=0.7,
        domain="platform",
        contradictions_with=["belief_b"],
        updated_at=NOW - timedelta(hours=1),
    )
    belief_b = Belief(
        id="belief_b",
        claim="B",
        confidence=0.7,
        domain="platform",
        contradictions_with=["belief_a"],
        updated_at=NOW - timedelta(hours=2),
    )
    edge = Edge(src_id="belief_c", dst_id="belief_d", edge_type="contradicts")
    belief_store = SimpleNamespace(beliefs={"belief_a": belief_a, "belief_b": belief_b}, edges={edge.key(): edge})

    telemetry = build_expert_dashboard_telemetry(FakeProfile(manifest), belief_store=belief_store, now=NOW)

    assert telemetry["freshness"]["status"] == "stale"
    assert telemetry["freshness"]["urgency"] == "high"
    assert telemetry["gaps"]["total"] == 4
    assert telemetry["gaps"]["open"] == 2
    assert telemetry["gaps"]["closed"] == 2
    assert telemetry["gaps"]["opened_last_7_days"] == 1
    assert telemetry["gaps"]["closed_last_7_days"] == 1
    assert telemetry["gaps"]["opened_last_30_days"] == 2
    assert telemetry["gaps"]["closed_last_30_days"] == 1
    assert telemetry["gaps"]["net_open_delta_30_days"] == 1
    assert telemetry["gaps"]["top_open"][0]["topic"] == "Fresh open gap"
    assert telemetry["contested_claims"]["manifest_claim_count"] == 1
    assert telemetry["contested_claims"]["belief_count"] == 2
    assert telemetry["contested_claims"]["contradiction_edge_count"] == 1
    assert telemetry["contested_claims"]["open_count"] == 5
    assert telemetry["contested_claims"]["sample"][0]["id"] == "belief_a"
