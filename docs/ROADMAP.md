# Deepr Development Roadmap

**Mission:** Research infrastructure for humans and AI agents to learn and advance at scale.

Deepr is the open-source, multi-provider platform for deep research automation. This roadmap outlines our path from adaptive planning (Level 3) toward more autonomous, self-improving research systems (Level 4-5).

## What's Going On - CLI Command Structure (November 2025)

**Problem:** Two competing entry points and mixed command grammar

**Current State:**
- `run` is the real, local, queue-backed executor with subcommands `single | campaign | team`
- `research.py` exists with `submit/status/get`, but it is NOT wired into main.py. It's effectively dead code from an older, provider-specific flow
- Mixed command grammar: Verbs-as-commands (`run`, `status`, `get`, `list`, `cancel`) + Noun groups (`budget`, `cost`, `analytics`, `vector`, `templates`)
- Jargon: `single`, `campaign`, `team` are not self-explanatory
- Roadmap tension: Phase-2 envisions `research --mode focus|project|team|documentation`, but there's already an unused `research.py`. Naming collision + migration ambiguity

**Recommendation (minimal breakage, maximal clarity):**

1. **Keep `run` as execution verb, rename modes to match intent**
   - `deepr run focus` (was `single`) - Quick, focused research
   - `deepr run project` (was `campaign`) - Multi-phase, context-chained
   - `deepr run team` (unchanged semantics, multi-perspective research)
   - `deepr run docs` (new: documentation-oriented research)
   - Provide aliases for backward compatibility: `single -> focus`, `campaign -> project`

2. **Make job management a single noun group: `jobs`**
   - `deepr jobs list`
   - `deepr jobs status <job-id>`
   - `deepr jobs get <job-id>`
   - `deepr jobs cancel <job-id>`
   - Add compatibility shims for current commands with deprecation warnings

3. **Resolve research.py**
   - **Option A (preferred):** Delete `research.py`. Fold anything useful into `run` and `jobs`. Avoids two top-level concepts doing the same thing
   - **Option B:** Make `research` canonical and turn `run` into alias. More churn
   - **Decision:** Option A is simpler and avoids breaking current usage

4. **Keep stable noun groups**
   - `deepr budget`, `cost`, `analytics`, `config`, `templates`, `vector`, `docs`, `migrate`, `interactive`
   - Consider folding `prep` into `deepr run project --plan-only` or renaming to `deepr plan`

**Migration Plan (low risk):**
- **Release N:** Add new subcommands and `jobs` group. Keep old commands as aliases with deprecation notices
- **Release N:** Update --help, README, examples to show new structure
- **Release N+1:** Delete `research.py` or integrate its bits
- **Release N+2:** Remove deprecated aliases once telemetry shows low usage

## Current Status

### v2.3 - Multi-Provider Support (In Development - October 30, 2025)

**Production-Ready Features:**

**Multi-Provider Architecture**
- OpenAI Deep Research API (o3, o4-mini) - Validated, production-ready
- Google Gemini Thinking Models (2.5-flash, 2.5-pro, 2.5-flash-lite) - Validated, production-ready
- Azure OpenAI (o3, o4-mini) - Production-ready, enterprise deployment
- xAI Grok (4-fast, 4, 3-mini) - In development, requires chat adapter
- Provider-agnostic architecture ready for future additions

**CLI Improvements (October 30, 2025)**
- Fixed critical bug: Jobs now properly submit to provider APIs
- Provider-specific parameter handling (background, metadata, tools)
- Gemini synchronous execution with immediate results
- Cost tracking per provider with token usage
- Provider selection via --provider flag
- NEW: Complete CLI restructure implemented (focus, project, docs, jobs)
- NEW: Unified jobs command group for job management
- NEW: Documentation-oriented research mode
- Backward compatibility maintained with deprecation warnings

**Bug Fixes (October 30, 2025)**
- Fixed 5 bugs in job status retrieval from providers (deepr jobs get)
  - create_storage() missing storage_type parameter
  - save_report() incorrect signature
  - ResearchResponse.output parsing (list of dicts, not string)
  - queue.update_job() method doesn't exist (use update_status/update_results)
  - ReportMetadata.path doesn't exist (use .url)
- Fixed 2 bugs in OpenAI tool configuration
  - web_search_preview tool missing required container parameter
  - Added validation for deep research models requiring at least one tool
  - Prevents confusing API errors when using --no-web --no-code flags

**Core Research Capabilities**
- Focused research jobs (`deepr run focus`) - All providers
- Multi-phase projects (`deepr run project`) - OpenAI validated
  - GPT-5 as research lead, reviewing and planning
  - Context chaining with automatic summarization
  - Adaptive workflow: plan, execute, review, replan
  - Validated: 2-phase campaign, $0.33 cost, excellent quality
