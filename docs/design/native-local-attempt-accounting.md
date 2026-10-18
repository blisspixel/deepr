# Native local generation attempt accounting

Date: 2026-10-18. Scope: the retained local-consult ledger finding.

A native Ollama consult can return an answer and a consult trace without an
append-only cost event. The same transport serves study and investigation.
The rehearsal separately records a pre-call marker, so adding another recorder
in the CLI would miss other callers and duplicate rehearsal attempts.

## Decision

The native completion boundary owns content-free, durable `$0` accounting.
Each invocation gets a unique attempt ID, with an optional caller correlation
ID for a rehearsal call. It records an intent before validation/probes, a
dispatch marker after cloud/model attestation and immediately before the POST,
and a terminal event before returning or propagating failure/cancellation.
The dispatch marker means transport may have begun, not that the daemon
received it. An interrupted attempt without a terminal event remains uncertain.
Preflight-only inspection keeps its existing read-only behavior.

Each event uses the existing configured CostLedger with bounded locking and
fsync. Failure to record intent or dispatch stops further work. Failure to
record a terminal event surfaces an accounting error and preserves the earlier
marker. No response is reported as successfully settled after that failure.
The ledger records model identity/digest, status, correlation, token counts when
available and exception type, never prompts, source bytes, answers, URLs or raw
exception text. Accounting does not widen network, model, spend or write authority
for expert knowledge. Repeated calls are distinct attempts, even if a caller
reuses a correlation ID.

Rehearsal worker and warm-up calls use this same boundary instead of writing a
second attempt. Workers retain their full research artifacts separately. The
orchestrator mirrors native events by their original idempotency keys and keeps
the existing legacy-record reader for retained older trials. Event counts are
not model-call counts; an attempt has multiple lifecycle records. Reconciliation
and interrupted-attempt summaries count distinct native attempt IDs, with the
legacy one-event representation preserved for older trials.

## Rejected alternatives

- CLI-only logging misses MCP, A2A and direct callers of the shared factory.
- Success-only logging loses refused, failed and killed attempts.
- Optional accounting or a caller bypass recreates an unrecorded transport.
- Keeping both worker and native attempt writers counts one call twice.
- Logging content in billing metadata copies sensitive research unnecessarily.

## Verification

Reproduce the missing record against the earlier backend. Exercise successful
responses, proof refusal, invalid requests, transport/malformed-response errors,
cancellation and failures at each persistence phase. Confirm dispatch never
precedes its durable marker, failed attestation never reuses a previous digest,
and read-only preflight creates no ledger. Exercise actual native worker
accounting and repeated mirroring, including a legacy interrupted attempt.
A small isolated live `$0` consult may validate wiring after offline checks;
it cannot qualify answer quality, S0 or a new model default.
