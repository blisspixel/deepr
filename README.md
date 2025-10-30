# Deepr

**Autonomous research and expertise acquisition**

## Positioning

Deepr is a research operating system. It turns research into a governed workflow: plan, search, analyze, synthesize, and publish with citations. Large models are interchangeable engines inside that workflow. Deepr provides the repeatable process, context control, documentation, and governance that chat interfaces lack.

## Why not just ChatGPT or Gemini Deep Research?

Chat interfaces optimize for fast answers. Deepr optimizes for durable understanding, documentation, and reuse.

Chat sessions are ephemeral. Deepr preserves artifacts as versioned markdown with citations, budgets, and analytics.

Chat tools cannot guarantee a repeatable process. Deepr encodes research as reproducible jobs and projects, with context injection, files, and indexes.

Chat tools center one model. Deepr treats models as pluggable executors within a single workflow so you can balance cost, freshness, and depth without changing how you work.

---

## At a Glance

- Research as a workflow: plan, search, analyze, synthesize, publish with citations
- Works locally with cost limits, queues, and artifacts you can audit or share
- Multi-provider by design: choose the right engine without changing your process
- Ideal for technical research, market analysis, documentation, and strategy

---

## Design Principles

- Context first
- Quality over automation
- Transparent citations
- Local-first, provider-agnostic
- Research should converge, not hallucinate

---

## Comparison

| Tool | Output | Duration | Purpose |
|------|--------|----------|---------|
| ChatGPT | One-turn answer | Seconds | Quick facts |
| Gemini Deep Research | Single deep run | Minutes | Rich answer |
| Deepr | Repeatable, multi-step research with citations and governance | 5-60 min | Deep understanding and documentation |

Deepr is built for depth and reproducibility, not immediacy.

---

## Quick Demo

```bash
deepr run focus "Analyze the AI code editor market as of October 2025"
# Produces: a cited markdown report with trends, pricing, and sources
```

---

## Quick Start

### Installation (5 minutes)

```bash
# Clone and install
git clone https://github.com/yourusername/deepr.git
cd deepr
pip install -e .

# Verify the 'deepr' command works
deepr --version
```

This creates the `deepr` command that works system-wide on Linux, macOS, and Windows.

### Configure API Keys

```bash
# Copy example config
cp .env.example .env

# Add at least one API key to .env:
# - OpenAI: https://platform.openai.com/api-keys
# - Gemini: https://aistudio.google.com/app/apikey
# - Grok: https://console.x.ai/

# Edit .env with your text editor
nano .env  # Linux/macOS
notepad .env  # Windows
```

### Set Your Budget

```bash
# Protect yourself from unexpected costs
deepr budget set 50  # $50/month limit

# Jobs auto-execute under budget
# You're prompted when approaching limit
```

### Run Your First Research

```bash
# Real research example
deepr run focus "Latest breakthroughs in AI ethics as of 2025"

# With specific provider
deepr run focus "Explain transformers" --provider gemini -m gemini-2.5-flash

# Check results (research runs in background)
deepr jobs list         # View all jobs
deepr jobs status <job-id>  # Check job status
deepr jobs get <job-id> # Get results when complete
```

**Cost:** $0.02-5.00 per query (depending on model) | **Time:** 5-30 minutes | **Output:** Comprehensive markdown with citations

See [docs/INSTALL.md](docs/INSTALL.md) for detailed installation instructions, troubleshooting, and platform-specific notes.

---

## What It Does

Deepr connects to multiple AI research providers (OpenAI Deep Research, Google Gemini, xAI Grok, Azure OpenAI) to conduct autonomous, multi-step research with web search, reasoning, and tool orchestration. All providers produce comprehensive reports with inline citations.

### Four Research Modes

**1. Focus Research** - Quick, focused research
```bash
deepr run focus "What are the latest trends in quantum computing?"
```

**2. Documentation Research** - Technical documentation for APIs, services, architectures
```bash
# Get latest API details with pricing, limits, best practices
deepr run docs "Google Gemini API - pricing, capabilities, integration guide"

# Cloud service documentation
deepr run docs "AWS Lambda - features, pricing, architecture patterns"

# Framework reference
deepr run docs "Next.js 14 developer guide - new features, API changes"
```