- File upload with vector store support (PDF, DOCX, TXT, MD, code) - IMPLEMENTED
  - OpenAI: Vector store creation with auto-ingestion monitoring
  - Gemini: Direct file upload with MIME type detection
  - Automatic cleanup with pattern matching
- Prompt refinement with date context and structured deliverables
- Budget management and cost tracking
- SQLite queue with filesystem storage

**Beta (needs more validation):**
- Dynamic research teams (`deepr run team`)
  - GPT-5 assembles optimal perspectives
  - Independent research prevents groupthink
  - Synthesis shows agreements, conflicts, recommendations
- Background worker with polling
- Human-in-the-loop controls

**Key Innovations:**
- Multi-provider support means model choice doesn't lock you in
- Immediate Gemini completion vs. OpenAI background jobs
- Framework extends to any provider (deep research, reasoning, or agentic)

## Agentic Levels Framework

Deepr's development follows a progression toward autonomy:

| Level | Description | Status |
|-------|-------------|--------|
| **Level 1** | Reactive Execution (single-turn) | Complete |
| **Level 2** | Procedural Automation (scripted sequences) | Complete |
| **Level 3** | Adaptive Planning (feedback-driven) | **Current (v2.3)** |
| **Level 4** | Reflective Optimization (learns from outcomes) | Target (v2.5) |
| **Level 5** | Autonomous Meta-Research (self-improving) | Vision (v3.0+) |

**Philosophy:** Quality over automation. We build trust through transparency and demonstrated quality before enabling greater autonomy.

## Near-Term Development

### v2.3 - Observability & UX Improvements (In Development - October 2025)

**Status:** Core modules tested with mocked APIs. Real API validation in progress.

**Test Coverage (October 30, 2025):**
- 28/28 unit tests passing (cost estimation, queue, storage)
- 14/14 CLI command tests passing (new command structure validation)
- Comprehensive provider test suite created (OpenAI, Gemini, Grok, Azure)
- End-to-end workflow tests implemented (submit -> status -> get)
- See [tests/README.md](../tests/README.md) and [docs/TESTING.md](TESTING.md)

**Real API Tests Validated (October 29-30, 2025):**
- Minimal research (o4-mini-deep-research): Works, cost $0.01-0.02, time 30-35s
- Realistic research (o4-mini-deep-research): Works, cost $0.11, time 6-7 min
- File upload & vector search: Works, cost $0.02, time 2 min
- Prompt refinement (gpt-5-mini): Works, cost <$0.001, time 5-25s
- Cost tracking: Works, estimates within 0.2-1.7x of actual
- Multi-phase campaign (o4-mini-deep-research): Works, cost $0.33, 2 phases completed
  - Phase 1: Comprehensive inventory (19K chars, $0.17, excellent citations)
  - Phase 2: Strategic analysis (32K chars, $0.16, builds on Phase 1 context)
  - Context chaining validated: Phase 2 references and analyzes Phase 1 results

**Key Findings from Real API Tests:**
- Output format uses 'output_text' not 'text' (fixed in code)
- Cost estimates tend to be conservative (actual 20-84% of estimate for simple queries)
- Deep research models trigger web searches even for trivial queries
- OpenAI API has intermittent failures (tests handle gracefully)
- Vector stores work correctly for semantic search over uploaded files

**What's Tested (Unit + Mocked):**
- Cost estimation logic - 17 unit tests (calculations only)
- SQLite queue operations - 11 unit tests (local database)
- Storage with human-readable naming - 17 unit tests (filesystem)
- OpenAI provider - 4 unit tests (fully mocked)
- Context chaining - 3 unit tests (logic only)

**What Still Needs Real API Validation:**
- Multi-phase campaign execution
- Ad-hoc job retrieval from OpenAI
- Analytics on real job data
- Provider error handling edge cases

**What Needs Testing (Not Validated at All):**
- Vector store management commands
- Config validation
- Human-in-the-loop controls
- Provider resilience/fallback
- Template system

**Priority 1: File Upload Enhancements - Implemented (needs testing)**

Vector store management commands implemented:

```bash
# Persistent vector stores for reuse
deepr vector create --name "company-knowledge" --files docs/*.pdf
deepr vector list
deepr vector info <vector-store-id>
deepr vector delete <vector-store-id>
deepr run single "Query" --vector-store company-knowledge
```

**Implemented:**
- Vector store CRUD operations
- Reuse across jobs
- ID/name lookup

**Known limitations:**
- Not tested with large file sets
- Error handling needs validation
- Performance with many stores unknown

**TODO:**
- ZIP archive support
- Comprehensive testing
- Performance optimization

