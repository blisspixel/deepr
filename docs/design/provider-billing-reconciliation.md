# Provider billing reconciliation and paid API recovery

Status: accepted for incremental implementation, 2026-07-27

## Decision

Deepr will treat the provider bill as external evidence and the canonical cost
ledger as local execution evidence. Neither source can silently replace or
rewrite the other. Reconciliation compares immutable snapshots, reports every
unexplained positive charge, and freezes paid API capacity before returning
from an applied non-clean result.

The first increment accepts one bounded, provider-neutral JSON contract. It is
offline and performs no provider, model, billing API, or network call. Preview
is the default and writes nothing. Apply reparses the source, recomputes a
strict ledger snapshot while holding the spend-policy lock, stores only a safe
normalized projection, and persists a freeze for any drift, ambiguity,
incomplete statement, unsupported currency, or missing receipt identity.

An operator-normalized file is not provider-authenticated evidence. Its source
hash proves which bytes Deepr inspected, not who produced them. Such evidence
may explain an incident and may trigger a freeze, but it cannot by itself
authorize strict paid API recovery.

Paid recovery is a separate deterministic transaction. It requires a typed
freeze identity, one atomic exposure snapshot, current provider-account control
evidence, a content-addressed clean reconciliation bound to the current strict
ledger snapshot, complete coverage for every requested metered account, and a
bounded evidence lease. Setting a positive budget changes only the ceiling. It
never changes blocked capacity into authorized capacity.

## Goals

1. Explain every positive provider charge using durable local receipt evidence
   or identify it as unexplained.
2. Preserve provider statements without copying raw exports, credentials,
   prompts, responses, authorization headers, or endpoints into runtime state.
3. Use exact decimal or integer micro-USD arithmetic for proof-critical money.
4. Keep negative drift, credits, refunds, and local overestimates from restoring
   spend authority.
5. Make billing drift a cross-process freeze reason rather than a report-only
   warning.
6. Prevent stale evidence from clearing a newer freeze.
7. Keep local and proven plan-quota capacity available while paid API capacity
   is blocked.

## Non-goals

- Calling provider billing APIs in the first increment.
- Guessing unstable provider CSV or JSON formats.
- Treating equal timestamps, models, tokens, or dollar values as proof of a
  billing match.
- Writing invoice lines, credits, tax, or adjustments into the canonical cost
  ledger.
- Reducing canonical settled spend after a provider credit or negative drift.
- Enabling paid fan-out, autonomous provider tools, or metered expert chat.
- Claiming control of calls made by another application or credential.

## Threat model

The contract must fail closed for:

- malformed, duplicate-key, oversized, deeply nested, or non-UTF-8 input;
- unknown fields that could conceal a cost or secret;
- naive or inverted time windows;
- floating-point money, non-finite values, unsupported currencies, or totals
  whose components do not sum exactly;
- provisional or incomplete provider statements;
- duplicate or conflicting receipt identities;
- an imported provider or account scope different from the operator's
  expectation;
- an unreadable, conflicting, or non-durable local cost ledger;
- concurrent policy mutation, reservation, settlement, or import;
- evidence imported before the current freeze or replayed for a later freeze;
- expired account-control evidence;
- incomplete metered-account coverage;
- account controls that permit overage or exceed the operator budget;
- atomic-write or fsync failure.

Errors report field paths and error classes, never rejected values.

## Import contract

`deepr-provider-billing-import-v1` is a closed JSON object with these sections:

```text
schema_version
kind
provider
billing_scope
statement
lines
```

`billing_scope` carries one required opaque, non-secret `scope_ref`. Optional
organization, project, workspace, subscription, account, and credential
fingerprint fields remain bounded identifiers. A credential fingerprint is a
one-way external identifier, never the credential itself.

`statement` contains a stable statement identifier, final or provisional
status, UTC period, USD currency in v1, source posture, and one signed decimal
net total.

Each billing line contains:

- a stable line identifier;
- category and capacity class;
- a UTC usage window;
- optional model, SKU, and pricing-tier identifiers;
- typed provider request, object, job, and client-correlation identifiers;
- bounded billed-unit components;
- signed decimal-string charge, credit, adjustment, tax, and net values.

The linked validator proves unique line IDs, component sums, statement sums,
time ordering, bounded cardinality, and secret-field rejection. JSON Schema
documents form. Python validation owns cross-field arithmetic and joins.

## Reconciliation contract

`deepr-provider-billing-reconciliation-v1` records:

