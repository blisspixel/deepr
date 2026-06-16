# Model Selection Guide

> **Note**: The [model registry](../deepr/providers/registry.py) is the single source of truth for model names and pricing. AI models evolve rapidly, so verify at provider websites. Run `deepr providers models` to diff the registry against each provider's live model list (flags newer versions of families you already use, with paste-ready registry stubs), or `python scripts/discover_models.py --show-registry` to see all registered models with pricing.

## Overview

**Deepr works with just one API key.** Add more keys and auto mode routes each query to the best available model - cheap for simple lookups, powerful for deep research.

Deepr uses a hybrid approach optimizing for both quality and cost. Different tasks benefit from different models, and auto mode handles the routing automatically based on which providers you have configured.

## Provider Landscape

### OpenAI (`OPENAI_API_KEY`)
- **Deep Research**: Turnkey async Deep Research API via Responses endpoint
- **Models**: o3-deep-research, o4-mini-deep-research, GPT-5.5, GPT-5.4, GPT-5.4-pro, GPT-5.4-mini, GPT-5.4-nano, GPT-5-mini, GPT-4.1, GPT-4.1-mini
- **Best for**: Deep research, planning, expert system (vector stores require OpenAI-compatible API)
- **Note**: GPT-5.4 is the current mainline default; use GPT-5.4-pro for hardest tasks and GPT-5-mini for value

### Google Gemini (`GEMINI_API_KEY`)
- **Deep Research**: Native Deep Research Agent via Interactions API (async background jobs)
- **Models**: Gemini 3.1 Pro Preview (default), Gemini 3.5 Flash, Gemini 3 Flash, Gemini 3.1 Flash-Lite (GA), Gemini 2.5 Flash, Deep Research Agent (`deep-research-pro-preview-12-2025`)
- **Best for**: Large context windows (1M+ tokens), document analysis, cost-effective research, agentic workflows
- **Note**: Gemini 3.5 Flash (GA May 19, 2026, Google I/O 2026) is the newest Flash generation - it beats Gemini 3.1 Pro on coding/agentic/multimodal benchmarks at ~4x faster output, priced at $1.50/$9.00 per MTok

### xAI Grok (`XAI_API_KEY`)
- **Deep Research**: Grok 4.20 Multi-Agent (4–16 parallel agents with autonomous tool use)
- **Models**: Grok 4.3 (flagship), Grok 4.20 Reasoning, Grok 4.20 Non-Reasoning, Grok 4.20 Multi-Agent
- **Best for**: Grok 4.3 tops leaderboards in agentic tool calling and instruction following; flagship quality on 4.20 ($2/$6 per MTok); real-time web + X search
- **Note**: Grok 4.3 is xAI's latest flagship with reasoning effort control (low/medium/high). Grok 4.20 remains the multi-agent deep research workhorse.

#### Grok 4.3 (Flagship)

| Feature | Details |
|---------|---------|
| Pricing | $1.25/1M input tokens, $2.50/1M output tokens |
| Context Window | 1,000,000 tokens |
| Capabilities | Reasoning (low/medium/high effort), agentic tool calling, instruction following |
| Strengths | #1 on agentic tool calling and instruction following leaderboards |
| Reasoning Effort | `low` (fast, cheap), `medium` (default), `high` (deep multi-step reasoning) |

```bash
# Use Grok 4.3 with default reasoning effort (medium)
deepr research "Topic" --model xai/grok-4-3

# Specify reasoning effort for complex tasks
deepr research "Complex multi-step analysis" --model xai/grok-4-3  # auto-routes to high effort in auto mode
```

#### Deprecated Grok Models (Retiring May 15, 2026)

The following legacy models will stop accepting API requests on **May 15, 2026 at 12:00pm PT**. Deepr auto-migrates requests to their successors transparently.

