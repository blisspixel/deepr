# Model Selection Guide

Status: current with Deepr v2.36.1. Last reviewed: 2026-07-13.

The source of truth for model IDs, pricing estimates, context windows, and
routing metadata is [src/deepr/providers/registry.py](../src/deepr/providers/registry.py).
This guide explains how to use that registry safely. Provider docs and prices
change faster than prose, so treat this document as an operating guide, not a
billing authority.

External model docs checked on 2026-07-01:

- OpenAI Models and Pricing:
  <https://platform.openai.com/docs/models>,
  <https://platform.openai.com/docs/pricing>,
  <https://openai.com/index/previewing-gpt-5-6-sol/>
- Claude Platform Models, Pricing, and Thinking:
  <https://platform.claude.com/docs/en/about-claude/models/overview>,
  <https://platform.claude.com/docs/en/about-claude/pricing>,
  <https://platform.claude.com/docs/en/about-claude/models/whats-new-sonnet-5>,
  <https://platform.claude.com/docs/en/build-with-claude/extended-thinking>,
  <https://platform.claude.com/docs/en/release-notes/overview>
- Google Gemini Models and Pricing:
  <https://ai.google.dev/gemini-api/docs/models>,
  <https://ai.google.dev/gemini-api/docs/pricing>
- xAI Models and Pricing:
  <https://docs.x.ai/developers/models>,
  <https://docs.x.ai/developers/pricing>
- Azure OpenAI and Azure AI Foundry:
  <https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure>,
  <https://learn.microsoft.com/azure/ai-foundry/agents/overview>

## 2026-07-01 Verification Matrix

| Provider | Current external signal | Deepr status | Action |
|----------|-------------------------|--------------|--------|
| OpenAI | Official API docs list GPT-5.5 as the recommended flagship and GPT-5.6 as trusted-partner preview only. | GPT-5.5 is registered. GPT-5.6 is watchlist-only. | Keep GPT-5.6 out of auto-routing until self-serve API access, pricing, context, and adapter behavior are verified. |
| Anthropic | Claude docs list Fable 5 as generally available, Mythos 5 as limited availability, and Sonnet 5 as the current balanced Sonnet with adaptive thinking. | Fable 5, Sonnet 5, Opus 4.8, and Haiku 4.5 are registered. Mythos is not registered. | Keep Sonnet 5 as the balanced Anthropic default. Keep Mythos out until access and settlement are normal. |
| Google Gemini | Gemini docs list Gemini 3.5 Flash and Gemini 3.1 Flash-Lite as stable; Gemini 3 Pro Preview and Gemini 3.1 Flash-Lite Preview are in the shut-down previous-model set. | Stable Gemini text models are registered. Managed Gemini Deep Research dispatch is gated because its autonomous loop lacks a complete request ceiling. The shut-down preview IDs are deprecated migration entries. | Do not target shut-down preview IDs in new benchmark or routing runs. |
| xAI | xAI docs direct general text work to Grok 4.3, list Grok Build 0.1 for coding, and price Imagine image/video APIs separately. | Grok 4.3 is the preferred xAI text default. Grok Build is watchlist-only. xAI image remains explicit premium capacity. | Keep coding and media model additions behind registry, adapter, and no-surprise-bills tests. |
| Azure AI Foundry | Foundry docs expose agents through the Responses API, deployment catalogs, regional limits, and managed endpoint controls. | Azure entries remain deployment targets, not global public model defaults. | Treat availability as subscription, deployment, and region dependent. |

## Current External Watchlist

These are visible in current provider docs but are not automatic Deepr routing
defaults unless the registry, adapter behavior, cost settlement, and tests are
explicitly updated.

- OpenAI lists GPT-5.6 as a trusted-partner preview with broad availability
  still pending. Treat it as watchlist-only until self-serve API access,
  pricing, context limits, and Responses API behavior are verified.
- Anthropic lists Claude Mythos 5 and the Mythos preview as limited
  availability. Keep them out of Deepr's public registry and auto-routing until
  API access and pricing are normal enough to test and settle.
- Gemini lists Gemini 3.5 Flash as stable and several Gemini or Nano Banana
  media models. Deepr's registry covers text and research backends; media
  models must stay explicit and cost-gated before any image or video path uses
  them.
- Google now lists `gemini-3-pro-preview` and
  `gemini-3.1-flash-lite-preview` in the shut-down previous-model set. Deepr
  keeps them only as deprecated migration entries for historical cost lookup.
- xAI currently directs general chat and reasoning workloads to Grok 4.3 and
  lists Grok Build 0.1 for agentic coding. The coding model should remain a
  watchlist item until Deepr has registry pricing, adapter expectations, and
  tests for its coding-specific behavior.
- xAI image, video, and voice surfaces are dedicated APIs with separate pricing.
  Deepr should continue treating xAI image generation as premium explicit
  capacity.
- Azure and Microsoft Foundry model availability is deployment and region
  dependent. A model appearing in Foundry docs is not enough to make it a
  globally selectable Deepr model.

Pricing notes:

- OpenAI currently exposes short-context, long-context, and priority pricing
  buckets for some models. Deepr should continue using conservative registry
  estimates until the estimator can pick the right bucket from prompt size and
  request class.
- Anthropic currently documents lower introductory Sonnet 5 pricing through
  2026-08-31, but Deepr estimates Sonnet 5 with the standard post-intro rates
  so budget gates do not understate future spend.
