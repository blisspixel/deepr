"""Regression guard: every built-in skill YAML must parse and load.

SkillManager silently skips a malformed skill (it logs "Skipping malformed
skill" and continues), so a broken ``skill.yaml`` would otherwise ship
undetected - exactly what happened to primr's manifest (a ``: `` in an
unquoted description). This test loads all built-in skills and asserts the
first-party instruments are present with their expected tools.
"""

from __future__ import annotations

from deepr.experts.skills.manager import SkillManager


def test_first_party_skills_load() -> None:
    manager = SkillManager(expert_name="builtin-skill-test")
    names = {s.name for s in manager.list_all()}
    for required in ("recon", "distillr", "primr"):
        assert required in names, f"built-in skill {required!r} failed to load (malformed YAML?)"


def test_first_party_skills_expose_expected_tools() -> None:
    manager = SkillManager(expert_name="builtin-skill-test")

    distillr = manager.get_skill("distillr")
    assert distillr is not None
    assert {t.name for t in distillr.tools} >= {"find_insights", "papers", "catch_up"}

    primr = manager.get_skill("primr")
    assert primr is not None
    assert {t.name for t in primr.tools} >= {"estimate_run", "research_company", "estimate_strategy"}


def test_every_builtin_skill_tool_is_well_formed() -> None:
    # A skill that parsed but has empty tools or blank names indicates a
    # silently-degraded manifest.
    manager = SkillManager(expert_name="builtin-skill-test")
    for skill in manager.list_all():
        assert skill.tools, f"{skill.name} has no tools"
        for tool in skill.tools:
            assert tool.name, f"{skill.name} has a nameless tool"
