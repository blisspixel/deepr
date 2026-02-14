# Model Benchmarks

Deepr includes a tiered model benchmark system that tests every provider across three distinct use cases. Results drive the auto-mode routing table — the system that picks which model handles each research query.

## Three Tiers

| Tier | What it tests | Models | Prompts | API | Typical cost |
|------|--------------|--------|---------|-----|-------------|
| **Chat** | Training data knowledge, reasoning, docs | 11 | 18 (6 task types) | Chat completions | ~$0.80 |
| **News** | Web search, freshness, citations | 6 | 6 (3 task types) | Grok Responses API + Gemini grounding | ~$0.20 |
| **Research** | Autonomous multi-source reports | 3 | 4 (2 task types) | OpenAI Responses (background) + Gemini Interactions | ~$0.12 |

**Total cost for a full `--tier all` run: ~$1.10** (actual, based on 2026-02-13 run).

## Quick Start

```bash
# 1. Validate your API keys work
python scripts/benchmark_models.py --validate

# 2. See what will run and estimated cost
python scripts/benchmark_models.py --dry-run --tier all

# 3. Run the cheapest test first (news, no judge, ~$0.05)
python scripts/benchmark_models.py --tier news --quick --no-judge

# 4. Full benchmark with saved results
python scripts/benchmark_models.py --tier all --save

# 5. Re-run a specific model that failed
python scripts/benchmark_models.py --tier chat --model gemini/gemini-2.5-pro --save
```

## Models Tested

### Chat Tier (11 models)

| Model | Provider | Typical cost/query |
|-------|----------|--------------------|
| openai/gpt-4.1-mini | OpenAI | $0.001 |
| openai/gpt-5-mini | OpenAI | $0.002 |
| openai/gpt-4.1 | OpenAI | $0.004 |
| openai/gpt-5 | OpenAI | $0.010 |
| xai/grok-4-fast | xAI | $0.001 |
| gemini/gemini-2.5-flash | Google | $0.001 |
| gemini/gemini-2.5-pro | Google | $0.012 |
| gemini/gemini-3-flash-preview | Google | $0.003 |
| gemini/gemini-3-pro-preview | Google | $0.012 |
| anthropic/claude-haiku-4-5 | Anthropic | $0.003 |
| anthropic/claude-sonnet-4-5 | Anthropic | $0.008 |

Optional expensive models (add `--include-expensive`): gpt-5.2, claude-opus-4-6.

### News Tier (6 models)

| Model | Provider | API used |
|-------|----------|----------|
| xai/grok-4-1-fast-reasoning | xAI | Responses API + `web_search` tool |
| xai/grok-4-fast-reasoning | xAI | Responses API + `web_search` tool |
| gemini/gemini-3-flash-preview | Google | generateContent + `google_search` grounding |
| gemini/gemini-3-pro-preview | Google | generateContent + `google_search` grounding |
| gemini/gemini-2.5-flash | Google | generateContent + `google_search` grounding |
| gemini/gemini-2.5-pro | Google | generateContent + `google_search` grounding |

### Research Tier (3 models)

| Model | Provider | API used | Typical time |
|-------|----------|----------|-------------|
| openai/o3-deep-research | OpenAI | Responses API (background + polling) | 5-15 min |
| openai/o4-mini-deep-research | OpenAI | Responses API (background + polling) | 10-20 min |
| gemini/deep-research | Google | Interactions API (background + polling) | 5-15 min |

Research tier jobs run asynchronously — the benchmark submits them with `"background": true`, then polls every 5-30s until completion. Timeout: 60 minutes per job.

## Scoring

Each tier uses a different scoring formula optimized for what matters:

### Chat: `quality = 0.70 * judge + 0.30 * reference_match`
- **Judge** (GPT-4.1-mini): Scores accuracy, completeness, clarity, reasoning, conciseness (0-10 each)
- **Reference match**: How closely the response matches the known-good answer

### News: `quality = 0.60 * judge + 0.40 * citation_score`
- **Judge**: Scores freshness (0.30), accuracy (0.20), citation quality (0.25), completeness (0.15), source diversity (0.10)
- **Citation score**: 60% citation count (0-8 normalized) + 40% domain diversity (0-5 unique domains normalized)

### Research: `quality = 0.50 * judge + 0.50 * citation_score`
- **Judge**: Scores comprehensiveness (0.25), accuracy (0.25), synthesis (0.20), structure (0.15), citation integration (0.15)
- **Citation score**: 35% count (0-20) + 25% domain diversity (0-10) + 25% report length (0-2000 words) + 15% structure (headings present)

