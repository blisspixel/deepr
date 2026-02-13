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

## Architecture Layers

Deepr is organized in three layers. When contributing, it helps to know which layer you're working in:

| Layer | What lives here | Examples |
|-------|----------------|----------|
| **Kernel** — reusable agent infrastructure | Task execution, budget enforcement, provider routing, trace/decision logging | `core/`, `observability/`, `providers/`, `queue/`, `routing/` |
| **Primitives** — swappable domain modules | Web search, citation extraction, expert memory, summarization, gap detection | `experts/`, `services/`, `tools/`, `storage/` |
| **Interfaces** — user-facing surfaces | CLI for scripting and experiments, web dashboard for operations and analytics | `cli/`, `web/`, `mcp/` |

The kernel is designed to be embeddable in other agent projects. The primitives are specific to research but follow patterns (belief states, gap backlogs, refresh policies) that generalize. The interfaces are thin wrappers over the lower layers.

---

## Current Status (v2.8.1)

Multi-provider research automation with expert system, MCP integration, and observability. 1200+ tests passing. Pre-commit hooks with ruff.

### Stable (Production-Ready)

These features are well-tested and used regularly:

- **Core research commands**: `research`, `check`, `learn` - reliable across providers
- **Cost controls**: Budget limits, cost tracking, `costs show/timeline/breakdown`
- **Expert creation**: `expert make`, `expert chat`, `expert export/import`
- **CLI output modes**: `--verbose`, `--json`, `--quiet`, `--explain`
- **Context discovery**: `deepr search`, `--context <id>` for reusing prior research
- **Provider support**: OpenAI (GPT-5.2, o3/o4-mini-deep-research), Gemini (2.5 Flash, Deep Research Agent), Anthropic (Claude Opus/Sonnet/Haiku 4.5)
- **Local storage**: SQLite persistence, markdown reports, expert profiles

### Experimental (Works but Evolving)

These features work but APIs or behavior may change:

- **Web dashboard**: Local research management UI - 10 polished pages with WebSocket push, skeleton loading, shadcn/ui components, mobile nav, accessibility
- **MCP server**: Functional with 16 tools, but MCP spec itself is still maturing
- **Agentic expert chat**: `--agentic` flag triggers autonomous research - powerful but can be expensive
- **Auto-fallback**: Provider failover works, but circuit breaker tuning is ongoing
- **Cloud deployment templates**: AWS/Azure/GCP templates provided but not battle-tested at scale
- **Grok provider**: Basic support, less tested than OpenAI/Gemini
- **Anthropic provider**: Uses Extended Thinking + orchestration (no native deep research API)

### What Works (Full List)

