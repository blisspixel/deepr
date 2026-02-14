# Model Selection Guide

> **Note**: Model information current as of February 2026. AI models evolve rapidly — verify current pricing at provider websites. The [model registry](../deepr/providers/registry.py) is the source of truth. Run `python scripts/discover_models.py --show-registry` to see all registered models with pricing.

## Overview

**Deepr works with just one API key.** Add more keys and auto mode routes each query to the best available model — cheap for simple lookups, powerful for deep research.

Deepr uses a hybrid approach optimizing for both quality and cost. Different tasks benefit from different models, and auto mode handles the routing automatically based on which providers you have configured.

## Provider Landscape

### OpenAI (`OPENAI_API_KEY`)
- **Deep Research**: Turnkey async Deep Research API via Responses endpoint
- **Models**: o3-deep-research, o4-mini-deep-research, GPT-5, GPT-5-mini, GPT-4.1, GPT-4.1-mini
- **Best for**: Deep research, planning, expert system (vector stores require OpenAI-compatible API)
- **Note**: GPT-5.2 available but requires approval; GPT-4.1 is widely available and cost-effective

### Google Gemini (`GEMINI_API_KEY`)
- **Deep Research**: Native Deep Research Agent via Interactions API (async background jobs)
- **Models**: Gemini 2.5 Flash, Gemini 3 Pro, Deep Research Agent (`deep-research-pro-preview-12-2025`)
- **Best for**: Large context windows (1M+ tokens), document analysis, cost-effective research

### xAI Grok (`XAI_API_KEY`)
- **Models**: Grok 4, Grok 4 Fast
- **Best for**: Cheapest general operations ($0.01/query), real-time web + X/Twitter search, latest news
- **Note**: Grok 4 Fast is the default for simple factual queries in auto mode

### Anthropic Claude (`ANTHROPIC_API_KEY`)
- **Deep Research**: No turnkey API — uses Extended Thinking + tool use + web search orchestration
- **Models**: Claude Opus 4.6, Claude Sonnet 4.5, Claude Haiku 4.5
- **Best for**: Complex reasoning with transparent thinking, coding tasks, nuanced analysis
- **Note**: Opus 4.6 (latest) recommended for research (~$0.80/query). All models support Extended Thinking. Requires a web search backend (Brave, Tavily, or DuckDuckGo)

### Azure OpenAI (`AZURE_OPENAI_KEY`)
- **Models**: Same as OpenAI, deployed through Azure
- **Best for**: Enterprise environments with Azure compliance requirements
- **Note**: Requires Azure AD credentials or managed identity; set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_KEY`

### Azure AI Foundry (`AZURE_PROJECT_ENDPOINT`)
- **Deep Research**: o3-deep-research via Agent Service with Bing grounding
- **Models**: o3-deep-research, GPT-5, GPT-5-mini, GPT-4.1, GPT-4.1-mini, GPT-4o
- **Best for**: Enterprise deep research with Bing web grounding, Azure compliance
- **Note**: Deep research limited to West US / Norway East / South Central US; GPT models available in 20+ regions

## Model Selection by Task

| Task | Recommended Model | Cost/query | Latency | Notes |
|------|-------------------|-----------|---------|-------|
| Deep Research (OpenAI) | o4-mini-deep-research | $0.10 | 5-20 min | Async, comprehensive |
| Deep Research (Gemini) | deep-research-pro-preview | ~$1.00 | 5-20 min | Async, Google Search built-in |
| Deep Research (Azure) | o3-deep-research | $0.50 | 5-20 min | Bing grounding, enterprise |
| Complex Research | o3-deep-research | $0.50 | 2-5 min | Extended reasoning chains |
| Planning/Curriculum | GPT-4.1 | $0.04 | ~2s | 1M+ context, cost-effective |
| Quick Lookups | Grok 4 Fast | $0.01 | ~1s | Cheapest option |
| Latest News / Web | Grok 4 Fast | $0.01 | ~1s | Real-time web + X search |
| Large Documents | Gemini 3 Pro | $0.15 | ~4s | 1M token context |
| Coding Tasks | Claude Sonnet 4.5 | $0.48 | ~3s | Best for code |
| Complex Reasoning | Claude Opus 4.6 | $0.80 | ~15s | Adaptive Thinking |
| Budget General | GPT-4.1-mini | $0.01 | ~1s | Cheapest OpenAI, 1M context |

## Cost Optimization Strategy

**The 80/20 Rule**: Use fast/cheap models for 80% of operations, reserve expensive models for the 20% that need them.

### Deep Research (~20% of operations)
- **Models**: o4-mini-deep-research, o3-deep-research, Gemini Deep Research Agent
- **Cost**: $0.50-$2.00 per query (OpenAI), ~$1.00 (Gemini)
- **Use for**: Novel problem-solving, critical decisions, complex synthesis
- **Note**: Both OpenAI and Gemini deep research use async background jobs with polling

### Fast/General Operations (~80% of operations)
- **Models**: Grok 4 Fast, Gemini 2.5 Flash
- **Cost**: $0.001-$0.01 per query (96-99% cheaper)
- **Use for**: News, docs, team research, learning, expert chat, planning

**Result**: Using fast models for routine operations reduces total costs by ~90%.

## Deepr's Model Usage

### Research Commands
```bash
# Uses o4-mini-deep-research by default
deepr research "Complex topic"

# Override with specific model
deepr research "Topic" --model o3-deep-research

# Use Gemini Deep Research Agent
deepr research "Topic" --model gemini-deep-research
```

### Expert System
- **Campaign mode (deep)**: o4-mini-deep-research (10-45 min per topic)
- **Focus mode (quick)**: GPT-4.1 ($0.04/query, 1M+ context)
- **Expert chat**: Provider-dependent (OpenAI for vector store experts)
- **Quick lookups**: Grok 4 Fast ($0.01, when XAI_API_KEY available)

### Adaptive Routing
Deepr's model router (`deepr/experts/router.py`) automatically selects models based on:
- Query complexity
- Budget remaining
- Task type (factual vs reasoning)
- Context size

## Provider Configuration

**You only need one key to start.** Set any of these in `.env`:

```bash
# Pick one to get started — add more later for smarter routing
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

All model definitions live in `deepr/providers/registry.py`. This is the single source of truth.

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