| Deprecated Model | Successor | Migration Notes |
|-----------------|-----------|-----------------|
| grok-4-1-fast-reasoning | xai/grok-4-3 | Reasoning workloads → Grok 4.3 |
| grok-4-fast-reasoning | xai/grok-4-3 | Reasoning workloads → Grok 4.3 |
| grok-4-0709 | xai/grok-4-3 | Reasoning workloads → Grok 4.3 |
| grok-3 | xai/grok-4-3 | Reasoning workloads → Grok 4.3 |
| grok-code-fast-1 | xai/grok-4-3 | Code workloads → Grok 4.3 |
| grok-4-1-fast-non-reasoning | xai/grok-4-20-non-reasoning | Non-reasoning workloads → Grok 4.20 Non-Reasoning |
| grok-4-fast-non-reasoning | xai/grok-4-20-non-reasoning | Non-reasoning workloads → Grok 4.20 Non-Reasoning |
| grok-imagine-image-pro | xai/grok-imagine-image | Image generation → Grok Imagine Image |

**Migration recommendations:**
- **Reasoning workloads** → `xai/grok-4-3` (better quality, competitive pricing)
- **Non-reasoning workloads** → `xai/grok-4-20-non-reasoning` (optimized for throughput)
- **Image generation** → `xai/grok-imagine-image` (direct successor)

### Anthropic Claude (`ANTHROPIC_API_KEY`)
- **Deep Research**: No turnkey API - uses Extended Thinking + tool use + web search orchestration
- **Models**: Claude Fable 5, Claude Opus 4.8, Claude Opus 4.7, Claude Opus 4.6, Claude Sonnet 4.6, Claude Sonnet 4.5, Claude Haiku 4.5
- **Best for**: Complex reasoning with transparent thinking, coding tasks, nuanced analysis
- **Note**: Opus 4.8 (GA May 28, 2026) is the recommended research flagship (~$0.85/query, $5/$25 per MTok). Claude Fable 5 ($10/$50 per MTok, ~$2.20/query) is the frontier tier above Opus - most capable, but its new tokenizer uses ~30% more tokens for the same text, its safety classifiers can refuse cyber/bio research topics, and it requires 30-day data retention; opt in deliberately. Sonnet 4.6 ($3/$15) is the best-value coding model. Fable 5, Opus 4.6+ and Sonnet 4.6 include the full 1M context window at standard pricing. Opus 4.6+, Sonnet 4.6, and Fable 5 use Adaptive Thinking (the provider sends `{"type": "adaptive"}` automatically; legacy models keep budgeted Extended Thinking). Requires a web search backend (Brave, Tavily, or DuckDuckGo)

### Azure OpenAI (`AZURE_OPENAI_KEY`)
- **Models**: Same as OpenAI, deployed through Azure
- **Best for**: Enterprise environments with Azure compliance requirements
- **Note**: Requires Azure AD credentials or managed identity; set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_KEY`

### Azure AI Foundry (`AZURE_PROJECT_ENDPOINT`)
- **Deep Research**: o3-deep-research via Agent Service with Bing grounding
- **Models**: o3-deep-research, GPT-5, GPT-5-mini, GPT-4.1, GPT-4.1-mini, GPT-4o, GPT-4o-mini
- **Best for**: Enterprise deep research with Bing web grounding, Azure compliance
- **Auth**: Azure AD / Managed Identity via `DefaultAzureCredential` (no API key option)
- **Architecture**: Agent/Thread/Run pattern for deep research; lightweight agents for regular models
- **Note**: Deep research limited to West US / Norway East / South Central US; GPT models available in 20+ regions via Global Standard deployment

| Model | Cost/Query | Context | Regions | Use Case |
|-------|-----------|---------|---------|----------|
| o3-deep-research | $0.50 | N/A | 3 regions | Enterprise deep research with Bing |
| GPT-5 | $0.15 | 400K | 10+ (Global Standard) | Frontier reasoning and synthesis |
| GPT-5-mini | $0.03 | 400K | Global Standard | Cost-effective GPT-5 alternative |
| GPT-4.1 | $0.04 | 1M+ | 19 regions (widest) | Long-context analysis, planning |
| GPT-4.1-mini | $0.01 | 1M+ | 19 regions | Budget long-context tasks |
| GPT-4o | $0.03 | 128K | Global Standard | General multimodal |
| GPT-4o-mini | $0.005 | 128K | Global Standard | Cheapest option |

#### Azure Foundry Setup Guide

**Prerequisites:**
1. An Azure subscription with Azure AI Foundry access
2. A project created in Azure AI Foundry (formerly Azure AI Studio)
3. Model deployments provisioned (Global Standard or Provisioned Throughput)
4. Azure CLI installed and authenticated (`az login`)

**Configuration:**

```bash
# Required: Azure AI Foundry project endpoint
AZURE_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com/api/projects/your-project-id