- Multi-provider support (OpenAI GPT-5.2, Gemini, Grok 4, Anthropic Claude, Azure)
- Deep Research via OpenAI API (o3/o4-mini-deep-research) and Gemini Interactions API (Deep Research Agent)
- Semantic commands (`research`, `learn`, `team`, `check`, `make`)
- Expert system with autonomous learning, agentic chat, knowledge synthesis, curriculum preview (`expert plan`)
- MCP server with 16 tools, persistence, security, multi-runtime configs
- Web dashboard (10 pages: overview, research studio, research live, results library, result detail, expert hub, expert profile, cost intelligence, trace explorer, settings)
- CLI trace flags (`--explain`, `--timeline`, `--full-trace`)
- Output modes (`--verbose`, `--json`, `--quiet`)
- Auto-fallback on provider failures with `--no-fallback` override
- **Auto mode** (`--auto`) for smart query routing based on complexity (10-20x cost savings)
- **Batch processing** (`--auto --batch queries.txt`) with per-query optimal routing
- Cost dashboard (`costs timeline`, `costs breakdown --period`, `costs expert`)
- Multi-layer budget protection with pause/resume
- Docker deployment option
- Cloud deployment templates (AWS, Azure, GCP)
- Pre-commit hooks (ruff lint+format, trailing whitespace, debug statement detection)
- Coverage configuration with 60% minimum threshold
- Context discovery with semantic search (`deepr search`, `--context` flag)
- Distributed tracing with MetadataEmitter, spans, cost attribution

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
| 7.2 | Interactive Mode (no-args menu, query history, model picker with costs) | v2.7 |
| 6.1 | Context Discovery (report indexing, semantic search, `deepr search` command) | v2.7 |
| 6.2 | Notify-Only Context Discovery (automatic related research detection on submit) | v2.7 |
| 6.3 | Explicit Context Reuse (`--context <id>` flag, stale warnings) | v2.7 |
| 5.1 | Real-Time Benchmarking (latency percentiles, task type success rates, `providers benchmark --history`) | v2.8 |
| 5.3 | Continuous Optimization (exploration/exploitation, auto-disable failing providers) | v2.8 |
| 6.4 | Temporal Knowledge Tracking (timestamps, context chaining, hypothesis evolution) | v2.8 |
| 6.5 | Dynamic Context Management (pruning, token budgets, findings storage) | v2.8 |
| 7.3 | Real-Time Progress (phase tracking, progress bar, partial results streaming) | v2.8 |
| 5.5 | Auto Mode: Smart Query Routing (`--auto`, `--batch`, `--dry-run`, complexity-based routing) | v2.8 |
| 4.6 | Decision Record Schema (`DecisionRecord` type, CLI table, trace sidebar, MCP queries) | v2.8 |
| Phase 5 | Expert Contract (`ExpertManifest`, `Claim`, `Gap`, `Source` types in `core/contracts.py`) | v2.8 |
| Phase 5 | Gap EV/Cost Ranking (`gap_scorer.py`, scored gaps in web + MCP) | v2.8 |
| Phase 5 | Source Provenance (`TrustClass` enum, content hashes, extraction method) | v2.8 |

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
- [x] Instrument `core/research.py` to emit spans per phase (submit, completion, cancel)
- [x] Instrument `experts/chat.py` to emit spans for tool calls (search, standard_research, deep_research)
- [x] Add cost attribution to each span (cost from token counts + model pricing)
- [x] Add token counts to spans (input, output via set_tokens())

#### 4.4 Decision Logs in Natural Language
- [x] Extend ThoughtStream to generate human-readable decision summaries (`generate_decision_summary()`)
- [x] Add concise summary method for CLI output (`get_why_summary()`)
- [x] Store decision logs alongside reports (`save_decision_log()` method)
- [x] Wire `--why` flag to CLI commands (alias for `--explain`)

#### 4.5 Research Quality Metrics
- [x] Entropy-based stopping criteria (`EntropyStoppingCriteria` in `observability/stopping_criteria.py`)
- [x] Information gain tracking per research phase (`InformationGainTracker` in `observability/information_gain.py`)
- [x] Auto-pivot detection (`StoppingDecision.pivot_suggestion` in stopping_criteria.py)
- [x] Quality score in research output (`QualityMetrics` in `observability/quality_metrics.py`)

#### 4.6 Decision Record Schema
- [x] `DecisionRecord` type with `DecisionType` enum (routing, stop, pivot, budget, belief_revision, gap_fill, conflict_resolution, source_selection) in `core/contracts.py`
- [x] ThoughtStream emits `DecisionRecord` objects via `record_decision()`, saves `decisions.json` alongside `decisions.md`
- [x] Decision records in Trace Explorer as a collapsible sidebar alongside the span waterfall
- [x] CLI `--explain` shows decision table (type, decision, confidence, cost impact)
- [x] MCP: `deepr_expert_manifest` returns decisions; web API: `GET /api/experts/<name>/decisions`

---

### Priority 5: Provider Routing (remaining)

**What exists:** AutonomousProviderRouter with scoring, fallback, circuit breakers. Auto-fallback wired into CLI.

#### 5.1 Real-Time Performance Benchmarking
- [x] Add latency percentiles (p50, p95, p99) to ProviderMetrics with sliding window
- [x] Track success rate by task type (research, chat, synthesis, planning)
- [x] Add `deepr providers benchmark` command with `--quick` and `--history` options
- [x] Store benchmark history for trend analysis (`get_benchmark_data()` method)

