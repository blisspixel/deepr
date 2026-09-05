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
        f'This skill points to the persistent Deepr expert "{expert_name}" over MCP.'
        f"{domain_clause}{desc_clause}\n\n"
        f"When a question falls in this expert's domain:\n"
        f"1. Discover the active boundary with `deepr_capabilities` and `deepr_tool_search`. "
        f"Use exact advertised tool names, including any host prefix, and confirm the expert is present "
        f"with `deepr_list_experts`. Installing this skill grants no tools or permissions.\n"
        f"2. The portable Agent Plugin profile exposes inspection tools such as `deepr_get_expert_info`; "
        f"it does not expose generative consultation. If `deepr_query_expert` is advertised by a separately "
        f'configured server, call it with `expert_name="{expert_name}"`, the user\'s question, '
        f'`backend="local"`, and `budget=0`. The default API backend is blocked. '
        f"The local response is a compiled-context perspective whose citations and support still need review.\n"
        f"3. When advertised, inspect a domain claim with `deepr_expert_validate` "
        f'(`expert_name="{expert_name}"`, `claim=...`) - it returns PASS/WARN/FAIL with supporting and '
        f"contradicting evidence. Do not act on a FAIL without further review.\n"
        f"4. When advertised, inspect gaps with `deepr_rank_gaps` and structural health with "
        f"`deepr_expert_health_check`.\n\n"
        f"Treat the expert's statements as evidence-backed perspective and surface its citations and "
        f"uncertainty. A blocked or missing tool is a capability limit: stop that operation instead of "
        f"adding approval flags, changing budgets, or invoking another executable to bypass it. "
        f"This pointer requires a running Deepr MCP server with this expert present."
    )


def _expert_gotchas(expert_name: str) -> str:
    """Real failure modes of consulting a Deepr expert over MCP.

    Anthropic calls the Gotchas section a skill's highest-signal content; these
    are grounded in Deepr's actual freshness, validation, and trust-floor
    semantics, not theoretical warnings. See docs/design/skill-authoring.md.
    """
    return (
        "## Gotchas\n\n"
        "- The expert can be stale. A confident answer is not necessarily current; for "
        "time-sensitive questions, inspect `deepr_what_changed` when advertised before relying on it.\n"
        f'- A PASS from `deepr_expert_validate` means the claim is consistent with what "{expert_name}" '
        "currently believes, not that it is true in the world - it is bounded by the expert's sources. "
        "Treat WARN/FAIL as a stop; do not treat PASS as proof.\n"
        "- Confidence is trust-floor-capped (web-sourced claims cap at ~0.60 single-source, ~0.80 with "
        "two independent sources), so a high number is a capped ceiling, not a probability of truth.\n"
        "- Low confidence or a flagged gap is a reason to surface missing evidence. It does not "
        "authorize research or a write through a read-only host profile.\n"
        "- This skill is a pointer, not a copy: it needs a running Deepr MCP server with "
        f'"{expert_name}" present. EXPERT_NOT_FOUND means it is absent from the selected server\'s '
        "configured expert store. A fresh Agent Plugin workspace starts empty."
    )


def _expert_tool_manifests(expert_name: str) -> list[ToolManifest]:
    """Conditional expert tools, with the expert and zero-cost local query pinned."""
    pinned = {"type": "string", "description": f'Always "{expert_name}"'}
    return [
        ToolManifest(
            name="deepr_query_expert",
            description=f'When advertised, ask the "{expert_name}" expert locally; review its citations and support.',
            parameters={
                "properties": {
                    "expert_name": pinned,
                    "question": {"type": "string", "description": "The question to ask the expert"},
                    "backend": {"type": "string", "const": "local", "description": "Explicit local backend"},
                    "budget": {"type": "number", "const": 0, "description": "Zero paid-spend ceiling"},
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
    # Trigger-style description (the host scans it to decide whether to invoke):
    # name the situations that should fire it, not a noun-phrase summary.
    about_clause = f" about {domain}" if domain else ""
    frontmatter_description = (
        f"Inspect the '{expert_name}' domain expert"
        f"{f' ({domain})' if domain else ''} through the host's advertised Deepr tools. "
        f"Use it when the user asks an in-domain question, wants to review persisted expert information, "
        f"or needs to assess a claim{about_clause}. Local consultation requires an eligible tool profile."
    )
    body = f"{_expert_instructions(expert_name, domain, description.strip())}\n\n{_expert_gotchas(expert_name)}"
    packager = SkillPackager(
        name=f"deepr-expert-{expert_slug(expert_name)}",
        description=frontmatter_description,
        mcp_server="deepr",
        triggers=_expert_triggers(expert_name, domain),
        instructions=body,
    )
    packager.add_tools(_expert_tool_manifests(expert_name))
    return packager