**Priority 2: Prompt Refinement Enhancements - Implemented (needs testing)**

```bash
# Dry-run mode
deepr run single "query" --dry-run  # Refinement auto-enabled via DEEPR_AUTO_REFINE=true

# Always-on refinement
# Add to .env: DEEPR_AUTO_REFINE=true
```

**Implemented:**
- Dry-run mode
- DEEPR_AUTO_REFINE config
- Date context injection
- Structured deliverables
- Uses gpt-5-mini (fast, cheap reasoning model)

**Validated (Real API test):**
- Transforms vague prompts into structured research questions
- Adds temporal context automatically (current date)
- Requests current best practices and latest approaches for technology topics
- Prioritizes trusted, authoritative sources (academic, official docs, industry reports)
- 100% improvement score in test (added date + structure + best practices)
- Time: 5-25s depending on load
- Example: "how to build microservices" becomes 15-section structured research brief with current best practices, authoritative sources, and actionable deliverables

**TODO:**
- Template save/load functionality
- More refinement patterns
- Quality validation

**Priority 3: Ad-Hoc Job Management - Implemented (needs testing)**

The `deepr get` command has been implemented to download research results without running a continuous worker.

```bash
deepr get <job-id>                   # Download specific job results from provider (checks OpenAI if not local)
deepr list                           # View all jobs
deepr list -s processing             # Filter by status
```

**Implemented functionality:**
- Download specific job results by ID
- Batch download all completed jobs
- Queue synchronization with provider
- Ad-hoc polling without worker

**Known limitations:**
- Job ID lookup issues (shortened vs full UUID)
- Not tested with large job queues
- Error handling for failed downloads needs validation
- Timeout behavior not thoroughly tested

**TODO:**
- Test with various job states (pending, running, failed)
- Validate batch download with many jobs
- Improve job ID resolution
- Add progress indicators for batch operations

**Priority 4: Observability & Transparency (PARTIALLY COMPLETE)**

**Completed:**
- **Cost attribution:** `deepr status <job-id>` shows cost and token usage
  - Token usage (input, output, reasoning)
  - Cost calculation (input cost, output cost, total)
  - Pricing information (per 1M tokens)
  - Job metadata (model, times, prompt)

**Remaining work:**
- **Decision logs:** "GPT-5 chose Phase 2 topics because [gap analysis]"
- **Reasoning traces:** Timeline view of how research evolved

**CLI additions (planned):**
```bash
deepr status <job-id> --explain      # Why this research path? (planned)
deepr status <job-id> --timeline     # Reasoning evolution (planned)
```

**Priority 5: Human-in-the-Loop Controls - Implemented (needs testing)**

**Implemented:**
- **Budget-based approval:** Set monthly budget, auto-execute under threshold
  - `deepr budget set 50` - Set $50/month limit
  - `deepr budget status` - Check current spending
  - Auto-executes jobs under 80% of budget
- **Manual confirmation:** Per-job approval for expensive operations
  - Jobs over budget threshold require confirmation
  - `-y` flag to skip confirmation
- **Pause/Resume campaigns:** Mid-campaign intervention (planned)
  - Pause/resume functionality exists but not exposed in new CLI yet

**Known limitations:**
- Not tested with multi-phase campaigns
- Pause state persistence not validated
- Resume behavior after errors unclear
- Review workflow only manually tested

**TODO:**
- Test pause/resume across campaign phases
- Validate state persistence after restarts
- Add tests for edge cases (pause during execution)
- Implement plan editing before resume

**Future enhancements (planned):**
```bash
deepr campaign edit <id>   # Modify plan before resuming (planned)
```

**Priority 6: Provider Resilience - Implemented (needs testing)**

**Implemented:**
- **Auto-retry with exponential backoff**
  - 3 retry attempts with 1s, 2s, 4s delays
  - Handles rate limits, connection errors, timeouts
- **Graceful degradation**
  - o3-deep-research → o4-mini-deep-research fallback
  - Automatic model downgrade on persistent failures
  - Aims to ensure research completes even if preferred model unavailable

**Known limitations:**
- Retry logic not tested under actual rate limits
- Fallback behavior not validated in production
- No metrics on retry success rates
- Unclear how it handles partial failures

**TODO:**
- Test retry behavior with actual API rate limits
- Validate graceful degradation under failures
- Add retry/fallback metrics and logging
- Test with various error conditions

**Future enhancements:**
- Provider health monitoring dashboard
- Auto-resume campaigns after recovery
- Multi-provider failover (OpenAI → Anthropic → Google)

### v2.4 - MCP Server & Multi-Provider Support (Q2 2026)

**Priority 1: Google Gemini Provider** [IMPLEMENTED]