#### 5.3 Continuous Optimization
- [x] Exploration vs exploitation (10% default, configurable via `exploration_rate`)
- [ ] A/B testing mode: same query on multiple providers (stretch goal)
- [x] `deepr providers status` command (health, circuit breaker state, auto-disabled)
- [x] Auto-disable failing providers (>50% failure rate, 1hr cooldown)

#### 5.5 Auto Mode: Smart Query Routing
- [x] `AutoModeRouter` combining `ModelRouter` query analysis with `AutonomousProviderRouter` metrics (`routing/auto_mode.py`)
- [x] `--auto` flag on `deepr research` for complexity-based routing (simple/moderate/complex)
- [x] `--batch` flag for processing multiple queries from `.txt` or `.json` files (`services/batch_auto.py`)
- [x] `--dry-run` flag to preview routing decisions and cost estimates without executing
- [x] `--prefer-cost` and `--prefer-speed` optimization flags
- [x] API key awareness: checks `OPENAI_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY` before routing to a provider
- [x] Tiered deep research models: simple → grok-4-fast ($0.01), moderate → o4-mini-deep-research ($0.10), complex → o3-deep-research ($0.50)
- [x] Budget-aware routing (downgrades through o3 → o4-mini → gpt-5.2 → grok-4-fast)
- [x] Auto-routed jobs in queue schema (`auto_routed`, `routing_decision`, `batch_id` fields)
- [x] AWS worker respects `routing_decision` for provider/model selection
- [x] 44 unit tests covering routing logic, API key awareness, batch parsing, dry-run execution

---

### Priority 6: Context Discovery

**What exists:** Reports stored with metadata, ContextBuilder service, ContextIndex with embeddings.

#### 6.1 Detect Related Prior Research
- [x] Index report metadata in SQLite with embeddings
- [x] Semantic similarity search (cosine, threshold > 0.7)
- [x] `deepr search "topic"` command with keyword + semantic results
- [x] Similarity scores and date sorting

#### 6.2 Notify-Only (Never Auto-Inject)
- [x] "Related research found" message before starting research
- [x] Actionable hint: "Use --context <id> to include previous findings"
- [x] `--no-context-discovery` flag to skip check

#### 6.3 Explicit Reuse with Warnings
- [x] `--context <report-id>` flag to include previous research
- [x] Stale context warnings (>30 days)
- [x] Cost savings estimate when using `--context`
- [x] Context lineage tracking (`--lineage` flag in trace command, tree visualization)

#### 6.4 Temporal Knowledge Tracking
- [x] Track *when* findings were discovered (`TemporalKnowledgeTracker` with timestamps)
- [x] Context chaining: output of phase N becomes structured input for phase N+1 (`ContextChainer`)
- [x] Research timeline visualization (`--timeline`, `--temporal` flags in trace command)
- [x] Hypothesis evolution tracking (`Hypothesis`, `HypothesisEvolution` in temporal_tracker.py)

#### 6.5 Dynamic Context Management
- [x] Context pruning for long research sessions (`ContextPruner` in services/context_pruner.py)
- [x] Token budget allocation across research phases (`TokenBudgetAllocator` in services/token_budget.py)
- [x] Offload intermediate findings to persistent storage (`FindingsStore` in storage/findings_store.py)
- [x] Context window utilization metrics in `--explain` output (`--show-budget` flag in trace command)

---

### Expert System Formalization

**What exists:** ExpertProfile with beliefs, gaps, budget manager, activity tracker, curriculum, metacognition, serializer, autonomous learning, gap-filling. Canonical types (`Claim`, `Gap`, `DecisionRecord`, `ExpertManifest`) in `core/contracts.py` with adapters on existing classes. Gap scoring via `gap_scorer.py`. Manifests queryable via MCP and web API.

