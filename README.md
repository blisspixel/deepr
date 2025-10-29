# Deepr

**Agentic learning and knowledge automation**

Deepr is the open-source, multi-provider platform for autonomous research and expertise acquisition. From preparing for tomorrow's meeting to becoming an expert on complex topics, Deepr autonomously researches, learns, and delivers understanding at any depth you need.

**For:** Researchers, analysts, product teams, developers, and AI agents who need deep understanding, not just keyword search.

**Why Deepr?**
- **MIT-licensed & locally deployable** - No vendor lock-in, run it on your infrastructure
- **Multi-provider architecture** - Works with OpenAI today, designed for any LLM provider tomorrow
- **Cited research reports** - Unlike chatbots, every claim includes source attributions for verification
- **Deep research, not search** - Multi-step reasoning with web search, not just keyword matching

## Quick Start

**Prerequisites:** Python 3.9+, Node.js 16+ (for web UI)

**1. Install:**
```bash
pip install -r requirements.txt
pip install -e .
```

**2. Configure:**
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

**3. Run Services:**
```bash
python bin/start-worker.py &              # Worker fetches completed jobs from OpenAI
python -m deepr.api.app &                 # API backend (http://localhost:5000)
cd deepr/web/frontend && npm run dev      # Frontend (http://localhost:3000)
```

**4. Submit Research:**
```bash
deepr research submit "Analyze AI code editor market" --yes
deepr research wait <job-id>
```

**Note on costs:** Deep research jobs use OpenAI's API and incur costs ($1-15 per job depending on depth). Deepr tracks usage per job - check the Web UI analytics or use `deepr queue stats` to monitor spending. Set budget limits in your config to avoid surprises.

Full setup guide: [docs/QUICKSTART.md](docs/QUICKSTART.md)

## What It Does

Deepr automates research at any depth - from quick focused queries to comprehensive expertise acquisition:

**Quick, focused research (no context needed):**

These examples demonstrate curiosity-driven research where no business context is required:

```bash
# Genuinely curious questions that work standalone
deepr research "Explain quantum entanglement from the perspective of someone who is blind from birth" --yes
# Estimated: 5-10 min, ~$1-2 | Result: Novel perspective on abstract physics

deepr research "What are the ethical arguments for and against gene editing in humans? Include perspectives from bioethicists, disability rights advocates, and religious scholars." --yes
# Estimated: 10-15 min, ~$2-3 | Result: Multi-perspective analysis

deepr research "Analyze the economics of vertical farming. Is it viable at scale?" --yes
# Estimated: 10-15 min, ~$2-3 | Result: Cost-benefit analysis with citations
```

**Research with explicit context injection:**

For business-specific queries, provide explicit context to make research actionable:

```bash
# Meeting prep WITH context (shows how to actually do it right)
deepr research "Research fintech payment processing landscape. Context: I'm meeting with Stripe's enterprise team tomorrow. Our company is $(cat company-brief.txt). Focus on what Stripe offers vs competitors, pricing models, integration complexity, and questions I should ask. Output: Brief with key talking points and smart questions." --yes
# Estimated: 10-15 min, ~$2-3 | Result: Contextualized prep

# Document analysis with file upload (NEW in v2.2)
deepr research "Analyze this product spec and identify technical risks" -f product-spec.pdf -f requirements.md --yes
# Estimated: 5-10 min, ~$1-2 | Result: Gap analysis with semantic search over uploaded docs

# Multiple documents for comprehensive analysis
deepr research "Analyze our competitive positioning" -f company-overview.pdf -f market-research.pdf -f competitor-analysis.xlsx --yes
# Uploads to vector store, enables semantic search across all documents
```

**Comprehensive autonomous expertise:**
```bash
# Multi-round research until mastery
deepr prep auto "Become expert on quantum computing commercialization. Research: technical readiness, market landscape, commercialization barriers, investment trends, and 5-year outlook. Validate understanding through simulated expert review." --rounds 5
# Estimated: 40-60 min, ~$5-10 | Result: PhD-level understanding with adversarial validation
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
# Vague, no context - AI has to guess
deepr research "Research our competitive landscape" --yes
# Result: Searches for random "competitive landscape" - useless

# Assumes AI knows your company
deepr research "Prepare for board meeting about Q4 strategy" --yes
# Result: Generic advice, no relevance to your actual situation
```

**Good (explicit context):**
```bash
# Identify yourself and inject context
deepr research "Research competitive landscape for research automation platforms. Context: We are Deepr, an open-source multi-provider deep research platform. Our tech stack: $(cat tech-summary.txt). Our differentiators: multi-phase adaptive research, MCP integration, provider-agnostic. Competitors: Perplexity, Elicit, Consensus. Focus on: feature comparison, pricing models, and our unique positioning. Output: Competitive matrix with strategic recommendations." --yes
# Result: Targeted analysis of YOUR actual competitive landscape

# Context from multiple files
deepr research "Analyze this customer call and provide strategic recommendations. Context: Call transcript: $(cat call-transcript.txt). Our product capabilities: $(cat product-brief.txt). Customer's industry: $(cat fintech-overview.txt). Output: Key insights, customer needs, recommended next steps, and questions to ask in follow-up." --yes
# Result: Contextualized analysis actually useful for your situation
```

