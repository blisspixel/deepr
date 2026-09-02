# Model Selection Guide

Status: current with Deepr v2.50.11. Last reviewed: 2026-09-02.

The source of truth for model IDs, pricing estimates, context windows, and
routing metadata is [src/deepr/providers/registry.py](../src/deepr/providers/registry.py),
with the preview-only OpenRouter catalog in
[src/deepr/providers/openrouter_catalog.py](../src/deepr/providers/openrouter_catalog.py).
This guide explains how to use that registry safely. Provider docs and prices
change faster than prose, so treat this document as an operating guide, not a
billing authority.

Direct-provider model docs checked through 2026-08-13. OpenRouter route and
current-key docs were checked through 2026-09-02:

- OpenAI Models and Pricing:
  <https://developers.openai.com/api/docs/models>,
  <https://developers.openai.com/api/docs/models/gpt-5.6-sol>,
  <https://developers.openai.com/api/docs/models/gpt-5.6-terra>,
  <https://developers.openai.com/api/docs/models/gpt-5.6-luna>
- Claude Platform Models, Pricing, and Thinking:
  <https://platform.claude.com/docs/en/about-claude/models/overview>,
  <https://platform.claude.com/docs/en/about-claude/pricing>,
  <https://platform.claude.com/docs/en/about-claude/models/whats-new-sonnet-5>,
  <https://platform.claude.com/docs/en/build-with-claude/extended-thinking>,
  <https://platform.claude.com/docs/en/release-notes/overview>
- Google Gemini Models and Pricing:
  <https://ai.google.dev/gemini-api/docs/models>,
  <https://ai.google.dev/gemini-api/docs/pricing>,
  <https://ai.google.dev/gemini-api/docs/generate-content/latest-model>,
  <https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/>
- xAI Models and Pricing:
  <https://docs.x.ai/developers/models>,
  <https://docs.x.ai/developers/pricing>
- Azure OpenAI and Azure AI Foundry:
  <https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure>,
  <https://learn.microsoft.com/azure/ai-foundry/agents/overview>
- OpenRouter models, provider routing, and current-key controls:
  <https://openrouter.ai/docs/guides/overview/models>,
  <https://openrouter.ai/docs/guides/routing/provider-selection>,
  <https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key>,
  <https://openrouter.ai/docs/guides/features/router-metadata>,
  <https://openrouter.ai/docs/cookbook/administration/usage-accounting>,
  <https://openrouter.ai/docs/guides/overview/auth/byok>,
  <https://openrouter.ai/docs/guides/features/service-tiers>

## 2026-08-13 Verification Matrix

| Provider | Current external signal | Deepr status | Action |
|----------|-------------------------|--------------|--------|
| OpenAI | Official API docs list GPT-5.6 Sol, Terra, and Luna as self-serve API models with published prices and limits. | All three are registered with cached-input and long-context pricing. Sol is the OpenAI task default. | Keep the exact tier visible in previews because the GPT-5.6 alias resolves to Sol and prompts above 272K input tokens cost more. |
| Anthropic | Claude docs list Fable 5, Opus 5, Sonnet 5, and Haiku 4.5 as current. Sonnet 5's $2/$10 launch price is now permanent. | All four are registered. Opus 5 is the research default and Sonnet 5 is the balanced default. Mythos remains invitation-only. | Use current first-party prices and keep limited-access Mythos outside automatic routing. |
| Google Gemini | Google released Gemini 3.6 Flash and Gemini 3.5 Flash-Lite as GA production API models on 2026-07-21. The same launch limits Gemini 3.5 Flash Cyber to a CodeMender pilot for governments and trusted partners. | Both GA API models are registered with standard pricing, cached-input pricing, context metadata, and the new thinking-level request shape. Flash Cyber is deliberately absent. Managed Gemini Deep Research remains gated because its autonomous loop lacks a complete request ceiling. | Use the GA API models for explicit bounded requests. Do not represent Flash Cyber as selectable Gemini API capacity. |
| xAI | Grok 4.6 launched on 2026-08-12. xAI also publishes Grok Build 0.1 and revived `grok-code-fast` aliases with current prices. | Grok 4.6 and Grok Build 0.1 are registered. Generic flagship aliases resolve to 4.6; quick routing can retain cheaper Grok 4.3. | Keep fast service tiers and server-side tools outside base estimates unless their separate charges are explicitly bounded. |
| Azure AI Foundry | Microsoft lists GPT-5.6 Sol, Terra, and Luna, but availability and billing remain deployment, quota, region, and service-tier dependent. | Azure entries remain tested deployment targets, not mirrors of every public OpenAI model. | Do not promote a catalog listing into Azure routing without deployment-specific pricing and adapter verification. |
| OpenRouter | Public endpoint metadata exposes provider tags, parameters, context, status, and price classes. A base provider tag can match non-tier variants. Router and generation metadata report provider display names, not the selected tag. BYOK can override ordering, while account defaults can force plugins. | Seven exact model slugs are preview-only. A no-key check requires one currently matched standard tag and bounded text-inference prices. An explicit-source check produces a sanitized key-control observation. Both deny dispatch authority. | Keep inference blocked until authenticated account controls exclude BYOK and paid defaults, the request and provider-route evidence are bound, total usage settles one durable parent, ambiguous outcomes freeze safely, and final billing reconciles. |

