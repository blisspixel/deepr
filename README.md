# Deepr

**Agentic learning and knowledge automation**

Deepr is the open-source, multi-provider platform for autonomous research and expertise acquisition. From preparing for tomorrow's meeting to becoming expert on complex topics, Deepr autonomously researches, learns, and delivers understanding at any depth you need.

For humans and AI agents who need to understand, not just search.

## Quick Start

```bash
# Install
pip install -r requirements.txt
pip install -e .
cp .env.example .env  # Add your OPENAI_API_KEY

# Start services
python bin/start-worker.py &              # Polls OpenAI for job completion
python -m deepr.api.app &                 # API server for web UI
cd deepr/web/frontend && npm run dev      # Web UI at http://localhost:3000

# Submit research via CLI
deepr research submit "Analyze AI code editor market" --yes
deepr research wait <job-id>
```

Full setup guide: [docs/QUICKSTART.md](docs/QUICKSTART.md)

## What It Does

Deepr automates research at any depth - from quick meeting prep to comprehensive expertise acquisition:

**Simple, everyday use:**
```bash
# Prepare for tomorrow's meeting
deepr research "Help me prepare for tomorrow's board meeting about Q4 strategy" --yes
# Time: 5-10 minutes, Cost: $1-2, Result: Talking points and anticipated concerns

# Research before customer call
deepr research "Meeting a fintech customer tomorrow. What should I know?" --yes
# Time: 5-10 minutes, Cost: $1-2, Result: Industry context and relevant questions
```

**Comprehensive expertise:**
```bash
# Autonomous multi-round research
deepr prep auto "Become expert on quantum computing commercialization" --rounds 5
# Time: 40-60 minutes, Cost: $5-10, Result: PhD-level understanding validated through adversarial testing
```

### Single Deep Research Jobs (Production Ready)

Submit research queries and get comprehensive reports with inline citations:

```bash
deepr research submit "Competitive analysis of AI code review tools" --yes
deepr research wait <job-id>
```

**Characteristics:**
- Time: 2-60+ minutes (autonomous research with web search)
- Cost: $0.50-$5+ per report (varies by depth and model)
- Output: Comprehensive markdown reports with inline citations
- Queue-based: Worker polls OpenAI, downloads results when complete

### Multi-Phase Research Campaigns (Beta)

Adaptive research workflow that mirrors how human research teams work: plan, execute, review, plan next phase.

**Manual workflow (recommended for important research):**
```bash
# Round 1: Foundation research
deepr prep plan "What should Ford do in EVs for 2026?" --topics 3
deepr prep execute --yes
# Wait for completion

# Round 2: GPT-5 reviews Phase 1, identifies gaps, plans Phase 2
deepr prep continue --topics 2

# Round 3: Final synthesis
deepr prep continue --topics 1
```

**Autonomous workflow (experimental):**
```bash
deepr prep auto "What should Ford do in EVs for 2026?" --rounds 3
# Fully autonomous: Plan, Execute, Review, Plan, Execute, Review, Synthesize
# Cost: $3-5, Time: 40-60 minutes
```

**How it works:**
- Agent identifies knowledge gaps after each round
- Autonomously decides what to research next
- Continues until comprehensive understanding achieved
- Can run mock conversations to surface blind spots
- Validates understanding through simulated expert review

### Dynamic Research Teams (Experimental)

GPT-5 assembles optimal research teams dynamically for each question, with different perspectives researching independently before synthesis:

```bash
# Balanced analysis with diverse perspectives
deepr team analyze "Should we pivot to enterprise?" --team-size 5

# Devil's advocate mode (emphasizes skeptical perspectives)
deepr team analyze "Our Q2 launch plan" --adversarial

# Grounded in actual company leadership
deepr team analyze "What's Anthropic's AI strategy?" --company "Anthropic"

# Cultural or demographic perspective
deepr team analyze "Market entry strategy" --perspective "Japanese business culture"
```

The system analyzes your question, designs an optimal team with diverse perspectives, executes research from each viewpoint, and synthesizes findings showing where perspectives agree, conflict, and converge.

## Why Context Management Matters

We learned this the hard way: When we asked Deepr to research "how to improve Deepr" without providing context, it found unrelated crypto projects named "Deepr" instead of analyzing our platform.

**The lesson:** Context injection is critical. Without it, research goes off-target.

