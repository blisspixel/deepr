# Cost and budget guidance

## Core rules

1. A budget is a hard ceiling, not a target or fixed quote.
2. Preview and dispatch must use the same finite request envelope.
3. Reserve the maximum before provider dispatch.
4. Durably mark the provider boundary before the call.
5. Settle exact reported usage when valid; otherwise settle the conservative
   reserved bound after an ambiguous provider outcome.
6. Write every spend source to the append-only canonical ledger.
7. Never retry or switch metered providers without a separate approved
   reservation.

Do not use static "typical cost" tables as authorization. Pricing, context
limits, built-in tool charges, provider-request count, output ceilings, and
serialized payload size determine the current hard envelope.

## Capacity classes

| Capacity | Deepr dollar ledger | Important caveat |
|----------|---------------------|------------------|
| Local Ollama | `$0` | Consumes local hardware and may be busy |
| Non-metered plan CLI | `$0` | May consume subscription quota or credits Deepr cannot prove |
| Metered-at-margin CLI | Blocked | Requires complete estimate/reserve/settle support |
| Bounded provider API | Actual or conservative settlement | Requires explicit approval and positive ceiling |

Copilot is visible/read-only in v2.36. CLI presence is never proof of free
remaining quota.

## Before a paid call

- State the selected provider, model, tools, and budget ceiling.
- Explain that final cost can be lower, but cannot exceed the admitted bound.
- Obtain explicit user approval.
- Submit one bounded job.
- Preserve reservation and trace identifiers.

If the current model/tool combination is unpriced or request-unbounded, stop.
Do not estimate from a similar model or remove a guard to make the call pass.

## After a call

- Report actual settled cost and cumulative task spend.
- If the outcome is ambiguous, say that the conservative ceiling may have been
  charged in Deepr's ledger.
- Reconcile provider-reported usage when the adapter supports it.
- Do not call a fallback provider automatically.

## Multi-call work

Metered batch, campaign, team, continuation, prepared, and autonomous runs are
gated until one durable parent reservation covers every nested call and each
child settles exactly. `$0` previews do not authorize execution.

Hosted file upload, indexing, search, vector retention, retrieval, and cleanup
are also gated until those lifecycle costs fit the same reservation.

## Local waits

A scheduled local `busy` result costs `$0` and records the next action. Report
the retry time and stop. Do not wait in-process for hours and do not fall
through to plan or API capacity.
