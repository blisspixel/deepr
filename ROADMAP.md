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
- [ ] Add `--explain` flag to `deepr research`
  - [ ] Create `ExplainFormatter` class in `cli/output.py`
  - [ ] Collect decision points during research execution
  - [ ] Format as bullet list: "Used GPT-5.2 because: cost < $1, task=planning"
  - [ ] Show at end of command, before result path
- [ ] Add `--timeline` flag
  - [ ] Create `TimelineFormatter` class
  - [ ] Track start/end timestamps for each phase
  - [ ] Format: `[00:00] Planning (2.3s) → [00:02] Searching (45.1s) → ...`
  - [ ] Include cost per phase in timeline
- [ ] Add `--full-trace` flag
  - [ ] Dump complete trace to `reports/{job_id}/trace.json`
  - [ ] Include all spans, metadata, token counts
  - [ ] Add `--trace-output <path>` for custom location
- [ ] Wire flags through to MetadataEmitter in `cli/commands/run.py`
  - [ ] Add flags to Click command decorator
  - [ ] Pass flags to research orchestrator
  - [ ] Ensure backward compatibility (no flags = current behavior)

#### 4.2 Auto-Generated Metadata
- [ ] Instrument `core/research.py` to emit spans
  - [ ] Add `@traced("plan")` decorator to planning phase
  - [ ] Add `@traced("search")` decorator to search phase
  - [ ] Add `@traced("analyze")` decorator to analysis phase
  - [ ] Add `@traced("synthesize")` decorator to synthesis phase
- [ ] Instrument `experts/chat.py` to emit spans for tool calls
  - [ ] Wrap each tool invocation in span context
  - [ ] Record tool name, arguments, result size
  - [ ] Track tool call duration
- [ ] Add cost attribution to each span
  - [ ] Calculate cost from token counts + model pricing
  - [ ] Store in span metadata: `{"cost_usd": 0.042, "tokens_in": 1500, "tokens_out": 800}`
  - [ ] Aggregate costs up the span tree
- [ ] Add token counts to spans
  - [ ] Track input tokens (prompt)
  - [ ] Track output tokens (completion)
  - [ ] Track cached tokens (if applicable)

#### 4.3 Cost Attribution Dashboard
- [ ] Create `deepr cost breakdown` command
  - [ ] Query cost data from SQLite
  - [ ] Group by: operation type, provider, model, expert
  - [ ] Format as table with totals
  - [ ] Add `--period` flag (today, week, month, all)
- [ ] Create `deepr cost timeline` command
  - [ ] Show daily/weekly/monthly cost trends
  - [ ] ASCII chart or simple table format
  - [ ] Highlight anomalies (days > 2x average)
- [ ] Add cost breakdown to report metadata
  - [ ] Store in `reports/{job_id}/metadata.json`
  - [ ] Include: total_cost, cost_by_phase, cost_by_model
- [ ] Show cost per expert, per research type
  - [ ] Add `deepr expert costs "Expert Name"` subcommand
  - [ ] Track learning vs chat vs research costs separately

#### 4.4 Decision Logs in Natural Language
- [ ] Extend ThoughtStream to generate human-readable summaries
  - [ ] Convert structured decisions to prose
  - [ ] Example: "Selected Grok 4 for this query because it's 10x cheaper than GPT-5.2 and the task is simple lookup."
- [ ] Add `--why` flag
  - [ ] Show model selection reasoning inline
  - [ ] Show provider fallback reasoning if triggered
  - [ ] Show budget decisions (why paused, why continued)
- [ ] Store decision logs alongside reports
  - [ ] Write to `reports/{job_id}/decisions.md`
  - [ ] Include timestamps and context
  - [ ] Link to relevant spans in trace.json

---

### Priority 5: Provider Routing (TODO)

**What exists:** AutonomousProviderRouter with scoring, fallback, circuit breakers (not wired into main flow)

