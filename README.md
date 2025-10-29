# Deepr

**Autonomous research and expertise acquisition**

Deepr is an open-source, multi-provider platform for deep research automation. From quick market analysis to comprehensive domain expertise, Deepr autonomously researches, learns, and delivers cited reports at any depth you need.

---

## Quick Start

### Installation

```bash
# Install Deepr
pip install .

# Configure
cp .env.example .env
# Add your OPENAI_API_KEY to .env

# Verify
deepr --version
```

See [docs/INSTALL.md](docs/INSTALL.md) for platform-specific instructions.

### Your First Research Job

```bash
# Submit research
deepr research submit "Analyze AI code editor market as of October 2025" --yes

# Wait for results
deepr research wait <job-id>
```

**Cost:** $1-5 per report | **Time:** 5-30 minutes | **Output:** Comprehensive markdown with citations

---

## What It Does

Deepr uses OpenAI's deep research models to conduct autonomous, multi-step research with web search and produces comprehensive reports with inline citations.

### Three Research Modes

**1. Single Research Jobs** - Submit one-off research queries
```bash
deepr research submit "What are the latest trends in quantum computing?" --yes
```

**2. Multi-Phase Campaigns** - Adaptive research that builds understanding over multiple rounds
```bash
# Manual control
deepr prep plan "What should Ford do in EVs for 2026?" --topics 3
deepr prep execute --yes
deepr prep continue --topics 2  # GPT-5 reviews and plans next phase

# Fully autonomous
deepr prep auto "What should Ford do in EVs for 2026?" --rounds 3
```

**3. Dynamic Research Teams** (Experimental) - Multiple perspectives research independently
```bash
deepr team analyze "Should we pivot to enterprise?" --team-size 5
```

---

## Key Features

### File Upload & Document Analysis
Upload documents for semantic search during research:
```bash
deepr research "Analyze this product spec and identify risks" \
  -f product-spec.pdf -f requirements.md --yes
```

### Automatic Prompt Refinement
Optimize queries with GPT-5-mini before submission:
```bash
deepr research "compare AI code editors" --refine-prompt --yes

# Or enable always-on refinement
echo "DEEPR_AUTO_REFINE=true" >> .env
```

### Vector Store Management
Create reusable document indexes:
```bash
deepr vector create --name "company-docs" --files docs/*.pdf
deepr research submit "Analyze competitive landscape" --vector-store company-docs --yes
```

### Cost Tracking & Analytics
```bash
deepr cost summary              # Total spending
deepr analytics report          # Success rates, trends
deepr research result <id> --cost  # Per-job breakdown
```

### Human-in-the-Loop Controls
```bash
deepr prep plan "..." --review-before-execute  # Require approval
deepr prep pause                                # Pause campaign
deepr prep resume                               # Resume campaign
```

---

## Context Management

**Critical lesson:** Without explicit context, research goes off-target.

### Bad (vague, no context)
```bash
deepr research "Research our competitive landscape" --yes
# Result: Generic analysis, not useful
```

### Good (explicit context)
```bash
deepr research "Research competitive landscape for research automation platforms.
Context: We are Deepr, an open-source multi-provider deep research platform.
Tech stack: Python, OpenAI Deep Research API, SQLite queue.
Differentiators: multi-phase adaptive research, MCP integration, provider-agnostic.
Competitors: Perplexity, Elicit, Consensus.
Focus on: feature comparison, pricing models, and our unique positioning.
Output: Competitive matrix with strategic recommendations." --yes
# Result: Targeted analysis of YOUR actual competitive landscape
```

### Context Injection Patterns

**File injection:**
```bash
deepr research "Context: $(cat company-brief.txt). Task: ..." --yes
```

**Multi-file context:**
```bash
deepr research "
Context: Call transcript: $(cat call.txt).
Our product: $(cat product-brief.txt).
Customer industry: $(cat fintech-overview.txt).
Task: Analyze call and provide recommendations." --yes
```

**Structured format:**
```bash
deepr research "
Research Task: [Your goal]
Context: [Who you are, what you're doing]
Scope: [Timeframe, geography, specific focus]
Include: [What sections/analysis you need]
Output: [Desired format and structure]" --yes
```

### Best Practices for Research Prompts

**Include temporal context:**
```bash
# Good: Includes date context for latest information
deepr research "As of October 2025, what are the latest developments in quantum computing commercialization? Focus on breakthroughs from 2024-2025, current technical readiness levels, and near-term market opportunities." --yes

# Bad: Ambiguous temporal context
deepr research "What are the latest developments in quantum computing?" --yes
# Problem: "Latest" is ambiguous - model may return older information
```

**Be specific about scope and depth:**
```bash
# Good: Clear scope and deliverables
deepr research "Research the competitive landscape for AI code review tools as of October 2025. Include: (1) Top 5 players by market share, (2) Feature comparison matrix, (3) Pricing models, (4) Recent funding/M&A activity. Focus on enterprise segment." --yes

# Bad: Vague scope
deepr research "Research AI code review tools" --yes
# Problem: Too broad - unclear what aspects matter or what depth is needed
```

