# Deepr

![Tests](https://img.shields.io/badge/tests-2800%2B%20passing-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)

Deep research from your terminal. Submit a question, get back a cited report in minutes. Build domain experts from your documents. Expose it all to AI agents via MCP.

```bash
deepr research "PostgreSQL connection pooling strategies for high-traffic applications"
```

Uses OpenAI's deep research models (o3, o4-mini) to produce structured, cited reports — the same reasoning behind ChatGPT's deep research, accessible as a CLI tool you can script, automate, and build on.

## What You Can Do

```bash
# Deep research with cited reports
deepr research "PostgreSQL connection pooling strategies for high-traffic applications"

# Fact verification
deepr check "Kubernetes 1.28 deprecated PodSecurityPolicy"

# Build an expert from your documents, then chat with it
deepr expert make "AWS Architect" --files "./docs/*.md" --learn --budget 10
deepr expert chat "AWS Architect" --agentic --budget 5

# Multi-perspective analysis (Six Thinking Hats)
deepr team "Should we build vs. buy our data platform?"

# Generate documentation from source files
deepr make docs --files "./src/*.py" --format markdown

# Multi-phase structured learning
deepr learn "Kubernetes networking" --phases 3
```

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

## Key Features

### Deep Research via CLI

Submit research queries that use OpenAI's reasoning models to search the web, synthesize sources, and produce structured reports with citations. Results are saved locally as markdown. Supports file uploads, vector stores, and multi-phase campaigns.

### Domain Experts

Create experts from your documents that answer questions using vector search. When an expert hits a knowledge gap, it can trigger its own research to fill it. Experts form beliefs with confidence levels, track what they don't know, and learn autonomously within budget limits. Export and share them.

```bash
deepr expert make "Supply Chain Expert" --learn --budget 10 --topics 10
deepr expert chat "Supply Chain Expert" --agentic --budget 5
deepr expert fill-gaps "Supply Chain Expert" --budget 5 --top 3
```

See [docs/EXPERTS.md](docs/EXPERTS.md) for details.

### MCP Integration

Exposes Deepr to AI agents via Model Context Protocol. Works with OpenClaw, Claude Desktop, Cursor, VS Code, and Zed.

Agents can submit and monitor research jobs, query domain experts, discover tools dynamically, subscribe to progress, and handle budget decisions. SQLite persistence, SSRF protection, Docker support.

See [mcp/README.md](mcp/README.md) for setup and [skills/deepr-research/](skills/deepr-research/) for the agent skill.

### Multi-Provider Routing

Works across OpenAI GPT-5.2, Google Gemini, xAI Grok, and Azure OpenAI. Automatically routes tasks to the best model for the job. Auto-fallback retries on provider failures with circuit breakers.

### Cost Controls

Research costs real money ($1-$20 per run depending on depth). Deepr has multi-layer budget protection: per-operation, daily, and monthly limits with alerts. Pause/resume at budget boundaries.

```bash
deepr costs show                                    # Summary
deepr costs timeline --days 14                      # Trends with anomaly detection
deepr costs breakdown --by provider --period week   # By provider, model, or operation
deepr cost estimate "Your prompt"                   # Pre-submission estimate
```

| Depth | Estimated Cost | Output |
|-------|---------------|--------|
| Quick insight | $1-$2 | Focused summary with citations |
| Comprehensive | $2-$5 | Detailed structured report |
| Multi-phase | $5-$15 | Context-linked analysis |
| Expert creation | $10-$20 | Complete knowledge artifact |

Start with small budgets (`deepr budget set 5`) and use pre-paid API credits with auto-reload OFF.

### Observability

```bash
deepr research "Topic" --explain     # Show model/cost reasoning
deepr research "Topic" --timeline    # Phase-by-phase timing and costs
deepr research "Topic" --full-trace  # Dump complete trace JSON
```

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

- [QUICK_START.md](docs/QUICK_START.md) - Setup guide
- [FEATURES.md](docs/FEATURES.md) - Complete command reference
- [EXAMPLES.md](docs/EXAMPLES.md) - Real-world use cases
- [EXPERTS.md](docs/EXPERTS.md) - Domain expert system
- [MODELS.md](docs/MODELS.md) - Model selection and providers
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Technical architecture and security
- [ROADMAP.md](ROADMAP.md) - Development priorities
- [CHANGELOG.md](docs/CHANGELOG.md) - Release history
- [mcp/README.md](mcp/README.md) - MCP integration

> Model and pricing information current as of February 2026.

## Security

- Input validation with path traversal protection
- SSRF protection blocking private/internal IPs, optional domain allowlist
- API keys via environment variables only, automatic log redaction
- Multi-layer budget controls
- Docker isolation (non-root, bridge networking, resource limits)

Report security issues: security@deepr.dev

## About

Deepr is a research automation tool by **Nick Seal**. It started as a weekend experiment with OpenAI's deep research API and grew into a system for automating research workflows, building document-based experts, and integrating with AI agents.

Feedback welcome at [GitHub Issues](https://github.com/blisspixel/deepr/issues).

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
