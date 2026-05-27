"""Unit tests for SKILL.md packager.

Tests generated SKILL.md contains all required frontmatter fields,
all public tools appear in tools list, and trigger patterns include
research keywords.

Feature: mcp-client-agent-interop
Requirements: 13.1, 13.2, 13.3
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deepr import __version__ as DEEPR_VERSION
from deepr.skills.packager import SkillPackager
from deepr.skills.templates import DEFAULT_TRIGGERS, ToolManifest

# --- Fixtures ---


@pytest.fixture()
def sample_tools() -> list[ToolManifest]:
    """Sample tools for testing."""
    return [
        ToolManifest(
            name="domain_lookup",
            description="Look up DNS records for a domain",
            parameters={
                "properties": {
                    "domain": {"type": "string", "description": "Domain to look up"},
                }
            },
            server_name="recon",
        ),
        ToolManifest(
            name="research_topic",
            description="Research a topic with budget control",
            parameters={
                "properties": {
                    "topic": {"type": "string", "description": "Research topic"},
                    "budget": {"type": "number", "description": "Budget limit"},
                }
            },
            server_name="deepr",
        ),
    ]


@pytest.fixture()
def packager(sample_tools: list[ToolManifest]) -> SkillPackager:
    """Packager with sample tools."""
    p = SkillPackager(
        name="deepr-research",
        description="Multi-provider research automation",
        version=DEEPR_VERSION,
        mcp_server="deepr",
    )
    p.add_tools(sample_tools)
    return p


# --- Frontmatter tests ---


class TestFrontmatter:
    """Test generated SKILL.md contains all required frontmatter fields."""

    def test_name_in_frontmatter(self, packager: SkillPackager) -> None:
        """Frontmatter contains name field."""
        content = packager.render()
        assert "name: deepr-research" in content

    def test_description_in_frontmatter(self, packager: SkillPackager) -> None:
        """Frontmatter contains description field."""
        content = packager.render()
        assert "description: Multi-provider research automation" in content

    def test_version_in_frontmatter(self, packager: SkillPackager) -> None:
        """Frontmatter contains version field."""
        content = packager.render()
        assert f"version: {DEEPR_VERSION}" in content

    def test_mcp_server_in_frontmatter(self, packager: SkillPackager) -> None:
        """Frontmatter contains mcp_server field."""
        content = packager.render()
        assert "mcp_server: deepr" in content

    def test_frontmatter_delimiters(self, packager: SkillPackager) -> None:
        """Frontmatter is wrapped in --- delimiters."""
        content = packager.render()
        assert content.strip().startswith("---")
        # Second --- closes frontmatter
        lines = content.strip().split("\n")
        assert lines[0] == "---"
        # Find closing ---
        closing_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                closing_idx = i
                break
        assert closing_idx is not None


# --- Tools list tests ---


class TestToolsList:
    """Test all public tools appear in tools list."""

    def test_all_tools_present(self, packager: SkillPackager, sample_tools: list[ToolManifest]) -> None:
        """All registered tools appear in rendered output."""
        content = packager.render()
        for tool in sample_tools:
            assert tool.name in content
            assert tool.description in content

    def test_tool_parameters_shown(self, packager: SkillPackager) -> None:
        """Tool parameters are included in output."""
        content = packager.render()
        assert "domain" in content
        assert "topic" in content
        assert "budget" in content

    def test_get_tools_manifest(self, packager: SkillPackager, sample_tools: list[ToolManifest]) -> None:
        """get_tools_manifest returns all registered tools."""
        manifest = packager.get_tools_manifest()
        assert len(manifest) == len(sample_tools)
        names = [t.name for t in manifest]
        assert "domain_lookup" in names
        assert "research_topic" in names

    def test_empty_tools_handled(self) -> None:
        """Packager with no tools renders without error."""
        p = SkillPackager(name="empty", version="1.0.0")
        content = p.render()
        assert "## Tools" in content

    def test_add_tool_increments(self, packager: SkillPackager) -> None:
        """Adding a tool increases manifest size."""
        before = len(packager.get_tools_manifest())
        packager.add_tool(ToolManifest(name="new_tool", description="New"))
        after = len(packager.get_tools_manifest())
        assert after == before + 1


# --- Trigger patterns tests ---


class TestTriggerPatterns:
    """Test trigger patterns include research keywords."""

    def test_research_keyword_present(self, packager: SkillPackager) -> None:
        """Triggers include 'research' keyword."""
        content = packager.render()
        assert "research" in content

    def test_analyze_keyword_present(self, packager: SkillPackager) -> None:
        """Triggers include 'analyze' keyword."""
        content = packager.render()
        assert "analyze" in content

    def test_investigate_keyword_present(self, packager: SkillPackager) -> None:
        """Triggers include 'investigate' keyword."""
        content = packager.render()
        assert "investigate" in content

    def test_triggers_section_exists(self, packager: SkillPackager) -> None:
        """Triggers section header is present."""
        content = packager.render()
        assert "## Triggers" in content

    def test_default_triggers_used(self) -> None:
        """Default triggers list contains research keywords."""
        assert "research" in DEFAULT_TRIGGERS
        assert "analyze" in DEFAULT_TRIGGERS
        assert "investigate" in DEFAULT_TRIGGERS

    def test_custom_triggers(self) -> None:
        """Custom triggers override defaults."""
        p = SkillPackager(
            name="custom",
            version="1.0.0",
            triggers=["custom-trigger", "another"],
        )
        content = p.render()
        assert "custom-trigger" in content
        assert "another" in content


# --- Generate to file tests ---


class TestGenerate:
    """Test generate writes SKILL.md to disk."""

    def test_generate_creates_file(self, packager: SkillPackager, tmp_path: Path) -> None:
        """generate() creates SKILL.md in output directory."""
        result_path = packager.generate(tmp_path)
        assert result_path.exists()
        assert result_path.name == "SKILL.md"

    def test_generate_creates_directory(self, packager: SkillPackager, tmp_path: Path) -> None:
        """generate() creates output directory if needed."""
        output = tmp_path / "nested" / "dir"
        result_path = packager.generate(output)
        assert result_path.exists()

    def test_generate_content_matches_render(self, packager: SkillPackager, tmp_path: Path) -> None:
        """File content matches render() output."""
        result_path = packager.generate(tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        render_content = packager.render()
        assert file_content == render_content
