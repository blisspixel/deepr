# Model Selection Guide

> **Note**: Model information current as of January 31, 2026. AI models evolve rapidly - verify current pricing and capabilities at provider websites before making decisions.

## Overview

Deepr uses a hybrid approach optimizing for both quality and cost. Different tasks benefit from different models.

## Provider Landscape

### OpenAI
- **Deep Research**: Only provider with turnkey async Deep Research API
- **Models**: GPT-5.2, GPT-5.1, gpt-5-mini, gpt-5-nano, o3-deep-research, o4-mini-deep-research
- **Best for**: Planning, curriculum generation, deep research

### xAI (Grok)
- **Models**: Grok 4, Grok 4 Fast, Grok 4 Heavy
- **Best for**: Cost-effective general operations, real-time X/Twitter integration
- **Note**: 47x cheaper than GPT-5.2 for comparable tasks

### Google (Gemini)
- **Models**: Gemini 2.5 Flash, Gemini 3 Pro
- **Best for**: Large context windows (1M+ tokens), document analysis

### Anthropic (Claude)
- **Models**: Claude Sonnet 4.5, Claude Opus 4.5, Claude Haiku 4.5
- **Best for**: Coding tasks, extended thinking/reasoning transparency

## Model Selection by Task

| Task | Recommended Model | Cost | Latency | Notes |
|------|-------------------|------|---------|-------|
| Deep Research | o4-mini-deep-research | $0.50-2.00 | 5-20 min | Async, comprehensive |
| Complex Research | o3-deep-research | $2.00-5.00 | 10-30 min | Maximum depth |
| Planning/Curriculum | GPT-5.2 | $0.20-0.30 | 2-5s | Best reasoning |
| Quick Lookups | Grok 4 Fast | $0.01 | <1s | Cost-effective |
| Large Documents | Gemini 3 Pro | $0.15 | 3-5s | 1M token context |
| Coding Tasks | Claude Sonnet 4.5 | $0.25 | 2-4s | Best for code |

## Cost Optimization Strategy

**The 80/20 Rule**: Use fast/cheap models for 80% of operations, reserve expensive models for the 20% that need them.

### Deep Research (~20% of operations)
- **Models**: o4-mini-deep-research, o3-deep-research
- **Cost**: $0.50-$5.00 per query
- **Use for**: Novel problem-solving, critical decisions, complex synthesis

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
```

### Expert System
- **Curriculum generation**: GPT-5.2
- **Expert chat**: GPT-5.2 with tool calling
- **Quick lookups**: Grok 4 Fast (when available)

### Adaptive Routing
Deepr's model router (`deepr/experts/router.py`) automatically selects models based on:
- Query complexity
- Budget remaining
- Task type (factual vs reasoning)
- Context size

## Provider Configuration

Set API keys in `.env`:
```bash
OPENAI_API_KEY=sk-...
XAI_API_KEY=...
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
```

Deepr will use available providers and route appropriately.

## Model Registry

All model definitions live in `deepr/providers/registry.py`. This is the single source of truth.

**When new models are released**: Update ONLY the registry. Never hardcode model names elsewhere in the codebase.

## Keeping Current

AI models change frequently. To verify current information:
- OpenAI: https://platform.openai.com/docs/models
- xAI: https://x.ai/api
- Google: https://ai.google.dev/models
- Anthropic: https://docs.anthropic.com/claude/docs/models-overview

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical architecture
- [FEATURES.md](FEATURES.md) - Feature guide with model options
- [../ROADMAP.md](../ROADMAP.md) - Development priorities