**Bad (research goes wrong):**
```bash
deepr research submit "Research our competitive landscape" --yes
# Result: AI searches web blindly, finds wrong products
```

**Good (research stays on-target):**
```bash
deepr prep plan "Research competitive landscape for research automation. Context: We are Deepr, an open-source platform that $(cat README.md | head -50)" --topics 4
# Result: AI knows who you are, researches correctly
```

**Best practices:**
1. Always identify yourself in prompts ("We are X, we do Y...")
2. Inject relevant context explicitly using `$(cat file.txt)`
3. Start broad in Phase 1, let GPT-5 review and narrow in Phase 2
4. Use `deepr prep continue` - GPT-5 acts as research lead, identifying gaps
5. Trust summarization - cuts 70% tokens while preserving meaning

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

Autonomous Learning (Level 5 vision):
User → Agent → Self-directed research loop
                ↓
            Identify gaps
                ↓
            Research autonomously
                ↓
            Validate understanding
                ↓
            Continue until expertise achieved
```

**Design principles:**
- Queue-based (deep research takes 2-60+ minutes, too long for synchronous)
- Local-first (SQLite queue, filesystem storage, no external database required)
- Provider-agnostic (OpenAI primary, architecture ready for multi-provider)

## Cost & Time

| Type | Cost | Time |
|------|------|------|
| Meeting prep / quick brief | $1-2 | 5-10 minutes |
| Simple queries | $0.05-$0.20 | 2-5 minutes |
| Medium reports | $0.20-$0.80 | 5-15 minutes |
| Comprehensive | $1-$3 | 15-30 minutes |
| Multi-phase campaigns | $3-$10 | 40-90 minutes |
| Deep expertise acquisition | $5-$15 | 60-120 minutes |

**Notes:**
- o3-deep-research costs approximately 10x more than o4-mini but provides more thorough analysis
- Multi-phase campaigns multiply by number of tasks
- Context chaining reduces redundancy between phases

## Use Cases

**Practical, everyday:**
- Meeting preparation and briefings
- Customer research before calls
- Industry context for conversations
- Quick competitor analysis
- Market trend updates

**Strategic, comprehensive:**
- Market analysis requiring multiple angles and perspectives
- Technical due diligence with dependencies between research topics
- Strategic planning needing comprehensive context
- Research where initial findings inform subsequent questions
- Autonomous expertise acquisition on complex topics

**For AI agents:**
- On-demand research capability via MCP
- Grounding LLM reasoning in fresh, cited data
- Multi-step knowledge gathering for complex tasks
- Autonomous learning in agentic workflows

**Not suitable for:**
- Quick facts (use regular GPT instead - seconds, $0.01)
- Conversational chat or real-time applications
- Isolated queries that don't benefit from depth
- Situations requiring sub-minute response times

## Current Status (v2.1)

**Production-ready:**
- Single deep research jobs via CLI and web UI
- Background worker with stuck job detection
- Cost tracking from OpenAI token usage
- Web UI with real-time job queue and cost analytics
- SQLite queue and filesystem storage

**Beta (functional, use with supervision):**
- Multi-phase campaigns (`deepr prep plan/execute/continue/auto`)
- GPT-5 as research lead, reviewing results and planning next phases
- Context chaining with automatic summarization
- Adaptive research workflow

**Experimental (functional, may change significantly):**
- Dynamic research teams (`deepr team analyze`)
- Team assembly optimized per question
- Multiple perspectives with conflict highlighting

## Vision: Agentic Learning at Scale

Deepr is evolving from adaptive planning toward autonomous expertise acquisition. We think of this progression in terms of "Agentic Levels":

| Level | Description | Deepr Status |
|-------|-------------|--------------|
| **Level 1** | Reactive Execution (single-turn) | Complete |
| **Level 2** | Procedural Automation (scripted) | Complete |
| **Level 3** | Adaptive Planning (feedback-driven) | **Current (v2.1)** |
| **Level 4** | Reflective Optimization (learns from outcomes) | Target (v2.4) |
| **Level 5** | Autonomous Expertise Acquisition | Vision (v3.0+) |

**Where we are (Level 3):**
- System plans, monitors, and adjusts research based on findings
- GPT-5 reviews results and plans next phases
- Requires human oversight and approval

**Where we're headed (Level 4-5):**
- Agent identifies its own knowledge gaps ("I don't understand X, need to research X")
- Plans next research autonomously based on findings
- Runs mock conversations and debates to surface blind spots
- Continues research until comprehensive understanding achieved
- Validates expertise through simulated PhD defense or expert panel review
- Presents findings with beginner's mind humility: "Here's what I understand, but I may have blind spots"

**What Level 5 means:**
- **Perceive:** Agent detects gaps in own understanding
- **Plan:** Autonomously decides what to research next
- **Execute:** Runs research without human direction
- **Evaluate:** "Do I understand this comprehensively? What's missing?"
- **Improve:** Researches gaps until expertise validated

This isn't consciousness - it's autonomous expertise acquisition. The agent becomes knowledgeable on any topic through self-directed learning.

**Our philosophy:** Quality over automation. We bias heavily toward fresh research and human judgment now to build trust for autonomy later. Autonomous systems must earn agency through demonstrated wisdom, not hype.

See [ROADMAP.md](ROADMAP.md) for detailed development plans.

## Multi-Provider Support

**Current reality (October 2025):**
- **OpenAI** is the only provider with a turnkey Deep Research API
- o3-deep-research and o4-mini-deep-research for comprehensive reports
- GPT-5 for planning and review in multi-phase campaigns

**Architecture ready for:**
- **Azure OpenAI** - Same models via Azure AI Foundry (enterprise deployment)
- **Anthropic** - Claude Extended Thinking implemented for reasoning transparency
- **Future providers** - When others launch Deep Research APIs, we'll integrate

**Provider selection:**
- Default: OpenAI (most mature Deep Research offering)
- Manual: `--provider openai|azure|anthropic` flag
- Future: Automatic routing to optimal provider per task type

## Configuration

`.env` file:

```bash
# OpenAI (primary)
OPENAI_API_KEY=sk-...

