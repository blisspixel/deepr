# Cost and budget guidance

## Core rules

Production paid dispatch is currently blocked. The transaction rules below
describe required controls, not permission to execute. A wallet, positive
budget, or user approval cannot supply the missing provider account-control
and credential-identity verifier.

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
| Eligible non-metered plan CLI | `$0` | Requires proven auth, confinement, quota, and disabled paid overage |
| Metered-at-margin CLI | Blocked | Requires complete estimate/reserve/settle support |
| Bounded provider API | Preview and offline reconciliation | Production dispatch remains blocked despite approval or a positive ceiling |

Some plan adapters are visible but not executable. CLI presence is never proof of free
remaining quota.

## Inspect a metered preview

- State the selected provider, model, tools, and budget ceiling.
- Explain the maximum envelope and that the preview makes no paid request.
- Report the production dispatch block separately from local budget headroom.
- Preserve returned preview and evidence identifiers without inventing a job.

If the current model/tool combination is unpriced or request-unbounded, stop.
Do not estimate from a similar model or remove a guard to make the call pass.

## Inspect recorded settlement

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
