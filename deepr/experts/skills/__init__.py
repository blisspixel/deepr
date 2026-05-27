"""Expert skills system — domain-specific capability packages.

Skills give each expert unique tools and domain-specific reasoning
instructions beyond their knowledge base. Supports Python tools
(local execution) and MCP tools (external server bridging).

Three-tier storage:
  - Built-in: deepr/skills/
  - User global: ~/.deepr/skills/
  - Expert-local: data/experts/{name}/skills/
"""

from deepr.experts.skills.definition import (
    SkillBudget,
    SkillDefinition,
    SkillTool,
    SkillTrigger,
)
from deepr.experts.skills.executor import MCPClientProxy, SkillExecutor
from deepr.experts.skills.expert_skill import (
    ExpertSkillWrapper,
    KnowledgeGap,
    ResearchContext,
    ToolInfo,
    ToolSuggestion,
)
from deepr.experts.skills.knowledge_absorber import AbsorbedFinding, KnowledgeAbsorber
from deepr.experts.skills.manager import SkillManager

__all__ = [
    "AbsorbedFinding",
    "ExpertSkillWrapper",
    "KnowledgeAbsorber",
    "KnowledgeGap",
    "MCPClientProxy",
    "ResearchContext",
    "SkillBudget",
    "SkillDefinition",
    "SkillExecutor",
    "SkillManager",
    "SkillTool",
    "SkillTrigger",
    "ToolInfo",
    "ToolSuggestion",
]
