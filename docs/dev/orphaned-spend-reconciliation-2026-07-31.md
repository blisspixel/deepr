# Orphaned spend reconciliation report

Date: 2026-07-31  
Scope: ROADMAP P0 forensic reconciliation of historical orphaned spend  
External spend: $0.00 (no provider calls)  
Ledger rewrite: none (append-only preserved)

## Method

1. Reproduced `deepr costs doctor` against the operator accounting roots
   (`~/.deepr/costs/cost_ledger.jsonl` and checkout `data/costs/cost_ledger.jsonl`).
2. Classified every positive-cost event in a 45-day window as matched (report
   dir join), then recorded durable dispositions for residual orphans.
3. Dispositions stored at `~/.deepr/costs/spend_dispositions.jsonl` via
   `deepr.observability.spend_dispositions` (schema
   `deepr-spend-disposition-v1`).
4. Re-ran doctor: unexplained spend **$0.00**.

## Totals (45-day window)

| Bucket | Events | USD |
| --- | ---: | ---: |
| Matched (report artifacts on disk) | 6 | 0.63 |
| Disposed | 143 | 41.16 |
| Unexplained | 0 | 0.00 |
| **Paid total in window** | **149** | **41.79** |

These figures match the ROADMAP 2026-07-29 finding of 143 orphans / $41.16
after report-join (matched rows differ only by later report retention).

## Disposition breakdown

| Kind | Events | Notes |
| --- | ---: | --- |
| `expected_non_report` | 87 | Portraits, expert chat, standard_research_fallback, council backfill, browser-chat failure path |
| `lost_artifact` | 56 | Research jobs / completions with job identity but no surviving report directory and no joinable queue row |
| `failed_or_cancelled` | 0 | Not used for this inventory |
| `unresolved_provider_evidence` | 0 | Not required; local identity was sufficient |

### expected_non_report evidence

- `portrait_generation` / `task_id` prefix `portrait_` never emit research report dirs.
- `expert_chat`, `standard_research_fallback`, and chat-path sources settle chat cost without report directories.
- `council_synthesis_backfill` is a non-report maintenance settle.

### lost_artifact evidence

- Primary cluster: 54 `research_job` events totaling **$37.79** settled via
  `queue.update_results` with UUID `task_id` values. None of those job ids
  remain in `queue/research_queue.db`. This is the historical campaign cited
  in doctor docs and ROADMAP.
- Additional `research_completion` settles with research-style task ids and
  no surviving report directory (including reservation reconciliation rows).
- Job identity retained on each disposition (`job_id` field). No provider
  receipt API was called; request ids already present on some ledger rows were
  preserved in the ledger, not required for disposition close-out.

## Integrity after apply

`deepr costs doctor --json` (2026-07-31):

- `unexplained_spend_usd`: 0
- `orphaned_spend_usd`: 0 (alias of unexplained)
- `disposed_spend_usd`: 41.16
- `matched_spend_usd`: 0.63
- Tracking checks: ledger writable, accounting ready, multi-root coverage,
  dashboard drift $0.00

## What this does not authorize

- Paid API unfreeze
- Metered expert chat re-enable
- Ledger mutation or refund of settled dollars
- Provider account-control recovery

## Review

Classification rules are deterministic and unit-tested. Operator review of this
report closes the ROADMAP P0 acceptance item for independent review of the
forensic inventory. Superseding dispositions may be appended if later provider
exports change a kind.
