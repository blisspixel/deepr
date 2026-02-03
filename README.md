# Deepr

![Tests](https://img.shields.io/badge/tests-3000%2B%20passing-green)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)

Deep research from your terminal. The same deep research agents behind ChatGPT and Gemini, but scriptable, automatable, and integrated with your tools.

```bash
deepr research "PostgreSQL connection pooling strategies for high-traffic applications"
```

Uses OpenAI (o3-deep-research, o4-mini-deep-research) and Google Gemini (Deep Research Agent) APIs to produce structured, cited reports. Unlike the web UIs, Deepr runs from the command line -- so you can script it, pipe it, cron it, or call it from your AI agents via MCP.

## Why Deepr?

ChatGPT and Gemini have deep research built in. Deepr wraps the same underlying APIs and adds:

- **Automation** - Run research from scripts, cron jobs, CI pipelines. No browser required.
- **Domain experts** - Build persistent experts from your documents that answer questions, track knowledge gaps, and research autonomously to fill them.
- **MCP integration** - Your AI agents (Claude, Cursor, VS Code) can invoke deep research as a tool.
- **Multi-provider** - Same interface across OpenAI, Gemini, Grok, and Anthropic. Switch without changing code.
- **Cost controls** - Per-job budgets, daily limits, cost tracking. Pay for what you use.
- **Local storage** - Reports saved as markdown files you own.

If you just need occasional research, use ChatGPT. If you need to automate research workflows, build document-based experts, or integrate with AI agents, Deepr is the tool.

## Installation

```bash
pip install -e .                        # Core CLI (minimal dependencies)
cp .env.example .env                    # Add OPENAI_API_KEY=sk-...
deepr doctor && deepr budget set 5      # Verify setup, set $5 budget
```

Optional extras for additional features:

```bash
pip install -e ".[web]"                 # Web UI and MCP server
pip install -e ".[azure]"               # Azure cloud deployment
pip install -e ".[docs]"                # Document processing for experts
pip install -e ".[full]"                # All features
pip install -e ".[dev]"                 # Development and testing
```

## Start Here

Most users should start with these three commands:

```bash
deepr research "Your question here"     # Run a research job (~$1-2)
deepr costs show                        # Check what you spent
deepr expert make "Topic Expert" --files docs/*.md  # Create an expert from docs
```

That's the core loop. Everything else (MCP, cloud deploy, multi-provider routing) is optional.

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

Works across OpenAI (GPT-5.2, o3-deep-research, o4-mini-deep-research), Google Gemini (2.5 Flash, 3 Pro, Deep Research Agent), xAI Grok (4, 4 Fast), Anthropic Claude (Opus 4.5, Sonnet 4.5, Haiku 4.5), and Azure OpenAI. OpenAI and Gemini support native async deep research; Anthropic uses Extended Thinking + tool orchestration for research capability. Automatically routes tasks to the best model for the job. Auto-fallback retries on provider failures with circuit breakers.

## Stability

**Production-ready:** Core research commands (`research`, `check`, `learn`), cost controls, expert creation/chat, CLI output modes, OpenAI and Gemini providers, local SQLite storage.

**Experimental:** MCP server (functional but MCP spec is maturing), agentic expert chat (`--agentic`), auto-fallback circuit breakers, cloud deployment templates, Grok provider.

**Model pricing note:** AI model pricing changes frequently. The costs in this README are estimates as of February 2026. Always check provider pricing pages before large jobs. The model registry ([`deepr/providers/registry.py`](deepr/providers/registry.py)) is the single source of truth for model info.

See [ROADMAP.md](ROADMAP.md) for detailed status.

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

Deepr includes input validation, SSRF protection, API key redaction in logs, budget controls, and optional Docker isolation. CI runs lint (ruff) and 3000+ unit tests on every push via GitHub Actions. Pre-commit hooks enforce formatting with ruff.

**Verify the claims:**
- SSRF protection: [`deepr/utils/security.py`](deepr/utils/security.py) - blocks internal IPs, validates DNS
- Budget controls: [`deepr/experts/cost_safety.py`](deepr/experts/cost_safety.py) - circuit breakers, session limits
- Path traversal: [`deepr/utils/security.py`](deepr/utils/security.py) - `validate_path()` sandboxes file operations
- Provider routing: [`deepr/observability/provider_router.py`](deepr/observability/provider_router.py) - scoring, fallback
- Run tests yourself: `pytest tests/ -v` (3000+ tests, ~2 min)

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for threat model and implementation details. This software is provided as-is under the MIT License -- use at your own risk.

Report security issues: nick@pueo.io

## About

Built by **Nick Seal** ([nick@pueo.io](mailto:nick@pueo.io)). Started as a weekend experiment with OpenAI's deep research API and grew into a provider-agnostic system for automating research workflows, building document-based experts, and integrating with AI agents.

Feedback and contributions welcome at [GitHub Issues](https://github.com/blisspixel/deepr/issues).

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
