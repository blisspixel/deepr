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

## Active Gap

The highest-leverage current gap is still in `v2.16`, not `v2.17`: capacity QOL needs concrete job dry-run previews and scheduler-facing guidance. Existing `deepr capacity next --task-class sync` ranks generic setup, eval, admission, and metered fallback steps. It does not yet let an operator describe the job shape, such as fresh/deep local sync context or scheduled maintenance, and then see whether Deepr should run locally, wait, or use explicit metered fallback.

That gap matters because it sits directly on the project promise: stop paying twice, make the cheapest safe route obvious, and never hide gates. It is also a workflow surface, so it can be improved deterministically without violating agentic-balance.

## Next Work

First slice: extend `deepr capacity next` with concrete job context while keeping it `$0` and read-only.

Planned behavior:

- Accept a sync context mode so `fresh` and `deep` jobs explain that local capacity is required.
- Fill suggested commands with an optional expert name and report id instead of only placeholders.
- For scheduled work, show a wait/reschedule action when local capacity is blocked rather than implying the scheduler should pay immediately.
- Keep metered fallback explicit and budget-gated, never automatic.

This is the right next step because it finishes a user-felt `v2.16` QOL item before widening into the larger `v2.17` `ExpertLoopRun` substrate.

## Spend Ledger For This Run

External paid spend: `$0.00`.

Only local filesystem reads, local tests, lint, and git operations are planned. No provider APIs, embeddings, paid evals, or paid research runs will be used.