#### Expert Contract
- [x] `ExpertManifest` dataclass: expert_name, domain, claims, gaps, decisions, policies, generated_at, computed properties (claim_count, open_gap_count, avg_confidence, top_gaps) in `core/contracts.py`
- [x] `Claim` type: atomic assertion + confidence + sources[] + created_at + updated_at + contradicts + tags
- [x] `Gap` type: topic + questions + priority + estimated_cost + expected_value + ev_cost_ratio + times_asked + filled status
- [x] Adapter methods: `Belief.to_claim()` in beliefs.py and synthesis.py, `KnowledgeGap.to_gap()` in synthesis.py and metacognition.py
- [x] `ExpertProfile.get_manifest()` composes claims, scored gaps, decisions, and policies into typed snapshot
- [ ] Generate `Delta` on expert updates: claims added/changed/removed between versions
- [ ] Define `ExpertPolicy` as explicit type (currently dict in manifest)

#### Gap Prioritization
- [x] `gap_scorer.py` with `score_gap()` and `rank_gaps()` functions
- [x] Formula: `ev_cost_ratio = expected_value / estimated_cost` where expected_value = `(priority/5 + frequency_boost)`
- [x] Domain velocity cost lookup: fast=$0.25, medium=$1.00, slow=$2.00
- [x] EV/cost ratio displayed in Expert Profile gaps tab (color-coded badge) and web API
- [x] `deepr_rank_gaps` MCP tool returns top N scored gaps

#### Source Provenance
- [x] `Source` type with `TrustClass` enum (primary, secondary, tertiary, self_generated) in `core/contracts.py`
- [x] Content hash + extraction method stored per source
- [x] `Belief.to_claim()` converts evidence_refs to Source objects with trust classification
- [ ] Optional `--high-trust-only` mode that restricts expert to primary/secondary sources

---

### Priority 7: Modern CLI UX (remaining)

#### 7.2 Interactive Mode
- [x] `deepr` with no args opens interactive menu (Rich-based)
- [x] Query autocomplete from recent history
- [x] Provider/model picker with cost estimates

#### 7.3 Real-Time Progress for Long Operations
- [x] Poll provider status API and show phase progress (`ResearchProgressTracker` in cli/realtime_progress.py)
- [x] Stream partial results when API supports it (`show_partial` option in tracker)
- [x] Progress bar for multi-phase operations (`--progress` flag in `deepr research wait`)

#### 7.4 TUI Dashboard (Stretch)
- [ ] `deepr ui` opens Textual-based terminal UI
- [ ] Active jobs, recent results, budget status
- [ ] Keyboard navigation, split pane layout

#### 7.5 Command Consolidation
- [x] Remove deprecated aliases (`run single`, `run campaign`)
- [x] Consolidate to core commands: `research`, `jobs`, `expert`, `config`
- [ ] Update documentation to match

#### 7.6 Output Improvements (remaining)
- [ ] Consistent key-value formatting across all commands
- [x] Truncate long outputs with "use --full to see all" (`print_truncated()` in colors.py)
- [x] Hyperlinks to reports in supported terminals (`make_hyperlink()`, `print_report_link()` in colors.py)

---

### Priority 8: NVIDIA Provider (LATER)

Support for self-hosted NVIDIA NIM infrastructure. Only for enterprises with existing NVIDIA deployments.

- [ ] NIM API client implementation
- [ ] Model registry entries for NIM models
- [ ] Documentation for self-hosted setup

---

### MCP Ecosystem (remaining)

**What exists:** Full MCP server with 16 tools, persistence, security, skill packaging, Docker, multi-runtime configs.

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

#### MCP Composability
- [x] `deepr_expert_manifest` tool returns full expert state (claims, gaps, decisions, policies)
- [x] `deepr_rank_gaps` tool returns top N scored gaps for proactive filling
- [x] `deepr_get_expert_info` includes claim_count, open_gap_count, avg_confidence
- [ ] All tool responses include artifact IDs (`job_id`, `report_id`, `expert_id`, `trace_id`) alongside summaries
- [ ] Expose `experts.diff(version_a, version_b)` for versioned comparison

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

