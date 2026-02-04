# Deepr Roadmap

> Development priorities and planned features. Model pricing current as of February 2026.

## Quick Links

| Document | Description |
|----------|-------------|
| [Models](docs/MODELS.md) | Provider comparison, costs, model selection |
| [Experts](docs/EXPERTS.md) | Creating and using domain experts |
| [Architecture](docs/ARCHITECTURE.md) | Technical details, security, observability |
| [Changelog](docs/CHANGELOG.md) | Release history with migration notes |
| [Vision](docs/VISION.md) | Long-term direction (v3.0+) |

---

## Current Status (v2.7)

Multi-provider research automation with expert system, MCP integration, and observability. 3000+ tests passing. CI via GitHub Actions, pre-commit hooks with ruff.

### Stable (Production-Ready)

These features are well-tested and used regularly:

- **Core research commands**: `research`, `check`, `learn` - reliable across providers
- **Cost controls**: Budget limits, cost tracking, `costs show/timeline/breakdown`
- **Expert creation**: `expert make`, `expert chat`, `expert export/import`
- **CLI output modes**: `--verbose`, `--json`, `--quiet`, `--explain`
- **Provider support**: OpenAI (GPT-5.2, o3/o4-mini-deep-research), Gemini (2.5 Flash, Deep Research Agent), Anthropic (Claude Opus/Sonnet/Haiku 4.5)
- **Local storage**: SQLite persistence, markdown reports, expert profiles

### Experimental (Works but Evolving)

These features work but APIs or behavior may change:

- **Web dashboard**: Local research management UI - job queue, results library, cost analytics
- **MCP server**: Functional with 10 tools, but MCP spec itself is still maturing
- **Agentic expert chat**: `--agentic` flag triggers autonomous research - powerful but can be expensive
- **Auto-fallback**: Provider failover works, but circuit breaker tuning is ongoing
- **Cloud deployment templates**: AWS/Azure/GCP templates provided but not battle-tested at scale
- **Grok provider**: Basic support, less tested than OpenAI/Gemini
- **Anthropic provider**: Uses Extended Thinking + orchestration (no native deep research API)

### What Works (Full List)

- Multi-provider support (OpenAI GPT-5.2, Gemini, Grok 4, Anthropic Claude, Azure)
- Deep Research via OpenAI API (o3/o4-mini-deep-research) and Gemini Interactions API (Deep Research Agent)
- Semantic commands (`research`, `learn`, `team`, `check`, `make`)
- Expert system with autonomous learning, agentic chat, knowledge synthesis
- MCP server with 10 tools, persistence, security, multi-runtime configs
- Web dashboard (job queue, results library, cost analytics, settings)
- CLI trace flags (`--explain`, `--timeline`, `--full-trace`)
- Output modes (`--verbose`, `--json`, `--quiet`)
- Auto-fallback on provider failures with `--no-fallback` override
- Cost dashboard (`costs timeline`, `costs breakdown --period`, `costs expert`)
- Multi-layer budget protection with pause/resume
- Docker deployment option
- Cloud deployment templates (AWS, Azure, GCP)
- GitHub Actions CI (lint + unit tests on push/PR)
- Pre-commit hooks (ruff lint+format, trailing whitespace, debug statement detection)
- Coverage configuration with 60% minimum threshold

---

## Completed Work

Implementation details for completed priorities are in the [Changelog](docs/CHANGELOG.md).

| Priority | Description | Version |
|----------|-------------|---------|
| P1 | UX Polish (doctor, progress, paths) | v2.0-2.1 |
| P2 | Semantic Commands (research, learn, team, check, make) | v2.2 |
| P2.5 | Expert System (create, chat, learn, export/import) | v2.3 |
| P3 | MCP Integration (server, tool discovery, subscriptions, elicitation) | v2.4-2.5 |
| 4.1 | CLI Trace Flags (--explain, --timeline, --full-trace) | v2.6 |
| 4.3 | Cost Attribution Dashboard (timeline, breakdown --period, expert costs) | v2.6 |
| 5.2 | Auto-Fallback on Provider Failures (retry, classify, --no-fallback) | v2.6 |
| 7.1 | Minimal Default Output (OutputMode, @output_options) | v2.6 |
| 9.1 | MCP Server Architecture (job pattern, resources, notifications, errors) | v2.5 |
| 9.2 | AgentSkill Packaging (SKILL.md, prompts, install scripts) | v2.5 |
| 9.4 | Security Hardening (Docker, SSRF, path traversal, sampling) | v2.5-2.6 |
| 9.5 | Claude-Specific Optimizations (CoT, lazy loading, context management) | v2.5 |
| 9.6 | Multi-Runtime Config Templates (OpenClaw, Claude Desktop, Cursor, VS Code) | v2.5 |
| 5.4 | Gemini Deep Research Agent (Interactions API, File Search Stores, adaptive polling) | v2.6 |
| 10.1 | Cloud Deployment Templates (AWS SAM, Azure Bicep, GCP Terraform) | v2.6 |

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