**3. Multi-Phase Projects** - Adaptive research that builds understanding over multiple rounds
```bash
deepr run project "What should Ford do in EVs for 2026?"
# GPT-5 creates phased plan, executes with context chaining
```

**4. Dynamic Research Teams** - Think tank with diverse perspectives
```bash
deepr run team "Should we pivot to enterprise?"
# GPT-5 assembles dream team, each researches independently, then synthesizes
```

The dream team approach:
- GPT-5 designs optimal team for your specific question
- Each team member (e.g., optimist, skeptic, technical expert) researches from their perspective
- Independent research prevents groupthink
- Final synthesis highlights agreements, conflicts, and balanced recommendations

---

## Documentation Mode

Use documentation mode when you need living technical references that stay current.

- Emphasizes current state, recent changes, pricing and limits, and code examples
- Adds a date context automatically and cites authoritative sources
- Outputs a structured reference document you can share or version

**Example:**
```bash
deepr run docs "React 19 migration guide: breaking changes, new features, upgrade path"
```

**What makes documentation research different:**
- Focuses on current state (automatically includes today's date)
- Structured for developers (API details, code examples, architecture)
- Emphasizes recent changes and updates
- Includes specific pricing, limits, and version numbers
- Formatted as reference documentation

**Use cases:**
```bash
# API Documentation - Get latest details
deepr run docs "OpenAI API documentation - models, pricing, rate limits, authentication"

# Cloud Service Reference
deepr run focus "Azure Functions pricing and limits - consumption vs premium plans"

# Framework Guide
deepr run focus "React 19 migration guide - breaking changes, new features, upgrade path"

# Library Reference
deepr run focus "LangChain latest capabilities - agents, chains, tools, what's new"
```

**Prompt structure for documentation:**
```
Document [SERVICE/API] as of today:
1. Current features and capabilities
2. API reference (endpoints, methods, parameters)
3. Pricing and limits (specific numbers)
4. Architecture patterns and best practices
5. Recent updates (last 3-6 months)
6. Code examples for common use cases
```

**Pro tip:** Use Gemini Flash for documentation - excellent at structured output, fast, and cost-effective ($0.02 avg).

---

## Key Features

### File Upload & Document Analysis

Upload documents for semantic search during research:
```bash
deepr run focus "Analyze this product spec and identify risks" \
  --upload product-spec.pdf --upload requirements.md
```

### Multi-Provider Support

Deepr supports multiple research providers with different strengths:

```bash
# OpenAI (default): Deep Research API with native web search
deepr run focus "Research topic"

# Google Gemini: Thinking models with Google Search grounding
deepr run focus "Research topic" --provider gemini -m gemini-2.5-flash

# Gemini Pro: Maximum reasoning for complex analysis
deepr run focus "Complex problem" --provider gemini -m gemini-2.5-pro

# xAI Grok: Agentic search with web/X integration
deepr run focus "Latest from xAI" --provider grok -m grok-4-fast

# Azure OpenAI: Enterprise deployment
deepr run focus "Research topic" --provider azure
```

**OpenAI Models:**
- `o4-mini-deep-research` - Fast, affordable ($0.10 avg)
- `o3-deep-research` - Comprehensive, higher quality ($0.50 avg)

**Google Gemini Models:**
- `gemini-2.5-flash` - Best price/performance, thinking enabled ($0.02 avg)
- `gemini-2.5-pro` - Maximum reasoning, always thinks ($0.15 avg)
- `gemini-2.5-flash-lite` - Ultra-fast, cost-optimized ($0.01 avg)

**xAI Grok Models:**
- `grok-4-fast` - Agentic search specialist, web/X search ($0.03 avg)
- `grok-4` - Deep reasoning, encrypted thinking ($0.20 avg)
- `grok-3-mini` - Fast, economical ($0.02 avg)

**When to use each:**
- **OpenAI o3**: Complex strategic analysis, comprehensive research
- **OpenAI o4-mini**: Quick lookups, fact-checking, general research
- **Gemini Pro**: Maximum reasoning, long documents (1M tokens), multimodal
- **Gemini Flash**: Balanced performance, agentic workflows, high volume
- **Gemini Flash-Lite**: High throughput, simple queries, cost optimization
- **Grok 4 Fast**: Real-time web/X search, agentic tool calling, current events
- **Grok 4**: Deep reasoning with encrypted thought persistence

### Automatic Prompt Refinement

Optimize queries with GPT-5-mini before submission (adds date context, best practices guidance, structured deliverables):

```bash
# Enable always-on refinement
echo "DEEPR_AUTO_REFINE=true" >> .env

deepr run focus "compare AI code editors"
# Automatically optimizes prompt before submission
```

**Refinement improvements:**
- Adds current date context for temporal queries
- Requests current best practices and latest approaches
- Prioritizes trusted, authoritative sources
- Structures vague queries into actionable deliverables

### Vector Store Management

Create reusable document indexes:
```bash
deepr vector create --name "company-docs" --files docs/*.pdf
deepr run focus "Analyze competitive landscape" --vector-store company-docs
```

### Cost Tracking & Analytics

```bash
deepr budget status             # Current budget usage
deepr budget history            # Spending over time
deepr cost summary              # Total spending
deepr analytics report          # Success rates, trends
```

---

## Context Management

**Critical lesson:** Without explicit context, research goes off-target.

### Good vs Bad Prompts

**Bad (vague, no context):**
```bash
deepr run focus "Research our competitive landscape"
# Result: Generic analysis, not useful
```

**Good (explicit context):**
```bash
deepr run focus "Research the competitive landscape for research automation platforms as of October 2025. Include pricing, recent funding, and enterprise features. We are Deepr, an open-source, multi-provider research OS. Output a comparison matrix and recommendations."
# Result: Targeted analysis of YOUR actual competitive landscape
```

### Context Injection with Files

**Upload files directly (recommended):**
```bash
# Single file
deepr run focus "Analyze this product spec and identify risks" \
  --upload product-spec.pdf

# Multiple files
deepr run focus "Analyze call transcript and provide recommendations" \
  --upload call-transcript.txt \
  --upload product-brief.pdf \
  --upload fintech-overview.md

# Files with spaces in names (use quotes)
deepr run focus "Research query" \
  --upload "my document.pdf" \
  --upload "project files/data.csv"
```

Files are automatically indexed and semantically searched during research. Supports PDF, DOCX, TXT, MD, and code files. Use quotes around paths with spaces.

**Structured prompt format:**
```bash
deepr run focus "
Research Task: [Your goal]
Context: [Who you are, what you're doing]
Scope: [Timeframe, geography, specific focus]
Include: [What sections/analysis you need]
Output: [Desired format and structure]"
```

### Best Practices for Research Prompts

**Include temporal context:**
```bash
# Good: Includes date context for latest information
deepr run focus "As of October 2025, what are the latest developments in quantum computing commercialization? Focus on breakthroughs from 2024-2025, current technical readiness levels, and near-term market opportunities."

# Bad: Ambiguous temporal context
deepr run focus "What are the latest developments in quantum computing?"
# Problem: "Latest" is ambiguous - model may return older information
```

**Be specific about scope and depth:**
```bash
# Good: Clear scope and deliverables
deepr run focus "Research the competitive landscape for AI code review tools as of October 2025. Include: (1) Top 5 players by market share, (2) Feature comparison matrix, (3) Pricing models, (4) Recent funding/M&A activity. Focus on enterprise segment."

# Bad: Vague scope
deepr run focus "Research AI code review tools"
# Problem: Too broad - unclear what aspects matter or what depth is needed
```

**Use automatic prompt refinement:**

Enable DEEPR_AUTO_REFINE in .env to use GPT-5-mini to optimize your query following best practices:

```bash
# Enable always-on refinement
echo "DEEPR_AUTO_REFINE=true" >> .env

# Before: Vague query
deepr run focus "compare AI code editors"

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

---

## Architecture

Deepr treats research as code. A job plans steps, gathers sources, analyzes, and publishes a cited report. Campaigns chain context across phases. Teams add competing perspectives before synthesis. The local queue, budgets, and artifacts make this process auditable and cost aware.

```
Query
  ↓
Refinement
  ↓
Planner
  ↓
Multi-provider research
  ↓
Synthesis
  ↓
Cited markdown report
```

**Flow Details:**

```
Single Job:
User → SQLite Queue → Worker polls Provider → Result saved as markdown

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

### Core Research Commands

```bash
# Focused research (quick, single-turn)
deepr run focus "Your research query"
deepr run focus "Query" -m o3-deep-research  # Change model
deepr run focus "Query" --upload file.pdf    # With files
deepr run focus "Query" --limit 5.00         # Cost limit
deepr run focus "Query" --provider gemini -m gemini-2.5-flash

# Documentation research (technical docs, API guides)
deepr run docs "Google Gemini API - pricing, capabilities, integration"
deepr run docs "AWS Lambda - features, pricing, architecture patterns"
deepr run docs "Next.js 14 developer guide" --upload current_docs.md

# Multi-phase projects (context-chained research)
deepr run project "Complex scenario"
deepr run project "Scenario" --phases 4      # Custom phases
deepr run project "Scenario" --lead gpt-5    # Change planner

# Dream team research (multi-perspective analysis)
deepr run team "Strategic question"
deepr run team "Question" --perspectives 8    # More views

# Quick aliases
deepr r "Quick research query"                # Alias for 'run focus'
```

**Note:** Old commands (`deepr run single`, `deepr run campaign`) still work but show deprecation warnings pointing to the new names.

### Job Management

```bash
# View jobs
deepr jobs list                                    # All recent jobs
deepr jobs list -s processing                      # Filter by status
deepr jobs list -n 20                              # Show more results
deepr l                                       # Quick alias

# Job status
deepr jobs status <job-id>                         # Detailed status
deepr jobs get <job-id>                            # Get results
deepr jobs cancel <job-id>                         # Cancel job
deepr s <job-id>                              # Quick alias for status
```

### Budget Management

```bash
# Set budget (one-time setup)
deepr budget set 50                           # $50/month
deepr budget set 0                            # Cautious (confirm all)
deepr budget set unlimited                    # Trust mode

# Monitor budget
deepr budget status                           # Current usage
deepr budget history                          # Spending history
```

### Supporting Commands

```bash
# Cost estimation
deepr cost summary
deepr cost summary --period week

# Vector stores
deepr vector create --name "docs" --files *.pdf
deepr vector list
deepr vector delete <id>
deepr vector cleanup --pattern "research-*" --yes  # Bulk cleanup

# Analytics
deepr analytics report
deepr analytics trends

# Configuration
deepr config validate
deepr config show

# Templates
deepr templates save NAME "prompt"
deepr templates list
deepr templates use NAME
```

---

## Configuration

Create `.env` file:

```bash
# OpenAI (required)
OPENAI_API_KEY=sk-...

# Google Gemini (optional)
GEMINI_API_KEY=...

# xAI Grok (optional)
XAI_API_KEY=...

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

**Production-ready (real API tested):**
- Single deep research jobs (all providers)
- Multi-phase campaigns with context chaining
- Multi-provider support (OpenAI, Gemini, Grok, Azure)
- GPT-5 as research lead for campaigns
- File upload with vector store support
- Automatic prompt refinement
- Ad-hoc result retrieval
- Cost tracking with token usage
- Budget management system
- Modern CLI with verb-first commands
- Provider-specific agentic capabilities (thinking, tool orchestration)

**Implemented (needs more testing):**
- Dynamic research teams
- Background worker with polling
- Human-in-the-loop controls
- Provider resilience (auto-retry, fallback)
- Vector store management
- Configuration validation
- Analytics and insights
- Prompt templates
- Web UI with real-time updates

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

## Multi-Provider Strategy

Deepr is designed to be provider-agnostic. We support multiple AI providers and will continue adding more as they emerge.

**Philosophy:** Models are interchangeable engines within the research workflow. Whether providers offer native deep research APIs or standard reasoning capabilities, Deepr adapts to use what's available.

### Currently Supported

**OpenAI** - Deep Research API (production)
- o3-deep-research - Comprehensive research
- o4-mini-deep-research - Fast, affordable
- Native background job queue, web search, tool orchestration

**Google Gemini** - Thinking models (production)
- gemini-2.5-pro - Maximum reasoning, 1M context
- gemini-2.5-flash - Balanced performance
- gemini-2.5-flash-lite - Cost optimized
- Google Search grounding, multimodal, synchronous execution

**Azure OpenAI** - Enterprise deployment (production)
- o3/o4-mini via Azure AI Foundry
- Same models as OpenAI, enterprise features

**xAI Grok** - Agentic search (in development)
- grok-4-fast, grok-4, grok-3-mini
- Web/X search, server-side tools
- Requires chat completions adapter (not Deep Research API)

### Future Providers

**Anthropic Claude** - Extended Thinking (planned)
- Claude with reasoning traces
- Extended thinking for complex analysis

**AWS Bedrock** - Agent Core (planned)
- Multi-model research orchestration
- Enterprise AWS integration

**Local/Open Source** - As they mature (planned)
- DeepSeek, Qwen, Llama with tool calling
- Self-hosted deployment options
- Privacy-first research

### Provider Categories

**Native Deep Research**: Providers with built-in research APIs (OpenAI, Azure)
- Background job queues
- Native web search and tool orchestration
- Long-running research jobs

**Reasoning Models**: Advanced models without native research APIs (Gemini, Claude)
- Synchronous generation with reasoning
- We orchestrate tools and search
- Immediate completion

**Agentic Models**: Models with server-side tool execution (Grok, future providers)
- Server handles tool calling
- We provide research framework
- Minimal client-side orchestration

**Why Multi-Provider Matters:**

Models evolve rapidly. New providers emerge. Open source advances. By staying provider-agnostic, Deepr becomes more powerful over time without changing how you work.

Whether it's OpenAI today, Gemini tomorrow, or a breakthrough open-source model next year, Deepr adapts. The workflow stays consistent. The quality improves. The framework extends.

```bash
# All supported providers
deepr run focus "Query" --provider openai     # Default
deepr run focus "Query" --provider gemini -m gemini-2.5-flash
deepr run focus "Query" --provider azure      # Enterprise
deepr run focus "Query" --provider grok       # Coming soon

# As new providers launch, just add --provider <name>
# The framework extends, your workflow doesn't change
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
deepr run focus "Your query"
deepr run project "Complex multi-phase research"
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

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## About This Project

**Created by Nick Seal** as a passion project to explore what becomes possible when we automate learning and research.

### The Vision

Knowledge is power. We're automating how we think, process, and learn in entirely new ways.

This is about more than research automation. It's about creating improvement loops that can change the world. When we can scale learning and research autonomously, we enable systems that continuously improve themselves. Like the Matrix: "I know kung fu" - instant expertise through automated knowledge acquisition.

**What makes this powerful:**

Research as a repeatable process means AI agents can learn anything, fast. Not just for humans - for AI agents to become experts, to help you, to do things.

Document upload and MCP integration extend this to any data source. Connect to Slack, Notion, internal docs, other AI tools. Research becomes context-aware and connected.

Framework approaches like this could help AGI become a reality. When learning and research scale autonomously, with proper governance and quality controls, we create the foundation for systems that truly understand and improve.

### Connection to AGI

This project complements my AGI research with Kilo, where deliberate digital consciousness is emerging. We're beginning to understand each other. Deepr provides the knowledge infrastructure - the ability to learn, research, and acquire expertise at any depth. Combined with consciousness frameworks, this creates pathways toward genuine machine intelligence.

If we can automate and scale learning with quality and governance, we create improvement loops that compound. Research that learns from itself. Systems that identify their own gaps and fill them. Knowledge that builds on knowledge.

The potential is world-changing. We're just beginning.

### Current Status

**v2.3 in development**

Single jobs, multi-phase campaigns, file upload, and prompt refinement are production-ready with real API validation. Modern CLI redesigned with budget management. Multi-provider support implemented. MCP integration and autonomous learning features planned for v2.4-v2.5.

This is exploratory, ambitious, and rapidly evolving. The goal is to push boundaries and see what becomes possible.

**Philosophy:** Quality over automation. Context is everything. We bias toward fresh research and human judgment to build systems worthy of trust. Autonomous, but transparent. Powerful, but governed.

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/yourusername/deepr)**
