# Deepr

**Knowledge Is Power. Automate It.**

Agentic research automation platform for deep research across multiple providers (OpenAI, Azure, Anthropic). Not just a wrapper—an intelligent system that plans, sequences, and chains research to build comprehensive understanding.

## What Makes This Different

Most AI tools give isolated answers. Deepr orchestrates multi-phase research campaigns where each phase builds on previous findings.

**Provider-Agnostic Platform**: Not a wrapper for one API - a research automation platform that works with multiple providers (OpenAI, Azure OpenAI, Anthropic, etc.) and intelligently routes tasks to the best provider for each job.

**The Problem**
You want to analyze the electric vehicle market. Traditional approach:
- Run 5 separate research queries
- Get 5 isolated reports
- Manually synthesize findings
- Figure out implications yourself

**The Deepr Way**
```bash
deepr prep plan "Analyze electric vehicle market" --topics 7
```

Agentic planner reasons about information needs:

**Phase 1: Foundation** (parallel - no dependencies)
- Market sizing and growth trends
- Key players and market share
- Technology comparison

**Phase 2: Analysis** (uses Phase 1 as context)
- Competitive dynamics [feeds: market data + player profiles]
- Technology roadmap [feeds: current tech comparison]

**Phase 3: Synthesis** (integrates all findings)
- Strategic implications [feeds: all previous research]
- Executive summary [feeds: complete analysis]

Each phase injects prior research as context using summarization techniques that cut token usage by ~70% while preserving key information. Phase 2 research prompts explicitly reference Phase 1 findings with phrases like "Using the market data from Phase 1..." Final synthesis integrates insights across all research.

**Result:** Comprehensive, interconnected analysis—not isolated reports. Research shows this approach improves both quality (less context dilution) and cost-effectiveness compared to sending full context repeatedly.

## Core Capabilities

**Single Deep Research Jobs**

For one comprehensive report:

```bash
deepr research submit "Competitive analysis of AI code review tools" --yes
deepr research wait <job-id>
```

Uses OpenAI Deep Research (o3/o4-mini) which:
- Takes 2-60+ minutes (agentic multi-step research)
- Costs $0.50-$5+ per report
- Autonomously searches, reads, analyzes, synthesizes
- Produces structured reports with inline citations

**Multi-Phase Research Campaigns** (in development)

For interconnected analysis:

```bash
# Step 1: Plan (costs $0.01, uses GPT-5)
# Use --check-docs to scan existing research and avoid redundancy
deepr prep plan "Build an AI code review tool" --topics 5 --check-docs

Phase 1: Foundation
  1. Market landscape analysis
  2. Technical approaches survey
  3. Integration patterns research

Phase 2: Analysis (uses Phase 1 context)
  4. Competitive positioning [needs: 1,2]
  5. Architecture recommendations [needs: 2,3]

Phase 3: Synthesis (uses all)
  6. Go-to-market strategy [needs: all]

# Step 2: Review and approve tasks
deepr prep review

# Step 3: Execute
deepr prep execute
```

Phase 2 research gets Phase 1 findings injected as context. Synthesis report integrates insights from all phases. Creates analysis greater than the sum of its parts.

## Architecture

```
Single Job:
User → Queue → Deep Research (2-60 min) → Result

Multi-Phase Campaign:
User → GPT-5 Planner → Research Plan
         ↓
     Phase 1 (parallel)
         ↓ [inject results as context]
     Phase 2 (sequential)
         ↓ [inject all results]
     Phase 3 (synthesis)
         ↓
     Comprehensive Analysis
```

Queue-based because deep research takes too long for synchronous request/response. Research agent polls OpenAI API and updates status when jobs complete.

## Quick Start

```bash
# Install
pip install -r requirements.txt
pip install -e .  # Install Deepr CLI
cp .env.example .env
# Edit .env: add OPENAI_API_KEY

# Start worker (polls OpenAI for job completion)
python bin/start-worker.py &

# Start API server (for web UI)
python deepr/api/app_simple.py &

# Start web interface (in another terminal)
cd deepr/web/frontend && npm install && npm run dev
# Visit http://localhost:3000

# Single research job
deepr research submit "Analyze AI code editor market" --yes
deepr research wait <job-id>

# Agentic doc analysis
deepr docs analyze "docs/my-project" "Your scenario" --topics 6

# Multi-phase campaign (in development)
deepr prep plan "Build an AI tool" --topics 5
deepr prep execute
```

Full guide: [docs/QUICKSTART.md](docs/QUICKSTART.md)

## What Is Deep Research?

Deep Research capabilities vary by provider but share core traits:

**OpenAI** (o3-deep-research, o4-mini-deep-research):
- Time: 2-60+ minutes per job
- Cost: $0.50-$5+ per report
- Turnkey API with autonomous planning and web search
- Current primary provider (most mature offering)

**Azure OpenAI** (same models, enterprise integration):
- Same core capabilities via Azure AI Foundry
- Tight integration with Azure ecosystem
- Bing Search for data retrieval

**Anthropic** (Claude with Extended Thinking):
- More control via SDK approach
- Custom tool integration
- Developer-managed agentic loop
- Future provider support

**Platform Approach**: Deepr is designed to work with multiple providers. Currently focused on OpenAI (most mature), with architecture built to support Azure OpenAI, Anthropic, and future providers as they emerge.

See [docs/DEEP_RESEARCH_EXPLAINED.md](docs/DEEP_RESEARCH_EXPLAINED.md) for provider comparison.

## Cost & Time

Simple queries: $0.05-$0.20, 2-5 minutes
Medium reports: $0.20-$0.80, 5-15 minutes
Comprehensive: $1-$3, 15-30 minutes

