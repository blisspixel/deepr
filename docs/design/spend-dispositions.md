# Spend dispositions for non-report settled events

Status: accepted for implementation, 2026-07-31

## Decision

The append-only cost ledger is never rewritten. When a settled positive-cost
event cannot be joined to a surviving report directory, Deepr records a
**durable disposition** in a separate append-only log
(`spend_dispositions.jsonl` under the cost data directory).

`deepr costs doctor` classifies paid events as:

1. **matched** - report directory join succeeds
2. **disposed** - no report match, but a disposition exists
3. **unexplained** - no report match and no disposition (fail-closed / exit 1)

Disposition kinds:

| Kind | Meaning |
| --- | --- |
| `failed_or_cancelled` | Settled after failure or cancellation |
| `expected_non_report` | Intentional non-report surface (portraits, chat, ...) |
| `lost_artifact` | Settlement with job identity but missing report artifact |
| `unresolved_provider_evidence` | Needs external receipt; still a recorded disposition |

## Non-goals

- Ledger rewrite or spend reduction
- Paid API unfreeze
- Provider billing API calls during forensic apply

## Commands

- `deepr costs doctor` - three-way classification
- `deepr costs dispose` - manual single-event disposition
- `deepr costs dispose-unexplained [--apply]` - deterministic local suggestions
- `deepr costs dispositions` - list latest dispositions

## Identity

Prefer non-empty ledger `idempotency_key` (`idem:...`). Otherwise hash a
canonical field set (`hash:...`). Latest disposition per event key wins.