Google Gemini 2.5 added as a research provider with agentic capabilities:

```bash
# Top-tier reasoning (equivalent to o3-deep-research)
deepr run single "query" --provider gemini --model gemini-2.5-pro

# Fast/efficient (equivalent to o4-mini-deep-research)
deepr run single "query" --provider gemini --model gemini-2.5-flash

# Cost-optimized for simpler tasks
deepr run single "query" --provider gemini --model gemini-2.5-flash-lite

# Campaign planning
deepr run campaign "scenario" --provider gemini --planner gemini-2.5-flash
```

**Gemini 2.5 Models (October 2025):**
- `gemini-2.5-pro`: Flagship reasoning, 1M token context, multimodal
- `gemini-2.5-flash`: Speed/efficiency optimized, 1M tokens, still high quality
- `gemini-2.5-flash-lite`: Lower cost, good for high-volume or simpler tasks

**Benefits:**
- Cost comparison: Gemini often cheaper than OpenAI
- Different research perspectives from different models
- Provider redundancy and failover
- 1M token context window for extremely long documents
- Native multimodal support (text, image, audio, video)
- Grounding with Google Search integration

**Implementation notes:**
- Leverage existing provider abstraction
- Support Gemini's native search/grounding capabilities
- Handle multimodal inputs for advanced use cases
- Cost tracking for Gemini pricing structure
- Support stable vs latest model aliases

**Implementation status:** Complete. See [docs/GEMINI_IMPLEMENTATION.md](GEMINI_IMPLEMENTATION.md)

**xAI Grok Provider** [IMPLEMENTED]

xAI Grok 4 added as a research provider with agentic tool calling:

```bash
# Agentic web/X search (recommended)
deepr run single "query" --provider grok --model grok-4-fast

# Deep reasoning
deepr run single "complex problem" --provider grok --model grok-4

# Fast and economical
deepr run single "simple query" --provider grok --model grok-3-mini
```

**Grok Models (October 2025):**
- `grok-4-fast`: Agentic search specialist, web/X search, reasoning ($0.20/$0.50 per M tokens)
- `grok-4`: Deep reasoning, encrypted thinking ($3.00/$15.00 per M tokens)
- `grok-3-mini`: Fast, economical ($0.30/$0.50 per M tokens)

**Agentic Capabilities:**
- Server-side tool calling (web_search, x_search, code_execution)
- Autonomous multi-step research with tool orchestration
- Reasoning traces with encrypted content for persistence
- Real-time X (Twitter) post search and analysis
- Citations and source traceability

**Implementation notes:**
- OpenAI API-compatible (extends OpenAIProvider)
- Custom endpoint: https://api.x.ai/v1
- Server-side tools executed autonomously by xAI
- Minimal implementation due to API compatibility

**Implementation status:** Complete. See [docs/MULTI_PROVIDER_SUMMARY.md](MULTI_PROVIDER_SUMMARY.md)

**Documentation Research Mode** [IMPLEMENTED]

Specialized research mode for generating technical documentation that stays current:

**What it does:**
- Automatically includes current date in prompts
- Structured for developers (API details, pricing, architecture patterns)
- Emphasizes recent changes and updates
- Formatted as reference documentation

**Usage:**
```bash
# API Documentation
deepr run single "Document OpenAI API as of today - models, pricing, rate limits, auth"

# Cloud Service Reference
deepr run single "AWS Lambda documentation - features, pricing, patterns, recent updates"

# Framework Guide
deepr run single "React 19 migration guide - breaking changes, new features, upgrade path"
```

**Use cases:**
- Cloud service documentation (AWS, Azure, GCP)
- AI model/API references
- Framework and library docs
- Architecture patterns and best practices
- Service pricing and limits (always changing)

**Why it's useful:**
APIs and cloud services change constantly. Traditional documentation goes stale.
With documentation research mode, you can generate fresh, current documentation on demand
by simply prompting for what you need with "as of today" or "latest" in the query.

**Best provider:** Gemini Flash - excellent at structured output, fast, cost-effective ($0.02 avg)

**Template:** See `deepr/templates/documentation_research.md` for prompt structure

**Priority 2: Web Content Extraction (MCP Tool)**

Extract structured content from specific URLs to inform research. Exposed as both CLI and MCP tool:

```bash
# CLI usage
deepr run single "Analyze X" --extract-from https://company.com/about

# Pre-extract and add to vector store
deepr vector create --name "company-sites" --extract https://company.com/*

# Standalone extraction
deepr extract https://company.com/about --format markdown
```

**MCP Tool Exposure:**
```typescript
// Other agents can call Deepr's extraction capability
{
  name: "extract_web_content",
  description: "Extract structured content from URLs",
  parameters: {
    url: "https://company.com/page",
    format: "markdown" | "json" | "text",
    depth: 1  // How many links deep to follow
  }
}
```

