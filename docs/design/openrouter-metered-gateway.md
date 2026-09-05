# OpenRouter Metered Gateway

Status: accepted for visible/read-only preview and proof increments, updated
2026-09-02.

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

- Each preview model now names one provider route tag and prices that
  route rather than relying on the model-wide lowest price. A base provider
  tag excludes service-tier variants unless the request explicitly opts into
  one, but it is not immutable physical endpoint identity.
- `deepr providers openrouter-check` fetches only the seven fixed public
  endpoint documents. It sends no credential, follows no redirects, ignores
  ambient proxies, pins validated public addresses to the original TLS name,
  caps each response at 2 MiB, rejects duplicate JSON keys, and checks exact
  model and current endpoint metadata identity. This unauthenticated endpoint
  access is observed behavior, not a stable authenticated API contract.
- Base provider tags can match every non-tier variant under that provider. The
  checker applies those routing semantics and fails if a proposal would admit
  more than one standard endpoint metadata record. Opt-in `fast`, `flex`, and
  `priority` service-tier records do not enter the standard route set.
- The public proof covers endpoint status, the 128K input plus 16K output
  envelope, required `max_tokens` and `response_format` parameters, and every
  reachable prompt, completion, cache-read, cache-write, reasoning, and fixed
  request price override. Cache reads may not exceed the registered cached-input
  cap, reasoning tokens may not exceed the completion cap, and fixed request
  pricing must be zero. Negative discount markups, malformed discounts, and
  unclassified price fields fail closed.
- Every route has a finite cache-write ceiling and an explicit evidence source.
  The checker reads all endpoint `input_cache_write*` fields, including
  Claude's one-hour rate. When the endpoint omits them, it applies OpenRouter's
  documented free-write posture for xAI and Moonshot or prompt-equivalent
  posture for DeepSeek. A newly reported nonzero price cannot silently inherit
  the old zero cap.
- The proof publishes a digest of the proposed provider object. That object has
  one `order` tag, the same one-entry `only` list,
  `allow_fallbacks=false`, `require_parameters=true`,
  `data_collection=deny`, prompt and completion `max_price` caps, and a zero
  fixed-request-price cap.
- The proposed request posture sends `X-OpenRouter-Cache: false` to disable
  OpenRouter response caching and `X-OpenRouter-Metadata: enabled` to expose
  the router's actual attempt, selected provider display identity, BYOK posture,
  and material pipeline stages. Cache replays omit router metadata, so both headers are
  required together. The request forbids explicit prompt-cache controls,
  fallback models, media, plugins, presets, server tools, deprecated usage
  opt-in parameters, and background execution. Usage is returned
  automatically. Response caching and upstream prompt caching are separate
  mechanisms.
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
  enough remaining headroom, consistent current-month usage arithmetic, and a future expiry
  when an expiry exists.
- The provider can validly return `null` for `limit`, `limit_remaining`, and
  `limit_reset`. `deepr-openrouter-key-control-v2` preserves those nullable
  values, treats them as insufficient hard-limit evidence, and renders them as
  not set rather than `$0.00`.

`data_collection=deny` is not a zero-data-retention promise. A future adapter
must expose the admitted retention posture. Adding `zdr=true` globally would
make several registered first-party routes unavailable, so the preview does
not silently add it. The `xai/zdr` tag is the only currently registered route
whose name itself selects a ZDR variant.

OpenRouter BYOK is a separate billing boundary. Applicable BYOK endpoints are
prioritized ahead of shared capacity and cannot currently be disabled per
request. The current-key `include_byok_in_limit` field can improve budget
visibility, but it does not prove that the upstream provider account has a hard
ceiling or that its separate bill is settled. Executable shared-capacity work
therefore also requires an authenticated management observation proving that
no applicable BYOK credential exists.

Workspace defaults are another pre-dispatch boundary. Default plugins can run
when the request omits them, and an administrator can prevent request-level
overrides. A future adapter therefore needs fresh authenticated evidence for a
dedicated workspace with no applicable default plugins, presets, routing
defaults, or guardrails. Detecting a pipeline stage after the response is
necessary for settlement, but it is too late to prevent a paid side effect.