**What exists:** React 18 + TypeScript + Vite + Tailwind CSS frontend with Flask + Flask-SocketIO backend. 10 pages with code-split routing, skeleton loading states, Radix UI (shadcn/ui) component library, Recharts charts, WebSocket real-time push via background poller. Drag-and-drop file upload, Ctrl+Enter submit, copy-to-clipboard, pagination, mobile hamburger nav, FOUC prevention, skip-to-content a11y. Light/dark/system theme. 23 API endpoints.

#### Completed
- [x] Job submission and queue monitoring with real-time status
- [x] Results library with search, sort, pagination (12/page)
- [x] Cost analytics with daily/monthly trends, budget alerts
- [x] Settings page (API keys, limits, defaults, environment info)
- [x] Modern UI with light/dark/system mode toggle
- [x] Full API coverage (jobs, costs, results, config)
- [x] Frontend overhaul: Radix UI (shadcn/ui pattern) component library, Recharts, Zustand state, React Query
- [x] Code-split lazy loading for all 10 routes (React.lazy + Suspense)
- [x] Report viewer with markdown rendering, citation sidebar, copy-to-clipboard, export dropdown
- [x] Expert management UI (list experts, view stats, chat, knowledge gaps, learning history)
- [x] Research live page with WebSocket real-time progress updates
- [x] Trace explorer for inspecting execution spans, timing, and cost attribution
- [x] Overview dashboard with activity feed, system health, spending summary
- [x] Research studio with mode selector, model picker, web search toggle, drag-and-drop file upload, Ctrl+Enter submit
- [x] Cost intelligence page with per-model breakdown, budget sliders, anomaly detection
- [x] Command palette (Ctrl+K) for quick navigation
- [x] Toast notifications for user feedback (Sonner)
- [x] Flask-SocketIO backend with background poller thread for real-time job status push
- [x] Skeleton loading states replacing all spinners (CardGridSkeleton, DetailSkeleton, FormSkeleton)
- [x] Standardized all form controls to shadcn/ui components (Input, Select, Button)
- [x] Mobile hamburger navigation via Sheet component
- [x] FOUC prevention with critical CSS inline
- [x] Skip-to-content accessibility link
- [x] Stale job cleanup endpoint (POST /api/jobs/cleanup-stale)

