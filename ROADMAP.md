# Deepr Roadmap

> Development priorities and planned features. Model/pricing notes updated through May 2026.

## Quick Links

| Document | Description |
|----------|-------------|
| [Models](docs/MODELS.md) | Provider comparison, costs, model selection |
| [Experts](docs/EXPERTS.md) | Creating and using domain experts |
| [Integrations](docs/INTEGRATIONS.md) | First-party tool integrations (recon, distillr, primr) |
| [Agentic Vision](docs/AGENTIC_VISION.md) | Agentic architecture, A2A, reflection, campaigns |
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

**Interoperability model:** Deepr is built to be one role on a larger agent team, not the orchestrator. Experts produce structured, handoff-ready artifacts (reports with citations, belief states, gap backlogs) that downstream agents can consume directly. An external orchestrator assigns work to a Deepr expert the same way it would assign work to any other role — via MCP tool calls with budget contracts and trace IDs that stitch across agent boundaries. This means Deepr doesn't need to know about the full workflow; it just needs to do its job well and hand off cleanly.

---

## Current Status (v2.10)

Multi-provider research automation with expert system, domain-specific skills, MCP integration, and observability. 4300+ tests. Pre-commit hooks with ruff.

### Stable (Production-Ready)

These features are well-tested and used regularly:

- **Core research commands**: `research`, `check`, `learn` - reliable across providers
- **Cost controls**: Budget limits, canonical cost ledger, cost tracking, `costs show/timeline/breakdown/doctor`
- **Expert creation**: `expert make`, `expert chat`, `expert export/import`
- **CLI output modes**: `--verbose`, `--json`, `--quiet`, `--explain`
- **Context discovery**: `deepr search`, `--context <id>` for reusing prior research
- **Provider support**: OpenAI (GPT-5.4, GPT-5.4-pro, GPT-5-mini, GPT-4.1, o3/o4-mini-deep-research), Gemini (3.1 Pro Preview, 3.5 Flash, 3 Flash, 2.5 Flash, Deep Research Agent), xAI Grok (4.3 flagship, 4.20 Reasoning/Non-Reasoning/Multi-Agent), Anthropic (Claude Opus 4.7/4.6, Sonnet 4.6/4.5, Haiku 4.5), Azure AI Foundry (o3-deep-research + Bing, GPT-5/5-mini, GPT-4.1/4.1-mini, GPT-4o)
- **Local storage**: SQLite persistence, markdown reports, expert profiles

### Experimental (Works but Evolving)

These features work but APIs or behavior may change:

- **Web dashboard**: Local research management UI - 12 polished pages with WebSocket push, skeleton loading, shadcn/ui components, mobile nav, accessibility
- **Expert skills**: Domain-specific capability packages with Python tools and MCP bridging. 4 built-in skills, CLI management, web API, auto-activation triggers
- **MCP server**: Functional with 18 tools, but MCP spec itself is still maturing
- **Agentic expert chat**: enabled by default in `expert chat` — autonomous research with slash commands, chat modes, visible reasoning, approval flows, expert council, and task planning. Pass `--no-research` to disable autonomous research triggers.
- **Auto-fallback**: Provider failover works, but circuit breaker tuning is ongoing
- **Cloud deployment templates**: AWS/Azure/GCP templates provided but not battle-tested at scale
- **Grok provider**: Grok 4.3 flagship + 4.20 multi-agent deep research; legacy models deprecated (retiring May 15, 2026) with auto-migration
- **Anthropic provider**: Uses Extended Thinking + orchestration (no native deep research API)
- **Azure AI Foundry provider**: Agent/Thread/Run pattern with Bing grounding; 7 models (o3-deep-research, gpt-5, gpt-5-mini, gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-4o-mini)

### What Works (Full List)

- Multi-provider support (OpenAI GPT-5.4/5-mini/4.1, Gemini 3.5 Flash/3.1 Pro/Flash-Lite/2.5, Grok 4.3/4.20, Anthropic Claude, Azure, Azure AI Foundry)
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
- Coverage configuration with 75% minimum threshold (raised from 60% in v2.10.3)
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
- Design for composability: experts are roles that receive input, produce handoff-ready output, and participate in multi-agent teams without owning the workflow.
- Make experts genuinely agentic: they plan, reflect, self-correct, and learn — not just wrap LLM calls.
- Speak every protocol: MCP for tools, A2A for agent-to-agent, agentskills.io for portability.
- Autonomy earns trust incrementally: start supervised, prove reliability, then expand bounds.

### Phase 1: Agentic Infrastructure Core

