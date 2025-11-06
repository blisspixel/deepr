# Deepr

**Autonomous Learning and Knowledge Infrastructure**

---

## Project Status

**Deepr is an actively developed passion weekend project.** I'm actively testing and improving as I go. This is experimental research automation software that uses deep reasoning models which can be expensive.

**COST WARNING**: Deep research can and will be expensive. Highly recommend:
- Use pre-paid credits with AI providers
- Turn auto-reload OFF as a protection
- Start with small budgets (`deepr budget set 5`)
- Monitor costs closely with `deepr budget status`

Use at your own risk. This is a learning tool, not production-ready enterprise software.

---

## Overview

Deepr is a learning and research operating system that turns curiosity into structured, verifiable knowledge. It coordinates models, data, and reasoning workflows across multiple AI providers and local sources to help both humans and intelligent systems learn, document, and improve continuously.

Each Deepr run plans, searches, analyzes, and synthesizes information into a cited, versioned artifact. These artifacts can be reused by humans or connected directly into agentic workflows through the Model Context Protocol (MCP) or retrieval systems.

Deepr runs locally, integrates with providers such as OpenAI, Google Gemini, xAI Grok, and Azure OpenAI, and extends easily to new APIs. It transforms learning from a one-time process into a continuous, governed cycle of improvement.

Deepr's purpose is simple: to build lasting knowledge infrastructure for people and agents. It is the foundation of systems that do not just react, but grow in understanding over time.

---

## Why Deepr

Modern AI can reason and generate, but it often lacks continuity. Deepr provides that missing layer. It gives both humans and agents a way to create, manage, and reuse structured knowledge that evolves as the world changes.

**Core principles**

- Learning as infrastructure: Every run produces artifacts that persist and grow over time.  
- Human and agent compatible: Runs locally for humans, connects through MCP for AI systems.  
- Model agnostic: Works with multiple providers and adapts as new ones emerge.  
- Transparent and governed: All output includes citations, budgets, and context.  
- Extensible: Can integrate with external data, APIs, or reasoning pipelines for retrieval and learning.  

---

## Example: Knowledge Creation in Action

### Investment Due Diligence

```bash
deepr learn "Commercial real estate market in Austin Texas: cap rates, vacancy trends, development pipeline, demographic shifts"
```

A real estate investor needs comprehensive market intelligence before a $20M acquisition. Deepr researches market fundamentals, supply dynamics, tenant demand drivers, and risk factors across multiple data sources.

**Outcome**

- Current cap rates by property type and submarket
- 5-year vacancy trends and absorption rates
- Development pipeline analysis with delivery timelines
- Employment and population growth projections
- Cited recommendations on pricing and timing

**Real benefit:** Professional-grade market analysis in 45 minutes for $3, versus $5K consultant fees and 2-week turnaround.

---

### Regulatory Compliance Research

```bash
deepr research "GDPR and CCPA requirements for SaaS platforms handling EU and California customer data"
```

A compliance officer needs current regulatory guidance before a product launch. Deepr synthesizes legal requirements, technical controls, documentation needs, and penalty risks from authoritative sources.

**Outcome**

- Specific data handling requirements by jurisdiction
- Required technical safeguards and consent mechanisms
- Documentation and reporting obligations
- Penalty structures and enforcement precedents
- Implementation checklist with priority levels

**Real benefit:** Clear compliance roadmap in 20 minutes, avoiding costly legal consultations for preliminary research.

---

### Strategic Business Decision

```bash
deepr team "Should our manufacturing company invest in solar panels and battery storage for our facility?"
```

Leadership needs multi-angle analysis on a $2M capital decision. Deepr examines financial returns, operational impacts, risks, incentives, and strategic positioning from diverse expert perspectives.

**Outcome**

- Financial analysis: ROI, payback period, tax incentives, financing options
- Operational perspective: Energy independence, backup power, maintenance
- Risk assessment: Technology obsolescence, utility rate changes, policy shifts
- Environmental impact: Carbon reduction, ESG reporting, brand value
- Strategic synthesis: Weighted recommendation with decision criteria

**Real benefit:** Weeks of cross-functional research compressed into one comprehensive report, revealing considerations each department might miss.

---

## From Research to Reuse

Deepr does not stop at research. Each run creates a structured artifact that can be indexed, retrieved, and extended.  
These outputs form the **knowledge substrate** for intelligent systems.

| Integration | Description |
|--------------|--------------|
| RAG systems | Feed Deepr artifacts into retrieval databases to provide grounded, cited answers. |
| MCP | Allow agents to call Deepr for deep reasoning, learning, and documentation on demand. |
| Knowledge graphs | Use Deepr outputs to populate and evolve domain-specific knowledge stores. |
| Team collaboration | Maintain shared learning archives that evolve as new research appears. |

