# Deepr

![Tests](https://img.shields.io/badge/tests-2800%2B%20passing-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)

CLI tool for AI-powered research that produces cited reports, builds domain experts, and integrates with AI agents via MCP. Multi-provider support (OpenAI GPT-5.2, Gemini, Grok, Azure). Local-first. Early-stage software.

> **Cost warning:** Deep research uses reasoning models that can cost $0.50-$20 per run. Start with small budgets (`deepr budget set 5`), use pre-paid credits with auto-reload OFF, and monitor costs. This is a learning tool, not production-ready enterprise software.

## Installation

**Prerequisites:** Python 3.9+

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr
pip install -e .
```

Configure at least one provider:

```bash
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk-...
```

Verify and set budget:

```bash
deepr doctor
deepr budget set 5
```

See [docs/QUICK_START.md](docs/QUICK_START.md) for a guided setup.

## Quick Examples

```bash
# Research (auto-detects mode)
deepr research "PostgreSQL connection pooling strategies for high-traffic applications"

# Fact verification
deepr check "Kubernetes 1.28 deprecated PodSecurityPolicy"

# Generate documentation
deepr make docs --files "./src/*.py" --format markdown

# Strategic analysis
deepr make strategy "Launch a SaaS product in healthcare" --perspective investor

# Multi-phase learning
deepr learn "Kubernetes networking" --phases 3

# Multi-perspective analysis
deepr team "Should we build vs. buy our data platform?"

# Create domain expert from documents
deepr expert make "AWS Architect" --files "./docs/*.md" --learn --budget 10

# Chat with expert (with agentic research)
deepr expert chat "AWS Architect" --agentic --budget 5

# Agentic research with Plan-Execute-Review cycles
deepr agentic research "Best practices for microservices observability" --rounds 3 --budget 10
```

See [docs/EXAMPLES.md](docs/EXAMPLES.md) for detailed use cases and [docs/FEATURES.md](docs/FEATURES.md) for the complete command reference.

## Key Features

### Multi-Provider Orchestration

Works across OpenAI GPT-5.2, Google Gemini, xAI Grok, Azure OpenAI. Automatically routes tasks to the best model for the job. Auto-fallback retries on provider failures.

### Domain Experts (Experimental)

Create experts from documents that answer questions using vector search. Experts can trigger research for knowledge gaps, form beliefs with confidence levels, and learn autonomously.

```bash
deepr expert make "Supply Chain Expert" --learn --budget 10 --topics 10
deepr expert chat "Supply Chain Expert" --agentic --budget 5
deepr expert fill-gaps "Supply Chain Expert" --budget 5 --top 3
```

Features: vector search, knowledge synthesis, belief formation, gap awareness, pause/resume at budget limits, export/import for sharing. See [docs/EXPERTS.md](docs/EXPERTS.md) for details.

### MCP Integration

Exposes Deepr to AI agents via Model Context Protocol. Works with OpenClaw, Claude Desktop, Cursor, VS Code, and Zed.

What agents can do: submit and monitor research jobs, query domain experts, discover tools dynamically, subscribe to progress, handle budget decisions, cancel jobs.

Infrastructure: SQLite persistence, SSRF protection, structured error responses, trace ID propagation, lazy loading, Docker support.

See [mcp/README.md](mcp/README.md) for setup and [skills/deepr-research/](skills/deepr-research/) for the agent skill.

### Cost Tracking

```bash
deepr costs show                                    # Summary
deepr costs timeline --days 14                      # Trends with anomaly detection
deepr costs breakdown --by provider --period week   # By provider, model, or operation
deepr costs expert "Expert Name"                    # Per-expert breakdown
deepr cost estimate "Your prompt"                   # Pre-submission estimate
```

### Observability

```bash
deepr research "Topic" --explain     # Show model/cost reasoning
deepr research "Topic" --timeline    # Phase-by-phase timing and costs
deepr research "Topic" --full-trace  # Dump complete trace JSON
```

## Cost Guidance

| Depth | Estimated Cost | Output |
|-------|---------------|--------|
| Quick insight | $1-$2 | Focused summary with citations |
| Comprehensive | $2-$5 | Detailed structured report |
| Multi-phase | $5-$15 | Context-linked analysis |
| Expert creation | $10-$20 | Complete knowledge artifact |

Actual costs vary by provider, model, prompt complexity, and context size. Multi-layer budget controls prevent runaway costs (per-operation, daily, and monthly limits with alerts). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#cost-safety) for details.

## Project Structure

```
deepr/
├── deepr/                  # Core package
│   ├── cli/                # Command-line interface
│   ├── core/               # Research orchestration
│   ├── experts/            # Expert system
│   ├── providers/          # AI provider integrations
│   ├── mcp/                # Model Context Protocol server
│   ├── tools/              # Backend protocols (search, browser)
│   └── utils/              # Utilities (scraping, etc.)
├── skills/                 # Agent skill packages
├── mcp/                    # Runtime config templates
├── docs/                   # Documentation
└── tests/                  # Test suite (2800+ tests)
```

## Documentation

> Model information current as of February 2026.

- [QUICK_START.md](docs/QUICK_START.md) - Setup guide
- [FEATURES.md](docs/FEATURES.md) - Complete command reference
- [EXAMPLES.md](docs/EXAMPLES.md) - Real-world use cases
- [EXPERTS.md](docs/EXPERTS.md) - Domain expert system
- [MODELS.md](docs/MODELS.md) - Model selection and providers
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Technical architecture and security
- [ROADMAP.md](ROADMAP.md) - Development priorities
- [CHANGELOG.md](docs/CHANGELOG.md) - Release history
- [mcp/README.md](mcp/README.md) - MCP integration

## Security

- Input validation with path traversal protection
- SSRF protection blocking private/internal IPs, optional domain allowlist
- API keys via environment variables only, automatic log redaction
- Multi-layer budget controls
- Docker isolation (non-root, bridge networking, resource limits)

Report security issues: security@deepr.dev

## About

Deepr is a research automation tool by **Nick Seal**.

What started as a weekend experiment has grown into a system for automating research workflows and building document-based experts. This is a learning project exploring practical approaches to research automation. It's not production-ready enterprise software.

Feedback welcome at [GitHub Issues](https://github.com/blisspixel/deepr/issues).

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
