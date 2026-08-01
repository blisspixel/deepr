# Parent budget transaction

Status: accepted substrate, 2026-07-31. Surface adoption incomplete.

## Decision

Metered multi-call expert lifecycle work must share one parent budget
transaction before any nested provider call. The pure coordination type is
`ParentBudgetTransaction` in `deepr.experts.parent_budget_transaction`.

## Guarantees

- Parent ceiling cannot exceed the absolute Deepr `$5` ceiling.
- Child admissions cannot oversubscribe remaining headroom.
- Dispatch mark is one-use from `admitted`.
- Settlement must be `<=` child max or the parent freezes and the child
  consumes its full max.
- Ambiguous usage uses `consume_child_ceiling`.
- Close requires every child terminal; frozen parents cannot close cleanly.

## Non-goals (current increment)

- Provider dispatch
- Durable on-disk parent transaction log (in-process first; durable store next)
- Re-enabling `METERED_EXPERT_MUTATIONS_ENABLED`

## Adoption checklist (per surface)

1. Open parent with explicit ceiling.
2. Admit each nested call maximum before construction.
3. Mark dispatch only after durable reservation succeeds.
4. Settle exact usage or consume full bound.
5. Hermetic tests for cancel, concurrency, replay, ledger failure.
6. Reviewed enable for that surface only.
