"""Per-expert SKILL.md export (agentskills.io distribution).

The generic :class:`~deepr.skills.packager.SkillPackager` exports Deepr's whole
tool surface. This module scopes a SKILL.md to a *single expert*: the generated
skill is named for the expert, triggers on its domain, and its body tells the
host agent (Claude Code, Codex, Cursor, OpenClaw, ...) to consult exactly this
expert through Deepr's MCP tools. One `SKILL.md` folder drops into any
agentskills.io-compatible host, turning a Deepr expert into a first-class,
installable skill there - the distribution play in ROADMAP Phase 4.

The export is read-only and local: it packages a pointer to the expert (calls
routed over MCP at run time), not a copy of the expert's knowledge.
"""

from __future__ import annotations

import re

from deepr.skills.packager import SkillPackager
from deepr.skills.templates import ToolManifest

# Base trigger words common to research/consultation skills.
_BASE_TRIGGERS = ["research", "analyze", "investigate", "expert", "consult"]


def expert_slug(name: str) -> str:
    """kebab-case slug for an expert name, safe for a skill directory/name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "expert"


def _expert_triggers(expert_name: str, domain: str) -> list[str]:
    """Trigger keywords: the expert name's words + domain words + base set."""
    words: list[str] = []
    for source in (expert_name, domain):
        for w in re.split(r"[^a-z0-9]+", source.lower()):
            if len(w) > 2 and w not in words:
                words.append(w)
    triggers = words + [t for t in _BASE_TRIGGERS if t not in words]
    return triggers


def _expert_instructions(expert_name: str, domain: str, description: str) -> str:
    """Body instructions telling the host agent how to consult the expert."""
    domain_clause = f" Its domain is {domain}." if domain else ""
    desc_clause = f" {description}" if description else ""
    return (
        f'This skill consults the persistent Deepr expert "{expert_name}" over MCP.'
        f"{domain_clause}{desc_clause}\n\n"
        f"When a question falls in this expert's domain:\n"
        f'1. Call `deepr_query_expert` with `expert_name="{expert_name}"` and the user\'s question. '
        f"You get a grounded, citation-backed answer drawn from the expert's accumulated knowledge.\n"
        f"2. Before acting on a domain claim, validate it with `deepr_expert_validate` "
        f'(`expert_name="{expert_name}"`, `claim=...`) - it returns PASS/WARN/FAIL with supporting and '
        f"contradicting evidence. Do not act on a FAIL without further review.\n"
        f"3. To see where the expert is under-informed, call `deepr_rank_gaps`; to audit its overall "
        f"health (freshness, contradictions, missing provenance) call `deepr_expert_health_check`.\n\n"
        f"The expert is a role, not a chat: prefer its grounded answers over your own priors for "
        f"in-domain questions, and surface its citations to the user. It requires a running Deepr MCP "
        f"server (`deepr mcp` / configured in your host) with this expert present."
    )


def _expert_tool_manifests(expert_name: str) -> list[ToolManifest]:
    """The expert-scoped read-side Deepr MCP tools, with expert_name pinned."""
    pinned = {"type": "string", "description": f'Always "{expert_name}"'}
    return [
        ToolManifest(
            name="deepr_query_expert",
            description=f'Ask the "{expert_name}" expert a question; returns a grounded, cited answer.',
            parameters={
                "properties": {
                    "expert_name": pinned,
                    "question": {"type": "string", "description": "The question to ask the expert"},
                }
            },
            server_name="deepr",
        ),
        ToolManifest(
            name="deepr_expert_validate",
            description=(
                f'Validate a claim against the "{expert_name}" expert\'s knowledge. '
                "Returns PASS/WARN/FAIL with confidence, citations, and caveats."
            ),
            parameters={
                "properties": {
                    "expert_name": pinned,
                    "claim": {"type": "string", "description": "The statement to assess"},
                }
            },
            server_name="deepr",
        ),
        ToolManifest(
            name="deepr_rank_gaps",
            description=f'List the "{expert_name}" expert\'s top knowledge gaps by expected value.',
            parameters={
                "properties": {
                    "expert_name": pinned,
                    "top_n": {"type": "integer", "description": "How many gaps to return (default 5)"},
                }
            },
            server_name="deepr",
        ),
        ToolManifest(
            name="deepr_expert_health_check",
            description=(
                f'Audit the "{expert_name}" expert\'s knowledge state '
                "(freshness, contradictions, missing provenance, open gaps). Read-only."
            ),
            parameters={"properties": {"expert_name": pinned}},
            server_name="deepr",
        ),
    ]


def build_expert_skill(
    expert_name: str,
    domain: str = "",
    description: str = "",
) -> SkillPackager:
    """Build a SkillPackager scoped to one expert.

    Args:
        expert_name: The expert's display name (used verbatim as the MCP
            ``expert_name`` argument the generated skill tells agents to pass).
        domain: The expert's domain (drives triggers + instructions).
        description: The expert's description (folded into the skill body).

    Returns:
        A configured SkillPackager; call ``.render()`` or ``.generate(dir)``.
    """
    frontmatter_description = (
        f"Consult the '{expert_name}' domain expert"
        f"{f' ({domain})' if domain else ''} - a persistent, citation-backed Deepr expert - "
        "for grounded answers, claim validation, and knowledge-gap analysis on in-domain questions."
    )
    packager = SkillPackager(
        name=f"deepr-expert-{expert_slug(expert_name)}",
        description=frontmatter_description,
        mcp_server="deepr",
        triggers=_expert_triggers(expert_name, domain),
        instructions=_expert_instructions(expert_name, domain, description.strip()),
    )
    packager.add_tools(_expert_tool_manifests(expert_name))
    return packager