- Gemini free-tier and quota-inclusive entries are useful for setup guidance,
  but automatic routing still depends on the local Deepr capacity profile,
  provider keys, quota posture, and budget gates.

## Operating Rules

- Run `python scripts/discover_models.py --show-registry` to see the local
  registry. This command is offline and does not call providers.
- Run `deepr providers models` or `python scripts/discover_models.py` only when
  you intentionally want live provider model-list checks. API discovery lists
  model names only; most provider APIs do not expose pricing.
- `python scripts/discover_models.py --llm` is gated in v2.36 before any model
  call. Restore it only with an exact estimate, explicit approval, durable
  reservation, and canonical settlement.
- Use `deepr research ... --dry-run` or the web preflight estimate before any
  metered research.
- Prefer local Ollama and admitted plan-quota capacity for routine maintenance.
  Metered APIs are the premium path and require explicit budget gates.
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

The registry currently contains 56 models across OpenAI, Gemini, xAI,
Anthropic, and Azure AI Foundry. The list below mirrors the registry on
2026-07-12; run the command above for exact pricing and context values. The web
Models page intentionally reports 39 active benchmarkable public text or
research models because Azure AI Foundry entries are deployment targets, premium
media entries are not chat capacity, and deprecated migration entries are hidden
from new benchmark target lists.

### OpenAI

Environment variable: `OPENAI_API_KEY`

Registered IDs:

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
- GPT-5.5 is the OpenAI flagship currently represented in Deepr defaults and
  routing priors. If OpenAI publishes a newer limited or preview model, keep it
  out of automatic routing until registry pricing and adapter behavior are
  verified.

Manual verification:

- Models: <https://platform.openai.com/docs/models>
- Pricing: <https://platform.openai.com/docs/pricing>
- GPT-5.6 preview status: <https://openai.com/index/previewing-gpt-5-6-sol/>

### Google Gemini

Environment variable: `GEMINI_API_KEY`

Registered IDs:

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

- Use Gemini for large-context document work and cost-sensitive multimodal or
  research workflows when the registry price and quality floor fit the task.
- Treat preview IDs as volatile. Re-check official docs before making them a
  default for durable workflows.
- Do not use shut-down preview IDs for new runs. They stay in the registry only
  so historical artifacts and cost records can still be interpreted.
- Keep Gemini image generation explicit. The registry's text/research support
  does not mean portraits or other image calls should run automatically.

Manual verification:

- Models: <https://ai.google.dev/gemini-api/docs/models>
- Pricing: <https://ai.google.dev/gemini-api/docs/pricing>

### xAI Grok

Environment variable: `XAI_API_KEY`

Registered IDs:

- `xai/grok-4-3`
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
- Grok 4.3 is the preferred xAI text default. Grok 4.20 multi-agent dispatch is
  gated because its fan-out is not yet covered by one durable parent
  reservation.
- Grok Build 0.1 is visible in current xAI docs as a coding-specific model, but
  it is not yet registered in Deepr. Add it only with pricing, adapter, and
  no-surprise-bills tests.
- Legacy Grok IDs and `xai/grok-imagine-image-pro` remain in the registry as
  deprecated migration entries. They are excluded from active web benchmark
  target counts and must not be promoted as defaults.
- xAI image generation is premium capacity. Deepr must not call it for
  background portraits, demo data, profile refresh, or screenshots.

Manual verification:

- Models: <https://docs.x.ai/developers/models>
- Pricing: <https://docs.x.ai/developers/pricing>

### Anthropic Claude

Environment variable: `ANTHROPIC_API_KEY`

Registered IDs:

- `anthropic/claude-fable-5`
- `anthropic/claude-sonnet-5`
- `anthropic/claude-opus-4-8`
- `anthropic/claude-opus-4-7`
- `anthropic/claude-opus-4-6`
- `anthropic/claude-opus-4-5`
- `anthropic/claude-sonnet-4-6`
- `anthropic/claude-sonnet-4-5`
- `anthropic/claude-haiku-4-5`

Default posture:

- `claude-sonnet-5` is Deepr's balanced Anthropic chat and synthesis default.
- `claude-opus-4-8` is the registered Anthropic research flagship when an
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
| Scheduled expert maintenance | Local admitted model, then observed non-metered plan quota | Background loops wait or stop when owned capacity is unavailable; automatic and explicit metered maintenance are gated in v2.36. |
| Quick lookup or lightweight synthesis | Cheapest capable registered model from configured provider, or local/plan backend if admitted | Keep quality floor and budget estimate visible. |
| Large inline prompt analysis | A registered long-context model whose declared request bound fits its context window | Hosted file and vector context is gated; preview the complete inline envelope. |
| Deep research | Bounded OpenAI or Azure OpenAI research envelopes | Gemini managed research, xAI multi-agent, and Azure Foundry agents are registered but gated until their complete run cost is enforceable. |
| Expert consultation | Local or explicit plan query/consult, or separately bounded API council synthesis | Standalone metered chat is gated; tools and streaming are not implied. |
| Portraits and images | Existing portrait or explicit local image endpoint | Paid portrait dispatch is gated in v2.36. |

## Safe Refresh Workflow

1. Check official provider docs and pricing pages linked above.
2. Run `python scripts/discover_models.py --show-registry` to confirm current
   local entries.
3. Run `deepr providers models` for a live model-list diff only when provider
   keys are intentionally available.
4. Update only `src/deepr/providers/registry.py` for model names, prices,
   context windows, and routing metadata.
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