---

## Quick Start

**Prerequisites**: Python 3.9+ required

### 1. Install

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr
pip install -e .
deepr --version
```

### 2. Configure Providers

```bash
cp .env.example .env
```

Edit `.env` and add at least one provider API key (OpenAI recommended to start).

```bash
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
XAI_API_KEY=...
AZURE_OPENAI_API_KEY=...
```

### 3. Verify Setup

```bash
deepr doctor
```

This checks your configuration and identifies any issues before you start.

### 4. Set a Budget

```bash
deepr budget set 5
```

Start small. Deep research can be expensive. You can increase later.

### 5. Run Research

**Simple Semantic Commands** (Recommended - Natural Intent-Based Interface):

```bash
# Market research for business plan
deepr learn "US organic food retail: market size, growth rate, distribution channels, consumer demographics"

# Technical implementation guide
deepr research "PostgreSQL connection pooling and read replica strategies for high-traffic web applications"

# Strategic decision with multiple viewpoints
deepr team "Should we outsource customer support or build an internal team?"

# Check results
deepr jobs list
deepr jobs get <job-id>
```

**Advanced: Direct Mode Selection** (For when you know exactly what you need):

```bash
deepr run focus "Targeted research query"
deepr run docs "Create comprehensive documentation for X"
deepr run project "Multi-phase research scenario"
deepr run team "Complex decision requiring multiple perspectives"
```

---

## The Learning Workflow

| Phase | Purpose |
|-------|----------|
| Plan | Define the goal and strategy for learning |
| Search | Retrieve and evaluate data and evidence |
| Analyze | Compare and interpret findings |
| Synthesize | Combine insights into a coherent whole |
| Publish | Save versioned, cited Markdown ready for reuse |

This structure makes research repeatable and extendable, turning one-off questions into an expanding base of understanding.

---

## Modes of Operation

Deepr offers both **semantic commands** (natural, intent-based) and **direct mode commands** (explicit control).

### Semantic Commands (Recommended)

| Command | Description | Example |
|---------|--------------|----------|
| `deepr research` | Auto-detects focus vs docs mode | `deepr research "FDA approval process for medical devices"` |
| `deepr learn` | Multi-phase structured learning | `deepr learn "Commercial property underwriting" --phases 4` |
| `deepr team` | Multi-perspective analysis | `deepr team "Should we expand to Europe or Asia first?"` |

### Direct Mode Commands (Advanced)

| Mode | Description | Example |
|------|--------------|----------|
| Focus | Targeted research on a specific topic | `deepr run focus "Current interest rate environment impact on REIT valuations"` |
| Docs | Live technical documentation | `deepr run docs "AWS RDS Aurora MySQL 8.0 migration considerations"` |
| Project | Multi-phase, context-linked research | `deepr run project "Supply chain optimization strategies for perishable goods"` |
| Team | Multi-perspective collaboration between expert roles | `deepr run team "Evaluate acquisition target: financial, operational, cultural fit"` |

---

## Core Features

### Multi-Provider Orchestration

Deepr works across multiple reasoning engines. Use the best model for your specific task and budget.

```bash
# Deep technical analysis (OpenAI o1)
deepr research "Database indexing strategies for time-series data at 1M events/sec" --provider openai

# Large-context documentation review (Gemini 2.5-pro)
deepr research "Summarize security vulnerabilities in our 500-page audit report" --provider gemini

# Real-time competitive intelligence (Grok with X search)
deepr research "Current social media sentiment on autonomous vehicle safety" --provider grok