## Current External Watchlist

These are visible in current provider docs but are not automatic Deepr routing
defaults unless the registry, adapter behavior, cost settlement, and tests are
explicitly updated.

- Anthropic lists Claude Mythos 5 and the Mythos preview as limited
  availability. Keep them out of Deepr's public registry and auto-routing until
  API access and pricing are normal enough to test and settle.
- Gemini 3.6 Flash and Gemini 3.5 Flash-Lite are stable and registered. The
  provider omits deprecated sampling parameters for both and uses
  `thinking_level` instead of `thinking_budget`. A future migration from the
  supported generateContent seam to the preferred Interactions API requires a
  separate contract review for usage, tools, streaming, and settlement.
- Gemini 3.5 Flash Cyber is limited-access CodeMender capacity, not a general
  Gemini API model. It remains outside the registry unless Google later
  publishes ordinary API access, pricing, identifiers, and terms that Deepr can
  test and settle.
- Gemini also lists media models. Deepr's registry covers text and research
  backends; media models must stay explicit and cost-gated before any image or
  video path uses them.
- Google now lists `gemini-3-pro-preview` and
  `gemini-3.1-flash-lite-preview` in the shut-down previous-model set. Deepr
  keeps them only as deprecated migration entries for historical cost lookup.
- xAI offers a 2x-priced fast Grok 4.6 variant and separately billed
  server-side tools. Deepr registers standard token pricing only and does not
  silently select fast service or provider tools.
- xAI image, video, and voice surfaces are dedicated APIs with separate pricing.
  Deepr should continue treating xAI image generation as premium explicit
  capacity.
- Azure and Microsoft Foundry model availability is deployment and region
  dependent. A model appearing in Foundry docs is not enough to make it a
  globally selectable Deepr model.

Pricing notes:

- GPT-5.6 standard rates per MTok are `$5/$0.50/$30` for Sol,
  `$2.50/$0.25/$15` for Terra, and `$1/$0.10/$6` for Luna, in
  input/cached-input/output order.
- GPT-5.6 prompts above 272K input tokens use 2x input and cached-input rates
  plus 1.5x output rates for the full request. Deepr applies this boundary in
  both preflight and settlement pricing.
- Anthropic made Sonnet 5's $2 input and $10 output per MTok launch rates
  permanent. Deepr uses those current rates plus $0.20 cache hits and $2.50
  five-minute cache writes.
- Gemini free-tier and quota-inclusive entries are useful for setup guidance,
  but automatic routing still depends on the local Deepr capacity profile,
  provider keys, quota posture, and budget gates.

## Operating Rules

- Run `python scripts/discover_models.py --show-registry` to see the local
  registry. This command is offline and does not call providers.