**Pattern: Structured context injection**
```bash
# Use the format from our best practices research
deepr research "Research Task: [Your goal]. Context: [Who you are, what you're doing]. Scope: [Boundaries - timeframe, geography, specific focus]. Include: [What sections/analysis you need]. Output: [Desired format and structure]." --yes
```

**Best practices:**
1. **Never assume AI knows your context** - Always inject it explicitly
2. **Use file injection** - `$(cat file.txt)` for documents, specs, transcripts
3. **Be specific about scope** - Timeframes, geography, industry, depth
4. **Define output format** - "Executive summary + 3 sections + recommendations"
5. **Identify yourself** - "We are X, we do Y, we're researching Z"
6. **Multi-file context** - Chain multiple `$(cat)` for comprehensive context

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

## Investment & Quality

Deep research takes time and resources because it's **comprehensive, not superficial**. The investment reflects the depth and quality you get.

| Research Depth | Investment | Time | What You Get |
|----------------|------------|------|--------------|
| Quick insights | $1-2 | 5-10 min | Focused analysis with citations |
| Thorough reports | $1-$5 | 15-30 min | Comprehensive synthesis from diverse sources |
| Multi-phase campaigns | $5-$15 | 40-90 min | Adaptive research that builds cumulative understanding |
| PhD-level expertise | $10-$20 | 60-120 min | World-class analysis with adversarial validation |

**Quality philosophy:**
- **o3-deep-research**: Use for breakthrough-quality research when you need the absolute best
- **o4-mini-deep-research**: Use for rapid exploration and iteration
- **Multi-phase**: Each round builds deeper understanding than starting from scratch
- **Context chaining**: Enables cumulative intelligence - later phases leverage earlier insights

**Accessible knowledge:** PhD-level research for $15 makes deep expertise available to individuals, startups, researchers, and AI agents - accelerating knowledge impact across the board.

## Best Practices for Research Prompts

**Include temporal context for current information:**

Research models need to know "today's date" to search for and prioritize recent information:

```bash
# Good: Includes date context for latest information
deepr research "As of October 2025, what are the latest developments in quantum computing commercialization? Focus on breakthroughs from 2024-2025, current technical readiness levels, and near-term market opportunities." --yes

# Bad: Ambiguous temporal context
deepr research "What are the latest developments in quantum computing?" --yes
# Problem: "Latest" is ambiguous - latest when? Model may return older information
```

**Be specific about scope and depth:**

```bash
# Good: Clear scope and deliverables
deepr research "Research the competitive landscape for AI code review tools as of October 2025. Include: (1) Top 5 players by market share, (2) Feature comparison matrix, (3) Pricing models, (4) Recent funding/M&A activity. Focus on enterprise segment." --yes

# Bad: Vague scope
deepr research "Research AI code review tools" --yes
# Problem: Too broad - unclear what aspects matter or what depth is needed
```

**Provide explicit context when it matters:**

```bash
# Good: Context makes the research actionable
deepr research "Research customer onboarding best practices for B2B SaaS. Context: We sell API infrastructure to developers, typical ACV $50K, 90-day sales cycle. Focus on: time-to-first-value optimization, technical documentation strategies, and reducing support burden during first 30 days." --yes

# Bad: Generic research without context
deepr research "Research customer onboarding best practices" --yes
# Problem: Generic advice won't be tailored to your specific situation
```

**Automatic prompt refinement (NEW in v2.2):**

Use `--refine-prompt` to automatically optimize your query following best practices:

```bash
# Before: Vague query
deepr research "compare AI code editors" --refine-prompt --yes

# After refinement (automatic):
# "As of October 2025, perform a comparative research analysis of AI-assisted
# code editors. Include: (1) Feature comparison, (2) Performance benchmarks,
# (3) Pricing models, (4) Integration capabilities, (5) Security/compliance.
# Focus on: GitHub Copilot, Cursor, Windsurf, Codeium, Tabnine..."

# What it does:
# - Adds current date context ("As of October 2025")
# - Suggests structured deliverables
# - Flags missing business context needs
# - Improves clarity and specificity
```

The refinement happens instantly (GPT-5-mini call, ~$0.001) before submitting to deep research. You see exactly what changed and can cancel if needed.

## Use Cases

**Curiosity-driven research (no context needed):**
- Novel perspectives on complex topics ("Explain X from Y's perspective")
- Ethical debates with multiple viewpoints
- Technical concepts explained for different audiences
- Feasibility analysis of emerging technologies
- Historical or scientific deep dives

**Contextualized business research (requires explicit context):**
- Meeting prep with customer/company context injected
- Competitive analysis for YOUR specific product/market
- Document analysis (specs, transcripts, reports)
- Strategic planning with company context and constraints
- Customer research grounded in your actual product/service

