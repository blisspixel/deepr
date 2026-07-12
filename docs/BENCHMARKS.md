# Model Benchmarks

Status: historical benchmark and dry-run guide. Live provider benchmark
execution is gated in v2.36. Current model names and prices live in
`src/deepr/providers/registry.py` and are summarized in [MODELS.md](MODELS.md).
The measured results below are dated snapshots from the saved benchmark runs
named in each section, not live provider recommendations or execution guidance.

The benchmark substrate defines four historical tiers. Saved results can inform
review, but v2.36 does not run live provider benchmarks or automatically promote
their output into metered routing.

## Four Tiers

| Tier | What it tests | Models | Prompts | API | Typical cost |
|------|--------------|--------|---------|-----|-------------|
| **Chat** | Training data knowledge, reasoning, docs | 22 default + opt-in premium | 18 (6 task types) | Chat completions | Dry-run estimate |
| **News** | Web search, freshness, citations | 5 | 6 (3 task types) | OpenAI web search, Gemini 2.5 grounding | Dry-run ceiling |
| **Research** | Bounded multi-source reports | 4 orchestrated | 4 (2 task types) | Bounded web-search orchestration | Dry-run ceiling |
| **Docs** | API doc fetching, SDK guides | 4 | 5 (3 task types) | Bounded web search + chat completions | Dry-run ceiling |

Dry-run prints the historical plan and preflight estimate without provider
calls. A larger cap does not enable live execution in v2.36.

## Quick Start

```bash
# See the frozen plan and maximum estimate without provider calls
python scripts/benchmark_models.py --dry-run --tier all

# Inspect prompts without provider calls
python scripts/benchmark_models.py --show-prompts

# Run provider-free local comparison through the supported CLI
deepr eval local --model qwen2.5:14b --judge-model qwen2.5:14b --save
```

## Current Benchmark Target Sets

These lists mirror `scripts/benchmark_models.py` as of 2026-07-12 and exclude
deprecated registry entries. Historical tables below may still mention retired
or deprecated models because they describe prior saved runs.

### Chat Tier (22 default models)

- OpenAI: `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5-mini`,
  `gpt-4.1`, `gpt-4.1-mini`, `gpt-5.4-nano`, `gpt-5-nano`,
  `gpt-4.1-nano`, `o3`, `o4-mini`
- Anthropic: `claude-opus-4-8`, `claude-sonnet-5`, `claude-haiku-4-5`
- Gemini: `gemini-3.5-flash`, `gemini-3.1-pro-preview`,
  `gemini-3.1-flash-lite`, `gemini-3-flash-preview`,
  `gemini-2.5-pro`
- xAI: `grok-4.3`, `grok-4.20-reasoning`,
  `grok-4.20-non-reasoning`

Optional expensive models (add `--include-expensive`): `openai/gpt-5.5-pro`,
`openai/gpt-5.4-pro`, and `anthropic/claude-fable-5`.

### News Tier (5 models)

- OpenAI Responses API with web search: `gpt-5.5`, `gpt-5.4`,
  `gpt-5-mini`
- Gemini grounding: `gemini-2.5-flash`, `gemini-2.5-pro`

### Research Tier (4 bounded models)

| Provider | Models | API used |
|----------|--------|----------|
| OpenAI | `gpt-5.4`, `o3`, `gpt-5-mini` | Responses API with bounded web-search calls |
| Gemini | `gemini-2.5-pro` | Generate Content with one grounded-prompt charge |

Native OpenAI and Gemini managed deep-research agents are not benchmark execution
targets. Their autonomous token and tool loops do not expose a deterministic
request-level monetary ceiling. Gemini 3 grounded requests are also excluded
because one request can issue multiple separately billed search queries without
a documented per-request query cap. xAI search is excluded because `max_turns`
does not bound the number of parallel billable tool invocations within a turn.
Historical native-agent results remain below as dated evidence, not as current
executable targets.

### Docs Tier (4 models)

- OpenAI: `gpt-5.4`, `gpt-5-mini`, `o3`
- Gemini: `gemini-2.5-pro`

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

