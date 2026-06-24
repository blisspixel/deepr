"""Tests for per-expert SKILL.md export (deepr.skills.expert_skill)."""

from __future__ import annotations

import pytest

from deepr.skills.expert_skill import build_expert_skill, expert_slug


class TestExpertSlug:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("AI Strategy Expert", "ai-strategy-expert"),
            ("FDA Regulations!", "fda-regulations"),
            ("  Spaces  ", "spaces"),
            ("***", "expert"),  # degenerate -> safe fallback
            ("Azure/Architect", "azure-architect"),
        ],
    )
    def test_slug(self, name, expected):
        assert expert_slug(name) == expected


class TestBuildExpertSkill:
    def test_frontmatter_and_name(self):
        md = build_expert_skill("AI Strategy Expert", "AI market strategy", "desc").render()
        assert "name: deepr-expert-ai-strategy-expert" in md
        assert "mcp_server: deepr" in md
        # agentskills.io requires name + description frontmatter keys
        assert "description:" in md
        assert "AI Strategy Expert" in md

    def test_includes_expert_scoped_tools(self):
        md = build_expert_skill("AI Strategy Expert").render()
        for tool in (
            "deepr_query_expert",
            "deepr_expert_validate",
            "deepr_rank_gaps",
            "deepr_expert_health_check",
        ):
            assert tool in md

    def test_expert_name_pinned_in_tool_params(self):
        # The skill must tell the host agent to pass this exact expert_name.
        md = build_expert_skill("AI Strategy Expert").render()
        assert 'Always "AI Strategy Expert"' in md

    def test_triggers_include_domain_and_name_words(self):
        pkg = build_expert_skill("Security Specialist", "cloud security posture")
        md = pkg.render()
        assert "## Triggers" in md
        # domain + name words should surface as triggers
        for word in ("security", "specialist", "cloud", "posture"):
            assert word in md.lower()

    def test_instructions_reference_consultation_flow(self):
        md = build_expert_skill("AI Strategy Expert", "AI").render()
        assert "deepr_query_expert" in md
        assert "PASS/WARN/FAIL" in md
        # Should frame the expert as a role to prefer over priors, and note the
        # MCP-server requirement.
        assert "MCP" in md

    def test_description_is_trigger_style(self):
        # The frontmatter description should name when to invoke, not summarize.
        md = build_expert_skill("AI Strategy Expert", "AI market strategy").render()
        assert "Use it when" in md

    def test_includes_gotchas_section_with_real_failure_modes(self):
        md = build_expert_skill("AI Strategy Expert", "AI").render()
        assert "## Gotchas" in md
        # PASS is not ground truth; confidence is capped; staleness is real.
        assert "do not treat PASS as proof" in md
        assert "trust-floor-capped" in md
        assert "deepr_what_changed" in md
        assert "EXPERT_NOT_FOUND" in md

    def test_no_domain_no_description_still_valid(self):
        md = build_expert_skill("Bare Expert").render()
        assert "name: deepr-expert-bare-expert" in md
        assert "Bare Expert" in md
        assert "## Gotchas" in md  # gotchas are always emitted

    def test_generate_writes_file(self, tmp_path):
        pkg = build_expert_skill("AI Strategy Expert", "AI")
        path = pkg.generate(tmp_path / "skill")
        assert path.exists()
        assert path.name == "SKILL.md"
        assert "deepr-expert-ai-strategy-expert" in path.read_text(encoding="utf-8")