Goal: make the agentic layer production-ready — subagent contracts, role-based handoffs, provider resilience.

- [x] Subagent runtime contract (planner → delegated workers → synthesizer) with per-subagent budget and trace IDs
- [x] Explicit handoff semantics: structured input/output contracts so experts can receive work from upstream agents and produce artifacts that downstream agents consume without custom integration
- [x] Bounded parallel fan-out for council/task planning with circuit-breaker safeguards
- [x] Return artifact IDs (`job_id`, `report_id`, `expert_id`, `trace_id`) from all MCP tools
- [x] Grok 4.20 multi-agent deep research via xAI Responses API:
  - [x] Dynamic agent count (4–16) based on query complexity and budget
  - [x] Parallel tool use with shared trace IDs and per-agent spend caps
  - [x] Integrate with existing bounded fan-out + circuit breakers
- [x] Legacy deep-research deprecation handling:
  - [x] Detect legacy `o3-deep-research` calls and warn
  - [x] Transparent auto-migration to `o3`/`o4-mini-deep-research` equivalents
  - [x] Routing confidence preserved through migration
- [ ] Finish Azure Foundry parity work:
  - [x] MODELS.md documentation
  - [ ] Live integration tests with Azure credentials
  - [ ] Deploy/test o3-deep-research + Bing grounding
  - [ ] Add Foundry model discovery and benchmark coverage

### Phase 2: MCP Client Reliability + Agent Interoperability

Goal: Deepr works as both MCP provider and consumer for real workflows, and speaks A2A for agent-to-agent coordination.

See [docs/AGENTIC_VISION.md](docs/AGENTIC_VISION.md) for the full agentic architecture rationale.

- [x] MCP client connections (stdio + SSE)
- [x] Configurable MCP client profiles (named server presets with connection details, auth, budget propagation, trace ID stitching, and automatic fallback)
- [x] Async durability (resume/reconnect, timeout/cancel, progress notifications)
- [x] Parallel dispatch across MCP servers with backpressure controls
- [ ] Elicitation routing + external request sandboxing (safe pass-through for CAPTCHA/paywall/credential flows from remote MCP tools; per-server rate limits)
- [x] MCP provider enhancements:
  - [x] Resources: expose expert knowledge state, gap backlogs, cost summaries as MCP resources
  - [x] Prompts: reusable prompt templates for research workflows, expert consultation, sector analysis
  - [x] Sampling: server-initiated completions (leverage host model for collaborative synthesis)
  - [x] Streaming progress for long-running research operations
- [x] A2A protocol support:
  - [x] `deepr a2a` command to start A2A server
  - [x] Agent Card at `/.well-known/agent.json` describing expert capabilities as skills
  - [x] Task lifecycle (submitted → working → completed/failed) with streaming updates
  - [x] Budget propagation and trace ID stitching via A2A task metadata
  - [ ] Multi-expert council exposed as A2A skill
- [ ] GitHub release workflow for skill distribution
- [x] Skill portability: package experts as agentskills.io SKILL.md for Claude Code, Kiro, Cursor

### Phase 2b: First-Party Tool Integrations

Goal: give experts access to specialized research instruments from sibling projects — grounding facts, source ingestion, and strategic synthesis.

See [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) for the full integration contract and implementation details.

- [ ] Recon integration (`pip install recon-tool`):
  - [ ] MCP client connection to recon's domain_lookup, batch_lookup, delta tools
  - [ ] Expert skill with auto-trigger on company domain mentions (grounding pre-flight)
  - [ ] Trace ID pass-through for cross-tool observability
- [ ] Distillr integration (`pip install distillr`):
  - [ ] MCP client connection to distillr's ingest and query tools
  - [ ] Corpus import bridge: distillr output (MD + YAML) → expert permanent knowledge
  - [ ] Async handling with progress notifications for long ingestion runs
  - [ ] Budget propagation (cap model spend per ingestion)
- [ ] Primr integration (`pip install primr`):
  - [ ] MCP client connection to primr's analyze_company and batch tools
  - [ ] Expert skill for autonomous company deep-dive delegation
  - [ ] Async durability for 35-50 min runs (progress, resume, budget awareness)
  - [ ] Quick-mode tool for lighter/faster company context

### Phase 3: Routing and Evaluation Confidence

Goal: continuously validate routing quality/cost claims with measurable feedback.

- [x] `deepr providers models` command (model discovery UX): live provider model lists diffed against the registry, scoped by default to newer versions of families already in use, with paste-ready registry stubs (`scripts/discover_models.py`)
- [ ] Stale-model CI checks + provider-family alerting
  - [x] `deepr eval` preflight warns when newer relevant models are missing from the registry
  - [ ] Scheduled CI job that alerts on provider model drift