The public route proof and current-key observation both explicitly return
`dispatch_authorized=false`. The key endpoint is not a final, complete billing
statement, the generic account-control gate does not consume this observation,
and no OpenRouter inference client exists.

## Live no-inference validation

The 2026-09-04 recheck passed all seven public routes. The current-key check
reached the expected refusal for a non-monthly, BYOK-excluded key above the
`$5` ceiling. Both checks reported no paid requests and no dispatch authority.
Regression fixtures additionally cover prior-month spending, a just-reset
month, inconsistent monthly counters, and numerically unrepresentable USD.

OpenRouter defines `usage` and `byok_usage` as lifetime totals and their
`*_monthly` counterparts as current UTC month totals in its
[official key schema](https://github.com/OpenRouterTeam/terraform-provider-openrouter/blob/main/docs/data-sources/api_key.md).
Only the monthly counters reconcile a monthly limit's remaining headroom.
Lifetime totals need not equal that month's spend. Each monthly counter must
still fit within its corresponding lifetime total; this correction does not
relax the limit, BYOK, expiration, or dispatch gates.

The 2026-09-02 validation exercised every shipped path without an inference
request:

- all seven public provider-route checks passed current endpoint, parameter,
  context, and price-class validation;
- the Qwen 3.8 Flash preview produced a `$0.15696` maximum envelope and the
  Claude Sonnet 5 preview produced a `$2.784` maximum envelope, with web search
  and Code Interpreter disabled;
- the current-key endpoint returned a valid `limit_reset: null`. The v1 parser
  incorrectly rejected it as non-text. The v2 parser now reaches the actual
  posture verdict and reports a non-monthly reset, a limit above Deepr's `$5`
  ceiling, and BYOK-excluded accounting as separate failures;
- every result reported zero inference requests, zero paid requests, and no
  dispatch authority.

This validates discovery, parsing, pricing, and refusal behavior. It does not
validate model answer quality, provider completion behavior, or final billing.

## Executable adapter requirements

OpenRouter dispatch remains blocked until one adapter proves all of these
properties for the exact attempt:

1. The current credential resolves to the same key identity admitted by the
   account-control evidence.
2. The current key reports a finite USD limit and enough `limit_remaining`.
   Authenticated management evidence proves no applicable BYOK credential can
   override the shared-capacity route and no account or workspace default can
   force a paid plugin, preset, route, service tier, or guardrail.
3. The payload names one exact model slug, one allowed upstream provider,
   `allow_fallbacks=false`, `require_parameters=true`, and a `max_price` no
   greater than Deepr's registered prompt, completion, and zero fixed-request
   ceilings. It also sends both request headers and contains none of the
   forbidden request features or nested prompt-cache controls.
4. Model fallback aliases, automatic model routing, paid server tools,
   plugins, web search, media, file storage, response state, service tiers, and
   background execution are absent.
5. Router metadata reports the requested exact model, `strategy=direct`,
   `attempt=1`, exactly one selected admitted provider/model, `is_byok=false`,
   and no pipeline stage. The response and generation record agree on model and
   provider display identity, but neither is claimed to expose the endpoint
   tag. The served tier is `default` or null, `num_fetches=0`,
   `num_search_results=0`, and no preset.
6. Automatically returned usage is captured completely, but an absent detailed
   field is unknown rather than zero. Immediate finite `usage.cost` is
   mandatory, remains within the hold, and agrees with generation
   `total_cost`. All present token, reasoning, cache, media, and tool details
   plus response and generation identities settle the append-only Deepr ledger.
   Deprecated usage opt-in parameters are not sent.
7. `X-OpenRouter-Cache-Status` is absent. `HIT` is rejected because it strips
   router metadata and zeroes usage; `MISS` is rejected because it proves
   response caching was enabled and the response was stored.
8. Retry count, input, output, serialized bytes, and the full request graph
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
3. Verify router metadata and generation metadata against the complete
   acceptance contract above. Use the `X-Generation-Id` response header for
   post-mortem reconciliation when an error lacks router metadata. Verify that
   response-cache and prompt-cache evidence matches the admitted request
   posture. The official response schemas currently do not expose the selected
   endpoint tag, so execution remains blocked until the composite route evidence
   is sufficient for the reviewed provider-family contract.
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