## Next Priorities

### Priority 4: Observability (remaining)

**What exists:** TraceContext, Span, MetadataEmitter, ThoughtStream, CLI trace flags, cost dashboard.

#### 4.2 Auto-Generated Metadata
- [ ] Instrument `core/research.py` to emit spans per phase (plan, search, analyze, synthesize)
- [ ] Instrument `experts/chat.py` to emit spans for tool calls
- [ ] Add cost attribution to each span (cost from token counts + model pricing)
- [ ] Add token counts to spans (input, output, cached)

#### 4.4 Decision Logs in Natural Language
- [ ] Extend ThoughtStream to generate human-readable decision summaries
- [ ] Add `--why` flag for inline model/provider/budget reasoning
- [ ] Store decision logs alongside reports in `reports/{job_id}/decisions.md`

#### 4.5 Research Quality Metrics
- [ ] Entropy-based stopping criteria (detect when searches yield diminishing returns)
- [ ] Information gain tracking per research phase
- [ ] Auto-pivot detection (when to change search strategy vs. terminate)
- [ ] Quality score in research output (novelty, relevance, confidence)

---

### Priority 5: Provider Routing (remaining)

**What exists:** AutonomousProviderRouter with scoring, fallback, circuit breakers. Auto-fallback wired into CLI.

#### 5.1 Real-Time Performance Benchmarking
- [ ] Add latency percentiles (p50, p95, p99) to ProviderMetrics with sliding window
- [ ] Track success rate by task type (research, chat, synthesis, planning)
- [ ] Add `deepr providers benchmark` command with `--quick` option
- [ ] Store benchmark history for trend analysis and degradation alerts

#### 5.3 Continuous Optimization
- [ ] Exploration vs exploitation (90/10 default, configurable)
- [ ] A/B testing mode: same query on multiple providers
- [ ] `deepr providers status` command (health, circuit breaker state)
- [ ] Auto-disable failing providers (>50% failure rate, 1hr cooldown)

---

### Priority 6: Context Discovery

**What exists:** Reports stored with metadata, ContextBuilder service.

#### 6.1 Detect Related Prior Research
- [ ] Index report metadata in SQLite with embeddings
- [ ] Semantic similarity search (cosine, threshold > 0.7)
- [ ] `deepr search "topic"` command with keyword + semantic results
- [ ] Similarity scores and date sorting

#### 6.2 Notify-Only (Never Auto-Inject)
- [ ] "Related research found" message before starting research
- [ ] Actionable hint: "Use --context <id> to include previous findings"
- [ ] `--ignore-related` flag to skip check

#### 6.3 Explicit Reuse with Warnings
- [ ] `--context <report-id>` flag to include previous research
- [ ] Stale context warnings (>30 days)
- [ ] Cost savings estimate and context lineage tracking

#### 6.4 Temporal Knowledge Tracking
- [ ] Track *when* findings were discovered (not just what)
- [ ] Context chaining: output of phase N becomes structured input for phase N+1
- [ ] Research timeline visualization (`--timeline` for multi-phase research)
- [ ] Hypothesis evolution tracking (how understanding changed during research)

#### 6.5 Dynamic Context Management
- [ ] Context pruning for long research sessions (summarize older findings)
- [ ] Token budget allocation across research phases
- [ ] Offload intermediate findings to persistent storage
- [ ] Context window utilization metrics in `--explain` output

---

### Priority 7: Modern CLI UX (remaining)

#### 7.2 Interactive Mode
- [ ] `deepr` with no args opens interactive menu (questionary/InquirerPy)
- [ ] Query autocomplete from recent history
- [ ] Provider/model picker with cost estimates

#### 7.3 Real-Time Progress for Long Operations
- [ ] Poll provider status API and show phase progress
- [ ] Stream partial results when API supports it
- [ ] Progress bar for multi-phase operations

#### 7.4 TUI Dashboard (Stretch)
- [ ] `deepr ui` opens Textual-based terminal UI
- [ ] Active jobs, recent results, budget status
- [ ] Keyboard navigation, split pane layout

#### 7.5 Command Consolidation
- [ ] Remove deprecated aliases (`run single`, `run campaign`)
- [ ] Consolidate to core commands: `research`, `jobs`, `expert`, `config`
- [ ] Update documentation to match