**Use cases:**
- Company research: Extract from their site, competitors, news articles
- Product analysis: Pull official docs, pricing pages, feature lists
- Technical research: Extract from documentation, GitHub READMEs, blog posts
- Due diligence: Structured extraction from multiple relevant sources
- Agent workflows: Any MCP-compatible agent can use Deepr's extraction as a tool

**Why this complements web search:**
- Web search (native in o3/o4): Broad discovery across the internet
- Content extraction: Deep, structured analysis of specific known sources
- Together: "Find the right sources (web search), then deeply analyze them (extraction)"
- MCP integration: Makes Deepr's extraction available to any agent ecosystem

**Architectural fit with MCP:**
- Deepr as MCP Server: Exposes extract_web_content tool to other agents
- Deepr as MCP Client: Can call other MCP servers for data access
- Web extraction becomes a reusable capability across agent workflows
- Research tasks can automatically extract from discovered sources

**Implementation considerations:**
- Respect robots.txt and rate limits
- Handle authentication for internal sources
- Extract and structure content intelligently (not just raw HTML)
- Cache extractions to avoid redundant requests
- Support multiple content types (HTML, PDF, markdown, JSON APIs)
- Rate limiting and politeness delays
- Configurable extraction depth and scope

**Priority 3: CLI UX Improvements - In Progress (October 30, 2025)**

The CLI is being redesigned with unified research verb and mode-based commands.

**Phase 1 - Completed (October 30):**
- Old: `deepr research submit` → New: `deepr run single`
- Old: `deepr prep plan/execute` → New: `deepr run campaign`
- Old: `deepr team analyze` → New: `deepr run team`
- Old: `deepr queue list` → New: `deepr list`
- Old: `deepr research status` → New: `deepr status`
- CLI bug fixed: Jobs now properly submit to provider APIs

**Phase 2 - Planned (November 2025):**

Unified research verb with mode-based interface:

```bash
# Research (canonical form)
deepr research "QUERY" --mode documentation|focus|project|team \
  [--provider openai|gemini|grok|azure] [-m MODEL] \
  [--upload FILE ...] [--index NAME] [--limit USD]

# Ergonomic aliases for humans
deepr docs "OpenAI API as of today: models, pricing, limits, examples"
deepr study "Latest trends in quantum error correction"
deepr project "EV strategy for 2026" --phases 4
deepr team "Should we pivot to enterprise?" --perspectives 6

# Jobs (noun-based grouping)
deepr jobs list
deepr jobs status <id>
deepr jobs get <id>
deepr jobs cancel <id>

# Budget and cost
deepr budget set 50
deepr budget status
deepr cost summary [--period week]

# Context data (renamed from vector)
deepr index create --name company-docs --files docs/*.pdf
deepr index list
deepr index delete <id>

# Analytics and config
deepr analytics report
deepr config validate
```

**Migration mapping:**
- `deepr run single "..."` → `deepr research "..." --mode focus` (alias: `deepr study`)
- `deepr run campaign "..."` → `deepr research "..." --mode project` (alias: `deepr project`)
- `deepr run team "..."` → `deepr research "..." --mode team` (alias: `deepr team`)
- Documentation: `deepr docs "..."` → `deepr research "..." --mode documentation`
- `deepr vector ...` → `deepr index ...`

**Current CLI Structure (Phase 1):**

```bash
# Primary actions (auto-execute if under budget)
deepr run single "query"                    # Single research
deepr run campaign "scenario"               # Multi-phase
deepr run team "question"                   # Dream team

# Budget management (set once, run freely)
deepr budget set 100                        # Set $100/month budget
deepr budget status                         # Show: $23/$100 used this month
deepr budget history                        # Spending over time

# Job management
deepr status <job-id>                       # Check status
deepr get <job-id>                          # Get results
deepr cancel <job-id>                       # Cancel job
deepr list                                  # List jobs
deepr list -s processing                    # Filter by status

# Quick aliases
deepr r "query"                             # Alias for 'run single'
deepr s <job-id>                            # Alias for 'status'
deepr l                                     # Alias for 'list'
```

**Budget-Based Approval:**

Instead of confirming every job, set a monthly budget and run freely:

```bash
# One-time setup
deepr budget set 50                         # $50/month budget

# Now run without confirmations
deepr run "market analysis"                 # Auto-executes (est: $2.50)
deepr run campaign "strategy"               # Auto-executes (est: $8.00)

# Budget protection
deepr run "large research"                  # Warns if approaching limit
# Shows: Budget $47/$50 (94%) - Continue? (y/n)

deepr budget status                         # Check spending anytime
# Shows: $47/$50 used this month (94%)
# Resets: November 1, 2025
```

