"""Machine-readable capability map for a consuming agent (``deepr_capabilities``).

A connecting agent should not have to read the README or probe by trial and
error to learn what Deepr offers, what is free, and how to spend $0. This builds
one versioned object it can fetch in a single free call: the expert roster, the
key tools with their live cost tiers and when-to-use, the owned/prepaid synthesis
paths, the cost-tier legend, and the structured-error contract.

Cost tiers and the tool set are read from the live registry, never hardcoded, so
this map cannot drift from the tools actually served. The curated ``use_when``
lines are the only prose, and they describe outcomes, not mechanics.
"""

from __future__ import annotations

from typing import Any

from deepr.mcp.search.registry import ToolRegistry

CAPABILITIES_SCHEMA_VERSION = "deepr-capabilities-v1"
CAPABILITIES_KIND = "deepr.capabilities"

# Cap the roster so the payload stays small for a large fleet; the count is exact.
_MAX_ROSTER = 50

# The tools an agent most needs to know, in the order it should consider them,
# each paired with an outcome-oriented "use when". cost_tier and the human
# description come from the registry at build time, so they never drift.
_KEY_TOOLS: tuple[tuple[str, str], ...] = (
    ("deepr_list_experts", "List the domain experts available to consult."),
    ("deepr_query_expert", "Ask one expert; set agentic=true to let it research what it does not know."),
    ("deepr_consult_experts", "Put a cross-domain question to the team; get one synthesized, calibrated answer."),
    ("deepr_what_changed", "See what an expert learned since a prior point."),
    ("deepr_explain_belief", "Get why an expert holds a claim, with its evidence."),
    ("deepr_expert_handoff", "Get a versioned snapshot of an expert to hand to another agent."),
    ("deepr_agentic_research", "Run a deep autonomous Plan-Execute-Review investigation (metered; confirm budget)."),
)


def build_capabilities(store: Any, registry: ToolRegistry, *, version: str) -> dict[str, Any]:
    """Build the ``deepr-capabilities-v1`` map. Read-only, $0, no provider calls."""
    roster = _roster(store)
    tools = [
        {"tool": name, "cost_tier": schema.cost_tier, "use_when": use_when}
        for name, use_when in _KEY_TOOLS
        if (schema := registry.get(name)) is not None
    ]
    return {
        "schema_version": CAPABILITIES_SCHEMA_VERSION,
        "kind": CAPABILITIES_KIND,
        "server": {"name": "deepr-research", "version": version},
        "experts": {"count": len(roster), "roster": roster[:_MAX_ROSTER]},
        "tools": tools,
        "zero_cost_synthesis": {
            "owned": "local",
            "prepaid_plans": ["codex", "claude"],
            "how": (
                "pass synthesis_backend='local', or 'plan' with plan='codex'|'claude', to run "
                "consult/query at $0 and disable silent metered fallback"
            ),
        },
        "cost_tiers": {
            "free": "$0, read-only",
            "low": "cents; owned/prepaid capable",
            "medium": "metered; confirm budget first",
            "high": "metered and larger; confirm budget first",
        },
        "error_contract": {
            "fields": ["error_code", "category", "retryable", "message"],
            "how": "branch on error_code; do not retry in a loop when retryable is false",
        },
        "discovery": {
            "free_orientation": ["deepr_status", "deepr_list_experts"],
            "search": "deepr_tool_search",
            "test_guide": "docs/MCP_AGENT_TEST_GUIDE.md",
        },
    }


def _roster(store: Any) -> list[dict[str, str]]:
    """Return a name-sorted, bounded list of ``{name, domain}`` for each expert."""
    roster = [
        {"name": name, "domain": getattr(profile, "domain", "") or getattr(profile, "description", "") or ""}
        for profile in store.list_all()
        if (name := getattr(profile, "name", "") or "")
    ]
    roster.sort(key=lambda entry: entry["name"].casefold())
    return roster