#### 5.1 Real-Time Performance Benchmarking
- [ ] Add latency percentiles to ProviderMetrics
  - [ ] Track p50, p95, p99 latency per provider
  - [ ] Use sliding window (last 100 requests)
  - [ ] Store in SQLite for persistence
- [ ] Track success rate by task type
  - [ ] Categories: research, chat, synthesis, planning
  - [ ] Calculate success rate per provider per category
  - [ ] Weight recent results higher (exponential decay)
- [ ] Add `deepr providers benchmark` command
  - [ ] Run standardized test queries against each provider
  - [ ] Measure: latency, token throughput, error rate
  - [ ] Output comparison table
  - [ ] Add `--quick` flag for fast smoke test
- [ ] Store benchmark history for trend analysis
  - [ ] Save each benchmark run with timestamp
  - [ ] Show trends: "GPT-5.2 latency increased 20% this week"
  - [ ] Alert on significant degradation

#### 5.2 Auto-Fallback on Provider Failures
- [ ] Wire AutonomousProviderRouter into `cli/commands/run.py`
  - [ ] Replace static provider selection with router
  - [ ] Pass task type hint to router for optimal selection
  - [ ] Respect `--provider` flag as override
- [ ] Add retry with fallback in `_run_single()`
  - [ ] On timeout: retry once, then fallback
  - [ ] On rate limit: immediate fallback
  - [ ] On auth error: skip provider, log warning
  - [ ] Max 3 fallback attempts before failure
- [ ] Emit fallback events to trace
  - [ ] Log: original provider, failure reason, fallback provider
  - [ ] Include in `--explain` output
  - [ ] Track fallback frequency per provider
- [ ] Add `--no-fallback` flag
  - [ ] Fail immediately on provider error
  - [ ] Useful for debugging provider-specific issues
  - [ ] Show clear error message with provider name

#### 5.3 Continuous Optimization
- [ ] Implement exploration vs exploitation
  - [ ] 90% exploitation: use best known provider
  - [ ] 10% exploration: try alternatives to gather data
  - [ ] Configurable ratio via `DEEPR_EXPLORATION_RATE`
  - [ ] Disable exploration with `--no-explore` flag
- [ ] A/B testing mode
  - [ ] `deepr providers ab-test "query" --providers gpt-5.2,grok-4`
  - [ ] Run same query on multiple providers
  - [ ] Compare: latency, cost, output quality (manual rating)
  - [ ] Store results for future reference
- [ ] Add `deepr providers status` command
  - [ ] Show all configured providers
  - [ ] Status: healthy, degraded, disabled, unconfigured
  - [ ] Last success/failure timestamp
  - [ ] Current circuit breaker state
- [ ] Auto-disable failing providers
  - [ ] Threshold: >50% failure rate over 10 requests
  - [ ] Auto-re-enable after 1 hour cooldown
  - [ ] Manual override: `deepr providers enable <name>`
  - [ ] Log disable/enable events

---

### Priority 6: Context Discovery (TODO)

**What exists:** Reports stored with metadata, ContextBuilder service

#### 6.1 Detect Related Prior Research
- [ ] Index report metadata in SQLite
  - [ ] Create `report_index` table: id, topic, date, cost, summary_embedding
  - [ ] Index on creation (hook into report save)
  - [ ] Backfill existing reports with `deepr index rebuild`
- [ ] Add semantic similarity search
  - [ ] Generate embeddings for report summaries (first 500 chars)
  - [ ] Use cosine similarity for matching
  - [ ] Cache embeddings to avoid recomputation
  - [ ] Threshold: similarity > 0.7 = related
- [ ] Create `deepr search "topic"` command
  - [ ] Search by keyword (title, summary)
  - [ ] Search by semantic similarity
  - [ ] Combine results, deduplicate
  - [ ] Output: report ID, date, similarity score, summary snippet
- [ ] Show similarity scores and dates
  - [ ] Format: `[0.85] 2026-01-15 - PostgreSQL connection pooling strategies`
  - [ ] Sort by relevance (similarity) by default
  - [ ] Add `--sort date` for chronological