**Budget modes:**
- `deepr budget set <amount>`: Auto-execute under budget, confirm when approaching
- `deepr budget set 0`: Confirm every job (cautious mode)
- `deepr budget set unlimited`: Never confirm (trust mode)

**Implementation Details:**
- Breaking change - clean slate approach (pre-1.0 rapid development)
- Old command structure removed entirely
- Convenient aliases added: `deepr r`, `deepr s`, `deepr l`
- All documentation updated simultaneously
- Budget checking integrated into submission flow

**Files Created/Modified:**
- `deepr/cli/commands/run.py` - New run command with single/campaign/team subcommands
- `deepr/cli/commands/status.py` - Job management (status, get, list, cancel) with ad-hoc retrieval
- `deepr/cli/commands/budget.py` - Budget management (set, status, history)
- `deepr/cli/commands/team.py` - Added run_dream_team() wrapper for new CLI
- Updated `deepr/cli/main.py` - Registered new commands, removed old structure

**Key Features:**
- Ad-hoc retrieval: `deepr get` checks OpenAI directly if job not completed locally
- Large report preview: Shows first 2000 chars for reports over 5000 chars
- Fixed storage paths: Uses actual saved paths instead of hardcoded ones
- Windows compatibility: ASCII-safe status indicators instead of Unicode

**User Benefits:**
- **Intuitive**: `deepr run single "query"` - you run research, not "submit to research subsystem"
- **Consistent**: All commands follow verb-first pattern (like git, docker, kubectl)
- **Shorter**: Primary actions have minimal nesting
- **Clear hierarchy**: `run` is the top-level action with variants (single, campaign, team)
- **Discoverable**: `deepr --help` shows actions you can take, not system subsections
- **Friction-free**: Set budget once, run freely without constant confirmations

**Priority 4: Deepr Expert - Chat with Research (Research in progress)**

Enable conversational access to accumulated research findings:

```bash
deepr expert chat                          # Interactive chat with all research
deepr expert export --format zip           # Export knowledge package
```

**Vision:**
- Chat interface that leverages temporal knowledge graphs of all research
- AI agent with access to full research history and context
- Export comprehensive knowledge packages (ZIP with all findings, citations, perspectives)
- Use exported packages in any LLM/RAG/agentic setup

**Research questions (in progress):**
- How to use temporal knowledge graphs to organize and validate research findings?
- Best practices for building TKGs from research outputs?
- Architecture for chat agent with full research context?
- Export format for maximum compatibility with LLM/RAG systems?

**Status:** Research phase - investigating TKG approaches, validation methods, and export formats

**Priority 5: Model Context Protocol Server (Key Goal)**

Enable AI agents and tools to use Deepr as a research capability. This is the primary extension point after CLI is solid:

```bash
deepr mcp serve                    # Start MCP server (stdio or HTTP)
deepr mcp serve --transport http   # Network-accessible MCP server
```

**MCP Tools Exposed:**
- `start_research(query, context)` → Returns job_id
- `get_report(job_id)` → Returns markdown report
- `list_jobs()` → Returns job queue
- `cancel_job(job_id)` → Cancels running job
- `extract_web_content(url, format)` → Returns structured content from URL (Priority 2 feature)
- `upload_files(files)` → Creates vector store and returns ID
- `refine_prompt(query)` → Returns optimized research prompt

**Agent Integration:**
- Claude Desktop, Cursor, Windsurf can call Deepr
- Agents autonomously submit research and retrieve reports
- Long-running jobs supported via MCP notifications
- Progress updates streamed to clients

**Priority 6: MCP Client (Connect to Data Sources)**

Deepr can use other MCP servers as data sources:

- Connect to Slack, Notion, filesystems via MCP
- "Research based on our internal docs" workflows
- Context injection from external sources
- Standardized data access across tools

**Priority 7: Dynamic Research Teams - Observability**

Make team perspectives visible:
- Show which team member contributed what findings
- Highlight where perspectives converge vs. diverge
- Cost breakdown per team member
- Export debate structure along with synthesis

**Priority 8: Web UI (Low Priority)**

Browser-based interface for convenience. Built after CLI is solid and MCP server is working:
- Optional UX layer on top of CLI functionality
- Real-time job monitoring
- Cost dashboard
- Report browsing

**Status:** Some implementation exists but low priority. CLI is primary interface. MCP server takes precedence over web UI.

### v2.5 - Learning & Optimization (Q3 2026)

**Moving toward Level 4: System learns from outcomes**

**Priority 1: Research Library & Discovery**

```bash
deepr library search "EV market"           # Semantic search past research
deepr library info <job-id>                # Detailed metadata + quality signals
```