- `deepr providers models` and live `python scripts/discover_models.py` remain
  gated because endpoint, proxy, retry, and account cost cannot be proven. Use
  official sources and an explicit reviewed registry change instead.
- `python scripts/discover_models.py --llm` is gated before any model
  call. Restore it only with an exact estimate, explicit approval, durable
  reservation, and canonical settlement.
- Use `deepr research ... --dry-run` or the web preflight estimate before any
  metered research.
- Prefer local Ollama and admitted plan-quota capacity for routine maintenance.
  Metered APIs are preview-only outside the narrow attended absorb transaction.
  Budget gates remain necessary but do
  not authorize production dispatch.
- Premium image generation is never a background default. Deepr only
  auto-selects local image endpoints for portraits; OpenAI, Gemini, and xAI
  image generation require explicit provider selection or the single premium
  auto opt-in `DEEPR_ALLOW_METERED_IMAGE_AUTO=1`.
- Treat official model listings as candidates until Deepr has registry pricing,
  provider-adapter behavior, usage settlement, and tests. Invitation-only,
  preview, product-surface-only, or region-only models should not become
  automatic routing candidates just because a provider page mentions them.
- Deprecated registry entries stay visible only for migration and cost safety.
  A deprecated model must not be promoted as a preferred default.

## Current Deepr Registry Snapshot

The registry currently contains 72 models: 65 direct-provider contracts across
OpenAI, Gemini, xAI, Anthropic, and Azure AI Foundry, plus seven preview-only
OpenRouter routes. The list below mirrors the registry on 2026-08-31; run the
offline command above for exact pricing and context values. The web
Models page intentionally reports 48 active benchmarkable public text or
research models because Azure AI Foundry entries are deployment targets, premium
media entries are not chat capacity, and deprecated or preview-only entries are
hidden from new benchmark target lists.

### OpenAI

Environment variable: `OPENAI_API_KEY`

Registered IDs:

- `openai/gpt-5.6-sol`
- `openai/gpt-5.6-terra`
- `openai/gpt-5.6-luna`
- `openai/gpt-5.5`
- `openai/gpt-5.5-pro`
- `openai/gpt-5.4`
- `openai/gpt-5.4-pro`
- `openai/gpt-5.4-mini`
- `openai/gpt-5.4-nano`
- `openai/gpt-5.2`
- `openai/gpt-5`
- `openai/gpt-5-mini`
- `openai/gpt-5-nano`
- `openai/gpt-4o-mini`
- `openai/gpt-4.1`
- `openai/gpt-4.1-mini`
- `openai/gpt-4.1-nano`
- `openai/o3`
- `openai/o4-mini`
- `openai/o3-deep-research`
- `openai/o4-mini-deep-research`

Default posture:

- Use GPT mainline models for synthesis, planning, and general research when
  OpenAI is the selected provider.
- Use Deep Research models only for explicitly deep, async research workloads
  with a budget ceiling.
- Use mini or nano variants for cheap classification, summaries, and routing
  only when quality risk is acceptable.
- GPT-5.6 Sol is the OpenAI task default. Terra is the balanced tier and Luna
  is the cost-sensitive tier. The `gpt-5.6` provider alias is priced as Sol.
- A 272K-token prompt is still base price. At 272,001 input tokens, Deepr
  applies the documented full-request long-context multipliers before a budget
  reservation can be admitted.

Manual verification:

- Models: <https://developers.openai.com/api/docs/models>
- GPT-5.6 Sol: <https://developers.openai.com/api/docs/models/gpt-5.6-sol>
- GPT-5.6 Terra: <https://developers.openai.com/api/docs/models/gpt-5.6-terra>
- GPT-5.6 Luna: <https://developers.openai.com/api/docs/models/gpt-5.6-luna>

### Google Gemini

Environment variable: `GEMINI_API_KEY`

Registered IDs:

- `gemini/gemini-3.6-flash`
- `gemini/gemini-3.5-flash-lite`
- `gemini/gemini-3.5-flash`
- `gemini/gemini-3-flash-preview`
- `gemini/gemini-3.1-flash-lite`
- `gemini/gemini-3.1-flash-lite-preview` (deprecated)
- `gemini/gemini-3.1-pro-preview`
- `gemini/gemini-3-pro-preview` (deprecated)
- `gemini/deep-research`
- `gemini/gemini-2.5-pro`
- `gemini/gemini-2.5-flash`
- `gemini/gemini-2.5-flash-lite`

Default posture:

- `gemini-flash` resolves to `gemini-3.6-flash`; `gemini-flash-lite`
  resolves to `gemini-3.5-flash-lite`. These aliases select a model but do not
  bypass explicit budget, tool, or provider gates. Alias resolution is shared
  by adapter dispatch, canonical pricing, bounded preflight, and the REST API.
- Provider-reported cached-content tokens settle at each model's documented
  cached-input rate; uncached prompt and billable output or thinking tokens use
  their standard rates.
- Gemini 3.6 Flash and Gemini 3.5 Flash-Lite reject the old sampling-control
  contract. Deepr omits `temperature`, `top_p`, and `top_k` for these models and
  sends the documented `thinking_level` values.
- Use Gemini for large-context document work and cost-sensitive multimodal or
  research workflows when the registry price and quality floor fit the task.
- Treat preview IDs as volatile. Re-check official docs before making them a
  default for durable workflows.
- Do not use shut-down preview IDs for new runs. They stay in the registry only
  so historical artifacts and cost records can still be interpreted.
- Keep Gemini image generation explicit. The registry's text/research support
  does not mean portraits or other image calls should run automatically.
- Do not target Gemini 3.5 Flash Cyber. Its announced CodeMender pilot is not a
  generally available Gemini API surface.

Manual verification:

- Models: <https://ai.google.dev/gemini-api/docs/models>
- Pricing: <https://ai.google.dev/gemini-api/docs/pricing>

### xAI Grok

Environment variable: `XAI_API_KEY`

Registered IDs:

- `xai/grok-4-6`
- `xai/grok-4-5`
- `xai/grok-4-3`
- `xai/grok-build-0-1`
- `xai/grok-4-20-reasoning`
- `xai/grok-4-20-non-reasoning`
- `xai/grok-4-20-multi-agent`
- `xai/grok-4-1-fast-reasoning` (deprecated)
- `xai/grok-4-1-fast-non-reasoning` (deprecated)
- `xai/grok-4-fast-reasoning` (deprecated)
- `xai/grok-4-fast-non-reasoning` (deprecated)
- `xai/grok-code-fast-1` (deprecated)
- `xai/grok-4-0709` (deprecated)
- `xai/grok-3` (deprecated)
- `xai/grok-imagine-image-pro` (deprecated premium media capacity)

Default posture:

- Prefer current Grok text models only for explicitly selected bounded xAI work
  without unpriced server-side tools.
- Generic `grok`, `grok-flagship`, and `grok-reasoning` aliases resolve to Grok
  4.6. Quick and fact-check routing retains Grok 4.3 because it is cheaper.
- Grok Build 0.1 is the current coding-specific entry. The documented
  `grok-code-fast`, `grok-code-fast-1`, and dated alias settle against the same
  $1/$2 standard rate and $0.20 cached-input rate.
- Grok 4.20 multi-agent dispatch is gated because its fan-out is not yet
  covered by one durable parent reservation.
- Legacy Grok IDs and `xai/grok-imagine-image-pro` remain in the registry as
  deprecated migration entries. They are excluded from active web benchmark
  target counts and must not be promoted as defaults.
- xAI image generation is premium capacity. Deepr must not call it for
  background portraits, demo data, profile refresh, or screenshots.

Manual verification:

- Models: <https://docs.x.ai/developers/models>
- Pricing: <https://docs.x.ai/developers/pricing>
- Grok 4.6: <https://docs.x.ai/developers/models/grok-4.6>
- Grok Build 0.1: <https://docs.x.ai/developers/models/grok-build-0.1>

### Anthropic Claude

Environment variable: `ANTHROPIC_API_KEY`

Registered IDs:

- `anthropic/claude-fable-5`
- `anthropic/claude-sonnet-5`
- `anthropic/claude-opus-5`
- `anthropic/claude-opus-4-8`
- `anthropic/claude-opus-4-7`
- `anthropic/claude-opus-4-6`
- `anthropic/claude-opus-4-5`
- `anthropic/claude-sonnet-4-6`
- `anthropic/claude-sonnet-4-5`
- `anthropic/claude-haiku-4-5`

Default posture:

- `claude-sonnet-5` is Deepr's balanced Anthropic chat and synthesis default.
- `claude-opus-5` is the registered Anthropic research flagship when an
  explicit budget supports a higher-cost call.
- `claude-fable-5` is a frontier, premium tier. It should be selected
  deliberately, not by background routing.
- Adaptive-thinking capable models are handled by the Anthropic provider. Do
  not hardcode unsupported sampling or thinking parameters outside the provider
  adapter.
- Anthropic product-surface features and API model availability are not the
  same thing. Register only Messages API models whose pricing and usage buckets
  Deepr can settle.

Manual verification:

- Models: <https://platform.claude.com/docs/en/about-claude/models/overview>
- Pricing: <https://platform.claude.com/docs/en/about-claude/pricing>
- Sonnet 5 migration notes:
  <https://platform.claude.com/docs/en/about-claude/models/whats-new-sonnet-5>
- Extended and adaptive thinking:
  <https://platform.claude.com/docs/en/build-with-claude/extended-thinking>

### OpenRouter Preview Catalog

The current-key check uses a hidden prompt by default. For an explicit local
workflow, put `OPENROUTER_API_KEY=...` in the checkout-local `.env` and add
`--from-env`; Deepr uses a quarantined process copy when available or parses
only that key from the bounded file without exporting it. It does not
unquarantine or export the key, pass it to a child process, or construct an
inference client. The repository ignores `.env`, but operators must still keep it out of
backups, logs, screenshots, and shared archives. An OS credential store is the
preferred future long-lived source.

Registered provider-route proposals checked on 2026-09-01:

| Model slug | Current endpoint metadata tag | Input / output cap per 1M | Cached input cap per 1M | Cache-write cap per 1M |
|---|---|---:|---:|---:|
| `openai/gpt-5.6-sol` | `openai` | `$2.00 / $10.00` | `$0.20` | `$2.50` |
| `anthropic/claude-sonnet-5` | `anthropic` | `$2.00 / $10.00` | `$0.20` | `$4.00` |
| `google/gemini-3.6-flash` | `google-ai-studio` | `$0.75 / $3.75` | `$0.075` | `$0.041667` |
| `x-ai/grok-4.6` | `xai/zdr` | `$2.00 / $6.00` | `$0.50` | `$0.00` |
| `qwen/qwen3.8-flash` | `alibaba` | `$0.15 / $0.47` | `$0.016` | `$0.20` |
| `moonshotai/kimi-k3` | `moonshotai/mxfp4` | `$3.00 / $15.00` | `$0.30` | `$0.00` |
| `deepseek/deepseek-v4-flash-0731` | `deepseek` | `$0.44 / $1.32` | `$0.014` | `$0.44` |

Default posture:

- The model argument uses the exact portion after `openrouter/`, such as
  `qwen/qwen3.8-flash`.
- Catalog rates define preview caps for the currently matched standard endpoint
  tags above, not the lowest route across OpenRouter. Base tags can match
  non-tier variants, so the check fails if another such record appears. The
  DeepSeek caps conservatively cover every current time-dependent override
  reachable by the 128K input envelope.
- The checker bounds prompt, completion, cached input, cache-write, reasoning,
  and fixed-request pricing. It rejects negative discount markups, malformed or
  unknown pricing classes, and a fixed request charge above zero. Reasoning
  tokens remain inside the completion-token ceiling and are not double counted.
- The checker reads every reported cache-write price, including Claude's
  one-hour rate. Where endpoint metadata omits the field, the documented xAI
  and Moonshot free-write posture or DeepSeek prompt-equivalent rate is
  explicit. A changed nonzero metadata rate fails the check.