#### 6.2 Notify-Only (Never Auto-Inject)
- [ ] Show "Related research found" message
  - [ ] Check for related reports before starting research
  - [ ] Display count and top 3 matches
  - [ ] Non-blocking: research continues after message
- [ ] Display actionable hint
  - [ ] "Found 3 related reports from last 30 days."
  - [ ] "Use --context <id> to include previous findings."
  - [ ] "Use --ignore-related to skip this check."
- [ ] Add `--ignore-related` flag
  - [ ] Skip the similarity check entirely
  - [ ] Useful for intentionally fresh research
  - [ ] Persists in config: `deepr config set ignore_related true`

#### 6.3 Explicit Reuse with Warnings
- [ ] Add `--context <report-id>` flag
  - [ ] Load previous report summary into context
  - [ ] Prepend to research prompt: "Building on previous research: ..."
  - [ ] Support multiple: `--context id1 --context id2`
- [ ] Warn if reusing stale context
  - [ ] Threshold: >30 days old
  - [ ] Warning: "Context from 45 days ago may be outdated. Continue? [y/N]"
  - [ ] Override with `--force`
- [ ] Show cost savings estimate
  - [ ] Calculate: "Reusing context saves ~$0.50 in search costs"
  - [ ] Based on historical cost of similar queries
- [ ] Track context lineage in report metadata
  - [ ] Store: `{"built_on": ["report-abc", "report-xyz"]}`
  - [ ] Show lineage in `deepr jobs status <id>`
  - [ ] Enable "research genealogy" queries
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

### Priority 9: MCP Ecosystem Integration (NEW)

**What exists:** Basic MCP server with tool discovery, subscriptions, elicitation

**Already implemented (from Priority 3):**
- Dynamic Tool Discovery (85% context reduction)
- Resource Subscriptions (70% token savings)
- Human-in-the-Loop Elicitation
- Sandboxed Execution contexts

**Goal:** Transform Deepr from standalone tool into a first-class citizen of the agentic AI ecosystem (OpenClaw, Claude Desktop, IDE integrations)

#### 9.1 Enhanced MCP Server Architecture
- [ ] Implement Job Pattern for async research
  - [ ] `start_research()` returns `{job_id, status, estimated_time}` immediately
  - [ ] `get_job_status(job_id)` for polling progress
  - [ ] `cancel_job(job_id)` for user-initiated cancellation
  - [ ] Store job state in SQLite for persistence across restarts
  - [ ] Add job timeout handling (configurable, default 30 min)
  - [ ] Make jobs resumable after Gateway/OpenClaw restart
- [ ] Expose reports as MCP Resources
  - [ ] `deepr://reports/{job_id}/final.md` - polished output
  - [ ] `deepr://reports/{job_id}/summary.json` - structured metadata
  - [ ] `deepr://logs/{job_id}/search_trace.json` - query history for provenance
  - [ ] `deepr://logs/{job_id}/decisions.md` - reasoning log
  - [ ] `deepr://cache/{url_hash}` - raw source content (optional, for verification)
- [ ] Progress notifications via MCP protocol
  - [ ] Emit `notifications/progress` events during research phases
  - [ ] Include phase name, percentage, current action description
  - [ ] Support both polling and push notification patterns
  - [ ] Event-driven bus: QueryReceived -> PlanCreated -> DataFound -> ReadingComplete -> SynthesisComplete
- [ ] Structured error responses
  - [ ] Return errors as structured objects, not exceptions
  - [ ] Include error_code, message, retry_hint, fallback_suggestion
  - [ ] Graceful degradation when sub-operations fail
  - [ ] Never raise uncaught exceptions in tools (return error strings instead)