**Discovery, not automatic reuse:**
- Find related past research
- Show: date, cost, model, user rating, perspective
- User reads, judges quality, decides to reuse
- Explicit `--reuse-context job-123` flag (high friction by design)
- Default: always fresh research

**Why conservative:** Context quality determines research quality. Bad context = bad research. Better to over-research than confidently deliver garbage.

**Priority 2: Quality Metrics & Benchmarking**

Track what works:
- Citation quality scores
- User ratings per report
- Cost/value ratios
- Provider performance by task type
- Rolling 30-day stats

Use for:
- Automatic provider routing (best tool for each task)
- Research strategy optimization
- Quality regression detection

**Priority 3: Basic Verification**

Start simple:
- Internal contradiction detection
- Citation coverage metrics
- Confidence scoring per claim
- Flag low-confidence sections for human review

**Priority 4: Platform Integrations**

- Export to Notion, Obsidian, Airtable
- Slack/Teams notifications for campaign completion
- Webhook support for custom workflows
- REST API improvements for programmatic access

## Long-Term Vision

### v3.0+ - Autonomous Expertise Acquisition (Level 5)

**Vision: Self-directed learning until mastery achieved**

Level 5 isn't about consciousness - it's about **autonomous expertise acquisition**. The system becomes expert on any topic through self-directed research.

**The Autonomous Learning Loop:**

```
User: "Become expert on quantum computing commercialization"

Agent Loop (autonomous):
  1. Identify knowledge gaps
     "I understand market overview but weak on supply chain"

  2. Research gaps autonomously
     Executes targeted research without human direction

  3. Run validation (PhD Defense simulation)
     Panel of simulated experts challenges understanding:
     - "Explain superconducting qubit stability trade-offs"
     - "Reconcile technical timeline with market projections"
     - "What are the three biggest commercialization risks?"

  4. If gaps found → Research more → Try again
     If comprehensive → Pass → Present with humility

  5. Present findings with beginner's mind
     "I've researched this comprehensively and validated
     understanding through adversarial review. Here's what
     I know... But I may have blind spots. Ask me anything,
     and if I don't know, I'll research it."
```

**Key Characteristics:**

1. **Perceive** - Agent detects gaps in own understanding ("I don't know X")
2. **Plan** - Autonomously decides what to research next based on gaps
3. **Execute** - Runs research without human direction
4. **Evaluate** - Validates comprehension through simulated expert panel
5. **Improve** - Continues until expertise passes validation

**Not consciousness, but self-directed learning.** The agent identifies what it doesn't know and figures it out autonomously.

**PhD Defense Validation:**

Simulated expert panel challenges agent's understanding:
- Adversarial questioning surfaces gaps
- Agent must demonstrate comprehensive knowledge
- Can't just memorize - must explain and defend
- Fails if gaps found, researches more, tries again
- Passes when understanding withstands scrutiny

Implementation via Constitutional AI: Encode assessment rules ("admit uncertainty", "provide reasoning steps") in model constitution, enabling self-critique and calibrated confidence (e.g., ECE < 5%, accuracy ≥95%).

**Humble Expertise:**

Even after validation, maintains beginner's mind:
- Confident about researched areas
- Transparent about methodology
- Admits potential blind spots
- Willing to research more if challenged
- "I understand this comprehensively, but contexts change"

**Key Features:**

**Autonomous Gap Identification:**
- After each research round, agent evaluates own understanding
- Identifies specific knowledge gaps
- Generates targeted research questions autonomously
- Continues until no major gaps remain

**Mock Conversations for Blind Spot Detection:**
- Simulated board discussions between perspectives
- Devil's advocate challenges assumptions
- Cultural or domain-specific viewpoints
- Conflicts reveal areas needing deeper research

**Validation Mechanisms:**
- PhD defense simulation (adversarial expert panel)
- Multi-provider consistency checks
- Citation confidence scoring
- Internal contradiction detection
- Self-assessment: "Do I understand this comprehensively?"

**Practical Applications:**
- Meeting prep: "Research customer's industry" (10 min, $2)
- Strategic planning: "Become expert on market dynamics" (60 min, $8)
- Due diligence: "Comprehensive analysis with validation" (2 hours, $15)
- Any depth needed, from quick brief to PhD-level expertise

**Smart Context Management:**
- "What's new since last research?" delta updates
- Incremental research vs. full re-research
- Knowledge freshness tracking
- Temporal awareness (market data vs. fundamentals)

**Multi-Tenancy & Scale:**
- Team workspaces with shared research libraries
- Access control and permissions
- Usage analytics per team/user
- Enterprise deployment options

## Multi-Provider Strategy