# Optional: Override default model deployments
AZURE_DEEP_RESEARCH_DEPLOYMENT=o3-deep-research    # Default
AZURE_GPT_DEPLOYMENT=gpt-4.1                       # Default
AZURE_BING_RESOURCE_NAME=your-bing-connection      # For Bing grounding
```

**Authentication:** Azure Foundry uses `DefaultAzureCredential` (Azure AD). No API key option. For local development, run `az login`. In production, use Managed Identity.

**Agent/Thread/Run Pattern:**

Azure Foundry uses the Agent Service pattern for all operations:
1. **Agent** - A reusable model configuration with tools (created once, cached)
2. **Thread** - A conversation context (created per research job)
3. **Run** - An execution of the agent on a thread (one per query)

Deep research agents include `DeepResearchTool` + `BingGroundingTool`. Regular agents use a lightweight configuration without research tools.

**o3-deep-research with Bing Grounding:**

To enable Bing-grounded deep research:
1. Create a Bing Search resource in Azure Portal
2. Add a Bing connection in your Azure AI Foundry project
3. Set `AZURE_BING_RESOURCE_NAME` to the connection name
4. Deploy `o3-deep-research` in a supported region (West US, Norway East, or South Central US)

```bash
# Example usage
deepr run focus "Market analysis of EV batteries" --provider azure --model o3-deep-research
```

The agent automatically uses Bing web grounding to find and cite current sources. Citations are returned in standard Deepr format.

**Pricing:** Azure Foundry pricing follows Azure AI Services rates. See [Azure AI Services pricing](https://azure.microsoft.com/pricing/details/cognitive-services/) for current per-token costs. The cost/query estimates above assume typical research workloads.

## Model Selection by Task

| Task | Recommended Model | Cost/query | Latency | Notes |
|------|-------------------|-----------|---------|-------|
| Deep Research (OpenAI) | o3-deep-research | see registry | 5-20 min | Async, highest-quality deep research baseline |
| Deep Research (Gemini) | deep-research-pro-preview | ~$2.50 | 5-20 min | Async, Google Search built-in, powered by Gemini 3.1 Pro |
| Deep Research (Azure) | o3-deep-research | $0.50 | 5-20 min | Bing grounding, enterprise |
| Deep Research (xAI) | grok-4.20-multi-agent | ~$0.50 | 30-120s | 4/16 parallel agents, web + X search |
| Complex Research | gpt-5.4 | see registry | ~seconds to minutes | strong reasoning/synthesis default |
| Agentic / Tool Calling | Grok 4.3 | ~$0.08 | ~2s | #1 agentic tool calling + instruction following |
| Quality Research (xAI) | Grok 4.20 Reasoning | ~$0.10 | ~3s | Flagship xAI, lowest hallucination rate |
| Planning/Curriculum | GPT-4.1 | $0.04 | ~2s | 1M+ context, cost-effective |
| Quick Lookups | Grok 4.20 Non-Reasoning | see registry | ~1s | best value for freshness/citation tasks |
| Latest News / Web | Grok 4.20 Non-Reasoning | see registry | ~1s | real-time web + strong value |
| Large Documents | Gemini 3.1 Pro | $0.20* | ~40s | 1M token context, configurable thinking |
| Fast Coding / Agentic | Gemini 3.5 Flash | ~$0.03 | ~1.5s | Beats 3.1 Pro on coding/agentic at Flash speed ($1.50/$9.00 per MTok) |
| Coding Tasks | Claude Sonnet 4.6 | $0.48 | ~3s | Best-value coding ($3/$15 per MTok) |
| Complex Reasoning | Claude Opus 4.7 | see registry | ~seconds | Most capable Claude; leads SWE-bench Pro |
| Budget General | GPT-4.1-mini | $0.01 | ~1s | Cheapest OpenAI, 1M context |

*\*Gemini 3.1 Pro has tiered pricing: $2/$12 per 1M tokens (input/output) for prompts ≤200K tokens, $4/$18 for prompts >200K tokens. The $0.20/query estimate assumes a typical sub-200K prompt. Large document analysis (250K+ tokens) costs roughly 2x more - e.g., a 500K-token corpus costs ~$2.27 vs ~$1.18 with sub-200K prompts. Use `--dry-run` to check before running.*

## Cost Optimization Strategy

**The 80/20 Rule**: Use fast/cheap models for 80% of operations, reserve expensive models for the 20% that need them.

### Deep Research (~20% of operations)
- **Models**: o4-mini-deep-research, o3-deep-research, Gemini Deep Research Agent, Grok 4.20 Multi-Agent
- **Cost**: $0.50-$2.00 per query (OpenAI), ~$2.50 (Gemini), ~$0.50 (Grok multi-agent)
- **Use for**: Novel problem-solving, critical decisions, complex synthesis
- **Note**: OpenAI and Gemini use async background jobs; Grok 4.20 multi-agent uses 4/16 parallel agents

### Fast/General Operations (~80% of operations)
- **Models**: Grok 4.20 Non-Reasoning, Grok 4.3 (low effort), Gemini 2.5 Flash
- **Cost**: $0.001-$0.01 per query (96-99% cheaper)
- **Use for**: News, docs, team research, learning, expert chat, planning

**Result**: Using fast models for routine operations reduces total costs by ~90%.

## Deepr's Model Usage

### Research Commands
```bash
# Uses deep research routing defaults (see config + benchmark preferences)
deepr research "Complex topic"