**Use automatic prompt refinement:**

The `--refine-prompt` flag uses GPT-5-mini to optimize your query following best practices:

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

**Always-on refinement:**
```bash
echo "DEEPR_AUTO_REFINE=true" >> .env
```

---

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

**Design Principles:**
- **Queue-based** - Deep research takes 2-60+ minutes, too long for synchronous
- **Local-first** - SQLite queue, filesystem storage, no external database required
- **Provider-agnostic** - OpenAI primary, architecture ready for multi-provider

---

## CLI Commands

### Research Operations
```bash
# Submit
deepr research submit "<prompt>" --yes
deepr research submit "<prompt>" -f file.pdf --yes
deepr research submit "<prompt>" --refine-prompt --yes
deepr research submit "<prompt>" --vector-store <name|id> --yes

# Retrieve
deepr research get <job-id>           # Download from provider
deepr research get --all              # Download all completed jobs
deepr research wait <job-id>          # Wait for completion
deepr research result <job-id>        # Display saved result
deepr research result <job-id> --cost # Show cost breakdown

# Manage
deepr research status <job-id>
deepr research cancel <job-id>
```

### Vector Stores (needs testing)
```bash
deepr vector create --name "docs" --files *.pdf
deepr vector list
deepr vector info <id>
deepr vector delete <id>
```

### Multi-Phase Campaigns
```bash
deepr prep plan "<goal>" --topics 5
deepr prep execute --yes
deepr prep continue --topics 3
deepr prep auto "<goal>" --rounds 3
deepr prep pause                      # needs testing
deepr prep resume                     # needs testing
```

### Queue & Cost
```bash
deepr queue list
deepr queue stats
deepr queue sync                      # needs testing

deepr cost summary
deepr cost summary --period week
```

### Analytics (needs testing)
```bash
deepr analytics report
deepr analytics report --period month
deepr analytics trends
deepr analytics failures
```

### Configuration (needs testing)
```bash
deepr config validate
deepr config show
deepr config set KEY VALUE
```

### Templates (needs testing)
```bash
deepr templates save NAME "prompt with {placeholders}"
deepr templates list
deepr templates use NAME --key value --yes
deepr templates delete NAME
```

---

## Configuration

Create `.env` file:
```bash
# OpenAI (required)
OPENAI_API_KEY=sk-...

# Azure OpenAI (optional)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...

# Anthropic (optional, for planning tasks)
ANTHROPIC_API_KEY=...

# Prompt refinement (optional)
DEEPR_AUTO_REFINE=false  # Set to true to always optimize prompts

# Cost limits (optional)
DEEPR_MAX_COST_PER_JOB=10.0
DEEPR_MAX_COST_PER_DAY=100.0
DEEPR_MAX_COST_PER_MONTH=1000.0
```

---

## Cost & Quality

Deep research takes time and resources because it's comprehensive, not superficial.

| Depth | Cost | Time | What You Get |
|-------|------|------|--------------|
| Quick insights | $1-2 | 5-10 min | Focused analysis with citations |
| Thorough reports | $1-5 | 15-30 min | Comprehensive synthesis |
| Multi-phase campaigns | $5-15 | 40-90 min | Adaptive research, cumulative understanding |
| Expert-level | $10-20 | 60-120 min | World-class analysis with validation |

**Quality philosophy:**
- **o3-deep-research** - Use for breakthrough-quality when you need the best
- **o4-mini-deep-research** - Use for rapid exploration and iteration
- **Multi-phase** - Each round builds deeper understanding
- **Context chaining** - Later phases leverage earlier insights

---

## Current Status

**v2.3 in development**

**Production-ready (tested):**
- Single deep research jobs
- File upload with vector store support
- Automatic prompt refinement
- Background worker
- Cost tracking
- Web UI with real-time updates

**Implemented (needs testing):**
- Ad-hoc result retrieval
- Cost breakdowns with token usage
- Human-in-the-loop controls
- Provider resilience (auto-retry, fallback)
- Vector store management
- Configuration validation
- Analytics and insights
- Prompt templates

**Beta:**
- Multi-phase campaigns
- GPT-5 as research lead
- Context chaining

**Experimental:**
- Dynamic research teams

See [docs/ROADMAP.md](docs/ROADMAP.md) for detailed development plans.

---

## Vision: Agentic Learning

Deepr is evolving from adaptive planning toward autonomous expertise acquisition.

| Level | Description | Status |
|-------|-------------|--------|
| **Level 1** | Reactive Execution (single-turn) | Complete |
| **Level 2** | Procedural Automation (scripted) | Complete |
| **Level 3** | Adaptive Planning (feedback-driven) | **Current (v2.3)** |
| **Level 4** | Reflective Optimization (learns from outcomes) | Target (v2.5) |
| **Level 5** | Autonomous Expertise Acquisition | Vision (v3.0+) |