**Current Reality (October 2025):**

Multiple providers now offer deep research capabilities:

- **OpenAI**: GPT-5 family with Deep Research API (o3-deep-research, o4-mini-deep-research)
- **Anthropic**: Claude Opus 4.1, Sonnet 4.5, Haiku 4.5 with Web Search tools
- **Google**: Gemini 2.5 Pro/Flash/Flash-Lite with Deep Research (Enterprise+)
- **xAI**: Grok 4 and Grok 4 Fast with agentic tool-calling
- **Azure OpenAI**: GPT-5 family via Azure AI Foundry (enterprise deployment)

**Provider Selection Strategy:**
- Current: OpenAI Deep Research API (most mature, turnkey solution)
- Manual: `--provider openai|azure|anthropic|google|xai` flag
- Planned: Automatic routing based on task type, cost, and performance
- Architecture: Provider-agnostic design, no vendor lock-in

**Deepr's Value Beyond Single-Provider Wrappers:**
- Intelligent multi-phase planning with context chaining
- Adaptive workflows (plan → execute → review → replan)
- Dynamic research teams with diverse perspectives
- Provider-agnostic architecture with automatic routing
- MCP integration for ecosystem compatibility

## Design Principles

**Quality Over Automation:**
- Bias toward fresh research and human judgment
- High friction for context reuse (quality preservation)
- Transparent by default
- Autonomous where proven reliable

**CLI First, Platform Agnostic:**
- Command-line is the primary interface (fully functional)
- MCP server for AI agent integration (primary extension point)
- Web UI optional (low priority, UX convenience only)
- Open source, works on any platform

**Local-First, Provider-Agnostic:**
- SQLite queue (no external database required)
- Filesystem storage (no cloud dependency)
- Multi-provider support (no vendor lock-in)
- Open standards (MCP, JSON-RPC)

**Observability Enables Trust:**
- Make reasoning visible before making it autonomous
- Full audit trails available on demand
- Cost transparency per task/phase/provider
- Explain decisions in natural language

**Open Ecosystem:**
- Standard protocols (MCP)
- Plugin architecture (planned)
- Community-driven templates and patterns
- Extensible for custom workflows

## Use Cases at Scale

**For Humans:**
- Market analysis and competitive intelligence
- Technical due diligence with dependencies
- Strategic planning with comprehensive context
- Academic research with citation management

**For AI Agents:**
- On-demand deep research capability via MCP
- Grounding LLM reasoning in fresh, cited data
- Multi-step knowledge gathering for complex tasks
- Autonomous research in agentic workflows

**For Teams:**
- Shared research libraries with semantic search
- Collaborative multi-phase campaigns
- Cost-effective alternative to consulting fees ($3-5 vs. $5,000+)
- Continuous learning and knowledge building

## Non-Goals

Explicitly NOT building:
- Chat interface (use regular LLMs)
- Real-time responses (deep research takes time by design)
- Sub-$1 research (comprehensive research has real cost)
- Mobile apps (CLI/web/MCP sufficient)
- Features without clear value
- Vendor lock-in or proprietary extensions

## Contributing

High-impact areas:
- Context chaining logic and prompt engineering
- Synthesis strategies for integrating findings
- Cost optimization techniques
- Template patterns for common research workflows
- Provider integrations
- MCP server implementation
- Documentation and examples

Most valuable work is on the intelligence layer (planning, context management, synthesis) rather than infrastructure.

## Dogfooding

We use Deepr to build Deepr. Recent examples:

- **Context injection best practices** ($0.17, 6 min) - Validated our ContextBuilder design, informed Phase 2 prompt engineering
- **MCP protocol research** ($0.18, 10 min) - Comprehensive analysis of MCP architecture and strategic value for Deepr
- **Competitive landscape** ($0.13) - Identified gaps vs. Elicit, Perplexity, Consensus, SciSpace

This validates the tool while generating implementation guidance. When we hit design questions, we research them using Deepr itself.

---

## Summary

Deepr is evolving from an adaptive planning system (Level 3) toward a self-improving research platform (Level 4-5) that serves both humans and AI agents.

**Near-term focus (v2.3-2.4):**
- Testing and validating v2.3 implementations
- Prompt refinement improvements
- Better UX (ad-hoc job management, observability)
- MCP server (AI agent integration)
- Provider resilience validation

**Medium-term (v2.5):**
- Learning from outcomes
- Quality metrics and benchmarking
- Basic verification
- Platform integrations

**Long-term (v3.0+):**
- Continuous learning and optimization
- Advanced verification
- Multi-tenancy and scale
- Platform maturity

**Core principle:** Build research infrastructure that enables humans and AI systems to learn and advance at scale. Quality and trust over hype and automation.
