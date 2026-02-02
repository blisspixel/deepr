# Deepr Development Roadmap

> **Note**: Model and pricing information current as of February 2026. AI evolves rapidly - verify at provider websites.

## Quick Links

- [Model Selection Guide](docs/MODELS.md) - Provider comparison, costs, when to use what
- [Expert System Guide](docs/EXPERTS.md) - Creating and using domain experts
- [Vision & Future](docs/VISION.md) - Aspirational features (v3.0+)
- [Architecture](docs/ARCHITECTURE.md) - Technical details, security, observability
- [Changelog](docs/CHANGELOG.md) - Detailed release history

---

## Current Status (v2.6)

Multi-provider research automation with expert system, MCP integration, and observability. 2800+ tests passing.

### What Works

- Multi-provider support (OpenAI GPT-5.2, Gemini, Grok 4, Azure)
- Deep Research via OpenAI API (o3/o4-mini-deep-research)
- Semantic commands (`research`, `learn`, `team`, `check`, `make`)
- Expert system with autonomous learning, agentic chat, knowledge synthesis
- MCP server with 10 tools, persistence, security, multi-runtime configs
- CLI trace flags (`--explain`, `--timeline`, `--full-trace`)
- Output modes (`--verbose`, `--json`, `--quiet`)
- Auto-fallback on provider failures with `--no-fallback` override
- Cost dashboard (`costs timeline`, `costs breakdown --period`, `costs expert`)
- Multi-layer budget protection with pause/resume
- Docker deployment option

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

### Priority 9: MCP Ecosystem (remaining)

**What exists:** Full MCP server with 10 tools, persistence, security, skill packaging, Docker, multi-runtime configs.

#### 9.2 Distribution (remaining)
- [ ] GitHub release workflow for skill distribution
- [ ] Add to ClawHub / skill registry (when available)

#### 9.3 MCP Client Mode (Deepr as Tool Consumer)
- Design complete (SearchBackend, BrowserBackend protocols, architecture doc)
- [ ] Implement MCP client connections (Stdio, SSE transports)
- [ ] Brave Search and Puppeteer/Playwright MCP adapters
- [ ] Recursive agent composition for sub-agent summarization

#### 9.4 Security (remaining)
- [ ] Wire sampling into web scraper (CAPTCHA/paywall detection)
- [ ] Rate limiting for external requests

#### 9.5 Structured Output (remaining)
- [ ] XML tags for complex results (not yet needed)

#### 9.7 Future MCP Directions (Stretch)
- [ ] Multi-agent swarm support (specialized variants, manager routing)
- [ ] Remote MCP and edge deployment (SSE, Cloudflare Workers)
- [ ] Memory integration (cross-session persistence, vector DB)

---

## Code Quality

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

1. **7.2 Interactive Mode** - High user value
2. **6.1 Context Discovery** - New feature, moderate effort
3. **4.2 Auto-Generated Metadata** - Observability depth
4. **7.3 Real-Time Progress** - Depends on API capabilities
5. **5.1 Provider Benchmarking** - Data-driven routing
6. **9.3 MCP Client Mode** - Design done, connections not yet built
7. **7.4 TUI Dashboard** - Stretch goal
8. **9.7 Future MCP Directions** - Stretch goals

---

## Model Strategy

**Dual approach: Deep Research + Fast Models**

| Use Case | Model | Cost | When |
|----------|-------|------|------|
| Deep Research | o4-mini-deep-research | $0.50-2.00 | Complex analysis (~20%) |
| Planning | GPT-5.2 | $0.20-0.30 | Curriculum, synthesis |
| Quick ops | Grok 4 Fast | $0.01 | Lookups, chat (~80%) |
| Large docs | Gemini 3 Pro | $0.15 | 1M token context |

Using fast models for 80% of operations reduces costs by ~90%.

See [docs/MODELS.md](docs/MODELS.md) for full guide.

---

## Budget Protection

Multi-layer controls prevent runaway costs:

**Hard Limits:**
- Per operation: $10 max
- Per day: $50 max
- Per month: $500 max

**Features:**
- Session budgets with alerts at 50%, 80%, 95%
- Circuit breaker after repeated failures
- Pause/resume for long-running operations
- CLI validation for high budgets

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#cost-safety) for details.

---

## Non-Goals

Not building:
- Chat interface (use ChatGPT)
- Real-time responses (deep research takes minutes)
- Sub-$1 research (comprehensive research costs money)
- Mobile apps
- Complex export formats
- Features that might not work reliably

---

## Philosophy

Every feature should:
- Support long-running research workflows
- Build context across phases
- Synthesize from multiple sources
- Work across providers

Focus on intelligence layer (planning, synthesis, routing), not infrastructure.

---

## Contributing

High-value areas:
- Context chaining logic
- Synthesis prompts
- Cost optimization
- Provider integrations
- CLI UX improvements

Most impactful work is on intelligence layer and user experience.

---

## Dogfooding

Deepr is used to build Deepr:
- Research implementation questions
- Get comprehensive answers with citations
- Implement based on findings
- Document the research

Example: "Research best practices for context injection in multi-step LLM workflows"
- Cost: $0.17
- Result: 15KB report with citations
- Impact: Validated ContextBuilder design

---

## Future Vision

See [docs/VISION.md](docs/VISION.md) for aspirational features:
- Visible thinking (show reasoning)
- Persistent memory (remember across sessions)
- Graph-based knowledge (relationship-aware retrieval)
- Self-improving experts
- Expert councils

---

## Version History

| Version | Focus | Status |
|---------|-------|--------|
| v2.0 | Core infrastructure | Complete |
| v2.1 | Adaptive research workflow | Complete |
| v2.2 | Semantic commands | Complete |
| v2.3 | Expert system | Complete |
| v2.4 | MCP integration | Complete |
| v2.5 | Agentic experts | Complete |
| v2.6 | MCP Ecosystem + Observability | In Progress |
| v2.7 | Modern CLI UX | Planned |
| v2.8 | Provider routing | Planned |
| v3.0+ | Self-improvement | Future |

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
