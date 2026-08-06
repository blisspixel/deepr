"""Deepen plan recipe tests ($0, no network)."""

from __future__ import annotations

from deepr.experts.deepen_plan import DEEPEN_PLAN_SCHEMA, build_deepen_plan


def test_build_deepen_plan_emits_distill_no_metered_and_absorb() -> None:
    plan = build_deepen_plan(
        expert_name="Meshtastic LoRa Mesh Automation",
        domain="Meshtastic LoRa mesh",
        query="Meshtastic meshtasticd MQTT",
    )
    assert plan.schema_version == DEEPEN_PLAN_SCHEMA
    assert plan.topic_slug
    assert plan.cost_usd == 0.0
    commands = " ".join(step.get("command") or "" for step in plan.steps)
    assert "distill --cost-mode no-metered" in commands
    assert "deepr expert absorb" in commands
    assert "--trust-class secondary" in commands
    md = plan.to_markdown()
    assert "Deepen plan:" in md
    assert "Capacity" in md
