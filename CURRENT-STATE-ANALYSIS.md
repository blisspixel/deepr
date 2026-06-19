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

## Active Gap

The capacity QOL item in `v2.16` now covers the recurring expert maintenance
surfaces at the CLI contract level: sync, gap-fill, reflection follow-ups, and
health-check actioning all have explicit scheduled wait or action-plan behavior.
The first `v2.17` durable loop slice is also in place: `ExpertLoopRun` defines
schema-versioned loop records, typed stop reasons, acceptance metrics, cost per
accepted change, append-only per-expert storage, and read-only
`deepr expert loop-status`.

That gap matters because it sits directly on the project promise: stop paying twice, make the cheapest safe route obvious, and never hide gates. It is also a workflow surface, so it can be improved deterministically without violating agentic-balance.

## Next Work

Next slice: instrument the scheduled expert surfaces to append `ExpertLoopRun`
snapshots, or add the MCP read tool for the new loop-status records.

## Spend Ledger For This Run

External paid spend: `$0.00`.

Only local filesystem reads, local tests, lint, and git operations are planned. No provider APIs, embeddings, paid evals, or paid research runs will be used.
