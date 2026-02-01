# Deepr

![Tests](https://img.shields.io/badge/tests-1217%20collected-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)

**TL;DR:** CLI tool for AI-powered research that produces cited reports, builds domain experts, and integrates with AI agents via MCP. Multi-provider support (OpenAI GPT-5.2, Gemini, Grok, Azure). Local-first. Early-stage software.

**Research Automation and Knowledge Infrastructure**

---

## Project Status

> **COST WARNING: Deep research can be expensive.**
>
> Deepr uses deep reasoning models that can cost $0.50-$20 per research run. Highly recommend:
> - Use pre-paid credits with AI providers
> - Turn auto-reload OFF as protection
> - Start with small budgets (`deepr budget set 5`)
> - Monitor costs closely with `deepr budget status`
>
> Use at your own risk. This is a learning tool, not production-ready enterprise software.

---

## Overview

Deepr is a research tool that coordinates AI models to produce structured, cited research artifacts. It automates the research workflow: planning, searching, analyzing, and synthesizing information into versioned markdown reports.

**What it does:**
- Plans, searches, analyzes, and synthesizes information
- Produces cited, versioned markdown reports
- Builds domain experts from documents (experimental)
- Integrates with AI agents via Model Context Protocol

**What makes it different:**
- Multi-provider support (OpenAI GPT-5.2, Gemini, Grok, Azure)
- Local-first (runs on your machine)
- Knowledge infrastructure (not just one-off queries)
- Expert system with learning capabilities (experimental)

See [docs/specifications/ARCHITECTURE.md](docs/specifications/ARCHITECTURE.md) for technical details on the self-improvement loop, autonomous learning, and knowledge synthesis.

---

## Quick Examples

### Simple Research
```bash
deepr research "PostgreSQL connection pooling strategies for high-traffic applications"
```

### Fact Verification
```bash
deepr check "Kubernetes 1.28 deprecated PodSecurityPolicy"
```

### Generate Documentation
```bash
deepr make docs --files "./src/*.py" --format markdown
```

### Strategic Analysis
```bash
deepr make strategy "Launch a SaaS product in healthcare" --perspective investor
```

### Agentic Research
```bash
deepr agentic research "Best practices for microservices observability" --rounds 3 --budget 10
```

### Multi-Phase Learning
```bash
deepr learn "Kubernetes networking: CNI, Services, Ingress, and best practices" --phases 3
```

### Strategic Team Analysis
```bash
deepr team "Should we build vs. buy our data platform?"
```

### Create Domain Expert
```bash
deepr expert make "AWS Architect" --files "./docs/*.md" --learn --budget 10
```

### Interactive Expert Chat
```bash
deepr expert chat "AWS Architect" --agentic --budget 5
```

### Intent-Based Help
```bash
deepr help verbs
```

See [docs/EXAMPLES.md](docs/EXAMPLES.md) for detailed use cases with real-world scenarios.

---

## Key Features

### Multi-Provider Orchestration

Works across OpenAI GPT-5.2, Google Gemini, xAI Grok, Azure OpenAI. Automatically routes tasks to the best model for the job.

```bash
deepr research "Topic" --provider grok --budget 2
```

See [ROADMAP.md](ROADMAP.md#model-strategy) for provider selection guidance.

### Domain Experts (Experimental)

Create experts from documents that can answer questions using vector search and optionally trigger research for knowledge gaps:

```bash
# Create expert and have it research a domain
deepr expert make "Supply Chain Expert" --learn --budget 10 --topics 10

# List available experts
deepr expert list

# Chat with expert
deepr expert chat "Supply Chain Expert"

# Chat with agentic research enabled
deepr expert chat "Supply Chain Expert" --agentic --budget 5

# Manually add knowledge to an expert
deepr expert learn "Supply Chain Expert" "latest shipping regulations 2026"

# Fill knowledge gaps proactively
deepr expert fill-gaps "Supply Chain Expert" --budget 5 --top 3

# Resume paused learning (after hitting daily/monthly limits)
deepr expert resume "Supply Chain Expert"

# Export expert knowledge for sharing
deepr expert export "Supply Chain Expert" --output ./exports/

# Import expert from exported corpus
deepr expert import "New Expert Name" --corpus ./exports/supply_chain_expert/
```

Features:
- Vector search: Expert retrieves relevant documents to answer questions
- Knowledge synthesis: Expert can create a summarized "worldview" from documents (experimental)
- Belief formation: Expert forms beliefs with confidence levels and evidence citations (experimental)
- Gap awareness: Expert tracks knowledge gaps and can research to fill them
- Manual learning: Add knowledge via topics or file uploads
- Pause/resume: Long-running learning pauses at budget limits and can be resumed
- Export/import: Package expert knowledge for sharing or backup

Status: Core implementation complete. Unit tests pass. Initial testing shows the system works as designed, but this is early-stage software. More real-world testing needed to validate reliability. The "consciousness" and "belief" terminology describes the architecture's goals, not claims about actual AI capabilities.

See [ROADMAP.md](ROADMAP.md#priority-25-agentic-expert-system-capability-extension) for detailed documentation.

### Structured Learning Workflow

Four types of knowledge artifacts that mirror how experts actually work. See [ROADMAP.md](ROADMAP.md#structured-learning-approach) for detailed workflow and cost breakdown.

### MCP Integration

Expose Deepr to AI agents via Model Context Protocol. Allows Claude Desktop, Cursor, and other MCP-compatible agents to:
- Submit long-running research jobs
- Query domain experts
- Orchestrate multi-step research workflows
- Subscribe to research progress via resource URIs
- Handle budget decisions through elicitation

**Advanced MCP Patterns:**
- Dynamic Tool Discovery: Reduces context by ~85% through on-demand tool schema loading
- Resource Subscriptions: Event-driven async monitoring (70% token savings vs polling)
- Human-in-the-Loop Elicitation: Cost governance with structured user decisions
- Sandboxed Execution: Isolated contexts for heavy research operations

**Status:** Core implementation complete. Testing with MCP clients ongoing.

See [mcp/README.md](mcp/README.md) for setup instructions and [skills/deepr-research/](skills/deepr-research/) for the Claude Skill.

### Web Scraping

Web scraping with fallback strategies for accessing web content when needed.

See [deepr/utils/scrape/README.md](deepr/utils/scrape/README.md) for API documentation.

---

## Installation

**Prerequisites:** Python 3.9+

**New to Deepr?** Start with [docs/QUICK_START.md](docs/QUICK_START.md) for a guided setup.

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr
pip install -e .
deepr --version
```

### Configure Providers

```bash
cp .env.example .env
```

Edit `.env` and add at least one provider API key:

```bash
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
XAI_API_KEY=...
AZURE_OPENAI_API_KEY=...
```

### Verify Setup

```bash
deepr doctor
```

Checks configuration and identifies issues before you start.

### Set Budget

```bash
deepr budget set 5
```

Start small. Deep research can be expensive. You can increase later.

---

## Basic Usage

### Research Commands

```bash
# Simple research (auto-detects mode)
deepr research "FDA approval process for medical devices"

# Multi-phase structured learning
deepr learn "Commercial property underwriting" --phases 4

# Multi-perspective analysis
deepr team "Should we expand to Europe or Asia first?"

# Latest developments (news)
deepr news "Kubernetes security vulnerabilities 2025"
```

### Semantic Commands

Intent-based commands that express what you want to accomplish:

```bash
# Fact verification - check if a claim is true
deepr check "PostgreSQL supports JSONB indexing since version 9.4"

# Generate documentation from files
deepr make docs --files "./src/*.py" --format markdown

# Generate documentation outline only
deepr make docs --files "./api/*.ts" --outline

# Generate strategic analysis
deepr make strategy "Enter the European market" --perspective competitor --horizon 2years

# Agentic research with Plan-Execute-Review cycles
deepr agentic research "Optimal database for our recommendation engine" --rounds 3 --budget 10

# Resume interrupted agentic research
deepr agentic research --resume

# Get help organized by intent
deepr help verbs
```

**Semantic Command Details:**

- **`deepr check`**: Verifies factual claims using web search and AI analysis. Returns verdict (true/false/uncertain), confidence score, and supporting sources.

- **`deepr make docs`**: Generates structured documentation from source files. Supports markdown and HTML output formats. Use `--outline` for structure-only preview.

- **`deepr make strategy`**: Creates strategic analysis with sections for situation analysis, options, recommendations, and risks. Use `--perspective` (neutral/competitor/investor) and `--horizon` (1year/2years/5years).

- **`deepr agentic research`**: Multi-round research with autonomous planning. Each round: plans approach, executes searches, reviews findings, and decides next steps. Saves state for resume capability.

- **`deepr help verbs`**: Shows all commands organized by intent (research, learn, make, expert, team) to help you find the right command for your goal.

### Expert System

```bash
# Create expert from documents
deepr expert make "Azure Expert" --files "./docs/*.md"

# Create expert with autonomous learning
deepr expert make "FDA Regulations" --files "docs/*.pdf" --learn --budget 10

# List experts
deepr expert list

# Chat with expert
deepr expert chat "Azure Expert"

# Chat with autonomous research capability
deepr expert chat "Azure Expert" --agentic --budget 5

# Get expert details
deepr expert info "Azure Expert"

# Manually add knowledge to expert
deepr expert learn "Azure Expert" "Azure AI Agent Service 2026"

# Fill knowledge gaps proactively
deepr expert fill-gaps "Azure Expert" --budget 5 --top 3

# Export expert for sharing/backup
deepr expert export "Azure Expert" --output ./exports/

# Import expert from corpus
deepr expert import "New Azure Expert" --corpus ./exports/azure_expert/
```

### Job Management

```bash
# List all jobs
deepr jobs list

# Check job status
deepr jobs status <job-id>

# Get completed result
deepr jobs get <job-id>

# Cancel running job
deepr jobs cancel <job-id>
```

### Diagnostics

```bash
# Check configuration and connectivity
deepr doctor

# Skip connectivity tests
deepr doctor --skip-connectivity

# View cost analytics
deepr cost summary
deepr analytics report
```

---

## Core Concepts

### The Learning Workflow

```
Plan - Search - Analyze - Synthesize - Publish
```

Each phase builds on the previous, creating a comprehensive understanding rather than isolated facts.

### Knowledge Artifacts

Research produces versioned markdown files with:
- Comprehensive analysis
- Inline citations
- Source attribution
- Metadata (cost, model, provider)
- Reproducible results

Stored in `reports/[job-id]/` with human-readable directory names.

### Budget Protection

Multi-layer budget controls prevent runaway costs:
- Per-operation limits: $5 default, $10 hard cap
- Daily limits: $25 default, $50 hard cap
- Monthly limits: $200 default, $500 hard cap
- Session-level budgets (expert chat)
- CLI validation warns for budgets over $10, requires confirmation over $25

**Pause/Resume for Long-Running Operations:**

When autonomous learning hits daily or monthly limits, it pauses gracefully instead of killing the process:
- Progress is automatically saved (completed topics, remaining work)
- Resume the next day with `deepr expert resume "Expert Name"`
- No work is lost - picks up exactly where it left off

```bash
# If learning pauses due to daily limit:
deepr expert resume "AWS Expert"

# Resume with a different budget:
deepr expert resume "AWS Expert" --budget 10
```

See [docs/specifications/ARCHITECTURE.md](docs/specifications/ARCHITECTURE.md) for technical details.

---

## Cost Guidance

Estimated costs with reasoning models:

| Depth | Cost | Time | Output |
|-------|------|------|--------|
| Quick insight | $1-$2 | 5-10 min | Focused summary with citations |
| Comprehensive | $2-$5 | 15-30 min | Detailed structured report |
| Multi-phase | $5-$15 | 45-90 min | Context-linked analysis |
| Expert creation | $10-$20 | 1-2 hours | Complete knowledge artifact |

Actual costs vary by provider, model, prompt complexity, and context size.

---

## Writing Better Prompts

Be specific. State the decision you need to make, the scope, and any constraints.

**Vague:**
```bash
deepr research "healthcare regulations"
```

**Better:**
```bash
deepr research "Compare HIPAA, HITECH, and state privacy laws for telehealth in CA, TX, NY. Focus on consent, data retention, breach notification. Include compliance checklist."
```

See [docs/EXAMPLES.md](docs/EXAMPLES.md) for more prompt examples and best practices.

---

## Documentation

**Getting Started:**
- [QUICK_START.md](docs/QUICK_START.md) - 5-minute setup guide

**Core Guides:**
- [EXAMPLES.md](docs/EXAMPLES.md) - Detailed real-world use cases
- [ROADMAP.md](ROADMAP.md#priority-25-agentic-expert-system-capability-extension) - Creating and using domain experts
- [ROADMAP.md](ROADMAP.md#structured-learning-approach) - Structured learning strategies

**Technical:**
- [ARCHITECTURE.md](docs/specifications/ARCHITECTURE.md) - Technical architecture
- [ROADMAP.md](ROADMAP.md#model-strategy) - Choosing the right model
- [mcp/README.md](mcp/README.md) - Model Context Protocol integration

**Project:**
- [ROADMAP.md](ROADMAP.md) - Development roadmap and future vision

---

## Project Structure

```
deepr/
├── deepr/              # Core package
│   ├── cli/            # Command-line interface
│   ├── core/           # Research orchestration
│   ├── experts/        # Expert system
│   ├── providers/      # AI provider integrations
│   ├── mcp/            # Model Context Protocol server
│   └── utils/          # Utilities (scraping, etc.)
├── data/               # Local data
│   └── experts/        # Expert profiles and knowledge
├── reports/            # Research outputs
├── docs/               # Documentation
└── tests/              # Test suite
```

See [docs/specifications/ARCHITECTURE.md](docs/specifications/ARCHITECTURE.md) for detailed component documentation.

---

## Interfaces

**Deepr is CLI-first.** The terminal interface is the primary way to use Deepr and gets the most attention.

- **CLI** - Primary interface with full feature set
- **Web UI** - Experimental local interface (`python -m deepr.api.app`)
- **MCP Server** - Experimental AI agent integration

---

## Security

Deepr implements multiple security layers:

- **Input Validation**: Path traversal protection, file size/type limits, prompt length limits
- **SSRF Protection**: Blocks requests to private IPs and localhost
- **API Key Security**: Environment variables only, automatic log redaction
- **Budget Controls**: Multi-layer cost limits prevent runaway spending
- **No Shell Injection**: All subprocess calls use safe argument lists

**Best Practices:**
- Start with small budgets (`deepr budget set 5`)
- Use pre-paid credits with auto-reload OFF
- Only upload files you trust
- Review [docs/specifications/SECURITY.md](docs/specifications/SECURITY.md) for complete guidance

**Report Security Issues:** security@deepr.dev

---

## Contributing

High-value areas:
- Context chaining logic
- Synthesis prompts
- Cost optimization
- Provider integrations

Most impactful work is on intelligence layer, not infrastructure.

---

## Vision

Deepr started as an experiment in making deep research accessible and repeatable. The goal is to turn research queries into structured, cited knowledge that can be built upon over time.

Current focus areas:
- Domain experts that can answer questions from uploaded documents
- Research workflows that chain multiple queries together
- Integration with AI agents via MCP

This is a learning project exploring how to build useful research automation. It's not production-ready enterprise software.

See [ROADMAP.md](ROADMAP.md) for development priorities and technical details.

---

## License

MIT License. See [LICENSE](LICENSE).

---

## About

Deepr is a research automation tool by **Nick Seal**.

What started as a weekend experiment has grown into a system for automating research workflows and building document-based experts. The project explores practical approaches to research automation and knowledge management.

Built with transparency. Actively evolving. Feedback welcome at [GitHub Issues](https://github.com/blisspixel/deepr/issues).

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