**Autonomous expertise acquisition:**
- Multi-round research until PhD-level understanding
- Self-directed gap identification and filling
- Validation through simulated expert review
- Building comprehensive domain expertise from scratch

**For AI agents (via MCP):**
- On-demand research capability for autonomous systems
- Grounding LLM reasoning in fresh, cited data
- Multi-step knowledge gathering for complex agent tasks
- Research infrastructure for digital consciousness systems

**Not suitable for:**
- Quick facts (use regular GPT instead - seconds, $0.01)
- Conversational chat or real-time applications
- Isolated queries that don't benefit from depth
- Situations requiring sub-minute response times

## Current Status (v2.2)

**Production-ready:**
- Single deep research jobs via CLI and web UI
- File upload with vector store support (PDF, DOCX, TXT, MD, code files)
- Automatic prompt refinement (adds date context, structure, clarity)
- Ad-hoc result retrieval (get results without running worker 24/7)
- Detailed cost breakdowns (token usage, pricing, per-job attribution)
- Human-in-the-loop controls (review plans before execution)
- Provider resilience (auto-retry with exponential backoff, graceful degradation)
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
| **Level 3** | Adaptive Planning (feedback-driven) | **Current (v2.2)** |
| **Level 4** | Reflective Optimization (learns from outcomes) | Target (v2.5) |
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

**Implementation approach:** Building on proven AI research patterns - ReAct for execution, Reflexion for learning from mistakes, Tree-of-Thoughts for strategic planning. These patterns have demonstrated 10-20x improvement in complex reasoning tasks.

**Our philosophy:** Quality over automation. We bias heavily toward fresh research and human judgment now to build trust for autonomy later. Autonomous systems must earn agency through demonstrated wisdom, not hype.

See [ROADMAP.md](ROADMAP.md) for detailed development plans.

## Multi-Provider Support

**Current reality (October 2025):**

Multiple providers now offer deep research capabilities with different strengths:

| Provider | Latest Models | Deep Research API | Pricing (per 1M tokens) |
|----------|--------------|-------------------|------------------------|
| **OpenAI** | GPT-5, GPT-5-mini, GPT-5-nano | Yes (turnkey) | GPT-5: $1.25 in / $10 out<br>Mini: $0.25 in / $2 out |
| **Anthropic** | Claude Opus 4.1, Sonnet 4.5, Haiku 4.5 | Yes (Web Search tools) | Opus: $15 in / $75 out<br>Sonnet: $3 in / $15 out<br>Haiku: $1 in / $5 out |
| **Google** | Gemini 2.5 Pro/Flash/Flash-Lite | Yes (Enterprise+) | Pro: $0.625-$1.25 in / $5-$7.50 out<br>Flash: $0.30 in / $2.50 out<br>Flash-Lite: $0.10 in / $0.40 out |
| **xAI** | Grok 4, Grok 4 Fast | Yes (agentic tools) | Grok 4: $3 in / $15 out<br>Fast: $0.20 in / $0.50 out |
| **Azure OpenAI** | GPT-5 family via Azure | Yes (enterprise) | Matches OpenAI pricing + enterprise features |

**Deepr's approach:**
- Currently using OpenAI's Deep Research API (o3-deep-research, o4-mini-deep-research)
- Architecture designed for multi-provider orchestration
- Provider selection: `--provider openai|azure|anthropic|google|xai`
- Planned: Automatic routing to optimal provider per task type

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
deepr research submit "<prompt>" -f file1.pdf -f file2.md --yes       # With file uploads
deepr research submit "<prompt>" --refine-prompt --yes                # Auto-optimize prompt
deepr research get <job-id>        # Get results - downloads from provider if ready (NEW in v2.2)
deepr research wait <job-id>       # Wait for completion and display when ready
deepr research status <job-id>     # Check status (local database only)
deepr research result <job-id>     # Display previously downloaded result
deepr research result <job-id> --cost  # Detailed cost breakdown (NEW in v2.2)
deepr research cancel <job-id>     # Cancel running job

# Multi-phase research (adaptive workflow)
deepr prep plan "High-level goal" --topics 5                    # Plan Phase 1
deepr prep plan "Goal" --topics 5 --review-before-execute       # Human-in-the-loop (NEW in v2.2)
deepr prep execute --yes                                        # Execute Phase 1
deepr prep continue --topics 3                                  # GPT-5 reviews, plans Phase 2
deepr prep auto "High-level goal" --rounds 3                    # Fully autonomous multi-round

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

MIT License - see [LICENSE](LICENSE) file for details.

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

**Current status:** v2.2 is production-ready for single jobs with file upload, prompt refinement, and ad-hoc retrieval. Multi-phase research is beta. MCP integration and autonomous learning features planned for v2.3-v2.4.

## Credits

Created by **Nick Seal**.

**Philosophy:** Automate research execution and strategy, but never sacrifice quality for automation. Context is everything. We bias toward fresh research and human judgment to build systems worthy of trust.

Knowledge is power. We're automating the learning.
