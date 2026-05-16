"""Property tests for SkillPackager.

Feature: mcp-client-agent-interop
Property: 29
Validates: Requirements 13.1, 13.2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.skills.packager import SkillPackager
from deepr.skills.templates import ToolManifest

# --- Strategies ---

tool_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=20,
)

tool_desc_st = st.text(min_size=1, max_size=50)

tool_manifest_st = st.builds(
    ToolManifest,
    name=tool_name_st,
    description=tool_desc_st,
    parameters=st.just({"properties": {"query": {"type": "string", "description": "Search query"}}}),
    server_name=st.just("deepr"),
)

version_st = st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True)


# --- Property 29: SKILL.md completeness ---


@settings(max_examples=100)
@given(
    tools=st.lists(tool_manifest_st, min_size=1, max_size=5),
    version=version_st,
    name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-"),
        min_size=3,
        max_size=20,
    ),
)
def test_skill_md_completeness(
    tools: list[ToolManifest],
    version: str,
    name: str,
) -> None:
    """Property 29: SKILL.md completeness.

    For any set of public MCP tools, the generated SKILL.md contains:
    - name, description, version, mcp_server in frontmatter
    - Every tool appears in the tools list with description and parameters

    **Validates: Requirements 13.1, 13.2**
    """
    packager = SkillPackager(
        name=name,
        description="Test skill",
        version=version,
        mcp_server="deepr",
    )
    packager.add_tools(tools)

    content = packager.render()

    # Frontmatter fields present
    assert f"name: {name}" in content, "name missing from frontmatter"
    assert f"version: {version}" in content, "version missing from frontmatter"
    assert "mcp_server: deepr" in content, "mcp_server missing from frontmatter"
    assert "description:" in content, "description missing from frontmatter"

    # Every tool appears
    for tool in tools:
        assert tool.name in content, f"Tool '{tool.name}' missing from SKILL.md"
        assert tool.description in content, f"Tool description '{tool.description}' missing from SKILL.md"


@settings(max_examples=100)
@given(tools=st.lists(tool_manifest_st, min_size=1, max_size=3))
def test_skill_md_has_triggers(tools: list[ToolManifest]) -> None:
    """SKILL.md includes trigger keywords.

    **Validates: Requirements 13.1**
    """
    packager = SkillPackager(name="test", version="1.0.0")
    packager.add_tools(tools)

    content = packager.render()

    # Should have triggers section with research keywords
    assert "## Triggers" in content
    assert "research" in content
