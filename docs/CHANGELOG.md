# Changelog

All notable changes to Deepr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.8.1] - 2026-02-12

### Added

**Background Job Polling + WebSocket Push**
- Flask-SocketIO initialization with `cors_allowed_origins="*"` and threading async mode
- Background poller thread that checks PROCESSING jobs every 15 seconds via provider API
- WebSocket events: `job_created` on submit, `job_completed`/`job_failed` on poller detection
- `to_dict()` method on `ResearchJob` dataclass (enum, datetime, Path serialization)
- `POST /api/jobs/cleanup-stale` endpoint to mark stuck/orphaned jobs as failed
- `socketio.run()` replaces `app.run()` for WebSocket support
- Frontend already handled all events via `use-websocket.ts` — now actually connected

**Web Dashboard UX Overhaul**
- Skeleton loading states: `CardGridSkeleton`, `DetailSkeleton`, `FormSkeleton`, `DashboardSkeleton` replacing all spinner patterns
- Honest progress phases: replaced fake time-based 6-phase progress with 3 status-based phases (Queued/Processing/Complete)
- Standardized all form controls to shadcn/ui components (Input, Select, Button) across research-studio, expert-hub, results-library, expert-profile
- Copy-to-clipboard button on result-detail page with toast feedback
- Cmd+Enter / Ctrl+Enter keyboard shortcut to submit research from textarea
- Drag-and-drop file upload on research studio with visual feedback and file type filtering
- Pagination on results library (12 per page, page controls, total count)
- Mobile hamburger navigation via Sheet component (sidebar hidden on small screens)
- FOUC prevention: critical CSS inlined in index.html
- Skip-to-content link for keyboard/screen-reader accessibility
- Settings page: Environment info card showing provider, queue, storage, API key status
- Research Live completed state: enriched with prompt text, 4-stat grid (cost, tokens, completed date, model), content preview with markdown stripping

### Fixed
- Timezone naive/aware datetime comparison errors across 10+ locations in app.py (`_ensure_utc()` helper)
- JSX unicode escape `\u21B5` rendering as literal text in keyboard hint (moved to JS expression)
- Flask serving stale asset hashes when restarted before rebuild
- Results API sort crashing on naive datetime comparison
- Activity feed sort crashing on naive datetime comparison

---

## [2.8.0] - 2026-02-04

### Added

**Provider Intelligence (5.1, 5.3)**
- Latency percentiles (p50, p95, p99) in `ProviderMetrics` for performance analysis
- Success rate tracking by task type (research, chat, synthesis, planning)
- `deepr providers benchmark --history` command to view historical benchmark data
- `deepr providers benchmark --json` for machine-readable output
- Exploration vs exploitation in provider routing (10% exploration rate, configurable)
- Auto-disable failing providers (>50% failure rate, 1hr cooldown)
- `deepr providers status` shows auto-disabled providers with cooldown info

**Advanced Context (6.4, 6.5)**
- Temporal knowledge tracking wired into `ResearchOrchestrator`
- `--temporal` flag in `deepr research trace` shows findings/hypothesis timeline
- `--lineage` flag in `deepr research trace` shows context flow visualization (tree view)
- Context chaining via `ContextChainer` for phase-to-phase handoff
- Temporal data export in trace files

**Web Dashboard Overhaul**
- Rebuilt frontend with React 18, Vite, Tailwind CSS 3.4, and Radix UI (shadcn/ui pattern) component library
- 10 pages with code-split lazy loading via React.lazy and Suspense
- New pages: Overview (activity feed, system health), Research Studio (mode selector, model picker), Research Live (WebSocket progress), Result Detail (markdown viewer, citation sidebar, export), Expert Hub (list, stats, knowledge gaps), Expert Profile (chat, gaps, history), Cost Intelligence (charts, budget sliders, anomaly detection), Trace Explorer (execution spans, timing, cost)
- WebSocket integration for real-time job status updates (Socket.io client connected in AppShell)
- Command palette (Ctrl+K) for quick navigation across all pages
- Light/dark/system theme support via Zustand store
- Toast notifications via Sonner for all user-facing actions
- Recharts for cost trends, model breakdown, and utilization charts
- Fixed: division by zero in cost utilization calculations
- Fixed: unsafe URL parsing in citation display
- Fixed: budget sliders firing mutations on every pixel drag (debounced)
- Fixed: expert profile "Research this" button was not wired
- Fixed: research studio mode selector was ignored in submit payload
- Fixed: citation sidebar invisible on mobile viewports
- Removed dead code: unused type files, legacy pages, stale constants, unused components

