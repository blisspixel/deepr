# Deepr

[![Tests](https://img.shields.io/badge/tests-3000%2B%20passing-brightgreen)](https://github.com/blisspixel/deepr/actions)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue)](https://github.com/blisspixel/deepr/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.7-orange)](ROADMAP.md)

**Deep research agents for automation — the same technology behind ChatGPT and Gemini, but scriptable.**

```bash
deepr research "What are the security implications of AWS Bedrock vs Azure OpenAI for enterprise RAG?"
```

ChatGPT and Gemini have powerful deep research, but it's trapped in a chat window. You can't script it, schedule it, or call it from your AI agents. Deepr fixes that.

## What You Can Do

- **Give your AI agents real research capabilities** — Claude Code, Cursor, VS Code can call deep research mid-task. Not hallucinations — actual research with citations. Agents can query experts, trigger research to fill knowledge gaps, and continue with accurate information.
- **Build institutional knowledge that doesn't walk out the door** — Create experts from your architecture docs, runbooks, and post-mortems. They learn, improve, and stay when people leave.
- **Weekly competitive intelligence** — Schedule research on competitor announcements, market trends, or regulatory changes. Wake up Monday with a digest.
- **Due diligence at scale** — Researching an acquisition target? Run 30 queries overnight covering their tech stack, patents, key hires, and market position.
- **Switch providers without changing code** — Same interface across OpenAI, Gemini, Grok, and Anthropic

## Why Deepr?

| If you need... | Use |
|----------------|-----|
| Occasional research | ChatGPT or Gemini web UI |
| Automated research on a schedule | **Deepr** |
| AI agents that can research and learn mid-task | **Deepr** (MCP + Skills) |
| Institutional knowledge that learns and persists | **Deepr** |
| Due diligence or competitive intel at scale | **Deepr** |

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
# Architecture decisions
deepr research "Kubernetes vs ECS Fargate for multi-tenant SaaS: cost, complexity, and scaling tradeoffs"

# Compliance research
deepr check "Does SOC 2 Type II require encryption at rest for all PII?"

# Technology evaluation
deepr learn "Service mesh options for hybrid cloud" --phases 3

# Strategic decisions
deepr team "Should we build an internal ML platform or use AWS SageMaker?"

# Vendor analysis
deepr make strategy "Migrate from Snowflake to Databricks" --perspective cost
```

### Domain Experts (The Interesting Part)

This is where Deepr goes beyond "ChatGPT but CLI."

**The problem:** Your best architect leaves. Their knowledge — scattered across Confluence, Slack threads, and their head — walks out the door. Or: AWS releases 47 new services this year. Your team can't keep up.

**Traditional RAG:** Upload docs → query → get answer. Static. Never learns. Never knows what it's missing.

**Deepr experts are different:**
- **Self-aware** — They recognize when they don't know something instead of hallucinating
- **Self-improving** — They can trigger research to fill their own knowledge gaps
- **Persistent** — New knowledge integrates permanently, not just for one session
- **Portable** — Export an expert and share it across your organization

```bash
# Create an expert from your architecture docs, runbooks, ADRs
deepr expert make "Platform Team Expert" --files docs/*.md confluence-export/*.html

# Chat with it — when it hits a knowledge gap, it researches
deepr expert chat "Platform Team Expert" --agentic --budget 5

# Proactively fill knowledge gaps (e.g., new AWS services)
deepr expert fill-gaps "Platform Team Expert" --budget 5 --top 3

# Export for the whole team
deepr expert export "Platform Team Expert" --output ./team-experts/
```

**Example:** You create a "Cloud Architecture" expert from your internal docs. Someone asks about AWS Bedrock Guardrails (released last month). Instead of hallucinating, the expert says "I don't have information on that" and (in agentic mode) researches it, then integrates the findings permanently. Next time anyone asks, it knows.

This is institutional knowledge that learns, improves, and doesn't quit.

See [docs/EXPERTS.md](docs/EXPERTS.md) for details.

### MCP + Skills (Research Infrastructure for AI Agents)

This is where Deepr becomes more than a CLI — it's **research infrastructure for AI agents**.

If you use Claude Code, Cursor, VS Code, or Zed, your AI agents can call Deepr as a tool via MCP. But with the included **skill** (`skills/deepr-research/`), agents learn *how* to use research intelligently:

**The workflow:**
```
You (in Cursor): "Design a multi-region failover system for DynamoDB"

Claude Code:
  1. Realizes it needs current AWS documentation (not 2023 training data)
  2. Calls deepr_query_expert("Cloud Architecture Expert", "DynamoDB multi-region patterns")
  3. Expert identifies knowledge gap: "I don't have info on DynamoDB Global Tables v2"
  4. Agent triggers deepr_agentic_research to fill the gap
  5. Expert learns the new information permanently
  6. Claude continues with accurate, cited architecture recommendations
```

**What the skill teaches agents:**
- When to use quick search vs deep research vs expert consultation
- How to chain: Research → Plan → Query Expert → Fill Gaps → Continue
- Cost awareness (confirm before expensive operations)
- Resource subscriptions (70% token savings vs polling)
- Sandboxed execution (heavy research runs isolated, clean results returned)

**The result:** Your AI coding assistant can do real research mid-task — not just hallucinate or use stale training data. And the experts it consults get smarter over time.

10 MCP tools, resource subscriptions, prompt templates, budget elicitation. See [mcp/README.md](mcp/README.md) for setup.

### Web Dashboard

A local research management interface for when you want a visual view of your research operations.

```bash
pip install -e ".[web]"
python -m deepr.web.app
# Open http://localhost:5000
```

**Features:**
- **Dashboard** - Quick research submission, active jobs, spending summary
- **Job Queue** - Monitor all jobs with real-time status updates, cancel running jobs
- **Results Library** - Search and browse completed research, grid/list views
- **Cost Analytics** - Daily/monthly spending trends, budget alerts, per-model breakdown
- **Settings** - API keys, budget limits, default model preferences

**For team deployment**, the dashboard can be containerized and deployed to cloud infrastructure. See [deploy/README.md](deploy/README.md) for AWS, Azure, and GCP templates. Authentication and multi-user features are on the roadmap.

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

**Experimental:** MCP server (works, but MCP spec is still maturing), web dashboard (functional for local use), agentic expert chat (`--agentic`), auto-fallback circuit breakers, cloud deployment templates.

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
| [Quick Start](docs/QUICK_START.md) | Installation and first research job |
| [Features](docs/FEATURES.md) | Complete command reference |
| [Experts](docs/EXPERTS.md) | Domain expert system |
| [Models](docs/MODELS.md) | Provider comparison and model selection |
| [Architecture](docs/ARCHITECTURE.md) | Technical architecture, security, budget protection |
| [Examples](docs/EXAMPLES.md) | Real-world usage examples |
| [MCP Integration](mcp/README.md) | MCP server setup and agent integration |
| [Deployment](deploy/README.md) | Cloud deployment (AWS, Azure, GCP) |
| [Changelog](docs/CHANGELOG.md) | Release history and migration notes |
| [Roadmap](ROADMAP.md) | Development priorities and future plans |

> **Note:** Model pricing changes frequently. Costs in this README are estimates as of February 2026. The [model registry](deepr/providers/registry.py) is the source of truth for current pricing.

## Requirements

- Python 3.9+
- API key for at least one provider (OpenAI, Gemini, Anthropic, Grok, or Azure)
- Optional: Node.js 18+ for web dashboard development

## Security

- Input validation and sanitization on all user inputs
- SSRF protection for web scraping operations
- API key redaction in logs and error messages
- Budget controls to prevent runaway costs
- Optional Docker isolation for untrusted workloads

CI runs ruff (lint + format) and 3000+ unit tests on every push. See [Architecture](docs/ARCHITECTURE.md) for threat model and security implementation details.

**Report security vulnerabilities:** [nick@pueo.io](mailto:nick@pueo.io) (please do not open public issues for security bugs)

## Contributing

Contributions are welcome. High-impact areas:

- **Provider integrations** — New providers or improvements to existing ones
- **Cost optimization** — Better token estimation, caching strategies
- **Expert system** — Knowledge synthesis, gap detection algorithms
- **CLI UX** — Interactive mode, progress indicators, output formatting

Before submitting a PR:

1. Run `ruff check . && ruff format .` to lint and format
2. Run `pytest tests/` to verify tests pass
3. Add tests for new functionality

See [ROADMAP.md](ROADMAP.md) for planned work and priorities.

## License

[MIT License](LICENSE) — use freely, attribution appreciated.

---

Built by [Nick Seal](mailto:nick@pueo.io). Started as a weekend experiment with OpenAI's deep research API and grew into a provider-agnostic research automation platform.

[GitHub](https://github.com/blisspixel/deepr) · [Issues](https://github.com/blisspixel/deepr/issues) · [Discussions](https://github.com/blisspixel/deepr/discussions)