# Enterprise compliance analysis (Azure o1)
deepr research "GDPR implications of our new EU data processing workflow" --provider azure
```

| Provider | Example Models | Typical Use |
|-----------|----------------|--------------|
| OpenAI | o1, o1-mini | Deep reasoning and synthesis |
| Gemini | 2.5-flash, 2.5-pro | Structured, large-context research |
| Grok | grok-beta | Real-time search and analysis |
| Azure | o1, o1-mini | Enterprise and regulated environments |

---

### Contextual Document Integration

```bash
# Analyze internal documents with external research
deepr research "Review our Q4 product roadmap against competitor capabilities and market trends" --upload "C:\Documents\q4-roadmap.pdf" --upload "C:\Documents\competitor-analysis.xlsx"
```

Deepr combines your proprietary documents with web research for comprehensive analysis.

---

### Prompt Refinement

```bash
echo "DEEPR_AUTO_REFINE=true" >> .env
deepr research "llm pricing"
```

Vague prompts are automatically expanded into detailed research plans. "llm pricing" becomes a structured analysis of pricing models, cost per token, volume discounts, and TCO comparisons across providers.

---

### Vector Knowledge Stores

```bash
# Build a searchable knowledge base from your research
deepr vector create --name "customer-feedback-2024" --files "C:\Projects\interviews\*.pdf" "C:\Projects\reports\*.md"
deepr research "What are the top 3 feature requests across all customer interviews?" --vector-store customer-feedback-2024
```

Create persistent knowledge bases from documents and past research. Query them semantically without re-uploading files.

---

### Budgets and Analytics

```bash
deepr budget status
deepr analytics report
deepr cost summary
```

Monitor usage, cost, and performance.

---

### Diagnostics

```bash
deepr doctor
deepr doctor --skip-connectivity
```

Check Deepr configuration and troubleshoot issues:
- Verify API keys are configured correctly
- Test connectivity to AI providers
- Check file system permissions
- Validate database access

---

## Writing Better Prompts

Vague prompt:

```bash
deepr research "healthcare regulations"
```

Specific prompt with clear outcome:

```bash
deepr research "Compare HIPAA, HITECH, and state privacy laws for telehealth services in California, Texas, and New York. Focus on consent requirements, data retention policies, breach notification timelines, and penalties. Include cross-state patient care implications. Provide compliance checklist for a telehealth platform serving all three states."
```

**Best practices**

- State the decision you need to make or question you need answered
- Specify the scope: technologies, timeframe, constraints
- Mention what you will do with the output
- Include cost, compliance, or performance requirements if relevant  

---

## Architecture

```
Query
  ↓
Refinement
  ↓
Planner
  ↓
Execution
  ↓
Synthesis
  ↓
