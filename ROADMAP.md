# Deepr Roadmap

> Development priorities and planned features. Model/pricing notes updated through March 2026.

## Quick Links

| Document | Description |
|----------|-------------|
| [Models](docs/MODELS.md) | Provider comparison, costs, model selection |
| [Experts](docs/EXPERTS.md) | Creating and using domain experts |
| [Architecture](docs/ARCHITECTURE.md) | Technical details, security, observability |
| [Changelog](docs/CHANGELOG.md) | Release history with migration notes |
| [Vision](docs/VISION.md) | Long-term direction (v3.0+) |

---

## Architecture Layers

Deepr is organized in three layers. When contributing, it helps to know which layer you're working in:

| Layer | What lives here | Examples |
|-------|----------------|----------|
| **Kernel** — reusable agent infrastructure | Task execution, budget enforcement, provider routing, trace/decision logging | `core/`, `observability/`, `providers/`, `queue/`, `routing/` |
| **Primitives** — swappable domain modules | Web search, citation extraction, expert memory, summarization, gap detection | `experts/`, `services/`, `tools/`, `storage/` |
| **Interfaces** — user-facing surfaces | CLI for scripting and experiments, web dashboard for operations and analytics | `cli/`, `web/`, `mcp/` |

The kernel is designed to be embeddable in other agent projects. The primitives are specific to research but follow patterns (belief states, gap backlogs, refresh policies) that generalize. The interfaces are thin wrappers over the lower layers.

---

## Current Status (v2.9.1)

Multi-provider research automation with expert system, domain-specific skills, MCP integration, and observability. 4300+ tests. Pre-commit hooks with ruff.

### Stable (Production-Ready)

These features are well-tested and used regularly:

- **Core research commands**: `research`, `check`, `learn` - reliable across providers
- **Cost controls**: Budget limits, canonical cost ledger, cost tracking, `costs show/timeline/breakdown/doctor`
- **Expert creation**: `expert make`, `expert chat`, `expert export/import`
- **CLI output modes**: `--verbose`, `--json`, `--quiet`, `--explain`
- **Context discovery**: `deepr search`, `--context <id>` for reusing prior research
- **Provider support**: OpenAI (GPT-5.4, GPT-5.4-pro, GPT-5-mini, GPT-4.1, o3/o4-mini-deep-research), Gemini (3.1 Pro Preview, 3 Flash, 2.5 Flash, Deep Research Agent), Anthropic (Claude Opus/Sonnet/Haiku 4.5), Azure AI Foundry (o3-deep-research + Bing, GPT-5/5-mini, GPT-4.1/4.1-mini, GPT-4o)
- **Local storage**: SQLite persistence, markdown reports, expert profiles

### Experimental (Works but Evolving)

These features work but APIs or behavior may change:

- **Web dashboard**: Local research management UI - 12 polished pages with WebSocket push, skeleton loading, shadcn/ui components, mobile nav, accessibility
- **Expert skills**: Domain-specific capability packages with Python tools and MCP bridging. 4 built-in skills, CLI management, web API, auto-activation triggers
- **MCP server**: Functional with 18 tools, but MCP spec itself is still maturing
- **Agentic expert chat**: `--agentic` flag triggers autonomous research with slash commands, chat modes, visible reasoning, approval flows, expert council, and task planning
- **Auto-fallback**: Provider failover works, but circuit breaker tuning is ongoing
- **Cloud deployment templates**: AWS/Azure/GCP templates provided but not battle-tested at scale
- **Grok provider**: Basic support, less tested than OpenAI/Gemini
- **Anthropic provider**: Uses Extended Thinking + orchestration (no native deep research API)
- **Azure AI Foundry provider**: Agent/Thread/Run pattern with Bing grounding; 7 models (o3-deep-research, gpt-5, gpt-5-mini, gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-4o-mini)

### What Works (Full List)

- Multi-provider support (OpenAI GPT-5.4/5-mini/4.1, Gemini 3.1 Pro/Flash-Lite/2.5, Grok 4.1 Fast variants, Anthropic Claude, Azure, Azure AI Foundry)
- Deep Research via OpenAI API (o3/o4-mini-deep-research) and Gemini Interactions API (Deep Research Agent)
- Semantic commands (`research`, `learn`, `team`, `check`, `make`)
- Expert system with autonomous learning, agentic chat (streaming, 27 slash commands, 4 chat modes, visible reasoning, context compaction, approval flows, expert council, task planning, memory commands), knowledge synthesis, curriculum preview (`expert plan`), domain-specific skills, AI-generated portraits
- Expert skills system: 4 built-in skills, Python + MCP tool types, auto-activation triggers, three-tier storage
- Conversations API for browsing and resuming past chat sessions
- MCP server with 18 tools, persistence, security, multi-runtime configs
- Web dashboard (12 pages: overview, research studio, research live, results library, result detail, expert hub, expert profile, cost intelligence, models & benchmarks, trace explorer, help, settings)
- CLI trace flags (`--explain`, `--timeline`, `--full-trace`)
- Output modes (`--verbose`, `--json`, `--quiet`)
- Auto-fallback on provider failures with `--no-fallback` override
- **Auto mode** (`--auto`) for smart query routing based on complexity (10-20x cost savings)
- **Batch processing** (`--auto --batch queries.txt`) with per-query optimal routing
- Cost dashboard (`costs timeline`, `costs breakdown --period`, `costs expert`, `costs doctor`)
- Multi-layer budget protection with pause/resume
- Docker deployment option
- Cloud deployment templates (AWS, Azure, GCP)
- Pre-commit hooks (ruff lint+format, trailing whitespace, debug statement detection)
- Coverage configuration with 60% minimum threshold
- Context discovery with semantic search (`deepr search`, `--context` flag)
- Distributed tracing with MetadataEmitter, spans, cost attribution

