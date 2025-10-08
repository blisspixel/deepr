# Deepr

**Knowledge Is Power. Automate It.**

Automate deep research using OpenAI's Deep Research API. Queue jobs via CLI or web UI, get comprehensive reports with inline citations. Built for multi-phase research campaigns where each phase builds on previous findings.

## Quick Start

```bash
# Install
pip install -r requirements.txt
pip install -e .
cp .env.example .env  # Add your OPENAI_API_KEY

# Start services
python bin/start-worker.py &              # Polls OpenAI for job completion
python deepr/api/app_simple.py &          # API server for web UI
cd deepr/web/frontend && npm run dev      # Web UI at http://localhost:3000

# Submit research via CLI
deepr research submit "Analyze AI code editor market" --yes
deepr research wait <job-id>
```

Full setup guide: [docs/QUICKSTART.md](docs/QUICKSTART.md)

## What It Does

**Single Deep Research Jobs** (working now)

Uses OpenAI Deep Research (o3/o4-mini) for autonomous multi-step research:

```bash
deepr research submit "Competitive analysis of AI code review tools" --yes
deepr research wait <job-id>
```

- Time: 2-60+ minutes (autonomous research with web search)
- Cost: $0.50-$5+ per report
- Output: Comprehensive markdown reports with inline citations
- Queue-based: Worker polls OpenAI, downloads results when complete

**Multi-Phase Research Campaigns** (in development)

Orchestrate interconnected research where each phase builds on previous findings:

```bash
deepr prep plan "Analyze electric vehicle market" --topics 7

# Generates intelligent plan:
Phase 1: Foundation (parallel)
  - Market sizing and growth trends
  - Key players and market share
  - Technology landscape

Phase 2: Analysis (uses Phase 1 as context)
  - Competitive dynamics [feeds: market data + players]
  - Technology roadmap [feeds: landscape analysis]

Phase 3: Synthesis (integrates all findings)
  - Strategic implications
  - Executive summary

deepr prep review    # Review generated plan
deepr prep execute   # Submit all jobs
```

How it works:
- Agentic planner (GPT-4) reasons about information needs and dependencies
- Context chaining: Phase 2 prompts explicitly reference Phase 1 findings
- Context summarization: Cuts token usage ~70% while preserving key information
- Smart task mix: Balances documentation (factual gathering) vs analysis (synthesis)
- Doc reuse: Checks existing research to avoid redundant work

Result: Comprehensive, interconnected analysis—not isolated reports.

## Architecture

```
Single Job:
User → SQLite Queue → Worker polls OpenAI → Result saved as markdown

Multi-Phase Campaign:
User → GPT-4 Planner → Research Plan (with dependencies)
         ↓
     Phase 1 (parallel execution)
         ↓ [inject summarized results as context]
     Phase 2 (sequential execution)
         ↓ [inject all findings]
     Phase 3 (synthesis)
```

**Why queue-based?** Deep research takes 2-60+ minutes per job—too long for synchronous request/response.

**Local-first design:**
- SQLite queue (no external database)
- Filesystem storage (no cloud required)
- OpenAI API (only external dependency)

## Cost & Time

| Type | Cost | Time |
|------|------|------|
| Simple queries | $0.05-$0.20 | 2-5 minutes |
| Medium reports | $0.20-$0.80 | 5-15 minutes |
| Comprehensive | $1-$3 | 15-30 minutes |

o3-deep-research costs ~10x more than o4-mini but is more thorough.

Multi-phase campaigns multiply by number of tasks, but context chaining reduces redundancy.

## Use Cases

**Good for:**
- Market analysis requiring multiple angles
- Technical due diligence with dependencies
- Strategic planning needing comprehensive context
- Research where findings inform subsequent questions

**Not for:**
- Quick facts (use regular GPT)
- Conversational chat
- Real-time applications
- Isolated queries without context needs

## Current Status

**v2.0 - Production Ready**

Working now:
- CLI: submit, wait, status, result, cancel, queue management
- Worker: Background polling with stuck job detection (auto-cancels queued >10min)
- Web UI: ChatGPT-style interface with real-time job queue, cost analytics, minimal monochrome design
- Cost tracking: Automatic from OpenAI token usage
- SQLite queue + filesystem storage
- Validated with live jobs