**Level 5 means:**
- Agent identifies its own knowledge gaps
- Plans next research autonomously
- Runs mock conversations to surface blind spots
- Continues until expertise validated
- Presents findings with humility: "Here's what I understand, but I may have blind spots"

This isn't consciousness - it's autonomous expertise acquisition through self-directed learning.

---

## Multi-Provider Support

**Current:** OpenAI Deep Research API (o3-deep-research, o4-mini-deep-research)

**Architecture ready for:**
- Anthropic (Claude with Extended Thinking)
- Google (Gemini with web search)
- xAI (Grok with agentic tools)
- Azure OpenAI

```bash
# Planned
deepr research submit "..." --provider anthropic --yes
```

---

## Use Cases

**Good for:**
- Market research and competitive analysis
- Meeting preparation with context
- Document analysis (specs, transcripts, reports)
- Strategic planning with company context
- Multi-round research until mastery
- Novel perspectives on complex topics
- Ethical debates with multiple viewpoints

**Not suitable for:**
- Quick facts (use regular GPT - seconds, $0.01)
- Conversational chat or real-time applications
- Sub-minute response time requirements

---

## What Is Deep Research?

Deep Research is autonomous multi-step research using advanced reasoning models:

1. **Planning** - Model breaks down query into research steps
2. **Execution** - Autonomously searches web, reads sources, gathers information
3. **Synthesis** - Analyzes findings, identifies patterns, generates insights
4. **Output** - Comprehensive report with inline citations

**Comparison with standard LLM queries:**
- **Standard GPT:** Single prompt, single response (seconds, $0.01)
- **Deep Research:** Agentic loop, comprehensive analysis (minutes-hours, $0.50-$5+)

The trade-off: 50-100x slower and more expensive, but produces comprehensive research reports that would take hours to compile manually.

---

## Interfaces

Deepr is designed to be used however you work:

**CLI (Primary Interface)**
```bash
deepr research submit "Your query" --yes
deepr prep auto "Complex multi-phase research" --rounds 3
```
Command-line interface for developers, scripts, and automation workflows.

**Local Web UI**
```bash
python -m deepr.api.app  # ChatGPT-style interface at localhost:5000
```
Visual interface for interactive use. Runs locally on Windows, Mac, or Linux - no external dependencies.

**MCP Server (Planned v2.4)**
```bash
deepr mcp serve  # Exposes Deepr as Model Context Protocol server
```
Enable AI agents and tools to use Deepr as a research capability:
- Claude Desktop, Cursor, Windsurf, and other MCP-aware tools can call Deepr
- Agents autonomously submit research requests and retrieve comprehensive reports
- Deepr becomes part of the AI agent's toolbox, just like any other capability

MCP also enables Deepr to connect to other data sources (Slack, Notion, internal docs) for context-aware research.

**Architecture Philosophy:**
- **CLI first** - Primary interface for power users and automation
- **Multi-interface** - Available where you need it (terminal, browser, AI agents)
- **Provider-agnostic** - OpenAI today, ready for others as they add deep research capabilities
- **Open standard** - MCP integration enables ecosystem compatibility

---

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) - Installation guide
- [docs/FEATURES.md](docs/FEATURES.md) - Complete feature reference
- [docs/ROADMAP.md](docs/ROADMAP.md) - Development roadmap
- [docs/CHANGELOG.md](docs/CHANGELOG.md) - Version history

---

## Contributing

High-impact areas:
- Context chaining logic and prompt engineering
- Synthesis strategies for integrating findings
- Cost optimization techniques
- Template patterns for common research workflows
- Provider integrations
- Documentation and examples

Most valuable work is on the intelligence layer (planning, context management, synthesis) rather than infrastructure.

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Mission

Deepr aims to be the open-source platform for agentic learning and knowledge automation. We're building research infrastructure that enables humans and AI systems to acquire expertise at any depth.

**Where we are:**
- Level 3 adaptive planning (production)
- Honest about current capabilities
- Realistic about challenges ahead

**Where we're going:**
- Level 5 autonomous expertise acquisition
- Agent validates own understanding through simulated expert review
- Presents findings with beginner's mind: confident but humble
- Admits gaps, researches more when needed

We're ambitious about the potential: autonomous research systems that earn trust through demonstrated wisdom, not hype. Quality and transparency before automation and scale.

**Current status:** v2.3 in development. Single jobs with file upload and prompt refinement are production-ready. Many v2.3 features implemented but need real-world testing. Multi-phase research is beta. MCP integration and autonomous learning features planned for v2.4-v2.5.

---

## Credits

Created by **Nick Seal**.

**Philosophy:** Automate research execution and strategy, but never sacrifice quality for automation. Context is everything. We bias toward fresh research and human judgment to build systems worthy of trust.

Knowledge is power. We're automating the learning.

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/yourusername/deepr)**