#### 9.2 AgentSkill Packaging for Distribution
- [ ] Create SKILL.md metadata file
  - [ ] YAML frontmatter: name, description, license, authors, version
  - [ ] Compatibility matrix: os (darwin, linux, win32), python version
  - [ ] Required environment variables list
  - [ ] Required binaries (python3, uv)
  - [ ] `requires.bins` validation (OpenClaw refuses to load if missing)
  - [ ] `requires.env` validation (warn if API keys missing)
- [ ] LLM-optimized tool descriptions
  - [ ] Add usage hints in tool docstrings ("Use when user asks for comprehensive analysis")
  - [ ] Add parameter guidance ("For financial topics, set depth=4 and breadth=6")
  - [ ] Add negative guidance ("Do not use for simple factual lookups")
  - [ ] Include example invocations in descriptions
  - [ ] Flatten nested Pydantic models for maximum client compatibility
- [ ] Prompt primitives for template menus
  - [ ] Implement `@mcp.prompt("deep_research_task")` decorator
  - [ ] Create standard research prompt templates
  - [ ] Allow users to select from template menu in Claude Desktop
- [ ] Installation and validation
  - [ ] Create `install.sh` / `install.ps1` scripts
  - [ ] Validate Python version and dependencies on load
  - [ ] Check for required API keys, warn if missing
  - [ ] Health check endpoint for runtime validation (`deepr_status` tool)
- [ ] Package structure
  - [ ] `~/.openclaw/skills/deepr-research/SKILL.md`
  - [ ] `~/.openclaw/skills/deepr-research/server.py`
  - [ ] `~/.openclaw/skills/deepr-research/requirements.txt`
  - [ ] Create GitHub release workflow for skill distribution
  - [ ] Add to ClawHub / skill registry (when available)

#### 9.3 MCP Client Mode (Deepr as Tool Consumer)
- [ ] Implement MCP client connection manager
  - [ ] Connect to local MCP servers via Stdio transport
  - [ ] Connect to remote MCP servers via SSE transport
  - [ ] Handle connection lifecycle (init, reconnect, cleanup)
  - [ ] Cache tool schemas from connected servers
- [ ] Swappable search backends
  - [ ] Abstract search interface in `deepr/tools/search.py`
  - [ ] Brave Search MCP adapter (`@modelcontextprotocol/server-brave-search`)
  - [ ] Tavily MCP adapter (when available)
  - [ ] Google Custom Search MCP adapter
  - [ ] Config option: `search_backend: "brave-mcp" | "tavily-mcp" | "builtin"`
- [ ] Swappable browser backends
  - [ ] Abstract browser interface in `deepr/tools/browser.py`
  - [ ] Puppeteer MCP adapter for JavaScript-heavy sites
  - [ ] Playwright MCP adapter alternative
  - [ ] Config option: `browser_backend: "builtin" | "puppeteer-mcp" | "playwright-mcp"`
- [ ] Recursive agent composition
  - [ ] Offload summarization to cheaper models via sub-agent (gpt-4o-mini)
  - [ ] Delegate PDF reading to specialized tool
  - [ ] Config for sub-agent model selection
  - [ ] Cost optimization: use expensive models for synthesis, cheap for reading
- [ ] Development workflow
  - [ ] Document MCP Inspector testing (`npx @modelcontextprotocol/inspector`)
  - [ ] Test server in isolation before OpenClaw integration
  - [ ] Add trace_id propagation for debugging across tool calls

#### 9.4 Security Hardening for Autonomous Operation
- [ ] Docker deployment option
  - [ ] Create `Dockerfile` with minimal attack surface
  - [ ] Non-root user execution (UID 1000)
  - [ ] Document volume mount strategy (workspace only)
  - [ ] Network isolation: prefer bridge over host mode
  - [ ] Add `docker-compose.yml` for easy deployment
- [ ] Path traversal protection
  - [ ] Validate all file paths against workspace root
  - [ ] Block access to `~/.ssh`, `~/.aws`, etc.
  - [ ] Implement safe path resolution utility:
    ```python
    safe_root = Path("~/.openclaw/workspace").resolve()
    target = (safe_root / filename).resolve()
    if safe_root not in target.parents:
        raise SecurityError("Path traversal blocked")
    ```
  - [ ] Add tests for path traversal attempts
