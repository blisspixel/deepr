# Deepr

![Tests](https://img.shields.io/badge/tests-316%20passing-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)

**TL;DR:** CLI tool for comprehensive AI-powered research that produces cited reports, builds self-improving domain experts, and integrates with AI agents via MCP. Multi-provider support (OpenAI GPT-5, Gemini, Grok, Azure). Local-first.

**Autonomous Learning and Knowledge Infrastructure**

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

Deepr is a research operating system that turns curiosity into structured, verifiable knowledge. It coordinates AI models, data sources, and reasoning workflows to produce comprehensive, cited research artifacts.

**What it does:**
- Plans, searches, analyzes, and synthesizes information
- Produces cited, versioned markdown reports
- Builds domain experts with autonomous learning
- Integrates with AI agents via Model Context Protocol

**What makes it different:**
- Multi-provider support (OpenAI GPT-5, Gemini, Grok, Azure)
- Local-first (runs on your machine)
- Knowledge infrastructure (not just one-off queries)
- Self-improving experts (learns from conversations)

See [docs/specifications/ARCHITECTURE.md](docs/specifications/ARCHITECTURE.md) for technical details on the self-improvement loop, autonomous learning, and knowledge synthesis.

---

## Quick Examples

### Simple Research
```bash
deepr research "PostgreSQL connection pooling strategies for high-traffic applications"
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

See [docs/EXAMPLES.md](docs/EXAMPLES.md) for detailed use cases with real-world scenarios.

---

## Key Features

### Multi-Provider Orchestration

Works across OpenAI GPT-5, Google Gemini, xAI Grok, Azure OpenAI. Automatically routes tasks to the best model for the job.

```bash
deepr research "Topic" --provider grok --budget 2
```

See [docs/MODEL_SELECTION.md](docs/MODEL_SELECTION.md) for provider selection guidance.

### Domain Experts with Autonomous Learning

Create experts that learn autonomously from research and synthesize knowledge into beliefs:

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

# Export expert consciousness for sharing
deepr expert export "Supply Chain Expert" --output ./exports/

# Import expert from exported corpus
deepr expert import "New Expert Name" --corpus ./exports/supply_chain_expert/
```

Features:
- Knowledge synthesis: Expert creates a "worldview" from research, not just RAG retrieval
- Belief formation: Expert forms beliefs with confidence levels and evidence citations
- Gap awareness: Expert tracks what it doesn't know and can research to fill gaps
- Continuous learning: Expert re-synthesizes consciousness after research conversations
- Manual learning: Add knowledge on demand via topics or file uploads
- Gap filling: Proactively research high-priority knowledge gaps
- Pause/resume: Long-running learning pauses gracefully at daily/monthly limits and can be resumed
- Export/import: Package expert consciousness for sharing or backup

Status: Core implementation complete. Unit tests pass (62 tests for new features). Initial testing shows experts form beliefs and speak from synthesized understanding. This is early-stage software - more extensive real-world testing needed to validate reliability at scale. The architecture aims toward "Level 5" agentic behavior (self-improving, meta-cognitive awareness) but we're not claiming to have achieved it yet.

See [docs/EXPERT_SYSTEM.md](docs/EXPERT_SYSTEM.md) for detailed documentation.

### Structured Learning Workflow

Four types of knowledge artifacts that mirror how experts actually work:

| Type | Purpose | Model | Cost | Command |
|------|---------|-------|------|---------|
| News | Latest developments | grok-4-fast | ~$0.001 | `deepr news` |
| Docs | Fundamentals, APIs | grok-4-fast | ~$0.002 | `deepr research --scrape` |
| Research | Deep analysis | o4-mini or grok | $0.001-$0.50 | `deepr research` |
| Team | Multi-perspective | grok-4-fast | ~$0.005 | `deepr team` |

Example learning Kubernetes from fundamentals to strategic decision for ~$0.51 total.

See [docs/LEARNING_WORKFLOW.md](docs/LEARNING_WORKFLOW.md) for comprehensive learning strategies.

### MCP Integration (Experimental)

Expose Deepr to AI agents via Model Context Protocol. Allows Claude Desktop, Cursor, and other MCP-compatible agents to:
- Submit long-running research jobs
- Query domain experts
- Orchestrate multi-step research workflows

**Status:** Code complete, not yet tested with actual MCP clients.

See [docs/MCP.md](docs/MCP.md) for setup instructions and limitations.

### Web Scraping

Intelligent web scraping with fallback strategies for accessing web content when needed.

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

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.

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
- [EXPERT_SYSTEM.md](docs/EXPERT_SYSTEM.md) - Creating and using domain experts
- [LEARNING_WORKFLOW.md](docs/LEARNING_WORKFLOW.md) - Structured learning strategies

**Technical:**
- [ARCHITECTURE.md](docs/specifications/ARCHITECTURE.md) - Technical architecture
- [MODEL_SELECTION.md](docs/MODEL_SELECTION.md) - Choosing the right model
- [MCP.md](docs/MCP.md) - Model Context Protocol integration

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
- Review [SECURITY.md](SECURITY.md) for complete guidance

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

Deepr is an experiment in making deep research accessible and repeatable. The goal: turn curiosity into structured knowledge that compounds over time.

Current focus: Self-improving domain experts that learn autonomously. Research that becomes permanent knowledge. AI systems that grow smarter with each conversation.

The aspiration: Infrastructure that helps both humans and AI systems learn better.

See [ROADMAP.md](ROADMAP.md) for development priorities and future vision.

---

## License

MIT License. See [LICENSE](LICENSE).

---

## About

Deepr is a research operating system and knowledge infrastructure platform by **Nick Seal**.

What started as a weekend experiment has evolved into a comprehensive system for autonomous learning, knowledge synthesis, and self-improving domain experts. The project explores how AI systems learn, remember, and improve over time.

Built with transparency. Designed for both individual learning and as infrastructure for AI agents. Actively evolving.

Contributions and feedback welcome at [GitHub Issues](https://github.com/blisspixel/deepr/issues).

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