**Expert System**
- `deepr expert plan` command to preview a learning curriculum without creating an expert or spending money
- Outputs as Rich table (default), JSON (`--json`), CSV (`--csv`), or prompts only (`-q`)
- Supports `--budget`, `--topics`, and `--no-discovery` options

**Expert & Decision Formalization (Phase 5)**
- Canonical types in `core/contracts.py`: `Source`, `Claim`, `Gap`, `DecisionRecord`, `ExpertManifest` with full serialization (`to_dict()`/`from_dict()`)
- `TrustClass` enum (primary, secondary, tertiary, self_generated) and `DecisionType` enum (routing, stop, pivot, budget, belief_revision, gap_fill, conflict_resolution, source_selection)
- `gap_scorer.py` with EV/cost ranking: `score_gap()` and `rank_gaps()` for rational gap prioritization
- Adapter methods: `Belief.to_claim()`, `KnowledgeGap.to_gap()` on existing classes for backward compatibility
- `ExpertProfile.get_manifest()` composes claims, scored gaps, and decision records into a typed snapshot
- `ThoughtStream.record_decision()` creates structured `DecisionRecord` objects alongside existing thought logging
- `--explain` flag now shows decision table (type, decision, confidence, cost impact) in CLI
- Web: Expert Profile page gains Claims tab, Decisions tab, and scored Gaps tab with EV/cost badges
- Web: Trace Explorer gains collapsible decision sidebar for the current job
- Web API: `GET /api/experts/<name>/manifest`, `/claims`, `/decisions` endpoints
- MCP: `deepr_expert_manifest` and `deepr_rank_gaps` tools for agent consumption
- 69 new unit tests (contracts, gap scorer, adapters)

**Real-Time Progress (7.3)**
- `ResearchProgressTracker` for live progress updates during research
- `--progress` flag in `deepr research wait` shows phase tracking with progress bar
- Phase detection (queued → initializing → searching → analyzing → synthesizing → finalizing)
- Partial results streaming when provider supports it
- Customizable poll intervals via `--poll-interval`

**Output Improvements (7.6)**
- `print_truncated()` utility for long output with "use --full to see all"
- `make_hyperlink()` and `print_report_link()` for clickable links in supported terminals

### Changed

- `ProviderMetrics.record_success()` and `record_failure()` now accept optional `task_type` parameter
- `AutonomousProviderRouter.record_result()` now accepts optional `task_type` parameter
- `AutonomousProviderRouter.select_provider()` now filters auto-disabled providers and adds exploration
- `get_status()` includes latency percentiles and task type stats per provider
- Enhanced providers CLI with historical data display and JSON export
- `MetadataEmitter.save_trace()` now includes temporal knowledge data when tracker is set
- Removed deprecated `run single` and `run campaign` commands (use `research` instead)

---

## [2.7.0] - 2026-02-04

### Added

**Context Discovery (6.1-6.3)**
- `deepr search query "topic"` command with semantic + keyword search across prior research
- `deepr search index` to index reports with embeddings (text-embedding-3-small)
- `deepr search stats` to view index statistics
- Automatic related research detection on `deepr research submit`
- `--context <job-id>` flag to include prior research as context
- `--no-context-discovery` flag to skip automatic detection
- Stale context warnings (>30 days old)
- Context truncation for token budget management
- Job ID prefix matching (can use `--context abc123` instead of full UUID)

**Observability Improvements (4.2, 4.4, 4.5)**
- Instrumented `core/research.py` with spans for submit, completion, cancel operations
- Instrumented `experts/chat.py` with spans for tool calls and message handling
- Cost attribution per span with token counts
- ThoughtStream decision summary generation (`generate_decision_summary()`, `get_why_summary()`)
- Research quality metrics: `EntropyStoppingCriteria`, `InformationGainTracker`, `QualityMetrics`
- Temporal knowledge tracking with `TemporalKnowledgeTracker`

