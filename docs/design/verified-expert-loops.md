# Design: verified expert loops

Status: active for v2.17.

Deepr already has loop-shaped surfaces: expert sync, absorb, reflection,
health-check, gap routing, and future campaigns. The next step is not a generic
agent orchestrator. The next step is a closed expert knowledge loop that keeps
state current, proves the result, records the run, and hands off a portable
status contract to other agents.

## Loop admission

A surface can graduate from advisory to autonomous only when all four conditions
hold:

1. The task repeats often enough that automation removes recurring human work.
2. Verification is automated and independent of the agent's self-report.
3. Budget/capacity is explicit, capped, and observable before work starts.
4. The agent has the tools, logs, and state needed to inspect failures.

If any condition is missing, keep the surface one-shot, advisory, or
human-gated. This keeps autonomy as an earned property of a surface, not a
default.

## Minimum viable loop

The first loop should have four pieces:

1. **Automation trigger**: manual, scheduled, or event-driven start plus a clear
   stop condition.
2. **Reusable context package**: expert profile, active gaps, recent belief
   changes, allowed tools, budget/capacity contract, and verifier requirements.
3. **Durable state**: an `ExpertLoopRun` record and compact iteration artifacts
   so a run survives process restarts and context resets.
4. **Verifier gate**: a deterministic or calibrated model-backed check that
   decides whether a knowledge-state change is accepted, rejected, retried, or
   escalated.

The gate is the product boundary. A model can propose completion, but the loop
only closes when the verifier and workflow state agree.

## Autonomy ladder

Deepr should build from the smallest reliable loop upward:

1. **Tool loop**: a single agent can call approved tools inside a bounded
   request.
2. **Goal loop**: a durable outer run repeats work until the verifier passes or
   a typed stop reason is recorded. This is the v2.17 target.
3. **Meta loop**: the system compares attempts, prompts, tools, or models and
   keeps the better strategy. This waits for goal-loop telemetry.
4. **Team loop**: multiple experts or specialist agents coordinate on a shared
   objective. This waits for versioned handoff schemas and hosted contracts.

Widening before the smaller loop has acceptance metrics creates expensive noise.

## ExpertLoopRun contract

The substrate should be schema-versioned from the start. Candidate fields:

- `run_id`, `schema_version`, `expert_name`, `loop_type`, `goal`, `trigger`
- `status`, `started_at`, `updated_at`, `finished_at`
- `iteration_count`, `max_iterations`, `state_artifact_path`
- `budget_limit`, `budget_spent`, `capacity_source`, `backend_profile_id`
- `trace_id`, `queue_id`, `job_id`, `approval_id`
- `input_refs`, `output_refs`, `knowledge_change_refs`
- `verifier_id`, `verifier_version`, `verifier_outcome`, `verifier_score`,
  `verifier_threshold`, `verifier_evidence_refs`
- `accepted_changes`, `rejected_changes`, `acceptance_rate`
- `cost_per_accepted_change`
- `stop_reason`, `failure_reason`, `next_action`

Accepted changes mean accepted knowledge-state mutations: absorbed beliefs,
updated confidence, closed gaps, resolved contradictions, refreshed citations, or
recorded no-op decisions that the verifier confirms as current.

## Stop reasons

Stop reasons are typed workflow state, not prose:

- `verifier_passed`
- `no_due_work`
- `budget_exhausted`
- `capacity_unavailable`
- `human_gate_required`
- `max_iterations`
- `tool_failure`
- `verifier_failed`
- `schema_error`
- `cancelled`

A run may be useful even when it stops early, but the reason must be queryable.

## Metrics

The dashboard and MCP read surface should expose:

- Acceptance rate: accepted changes divided by attempted changes.
- Cost per accepted change: Deepr spend divided by accepted changes, with local
  and prepaid capacity separated from metered API spend.
- Retry count and verifier failure rate.
- Gap velocity: opened, refreshed, and closed gaps per run window.
- Freshness delta: stale beliefs before and after the run.
- Contested-claim delta: open contradictions before and after the run.

If a loop rejects most attempted changes, it stays supervised while prompts,
tools, or verifiers improve. The goal is not more iterations. The goal is fewer
human-reviewed failures per accepted knowledge change.

## OKF boundary

OKF is the interchange view, not the source of truth. Export regenerates Markdown
concepts from the belief/event/edge store. Import routes through the same
verified absorb path as any other corpus. Generated Markdown must never bypass
source trust, contradiction checks, citation requirements, or the
generated-artifact regeneration invariant.

## Non-goals

- No generic workflow orchestrator.
- No unbounded loops or swarms.
- No model self-declared completion on the critical path.
- No paid calls by default.
- No OKF bundle as authoritative expert state.
- No meta/team loop before the goal loop has durable telemetry.

## Build order

1. Define the `ExpertLoopRun` schema, typed stop reasons, and append-only run
   storage.
2. Add `deepr expert loop-status NAME` plus the MCP read tool.
3. Instrument existing sync, absorb, reflection, and health-check actions as
   loop attempts without changing behavior.
4. Add verifier adapters for continuity, gap closure, contradiction state,
   citation freshness, and budget/capacity eligibility.
5. Turn one existing advisory surface into a closed goal loop behind the
   admission contract.
6. Add dashboard/API rollups for freshness, gaps, verifier failures, next action,
   capacity source, acceptance rate, and cost per accepted change.
7. Land OKF export/import as a portable view over the verified state.
