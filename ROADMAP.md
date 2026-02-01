# Deepr Development Roadmap

> **Note**: Model and pricing information current as of January 31, 2026. AI evolves rapidly - verify at provider websites.

## Quick Links

- [Model Selection Guide](docs/MODELS.md) - Provider comparison, costs, when to use what
- [Expert System Guide](docs/EXPERTS.md) - Creating and using domain experts
- [Vision & Future](docs/VISION.md) - Aspirational features (v3.0+)
- [Architecture](docs/ARCHITECTURE.md) - Technical details, security, observability

---

## Current Status (v2.5)

### What Works

- Multi-provider support (OpenAI GPT-5.2, Gemini, Grok 4, Azure)
- Deep Research via OpenAI API (o3/o4-mini-deep-research)
- Semantic commands (`research`, `learn`, `team`, `check`, `make`)
- Expert system with autonomous learning
- Agentic expert chat (experts can trigger research)
- Knowledge synthesis and gap awareness
- MCP server for AI agent integration
- Multi-layer budget protection
- CLI and Web UI

### Recent Completions

- [x] Semantic command interface
- [x] Expert system foundation (create, chat, learn)
- [x] Autonomous learning with curriculum generation
- [x] Agentic research in expert chat
- [x] MCP Advanced Patterns (Dynamic Tool Discovery, Subscriptions, Elicitation)
- [x] Budget protection with pause/resume
- [x] 302+ tests passing

---

## Completed Priorities

### Priority 1: UX Polish (DONE)

- [x] Cross-platform path handling
- [x] Progress feedback during operations
- [x] `deepr doctor` diagnostics
- [x] Stale job status refresh
- [x] Consistent command patterns

### Priority 2: Semantic Commands (DONE)

- [x] `deepr research` with auto-mode detection
- [x] `deepr learn` for multi-phase learning
- [x] `deepr team` for multi-perspective analysis
- [x] `deepr check` for fact verification
- [x] `deepr make docs/strategy` for artifact generation

### Priority 2.5: Expert System (DONE)

- [x] Expert creation with document ingestion
- [x] Agentic chat with research triggers
- [x] Knowledge gap detection and filling
- [x] Export/import for sharing

### Priority 3: MCP Integration (DONE)

- [x] Core MCP server implementation
- [x] Dynamic tool discovery (85% context reduction)
- [x] Resource subscriptions (70% token savings)
- [x] Human-in-the-loop elicitation

---

## Active Priorities

### Priority 4: Observability (IN PROGRESS)

**What exists:** TraceContext, Span, MetadataEmitter, ThoughtStream infrastructure

#### 4.1 CLI Flags for Trace Visibility
- [ ] Add `--explain` flag to `deepr research` - shows decision summary at end
- [ ] Add `--timeline` flag - shows chronological operation breakdown  
- [ ] Add `--full-trace` flag - dumps complete trace JSON to file
- [ ] Wire flags through to MetadataEmitter in `cli/commands/run.py`

#### 4.2 Auto-Generated Metadata
- [ ] Instrument `core/research.py` to emit spans for each phase (plan/search/analyze/synthesize)
- [ ] Instrument `experts/chat.py` to emit spans for tool calls
- [ ] Add cost attribution to each span (tracked but not always emitted)
- [ ] Add token counts to spans

#### 4.3 Cost Attribution Dashboard
- [ ] Create `deepr cost breakdown` command showing cost by operation type
- [ ] Create `deepr cost timeline` showing cost over time (daily/weekly/monthly)
- [ ] Add cost breakdown to report metadata
- [ ] Show cost per expert, per research type

#### 4.4 Decision Logs in Natural Language
- [ ] Extend ThoughtStream to generate human-readable summaries
- [ ] Add `--why` flag that explains model/provider selection reasoning
- [ ] Store decision logs alongside reports in `reports/*/decisions.md`

---

### Priority 5: Provider Routing (TODO)

**What exists:** AutonomousProviderRouter with scoring, fallback, circuit breakers (not wired into main flow)

#### 5.1 Real-Time Performance Benchmarking
- [ ] Add latency percentiles (p50, p95, p99) to ProviderMetrics
- [ ] Track success rate by task type (research vs chat vs synthesis)
- [ ] Add `deepr providers benchmark` command to run test queries
- [ ] Store benchmark history for trend analysis

#### 5.2 Auto-Fallback on Provider Failures
- [ ] Wire AutonomousProviderRouter into `cli/commands/run.py` (currently static selection)
- [ ] Add retry with fallback in `_run_single()` when provider fails
- [ ] Emit fallback events to trace for visibility
- [ ] Add `--no-fallback` flag to disable for debugging

#### 5.3 Continuous Optimization
- [ ] Implement exploration vs exploitation for new models (10% exploration)
- [ ] A/B testing mode: randomly try alternatives, track results
- [ ] Add `deepr providers status` showing health of all configured providers
- [ ] Auto-disable providers with >50% failure rate

---

### Priority 6: Context Discovery (TODO)

**What exists:** Reports stored with metadata, ContextBuilder service

