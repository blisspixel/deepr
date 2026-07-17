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
| `deepr-expert-next-v1` | [expert-next-v1.json](expert-next-v1.json) | Read-only structural next-action guidance for building, recovering, learning, or maintaining one expert |
| `deepr-expert-memory-card-v1` | [expert-memory-card-v1.json](expert-memory-card-v1.json) | Generated `EXPERT.md` orientation view over profile, manifest, belief events, and self-model state |
| `deepr-expert-blueprint-draft-v1` | [expert-blueprint-draft-v1.json](expert-blueprint-draft-v1.json) | Structurally constrained but explicitly unreviewed and non-authoritative purpose draft |
| `deepr-expert-blueprint-preflight-v1` | [expert-blueprint-preflight-v1.json](expert-blueprint-preflight-v1.json) | Zero-call normalized hash, structural summary, and review packet that claims no semantic quality, review, or authority |
| `deepr-expert-blueprint-v1` | [expert-blueprint-v1.json](expert-blueprint-v1.json) | Append-only operator-attested mission, decision use cases, source policy, and acceptance cases with unverified reviewer identity and no human-authorship claim |
| `deepr-expert-outcome-v1` | [expert-outcome-v1.json](expert-outcome-v1.json) | Append-only operator-attested observation about an expert-supported decision, with optional trace and evidence links and unverified reviewer identity |
| `deepr-expert-outcome-summary-v1` | [expert-outcome-summary-v1.json](expert-outcome-summary-v1.json) | Read-only structural counts and linkage coverage over operator-attested outcomes, without an inferred quality verdict |
| `deepr-expert-value-review-v1` | [expert-value-review-v1.json](expert-value-review-v1.json) | Blueprint-bound four-arm workbook over frozen longitudinal source worlds and hashed run artifacts, with operator semantic and protocol attestations that deny verified identity and human-authorship claims |
| `deepr-expert-value-report-v1` | [expert-value-report-v1.json](expert-value-report-v1.json) | Zero-call descriptive arm metrics, risk rates, costs, effort, outcome links, paired-bootstrap intervals, deltas, cost-only break-even estimates, and explicit operator-attested or root-confined local artifact verification status without a superiority flag, winner, or default change |
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
| `deepr-consult-v1` | [consult-v1.json](consult-v1.json) | One-shot synthesis over stored packets from one or many experts, with explicit zero-peer-turn, zero-knowledge-write, and bounded synthesis-call metadata |
| `deepr-consult-trace-v1` | [consult-trace-v1.json](consult-trace-v1.json) | Local replayable consult trace records with selected-order context-position metadata for turning consult failures into eval and gap candidates |
| `deepr-consult-lifecycle-event-v1` | [consult-lifecycle-event-v1.json](consult-lifecycle-event-v1.json) | Append-only pre-dispatch consult lifecycle journal with spend evidence, bounded progress, capacity posture, resumable states, and no answer or private reasoning content |
| `deepr-expert-conversation-v1` | [expert-conversation-v1.json](expert-conversation-v1.json) | Protocol-neutral durable expert-conversation projection with pinned capacity, bounds, retention, and application identity |
| `deepr-expert-conversation-turn-v1` | [expert-conversation-turn-v1.json](expert-conversation-turn-v1.json) | One bounded conversation turn with structured advice, context lineage, capacity, typed stop, and consult traces |
| `deepr-expert-conversation-event-v1` | [expert-conversation-event-v1.json](expert-conversation-event-v1.json) | Append-only content-free lifecycle audit event for durable expert conversations |
| `deepr-expert-context-snapshot-v1` | [expert-context-snapshot-v1.json](expert-context-snapshot-v1.json) | Immutable bounded expert-state packet pinned to one conversation, with explicit content-deletion state |
| `deepr-expert-conversation-error-v1` | [expert-conversation-error-v1.json](expert-conversation-error-v1.json) | Typed redacted error envelope for conversation adapters and optimistic-concurrency recovery |
| `deepr-conversation-eval-v1` | [conversation-eval-v1.json](conversation-eval-v1.json) | Zero-cost frozen-fixture structural evaluation and repeated-one-shot comparison manifest for conversation contracts |
| `deepr-deliberation-eval-v1` | [deliberation-eval-v1.json](deliberation-eval-v1.json) | Zero-cost frozen-fixture structural evaluation for bounded deliberation; semantic quality remains explicitly unreviewed |
| `deepr-consult-trace-candidates-v1` | [consult-trace-candidates-v1.json](consult-trace-candidates-v1.json) | Sanitized gap and eval candidates mined from failed, low-context, or middle-context review consult traces |
| `deepr-consult-quality-eval-case-v1` | [consult-quality-eval-case-v1.json](consult-quality-eval-case-v1.json) | Read-only semantic quality review case packet for human or calibrated-model consult judging, including hallucination risk checks and middle-context metadata |
| `deepr-consult-quality-review-v1` | [consult-quality-review-v1.json](consult-quality-review-v1.json) | Reviewed consult-quality score artifact with explicit semantic judge metadata, policy gate, and safe gap/eval promotion actions |
| `deepr-consult-quality-trend-v1` | [consult-quality-trend-v1.json](consult-quality-trend-v1.json) | Read-only trend report over reviewed consult-quality artifacts with deterministic prompt-regression candidate selection |
| `deepr-hallucination-risk-report-v1` | [hallucination-risk-report-v1.json](hallucination-risk-report-v1.json) | Read-only advisory hallucination-pattern risk signals, prompt-regression candidates, and context-position summaries across consult, handoff, and source-pack artifacts |
| `deepr-recall-eval-report-v2` | [recall-eval-report-v2.json](recall-eval-report-v2.json) | Read-only paired lexical/vector recall evaluation with standard IR metrics and deterministic bootstrap uncertainty |
| `deepr-recall-operator-validation-v1` | [recall-operator-validation-v1.json](recall-operator-validation-v1.json) | Read-only recall-library evidence block that gates explicit sync preference and records that default routing remains unchanged |
| `deepr-recall-library-inventory-v1` | [recall-library-inventory-v1.json](recall-library-inventory-v1.json) | Read-only inventory of accumulated recall case libraries and whether they have enough labels for route-evidence evals |
| `deepr-recall-library-validation-plan-v1` | [recall-library-validation-plan-v1.json](recall-library-validation-plan-v1.json) | Read-only command plan for validating ready accumulated recall libraries without executing retrieval or changing routing |
| `deepr-mcp-consult-validation-v1` | [mcp-consult-validation-v1.json](mcp-consult-validation-v1.json) | No-metered MCP expert-consult validation report for offline fixtures, in-process checks, and HTTP endpoints |
| `deepr-mcp-consult-fleet-validation-v1` | [mcp-consult-fleet-validation-v1.json](mcp-consult-fleet-validation-v1.json) | Bounded concurrent no-metered consult validation across selected plan backends |
| `deepr-recon-evidence-handoff-v1` | [recon-evidence-handoff-v1.json](recon-evidence-handoff-v1.json) | Lossless queried-domain evidence handoff that separates observations from unresolved inferences and cannot authorize organization product-use verdicts |
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
| `deepr-cost-spend-decisions-v1` | [cost-spend-decisions-v1.json](cost-spend-decisions-v1.json) | Read-only `$0` spend-decision readback payload over the append-only value-gate log |
| `deepr-sync-capacity-gate-v1` | [sync-capacity-gate-v1.json](sync-capacity-gate-v1.json) | Read-only sync capacity wait/block payload with embedded capacity and self-model guidance |
| `deepr-scheduled-gap-fill-wait-v1` | [scheduled-gap-fill-wait-v1.json](scheduled-gap-fill-wait-v1.json) | Read-only scheduled gap-fill wait payload with routed gaps and safe next actions |
| `deepr-scheduled-reflection-wait-v1` | [scheduled-reflection-wait-v1.json](scheduled-reflection-wait-v1.json) | Read-only scheduled reflection wait payload for evaluator and follow-up capacity gates |
| `deepr-scheduled-reflection-run-v1` | [scheduled-reflection-run-v1.json](scheduled-reflection-run-v1.json) | Scheduled reflection run on admitted owned/prepaid capacity, with capacity source and follow-up dispatch state |
| `deepr-health-check-action-plan-v1` | [health-check-action-plan-v1.json](health-check-action-plan-v1.json) | Legacy scheduled health-check action plan retained for compatibility; runtime could attach a loop run despite its read-only declaration |
| `deepr-health-check-action-plan-v2` | [health-check-action-plan-v2.json](health-check-action-plan-v2.json) | Read-only scheduled health-check action plan without a persisted or pending loop run |
| `deepr-health-check-archive-confirmation-v1` | [health-check-archive-confirmation-v1.json](health-check-archive-confirmation-v1.json) | Read-only scheduled health-check archive wait payload for reversible stale-belief cleanup or overlap lock contention |
| `deepr-cli-operation-result-v1` | [cli-operation-result-v1.json](cli-operation-result-v1.json) | Stable `OperationResult` envelope emitted by shared CLI `--json` output helpers |

Generated artifacts remain derived views unless the schema explicitly says
otherwise. The belief/event/edge store remains canonical for expert knowledge,
and OKF import goes through the verified absorb path.