---

## Completed Work

Completed implementation details now live in [docs/CHANGELOG.md](docs/CHANGELOG.md) by release (`v2.0` through `v2.9.1`).

Use this roadmap for active and upcoming work only; move new completed checklist items into the changelog at release time.

---

## Cloud Deployment

Serverless deployment templates for AWS, Azure, and GCP. Each uses native cloud tooling. See [deploy/README.md](deploy/README.md).

| Cloud | IaC | API | Queue | Worker | Database | Storage |
|-------|-----|-----|-------|--------|----------|---------|
| AWS | SAM/CloudFormation | Lambda | SQS | Fargate | DynamoDB | S3 |
| Azure | Bicep | Functions | Queue Storage | Container Apps | Cosmos DB | Blob Storage |
| GCP | Terraform | Cloud Functions | Pub/Sub | Cloud Run | Firestore | Cloud Storage |

All deployments include:
- API key authentication (Bearer token and X-Api-Key header)
- CORS preflight handling for browser clients
- Input validation and request sanitization
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options)
- Auto-scaling workers based on queue depth
- Secrets management (no API keys in code)
- 90-day document TTL for automatic cleanup
- Dead letter queues for failed jobs

A shared library (`deploy/shared/deepr_api_common/`) provides reusable validation, security, and response utilities across all cloud handlers.

```bash
# Quick start (AWS example)
cd deploy/aws
cp .env.example .env  # Add your API keys
sam build && sam deploy --guided
```

---

## Execution Plan (Single Source of Truth)

This is the canonical plan for remaining work. Keep each item in one place only; when completed, move it to [docs/CHANGELOG.md](docs/CHANGELOG.md).

### Planning Principles

- Prioritize research infrastructure over chat novelty.
- Preserve budgeted autonomy, auditability, and provider portability.
- Ship capabilities that improve measurable quality, cost-efficiency, and reliability.
- Keep orchestration bounded: no unbounded swarms, no opaque autonomy.

### Phase 1 (v2.10): Agentic Infrastructure Core

Goal: make Deepr more agentic in a controlled, infrastructure-first way.

- [ ] Subagent runtime contract (planner -> delegated workers -> synthesizer) with per-subagent budget and trace IDs
- [ ] Explicit handoff semantics (agent-as-tools + deterministic orchestration path)
- [ ] Bounded parallel fan-out for council/task planning with circuit-breaker safeguards
- [ ] Return artifact IDs (`job_id`, `report_id`, `expert_id`, `trace_id`) from all MCP tools
- [ ] Finish Azure Foundry parity work:
  - [ ] MODELS.md documentation
  - [ ] Live integration tests with Azure credentials
  - [ ] Deploy/test o3-deep-research + Bing grounding
  - [ ] Add Foundry model discovery and benchmark coverage

### Phase 2 (v2.10-v2.11): MCP Client Reliability

Goal: Deepr works as both MCP provider and consumer for real workflows.

- [ ] MCP client connections (stdio + SSE)
- [ ] Async durability (resume/reconnect, timeout/cancel, progress notifications)
- [ ] Parallel dispatch across MCP servers with backpressure controls
- [ ] Elicitation routing for blocked operations (CAPTCHA/paywall/credential pass-through)
- [ ] GitHub release workflow for skill distribution
- [ ] External request rate limiting + scraper sampling integration

### Phase 3 (v2.11): Routing and Evaluation Confidence

Goal: continuously validate routing quality/cost claims.

- [ ] `deepr providers models` command (model discovery UX)
- [ ] Stale-model CI checks + provider-family alerting
- [ ] Eval methodology v2:
  - [ ] citation quality, grounding, synthesis depth, temporal accuracy
  - [ ] expert-specific metrics (gap detection, integration quality, belief revision)
  - [ ] task-level cost-efficiency scoring
  - [ ] methodology versioning for run comparability
- [ ] Routing A/B mode and comparison vs single-model defaults

### Phase 4 (v2.11-v2.12): Expert and Skills Quality Loop