The script retains dry-run estimates and historical checkpoint readers. Its
live provider, judge, validation, fill-gap, new-model, and resume paths fail
closed in v2.36 until every call uses the shared durable research transaction.
Raising `--budget`, `--max-estimated-cost`, or `--no-cost-cap` does not unlock
them. Unknown pricing and request-level bounds also fail closed.

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
| `--budget DOLLARS` | Hard runtime ceiling shared by evaluation, judge, and validation calls |
| `--save` | Save results to `data/benchmarks/` |
| `--resume` | Gated live path; historical checkpoints remain readable |
| `--compare FILE` | Gated live path; compares a new run against a previous run |
| `--validate` | Gated live path; would test provider APIs |
| `--dry-run` | Show plan + cost estimate without making calls |
| `--show-prompts` | Display all eval prompts and exit |
| `--regenerate-rankings` | Rebuild rankings from stored benchmark data at `$0` |
| `--include-expensive` | Add expensive opt-in models to chat tier |
| `--fill-gaps` | Load prior results and run only missing model+tier combos |
| `--new-models` | Alias for `--fill-gaps` (recommended for new model launches) |
| `--max-estimated-cost DOLLARS` | Preflight threshold and runtime ceiling when `--budget` is absent |
| `--no-cost-cap` | Disable the default estimate cap; does not unlock live execution |
| `--judge-model MODEL` | Override the judge (default: openai/gpt-4.1-mini) |
| `--format table\|json` | Output format |
| `--emit-routing-config` | Gated live path; use `--regenerate-rankings` for stored data |
| `-v, --verbose` | Debug logging |

## Historical checkpoints

Existing `data/benchmarks/.checkpoint.json` files remain readable for forensic
review. Non-dry resume is not a works-now v2.36 path and must not dispatch or
replay provider calls.

## Historical Routing Snapshot

From the saved `data/benchmarks/routing_preferences.json` baseline used for
the 2026-02 benchmark notes:

- Freshness/citation/source diversity: `xai/grok-4-1-fast-non-reasoning`
- API reference + integration guide quality: `openai/gpt-5.4`
- Quick lookup/synthesis/technical docs quality: `gemini/gemini-3.1-pro-preview`
- Common value winner for chat-style tasks: `openai/gpt-4.1-nano`

These are task-specific historical winners. Current routing changes should use
a fresh cost-gated benchmark run, prefer `best_value` for cost-sensitive default
flows, and use `best_quality` only when explicitly requested.

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
- **gemini/gemini-2.5-pro**: **0.83** quality (33.2s, $0.180) - originally 0.00 due to thinking tokens eating the maxOutputTokens budget. Tied for #1 after fix.
- **openai/gpt-5**: **0.64** quality (40.1s, $0.180) - originally 5/18 timed out at 60s. After increasing timeout to 180s, all 18 passed. Still underperforms cheaper models - slow and expensive for the quality.

*Added 2026-02-19:*
- **gemini/gemini-3.1-pro-preview**: **0.83** quality (39.0s, $0.220) - tied for #1 with gpt-4.1-mini and gemini-2.5-pro. Strong across all task types, especially document_analysis (0.91) and quick_lookup (0.90). Configurable thinking adds latency (~40s avg) but improves reasoning quality vs 3.0 Pro (0.46 -> 0.83).

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

*Added 2026-02-19:*
- **gemini/gemini-3.1-pro-preview**: **0.48** quality (82.0s, 7.3 avg citations, $0.073) - ranks between Gemini 2.5 Pro and 3.0 Pro. Higher latency than other Gemini models due to thinking tokens.

Grok dominates the news tier. Grok 4.1 leads on freshness; Grok 4.0 leads on citation quality and source diversity. Gemini 3 models produce fewer citations than 2.5 models, suggesting grounding API maturity differences.

### Research Tier

| Rank | Model | Quality | Latency | Avg Citations | Avg Words | Cost |
|------|-------|---------|---------|---------------|-----------|------|
| 1 | openai/o3-deep-research | **0.84** | 7.0 min | 88.5 | 6214 | $0.097 |
| 2 | openai/o4-mini-deep-research | 0.82 | 11.3 min | 70.2 | 1937 | $0.010 |
| 3 | gemini/deep-research | 0.60 | 6.9 min | 0.0 | 2320 | $0.011 |

o3-deep-research produces the longest, most-cited reports. o4-mini is nearly as good at 1/10th the cost. Gemini deep-research returned zero parsed citations (API may structure them differently than expected).

*Added 2026-02-19:*
- **gemini/gemini-3.1-pro-preview** (orchestrated research): **0.60** quality (72.5s, $0.049) - uses web search tool orchestration rather than native deep research. Faster (~1 min vs 5-15 min) but lower quality than dedicated deep research models. Good for budget-conscious research.

### Docs Tier (2026-02-14 Baseline)