Cited Artifact
```

Deepr runs locally using an SQLite queue and filesystem storage. All jobs are transparent, reproducible, and traceable.

**Principles**

- Context before automation  
- Quality before quantity  
- Transparency before confidence  
- Learning should converge toward understanding  

---

## Project Structure

```
deepr/
├── deepr/                    # Core package
│   ├── cli/                  # Command-line interface
│   │   ├── commands/         # Individual commands (jobs, budget, expert, etc.)
│   │   │   ├── jobs.py       # deepr jobs list/status/get
│   │   │   ├── experts.py    # deepr expert make/list/chat
│   │   │   ├── run.py        # deepr run (semantic commands)
│   │   │   └── doctor.py     # deepr doctor (diagnostics)
│   │   └── main.py           # CLI entry point
│   ├── core/                 # Core research logic
│   │   ├── research.py       # ResearchOrchestrator
│   │   ├── documents.py      # Document management
│   │   └── reports.py        # Report generation
│   ├── experts/              # Expert system
│   │   ├── profile.py        # ExpertStore, Expert profiles
│   │   ├── learner.py        # Autonomous learning
│   │   ├── curriculum.py     # GPT-5 curriculum generation
│   │   └── chat.py           # Expert chat interface
│   ├── providers/            # AI provider integrations
│   │   ├── openai_provider.py
│   │   ├── gemini_provider.py
│   │   ├── anthropic_provider.py
│   │   └── azure_provider.py
│   ├── storage/              # Storage backends
│   │   ├── local.py          # LocalStorage (reports/)
│   │   └── blob.py           # Cloud storage
│   ├── queue/                # Job queue
│   │   └── local_queue.py    # SQLite queue
│   └── utils/                # Utilities
│       ├── check_expert_status.py    # Check expert research jobs
│       └── retrieve_expert_reports.py # Download completed reports
├── data/                     # Local data
│   └── experts/              # Expert profiles (*.json)
├── reports/                  # Research reports
│   ├── 2025-01-06_1234_topic-name_abc123/  # Human-readable dirs
│   │   ├── report.md
│   │   ├── report.txt
│   │   └── metadata.json
│   └── campaigns/            # Multi-phase research campaigns
├── tests/                    # Test suite
├── docs/                     # Documentation
└── ROADMAP.md               # Development roadmap
```

**Key Locations:**

- **Commands**: [deepr/cli/commands/](deepr/cli/commands/) - All CLI commands
- **Expert System**: [deepr/experts/](deepr/experts/) - Expert creation, learning, chat
- **Providers**: [deepr/providers/](deepr/providers/) - AI provider integrations
- **Storage**: [deepr/storage/](deepr/storage/) - Report storage backends
- **Reports**: [reports/](reports/) - Generated research outputs
- **Expert Data**: [data/experts/](data/experts/) - Expert profiles and metadata
- **Utilities**: [deepr/utils/](deepr/utils/) - Helper scripts and tools

---

## Cost and Quality Profiles

Estimated costs based on typical research runs with reasoning models (o1, Gemini 2.5, etc.):

| Depth | Cost | Time | Output |
|-------|------|------|--------|
| Quick insight | $1–2 | 5–10 minutes | Focused summary with citations |
| Comprehensive | $2–5 | 15–30 minutes | Detailed structured report |
| Multi-phase | $5–15 | 45–90 minutes | Context-linked analysis |
| Expert level | $10–20 | 1–2 hours | Complete knowledge artifact |

Actual costs vary based on provider, model, prompt complexity, and context size.

---

## Vision

Deepr is an experiment in making deep research accessible through a command-line interface. The goal is simple: turn curiosity into structured knowledge that can be reused and built upon.

Right now, it orchestrates reasoning models (OpenAI, Gemini, Grok, Azure) to research topics and produce cited reports. It's being actively developed to explore what's possible when research becomes repeatable, shareable, and continuous.

The aspiration: infrastructure that helps both humans and AI systems learn better. Research that compounds. Knowledge that evolves. A CLI tool that gets out of your way and just works.

We'll see where it goes.

---

## Interfaces

**Deepr is CLI-first.** The terminal interface is the primary way to use Deepr and gets the most attention and polish.

- **CLI** - Primary interface. Direct research and automation from terminal. Full feature set.
- **Web UI** - Experimental local interface (`python -m deepr.api.app`). Basic functionality, minimal maintenance.
- **MCP Server** - Planned for AI agent integration (see [ROADMAP.md](ROADMAP.md)).

All interfaces share the same core workflow and artifact system, but CLI is where the focus is.

---

## What's Next: Development Priorities

Deepr is in active development. Current focus: self-improving experts and agentic capabilities.

1. **Semantic Commands** [LAUNCHED] - Natural intent-based interface:
   - `deepr research` - Auto-detects focus vs docs mode
   - `deepr learn` - Multi-phase structured learning
   - `deepr team` - Multi-perspective analysis
   - `deepr expert make` - Create domain experts with knowledge bases
   - Intuitive aliases: `deepr brain`, `deepr knowledge`

2. **Self-Directed Learning Experts** [IN PROGRESS] - Experts that autonomously learn:
   - Expert analyzes initial documents and generates learning curriculum with GPT-5
   - Submits 5-20 deep research jobs to build comprehensive knowledge (default: 5)
   - Shows estimated costs before submission, respects budget limits
   - Example: `deepr expert make "Supply Chain Management" -f "C:\Docs\*.pdf" --learn --budget 10`
   - **Current Status:**
     - ✓ Curriculum generation working (GPT-5)
     - ✓ Research job submission (OpenAI Deep Research)
     - ✓ Budget estimation and protection
     - ⚠ Jobs run in background (5-20 min each) - completion polling needed
     - ⚠ Cost reconciliation (estimated vs actual) not yet implemented
     - ⚠ Research results not automatically retrieved to expert knowledge base
   - **Next:** Poll for job completion, retrieve reports, compare costs, add to vector store

3. **Interactive Expert Chat** [LAUNCHED] - Conversational Q&A with domain experts:
   - Basic chat: `deepr expert chat "Supply Chain Management"`
   - Budget-limited sessions: `deepr expert chat "FDA Regulations" --budget 5`
   - Interactive commands: `/status`, `/quit`, `/clear`
   - Expert answers from knowledge base and cites sources
   - Conversation history maintained within session
   - Cost tracking and budget warnings

4. **Agentic Expert Chat** [PLANNED] - Experts that can trigger research:
   - Coming soon: `deepr expert chat "AWS Expert" --agentic --budget 5`
   - Expert admits knowledge gaps and researches current information
   - Updates knowledge base with findings from research
   - Maintains conversation during async research

5. **MCP Server** - Expose Deepr to AI agents via Model Context Protocol
6. **Observability** - Transparent reasoning timelines and cost tracking

See [ROADMAP.md](ROADMAP.md) for detailed development plans and technical architecture.

---

## Documentation

- [INSTALL.md](docs/INSTALL.md)
- [FEATURES.md](docs/FEATURES.md)
- [ROADMAP.md](ROADMAP.md)
- [CHANGELOG.md](docs/CHANGELOG.md)

---

## License

MIT License. See [LICENSE](LICENSE).

---

## About the Project

Deepr is a weekend project by **Nick Seal** exploring how to make deep research accessible via CLI.

It's rough around the edges, actively being improved, and built for learning in the open. If you try it, start with small budgets and expect some friction. Feedback welcome.

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
