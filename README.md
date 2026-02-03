# Deepr

![Tests](https://img.shields.io/badge/tests-2820%2B%20passing-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)

Deep research from your terminal. Submit a question, get back a cited report in minutes. Build domain experts from your documents. Expose it all to AI agents via MCP.

```bash
deepr research "PostgreSQL connection pooling strategies for high-traffic applications"
```

Uses deep research agents from OpenAI (o3-deep-research, o4-mini-deep-research) and Google Gemini (Deep Research Agent) to produce structured, cited reports -- the same reasoning behind ChatGPT and Gemini deep research, accessible as a CLI tool you can script, automate, and build on.

## Installation

```bash
pip install -e .                        # Python 3.9+
cp .env.example .env                    # Add OPENAI_API_KEY=sk-...
deepr doctor && deepr budget set 5      # Verify setup, set $5 budget
```

See [docs/QUICK_START.md](docs/QUICK_START.md) for a guided setup.

## Features

### Deep Research via CLI

Submit research queries that use deep research agents (OpenAI Responses API, Gemini Interactions API) to search the web, synthesize sources, and produce structured reports with citations. Results saved locally as markdown. Supports file uploads, vector stores, and multi-phase campaigns.

```bash
deepr research "How do top fintech companies handle PCI compliance at scale?"
deepr check "Kubernetes 1.28 deprecated PodSecurityPolicy"
deepr learn "Kubernetes networking" --phases 3
deepr team "Should we build vs. buy our data platform?"
deepr make strategy "Launch a SaaS product in healthcare" --perspective investor
```

### Domain Experts

Create experts from your documents that answer questions using vector search. When an expert hits a knowledge gap, it can trigger its own research to fill it. Experts form beliefs with confidence levels, track what they don't know, and learn autonomously within budget limits. Export and share them.

```bash
deepr expert make "Supply Chain Expert" --files docs/*.md --learn --budget 10
deepr expert chat "Supply Chain Expert" --agentic --budget 5
deepr expert fill-gaps "Supply Chain Expert" --budget 5 --top 3
```

See [docs/EXPERTS.md](docs/EXPERTS.md) for details.

### MCP Integration

Exposes Deepr to AI agents via Model Context Protocol. Works with OpenClaw, Claude Desktop, Cursor, VS Code, and Zed.

Agents can submit and monitor research jobs, query domain experts, discover tools dynamically, subscribe to progress, and handle budget decisions. SQLite persistence, SSRF protection, Docker support.

See [mcp/README.md](mcp/README.md) for setup and [skills/deepr-research/](skills/deepr-research/) for the agent skill.

### Multi-Provider Routing

Works across OpenAI (GPT-5.2, o3-deep-research, o4-mini-deep-research), Google Gemini (2.5 Flash, 3 Pro, Deep Research Agent), xAI Grok (4, 4 Fast), and Azure OpenAI. Both OpenAI and Gemini support native async deep research via the same provider-agnostic interface. Automatically routes tasks to the best model for the job. Auto-fallback retries on provider failures with circuit breakers.

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

## Documentation

| Guide | Description |
|-------|-------------|
| [QUICK_START](docs/QUICK_START.md) | Installation and first research job |
| [FEATURES](docs/FEATURES.md) | Complete command reference |
| [EXPERTS](docs/EXPERTS.md) | Domain expert system |
| [MODELS](docs/MODELS.md) | Provider comparison and model selection |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Technical architecture, security, budget protection |
| [ROADMAP](ROADMAP.md) | Development priorities |
| [MCP](mcp/README.md) | MCP server setup and agent integration |

Model and pricing information current as of February 2026.

## Security

Deepr includes input validation, SSRF protection, API key redaction in logs, budget controls, and optional Docker isolation. See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for details. This software is provided as-is under the MIT License — use at your own risk.

Report security issues: nick@pueo.io

## About

Built by **Nick Seal** ([nick@pueo.io](mailto:nick@pueo.io)). Started as a weekend experiment with OpenAI's deep research API and grew into a provider-agnostic system for automating research workflows, building document-based experts, and integrating with AI agents.

Feedback and contributions welcome at [GitHub Issues](https://github.com/blisspixel/deepr/issues).

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