#### 7.6 Output Improvements (remaining)
- [ ] Consistent key-value formatting across all commands
- [ ] Truncate long outputs with "use --full to see all"
- [ ] Hyperlinks to reports in supported terminals

---

### Priority 8: NVIDIA Provider (LATER)

Support for self-hosted NVIDIA NIM infrastructure. Only for enterprises with existing NVIDIA deployments.

- [ ] NIM API client implementation
- [ ] Model registry entries for NIM models
- [ ] Documentation for self-hosted setup

---

### MCP Ecosystem (remaining)

**What exists:** Full MCP server with 10 tools, persistence, security, skill packaging, Docker, multi-runtime configs.

#### MCP Client Mode (Deepr as Tool Consumer)
- Design complete (SearchBackend, BrowserBackend protocols, architecture doc)
- [ ] Implement MCP client connections (Stdio, SSE transports)
- [ ] Brave Search and Puppeteer/Playwright MCP adapters
- [ ] Recursive agent composition for sub-agent summarization

#### Async Task Handling
- [ ] Long-running task support with `task_id` returns
- [ ] Progress monitoring via `notifications/progress` subscription
- [ ] Task durability (survive connection interruptions, resume on reconnect)
- [ ] Parallel task dispatch (multiple MCP servers simultaneously)
- [ ] Task timeout and cancellation support

#### Enhanced Elicitation
- [ ] Human-in-the-loop for blocked operations (CAPTCHA, paywall, ambiguous data)
- [ ] Elicitation routing to user via CLI prompt or web dashboard notification
- [ ] Credential pass-through for gated content (user provides, agent uses)
- [ ] Elicitation timeout with graceful degradation

#### Remaining MCP Items
- [ ] GitHub release workflow for skill distribution
- [ ] Wire sampling into web scraper (CAPTCHA/paywall detection)
- [ ] Rate limiting for external requests

#### Skill System Enhancements
- [ ] Skill format conversion (Claude Skills ↔ OpenClaw Skills)
- [ ] Meta-skills: generate temporary skills for niche research topics
- [ ] Skill marketplace discovery (`deepr skills search`)
- [ ] Skill versioning and dependency management

#### Stretch Goals
- [ ] Multi-agent swarm support (specialized variants, manager routing)
- [ ] Remote MCP and edge deployment (SSE, Cloudflare Workers)
- [ ] Memory integration (cross-session persistence, vector DB)

---

### Execution Security

**What exists:** Docker deployment, SSRF protection, path traversal prevention, API key encryption.

Defense-in-depth for autonomous research operations, especially when using agentic mode or MCP tools with write access.

#### Cryptographic Verification
- [ ] Sign all instructions sent to MCP tools (prevent prompt injection relay)
- [ ] Hash verification for tool outputs (detect tampering)
- [ ] Audit trail with cryptographic proof of execution sequence
- [ ] Optional: Integrate with signing services (Crittora, Sigstore)

#### Execution Isolation
- [ ] Sandboxed execution for untrusted tool outputs (parse in isolated process)
- [ ] Container-per-task option for high-security research
- [ ] Resource limits (CPU, memory, network) per MCP tool invocation
- [ ] Network egress controls (allowlist domains for research tools)

#### Permission Boundaries
- [ ] Read-only default for all file operations
- [ ] Write operations require explicit `--allow-write` or elicitation confirmation
- [ ] Budget policy enforcement (max spend per session/day)
- [ ] Tool allowlist per research mode (`--tools web,search` restricts available tools)

---

### Web Dashboard

Local research management interface for monitoring batch operations. CLI remains primary for scripting/automation; dashboard provides visibility when running many concurrent jobs.

**What exists:** React + TypeScript frontend with Flask backend. Dashboard, job queue, results library, cost analytics, settings. Light/dark mode. 22 API endpoints.

#### Completed
- [x] Job submission and queue monitoring with real-time status
- [x] Results library with search, sort, grid/list views
- [x] Cost analytics with daily/monthly trends, budget alerts
- [x] Settings page (API keys, limits, defaults)
- [x] Modern UI with light/dark mode toggle
- [x] Full API coverage (jobs, costs, results, config)

#### Core Improvements
- [ ] Report viewer with full markdown rendering and syntax highlighting
- [ ] Expert management UI (list, create, chat with domain experts)
- [ ] Job detail page with live progress updates (WebSocket)
- [ ] Export results (PDF, DOCX in addition to Markdown)
- [ ] Tags and folders for organizing research by project

#### Team Deployment
- [ ] Authentication (JWT or OAuth)
- [ ] Team workspaces with shared research libraries
- [ ] Role-based access (admin, researcher, viewer)
- [ ] Per-user API key management
- [ ] Audit log (who ran what, when)

