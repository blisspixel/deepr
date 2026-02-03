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

### MCP Ecosystem (remaining)

**What exists:** Full MCP server with 10 tools, persistence, security, skill packaging, Docker, multi-runtime configs.

#### MCP Client Mode (Deepr as Tool Consumer)
- Design complete (SearchBackend, BrowserBackend protocols, architecture doc)
- [ ] Implement MCP client connections (Stdio, SSE transports)
- [ ] Brave Search and Puppeteer/Playwright MCP adapters
- [ ] Recursive agent composition for sub-agent summarization

#### Remaining MCP Items
- [ ] GitHub release workflow for skill distribution
- [ ] Wire sampling into web scraper (CAPTCHA/paywall detection)
- [ ] Rate limiting for external requests

#### Stretch Goals
- [ ] Multi-agent swarm support (specialized variants, manager routing)
- [ ] Remote MCP and edge deployment (SSE, Cloudflare Workers)
- [ ] Memory integration (cross-session persistence, vector DB)

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

1. **7.2 Interactive Mode** - High user value
2. **6.1 Context Discovery** - New feature, moderate effort
3. **4.2 Auto-Generated Metadata** - Observability depth
4. **7.3 Real-Time Progress** - Depends on API capabilities
5. **5.1 Provider Benchmarking** - Data-driven routing
6. **9.3 MCP Client Mode** - Design done, connections not yet built
7. **7.4 TUI Dashboard** - Stretch goal
8. **9.7 Future MCP Directions** - Stretch goals

---

## Non-Goals

Not building:
- Chat interface (use ChatGPT, Copilot, Claude, Gemini, Grok, etc.)
- Real-time responses (deep research takes minutes by design)
- Sub-$1 research (comprehensive research costs money)
- Mobile apps
- Features that might not work reliably

## Contributing

High-value areas: context chaining logic, synthesis prompts, cost optimization, provider integrations, CLI UX. Most impactful work is on the intelligence layer, not infrastructure.

## Version History

| Version | Focus | Status |
|---------|-------|--------|
| v2.0-2.1 | Core infrastructure, adaptive research | Complete |
| v2.2 | Semantic commands | Complete |
| v2.3 | Expert system | Complete |
| v2.4-2.5 | MCP integration, agentic experts | Complete |
| v2.6 | Observability, fallback, cost dashboard | In Progress |
| v2.7 | Modern CLI UX | Planned |
| v2.8 | Provider routing | Planned |
| v3.0+ | Self-improvement | Future |

See [docs/MODELS.md](docs/MODELS.md) for model selection, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details and budget protection, and [docs/VISION.md](docs/VISION.md) for long-term direction.

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