**v2.1 - Active Development**

Building now:
- Agentic planner: Multi-phase research with dependencies
- Context chaining: Feed prior research to later phases
- Doc analysis: `deepr docs analyze` scans existing research, identifies gaps
- Results library: Browse and view completed research

See [ROADMAP.md](ROADMAP.md) for details.

## Multi-Provider Support

Deepr is designed to work with multiple deep research providers:

**OpenAI** (o3-deep-research, o4-mini-deep-research):
- Current primary provider (most mature offering)
- Turnkey API with autonomous planning and web search
- Time: 2-60+ minutes, Cost: $0.50-$5+ per report

**Azure OpenAI** (same models, enterprise integration):
- Same core capabilities via Azure AI Foundry
- Bing Search integration for data retrieval
- Enterprise compliance and deployment

**Anthropic** (Claude with Extended Thinking):
- SDK-based approach with more control
- Custom tool integration
- Future provider support

Provider selection:
- Default: OpenAI (most mature)
- Manual: CLI `--provider openai|azure|anthropic` flag
- Future: Auto-routing to best provider per task

## Configuration

`.env` file:

```bash
# OpenAI (primary)
OPENAI_API_KEY=sk-...

# Azure OpenAI (optional)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...

# Anthropic (future)
ANTHROPIC_API_KEY=...

# Cost limits
DEEPR_MAX_COST_PER_JOB=10.0
DEEPR_MAX_COST_PER_DAY=100.0
DEEPR_MAX_COST_PER_MONTH=1000.0
```

## CLI Commands

```bash
# Single research job
deepr research submit "<prompt>" --yes
deepr research wait <job-id>       # Wait for completion
deepr research status <job-id>     # Check status
deepr research result <job-id>     # Display result
deepr research cancel <job-id>     # Cancel job

# Multi-phase campaign (in development)
deepr prep plan "High-level goal" --topics 5
deepr prep review                  # Review generated plan
deepr prep execute                 # Submit all jobs

# Queue management
deepr queue list                   # List all jobs
deepr queue stats                  # Show queue statistics

# Doc analysis (in development)
deepr docs analyze "path/to/docs" "Your scenario" --topics 6
# Scans docs, identifies gaps, generates research plan
```

Web UI alternative:
```bash
python -m deepr.api.app            # Start API server
# Visit http://localhost:5000
```

## What Is Deep Research?

Deep Research is autonomous multi-step research using advanced LLMs:

1. **Planning**: Model breaks down query into research steps
2. **Execution**: Autonomously searches web, reads sources, gathers information
3. **Synthesis**: Analyzes findings, identifies patterns, generates insights
4. **Output**: Comprehensive report with inline citations

This differs from standard LLM queries:
- Standard GPT: Single prompt → single response (seconds, $0.01)
- Deep Research: Agentic loop → comprehensive analysis (minutes-hours, $0.50-$5+)

See [docs/DEEP_RESEARCH_EXPLAINED.md](docs/DEEP_RESEARCH_EXPLAINED.md) for detailed comparison.

## Documentation

- [docs/QUICKSTART.md](docs/QUICKSTART.md) - Detailed setup guide
- [docs/CLI_GUIDE.md](docs/CLI_GUIDE.md) - Complete command reference
- [docs/DEEP_RESEARCH_EXPLAINED.md](docs/DEEP_RESEARCH_EXPLAINED.md) - Deep research vs standard LLMs
- [docs/AGENTIC_PLANNING_EXAMPLE.md](docs/AGENTIC_PLANNING_EXAMPLE.md) - Multi-phase research walkthrough
- [ROADMAP.md](ROADMAP.md) - Development roadmap and plans

## Philosophy

Research is the foundation of good decision-making. Comprehensive research requires understanding what you need to know, sequencing research intelligently, building context across findings, and synthesizing insights.

Deepr automates this entire process. State your goal once, get comprehensive interconnected analysis.

**Do your homework. Knowledge is power. Automate it.**