**Code Quality**
- Configuration consolidation: single `Settings` class in `core/settings.py`
- ExpertProfile refactoring with composed managers (`budget_manager.py`, `activity_tracker.py`)
- 300+ new tests (1200+ total)

### Changed

- Interactive mode (`deepr` with no args) now shows model picker with cost estimates
- Improved test stability with faster hypothesis strategies

### Fixed

- Flaky hypothesis test `test_episode_tags_preserved` (42+ second generation time)
- Windows console Unicode encoding for ThoughtStream summaries

---

## [2.6.0] - 2026-02-03

### Added

**Documentation Overhaul**
- Rewrote README to better communicate value proposition for enterprise users (cloud architects, CIOs)
- Added "MCP + Skills" section highlighting research infrastructure for AI agents
- New workflow example: Claude Code → query expert → fill knowledge gaps → continue with accurate info
- Emphasized expert system differentiation: self-aware, self-improving, persistent, portable
- Enterprise-focused examples: competitive intelligence, due diligence at scale, institutional knowledge retention
- Updated decision table and "What You Can Do" section with AI agent capabilities first

**CLI Trace Flags (4.1)**
- `--explain` flag on `deepr research` and `deepr run focus` shows task hierarchy with model/cost reasoning
- `--timeline` flag renders Rich table with offset, task, status, duration, cost per phase
- `--full-trace` flag dumps complete trace JSON to `data/traces/{job_id}_trace.json`
- `TraceFlags` dataclass wired through CLI command decorators, backward compatible

**Output Modes (7.1)**
- `OutputMode` enum: MINIMAL (default), VERBOSE, JSON, QUIET
- `OutputContext` and `OutputFormatter` for consistent output across commands
- `@output_options` decorator adds `--verbose`, `--json`, `--quiet` to commands
- Conflicting flags rejected with clear error messages

**Gemini Deep Research Agent (5.4)**
- Native Gemini Deep Research support via Google Interactions API (`client.interactions.create()`)
- Dual-mode `GeminiProvider`: deep research agent for async research, `generate_content` for regular queries
- Model detection routes `deep-research` models to Interactions API automatically
- File Search Store integration for document grounding (`client.file_search_stores.create()`)
- Citation URL resolution for Google grounding redirect URLs
- Adaptive polling intervals: 5s (first 60s), 10s (60-300s), 20s (300s+)
- Experimental API warning suppression for stable operation
- Added `gemini/deep-research` to model capabilities registry
- 19 new tests covering deep research submission, status polling, file stores, citations, and adaptive polling

**Auto-Fallback on Provider Failures (5.2)**
- `AutonomousProviderRouter` wired into `_run_single()` in `cli/commands/run.py`
- Retry with fallback: timeout retries once then falls back, rate limit falls back immediately, auth error skips provider
- Max 3 fallback attempts before failure
- `_classify_provider_error()` bridges provider errors to core error hierarchy
- Vector store graceful degradation when falling back to non-OpenAI providers
- Fallback events emitted to trace and shown in `--explain` output
- `--no-fallback` flag on `focus`, `single`, `docs`, `run_alias`, `research` commands

**Cost Attribution Dashboard (4.3)**
- `deepr costs breakdown --period` flag (today, week, month, all) replaces `--days`
- `deepr costs timeline` command with ASCII bar chart, anomaly detection (>2x average), `--weekly` aggregation
- `deepr costs expert "Name"` subcommand shows per-expert cost breakdown, budget utilization, per-operation costs
- `CostAggregator.get_entries_by_expert()` and `get_expert_breakdown()` helpers
- Cost metadata (`total_cost`, `cost_by_model`) stored in `reports/{job_id}/metadata.json`

**Docker and Deployment**
- Dockerfile with Python 3.11-slim, non-root user (UID 1000), healthcheck
- `.dockerignore` reducing build context from 168MB to ~2MB
- `docker-compose.yml` with bridge network, resource limits (512MB, 1 CPU)

