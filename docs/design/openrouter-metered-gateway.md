# OpenRouter Metered Gateway

Status: accepted for visible/read-only preview and proof increments, updated
2026-09-01.

## Problem

OpenRouter exposes many model families behind one OpenAI-compatible API and
uses exact, provider-qualified model slugs. That is useful for comparing
models that Deepr cannot reach through its current direct-provider adapters.

It also adds a second routing and billing boundary. By default OpenRouter can
load-balance one model across upstream providers and fall back when an endpoint
fails. Its model catalog reports the lowest available price structure, not a
durable maximum for every upstream endpoint. A working API key and a Deepr
budget therefore do not prove the provider route or maximum marginal charge.

## Initial Decision

Ship OpenRouter first as an exact-model, write-free research preview:

- Register a small dated catalog of exact OpenRouter model slugs from several
  model families.
- Mark every entry preview-only so automatic routing, expert routing, and
  benchmark evaluation cannot select it.
- Permit `deepr research --provider openrouter --model <slug> --preview` to
  calculate Deepr's finite request envelope with all tools disabled.
- Refuse the same route before reservation or provider construction when
  `--preview` is absent.
- Do not automatically load `OPENROUTER_API_KEY`, construct an OpenRouter
  inference client, or call an inference endpoint in this increment.

The initial catalog rates were a dated proposal for the future request's
`max_price` constraint. They were not a claim that OpenRouter's lowest
advertised route would remain available.

## Accepted Proof Increment

The 2026-09-01 increment closes two prerequisites without enabling inference:

- Each preview model now names one exact upstream endpoint tag and prices that
  endpoint rather than relying on the model-wide lowest price.
- `deepr providers openrouter-check` fetches only the seven fixed public
  endpoint documents. It sends no credential, follows no redirects, ignores
  ambient proxies, pins validated public addresses to the original TLS name,
  caps each response at 2 MiB, rejects duplicate JSON keys, and checks exact
  model and endpoint identity.
- The public proof covers endpoint status, the 128K input plus 16K output
  envelope, required `max_tokens` and `response_format` parameters, and every
  conditional prompt, completion, and cache-write price override reachable by
  that input ceiling.
- Every route has a finite cache-write ceiling and an explicit evidence source.
  The checker reads all endpoint `input_cache_write*` fields, including
  Claude's one-hour rate. When the endpoint omits them, it applies OpenRouter's
  documented free-write posture for xAI and Moonshot or prompt-equivalent
  posture for DeepSeek. A newly reported nonzero price cannot silently inherit
  the old zero cap.
- The proof publishes a digest of the proposed provider object. That object has
  one `order` tag, the same one-entry `only` list,
  `allow_fallbacks=false`, `require_parameters=true`,
  `data_collection=deny`, and prompt and completion `max_price` caps.
- The proposed request posture sends `X-OpenRouter-Cache: false` to disable
  OpenRouter response caching and forbids explicit prompt-cache controls,
  fallback models, plugins, presets, server tools, and background execution.
  Response caching and upstream prompt caching are separate mechanisms.
- Because OpenRouter's provider `max_price` object does not include a
  cache-write cap, Deepr's preview envelope adds a full-input cache-write charge
  to ordinary no-cache input. This remains conservative if the provider treats
  those buckets as alternatives.
- `deepr providers openrouter-key-check` exposes no key argument. It accepts a
  key through a hidden prompt by default. Explicit `--from-env` uses an
  already-quarantined process copy when available or parses only
  `OPENROUTER_API_KEY` from the bounded checkout-local `.env` without exporting
  it. It never unquarantines or exports that value or passes it to a child. The
  command makes one authenticated read-only request to `/api/v1/key`, binds a
  deterministic domain-separated scrypt credential fingerprint to the
  response, and emits only hashed account and label references.
- The key observation requires a non-management, non-provisioning, paid-tier
  key with a BYOK-inclusive monthly limit at or below Deepr's `$5` ceiling,
  enough remaining headroom, consistent usage arithmetic, and a future expiry
  when an expiry exists.

The public route proof and current-key observation both explicitly return
`dispatch_authorized=false`. The key endpoint is not a final, complete billing
statement, the generic account-control gate does not consume this observation,
and no OpenRouter inference client exists.

## Executable adapter requirements

OpenRouter dispatch remains blocked until one adapter proves all of these
properties for the exact attempt:

1. The current credential resolves to the same key identity admitted by the
   account-control evidence.
2. The current key reports a finite USD limit and enough `limit_remaining`,
   with BYOK usage included if BYOK is allowed at all.
3. The payload names one exact model slug, one allowed upstream provider,
   `allow_fallbacks=false`, `require_parameters=true`, and a `max_price` no
   greater than Deepr's registered prompt/completion ceiling. It also sends the
   response-cache disable header and contains none of the forbidden request
   features or nested prompt-cache controls.
4. Model fallback aliases, automatic model routing, paid server tools,
   plugins, web search, file storage, and background execution are absent.
5. The response identifies the actual model and upstream provider, and every
   reported prompt, completion, reasoning, cache read, cache write, tool, and
   total-cost bucket settles the append-only Deepr ledger.
6. Retry count, input, output, serialized bytes, and the full request graph
   remain under one durable parent reservation.

The current-key observation now binds the credential used for that read-only
request to its live limit response. It still needs a reviewed verifier that
joins the observation to stored account policy, the exact dispatched request,
the durable parent, and final billing evidence. A management key is not required
merely to make inference work and must not become runtime authority.

## Remaining Proof Gap

The following work remains ordered behind v2.53:

1. Adopt `DurableParentBudget` for the exact OpenRouter attempt and bind the
   complete request digest before any network dispatch.
2. Construct one Deepr-owned client with zero SDK retries, no redirects, no
   ambient proxies, the official gateway endpoint, and the prompted credential
   fingerprint from a fresh control observation.
3. Verify the immediate response and generation metadata report the admitted
   exact model and upstream provider tag, no server tools, and no additional
   fetches. Verify that response-cache and prompt-cache evidence matches the
   admitted request posture.
4. Settle reported total cost and provider receipt identifiers into both the
   child and append-only canonical ledger. Unknown or conflicting evidence must
   consume the full hold and freeze the parent for reconciliation.
5. Reconcile the provider's final billing export or authenticated complete
   statement before account-control evidence can recover or extend authority.

## Alternatives rejected

### Treat OpenRouter as another OpenAI base URL

Rejected. API shape compatibility does not bind the upstream provider,
fallback behavior, price, account controls, or settlement receipt.

### Enable dispatch after one live API-key smoke test

Rejected. A successful paid request proves connectivity and present balance,
not a hard provider ceiling, credential identity continuity, or no-fallback
behavior. It would also violate the current production metered quarantine.

### Import the full live model catalog

Rejected. The catalog is large and mutable, and its lowest-price fields are not
execution authority. The shipped proof reads only seven fixed model endpoint
documents and never adds or changes a registry entry automatically.

## Verification

No-network tests must prove exact slug resolution, conservative cache-write
preview pricing, disabled tools, exclusion from all routing and evaluation
candidates, dispatch refusal before any reservation or provider construction,
exact proposed routing shape, strict untrusted metadata parsing, every reachable
price class, secret-safe key observation, and explicit non-authority. A live
public metadata check may verify current route eligibility with no key.
Documentation must continue to label OpenRouter as visible/read-only.
