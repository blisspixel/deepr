# Current State Analysis

Date: 2026-06-19

## Alignment Summary

Deepr is aligned around one active product bet: persistent domain experts that can keep verified knowledge current without silent spend. The README sells this as research infrastructure, not another chat window. The roadmap makes `v2.16` the active capacity release, with local Ollama already usable for `$0` expert maintenance and plan-quota adapters still explicitly not execution backends. `AGENTIC_BALANCE.md` is the governing boundary: deterministic workflow code owns spend, writes, routing gates, durable state, and verifier outcomes; model judgment owns meaning such as contradiction, grounding, deduplication, and synthesis.

No clarification is needed before continuing. The docs are internally consistent about what works now, what is visible/read-only, and what remains planned.

## What Works Now

- API-backed research works with budget gates and the append-only cost ledger.
- Local expert creation and maintenance work through `expert make --local`, `expert sync --local`, `expert sync --local --fresh-context`, `expert sync --local --deep-context`, `expert absorb --local`, `eval local`, `eval local-context`, and scored `capacity admit`.
- Capacity visibility is in place through `deepr capacity`, quota observations, normalized backend profiles, eligibility decisions, pure backend selection, and `deepr capacity next`.
- The evidence layer is present through `eval continuity`, `eval calibrate`, source-trust floors, event logs, typed edges, lifecycle archival, and model-verdict routing for semantic absorb checks.
- Portable data is in place through `DEEPR_DATA_DIR`, `DEEPR_EXPERTS_PATH`, and `DEEPR_REPORTS_PATH`, with the cost ledger deliberately machine-local.

## Recent Progress

The first capacity QOL slice is now in place. `deepr capacity next` accepts
concrete job context (`--expert`, `--report-id`, `--context-mode`, and
`--scheduled`) and returns deterministic wait/fallback guidance without running
research or spending.

`deepr expert sync --scheduled` now consumes the same guidance before launching a
due subscription sync. If a scheduled run would otherwise fall through to
metered API, or if fresh/deep context needs local capacity, the command returns a
wait payload with next actions instead of spending. Explicit `--api` remains the
operator override.

`deepr expert route-gaps --execute --scheduled` now returns pending routes and a
wait state instead of starting metered gap-fill research from recurring
schedulers. This does not pretend gap-fill has a cheap backend yet; it exposes
the pending work and waits.

`deepr expert reflect --scheduled` now validates the report lookup and returns a
structured wait before the reflection evaluator or follow-up research can run.
This keeps recurring reflection follow-up jobs honest while cheap evaluator
capacity is still planned.

`deepr expert health-check --scheduled` now emits a scheduler action plan for
the audit's recommended actions. Metered recommendations wait for capacity,
confirm-gated local writes wait for confirmation, and `--archive-stale
--scheduled` will not mutate unless `--yes` is explicit.

Scheduled expert wait and action-plan surfaces now append durable
`ExpertLoopRun` snapshots and include `loop_run` JSON. This covers sync,
gap-fill route execution, reflection follow-ups, and health-check action plans,
so blocked recurring maintenance is visible through `deepr expert loop-status`
without repeating the job.

The loop-status state is now available to host agents through the
`deepr_expert_loop_status` MCP tool, with optional status and loop-type filters.

Successful `deepr expert sync` runs now append completed or failed
`ExpertLoopRun` snapshots with trigger, budget spent, capacity source, accepted
change count, and next action for failed topics.

Non-dry `deepr expert route-gaps --execute` runs now append gap-fill
`ExpertLoopRun` snapshots too. The record carries trigger, budget spent,
capacity source, accepted-change count, typed failure stops, and concrete next
actions for failed outcomes, deferred specialist routes, or budget exhaustion.

`deepr expert reflect` now appends reflection `ExpertLoopRun` snapshots with
verifier outcome, score, model version, typed verifier-failed stops, and
follow-up absorption metrics when `--execute-followups` runs.

`deepr expert health-check` and confirmed `--archive-stale` runs now append
health-check `ExpertLoopRun` snapshots with verifier outcome, recommended
action state, accepted archival counts, and typed stops for critical reports,
capacity waits, confirmation gates, or no corrective work.

The dashboard API now exposes `/api/experts/{name}/loop-status`, a read-only
rollup over the same durable run records. It returns the latest run, last sync
result, waiting scheduled action, latest failure, status and loop-type counts,
capacity-source counts, spend totals, acceptance metrics, cost per accepted
change, verifier-failure count, and recent run records. The same response now
includes `expert_state` telemetry for freshness, 7-day and 30-day gap velocity,
top open gaps, and contested/open claim counts from structured manifest links
and belief contradiction edges.

The loop completion contract is now enforced at the record layer.
`ExpertLoopRun` rejects completed, failed, or cancelled records without a typed
stop reason, and rejects waiting, completed, failed, or cancelled records when
the stop reason does not match the status.

## Active Gap

The capacity QOL item in `v2.16` now covers the recurring expert maintenance
surfaces at the CLI contract level: sync, gap-fill, reflection follow-ups, and
health-check actioning all have explicit scheduled wait or action-plan behavior.
The first `v2.17` durable loop slice is also in place: `ExpertLoopRun` defines
schema-versioned loop records, typed stop reasons, acceptance metrics, cost per
accepted change, append-only per-expert storage, and read-only
`deepr expert loop-status`. Scheduled wait/action-plan instrumentation now feeds
that store for the recurring expert surfaces that can safely stop before spend
or mutation. MCP read access is also in place for host agents, and completed
sync, gap-fill execution, reflection, and health-check runs now feed the same
lifecycle. The web API can summarize those records and adjacent expert-state
telemetry for the dashboard without rerunning work or spending.

That gap matters because it sits directly on the project promise: stop paying twice, make the cheapest safe route obvious, and never hide gates. It is also a workflow surface, so it can be improved deterministically without violating agentic-balance.

## Next Work

Next slice: codify the loop admission contract so a surface can declare whether
it has repeat demand, automated verification, explicit budget/capacity, and
failure-diagnosis state before it graduates from advisory to autonomous.

## Spend Ledger For This Run

External paid spend: `$0.00`.

Only local filesystem reads, local tests, lint, and git operations are planned. No provider APIs, embeddings, paid evals, or paid research runs will be used.