- source and normalized payload SHA-256 values;
- the strict ledger snapshot SHA-256;
- provider, billing scope, period, and currency;
- finality, completeness, and provider-source posture from the statement;
- provider-authoritative, local-ledger, and net-drift totals;
- gross unexplained positive cost before credits or overestimates;
- match counts and typed match bases;
- bounded unmatched-provider and unmatched-ledger summaries;
- explicit authority limitations;
- status, freeze requirement, and freeze result;
- zero-network and zero-provider-call assertions.

The report is a derived, reproducible view. The safe normalized import is the
immutable evidence record. Raw provider exports remain outside Deepr's managed
runtime state.

## Matching rules

Matches use canonical provider equality plus one unique receipt identity in
this order:

1. provider HTTP request ID;
2. provider object ID;
3. provider job or object ID preserved in the ledger request field;
4. legacy provider request ID metadata;
5. client correlation ID.

Multiple provider lines may group to one local event. Their exact Decimal sum
is compared with the local event. Two identities resolving to different local
events, one identity resolving to multiple events, or an identity reused across
providers is ambiguous and non-clean.

Timestamp proximity, model equality, token equality, and equal price are
diagnostics only. They never establish a match.

## Drift rules

- Any unmatched positive metered charge contributes its full amount to gross
  unexplained positive cost.
- Any matched provider amount above its local event contributes the positive
  difference.
- Tax, fees, storage, cache, or tool charges without an explicitly settled
  local basis remain unexplained.
- Credits, refunds, negative adjustments, and local overestimates are reported
  separately and never offset a different unexplained positive line.
- A final USD statement is clean only when every positive metered line has one
  exact receipt join, no join is ambiguous, provider account scope is explicit,
  and gross unexplained positive cost is zero.
- Provisional, unsupported-currency, incomplete, ambiguous, or unmatched
  statements cannot authorize recovery.

## Storage

Runtime state lives beneath the canonical cost-data root:

```text
provider_billing/
  imports/<source-sha256>.json
  reconciliations/<source-sha256>-<ledger-sha256>.json
  reconciliations_by_hash/<reconciliation-sha256>.json
  account_evidence/<evidence-id>.json
  .lock
```

Files use content-addressed, Windows-safe names. Creation is atomic, fsynced,
and non-overwriting under one cross-process file lock. Identical replay is
idempotent. A path collision with different content is corruption and blocks
the operation.

## Preview and apply

The CLI contract is:

```text
deepr costs reconcile-billing PATH
deepr costs reconcile-billing PATH --json
deepr costs reconcile-billing PATH --apply
deepr costs reconcile-billing PATH --expect-provider PROVIDER
deepr costs reconcile-billing PATH --expect-scope-ref SCOPE
```

Preview:

1. Reads and validates the source under size and count limits.
2. Obtains a strict read-only ledger snapshot.
3. Computes and displays reconciliation.
4. Writes nothing and does not mutate the freeze.

Apply:

1. Acquires `spend_policy_lock`.
2. Re-reads and revalidates the source.
3. Recomputes the strict ledger snapshot and snapshot hash.
4. Computes reconciliation.
5. Persists a freeze under the same policy lock when status is non-clean.
6. Stores the safe normalized import and derived report atomically.
7. Returns nonzero for every risky, incomplete, unknown, or failed result.

There is no ignore-drift, tolerance, force, or automatic-unfreeze option.

Only positive `api_metered` lines may match canonical metered ledger events.
`prepaid_plan`, `owned_local`, and `unknown` net totals remain separate in the
report. Unknown positive charges remain fail-closed. Operator-normalized class
labels cannot prove that overage is disabled, so non-metered positive lines in
that posture produce an incomplete result rather than being mislabeled as API
drift or treated as recovery evidence.

## Freeze identity and recovery

Every persisted freeze receives:

- `freeze_id`;
- `freeze_kind`;
- `frozen_at`;
- required recovery predicates;
- recovery evidence IDs after a successful recovery;
- evidence-lease expiration.

Freeze kinds include manual, zero ceiling, cost-ceiling divergence, billing
divergence, account-control unknown, account-control expired, and
account-identity mismatch.

Recovery must execute in this order:

1. Acquire `spend_policy_lock`.
2. Re-read and validate the same freeze ID.
3. Obtain one atomic snapshot of settled spend, active holds, and unresolved
   post-dispatch holds.
4. Strictly read immutable account-evidence records and their exact
   content-addressed reconciliation reports.
5. Verify evidence was created after and binds to the current freeze.
6. Require each reconciliation to be clean, final, complete, USD, and bound to
   the same provider, account, scope, authenticated source, and current strict
   ledger snapshot.