#### 6.1 Detect Related Prior Research
- [ ] Index report metadata (topic, date, cost, summary) in SQLite
- [ ] Add semantic similarity search across report summaries using embeddings
- [ ] Create `deepr search "topic"` to find related reports
- [ ] Show similarity scores and dates

#### 6.2 Notify-Only (Never Auto-Inject)
- [ ] Show "Related research found" message before starting new research
- [ ] Display: "Found 3 related reports from last 30 days. Use --context to include."
- [ ] Add `--ignore-related` flag to skip notification

#### 6.3 Explicit Reuse with Warnings
- [ ] Add `--context <report-id>` flag for explicit context reuse
- [ ] Warn if reusing stale context (>30 days old)
- [ ] Show cost savings estimate when reusing context
- [ ] Track context lineage in report metadata (which reports built on which)

---

### Priority 7: Modern CLI UX (NEW)

**Problem:** Current CLI feels like 2020 - wall of text output, no interactivity, no streaming.

#### 7.1 Minimal Default Output
- [ ] Default to quiet mode: `✓ Research complete (2m 15s, $0.42) → reports/abc123/`
- [ ] Move current verbose output to `--verbose` flag
- [ ] Add `--json` flag for machine-readable output (for scripting/piping)
- [ ] Add `--quiet` flag for zero output except errors

#### 7.2 Interactive Mode
- [ ] `deepr` with no args → interactive menu using `questionary` or `InquirerPy`
- [ ] `deepr research` with no query → prompt for query interactively
- [ ] Recent queries autocomplete (store last 20 queries)
- [ ] Provider/model picker with cost estimates
- [ ] Budget confirmation as interactive prompt, not y/n

#### 7.3 Real-Time Progress for Long Operations
- [ ] Poll OpenAI deep research status API and show phase progress
- [ ] Display: "Searching... (12 sources found)" → "Analyzing..." → "Synthesizing..."
- [ ] Stream partial results when API supports it
- [ ] Show ETA based on historical job durations
- [ ] Progress bar for multi-phase operations

#### 7.4 TUI Dashboard (Stretch Goal)
- [ ] `deepr ui` → opens Textual-based terminal UI
- [ ] Dashboard showing: active jobs, recent results, budget status
- [ ] Live updating job status
- [ ] Keyboard navigation (j/k for up/down, enter to view)
- [ ] Split pane: job list | job details

#### 7.5 Command Consolidation
- [ ] Remove deprecated command aliases (`run single`, `run campaign`)
- [ ] Consolidate to three top-level commands:
  - `deepr research "query"` - all research operations
  - `deepr jobs` - job management (list, status, cancel, get)
  - `deepr expert` - expert system
- [ ] Add `deepr config` for settings (budget, default provider, etc.)
- [ ] Update all documentation to reflect simplified commands

#### 7.6 Output Improvements
- [ ] Remove `======` separator walls
- [ ] Use subtle dividers (single line, dim color)
- [ ] Consistent key-value formatting across all commands
- [ ] Truncate long outputs with "... (use --full to see all)"
- [ ] Hyperlinks to reports in terminals that support them (iTerm2, Windows Terminal)

---

### Priority 8: NVIDIA Provider (LATER)

Support for self-hosted NVIDIA NIM infrastructure. Only for enterprises with existing NVIDIA deployments.

- [ ] NIM API client implementation
- [ ] Model registry entries for NIM models
- [ ] Documentation for self-hosted setup

---

## Code Quality

### Completed
- [x] Custom exception hierarchy (`deepr/core/errors.py`)
- [x] Embedding cache for search optimization
- [x] Test organization cleanup
- [x] Performance documentation
- [x] Security documentation

### TODO

#### ExpertProfile Refactoring
- [ ] Split `experts/profile.py` into `profile.py` (data) and `profile_manager.py` (operations)
- [ ] Extract belief management to `experts/beliefs_manager.py`
- [ ] Add profile versioning for schema migrations
- [ ] Add profile validation on load

#### Configuration Consolidation
- [ ] Audit all config sources (`config.py`, `unified_config.py`, env vars, CLI flags)
- [ ] Create single `Settings` class as source of truth
- [ ] Deprecate duplicate config loading paths
- [ ] Add `deepr config show` to display effective configuration

#### Test Coverage
- [ ] Add integration tests for provider fallback
- [ ] Add tests for CLI interactive mode
- [ ] Add performance regression tests
- [ ] Target: 80% coverage on core modules

---

## Build Order

Recommended implementation sequence:

1. **7.1 Minimal Default Output** - Quick win, improves UX immediately
2. **4.1 CLI Trace Flags** - Infrastructure exists, just needs CLI wiring
3. **5.2 Auto-Fallback** - Router exists, needs integration
4. **7.2 Interactive Mode** - High user value
5. **4.3 Cost Dashboard** - Data exists, needs CLI
6. **6.1 Context Discovery** - New feature, moderate effort
7. **7.3 Real-Time Progress** - Depends on API capabilities
8. **7.4 TUI Dashboard** - Stretch goal, nice to have

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

We use Deepr to build Deepr:
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
| v2.6 | Observability | In Progress |
| v2.7 | Modern CLI UX | Planned |
| v2.8 | Provider routing | Planned |
| v3.0+ | Self-improvement | Future |

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
