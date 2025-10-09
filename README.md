# Deepr

**Knowledge Is Power. Automate It.**

Automate deep research using OpenAI's Deep Research API. Queue jobs via CLI or web UI, get comprehensive reports with inline citations. Built for multi-phase research campaigns where each phase builds on previous findings.

**Philosophy:** Think like a human, use AI. Or in this case: think like a small research team, use Deepr.

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

**Multi-Phase Research Campaigns** (beta - adaptive research workflow)

Replicates how a human research team works: plan → execute → review → plan next phase.

**Recommended workflow (stable):**
```bash
# Round 1: Foundation research
deepr prep plan "What should Ford do in EVs for 2026?" --topics 3
deepr prep execute --yes
# Wait for completion (~15 min)...

# Round 2: GPT-5 reviews Phase 1 results, plans Phase 2
deepr prep continue --topics 2
# AI research lead reviews findings, identifies gaps
# Suggests next research questions based on what was learned
# User reviews and executes

# Round 3: Final synthesis
deepr prep continue --topics 1
```

**Fully autonomous workflow:**
```bash
deepr prep auto "What should Ford do in EVs for 2026?" --rounds 3
# Complete autonomous research:
# Plan Phase 1 → Execute → Review → Plan Phase 2 → Execute → Review → Plan Phase 3 → Execute
# Cost: ~$3-5, Time: 40-60 minutes
```

**Why context management is critical:**

Context is everything. Without proper context injection, research goes off-target. We proved this ourselves - when we asked Deepr to research "how to improve Deepr", it found unrelated crypto projects named "Deepr" instead of analyzing our platform.

The fix: Inject context explicitly.

**Bad (research goes wrong):**
```bash
deepr research submit "Research our competitive landscape" --yes
# Result: AI searches web blindly, finds wrong products
```

**Good (research stays on-target):**
```bash
deepr prep plan "Research competitive landscape for research automation. Context: We are Deepr - $(cat README.md | head -50)" --topics 4
# Result: AI knows WHO you are, researches correctly
```

**Multi-phase (best - adaptive with context):**
- Later phases informed by actual findings, not guesses
- GPT-5 acts as research lead, reviewing and planning next steps
- Each round builds on real data from previous rounds
- Context summarization cuts token usage 70% while preserving meaning
- Works with call transcripts, documents, specific scenarios

**Example with context injection:**
```bash
# Manual workflow (recommended)
deepr prep plan "Review call transcript with DemoCorp's CEO. Research their competitive position and provide strategic recommendations. Context: $(cat call.txt)" --topics 3
deepr prep execute --yes
# Wait for Phase 1 completion...
deepr prep continue --topics 2  # GPT-5 reviews and plans Phase 2
```

How it works:
- Round 1: Research DemoCorp + market (with call context)
- Round 2: GPT-5 reviews results, identifies gaps, researches specifics
- Round 3: Synthesize strategy grounded in research + call insights

This is agentic AI with research depth—not just reasoning, but researching between reasoning steps with proper context management.

## Architecture

```
Single Job:
User → SQLite Queue → Worker polls OpenAI → Result saved as markdown

Multi-Phase Campaign:
User → GPT-5 Planner → Research Plan (with dependencies)
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

## Context Management Best Practices

Context injection determines research quality. Follow these practices:

1. **Always identify yourself** - Include "We are X, we do Y..." in prompts
2. **Inject context explicitly** - Use `--context "$(cat file.txt)"` to provide docs/transcripts/data
3. **Start broad, narrow with reviews** - Phase 1 foundation, let GPT-5 review and plan Phase 2 specifics
4. **Trust summarization** - gpt-5-mini cuts 70% tokens while preserving key information
5. **Use prep continue** - GPT-5 acts as research lead, identifies gaps better than guessing upfront

Without context, research goes off-target. With proper context injection, you get accurate, focused analysis.

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

**v2.1 - Current Release**

Stable:
- Single deep research jobs: CLI + web UI for o3/o4-mini-deep-research
- Worker: Background polling with stuck job detection (auto-cancels queued >10min)
- Web UI: ChatGPT-style interface with real-time job queue, cost analytics, minimal monochrome design
- Cost tracking: Automatic from OpenAI token usage
- SQLite queue + filesystem storage

Beta (functional, adaptive research workflow):
- `deepr prep plan` - GPT-5 generates research plan
- `deepr prep execute` - Execute plan with context chaining
- `deepr prep continue` - GPT-5 reviews results, plans next phase
- `deepr prep auto` - Fully autonomous multi-round research (working)
- ResearchReviewer: GPT-5 acts as research lead, adapting strategy based on findings

**v2.2 - Next Up**

Future features:
- Doc analysis: `deepr docs analyze` scans existing research, identifies gaps
- Results library: Browse and view completed research
- Multi-provider routing: Auto-select best provider per task
- Advanced dependency graphs: Visualize research campaign flow

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

# Multi-phase research (adaptive workflow)
deepr prep plan "High-level goal" --topics 5      # Plan Phase 1
deepr prep execute --yes                          # Execute Phase 1
deepr prep continue --topics 3                    # GPT-5 reviews, plans Phase 2
deepr prep auto "High-level goal" --rounds 3      # Fully autonomous multi-round

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

Think like a human, use AI. Or in this case: **think like a small research team, use Deepr.**

Research is the foundation of good decision-making. Comprehensive research requires understanding what you need to know, sequencing research intelligently, building context across findings, and synthesizing insights.

**Deepr is a Level 4 Multi-Agent System** (though you don't need to know that to use it):

Deepr replicates how human research teams actually work:
- **Blue Hat (Orchestrator)**: ResearchPlanner + BatchExecutor manage the process
- **White Hat (Facts)**: Documentation tasks gather objective data
- **Green Hat (Creative)**: ResearchReviewer identifies new research angles
- **Yellow/Black Hats (Analysis)**: Tasks evaluate opportunities and risks
- **Synthesis**: GPT-5 weaves everything into coherent insights

This isn't just metaphor—it's architecture. Deepr implements proven multi-agent orchestration patterns from decades of MAS (Multi-Agent Systems) research. The key insight: **success comes from robust orchestration, not sophisticated prompts**.

The difference: Your "research team" is GPT-5 (planning and reviewing) + o3/o4-mini (executing deep research). Cost: $3-5 per campaign instead of $5,000+ consulting fees. Time: 40-60 minutes instead of weeks.

**Future (v2.3):** Explicit Six Thinking Hats mode, Red Team analysis, conflict resolution, agentic level control.

**Do your homework. Knowledge is power. Automate it.**

---

## Credits

Created by **Nick Seal**.

Deepr is an open-source research automation platform designed to make comprehensive research accessible and affordable. Built with the philosophy that AI should replicate human workflows, not replace human thinking.