#### Operational Analytics
The dashboard should show *posture* (what's working, what's failing, what we're learning) rather than just counts. These surface the decision records and quality metrics that the kernel already tracks.

- [ ] Cost vs quality frontier — scatter plot (x=cost, y=quality score, color=model) as the platform's north star chart
- [ ] Top failure modes breakdown (provider, prompt, tool, stopping) — where to focus reliability work
- [ ] Routing decisions summary — which models are being selected and why
- [ ] Expert gap velocity — gaps created vs closed over time
- [ ] Citation density and freshness — are sources getting stale?
- [ ] Recommended actions — actionable alerts: "Provider X degraded", "N experts stale (>30d) used recently", "Budget circuit breaker triggered", "Top gap worth filling (EV/cost)"

#### Core Improvements
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
- [ ] Comparison view (side-by-side research results with citation overlap)
- [ ] Research templates (save and reuse prompts)
- [ ] Bulk operations UI (batch submit, bulk cancel, bulk export)
- [ ] Expert diff view — claim-level changes after gap-fill or refresh, with new sources highlighted
- [ ] "Reuse" button on results — start new job seeded from existing report as context

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
- [x] Split profile operations into composed managers (`budget_manager.py`, `activity_tracker.py`)
- [x] Extract belief management to `experts/beliefs.py`
- [ ] Add profile versioning for schema migrations

#### Configuration Consolidation
- [x] Audit all config sources (`config.py`, `unified_config.py`, env vars, CLI flags)
- [x] Create single `Settings` class as source of truth (`core/settings.py`)
- [x] Deprecate duplicate config loading paths (legacy `load_config()` wrapper added)

#### Test Coverage
- [ ] Add integration tests for provider fallback
- [ ] Add performance regression tests
- [ ] Target: 80% coverage on core modules

---

## Build Order

Recommended sequence for remaining work. Phases 1-4 (polish, provider intelligence, advanced context, real-time progress) are complete — see [Changelog](docs/CHANGELOG.md) for details.

### Phase 5: Expert & Decision Formalization (Done — v2.8)
*Typed core abstractions composable across CLI/web/MCP*

| Item | Description | Status |
|------|-------------|--------|
| Expert contract | `ExpertManifest`, `Claim`, `Gap` types in `core/contracts.py` with `to_dict()`/`from_dict()` | Done |
| Gap EV/cost ranking | `gap_scorer.py` with `score_gap()` and `rank_gaps()`, EV/cost ratio in web + MCP | Done |
| Source provenance | `Source` with `TrustClass` enum, content hashes, extraction method | Done |
| Decision record schema | `DecisionRecord` with `DecisionType` enum, CLI table, trace sidebar, MCP | Done |
| MCP composability | `deepr_expert_manifest` and `deepr_rank_gaps` tools, web API endpoints | Done |

### Phase 6: MCP Client Mode
*Deepr as tool consumer, not just provider*

| Item | Description | Effort |
|------|-------------|--------|
| - | Implement MCP client connections (Stdio, SSE) | Large |
| - | Brave Search and Puppeteer adapters | Medium |
| - | Async task handling with progress monitoring | Large |
| - | Enhanced elicitation (human-in-the-loop) | Medium |

### Phase 7: Web Dashboard
*Operational analytics and advanced features*

| Item | Description | Effort | Status |
|------|-------------|--------|--------|
| - | Report viewer with markdown rendering | Medium | Done |
| - | Expert management UI | Medium | Done |
| - | Trace explorer | Medium | Done |
| - | Cost intelligence with charts | Medium | Done |
| - | Operational analytics (posture cards, cost-quality frontier, alerts) | Medium | Pending |
| - | Decision sidebar in trace explorer | Medium | Done |
| - | Expert diff view (claim-level changes after refresh) | Medium | Pending |
| - | Tags and folders for organizing research | Medium | Pending |
| - | Export results (PDF, DOCX) | Medium | Pending |
| - | Comparison view (side-by-side reports) | Medium | Pending |

### Phase 8: Team Features
*Multi-user deployment*

| Item | Description | Effort |
|------|-------------|--------|
| - | Authentication (JWT/OAuth) | Large |
| - | Team workspaces with shared libraries | Large |
| - | Role-based access and audit log | Medium |

### Phase 9: Security Hardening
*For production agentic deployments*

| Item | Description | Effort |
|------|-------------|--------|
| - | Permission boundaries (read-only default) | Medium |
| - | Execution isolation (sandboxed parsing) | Large |
| - | Cryptographic verification (stretch) | Large |

### Stretch Goals
*Nice to have, lower priority*

- README demo GIF (CLI research query + web dashboard)
- 7.4 TUI Dashboard (Textual-based)
- 8.x NVIDIA NIM Provider
- Skill marketplace and meta-skills
- Multi-agent swarm support
- Remote MCP (SSE, edge deployment)

---

## Non-Goals

Explicitly out of scope:

- **Chat interface** — Use ChatGPT, Claude, Gemini, etc. for conversational AI
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
| v2.8.1 | WebSocket push, background poller, UX overhaul (skeletons, shadcn, drag-drop, a11y) | Complete |
| v2.9 | Web analytics, expert diffs, team features | Planned |
| v2.10 | Team features (auth, workspaces) | Planned |
| v3.0+ | Self-improvement, autonomous learning | Future |

---

**Questions?** Open a [GitHub Discussion](https://github.com/blisspixel/deepr/discussions) or check the [documentation](docs/).

[MIT License](LICENSE) · [GitHub](https://github.com/blisspixel/deepr)
