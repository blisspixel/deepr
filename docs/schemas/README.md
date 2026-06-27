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
| `deepr-expert-self-model-v1` | [expert-self-model-v1.json](expert-self-model-v1.json) | Read-only expert capabilities, limits, goals, calibration, risks, and current-focus packet |
| `deepr-expert-self-model-update-v1` | [expert-self-model-update-v1.json](expert-self-model-update-v1.json) | Verifier-gated review record for monitor proposals that would change self-model interpretation |
| `deepr-expert-self-model-update-acceptance-v1` | [expert-self-model-update-acceptance-v1.json](expert-self-model-update-acceptance-v1.json) | Human-reviewed acceptance record with outcome evidence and policy gates for a recorded self-model update |
| `deepr-metacognitive-monitor-v1` | [metacognitive-monitor-v1.json](metacognitive-monitor-v1.json) | Read-only reviewed proposals from self-model, loop-run, and consult-trace evidence |
| `deepr-metacognitive-promotion-v1` | [metacognitive-promotion-v1.json](metacognitive-promotion-v1.json) | Preview or applied result for reviewed monitor proposal promotion into gap or eval artifacts |
| `deepr-loop-status-v1` | [loop-status-v1.json](loop-status-v1.json) | Durable loop status rollup and embedded `ExpertLoopRun` records with optional run context |
| `deepr-okf-profile-v1` | [okf-profile-v1.json](okf-profile-v1.json) | Mapping from Deepr structured expert state to regenerated OKF Markdown bundles |
| `deepr-mcp-remote-audit-v1` | [mcp-remote-audit-v1.json](mcp-remote-audit-v1.json) | Append-only scoped-key remote MCP tool-call audit events |
| `deepr-mcp-registration-manifest-v1` | [mcp-registration-manifest-v1.json](mcp-registration-manifest-v1.json) | Token-redacted hosted MCP endpoint registration metadata plus optional smoke results |
| `deepr-a2a-task-v1` | [a2a-task-v1.json](a2a-task-v1.json) | Agent-to-agent task state envelope for A2A create, status, cancel, and result responses |
| `deepr-consult-trace-v1` | [consult-trace-v1.json](consult-trace-v1.json) | Local replayable consult trace records for turning consult failures into eval and gap candidates |
| `deepr-consult-trace-candidates-v1` | [consult-trace-candidates-v1.json](consult-trace-candidates-v1.json) | Sanitized gap and eval candidates mined from failed or low-context consult traces |
| `deepr-source-pack-manifest-v1` | [source-pack-manifest-v1.json](source-pack-manifest-v1.json) | Deterministic source-pack compiler manifest with provenance hashes and no semantic verdicts |
| `deepr-source-note-v1` | [source-note-v1.json](source-note-v1.json) | Deterministic source-note cards with stable IDs, source windows, hashes, and provenance refs |
| `deepr-capacity-next-v1` | [capacity-next-v1.json](capacity-next-v1.json) | Read-only `$0` capacity guidance payload for scheduler and CLI consumers |
| `deepr-sync-capacity-gate-v1` | [sync-capacity-gate-v1.json](sync-capacity-gate-v1.json) | Read-only sync capacity wait/block payload with embedded capacity and self-model guidance |
| `deepr-scheduled-gap-fill-wait-v1` | [scheduled-gap-fill-wait-v1.json](scheduled-gap-fill-wait-v1.json) | Read-only scheduled gap-fill wait payload with routed gaps and safe next actions |
| `deepr-scheduled-reflection-wait-v1` | [scheduled-reflection-wait-v1.json](scheduled-reflection-wait-v1.json) | Read-only scheduled reflection wait payload for evaluator and follow-up capacity gates |
| `deepr-health-check-action-plan-v1` | [health-check-action-plan-v1.json](health-check-action-plan-v1.json) | Read-only scheduled health-check action plan with per-action scheduler status |
| `deepr-health-check-archive-confirmation-v1` | [health-check-archive-confirmation-v1.json](health-check-archive-confirmation-v1.json) | Read-only scheduled health-check archive confirmation payload for reversible stale-belief cleanup |
| `deepr-cli-operation-result-v1` | [cli-operation-result-v1.json](cli-operation-result-v1.json) | Stable `OperationResult` envelope emitted by shared CLI `--json` output helpers |

Generated artifacts remain derived views unless the schema explicitly says
otherwise. The belief/event/edge store remains canonical for expert knowledge,
and OKF import goes through the verified absorb path.
