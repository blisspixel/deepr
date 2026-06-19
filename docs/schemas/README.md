# Deepr Schema Registry

This directory contains published contracts for downstream agents and hosted
surfaces. The machine-readable registry is [registry.json](registry.json).

## Compatibility

All v1 schemas are additive within the same schema version:

- New optional fields may appear without a version bump.
- Required fields keep their existing meaning for the life of the schema.
- Removing a required field, changing its type, or changing its meaning requires
  a new `schema_version` and a new schema file.
- Deprecated fields remain readable until a new schema version replaces them.

## Published Schemas

| Schema | File | Purpose |
|---|---|---|
| `deepr-expert-handoff-v1` | [expert-handoff-v1.json](expert-handoff-v1.json) | Bounded read-only expert handoff payload for MCP and web consumers |
| `deepr-loop-status-v1` | [loop-status-v1.json](loop-status-v1.json) | Durable loop status rollup and embedded `ExpertLoopRun` records |
| `deepr-okf-profile-v1` | [okf-profile-v1.json](okf-profile-v1.json) | Mapping from Deepr structured expert state to regenerated OKF Markdown bundles |
| `deepr-mcp-remote-audit-v1` | [mcp-remote-audit-v1.json](mcp-remote-audit-v1.json) | Append-only scoped-key remote MCP tool-call audit events |

Generated artifacts remain derived views unless the schema explicitly says
otherwise. The belief/event/edge store remains canonical for expert knowledge,
and OKF import goes through the verified absorb path.