o3-deep-research costs ~10x more but is more thorough.

Multi-phase campaigns: Multiply by number of tasks, get interconnected analysis.

## Use Cases

**Good For:**
- Market analysis requiring multiple angles
- Technical due diligence with dependencies
- Strategic planning needing comprehensive context
- Research where findings inform subsequent questions

**Not For:**
- Quick facts (use regular GPT)
- Conversational chat
- Real-time applications
- Isolated queries without context needs

## The Agentic Planning Insight

Traditional tools: "Split topic into subtopics"

Deepr: "Reason about information architecture and task mix"

**Smart Task Mix**

The planner generates the right balance of documentation and analysis:

Documentation tasks (gather facts):
- "Document latest OpenAI pricing and rate limits"
- "Compile Python async/await best practices"
- Goal: Create reference materials, factual basis

Research/Analysis tasks (generate insights):
- "Analyze trade-offs between SQLite vs PostgreSQL"
- "Evaluate cost-effectiveness of LLM providers"
- Goal: Synthesize information, make recommendations

**Why This Matters**

Phase 1: Mix of documentation (facts) + foundational research (landscape)
Phase 2: Analysis tasks USE Phase 1 docs as context
Phase 3: Synthesis integrates facts AND insights

This is cost-effective because:
- Documentation tasks are cheaper (factual gathering)
- Analysis tasks benefit from compiled docs as context
- Context summarization cuts token usage by ~70% (research-backed)
- Avoids duplicating information we already have
- Reduces context dilution (improves quality when context is focused)
- Balances comprehensive research with cost control

**Planning Philosophy**
- What facts do we need? → Documentation tasks
- What depends on those facts? → Analysis with dependencies
- Do we already have docs? → Check with GPT-5, reuse if sufficient
- Is existing doc outdated? → Queue update with specific gaps
- Is this obvious or low-value? → Skip it

**Intelligent Doc Analysis** (Agentic Workflow)

The `deepr docs analyze` command is a fully agentic workflow:

```bash
deepr docs analyze "docs/my-project" "Building a chat app" --topics 6
```

What happens:
1. **Agent scans** the docs directory (any location you specify)
2. **GPT-5 analyzes** what exists vs what's needed for your scenario
3. **Agent generates** research plan to fill gaps
4. **You approve** (or use `--execute` to skip)
5. **Agent queues** research jobs
6. **Results saved** back to docs when complete

Works anywhere:
- `deepr docs analyze "./my-docs" "React best practices"`
- `deepr docs analyze "C:/project/docs" "AI safety guidelines"`
- `deepr docs analyze "../research" "Go concurrency patterns"`

Benefits:
- Dynamic (works with ANY docs location, ANY scenario)
- Intelligent (GPT-5 reasons about what's missing)
- Automated (queues research, saves results)
- Cost-effective (only researches actual gaps)

The goal: Maximum value research, zero waste.

## Documentation

- [docs/QUICKSTART.md](docs/QUICKSTART.md) - Setup guide
- [docs/DEEP_RESEARCH_EXPLAINED.md](docs/DEEP_RESEARCH_EXPLAINED.md) - Deep research vs GPT
- [docs/AGENTIC_PLANNING_EXAMPLE.md](docs/AGENTIC_PLANNING_EXAMPLE.md) - Concrete example
- [docs/CLI_GUIDE.md](docs/CLI_GUIDE.md) - Command reference
- [ROADMAP.md](ROADMAP.md) - Development plans

## Current Status

**v2.0 - Production Ready**

Working now:
- Core infrastructure: Queue, storage, OpenAI integration
- CLI: submit, wait, status, result, cancel, queue management
- Worker: Background polling with stuck job detection
- Web UI: ChatGPT-style interface (React + Vite + TailwindCSS)
  - Job queue with real-time updates
  - Cost analytics with budget tracking
  - Submit research jobs
  - Minimal monochrome design
- Cost tracking: Automatic from token usage
- API: Flask REST endpoints for web UI
- Validated with live jobs

**v2.1 - Active Development**

Building now:
- Agentic planner: Multi-phase research with dependencies
- Context chaining: Feed prior research to later phases
- Batch execution: Submit entire research campaign
- Results library: Browse and view completed research

## Philosophy

Research is the foundation of good decision-making. Comprehensive research requires:
- Understanding what you need to know
- Sequencing research intelligently
- Building context across findings
- Synthesizing insights

Deepr automates this entire process. State your goal once, get comprehensive interconnected analysis.

**Do your homework. Knowledge is power. Automate it.**

## Configuration

`.env` file supports multiple providers:
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
```

Provider selection:
- Auto: Deepr picks best provider per task (future)
- Manual: Specify provider via CLI `--provider openai|azure|anthropic`
- Default: OpenAI (most mature deep research offering)

## Local-First Architecture

Built for your workstation (Linux/Mac/Windows):
- SQLite queue (no external database)
- Filesystem storage (no cloud required)
- OpenAI API (only external dependency)

Cloud/container deployment supported but not primary focus.

## CLI Commands

```bash
# Single research job
deepr research submit "<prompt>" --yes
deepr research wait <job-id>
deepr research status <job-id>
deepr research result <job-id>
deepr research cancel <job-id>

# Agentic documentation analysis (NEW!)
deepr docs analyze "path/to/docs" "Your scenario" --topics 6
# Scans docs, identifies gaps, generates plan, queues research

# Multi-phase campaign (in development)
deepr prep plan "High-level goal" --topics 5
deepr prep review
deepr prep execute

# Queue management
deepr queue list
deepr queue stats

# Web interface (monitor jobs visually)
python -m deepr.api.app
# Then visit http://localhost:5000
```