## CLI Reference

```
python scripts/benchmark_models.py [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--tier chat\|news\|research\|all` | Which tier to benchmark (default: chat) |
| `--model MODEL` | Only benchmark one model (e.g. `openai/gpt-5`) |
| `--provider PROVIDER` | Only benchmark models from this provider |
| `--quick` | Run 1 prompt per task type instead of all |
| `--no-judge` | Skip LLM judge, use reference/citation scoring only |
| `--budget DOLLARS` | Maximum spend — bypasses interactive safety prompt |
| `--save` | Save results to `data/benchmarks/` |
| `--resume` | Resume from checkpoint — skip completed evals |
| `--compare FILE` | Compare against a previous benchmark run |
| `--validate` | Test provider APIs (no benchmark) |
| `--dry-run` | Show plan + cost estimate without making calls |
| `--show-prompts` | Display all eval prompts and exit |
| `--include-expensive` | Add gpt-5.2 and claude-opus-4-6 to chat tier |
| `--judge-model MODEL` | Override the judge (default: openai/gpt-4.1-mini) |
| `--format table\|json` | Output format |
| `--emit-routing-config` | Write `routing_preferences.json` for auto-mode |
| `-v, --verbose` | Debug logging |

## Checkpoint / Resume

Every eval result is auto-saved to `data/benchmarks/.checkpoint.json` after completion. If a run crashes (network error, timeout, Ctrl+C):

```bash
python scripts/benchmark_models.py --tier all --resume --save
```

This skips already-completed evals and picks up where you left off. The checkpoint is cleared after a successful run.

For research tier jobs that may take 45+ minutes, the timeout is set to 60 minutes. If a job times out, the error message includes the job ID so you can check it manually:

```
TimeoutError: OpenAI deep research timed out after 3600s.
Job resp_abc123 may still be running -- check with:
GET https://api.openai.com/v1/responses/resp_abc123
```

## Results (2026-02-13 Baseline)

### Chat Tier

| Rank | Model | Quality | Latency | Cost | $/Quality |
|------|-------|---------|---------|------|-----------|
| 1 | openai/gpt-4.1-mini | **0.82** | 8.6s | $0.016 | $0.019 |
| 2 | xai/grok-4-fast | 0.81 | 6.8s | $0.005 | $0.007 |
| 3 | openai/gpt-4.1 | 0.80 | 8.5s | $0.079 | $0.098 |
| 4 | anthropic/claude-sonnet-4-5 | 0.78 | 10.4s | $0.143 | $0.183 |
| 5 | anthropic/claude-haiku-4-5 | 0.77 | 4.7s | $0.048 | $0.062 |
| 6 | openai/gpt-5-mini | 0.69 | 16.5s | $0.036 | $0.052 |
| 7 | gemini/gemini-3-pro-preview | 0.46 | 11.0s | $0.220 | $0.482 |
| 8 | gemini/gemini-3-flash-preview | 0.36 | 4.0s | $0.055 | $0.152 |
| 9 | gemini/gemini-2.5-flash | 0.30 | 2.9s | $0.045 | $0.152 |

*Re-run results (fixing bugs in original run):*
- **gemini/gemini-2.5-pro**: **0.83** quality (33.2s, $0.180) — originally 0.00 due to thinking tokens eating the maxOutputTokens budget. Tied for #1 after fix.
- **openai/gpt-5**: **0.64** quality (40.1s, $0.180) — originally 5/18 timed out at 60s. After increasing timeout to 180s, all 18 passed. Still underperforms cheaper models — slow and expensive for the quality.

Chat best-by-task: document_analysis (gpt-5-mini), knowledge_base (claude-sonnet-4-5), quick_lookup (gemini-3-pro-preview), reasoning (gpt-4.1-mini), synthesis (gpt-4.1), technical_docs (grok-4-fast).

Best value across all chat tasks: **xai/grok-4-fast** ($0.007/quality point).

### News Tier

| Rank | Model | Quality | Latency | Avg Citations | Cost |
|------|-------|---------|---------|---------------|------|
| 1 | xai/grok-4-1-fast-reasoning | **0.66** | 24.8s | 19.0 | $0.002 |
| 2 | xai/grok-4-fast-reasoning | 0.65 | 20.2s | 13.3 | ~$0.00 |
| 3 | gemini/gemini-2.5-pro | 0.45 | 25.1s | 20.2 | $0.060 |
| 4 | gemini/gemini-3-pro-preview | 0.42 | 53.8s | 7.3 | $0.073 |
| 5 | gemini/gemini-2.5-flash | 0.42 | 10.3s | 13.8 | $0.015 |
| 6 | gemini/gemini-3-flash-preview | 0.36 | 22.4s | 5.2 | $0.018 |

