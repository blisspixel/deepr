# Research cost reservation safety

Date: 2026-07-09
Status: implemented

## Context

REST and web submissions can run in different processes from the worker that
settles provider usage. A process-local budget check cannot prevent concurrent
processes from overcommitting one daily ceiling, and a provider POST can be
accepted even when its response is lost. The cost ledger is append-only, while
queue state and reservations use SQLite, so completion cannot rely on a single
cross-file transaction.

## Decision

Provider-backed REST, web, direct CLI, campaign-batch, MCP, and internal
orchestrator research reserves the maximum estimate before provider
submission. Direct CLI admission also precedes document upload and vector-store
creation, so provider-side preparation cannot occur after a rejected ceiling.
CLI fallback routes reserve the full configured per-call ceiling because the
eventual provider and model may differ from the initial route.
Paid synchronous planning calls also reserve that full ceiling, then settle
provider-reported token usage. `research_reservations.db` serializes active
holds with
`BEGIN IMMEDIATE`, and the reservation commit occurs while holding the same
cross-process lock used by the JSONL cost ledger. This makes the ledger snapshot
and hold commit one ordered critical section across API, web, and worker
processes.

Settlement appends the canonical `job:<id>:completion` event before closing the
durable hold. Queue result persistence uses the same key for the initial cost
and a distinct correction key only for later positive deltas. If either side
finishes first, reconciliation closes a hold from the canonical event. Before a
new submission, terminal or missing queue records repair orphaned holds. A
missing queue record is settled at the held maximum after a grace interval, not
refunded, because provider acceptance cannot be disproved.

Provider submission carries one stable idempotency key through retries only
when the provider exposes a supported server-side idempotency contract.
Adapters without such a contract make one creation attempt and do not replay an
ambiguous paid operation. Definitive rejection refunds the hold. Connection
loss or timeout is an ambiguous outcome and settles the maximum estimate
conservatively. Queued cancellation and provider dispatch compete through one
SQLite compare-and-set transition, so a stale queued snapshot cannot refund a
claimed submission. Accepted cancellation closes provider work first, then
cost state, then queue state. The modern CLI may route a definitive rejection
to another provider under the same ceiling, but suppresses fallback when the
first provider may have accepted work.

Synchronous OpenAI planning clients set SDK `max_retries=0`. Those calls do not
carry a supported application idempotency key, so retrying inside the SDK would
hide multiple paid POST attempts behind one reservation outcome.
Campaign context summaries, research review/planning, context-index embeddings,
and explicit semantic context queries use the same rule. Automatic context
discovery before research confirmation remains keyword-only and makes no model
call.

## Rejected alternatives

- Process-local counters and locks do not coordinate independent services.
- Reserving expected cost admits combinations whose maximum outcomes exceed a
  hard budget ceiling.
- Releasing every submission exception treats an accepted request with a lost
  response as free and creates a silent-money path.
- Giving JSONL and SQLite separate locks leaves a race between the spend
  snapshot and hold insertion.
- Expiring all old active holds is unsafe because valid deep research can be
  long-running. Reconciliation requires terminal queue or canonical ledger
  evidence.

## Failure and recovery contract

- A ledger write failure leaves the durable hold active.
- A queue completion event with the canonical key repairs a failed settlement.
- A terminal queue record is reconciled before the next paid submission.
- An accepted cancellation without reported usage settles the held maximum.
- A CLI polling boundary attempts provider cancellation. If cancellation cannot
  be confirmed, the queue remains processing and the durable hold stays active
  for later polling or reconciliation.
- A queued cancellation closes cost only after its queued-to-cancelled
  compare-and-set wins against the dispatch claim. It refunds when no provider
  preparation occurred; otherwise it cleans created resources and settles the
  held maximum conservatively.
- Duplicate settlement and queue result writes are idempotent across processes.
- Provider files and vector stores created after admission are deleted on a
  pre-submit rollback. The held maximum is still settled because deletion does
  not prove that provider-side preparation incurred no charge.
- Successful direct-CLI jobs persist provider file identifiers and delete files
  and vector stores during immediate or worker completion. OpenAI-compatible
  vector stores also expire one day after last activity if cleanup is missed.
- Synchronous campaign commands poll accepted jobs through the worker's shared
  finalization path. A bounded-wait cancellation that cannot be confirmed keeps
  both processing state and its hold active.
- Expert claim validation uses durable metered admission in both CLI and MCP
  surfaces; its SDK client has retries disabled because the request has no
  provider idempotency contract.

## Current external guidance

- The official OpenAI Python SDK documents automatic retries for connection,
  timeout, 408, 409, 429, and server errors, and its request implementation
  creates one idempotency key that is reused across retry attempts. Reviewed
  2026-07-09:
  <https://github.com/openai/openai-python>
- The current Azure OpenAI Responses guidance documents background response
  polling and idempotent cancellation. Reviewed 2026-07-09:
  <https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses>
- The current Azure OpenAI quota guidance confirms SDK exponential retry for
  transient failures and recommends retry-delay handling for throttling.
  Reviewed 2026-07-09:
  <https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota>
- The Google Gen AI Python SDK documents streaming generation but does not
  expose an idempotency parameter for `generate_content_stream`; Deepr therefore
  does not apply an application retry to that paid operation. Reviewed
  2026-07-09:
  <https://googleapis.github.io/python-genai/genai.html>

## Consequences

The reservation database and ledger lock file are machine-local cost-control
state under `DEEPR_COST_DATA_DIR`. Reservations fail closed when either store is
unavailable. Conservative settlement can overstate a cancelled or ambiguous
request, but it cannot silently understate potential provider spend. Operators
can compare later provider invoices and append an explicit correction through
the existing cost reconciliation workflow.