# Override with specific model
deepr research "Topic" --model openai/o3-deep-research

# Use Gemini Deep Research Agent
deepr research "Topic" --model gemini-deep-research
```

### Expert System
- **Campaign mode (deep)**: o3-deep-research / o4-mini-deep-research (provider + budget dependent)
- **Focus mode (quick)**: GPT-4.1 ($0.04/query, 1M+ context)
- **Expert chat**: Provider-dependent (OpenAI for vector store experts)
- **Quick lookups**: Grok 4.20 Non-Reasoning ($0.01, when XAI_API_KEY available)

### Adaptive Routing
Deepr's model router (`src/deepr/experts/router.py`) automatically selects models based on:
- Query complexity
- Budget remaining
- Task type (factual vs reasoning)
- Context size

## Provider Configuration

**You only need one key to start.** Set any of these in `.env`:

```bash
# Pick one to get started - add more later for smarter routing
OPENAI_API_KEY=sk-...                   # Deep research + GPT models
GEMINI_API_KEY=...                      # Cost-effective, large context
XAI_API_KEY=...                         # Cheapest, real-time web search
ANTHROPIC_API_KEY=...                   # Complex reasoning, coding

# Enterprise options
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
# AZURE_OPENAI_KEY=...
# AZURE_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com/...
```

Auto mode detects which keys are configured and routes accordingly. With one key, all queries go to that provider. With multiple keys, simple queries go to the cheapest provider and complex queries go to the most capable one.

## Model Registry

All model definitions live in `src/deepr/providers/registry.py`. This is the single source of truth.

**When new models are released**: Update ONLY the registry. Never hardcode model names elsewhere in the codebase.

## Keeping Current

AI models change frequently. Deepr includes a discovery script to check for new models:

```bash
# Show current registry
python scripts/discover_models.py --show-registry

# Check live APIs for new models (uses your configured keys)
python scripts/discover_models.py

# Use LLM (Grok preferred) to look up latest models + pricing
python scripts/discover_models.py --llm
```

Provider docs for manual verification:
- OpenAI: https://platform.openai.com/docs/models
- xAI: https://x.ai/api
- Google: https://ai.google.dev/models
- Anthropic: https://docs.anthropic.com/claude/docs/models-overview
- Azure AI Foundry: https://learn.microsoft.com/azure/ai-services/agents/

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical architecture
- [FEATURES.md](FEATURES.md) - Feature guide with model options
- [../ROADMAP.md](../ROADMAP.md) - Development priorities