7. Reload the immutable normalized import and reproduce the complete report
   with deterministic reconciliation code. A stored `status: clean` field is
   never accepted as an assertion by itself.
8. Require the statement period to cover the evidence observation and every
   positive local event for that provider through the observation time.
9. Require complete coverage for every requested metered account.
10. Require provider-verified hard-limit or prepaid-no-overage evidence, then
   resolve and exactly match the current provider, account, scope, and external
   credential fingerprint.
11. Require zero positive billing drift and no unresolved post-dispatch hold.
12. Require aggregate account allocations not to exceed the operator ceiling.
13. Atomically clear the freeze and persist exact evidence IDs plus the
    earliest expiration.

Operator-attested and unknown control evidence is visible in status but does
not authorize strict recovery. `resolve_spend_caps` collapses paid authority to
zero after a recovery lease expires. A new positive drift or changed control
posture creates a new freeze ID, invalidating earlier evidence.

A locally constructed evidence document, source-posture label, and source hash
are never sufficient. Production remains blocked until a provider-specific
authenticated issuer and current account/credential identity resolver exist.
The current release intentionally ships neither hook.

Provider reporting delay prevents a universal freshness interval. A final
statement can lag recent activity even when its period end is current. Recovery
therefore requires the statement period to include `observed_at`, to cover
every positive local provider event through that instant, and to reconcile
against the exact current strict ledger snapshot. These checks prevent a stale
or changed local ledger from clearing a freeze, but they cannot prove that a
provider has finished reporting delayed external activity. A provider adapter
must establish that final and complete have that meaning for its authenticated
source before it can issue recovery evidence. No production adapter currently
does so, so paid recovery remains blocked.

`budget set` only changes the numeric ceiling. `budget set 0` creates a typed
zero-ceiling freeze. Raising the number preserves the freeze. `budget unfreeze`
delegates only to the recovery transaction and has no force path.

## Workflow and agent boundary

All import validation, receipt matching, arithmetic, storage, freeze behavior,
and recovery eligibility are deterministic workflow code because they govern
money and side effects. A model may help an operator interpret unmatched lines
outside this contract, but its judgment cannot create a match, alter a total,
mark evidence verified, or authorize spend.

## Rollout

1. Publish and validate the normalized import and reconciliation contracts.
2. Ship write-free preview and fail-closed apply with immutable storage.
3. Add freeze IDs, zero-ceiling persistence, and one atomic exposure snapshot.
4. Add typed account-control evidence and strict recovery evaluation.
5. Add provider-native read-only adapters only when their official exports or
   billing APIs expose stable, testable contracts.
6. Bind every metered dispatch to the exact provider account and credential
   fingerprint before any evidence can be labeled provider-verified.
7. Add durable threshold notification delivery and billing-import freshness
   monitoring.

Each step remains fail-closed if later steps are absent.

## Acceptance criteria

1. Preview performs no write, freeze mutation, network call, or provider call.
2. Apply revalidates source and ledger under the spend-policy lock.
3. All proof-critical money uses exact Decimal or integer micro-USD arithmetic.
4. No negative drift or credit reduces the canonical ledger or increases
   headroom.
5. Any unexplained positive charge, ambiguous join, provisional statement,
   unsupported currency, or incomplete coverage freezes paid API capacity.
6. Safe normalized evidence and derived reports are immutable, fsynced, and
   idempotent.
7. Secrets and raw prompts or responses are never persisted or echoed.
8. `budget set 0` followed by a positive setting remains frozen.
9. Unfreeze reads one atomic exposure snapshot and refuses active or unresolved
   post-dispatch holds.
10. Evidence from an earlier freeze cannot clear a newer freeze.
11. Evidence expiration blocks the next reservation and dispatch recheck.
12. Missing, non-clean, stale, or ledger-mismatched reconciliation evidence
    cannot clear a freeze.
13. Local and proven plan-quota capacity remain available throughout.

## Rejected alternatives

- Importing invoice lines into the canonical ledger. Credits are negative,
  invoice categories differ from execution events, and doing so would mutate or
  double-count local spend truth.
- Guessing matches from amount, model, timestamp, or token similarity. Those
  are diagnostics, not receipt identity.
- Letting credits offset unrelated unexplained charges. This can hide an
  unauthorized call.
- Treating a source SHA-256 as provider authentication. It proves file identity
  only.
- Allowing operator confirmation or a force flag to bypass missing evidence.
- Using a shared append-only JSONL without cross-process serialization.
- Clearing a freeze merely because the calendar month changed.
