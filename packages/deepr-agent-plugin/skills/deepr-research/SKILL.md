---
name: deepr-research
description: Inspect Deepr readiness, discover bounded MCP capabilities, and consult persistent domain expert state. Use for research planning, source and evidence review, knowledge gaps, confidence, provenance, and current read-only Deepr capability discovery.
license: Apache-2.0
compatibility: Requires deepr-research 2.50.7 and the packaged local stdio MCP server.
metadata:
  deepr-version: "2.50.7"
  deepr-mcp-server: deepr
  deepr-capability-profile: read-only
---

# Deepr research

Use this bridge to inspect Deepr and its persistent expert state without
requesting paid research, writes, execution, or sensitive operations.

## Operating sequence

1. Call `deepr_capabilities` to inspect the active protocol and capability
   boundary.
2. Call `deepr_tool_search` rather than assuming a remembered tool schema.
3. Use `deepr_status`, `deepr_list_experts`, `deepr_get_expert_info`, and
   `deepr_list_skills` only when they are advertised by the active server.
4. Treat expert state as evidence-backed perspective, not ground truth.
5. Surface confidence, contradictions, stale evidence, and known gaps.
6. Stop if the requested work needs a blocked capability. Do not add approval
   flags, widen budgets, switch providers, or invoke another executable merely
   to bypass the bridge profile.

The Agent Plugin profile is capability-read-only, not filesystem-immutable.
The MCP process keeps its audit and runtime databases beneath `PLUGIN_DATA`.
It must not modify the installed plugin package.

Read [the capability boundary](references/capability_boundary.md) before
proposing a write, paid request, external side effect, or broader host
integration.