- OpenRouter's prompt/completion `max_price` fields do not cap cache writes.
  Preview estimates therefore add a full-input cache-write reserve to ordinary
  input, even when the upstream may charge only one bucket.
- All tools are disabled. Automatic model routing, expert routing, benchmark
  evaluation, model fallbacks, and provider fallbacks cannot select these
  entries.
- Execution is blocked before reservation and provider construction. A future
  request must pin one upstream provider, disable fallback, require parameter
  support, set `max_price` to no more than the registered prompt, completion,
  and zero fixed-request rate, send `X-OpenRouter-Cache: false` and
  `X-OpenRouter-Metadata: enabled`, and omit service tiers, media, explicit
  prompt-cache controls, paid server features, and deprecated usage opt-ins.
- `deepr providers openrouter-check` makes at most seven pinned public metadata
  requests with no key, no redirects, no ambient proxy, bounded response bytes,
  and strict duplicate-key rejection. This no-key endpoint behavior is observed,
  not authenticated dispatch authority. The check fails nonzero if the matched
  route set, status, reachable prices, required parameters, or context drift.
- `deepr providers openrouter-key-check --required-headroom 5` prompts without
  echo for one key. Add `--from-env` only to opt into the bounded local secret
  source. The command makes one read-only current-key request and requires a
  BYOK-inclusive monthly limit at or below `$5`, sufficient remaining headroom,
  reconciling usage counters, and a live expiry when one is configured. Its
  sanitized result always reports incomplete billing reconciliation and no
  dispatch authority.
- OpenRouter permits nullable limit and reset controls. The v2 sanitized
  observation preserves an observed `null`, reports missing or non-monthly
  authority as ineligible, and never renders an absent limit as zero spend.
- A future shared-capacity adapter must prove that no applicable BYOK key or
  account-enforced paid plugin exists. It must require direct, one-attempt,
  non-BYOK router metadata with no pipeline stage, default or null service tier,
  no cache status, search, fetch, media, or preset, and matching response and
  generation total cost. Neither metadata surface exposes the endpoint tag.

Manual verification:

- Model catalog: <https://openrouter.ai/docs/guides/overview/models>
- Provider routing: <https://openrouter.ai/docs/guides/routing/provider-selection>
- Router metadata: <https://openrouter.ai/docs/guides/features/router-metadata>
- Usage accounting: <https://openrouter.ai/docs/cookbook/administration/usage-accounting>
- BYOK routing: <https://openrouter.ai/docs/guides/overview/auth/byok>
- Service tiers: <https://openrouter.ai/docs/guides/features/service-tiers>
- Current-key limits:
  <https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key>
- Generation usage metadata:
  <https://openrouter.ai/docs/api/api-reference/generations/get-request-&-usage-metadata-for-a-generation>
- Prompt caching: <https://openrouter.ai/docs/guides/best-practices/prompt-caching>
- Response caching: <https://openrouter.ai/docs/guides/features/response-caching>
- Design: [openrouter-metered-gateway.md](design/openrouter-metered-gateway.md)

### Azure AI Foundry and Azure OpenAI

Environment variables:

- `AZURE_PROJECT_ENDPOINT` for Azure AI Foundry Agent Service.
- `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_KEY` for Azure OpenAI compatible
  deployments.

Registered Azure AI Foundry IDs:

- `azure-foundry/o3-deep-research`
- `azure-foundry/gpt-5`
- `azure-foundry/gpt-5-mini`
- `azure-foundry/gpt-4.1`
- `azure-foundry/gpt-4.1-mini`
- `azure-foundry/gpt-4o`
- `azure-foundry/gpt-4o-mini`

Default posture:

- Azure model availability is deployment and region dependent. The registry
  names Deepr-tested deployment targets, not every model Microsoft may expose
  in a given subscription.
- Azure AI Foundry deep research remains a registered deployment target but is
  gated until the agent run exposes the complete output and tool ceiling needed
  for paid dispatch.