| Rank | Model | Quality | Latency | Cost |
|------|-------|---------|---------|------|
| 1 | openai/gpt-5.2 | **0.83** | 69.9s | $0.042 |
| 2 | xai/grok-4-fast-reasoning | 0.78 | 54.7s | $0.001 |
| 3 | xai/grok-4-1-fast-reasoning | 0.77 | 41.8s | $0.001 |
| 4 | openai/gpt-5 | 0.75 | 140.0s | $0.030 |
| 5 | gemini/gemini-3-pro-preview | 0.70 | 58.4s | $0.037 |
| 6 | gemini/gemini-3.1-pro-preview | 0.68 | 80.3s | $0.049 |
| 7 | openai/gpt-5-mini | 0.65 | 38.7s | $0.006 |
| 8 | openai/o3 | 0.65 | 42.0s | $0.025 |
| 9 | gemini/gemini-2.5-pro | 0.37 | 41.6s | $0.030 |

Docs tier tests API documentation fetching, SDK guides, and integration guides. Grok models offer the best value (near-top quality at $0.001). Gemini 3.1 Pro (0.68) scores slightly below 3.0 Pro (0.70) here - the thinking overhead adds latency without improving doc-fetching quality. 1 eval timed out for 3.1 Pro on the SDK documentation prompt.

### Historical Cross-Tier Routing Snapshot

This table is part of the 2026-02 saved benchmark narrative. Do not treat it
as the current routing table. Current routing should be regenerated from fresh
cost-gated benchmark data and filtered through the active registry.

| Use case | Recommended model | Fallback | Cost |
|----------|------------------|----------|------|
| Quick lookup / simple Q&A | xai/grok-4-fast | openai/gpt-4.1-mini | $0.001-0.01 |
| Technical docs / reasoning | openai/gpt-4.1-mini | openai/gpt-4.1 | $0.01-0.08 |
| Live news / fresh info | xai/grok-4-1-fast-reasoning | xai/grok-4-fast-reasoning | $0.002 |
| Expert knowledge synthesis | anthropic/claude-sonnet-4-5 | openai/gpt-4.1 | $0.08-0.14 |
| Deep research report | openai/o4-mini-deep-research | openai/o3-deep-research | $0.01-0.10 |

## New Model Onboarding Playbook

Use this process whenever providers release new models.

1. Discovery
- Check provider model docs/changelogs (OpenAI, Anthropic, Google, xAI).
- Only consider models that match Deepr workflows: `deep_research`, `reasoning/synthesis`, or `cheap lookup/news/docs`.

2. Registry update
- Add model metadata in `src/deepr/providers/registry.py` (pricing, latency, context, strengths/weaknesses).
- Add provider alias/mapping support in provider implementation if model IDs differ from friendly names.

3. Tier placement
- Put each model only in relevant tiers in `scripts/benchmark_models.py`:
  - `ORCHESTRATED_RESEARCH_MODELS` for web-search orchestration
  - `NEWS_MODELS` / `DOCS_MODELS` only if web-grounded docs/news behavior matters
- Do not add a managed agent or grounded model unless its token and tool charges
  have deterministic request-level maxima that the estimator covers.

4. Provider-free evidence flow
- Estimate first: `deepr eval new --dry-run --tier all`
- Run `deepr eval local` or `deepr eval local-context` for current `$0`
  evidence.
- Do not run non-dry `deepr eval new` until the v2.36 live benchmark gate is
  restored through the shared transaction.

5. Promote or rollback
- If quality improves for target tier(s), keep model in routing candidates.
- If quality regresses or cost/latency is poor, keep model in registry but remove from benchmark defaults/routing candidates.

## Adding New Models

1. Add the model to `src/deepr/providers/registry.py` with pricing and capabilities
2. Add it to the appropriate tier list in `scripts/benchmark_models.py`:
   - `DEFAULT_MODELS` for chat tier
   - `NEWS_MODELS` for news tier
   - `ORCHESTRATED_RESEARCH_MODELS` for research tier (web-search orchestration)
   - `DOCS_MODELS` for docs tier
3. If it needs a new API caller, add a `call_*` function and route it in `call_model()`
4. Dry-run: `python scripts/benchmark_models.py --dry-run --tier <tier> --model <new_model>`
5. Collect provider-free evidence with `deepr eval local` where applicable.
   Live validation and benchmark dispatch remain gated in v2.36.

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
- **Managed deep-research agents**: Historical results remain documented, but
  paid benchmark execution is blocked until provider APIs expose deterministic
  per-request token and tool ceilings.
- **Gemini 3 grounding**: Paid benchmark execution is blocked because billing is
  per generated search query and the API documents no per-request query cap.
- **xAI search tools**: Paid benchmark execution is blocked because `max_turns`
  does not cap parallel billable tool invocations within each turn. Chat-tier
  Grok 4.3 evaluation uses the Responses API without server-side tools.
