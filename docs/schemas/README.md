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
| `deepr-expert-memory-card-v1` | [expert-memory-card-v1.json](expert-memory-card-v1.json) | Generated `EXPERT.md` orientation view over profile, manifest, belief events, and self-model state |
| `deepr-expert-mutation-audit-v1` | [expert-mutation-audit-v1.json](expert-mutation-audit-v1.json) | Append-only belief mutation audit entry with actor, operation, and before/after state hashes |
| `deepr-expert-self-model-update-v1` | [expert-self-model-update-v1.json](expert-self-model-update-v1.json) | Verifier-gated review record for monitor proposals that would change self-model interpretation |
| `deepr-expert-self-model-update-acceptance-v1` | [expert-self-model-update-acceptance-v1.json](expert-self-model-update-acceptance-v1.json) | Human-reviewed acceptance record with outcome evidence and policy gates for a recorded self-model update |
| `deepr-metacognitive-monitor-v1` | [metacognitive-monitor-v1.json](metacognitive-monitor-v1.json) | Read-only reviewed proposals from self-model, loop-run, and consult-trace evidence |
| `deepr-metacognitive-promotion-v1` | [metacognitive-promotion-v1.json](metacognitive-promotion-v1.json) | Preview or applied result for reviewed monitor proposal promotion into gap or eval artifacts |
| `deepr-loop-status-v1` | [loop-status-v1.json](loop-status-v1.json) | Durable loop status rollup and embedded `ExpertLoopRun` records with optional run context |
| `deepr-okf-profile-v1` | [okf-profile-v1.json](okf-profile-v1.json) | Mapping from Deepr structured expert state to regenerated OKF Markdown bundles |
| `deepr-mcp-remote-audit-v1` | [mcp-remote-audit-v1.json](mcp-remote-audit-v1.json) | Append-only scoped-key remote MCP tool-call audit events |
| `deepr-mcp-registration-manifest-v1` | [mcp-registration-manifest-v1.json](mcp-registration-manifest-v1.json) | Token-redacted hosted MCP endpoint registration metadata plus optional smoke results |
| `deepr-a2a-task-v1` | [a2a-task-v1.json](a2a-task-v1.json) | Agent-to-agent task state envelope for A2A create, status, cancel, result responses, and attached task artifacts |
| `deepr-a2a-host-validation-v1` | [a2a-host-validation-v1.json](a2a-host-validation-v1.json) | No-metered A2A Agent Card and consult task validation report for offline fixtures and HTTP endpoints |
| `deepr-consult-v1` | [consult-v1.json](consult-v1.json) | Expert consult artifact for one-expert and multi-expert MCP or CLI guidance |
| `deepr-consult-trace-v1` | [consult-trace-v1.json](consult-trace-v1.json) | Local replayable consult trace records for turning consult failures into eval and gap candidates |
| `deepr-consult-trace-candidates-v1` | [consult-trace-candidates-v1.json](consult-trace-candidates-v1.json) | Sanitized gap and eval candidates mined from failed or low-context consult traces |
| `deepr-consult-quality-eval-case-v1` | [consult-quality-eval-case-v1.json](consult-quality-eval-case-v1.json) | Read-only semantic quality review case packet for human or calibrated-model consult judging, including hallucination risk checks |
| `deepr-consult-quality-review-v1` | [consult-quality-review-v1.json](consult-quality-review-v1.json) | Reviewed consult-quality score artifact with explicit semantic judge, policy gate, and safe gap/eval promotion actions |
| `deepr-consult-quality-trend-v1` | [consult-quality-trend-v1.json](consult-quality-trend-v1.json) | Read-only trend report over reviewed consult-quality artifacts with deterministic prompt-regression candidate selection |
| `deepr-hallucination-risk-report-v1` | [hallucination-risk-report-v1.json](hallucination-risk-report-v1.json) | Read-only advisory hallucination-pattern risk signals and prompt-regression candidates across consult, handoff, and source-pack artifacts |
| `deepr-mcp-consult-validation-v1` | [mcp-consult-validation-v1.json](mcp-consult-validation-v1.json) | No-metered MCP expert-consult validation report for offline fixtures, in-process checks, and HTTP endpoints |
| `deepr-mcp-consult-fleet-validation-v1` | [mcp-consult-fleet-validation-v1.json](mcp-consult-fleet-validation-v1.json) | Bounded concurrent no-metered consult validation across selected plan backends |
| `deepr-source-pack-manifest-v1` | [source-pack-manifest-v1.json](source-pack-manifest-v1.json) | Deterministic source-pack compiler manifest with provenance hashes and no semantic verdicts |
| `deepr-source-note-v1` | [source-note-v1.json](source-note-v1.json) | Deterministic source-note cards with stable IDs, source windows, hashes, and provenance refs |
| `deepr-semantic-claim-extraction-v1` | [semantic-claim-extraction-v1.json](semantic-claim-extraction-v1.json) | Verifier-gated semantic claim candidates from source notes with prompt/schema version capture and no graph writes |
| `deepr-claim-verification-v1` | [claim-verification-v1.json](claim-verification-v1.json) | Verifier decisions for support, contradiction, deduplication, temporal scope, optional candidate edge decisions with temporal qualifiers, and type-specific policy gates |
| `deepr-graph-commit-envelope-v1` | [graph-commit-envelope-v1.json](graph-commit-envelope-v1.json) | Deterministic commit boundary for verified factual compiler decisions with idempotent add-belief operations, verifier-supplied typed edges, and explicit apply gating |
| `deepr-graph-commit-envelope-v2` | [graph-commit-envelope-v2.json](graph-commit-envelope-v2.json) | Deterministic commit boundary for verified compiler decisions with idempotent add-belief, typed-edge, and promote-gap operations |
| `deepr-graph-commit-envelope-v3` | [graph-commit-envelope-v3.json](graph-commit-envelope-v3.json) | Deterministic commit boundary for verified compiler decisions with idempotent add-belief, typed-edge, promote-gap, and promote-exploration-agenda operations |
| `deepr-graph-commit-envelope-v4` | [graph-commit-envelope-v4.json](graph-commit-envelope-v4.json) | Deterministic commit boundary for verified compiler decisions with idempotent add-belief, typed-edge, promote-gap, promote-exploration-agenda, and promote-hypothesis operations |
| `deepr-graph-commit-envelope-v5` | [graph-commit-envelope-v5.json](graph-commit-envelope-v5.json) | Deterministic commit boundary for verified compiler decisions with idempotent add-belief, typed-edge, promote-gap, promote-exploration-agenda, promote-hypothesis, and promote-concept operations |
| `deepr-graph-commit-envelope-v6` | [graph-commit-envelope-v6.json](graph-commit-envelope-v6.json) | Deterministic commit boundary for verified compiler decisions with idempotent add-belief, typed-edge, promote-gap, promote-exploration-agenda, promote-hypothesis, promote-concept, and promote-stance operations |
| `deepr-graph-commit-envelope-v7` | [graph-commit-envelope-v7.json](graph-commit-envelope-v7.json) | Deterministic commit boundary for verified compiler decisions with idempotent add-belief, typed-edge, promote-gap, promote-exploration-agenda, promote-hypothesis, promote-concept, promote-stance, and promote-original-idea operations |
| `deepr-graph-commit-envelope-v8` | [graph-commit-envelope-v8.json](graph-commit-envelope-v8.json) | Deterministic commit boundary for verified compiler decisions with idempotent add-belief, typed-edge temporal qualifiers, and perspective-state promotion operations |
| `deepr-graph-commit-apply-v1` | [graph-commit-apply-v1.json](graph-commit-apply-v1.json) | Explicit apply result for idempotent commit writes into the canonical belief, event, edge, metacognition, exploration-agenda, hypothesis, concept, stance, and original-idea stores |
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