# Azure OpenAI (optional, for enterprise deployment)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...

# Anthropic (optional, for Extended Thinking in planning tasks)
ANTHROPIC_API_KEY=...

# Cost limits (optional safeguards)
DEEPR_MAX_COST_PER_JOB=10.0
DEEPR_MAX_COST_PER_DAY=100.0
DEEPR_MAX_COST_PER_MONTH=1000.0
```

## CLI Commands

```bash
# Single research job
deepr research submit "<prompt>" --yes
deepr research wait <job-id>       # Wait for completion (passive - checks local status)
deepr research status <job-id>     # Check status (local database only)
deepr research result <job-id>     # Display result (if downloaded)
deepr research cancel <job-id>     # Cancel job

# Multi-phase research (adaptive workflow)
deepr prep plan "High-level goal" --topics 5      # Plan Phase 1
deepr prep execute --yes                          # Execute Phase 1
deepr prep continue --topics 3                    # GPT-5 reviews, plans Phase 2
deepr prep auto "High-level goal" --rounds 3      # Fully autonomous multi-round

# Dynamic research teams (experimental)
deepr team analyze "Should we pivot to enterprise?" --team-size 5
deepr team analyze "Our Q2 launch plan" --adversarial
deepr team analyze "What's Anthropic's strategy?" --company "Anthropic"
deepr team analyze "Market entry strategy" --perspective "Japanese business culture"

# Queue management
deepr queue list                   # List all jobs
deepr queue stats                  # Show queue statistics