**Cloud Deployment Templates (10.1)**
- AWS SAM/CloudFormation template (`deploy/aws/`) with Lambda API, SQS queue, Fargate worker, DynamoDB, S3
- Azure Bicep template (`deploy/azure/`) with Functions, Queue Storage, Container Apps, Cosmos DB, Blob Storage
- GCP Terraform template (`deploy/gcp/`) with Cloud Functions, Pub/Sub, Cloud Run, Firestore, Cloud Storage
- Shared API library (`deploy/shared/deepr_api_common/`) with validation, security headers, response utilities
- API key authentication via Authorization Bearer token and X-Api-Key header
- CORS preflight OPTIONS handling on all endpoints
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options, Cache-Control)
- 90-day TTL on job documents for automatic cleanup (DynamoDB, Firestore, Cosmos DB)
- Input validation with sanitization (prompt length, model validation, UUID format)
- Detailed deployment documentation in `deploy/README.md`

**CI and Code Quality Tooling**
- GitHub Actions CI workflow: lint (ruff) + unit tests on push to `main` and PRs, Python 3.11/3.12 matrix
- `.pre-commit-config.yaml` with ruff (lint+format), trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files, debug-statements
- `[tool.coverage]` in `pyproject.toml`: source/omit config, 60% minimum threshold, show_missing
- `[tool.ruff]` configuration in `pyproject.toml`
- `CONTRIBUTING.md` with setup, dev workflow, code style, testing, and guidelines
- CI enforces coverage minimum (`--cov-fail-under=60`) via `pytest-cov`
- `pytest-cov` added to `[project.optional-dependencies] dev`

### Fixed
- Fixed `pyproject.toml` URLs pointing to wrong GitHub organization
- Moved `test_conversation_memory.py` from unit to integration tests (was loading 4.3GB knowledge graph)
- Fixed model registry tests referencing `gpt-5` instead of `gpt-5.2`
- Fixed staleness urgency test expecting wrong value for missing cutoff date
- Fixed skill frontmatter token count test (limit bumped from 200 to 300 after metadata growth)
- Fixed flaky Hypothesis test `test_negation_detected_as_contradiction` (negation words in generated inputs + deadline exceeded on cold init)
- Fixed flaky Hypothesis test `test_normalize_produces_absolute_path` (drive-relative paths like `H:0` misidentified as absolute on Windows)

### Changed
- Test suite grew from 1300 to 2820+ tests
- Unified all version strings to 2.6.0 across package, CLI, API, and user-agent
- Replaced 47 `print()` calls in 13 library modules with structured `logging` (lazy `%s` formatting)
- Consolidated model pricing into single registry source of truth (`deepr/providers/registry.py`); removed hardcoded pricing from `base.py`, `research.py`, and provider modules
- Tightened exception handling in core, providers, and MCP server (bare `except Exception` replaced with `openai.OpenAIError`, `GenaiAPIError`, `DeeprError`, `OSError`, etc.)
- Tightened exception handling in storage and services: `storage/local.py` (5 catches → `OSError`), `storage/blob.py` (7 catches → `AzureError`), `core/jobs.py` (4 catches → `json.JSONDecodeError`/`KeyError`/`TypeError`/`ValueError`), `utils/scrape/fetcher.py` (1 catch → `requests.RequestException`/`json.JSONDecodeError`/`KeyError`/`ValueError`)
- Split monolithic `cli/commands/semantic.py` (3,318 lines) into `cli/commands/semantic/` package: `research.py` (research/learn/team/check commands), `artifacts.py` (make/agentic commands), `experts.py` (expert subcommands). Backward-compatible re-exports in `__init__.py`
- Removed `sys.path.insert()` hack in MCP server; uses standard package imports
- Removed 4 DEBUG `print()` statements left in production code (`semantic.py`)
- Fixed 3 bare `except:` catches with specific exception types (`prep.py`, `web/app.py`)
- Single-sourced version string: 5 modules now import `__version__` from `deepr/__init__.py` instead of hardcoding
- Replaced last `sys.path.insert()` in MCP server (skills loading) with `importlib.util.spec_from_file_location()`
- Converted remaining `print()` in `formatting/normalize.py` and `formatting/converters.py` to structured logging
- Dockerfile uses `pip install --no-cache-dir .` instead of editable install