- [ ] Network security
  - [ ] Block requests to internal IPs (127.0.0.0/8, 192.168.0.0/16, 10.0.0.0/8)
  - [ ] Allowlist mode for outbound domains (optional)
  - [ ] Rate limiting for external requests
  - [ ] Log all outbound requests for audit
- [ ] Human-in-the-loop sampling
  - [ ] Implement MCP Sampling primitive for user confirmation
  - [ ] Pause on CAPTCHA detection, request user help
  - [ ] Pause on paywall detection, offer alternatives
  - [ ] Configurable sensitivity levels (always-ask, smart, never-ask)

#### 9.5 Claude-Specific Optimizations
- [ ] Chain of Thought prompting
  - [ ] Add `<thinking>` tag guidance in SKILL.md instructions
  - [ ] Encourage parameter reasoning before tool invocation
  - [ ] Add "explain your search strategy" to tool descriptions
  - [ ] Force System 2 check: "When using this tool, first explain your strategy"
- [ ] Structured output formatting
  - [ ] Return complex results in XML tags for better parsing
  - [ ] `<research_result>`, `<summary>`, `<key_sources>`, `<resource_link>`
  - [ ] Add schema documentation for structured outputs
- [ ] Context window management
  - [ ] Return summary + resource URI for large outputs (lazy loading)
  - [ ] Implement "lazy loading" pattern (agent fetches details on demand)
  - [ ] Add `max_response_tokens` config option
  - [ ] Truncation with "use resource URI for full content" hint
  - [ ] Example: "Key points: A, B, C. Full 15,000 word doc at deepr://reports/xyz"

#### 9.6 OpenClaw Configuration Templates
- [ ] Create `mcp/openclaw-config.json` template
  - [ ] Stdio transport configuration (local)
  - [ ] SSE transport configuration (remote)
  - [ ] Environment variable injection
  - [ ] autoAllow settings for common tools
- [ ] Create `mcp/claude-desktop-config.json` template
- [ ] Documentation for each runtime environment
  - [ ] OpenClaw setup guide
  - [ ] Claude Desktop setup guide
  - [ ] VS Code / Cursor setup guide
  - [ ] Zed setup guide

#### 9.7 Future MCP Directions (Stretch Goals)
- [ ] Multi-agent swarm support
  - [ ] Specialized variants: Deepr-Finance, Deepr-Code
  - [ ] OpenClaw as "Manager Agent" routing to specialists
  - [ ] Tool definitions for domain-specific research
- [ ] Remote MCP and edge deployment
  - [ ] SSE transport for cloud-hosted Deepr
  - [ ] Cloudflare Workers deployment option
  - [ ] Parallel research instances (50+ concurrent)
  - [ ] Config switch: `command` (local) vs `url` (remote)
- [ ] Memory integration
  - [ ] "You researched X last week, use cached results?"
  - [ ] Integration with OpenClaw Memory MCP Server
  - [ ] Local Vector DB option (Chroma/FAISS)
  - [ ] Cross-session knowledge persistence

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
8. **9.1 Enhanced MCP Server** - Job pattern enables better agent integration
9. **9.2 AgentSkill Packaging** - Distribution for OpenClaw/Claude Desktop
10. **9.4 Security Hardening** - Required before public skill distribution
11. **9.5 Claude-Specific Optimizations** - Better LLM integration
12. **9.6 OpenClaw Configuration Templates** - User onboarding
13. **7.4 TUI Dashboard** - Stretch goal, nice to have
14. **9.3 MCP Client Mode** - Advanced, enables swappable backends
15. **9.7 Future MCP Directions** - Stretch goals (swarms, edge, memory)

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
| v2.9 | MCP Ecosystem | Planned |
| v3.0+ | Self-improvement | Future |

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