#### Advanced Features
- [ ] Scheduled/recurring research (cron-like)
- [ ] Webhooks for external integrations (Slack, email)
- [ ] Comparison view (side-by-side research results)
- [ ] Research templates (save and reuse prompts)
- [ ] Bulk operations UI (batch submit, bulk cancel, bulk export)

---

## Code Quality

#### Completed
- [x] Split `cli/commands/semantic.py` (3,318 lines) into `cli/commands/semantic/` package (`research.py`, `artifacts.py`, `experts.py`)
- [x] Tightened exception handling across storage, providers, core, and services (replaced broad `except Exception` with specific types)
- [x] Consolidated model pricing into single registry source of truth (`providers/registry.py`)
- [x] Replaced `print()` calls in library code with structured `logging`
- [x] Removed dead legacy CLI module, `setup.py`, `sys.path` hacks
- [x] Single-sourced version string from `deepr/__init__.py`

#### ExpertProfile Refactoring
- [ ] Split `experts/profile.py` into `profile.py` (data) and `profile_manager.py` (operations)
- [ ] Extract belief management to `experts/beliefs_manager.py`
- [ ] Add profile versioning for schema migrations

#### Configuration Consolidation
- [ ] Audit all config sources (`config.py`, `unified_config.py`, env vars, CLI flags)
- [ ] Create single `Settings` class as source of truth
- [ ] Deprecate duplicate config loading paths

#### Test Coverage
- [ ] Add integration tests for provider fallback
- [ ] Add performance regression tests
- [ ] Target: 80% coverage on core modules

---

## Build Order

Recommended sequence for remaining work:

**CLI & Core:**
1. **7.2 Interactive Mode** - High user value
2. **6.1 Context Discovery** - New feature, moderate effort
3. **4.2 Auto-Generated Metadata** - Observability depth
4. **4.5 Research Quality Metrics** - Entropy-based stopping, quality scores
5. **6.4-6.5 Temporal Knowledge & Context Management** - Long research sessions
6. **7.3 Real-Time Progress** - Depends on API capabilities
7. **5.1 Provider Benchmarking** - Data-driven routing

**MCP & Execution:**
8. **MCP Client Mode** - Design done, connections not yet built
9. **Async Task Handling** - Progress monitoring, parallel dispatch
10. **Enhanced Elicitation** - Human-in-the-loop for blocked operations
11. **Execution Security** - Permission boundaries, isolation (for agentic mode)

**Web Dashboard:**
12. **Report Viewer** - Markdown rendering, syntax highlighting
13. **Expert Management UI** - Expose CLI expert features to web
14. **WebSocket Progress** - Real-time job updates

**Team Features:**
15. **Authentication** - Required for team deployment
16. **Skill System Enhancements** - Conversion, meta-skills, marketplace
17. **7.4 TUI Dashboard** - Stretch goal

---

## Non-Goals

Explicitly out of scope:

- **Chat interface** — Use ChatGPT, Claude, Gemini, etc. for conversational AI
- **Real-time responses** — Deep research takes minutes by design; this is a feature, not a bug
- **Sub-$1 research** — Comprehensive research requires substantial compute
- **Mobile apps** — CLI and web dashboard cover the use cases
- **Unreliable features** — Nothing ships until it works consistently

## Contributing

We welcome contributions. Here's where help is most valuable:

| Area | Examples | Impact |
|------|----------|--------|
| **Context management** | Temporal tracking, context pruning, phase chaining | High |
| **Research quality** | Entropy metrics, stopping criteria, quality scoring | High |
| **MCP client mode** | Async tasks, progress handling, elicitation flows | High |
| **Provider integrations** | New providers, API updates, error handling | High |
| **Cost optimization** | Token estimation, caching, batch strategies | High |
| **Expert system** | Knowledge synthesis, gap detection, learning | High |
| **Execution security** | Sandboxing, verification, permission boundaries | Medium |
| **CLI UX** | Interactive mode, progress, output formatting | Medium |
| **Web dashboard** | React components, API endpoints, real-time updates | Medium |
| **Documentation** | Examples, tutorials, API docs | Medium |
| **Testing** | Integration tests, edge cases, provider mocks | Medium |

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
| v2.7 | Web dashboard, modern CLI UX | In Progress |
| v2.8 | Provider routing, context discovery | Planned |
| v2.9 | Team features (auth, workspaces) | Planned |
| v3.0+ | Self-improvement | Future |

---

**Questions?** Open a [GitHub Discussion](https://github.com/blisspixel/deepr/discussions) or check the [documentation](docs/).

[MIT License](LICENSE) · [GitHub](https://github.com/blisspixel/deepr)