- Removed redundant `black` from pre-commit hooks (ruff-format covers formatting) and `[tool.black]` from `pyproject.toml`
- Replaced 10 stub TODO comments in API routes with explanatory comments noting CLI-managed features
- Cleaned up API route stubs in `config.py`, `jobs.py`, `cost.py`, `results.py`

### Removed
- Deleted dead legacy CLI module (`deepr/cli.py`, 350 lines) shadowed by `deepr/cli/` package
- Deleted `setup.py` (fully redundant with `pyproject.toml`)

## [2.5.0] - 2026-01-15

### Added

**MCP Advanced Patterns Implementation**
- Added Dynamic Tool Discovery with BM25/vector search in `deepr/mcp/search/registry.py`
- Added Resource Subscriptions for event-driven async monitoring in `deepr/mcp/state/subscriptions.py`
- Added Human-in-the-Loop Elicitation for cost governance in `deepr/mcp/state/elicitation.py`
- Added Sandboxed Execution for isolated research contexts in `deepr/mcp/state/sandbox.py`
- Added JobManager for background task coordination in `deepr/mcp/state/job_manager.py`
- Added ResourceHandler for MCP resource protocol in `deepr/mcp/state/resource_handler.py`
- Added ExpertResources for expert profile/beliefs/gaps resources in `deepr/mcp/state/expert_resources.py`

**Transport Layer**
- Added Stdio transport for local process communication in `deepr/mcp/transport/stdio.py`
- Added Streamable HTTP transport for cloud deployment in `deepr/mcp/transport/http.py`
- StdioTransport ensures research data never leaves local process tree
- StreamingHttpTransport supports SSE for server-to-client notifications
- HttpClient for connecting to remote MCP servers

**Agent Trajectory Evaluation**
- Added TrajectoryMetrics for tracking agent performance in `deepr/mcp/evaluation/metrics.py`
- Tracks trajectory efficiency (steps vs optimal golden path)
- Tracks citation accuracy (beliefs with cited sources)
- Tracks hallucination rate (invented parameters not in schema)
- Tracks context economy (tokens per task)
- MetricsTracker for aggregating metrics across sessions

**MCP Server Architecture**
- Job pattern for async research: `deepr_research()` returns immediately, poll with `deepr_check_status()`
- SQLite persistence for job state across server restarts
- Reports exposed as MCP Resources (`deepr://reports/{job_id}/final.md`, `summary.json`, etc.)
- Progress notifications via subscription manager
- Structured error responses with `ToolError` dataclass (error_code, retry_hint, fallback_suggestion)
- Trace ID propagation for end-to-end debugging

**Claude Skill Infrastructure**
- Created `skills/deepr-research/` directory following Claude Skill conventions
- Added SKILL.md with activation keywords and progressive disclosure
- Added reference documents for research modes, expert system, cost guidance, prompt patterns, troubleshooting, and MCP patterns
- Added scripts for research decision classification and result formatting
- Added templates for research report output
- LLM-optimized tool descriptions with usage hints, negative guidance, example invocations
- Prompt primitives: `deep_research_task`, `expert_consultation`, `comparative_analysis`
- Install scripts (`install.sh`, `install.ps1`) with env var checking
- `deepr_status` health check tool

**Security Hardening**
- SSRF protection: blocks requests to private/internal IPs, optional domain allowlist
- Path traversal protection via `PathValidator` in sandbox module
- MCP Sampling primitives for human-in-the-loop (`SamplingRequest`, `SamplingResponse`)

**Multi-Runtime Configuration**
- Config templates for OpenClaw, Claude Desktop, Cursor, VS Code
- Docker variant config with volume mounts
- Per-runtime setup guides in `mcp/README.md`

**Claude-Specific Optimizations**
- Chain of Thought guidance prepended to research tool descriptions
- Lazy loading for large reports (summary + resource URI, configurable threshold)