# Background worker (required for automatic job completion)
python bin/start-worker.py         # Polls OpenAI every 30s, downloads results
```

**Note on job completion:** Jobs require the worker running to fetch results from OpenAI. The worker polls every 30 seconds and automatically downloads completed reports.

**Planned UX improvement:** We're adding `deepr research poll <job-id>` to manually check OpenAI and download results without running a continuous worker. This will enable ad-hoc usage patterns like daily check-ins or CI/CD scenarios. See [ROADMAP.md](ROADMAP.md) for details.

Web UI alternative:
```bash
python -m deepr.api.app            # Start API server at http://localhost:5000
```

## What Is Deep Research?

Deep Research is autonomous multi-step research using advanced reasoning models:

1. **Planning**: Model breaks down query into research steps
2. **Execution**: Autonomously searches web, reads sources, gathers information
3. **Synthesis**: Analyzes findings, identifies patterns, generates insights
4. **Output**: Comprehensive report with inline citations

**Comparison with standard LLM queries:**
- Standard GPT: Single prompt, single response (seconds, $0.01)
- Deep Research: Agentic loop, comprehensive analysis (minutes-hours, $0.50-$5+)

The trade-off: 50-100x slower and more expensive, but produces comprehensive research reports that would take hours to compile manually.

See [docs/DEEP_RESEARCH_EXPLAINED.md](docs/DEEP_RESEARCH_EXPLAINED.md) for detailed comparison.

## Interfaces & Integration

Deepr is designed to be used however you work:

**CLI First (Primary Interface):**
```bash
deepr research submit "Your research query" --yes
deepr prep auto "Complex multi-phase research" --rounds 3
```
Command-line interface for developers, scripts, and automation workflows.

**Local Web UI:**
```bash
python -m deepr.api.app  # ChatGPT-style interface at localhost:5000
```
Visual interface for interactive use. Runs locally on Windows, Mac, or Linux - no external dependencies.

**MCP Server (Planned v2.3):**
```bash
deepr mcp serve  # Exposes Deepr as Model Context Protocol server
```
Enable AI agents and tools to use Deepr as a research capability:
- Claude Desktop, Cursor, Windsurf, and other MCP-aware tools can call Deepr
- Agents autonomously submit research requests and retrieve comprehensive reports
- Deepr becomes part of the AI agent's toolbox, just like any other capability

MCP also enables Deepr to connect to other data sources (Slack, Notion, internal docs) for context-aware research. See the [MCP Research Report](data/reports/6cd24fda-3edd-4ebe-9179-f9b2fba940eb/report.md) for architectural details.

**Architecture Philosophy:**
- **CLI first** - Primary interface for power users and automation
- **Multi-interface** - Available where you need it (terminal, browser, AI agents)
- **Provider-agnostic** - OpenAI today, ready for others as they add deep research capabilities
- **Open standard** - MCP integration enables ecosystem compatibility

## Documentation

- [docs/QUICKSTART.md](docs/QUICKSTART.md) - Detailed setup guide
- [docs/CLI_GUIDE.md](docs/CLI_GUIDE.md) - Complete command reference
- [docs/DEEP_RESEARCH_EXPLAINED.md](docs/DEEP_RESEARCH_EXPLAINED.md) - Deep research vs standard LLMs
- [docs/AGENTIC_PLANNING_EXAMPLE.md](docs/AGENTIC_PLANNING_EXAMPLE.md) - Multi-phase research walkthrough
- [ROADMAP.md](ROADMAP.md) - Development roadmap and future vision

## Contributing

We welcome contributions, especially in these high-impact areas:

- Context chaining logic and prompt engineering
- Synthesis strategies (integrating findings from multiple sources)
- Cost optimization techniques
- Template patterns for common research workflows
- MCP server implementation
- Documentation and examples

The most impactful work is on the intelligence layer (planning, context management, synthesis) rather than infrastructure.

## License

Open source (license details in repository).

---

## Mission

Deepr aims to be **the** open-source platform for agentic learning and knowledge automation. We're building research infrastructure that enables humans and AI systems to acquire expertise at any depth - from quick meeting briefs to comprehensive domain mastery.

**What we're building:**
- **Multi-provider support** - OpenAI today, any provider with deep research capabilities tomorrow
- **Multiple interfaces** - CLI for developers, web UI for teams, MCP for AI agents
- **Autonomous learning** - Self-directed research that identifies gaps and continues until expertise achieved
- **Universal infrastructure** - Works for humans and AI agents (including digital consciousness systems) alike
- **Open ecosystem** - Standard protocols (MCP), provider-agnostic architecture, community-driven

**Where we are:**
- Level 3 adaptive planning (production)
- Humble about current capabilities
- Realistic about challenges ahead

**Where we're going:**
- Level 5 autonomous expertise acquisition
- Agent validates own understanding through simulated expert review
- Presents findings with beginner's mind: confident but humble
- Admits gaps, researches more when needed

We're ambitious about the potential: autonomous research systems that earn trust through demonstrated wisdom, not hype. Quality and transparency before automation and scale.

**Current status:** Production-ready for single and multi-phase research. Beta for dynamic research teams. MCP integration and autonomous learning features planned for v2.3+.

## Credits

Created by **Nick Seal**.

**Philosophy:** Automate research execution and strategy, but never sacrifice quality for automation. Context is everything. We bias toward fresh research and human judgment to build systems worthy of trust.

Knowledge is power. We're automating the learning.
