# Research cost reservation safety

Date: 2026-07-09, absorber and provider-lifecycle extensions 2026-07-12
Status: implemented

## Context

REST and web submissions can run in different processes from the worker that
settles provider usage. A process-local budget check cannot prevent concurrent
processes from overcommitting one daily ceiling, and a provider POST can be
accepted even when its response is lost. The cost ledger is append-only, while
queue state and reservations use SQLite, so completion cannot rely on a single
cross-file transaction.

## v2.36 Scope Correction

The shared provider-research and metered absorber reservation contracts below
remain implemented. A release safety audit found that several higher-level
expert lifecycle commands still compose calls, hosted storage, and tools
outside one durable parent-run transaction. v2.36 therefore gates nonlocal
`expert make` and `--learn`, API curriculum `expert plan`, provider-backed
`expert refresh` and `--synthesize`, API `fill-gaps` including consensus and
deep modes, API `expert sync --compile-claims`, and paid
`deepr eval calibrate --corpus` before provider work.

Re-enable each surface only after every nested call uses the shared durable
reserve, dispatch-mark, and required settlement wrapper; all storage and tool
side effects are priced; and the parent run ceiling survives cancellation,
concurrency, replay, and ledger failure. Local and explicit plan-quota expert
paths and `$0` `deepr eval calibrate --from` remain available.

## Decision

Provider-backed REST, web, direct CLI, MCP, and internal single-job orchestrator
research reserves the maximum estimate before provider submission for the
bounded surfaces that remain enabled. In v2.36,
hosted document upload, file search, and vector-store creation or attachment
fail before provider work because their complete storage lifecycle is not yet
priced. Metered batch, campaign, team, and prepared multi-call execution also
fails before paid work until every nested call belongs to one durable parent
reservation. Automatic cross-provider metered fallback is disabled until each
provider attempt owns a separate reservation and the full retry envelope is
approved.
Paid synchronous planning calls also reserve that full ceiling, then settle
provider-reported token usage. `research_reservations.db` serializes active
holds with
`BEGIN IMMEDIATE`, and the reservation commit occurs while holding the same
cross-process lock used by the JSONL cost ledger. This makes the ledger snapshot
and hold commit one ordered critical section across API, web, and worker
processes.

Metered `ReportAbsorber` calls use the same durable boundary. Extraction and
every routed contradiction, dedup, or optional conflict-adjudication verdict
reserve before dispatch, then settle provider-reported usage into the canonical
cost ledger. The caller supplies one run ceiling to `absorb`; before every
dynamic dispatch the absorber requires enough remaining headroom for that
call's conservative hold. Provider-reported settlement is accumulated across
the run and returned as `actual_cost`, while missing usage consumes the held
amount. A budget denial therefore happens before the next provider call, and a
settlement above the approved run ceiling fails closed. Optional adjudication
uses an injected, budgeted completion seam and cannot write a contested belief
when its reservation fails.

The reservation is also enforced in the provider request. Metered absorption
requires an exact OpenAI registry pricing contract, computes a conservative
input-token ceiling from UTF-8 bytes plus fixed chat-protocol allowance, and
derives `max_completion_tokens` from the remaining per-call dollars and model
output price. The request is refused before client construction when the input
plus one output token cannot fit, the model is unknown, pricing is nonpositive,
or the request model differs from the accounted model. Post-settlement checks
remain defense in depth rather than the first point where an overrun is found.

A nonzero absorber cost estimate means metered capacity and enables this
boundary; local Ollama and prepaid plan-quota callers must pass
`estimated_cost=0.0`, which keeps their existing direct `$0` path and reports
zero actual cost. A metered-at-margin CLI is not a prepaid plan-quota caller: it
remains execution-blocked until its adapter can estimate, reserve, settle
usage, and write the canonical cost ledger. The absorber owns this accounting so
direct CLI absorb, MCP absorb, OKF import, gap fill, calibration, and the
default API-backed sync absorption path cannot drift into separate partial
implementations. Direct CLI, MCP, sync, and gap-fill callers pass their approved
remaining ceiling into the absorber and use settled aggregate cost for run and
profile totals. Paid dry runs record spend without advancing knowledge
freshness. Callers must not duplicate ledger writes for absorber model calls.

The older standalone conflict-resolution CLI and web endpoint are blocked
before store or provider construction. Their budget limited pair count but did
not cover model-based detection, adjudication, or consensus dispatch. They stay
blocked until all three stages use this reservation contract, an explicit
confirmation, bounded provider requests, and aggregate settlement. The `$0`
contested read view remains available.

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

Immediately before that queue claim, every queue-backed provider dispatch
restores reservation identity from the queued metadata and verifies the exact
reservation ID, job ID, provider, model, and maximum held cost against one
active job-owned row in `research_reservations.db`. An in-memory reservation is
not dispatch authority by itself. Missing, closed, malformed, or mismatched
identity marks the job failed before any provider POST. A transient reservation
store read failure leaves the job queued and the possible hold intact so a
later retry can repeat the same check without surprise spend.

The persisted `ResearchJob.provider` is the authority for every later provider
side effect. Web polling constructs that recorded adapter for status reads and
threads the same provider ownership into terminal cleanup. Cost-reservation
restoration and unreserved completion settlement also use the recorded
provider, not an interface default. An unknown, unsupported, or temporarily
unconfigurable provider remains active and visible for operator recovery; the
poller records a safe diagnostic and never probes, cancels, cleans, or falls
back through a different provider adapter.

The shipped dashboard research submission path is OpenAI-only. Single and
batch submissions therefore accept only the explicit OpenAI subset of the web
model allowlist, set `ResearchJob.provider="openai"`, and reject a model from a
different provider family before reservation or provider construction. Future
multi-provider web submission requires an explicit provider field plus a
provider/model compatibility contract; model-name guessing is not routing.

Synchronous OpenAI planning clients set SDK `max_retries=0`. Those calls do not
carry a supported application idempotency key, so retrying inside the SDK would
hide multiple paid POST attempts behind one reservation outcome.
The lazily constructed OpenAI absorber client also sets `max_retries=0` for the
same reason. A reservation or canonical settlement failure aborts absorption;
contradiction and dedup's conservative semantic fallback does not swallow a
money-path failure. A definite provider rejection refunds its hold. An
ambiguous provider exception settles the held maximum even when a semantic
verdict later falls back to unverified.
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
- A transient pre-dispatch reservation read failure leaves the job queued and
  makes no provider call. Deterministic missing or mismatched identity fails the
  job and releases only the expected job's hold.
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
- Legacy cleanup remains available for provider files and vector stores created
  by earlier releases. New hosted storage creation and attachment are gated in
  v2.36 before any provider side effect.
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
