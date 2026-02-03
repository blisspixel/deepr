# Deepr

![Tests](https://img.shields.io/badge/tests-3000%2B%20passing-green)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)

**The same deep research agents behind ChatGPT and Gemini — but scriptable.**

```bash
deepr research "PostgreSQL connection pooling strategies for high-traffic applications"
```

ChatGPT and Gemini have powerful deep research, but it's trapped in a chat window. You can't script it, schedule it, or call it from your AI agents. Deepr fixes that.

## What You Can Do

- **Schedule overnight research** — Set up a cron job, wake up to a structured report with citations
- **Batch-process queries** — Run 50 research jobs overnight for competitive analysis, market research, or documentation
- **Give your AI agents research superpowers** — Claude, Cursor, and VS Code can call deep research mid-task via MCP
- **Build experts from your docs** — Upload your documents, create an expert that knows what it doesn't know and researches to fill gaps
- **Switch providers without changing code** — Same interface across OpenAI, Gemini, Grok, and Anthropic

## Why Deepr?

| If you need... | Use |
|----------------|-----|
| Occasional research | ChatGPT or Gemini web UI |
| Automated research workflows | **Deepr** |
| AI agents that can research | **Deepr** (via MCP) |
| Document-based experts that learn | **Deepr** |

Deepr wraps the same underlying APIs (OpenAI's o3/o4-mini-deep-research, Gemini's Deep Research Agent) and adds:

- **Automation** — Run from scripts, cron jobs, CI pipelines. No browser required.
- **Domain experts** — Build persistent experts from your documents that answer questions, recognize knowledge gaps, and research autonomously to fill them.
- **MCP integration** — Your AI agents (Claude Desktop, Cursor, VS Code, Zed) can invoke deep research as a tool.
- **Multi-provider** — Same interface across OpenAI, Gemini, Grok, and Anthropic. Auto-fallback on failures.
- **Cost controls** — Per-job budgets, daily limits, cost tracking. Never get surprised by a bill.
- **Local storage** — Reports saved as markdown files you own. No vendor lock-in.

## Quick Start

```bash
pip install -e .                        # Install
cp .env.example .env                    # Add OPENAI_API_KEY=sk-...
deepr doctor && deepr budget set 5      # Verify setup, set $5 budget
deepr research "Your question here"     # Run your first research job (~$1-2)
```

That's it. Results saved to `reports/` as markdown with citations.

Optional extras:

```bash
pip install -e ".[web]"                 # Web UI and MCP server
pip install -e ".[docs]"                # Document processing for experts
pip install -e ".[full]"                # All features
```

See [docs/QUICK_START.md](docs/QUICK_START.md) for a guided setup.

## Features

### Deep Research via CLI

Submit research queries that use the same deep research agents as ChatGPT and Gemini. They search the web, synthesize sources, and produce structured reports with citations. Results saved locally as markdown.

```bash
deepr research "How do top fintech companies handle PCI compliance at scale?"
deepr check "Kubernetes 1.28 deprecated PodSecurityPolicy"
deepr learn "Kubernetes networking" --phases 3
deepr team "Should we build vs. buy our data platform?"
deepr make strategy "Launch a SaaS product in healthcare" --perspective investor
```

### Domain Experts (The Interesting Part)

This is where Deepr goes beyond simple API wrappers.

Traditional RAG: Upload docs → query → get answer. Static. Never learns.

Deepr experts: Upload docs → expert recognizes what it *doesn't* know → triggers research to fill gaps → integrates new knowledge permanently.

```bash
# Create an expert from your documents
deepr expert make "Supply Chain Expert" --files docs/*.md

# Chat with it — when it hits a knowledge gap, it researches
deepr expert chat "Supply Chain Expert" --agentic --budget 5

# Proactively fill knowledge gaps
deepr expert fill-gaps "Supply Chain Expert" --budget 5 --top 3
```

Experts form beliefs with confidence levels, track what they don't know, and learn autonomously within budget limits. Export and share them.

See [docs/EXPERTS.md](docs/EXPERTS.md) for details.

### MCP Integration (For AI Agent Users)

If you use Claude Desktop, Cursor, VS Code, or Zed — your AI agents can call Deepr as a tool via Model Context Protocol.

**Example workflow:** You're coding in Cursor, ask about a library, and your agent realizes it needs current information. It calls `deepr research`, waits for results, and continues with accurate, cited information.

Agents can submit and monitor research jobs, query domain experts, subscribe to progress, and handle budget decisions. SQLite persistence, SSRF protection, Docker support.

See [mcp/README.md](mcp/README.md) for setup.

### Multi-Provider Support

Works across OpenAI, Google Gemini, xAI Grok, Anthropic Claude, and Azure OpenAI. OpenAI and Gemini have native async deep research APIs; Anthropic uses Extended Thinking + tool orchestration. Deepr automatically routes tasks to the best model for the job and retries on failures.

| Provider | Deep Research | Best For |
|----------|---------------|----------|
| OpenAI | o3/o4-mini-deep-research | Comprehensive research |
| Gemini | Deep Research Agent | Large context, Google Search |
| Grok | Via orchestration | Cost-effective general tasks |
| Anthropic | Extended Thinking | Complex reasoning, coding |

## What's Stable vs Experimental

**Production-ready:** Core research commands (`research`, `check`, `learn`), cost controls, expert creation/chat, OpenAI and Gemini providers, local SQLite storage. 3000+ tests.

**Experimental:** MCP server (works, but MCP spec is still maturing), agentic expert chat (`--agentic`), auto-fallback circuit breakers, cloud deployment templates.

See [ROADMAP.md](ROADMAP.md) for detailed status.

## Cost Controls

Research costs real money ($1-$20 per run depending on depth). Deepr has multi-layer budget protection so you don't get surprised:

- Per-operation, daily, and monthly limits
- Pre-submission cost estimates
- Pause/resume at budget boundaries
- Cost tracking and anomaly detection

```bash
deepr budget set 5                                  # Set $5 limit
deepr cost estimate "Your prompt"                   # Estimate before running
deepr costs show                                    # See what you've spent
deepr costs timeline --days 14                      # Trends with anomaly detection
```

| Depth | Estimated Cost | Output |
|-------|---------------|--------|
| Quick insight | $1-$2 | Focused summary with citations |
| Comprehensive | $2-$5 | Detailed structured report |
| Multi-phase | $5-$15 | Context-linked analysis |

**Tip:** Start with small budgets and use pre-paid API credits with auto-reload OFF.

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

**Note:** Model pricing changes frequently. Costs in this README are estimates as of February 2026. The model registry ([`deepr/providers/registry.py`](deepr/providers/registry.py)) is the single source of truth.

## Security

Input validation, SSRF protection, API key redaction, budget controls, optional Docker isolation. CI runs lint (ruff) and 3000+ unit tests on every push.

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for threat model and implementation details.

Report security issues: nick@pueo.io

## About

Built by **Nick Seal** ([nick@pueo.io](mailto:nick@pueo.io)). Started as a weekend experiment with OpenAI's deep research API and grew into a provider-agnostic system for automating research workflows.

Feedback and contributions welcome at [GitHub Issues](https://github.com/blisspixel/deepr/issues).

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