Goal: improve expert outcomes with measurable impact, not feature sprawl.

- [ ] Expert manifest diff (`Delta`) and explicit `ExpertPolicy` type
- [ ] Optional `--high-trust-only` mode (primary/secondary sources only)
- [ ] Skill efficacy measurement (impact on citations, gap-fill success, cost)
- [ ] Skill templates + versioning/dependency management
- [ ] Skill format conversion (Claude Skills <-> OpenClaw Skills)
- [ ] Keep skill design constrained (focused modules, measurable outcomes)

### Phase 5 (v2.12): Operations, Team, and Security Hardening

Goal: production posture for multi-user and autonomous deployments.

- [ ] Web operations analytics:
  - [ ] cost-vs-quality frontier
  - [ ] failure-mode breakdown
  - [ ] routing decision analytics
  - [ ] expert gap velocity / citation freshness / recommended actions
- [ ] Benchmark UX completion:
  - [ ] WebSocket benchmark progress
  - [ ] run comparison deltas
  - [ ] provider validation action in UI
- [ ] Team features (auth, workspaces, RBAC, audit log)
- [ ] Permission boundaries (`--allow-write`, tool allowlists, budget policy enforcement)
- [ ] Execution isolation (sandboxed parsing, resource limits, egress controls)
- [ ] Cryptographic verification and execution-proof audit trail (stretch)

### Backlog (Not in Active Sequence)

- [ ] Local model support on NVIDIA hardware (DGX Spark, Jetson Orin Nano Super)
- [ ] Remote MCP and edge deployment (SSE, Cloudflare Workers)
- [ ] Skill marketplace and meta-skills
- [ ] Multi-agent swarm support beyond bounded subagent orchestration
- [ ] `deepr ui` Textual dashboard
- [ ] README demo GIF
- [ ] Code quality carry-over:
  - [ ] profile schema versioning
  - [ ] provider fallback integration tests
  - [ ] performance regression tests
  - [ ] 80% coverage target on core modules

---

## Non-Goals

Explicitly out of scope:

- **General-purpose chat** — Expert chat is domain-focused; for open-ended conversation, use ChatGPT, Claude, Gemini, etc.
- **Real-time responses** — Deep research takes minutes by design; this is a feature, not a bug
- **Sub-$1 comprehensive research** — Deep research requires substantial compute (use `--auto` for simple queries at $0.01)
- **Mobile apps** — CLI and web dashboard cover the use cases
- **Unreliable features** — Nothing ships until it works consistently

## Contributing

We welcome contributions. Here's where help is most valuable:

| Area | Examples | Impact |
|------|----------|--------|
| **Expert formalization** | Expert diffs, policy types, high-trust-only mode | Medium |
| **MCP client mode** | Client connections, async tasks, elicitation | High |
| **Testing** | Integration tests, provider mocks, 80% coverage | High |
| **Web dashboard** | Operational analytics, expert diff, comparison view | High |
| **Security** | Permission boundaries, sandboxing, isolation | Medium |
| **Documentation** | Examples, tutorials, API docs | Medium |

**Before contributing:**

1. Check [open issues](https://github.com/blisspixel/deepr/issues) for existing work
2. For large changes, open an issue first to discuss approach
3. Run `ruff check . && ruff format .` before committing
4. Add tests for new functionality
5. Update documentation if adding features

Most impactful work is on the intelligence layer (prompts, synthesis, expert learning) rather than infrastructure.

## Version History

| Version | Focus | Status |
|---------|-------|--------|
| v2.0-2.1 | Core infrastructure, adaptive research | Complete |
| v2.2 | Semantic commands | Complete |
| v2.3 | Expert system | Complete |
| v2.4-2.5 | MCP integration, agentic experts | Complete |
| v2.6 | Observability, fallback, cost dashboard | Complete |
| v2.7 | Context discovery, interactive mode, tracing | Complete |
| v2.8 | Provider intelligence, advanced context, real-time progress, expert formalization | Complete |
| v2.8.1 | WebSocket push, background poller, UX overhaul, benchmarks page, help page, demo data, error standardization | Complete |
| v2.9.0 | Expert skills, agentic chat (slash commands, modes, reasoning, approval, council, task planning), portraits, conversations API | Complete |
| v2.9.1 | `deepr web` CLI command, documentation updates | Complete |
| v2.10 | Agentic infrastructure core, Azure Foundry parity, MCP client reliability (start) | Planned |
| v2.11 | Routing/evaluation confidence, expert+skills quality loop | Planned |
| v2.12 | Ops analytics, team readiness, security hardening | Planned |
| v3.0+ | Self-improvement, autonomous learning | Future |

---

**Questions?** Open a [GitHub Discussion](https://github.com/blisspixel/deepr/discussions) or check the [documentation](docs/).

[MIT License](LICENSE) · [GitHub](https://github.com/blisspixel/deepr)