**Elicitation System**
- ElicitationHandler for structured user input requests via JSON-RPC
- BudgetDecision enum with APPROVE_OVERRIDE, OPTIMIZE_FOR_COST, ABORT options
- CostOptimizer for dynamic model switching when optimizing for cost
- Budget limit triggers that pause jobs and request user decisions
- JSON Schema support for structured elicitation responses

**Sandbox System**
- SandboxManager for isolated execution contexts
- PathValidator with path traversal attack prevention
- SandboxConfig for configurable isolation settings
- Filesystem isolation with strict working directory enforcement
- Report synthesis and merge for extracting results from sandboxed contexts

**Test Coverage**
- 302 tests passing across MCP and skill modules
- 34 tests for transport layer (stdio and HTTP)
- 34 tests for trajectory metrics
- 37 tests for elicitation module
- 36 tests for sandbox module
- Property-based tests using Hypothesis for core skill logic

## [2.3.0] - 2025-11-15

### Added

**Always-On Prompt Refinement**
- Added `DEEPR_AUTO_REFINE` configuration option in .env
- When enabled, automatically applies prompt refinement to all research submissions
- No need to specify `--refine-prompt` flag each time
- Provides seamless best practices for all queries

**Campaign Pause/Resume Controls**
- Added `deepr prep pause` command to pause active research campaigns
- Added `deepr prep resume` command to resume paused campaigns
- Execute command now checks pause status before running
- Enables mid-campaign intervention for human oversight
- Supports both specific plan IDs and most recent campaign

**Persistent Vector Store Management**
- Added `deepr vector create` command to create reusable vector stores
- Added `deepr vector list` command to list all vector stores
- Added `deepr vector info` command to show vector store details
- Added `deepr vector delete` command to remove vector stores
- Added `--vector-store` flag to `deepr research submit` for reusing existing stores
- Vector stores can be looked up by ID or name
- Enables document indexing once, reuse across multiple research jobs

**Batch Job Download and Queue Sync**
- Added `--all` flag to `deepr research get` for downloading all completed jobs
- Added `deepr queue sync` command to update all job statuses without downloading
- Automatically checks provider for all pending jobs and downloads completed ones
- Useful for batch processing after submitting multiple research jobs
- Queue sync updates local status to match provider without downloading results

**Enhanced Cost Management**
- Added `--period` flag to `deepr cost summary` (today, week, month, all)
- Cost breakdown by model showing per-model spending and job counts
- Budget tracking with percentage of daily/monthly limits
- Improved statistics with total jobs, completed count, and averages

**Research Export**
- Added `deepr research export` command for exporting in multiple formats
- Supports markdown, txt, json, and html export formats
- Automatic output path generation or custom output location
- Includes job metadata, content, and usage statistics in exports

**Build and Installation**
- Added pyproject.toml for modern Python packaging
- Created INSTALL.md with platform-specific instructions
- Added install scripts for Linux/macOS (install.sh) and Windows (install.bat)
- Added Makefile for common development tasks
- Added build scripts (build.bat for Windows)
- Updated setup.py to version 2.3.0
- Console script entry point enables `deepr` command globally

**Configuration Management**
- Added `deepr config validate` command to check configuration and API connectivity
- Added `deepr config show` command to display current settings (sanitized)
- Added `deepr config set` command to update configuration values
- Validates API keys, directories, and budget limits
- Tests provider connectivity during validation

**Analytics and Insights**
- Added `deepr analytics report` command for usage analytics
- Success rates, model performance, cost analysis by time period
- Added `deepr analytics trends` showing daily job counts and costs
- Added `deepr analytics failures` for failure pattern analysis
- Identifies most cost-effective models and provides recommendations

**Prompt Templates**
- Added `deepr templates save` to save reusable prompts with placeholders
- Added `deepr templates list` to view all saved templates
- Added `deepr templates show` to display template details
- Added `deepr templates delete` to remove templates
- Added `deepr templates use` to submit research using templates
- Tracks usage count for each template
- Supports placeholder substitution (e.g., {industry}, {region})

### Changed
- Execute command now prevents execution of paused campaigns
- Improved human-in-the-loop controls with pause/resume workflow
- Research submit command now supports both new file uploads and existing vector stores
- Simplified README Quick Start to focus on pip install workflow

