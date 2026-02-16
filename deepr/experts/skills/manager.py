"""Skill discovery, indexing, and activation.

Scans three tiers of skill storage (built-in, user global, expert-local),
builds an index, and provides query-based skill detection.
"""

from __future__ import annotations

import logging
from pathlib import Path

from deepr.experts.skills.definition import SkillDefinition

logger = logging.getLogger(__name__)

# Tier paths (later tiers override earlier ones for same-name skills)
_BUILTIN_DIR = Path(__file__).parent.parent.parent / "skills"
_USER_GLOBAL_DIR = Path.home() / ".deepr" / "skills"


class SkillManager:
    """Discovers and indexes skills across all storage tiers."""

    def __init__(self, expert_name: str | None = None):
        """Scan all 3 tiers and build the skill index.

        Args:
            expert_name: If provided, also scan expert-local skills.
        """
        self._skills: dict[str, SkillDefinition] = {}
        self._expert_name = expert_name

        # Scan tiers in priority order (later overrides earlier)
        self._scan_tier(_BUILTIN_DIR, "built-in")
        self._scan_tier(_USER_GLOBAL_DIR, "global")

        if expert_name:
            expert_skills_dir = Path("data/experts") / expert_name / "skills"
            self._scan_tier(expert_skills_dir, "expert-local")

    def _scan_tier(self, base_dir: Path, tier: str) -> None:
        """Scan a directory for skill subdirectories containing skill.yaml."""
        if not base_dir.exists():
            return

        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest = child / "skill.yaml"
            if not manifest.exists():
                continue
            try:
                skill = SkillDefinition.load(child, tier)
                self._skills[skill.name] = skill  # Later tiers override
            except Exception as e:
                logger.warning("Skipping malformed skill %s: %s", child.name, e)

    def get_skill(self, name: str) -> SkillDefinition | None:
        """Get a single skill by name."""
        return self._skills.get(name)

    def list_all(self) -> list[SkillDefinition]:
        """List all discovered skills."""
        return list(self._skills.values())

    def get_installed_skills(self, names: list[str]) -> list[SkillDefinition]:
        """Get definitions for a list of installed skill names.

        Silently skips names that don't resolve to a known skill.
        """
        result = []
        for name in names:
            skill = self._skills.get(name)
            if skill:
                result.append(skill)
        return result

    def detect_skills_for_query(self, query: str, installed_names: list[str]) -> list[SkillDefinition]:
        """Detect which installed skills match a user query.

        Only checks skills that are installed on the expert.

        Args:
            query: The user's message
            installed_names: Skill names installed on the expert

        Returns:
            List of matching SkillDefinitions
        """
        matches = []
        for name in installed_names:
            skill = self._skills.get(name)
            if skill and skill.triggers.matches(query):
                matches.append(skill)
        return matches

    def suggest_skills_for_domain(self, domain: str) -> list[SkillDefinition]:
        """Suggest skills whose domain tags match a given domain.

        Args:
            domain: The expert's domain string

        Returns:
            List of skills with matching domain tags
        """
        domain_lower = domain.lower()
        suggestions = []
        for skill in self._skills.values():
            for tag in skill.domains:
                if tag.lower() in domain_lower or domain_lower in tag.lower():
                    suggestions.append(skill)
                    break
        return suggestions
