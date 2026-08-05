"""Diverse council plan composition and diversity gate."""

from __future__ import annotations

from deepr.experts.council_plan import (
    COUNCIL_PLAN_SCHEMA,
    DIVERSITY_AXES,
    build_scaffold_council_plan,
    validate_diversity,
)


def test_scaffold_covers_min_axes() -> None:
    plan = build_scaffold_council_plan(
        "NephMesh: intent-driven mesh and SDR when carrier fails",
        role_count=5,
    )
    assert plan.schema_version == COUNCIL_PLAN_SCHEMA
    assert plan.diversity_ok is True
    assert len(plan.axes_covered) >= 4
    assert len(plan.roles) >= 4
    assert "make" in plan.to_markdown().lower()
    assert "deepen-plan" in plan.to_markdown()
    assert plan.consult_prompt
    axes = {r["axis"] for r in plan.roles}
    assert axes <= {a["id"] for a in DIVERSITY_AXES}


def test_diversity_gate_rejects_single_axis_clones() -> None:
    roles = [
        {
            "name": f"Mesh Expert {i}",
            "domain_description": "mesh",
            "axis": "domain_practitioner",
            "perspective_lens": "x",
            "dissent_style": "y",
            "make_description": "mesh",
            "deepen_query": "mesh",
        }
        for i in range(5)
    ]
    ok, covered = validate_diversity(roles)
    assert ok is False
    assert covered == ["domain_practitioner"]


def test_scaffold_marks_existing_expert_when_name_overlaps() -> None:
    plan = build_scaffold_council_plan(
        "security for off-grid networks",
        role_count=4,
        existing_experts=["Adversary Red Team Analyst Extra"],
    )
    # template name is Adversary Red Team Analyst - substring match either way
    matched = [r for r in plan.roles if r.get("existing_expert")]
    assert matched