- Refresh Azure registry entries only after adapter behavior and deployment
  names are tested locally or in CI-like validation.

Manual verification:

- Azure OpenAI models:
  <https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure>
- Azure AI Foundry Agent Service:
  <https://learn.microsoft.com/azure/ai-foundry/agents/overview>
- Azure AI Services pricing:
  <https://azure.microsoft.com/pricing/details/cognitive-services/>

## Selection by Workload

| Workload | Preferred capacity order | Notes |
|----------|--------------------------|-------|
| Scheduled expert maintenance | Local admitted model, then observed non-metered plan quota | Background loops wait or stop when owned capacity is unavailable; automatic and explicit metered maintenance are gated. |
| Quick lookup or lightweight synthesis | Cheapest capable registered model from configured provider, or local/plan backend if admitted | Keep quality floor and budget estimate visible. |
| Large inline prompt analysis | A registered long-context model whose declared request bound fits its context window | Hosted file and vector context is gated; preview the complete inline envelope. |
| Deep research | Bounded OpenAI or Azure OpenAI research envelopes | Gemini managed research, xAI multi-agent, and Azure Foundry agents are registered but gated until their complete run cost is enforceable. |
| Expert consultation | Local or explicit plan query/consult; metered API council synthesis is preview-only | Production metered dispatch is blocked until authenticated account controls and current credential identity are proven; tools and streaming are not implied. |
| Portraits and images | Existing portrait or explicit local image endpoint | Paid portrait dispatch is gated. |

## Safe Refresh Workflow

1. Check official provider docs and pricing pages linked above.
2. Run `python scripts/discover_models.py --show-registry` to confirm current
   local entries.
3. Run `deepr providers models` for a live model-list diff only when provider
   keys are intentionally available.
4. Update `src/deepr/providers/registry.py` for direct-provider contracts or
   `src/deepr/providers/openrouter_catalog.py` for preview-only OpenRouter
   routes. Keep model names, prices, context windows, and routing metadata in
   those registries.
5. Add or update provider-adapter tests when a model needs changed API
   parameters, thinking controls, streaming behavior, tool policy, or usage
   settlement.
6. Update docs qualitatively. Avoid duplicating exact prices outside the
   registry unless the text is explicitly a dated snapshot.
7. Rebuild and regenerate screenshots only from local/demo data. Do not use
   premium image APIs for docs or screenshots.
8. Run the no-key unit gate. Live provider validation stays explicit and
   opt-in.

## Cost and Capacity Policy

Deepr's default stance is no surprise bills:

- Local Ollama is `$0` marginal cost but still consumes hardware and must pass
  task-specific admission before automatic routing.
- Plan-quota CLIs are treated as non-metered only when auth mode and quota
  observation support that claim. A CLI authenticated by an API key is refused
  as plan capacity.
- Metered provider APIs require estimates, reservations, budget ceilings, and
  append-only settlement.
- Provider-reported usage is not optional for settlement. Missing or
  unpriceable usage must fail closed or use conservative registry pricing.
- Image generation is premium unless it is a local endpoint. Background
  profile updates and screenshots should reuse existing portraits or local
  demo assets.

## Known Gaps

- The model-freshness loop is still manual. The roadmap keeps the automated
  periodic discovery and opt-in registry update flow open.
- Azure model availability is region and deployment specific. Registry support
  should lag official listings until deployment behavior is verified.
- Provider docs may expose invitation-only, preview, or product-surface models
  that Deepr should not register until API behavior, pricing, and safety gates
  are clear.
- Registry support does not imply automatic routing. A model becomes an
  automatic candidate only when backend capability declarations, quality
  priors, budget gates, usage settlement, and tests support the task.

## See Also

- [FEATURES.md](FEATURES.md) - feature guide with model-related commands
- [CAPACITY.md](CAPACITY.md) - local, plan-quota, metered API, and scheduler
  capacity rules
- [BENCHMARKS.md](BENCHMARKS.md) - scoring and model-quality evidence
- [../ROADMAP.md](../ROADMAP.md) - active model-freshness and capacity work