## [2.2.0] - 2025-10-29

### Added

**File Upload & Vector Stores**
- Added `--files` / `-f` flag to `deepr research submit` for document upload
- Automatic vector store creation and indexing for semantic search
- Support for PDF, DOCX, TXT, MD, and code files
- Successfully tested with multi-document research workflows

**Automatic Prompt Refinement**
- Added `--refine-prompt` flag to optimize research queries automatically
- Uses GPT-5.2-mini to enhance prompts with temporal context and structure (~$0.001 per refinement)
- Automatically adds current date context ("As of October 2025...")
- Suggests structured deliverables and flags missing business context
- Provides before/after comparison of prompt improvements

**Ad-Hoc Result Retrieval**
- Added `deepr research get <job-id>` command for on-demand result downloads
- Check provider status and download results without continuous worker
- Perfect for daily check-ins, CI/CD integration, and casual usage
- Eliminates need for 24/7 worker process

**Detailed Cost Breakdowns**
- Added `--cost` flag to `deepr research result` command
- Shows comprehensive token usage breakdown (input/output/reasoning)
- Displays separate cost calculations for input and output tokens
- Includes model pricing information (per 1M tokens)
- Shows job metadata and prompt context

**Human-in-the-Loop Controls**
- Added `--review-before-execute` flag to `deepr prep plan` command
- Tasks start unapproved when flag is used, requiring explicit human approval
- Prevents autonomous execution without oversight
- Use `deepr prep review` to approve/reject tasks before execution

**Provider Resilience**
- Implemented retry logic with exponential backoff (3 attempts: 1s, 2s, 4s delays)
- Graceful degradation: automatically falls back from o3-deep-research to o4-mini-deep-research
- Handles rate limits, connection errors, and timeouts automatically
- Ensures research completes even if preferred model is unavailable

### Changed

**CLI Commands**
- Renamed `poll` to `get` for clearer intent (retrieve results)
- Improved command descriptions and help text across all commands
- Enhanced error messages with actionable guidance

**Documentation**
- Restructured README Quick Start with clear numbered steps
- Added prerequisites section (Python 3.9+, Node.js 16+)
- Added "Why Deepr?" value proposition with key differentiators
- Clarified target audience (researchers, analysts, product teams, developers, AI agents)
- Added cost warning and budget management guidance
- Updated all time/cost estimates to "Estimated: ~$X" format
- Added descriptive context before code example sections
- Fixed grammar issues ("becoming an expert", improved wording)
- Updated Multi-Provider Support section with current October 2025 models
- Removed all emojis from documentation

**ROADMAP**
- Updated from v2.1 to v2.2 release status
- Marked priorities 1-6 as complete or partially complete
- Added implementation details for each completed feature
- Clarified model references (GPT-5, o3-deep-research, o4-mini-deep-research)
- Updated version timeline (v2.3, v2.4, v2.5)
- Updated Agentic Levels table to reflect current progress

### Fixed
- Fixed version inconsistencies throughout documentation (v2.1 → v2.2)
- Fixed port references (backend: 5000, frontend: 3000)
- Corrected model naming for clarity
- Improved Unicode handling in CLI output for Windows compatibility

### Meta-Research
- Used Deepr itself to analyze README and ROADMAP for refinement opportunities
- Applied 12+ specific recommendations from research report
- Research cost: $2.00 for comprehensive documentation review
- Demonstrated platform capabilities through self-improvement

## [2.1.0] - 2025-10-XX

### Added
- Multi-phase research campaigns with adaptive planning
- GPT-5.2 as research lead for reviewing and planning phases
- Context chaining with automatic summarization
- Dynamic research teams (experimental)
- Web UI with real-time updates and cost analytics

### Changed
- Improved background worker with stuck job detection
- Enhanced cost tracking from OpenAI token usage

## [2.0.0] - 2025-10-XX

### Added
- Initial release of Deepr
- Single deep research jobs via CLI
- OpenAI Deep Research integration (o3, o4-mini models)
- SQLite queue and filesystem storage
- Background worker with automatic polling
- Basic web UI

---

For more details on upcoming features, see [ROADMAP.md](ROADMAP.md).
