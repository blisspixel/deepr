"""Skill portability — SKILL.md generation and packaging.

Exports Deepr expert capabilities as agentskills.io SKILL.md files
for interoperability with other agent frameworks.
"""

from deepr.skills.packager import SkillPackager
from deepr.skills.templates import SKILL_TEMPLATE, ToolManifest

__all__ = [
    "SKILL_TEMPLATE",
    "SkillPackager",
    "ToolManifest",
]