- [ ] Routing preview: `deepr research --preview --auto` shows exact model choice, estimated cost, and confidence before executing
- [ ] Eval methodology v2:
  - [ ] Citation quality, grounding, synthesis depth, temporal accuracy
  - [ ] Expert-specific metrics: gap-detection success rate, belief-revision accuracy, citation freshness score, integration quality
  - [ ] Task-level cost-efficiency scoring
  - [ ] Methodology versioning for run comparability
- [ ] A/B shadow mode (opt-in): run shadow query in parallel against baseline for continuous routing comparison

### Phase 4: Expert Intelligence and Quality Loop

Goal: make experts genuinely agentic — self-correcting, strategically autonomous, graph-structured memory.

- [ ] Reflection loop (self-correction before delivery):
  - [ ] Post-research quality evaluation: citation grounding, logical gaps, confidence calibration
  - [ ] Automatic re-research on specific gaps identified by reflection
  - [ ] Reflection metadata in output (what was revised, why, quality score)
  - [ ] Configurable reflection depth (0 = no reflection, 1 = single pass, 2 = iterative)
- [ ] Graph-structured expert memory:
  - [ ] Knowledge graph with typed nodes (fact, signal, inference, belief) and edges (supports, contradicts, enables)
  - [ ] Temporal awareness: confidence trajectories, staleness detection, refresh triggers
  - [ ] Inference chains: expert can explain *why* it believes something (trace through evidence)
  - [ ] Contradiction detection: new evidence that conflicts with existing beliefs surfaces automatically
- [ ] Dynamic tool selection via gap analysis:
  - [ ] Gap-to-tool mapping engine (infrastructure gaps → recon, academic gaps → distillr, strategic gaps → primr)
  - [ ] Value/cost estimation per gap-fill option
  - [ ] Strategic prioritization: fill highest-value gaps first within budget
- [ ] Expert-as-guardrail mode:
  - [ ] `validate` tool alongside `research` and `chat` — expert applies knowledge as a filter/validator
  - [ ] PASS/WARN/FAIL assessment with citations and confidence
  - [ ] Useful for downstream agents that need domain validation before acting
- [ ] Expert manifest diff (`Delta`) and explicit `ExpertPolicy` type
- [ ] Optional `--high-trust-only` mode (primary/secondary sources only)
- [ ] Structured corpus import as first-class skill:
  - [ ] One-command ingest of MD/JSON/JSONL bundles as permanent expert knowledge
  - [ ] Auto-gap detection and citation mapping on imported corpora
  - [ ] Works with any structured output (research reports, synthesis docs, company briefs)
- [ ] Skill auto-generation from research artifacts:
  - [ ] `expert skill make "Topic" --from-report artifact.md` generates skill with tools and triggers
  - [ ] Dependency tracking between generated skills
  - [ ] Efficacy scoring (citations added, gaps closed, cost impact)
- [ ] Skill templates + versioning/dependency management
- [ ] Skill format conversion (Claude Skills ↔ OpenClaw Skills ↔ agentskills.io)
- [ ] Keep skill design constrained (focused modules, measurable outcomes)

### Phase 4b: Autonomous Research Campaigns

Goal: experts that run multi-day research investigations autonomously within budget bounds.

- [ ] Campaign definition: goal, budget, duration, checkpoint frequency, stop conditions
- [ ] Background campaign executor (queue-based, persists state, survives process restarts)
- [ ] Multi-phase planning: expert decomposes goal into research phases, executes sequentially
- [ ] Checkpoint system: periodic summaries of progress, spend, gaps remaining, next steps
- [ ] Human-in-the-loop gates: configurable approval thresholds (budget %, high-risk operations)
- [ ] Campaign resume/pause/cancel with state preservation
- [ ] Multi-expert campaigns: council of experts works on shared goal over time
- [ ] Campaign artifacts: final synthesis + all intermediate checkpoints as auditable trail
- [ ] `deepr expert campaign` CLI command + MCP tool + A2A skill

### Phase 5: Operations, Team, and Security Hardening

Goal: production posture for multi-user and autonomous deployments.

- [ ] Structured handoff contracts:
  - [ ] Versioned JSON schemas for expert output (claims, confidence, citations, gaps, staleness)
  - [ ] Downstream agents can validate handoff artifacts against published schemas
  - [ ] Schema registry with backward compatibility guarantees