Grok dominates the news tier. Grok 4.1 leads on freshness; Grok 4.0 leads on citation quality and source diversity. Gemini 3 models produce fewer citations than 2.5 models, suggesting grounding API maturity differences.

### Research Tier

| Rank | Model | Quality | Latency | Avg Citations | Avg Words | Cost |
|------|-------|---------|---------|---------------|-----------|------|
| 1 | openai/o3-deep-research | **0.84** | 7.0 min | 88.5 | 6214 | $0.097 |
| 2 | openai/o4-mini-deep-research | 0.82 | 11.3 min | 70.2 | 1937 | $0.010 |
| 3 | gemini/deep-research | 0.60 | 6.9 min | 0.0 | 2320 | $0.011 |

o3-deep-research produces the longest, most-cited reports. o4-mini is nearly as good at 1/10th the cost. Gemini deep-research returned zero parsed citations (API may structure them differently than expected).

### Cross-Tier Routing Recommendations

| Use case | Recommended model | Fallback | Cost |
|----------|------------------|----------|------|
| Quick lookup / simple Q&A | xai/grok-4-fast | openai/gpt-4.1-mini | $0.001-0.01 |
| Technical docs / reasoning | openai/gpt-4.1-mini | openai/gpt-4.1 | $0.01-0.08 |
| Live news / fresh info | xai/grok-4-1-fast-reasoning | xai/grok-4-fast-reasoning | $0.002 |
| Expert knowledge synthesis | anthropic/claude-sonnet-4-5 | openai/gpt-4.1 | $0.08-0.14 |
| Deep research report | openai/o4-mini-deep-research | openai/o3-deep-research | $0.01-0.10 |

## Adding New Models

1. Add the model to `deepr/providers/registry.py` with pricing and capabilities
2. Add it to the appropriate tier list in `scripts/benchmark_models.py`:
   - `DEFAULT_MODELS` for chat tier
   - `NEWS_MODELS` for news tier
   - `RESEARCH_MODELS` for research tier
3. If it needs a new API caller, add a `call_*` function and route it in `call_model()`
4. Validate: `python scripts/benchmark_models.py --validate --tier <tier>`
5. Benchmark: `python scripts/benchmark_models.py --tier <tier> --model <new_model> --save`

## Output Files

Results are saved to `data/benchmarks/benchmark_YYYYMMDD_HHMMSS.json` with structure:

```json
{
  "timestamp": "2026-02-13T21:40:03Z",
  "total_cost": 0.17,
  "rankings": [
    {
      "model_key": "xai/grok-4-1-fast-reasoning",
      "avg_quality": 0.66,
      "avg_latency_ms": 24828,
      "total_cost": 0.002,
      "cost_per_quality": 0.003,
      "scores_by_type": {"freshness": 0.64, "citation_quality": 0.58, "source_diversity": 0.77},
      "num_evals": 6,
      "errors": 0,
      "tier": "news"
    }
  ],
  "results": [
    {
      "model": "xai/grok-4-1-fast-reasoning",
      "tier": "news",
      "task_type": "freshness",
      "difficulty": "medium",
      "quality": 0.72,
      "judge_score": 0.55,
      "citation_score": 1.0,
      "citation_count": 21,
      "latency_ms": 17800,
      "judge_details": {"freshness": 7.0, "accuracy": 6.0, ...}
    }
  ]
}
```

## Known Issues

- **Gemini 2.5 Pro (chat tier)**: Mandatory thinking tokens consume the entire `maxOutputTokens` budget on small prompts. Fixed by increasing the budget to `max_tokens + 3072` for pro models. Re-run required for older results.
- **GPT-5 timeouts**: Reasoning-hard prompts can exceed the 60s timeout. 2 of 18 evals failed in the baseline run.
- **Gemini deep-research citations**: The Interactions API returns citations in a structure that may differ from what the parser expects, resulting in 0 parsed citations despite the reports containing source references.
- **Gemini 3 grounding**: Newer than 2.5, but currently produces fewer grounding citations in the news tier (5-7 avg vs 14-20 for 2.5 models). May improve as the API matures.
