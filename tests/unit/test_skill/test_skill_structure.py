"""
Property-based tests for Claude Skill structure validation.

Feature: deepr-claude-skill
Tests SKILL.md structure, YAML frontmatter, and content requirements.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given, settings, strategies as st

SKILL_PATH = Path("skills/deepr-research/SKILL.md")
REQUIRED_KEYWORDS = ["research", "deep research", "domain expert", "async"]


def parse_skill_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from SKILL.md content."""
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)
    if not match:
        raise ValueError("Invalid SKILL.md format: missing YAML frontmatter")
    
    frontmatter = yaml.safe_load(match.group(1))
    body = match.group(2)
    return frontmatter, body


def count_tokens_approximate(text: str) -> int:
    """Approximate token count (roughly 4 chars per token for English)."""
    return len(text) // 4


class TestSkillFileExists:
    """Verify skill file structure exists."""
    
    def test_skill_md_exists(self) -> None:
        """SKILL.md file must exist at expected path."""
        assert SKILL_PATH.exists(), f"SKILL.md not found at {SKILL_PATH}"
    
    def test_references_directory_exists(self) -> None:
        """References directory must exist."""
        refs_path = SKILL_PATH.parent / "references"
        assert refs_path.exists(), "references/ directory not found"
    
    def test_scripts_directory_exists(self) -> None:
        """Scripts directory must exist."""
        scripts_path = SKILL_PATH.parent / "scripts"
        assert scripts_path.exists(), "scripts/ directory not found"
    
    def test_templates_directory_exists(self) -> None:
        """Templates directory must exist."""
        templates_path = SKILL_PATH.parent / "templates"
        assert templates_path.exists(), "templates/ directory not found"


class TestYAMLFrontmatter:
    """
    Property 1: YAML Frontmatter Validity
    
    For any valid SKILL.md file, parsing the YAML frontmatter SHALL produce
    a valid object containing the required fields: name (non-empty string),
    description (non-empty string), and version (valid semver string).
    
    Validates: Requirements 1.1
    """
    
    @pytest.fixture
    def skill_content(self) -> str:
        """Load SKILL.md content."""
        return SKILL_PATH.read_text(encoding="utf-8")
    
    @pytest.fixture
    def frontmatter(self, skill_content: str) -> dict[str, Any]:
        """Parse frontmatter from skill content."""
        fm, _ = parse_skill_frontmatter(skill_content)
        return fm
    
    def test_frontmatter_parses_without_error(self, skill_content: str) -> None:
        """YAML frontmatter must parse without errors."""
        frontmatter, body = parse_skill_frontmatter(skill_content)
        assert frontmatter is not None
        assert body is not None
    
    def test_name_field_exists_and_nonempty(self, frontmatter: dict[str, Any]) -> None:
        """Name field must exist and be non-empty string."""
        assert "name" in frontmatter, "Missing 'name' field in frontmatter"
        assert isinstance(frontmatter["name"], str), "name must be string"
        assert len(frontmatter["name"].strip()) > 0, "name must be non-empty"
    
    def test_description_field_exists_and_nonempty(self, frontmatter: dict[str, Any]) -> None:
        """Description field must exist and be non-empty string."""
        assert "description" in frontmatter, "Missing 'description' field"
        assert isinstance(frontmatter["description"], str), "description must be string"
        assert len(frontmatter["description"].strip()) > 0, "description must be non-empty"
    
    def test_version_field_is_valid_semver(self, frontmatter: dict[str, Any]) -> None:
        """Version field must be valid semver format."""
        assert "version" in frontmatter, "Missing 'version' field"
        version = frontmatter["version"]
        
        # Semver pattern: MAJOR.MINOR.PATCH with optional pre-release
        semver_pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$"
        assert re.match(semver_pattern, version), f"Invalid semver: {version}"


class TestActivationKeywords:
    """
    Property 6: Activation Keywords Completeness
    
    For any valid SKILL.md description field, the description SHALL contain
    all required activation keywords: "research", "deep research", 
    "domain expert", "async".
    
    Validates: Requirements 10.1
    """
    
    @pytest.fixture
    def description(self) -> str:
        """Extract description from frontmatter."""
        content = SKILL_PATH.read_text(encoding="utf-8")
        frontmatter, _ = parse_skill_frontmatter(content)
        return frontmatter["description"].lower()
    
    @pytest.mark.parametrize("keyword", REQUIRED_KEYWORDS)
    def test_required_keyword_present(self, description: str, keyword: str) -> None:
        """Each required activation keyword must be present in description."""
        assert keyword in description, f"Missing keyword: '{keyword}'"
    
    def test_all_keywords_present(self, description: str) -> None:
        """All required keywords must be present."""
        missing = [kw for kw in REQUIRED_KEYWORDS if kw not in description]
        assert not missing, f"Missing keywords: {missing}"


class TestTokenCount:
    """Verify SKILL.md respects token limits for progressive disclosure."""
    
    def test_skill_md_under_5000_tokens(self) -> None:
        """SKILL.md instructions must be under 5000 tokens."""
        content = SKILL_PATH.read_text(encoding="utf-8")
        _, body = parse_skill_frontmatter(content)
        
        token_count = count_tokens_approximate(body)
        assert token_count < 5000, f"SKILL.md body is {token_count} tokens (limit: 5000)"
    
    def test_frontmatter_under_200_tokens(self) -> None:
        """Frontmatter metadata should be concise (~100-200 tokens)."""
        content = SKILL_PATH.read_text(encoding="utf-8")
        frontmatter, _ = parse_skill_frontmatter(content)
        
        # Serialize frontmatter back to estimate size
        fm_text = yaml.dump(frontmatter)
        token_count = count_tokens_approximate(fm_text)
        assert token_count < 200, f"Frontmatter is {token_count} tokens (target: <200)"


class TestPropertyBasedFrontmatter:
    """
    Property-based tests using Hypothesis to verify frontmatter parsing
    is robust against various valid inputs.
    """
    
    # Safe alphabet for YAML names (no special chars, no pure digits)
    SAFE_NAME_CHARS = st.sampled_from("abcdefghijklmnopqrstuvwxyz-_")
    
    @given(
        name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=3, max_size=30),
        version=st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_valid_frontmatter_always_parses(self, name: str, version: str) -> None:
        """Any valid frontmatter structure should parse correctly."""
        # Ensure name starts with letter (YAML-safe)
        if not name or not name[0].isalpha():
            name = "skill-" + name
        
        description = "Test skill for research and deep research with domain expert and async capabilities"
        
        skill_content = f"""---
name: "{name}"
description: "{description}"
version: "{version}"
---

# Test Content
"""
        frontmatter, body = parse_skill_frontmatter(skill_content)
        
        assert frontmatter["name"] == name
        assert frontmatter["version"] == version
        assert "research" in frontmatter["description"].lower()
    
    @given(
        major=st.integers(min_value=0, max_value=99),
        minor=st.integers(min_value=0, max_value=99),
        patch=st.integers(min_value=0, max_value=99),
    )
    @settings(max_examples=30)
    def test_semver_versions_are_valid(self, major: int, minor: int, patch: int) -> None:
        """Generated semver versions should match pattern."""
        version = f"{major}.{minor}.{patch}"
        semver_pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$"
        assert re.match(semver_pattern, version)