- [ ] Web operations analytics:
  - [ ] Cost-vs-quality frontier scatter (every routing decision plotted)
  - [ ] Failure-mode breakdown
  - [ ] Routing decision analytics
  - [ ] Expert gap velocity / citation freshness / recommended actions
  - [ ] Anomaly alerts: routing drift, gap velocity spikes, cost outliers after model releases
- [ ] Benchmark UX completion:
  - [ ] WebSocket benchmark progress
  - [ ] Run comparison deltas
  - [ ] Provider validation action in UI
- [ ] Team features (auth, workspaces, RBAC, audit log)
- [ ] Permission boundaries (`--allow-write`, tool allowlists, budget policy enforcement)
- [ ] Execution isolation (sandboxed parsing, resource limits, egress controls)
- [ ] Cryptographic verification and execution-proof audit trail (stretch)

### Backlog (Not in Active Sequence)

- [ ] Self-improving routing via expert feedback loops (experts detect poor routing in their own gaps → trigger micro-evals → propose routing-table updates)
- [ ] Azure Foundry durable agent orchestration + HITL (long-running experts that survive restarts, wait for human approval via SignalR/Durable Functions)
- [ ] Expert watch sources: pull from configured MCP or REST endpoints into relevant experts on schedule (`deepr expert sync`)
- [ ] Local model support on NVIDIA hardware (DGX Spark, Jetson Orin Nano Super) with automatic offload when cloud budget exhausted
- [ ] Remote MCP and edge deployment (SSE, Cloudflare Workers)
- [ ] Skill marketplace and meta-skills
- [ ] Multi-agent swarm support beyond bounded subagent orchestration
- [ ] `deepr ui` Textual dashboard
- [ ] README demo GIF
- [ ] Code quality carry-over:
  - [ ] Profile schema versioning
  - [ ] Provider fallback integration tests
  - [ ] Performance regression tests
  - [ ] 80% coverage target on core modules

---

## Non-Goals

Explicitly out of scope:

- **General-purpose chat** — Expert chat is domain-focused; for open-ended conversation, use ChatGPT, Claude, Gemini, etc.
- **Workflow orchestration** — Deepr experts are roles that participate in multi-agent teams, but Deepr is not the orchestrator. It handles its domain (research, knowledge, gap detection) and hands off cleanly. Workflow coordination belongs to a separate orchestration layer.
- **Real-time responses** — Deep research takes minutes by design; this is a feature, not a bug
- **Sub-$1 comprehensive research** — Deep research requires substantial compute (use `--auto` for simple queries at $0.01)
- **Mobile apps** — CLI and web dashboard cover the use cases
- **Unreliable features** — Nothing ships until it works consistently

## Contributing

We welcome contributions. Here's where help is most valuable:

| Area | Examples | Impact |
|------|----------|--------|
| **Agent interoperability** | A2A protocol, MCP resources/prompts/sampling, skill portability | High |
| **MCP client mode** | Client connections, profiles, async tasks, elicitation | High |
| **First-party integrations** | Recon grounding, Distillr corpus import, Primr company analysis | High |
| **Expert intelligence** | Reflection loop, graph memory, dynamic tool selection, guardrail mode | High |
| **Expert quality loop** | Corpus import, skill auto-gen, expert diffs, efficacy scoring | High |
| **Testing** | Integration tests, provider mocks, 80% coverage | High |
| **Web dashboard** | Operational analytics, anomaly alerts, cost frontier | Medium |
| **Provider resilience** | Legacy deprecation handling, routing preview, A/B shadow | Medium |
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
| v2.10 | Agentic infrastructure core, Grok 4.3 flagship, legacy migration, Azure Foundry parity | In Progress |
| v2.10.1 | MCP client + A2A protocol, agent interoperability, skill portability | Complete |
| v2.10+ | First-party integrations: recon, distillr, primr | Planned |
| v2.11 | Routing preview, eval methodology v2, expert-specific metrics, A/B shadow | Planned |
| v2.11+ | Expert intelligence: reflection loop, graph memory, dynamic tool selection, guardrail mode | Planned |
| v2.12 | Autonomous research campaigns, multi-day expert investigations | Planned |
| v2.13 | Ops analytics, anomaly alerts, team/RBAC, security hardening | Planned |
| v3.0+ | Self-improving routing, autonomous learning, campaign orchestration | Future |

---

**Questions?** Open a [GitHub Discussion](https://github.com/blisspixel/deepr/discussions) or check the [documentation](docs/).

[MIT License](LICENSE) · [GitHub](https://github.com/blisspixel/deepr)
