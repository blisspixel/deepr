# Metered expert chat re-enable gate

Status: blocked in v2.42. Last reviewed: 2026-07-31.

Offline maximum-charge evaluation lives in
`deepr.experts.maximum_charge_contract`. A complete offline verdict is
necessary but not sufficient for re-enable. Runtime flags
`METERED_EXPERT_CHAT_EXECUTION_ENABLED` and
`MAXIMUM_CHARGE_CONTRACT_RUNTIME_PROVEN` both remain false until a reviewed
source change after live provider overage-off observation.

Metered expert chat cannot be enabled by configuration, a feature flag, or
`DEEPR_ALLOW_METERED_EXPERT_CHAT`. The runtime gate always refuses paid chat,
streaming, Grok web and X research, paid fallback, background deep research,
and deep-research retrieval before provider work. Local and proven zero-dollar
plan capacity remain available.

The former design was insufficient. A fixed average estimate plus an output
token cap did not price serialized chat history, reasoning, tools, cache writes,
hosted storage, background work, or provider-side retries. Final usage could
only reveal an overrun after billing. Post-bill detection is observability, not
a hard ceiling.

## Required proof before re-enable

One reviewed transaction must prove all of the following before any provider
call:

1. One parent dollar ceiling covers the initial turn, every tool-loop turn,
   streaming, compaction, embeddings, storage, fallbacks, and cleanup.
2. The request binds conservative serialized input, output, reasoning, tool,
   cache, retry, redirect, storage, and background-job maxima.
3. The provider enforces a maximum charge or every billable unit has an exact
   pre-dispatch maximum. An average or expected cost is rejected.
4. Deepr owns construction of the SDK client with retries disabled, redirects
   disabled, environment proxy and endpoint overrides rejected, and an
   official priced endpoint pinned.
5. An opaque one-use attestation binds the concrete client, provider, model,
   endpoint, account, billing scope, credential identity, request digest, and
   durable reservation.
6. Paid overage is proven disabled or an authenticated provider hard limit is
   no greater than Deepr's remaining monthly headroom.
7. Provider-returned model and account evidence match the reservation. Missing
   or mismatched identity consumes the full hold and freezes paid dispatch for
   reconciliation.
8. Cancellation, timeouts, malformed usage, partial streams, lost responses,
   process crashes, and ledger failures conservatively consume the hold without
   replay.
9. Concurrency cannot reserve more than the remaining per-job, daily, weekly,
   and monthly headroom. The absolute Deepr total ceiling remains `$5.00`.
10. Tests prove that no runtime variable, injected client, custom transport,
    proxy, base URL, fallback, or nested tool can bypass these controls.

## Acceptance

Re-enable only through a reviewed source change after the complete contract
passes unit, adversarial, cancellation, concurrency, packaging, and live
provider-control validation. The live check must estimate its own maximum cost
first and requires separate explicit authorization. Until then, the correct
result is a typed pre-dispatch refusal and `$0.00` provider spend.
