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

## Current Status (v2.12)

Multi-provider research automation with expert system, domain-specific skills, MCP integration, native first-party instruments (Recon + Distillr + Primr; Phase 2b complete), and observability. 4851+ unit tests, 78% branch coverage on Python 3.12-3.14. Toolchain managed by `uv` (`uv.lock` committed); pre-commit hooks with ruff; type checking (mypy) and dependency audit (`pip-audit`) wired into CI as ratcheting baselines (see [Phase E](#phase-e-engineering-standards-and-code-quality-elevation-foundational-continuous)).

### Stable (Production-Ready)

These features are well-tested and used regularly:

- **Core research commands**: `research`, `check`, `learn` - reliable across providers
- **Cost controls**: Budget limits, canonical cost ledger, cost tracking, `costs show/timeline/breakdown/doctor`
- **Expert creation**: `expert make`, `expert chat`, `expert export/import`
- **CLI output modes**: `--verbose`, `--json`, `--quiet`, `--explain`
- **Context discovery**: `deepr search`, `--context <id>` for reusing prior research
- **Provider support**: OpenAI (GPT-5.4, GPT-5.4-pro, GPT-5-mini, GPT-4.1, o3/o4-mini-deep-research), Gemini (3.1 Pro Preview, 3.5 Flash, 3 Flash, 2.5 Flash, Deep Research Agent), xAI Grok (4.20 flagship: Reasoning/Non-Reasoning/Multi-Agent; plus 4.3), Anthropic (Claude Opus 4.8/4.7/4.6, Sonnet 4.6/4.5, Haiku 4.5), Azure AI Foundry (o3-deep-research + Bing, GPT-5/5-mini, GPT-4.1/4.1-mini, GPT-4o)
- **Local storage**: SQLite persistence, markdown reports, expert profiles

### Experimental (Works but Evolving)

These features work but APIs or behavior may change:

- **Web dashboard**: Local research management UI - 12 polished pages with WebSocket push, skeleton loading, shadcn/ui components, mobile nav, accessibility
- **Expert skills**: Domain-specific capability packages with Python tools and MCP bridging. 7 built-in skills (incl. native Recon, Distillr, and Primr), CLI management, web API, auto-activation triggers
- **Native Recon instrument** (v2.11.0): auto-discovered when `pip install recon-tool` is present; autonomous cost-$0 domain probe in agentic expert chat; passive infrastructure/email-security intelligence absorbed into expert context
- **Native Distillr instrument** (v2.12): auto-discovered when `pip install distillr` is present (`distill-mcp` on PATH); source ingestion (papers/videos/sites) into a synthesized corpus, absorbed as academic knowledge with provenance; budget-capped and approval-gated (free `query_library` first)
- **Native Primr instrument** (v2.12): auto-discovered when `pip install primr` is present (`primr-mcp` on PATH); strategic company deep-dives (positioning, hiring signals, initiatives, tech stack) absorbed across infrastructure + strategic categories with report provenance; long-running, budget-capped, every paid run approval-gated (estimate first, `quick_lookup` for fast context)
- **MCP server**: Functional with 21 tools, but MCP spec itself is still maturing
- **Agentic expert chat**: enabled by default in `expert chat` — autonomous research with slash commands, chat modes, visible reasoning, approval flows, expert council, and task planning. Pass `--no-research` to disable autonomous research triggers.
- **Auto-fallback**: Provider failover works, but circuit breaker tuning is ongoing
- **Cloud deployment templates**: AWS/Azure/GCP templates provided but not battle-tested at scale
- **Grok provider**: Grok 4.20 flagship + multi-agent deep research (plus Grok 4.3); legacy models deprecated (retiring May 15, 2026) with auto-migration
- **Anthropic provider**: Uses Extended Thinking + orchestration (no native deep research API)
- **Azure AI Foundry provider**: Agent/Thread/Run pattern with Bing grounding; 7 models (o3-deep-research, gpt-5, gpt-5-mini, gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-4o-mini)

### What Works (Full List)

- Multi-provider support (OpenAI GPT-5.4/5-mini/4.1, Gemini 3.5 Flash/3.1 Pro/Flash-Lite/2.5, Grok 4.20/4.3, Anthropic Claude, Azure, Azure AI Foundry)
- Deep Research via OpenAI API (o3/o4-mini-deep-research) and Gemini Interactions API (Deep Research Agent)
- Semantic commands (`research`, `learn`, `team`, `check`, `make`)
- Expert system with autonomous learning, agentic chat (streaming, 27 slash commands, 4 chat modes, visible reasoning, context compaction, approval flows, expert council, task planning, memory commands), knowledge synthesis, curriculum preview (`expert plan`), domain-specific skills, AI-generated portraits
- Expert skills system: 7 built-in skills, Python + MCP tool types, auto-activation triggers, three-tier storage
- Conversations API for browsing and resuming past chat sessions
- MCP server with 21 tools, persistence, security, multi-runtime configs
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
- `uv`-managed toolchain (`uv.lock` + `.python-version` for reproducible dev/CI/container environments; setuptools build backend preserved for `pip install` compatibility)
- Pre-commit hooks (ruff lint+format, trailing whitespace, debug statement detection); CI also runs mypy (type-check baseline) and pip-audit (dependency audit) as non-blocking gates ratcheting toward blocking (Phase E)
- Coverage configuration with 78% minimum threshold (`fail_under = 78`; branch coverage enabled - stricter than the prior 80% line gate, ratcheting toward 95)
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
- Experts are tailored second brains, not one generic vault. The unit of knowledge is the expert: a domain-scoped knowledge base (beliefs, confidence, gaps, citations) that stays current on its topic and deploys as part of an agent team. Deepr gives you second brains with an s, not a single undifferentiated brain, and the value compounds when those brains are consulted as a team.
- Make experts genuinely agentic: they plan, reflect, self-correct, and learn — not just wrap LLM calls.
- Speak every protocol: MCP for tools, A2A for agent-to-agent, agentskills.io for portability.
- Autonomy earns trust incrementally: start supervised, prove reliability, then expand bounds.
- Engineering standards are a feature: the kernel is meant to be embedded and the MCP server is meant to be installed by other agents, so reproducibility, type safety, and security posture are part of the product, not overhead.

### Phase E: Engineering Standards and Code-Quality Elevation (foundational, continuous)

Goal: hold every line of Deepr to a verifiable, reproducible, secure standard so the kernel is safe to embed and the platform scales across releases without regression. This track runs alongside feature work.

The gate targets below are firm commitments, not a soft "raise it when convenient" ratchet. The one sequencing rule is honest: a blocking gate is only switched on once the code already satisfies it (you do not turn a 23k-line codebase red to make a point). So each gate lands in two moves - wire it in non-blocking to record a baseline, then flip it to blocking once the code is clean - and the flip is committed work, not aspiration.

**Adopted standard (the committed end state):**

- **Python**: floor **3.12** (tested on 3.12 / 3.13 / 3.14). Rationale: 3.10 reaches EOL Oct 2026 and 3.11 only Oct 2027, while a 3.12 floor buys security coverage to Oct 2028 and matches ecosystem convergence (most quality libs, base images, and runners have dropped older). Deliberately not single-version-pinned - Deepr is an embeddable kernel and an MCP server other agents `pip install`, so it must stay broadly installable across the supported window.
- **Toolchain**: `uv` is the canonical package and Python-version manager - reproducible `uv.lock`, pinned `.python-version`, `uv pip install` in CI. setuptools stays the build backend so `pip install deepr-research` keeps working for downstream consumers.
- **Lint / format**: Ruff remains the single linter + formatter. Ruleset modernized to the Python 3.12 baseline (PEP 604 unions, `datetime.UTC`); next, complexity caps (C901) and promotion of the security (S) rules from advisory to blocking for new code.
- **Types**: mypy is a blocking `--strict` gate; target is 100% of `deepr/` strict-clean. Wired non-blocking first to record the baseline, then strict-blocking on `core/` + `providers/` + `mcp/` and every new module, ratcheting package-by-package until the whole tree is clean. (Astral's `ty` is a candidate to replace mypy once it stabilizes.)
- **Coverage**: branch coverage enabled; the `fail_under` gate ratchets 78 -> 85 -> 90 -> 95 as branch-covering tests land (78 is the real branch baseline; branch is stricter than the old 80% line metric). The justified omit list (LLM-driven and live-provider paths) is preserved, not erased to inflate the number.
- **Security**: `pip-audit` blocking on every push; Dependabot weekly (pip + github-actions + npm); SBOM via `uv export` per release; OpenSSF secure-coding practices (boundary validation with Pydantic v2, no secret logging, exception safety) as review criteria.
- **Architecture discipline** (Power-of-10, adapted to Python): bounded loops, narrowest-scope declarations, small functions, no runtime `eval`/`exec` - enforced where Ruff can (complexity, S-rules) and applied as review guidance where it cannot.
- **Validation & invariants** ("parse, don't validate"): external data is parsed once at the boundary into rich domain types (strict Pydantic v2 with `strict=True, extra='forbid'`, frozen dataclasses, `NewType`s) so illegal states are unrepresentable and core logic never receives raw, possibly-invalid primitives. Safety-critical kernel invariants (budget never overspends, cost ledger stays append-only, every claim carries a citation) are enforced with targeted runtime assertions plus the existing Pydantic models. (We evaluated the `deal` Design-by-Contract library and chose plain asserts + Pydantic instead - same guarantees on the paths that matter, no extra dependency or runtime-stripping complexity.)
- **Testing rigor**: beyond branch coverage, prove the suite actually catches regressions. Periodic **mutation testing** (mutmut or equivalent) on kernel modules; **property-based and stateful Hypothesis** for complex lifecycles (budget ledger, expert knowledge/belief state, queue); and **fault-injection / chaos tests** at provider and network boundaries (timeouts, malformed payloads, provider outages) to prove the auto-fallback, circuit breakers, exception hygiene, and structured logging behave under turbulence. `xfail` stays disallowed in CI.
- **Supply chain**: hash-pinned, reproducible installs (`uv sync --frozen` / `uv.lock` hashes) in CI; `uv lock --upgrade` on a schedule behind review gates. *If/when Deepr publishes to PyPI*, publish via OIDC trusted publishing (no static credentials in CI) with GitHub build-provenance attestation. (Full SLSA L3 + in-toto/Sigstore is a deliberate non-goal - see below.)
- **Concurrency discipline** (review guidance): prefer explicit message passing (queues, immutable payloads) over shared mutable state; any shared mutable state crosses threads only behind explicit, reviewable synchronization. Applied as review guidance, not a free-threading mandate (see non-goals).
- **Observability**: align the existing tracing layer (MetadataEmitter, spans, trace IDs) with OpenTelemetry semantic conventions and keep secrets out of logs; evaluate (not mandate) `structlog` for the stdlib-logging surface rather than ripping out working infrastructure.

**Explicit non-goals for this track** (recorded so they are not re-litigated):

- **Pure-Python-first / banning C extensions.** Incompatible with Deepr's foundation: pydantic-core (Rust), aiohttp, numpy, and every provider SDK ship compiled wheels. The dependency base is the value; we will not trade it for a purity constraint.
- **Free-threaded 3.14t as a target.** Deepr is I/O-bound (provider/network calls), so free-threading buys little, and its compiled dependencies do not support the `cp314t` ABI. Revisit only if a genuinely CPU-bound, parallelizable hot path appears and the ecosystem has caught up.
- **Full SLSA Level 3 + in-toto/Sigstore attestation.** Disproportionate for a spare-time, solo-maintained project with no SLA. We adopt the achievable subset (OIDC publishing + GitHub build provenance) instead of the full enterprise apparatus.
- **Wholesale `structlog` migration.** Deepr already has stdlib logging plus a purpose-built tracing layer; aligning that with OTel conventions is higher-value than replacing it.

**Sequenced work:**

- [x] Raise Python floor to 3.12 (dropped 3.9/3.10/3.11); classifiers + ruff `target-version` (`py312`) + CI matrix (3.12/3.13 blocking, 3.14 non-blocking) updated; `uv.lock` regenerated
- [x] Modernize syntax to the 3.12 baseline via Ruff autofix (PEP 604 `X | None`, `datetime.UTC`, exception/import aliases)
- [x] Adopt `uv` in CI; commit `uv.lock` + `.python-version`
- [x] Dependabot (pip + github-actions + npm, weekly)
- [x] mypy wired into CI (non-blocking baseline) with `[tool.mypy]` config; baseline is 314 errors across 76 of 262 checked files
- [x] `pip-audit` wired into CI, **blocking** — baseline cleared by bumping flask-cors past CVE-2024-6839/6844/6866; accepted advisories are pinned via `--ignore-vuln` rather than by disabling the gate
- [x] `core/` driven to mypy `--strict`-clean (44 kernel errors fixed) and flipped to a **blocking** gate - the first strict island (budget, cost, contracts, research orchestration)
- [x] `providers/` driven to mypy `--strict`-clean (82 errors fixed across all 7 adapters + `__init__`; included real fixes - grok's vector-store stubs realigned to the base `DeepResearchProvider` contract, optional-import typing) and added to the blocking `mypy --strict deepr/core deepr/providers` gate
- [ ] Extend the strict-blocking gate to `mcp/` (216 errors), then the rest of the tree (whole-tree `mypy` stays a non-blocking baseline meanwhile)
- [ ] Deferred semantic migrations currently ignored in Ruff: `UP042` (str-enum -> `StrEnum`), `UP047` (PEP 695 generics), and `B905` (explicit `zip(strict=)`) - applied deliberately, not by blanket autofix
- [x] Enable `--cov-branch` (branch baseline 78%); `fail_under = 78`, ratcheting 78 -> 85 -> 90 -> 95 as branch tests land
- [x] `C901` complexity cap (max-complexity 10) surfaced as an advisory CI signal (134 functions over cap); promote to blocking as the worst offenders are refactored. S-rules remain advisory (all 93 current findings are in the documented-legacy set)
- [ ] "Parse, don't validate" pass: strict Pydantic (`strict=True, extra='forbid'`) at boundaries + targeted kernel invariant assertions (budget, append-only ledger, citation provenance)
- [x] Mutation testing (mutmut) wired as a scheduled/on-demand non-blocking job over kernel modules (`[tool.mutmut]` scope: core/, cost ledger, cost safety); establish + raise the mutation score next
- [ ] Expand Hypothesis to property-based + stateful tests on kernel lifecycles (budget ledger, expert/belief state, queue)
- [ ] Fault-injection / chaos tests at provider + network boundaries (timeouts, malformed payloads, provider outages) to validate fallback, circuit breakers, and logging
- [x] SBOM generation (`uv export`, hash-pinned) published as a CI build artifact
- [ ] Supply chain (remaining): switch CI installs to `uv sync --frozen`; add a scheduled `uv lock --upgrade` behind review; (if publishing) OIDC trusted publishing + GitHub build-provenance attestation
- [ ] Align tracing with OpenTelemetry semantic conventions; evaluate `structlog` for the logging surface
- [ ] Extract a reusable CI workflow + Copier/template repo so sibling projects (recon, distillr, primr) inherit the same standard from day zero

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

Builds directly on Phase 2 MCP client profiles, budget propagation, and trace ID stitching. Shipped in effort-to-value order (Recon, then Distillr, then Primr). **All three first-party instruments are now integrated** — Phase 2b is complete; remaining sub-items are follow-ons that depend on the sibling tools shipping new verbs (e.g. distillr `ask`/`audit`) or on Phase 4 (`expert sync`).

- [x] (1) Recon integration (`pip install recon-tool`) — **delivered in v2.11.0**:
  - [x] MCP client connection to recon's `lookup_tenant`, `analyze_posture`, `assess_exposure`, `find_hardening_gaps`, `chain_lookup` tools (auto-discovered when the `recon` binary is on PATH)
  - [x] Expert skill with auto-trigger on company domain mentions — autonomous cost-$0 probe in expert chat, findings absorbed into the system prompt for the turn via `KnowledgeAbsorber.categorize_recon_response`
  - [x] Trace ID pass-through for cross-tool observability (recon probes recorded in `reasoning_trace` with timestamp, domain, findings_count, cost)
- [x] (2) Distillr integration (`pip install distillr`) — **delivered in v2.12**:
  - [x] MCP client connection to distillr's ingest and query tools (built-in `distillr` skill + auto-discovered profile when `distill-mcp` is on PATH)
  - [x] Corpus import bridge: distillr output (MD + YAML) → expert permanent knowledge (`KnowledgeAbsorber.categorize_distillr_response`, absorbed as academic findings with synthesis-path provenance)
  - [x] Async handling with progress notifications for long ingestion runs (profile `progress: true`, reusing the existing MCP client `ProgressNotifier`)
  - [x] Budget propagation (cap model spend per ingestion) — per-call `budget_limit` cap enforced by `BudgetPropagator`; only free `query_library` auto-approves, ingestion is approval-gated
  - [x] Freshness engine: consume distillr's refresh/delta tool to re-run a subscribed topic and integrate only new material - this is what powers expert "stay current" (see Phase 4 expert sync)
  - [ ] Topic subscriptions: experts register topics with distillr; scheduled sync pulls deltas over time (lands with Phase 4 `expert sync`)
  - [ ] Consume distillr's corpus-layer verbs as they ship (`ask`, `audit`, gap-driven discover) instead of reimplementing them; Deepr's job is verification, belief integration, and orchestration on top of distillr's corpus primitives
- [x] (3) Primr integration (`pip install primr`) — **delivered in v2.12**:
  - [x] MCP client connection to primr's analyze_company and batch tools (built-in `primr` skill + auto-discovered profile when `primr-mcp` is on PATH; `research_company`, `batch_analyze`, `generate_strategy`)
  - [x] Expert skill for autonomous company deep-dive delegation (`deepr/skills/primr/`, every paid tool approval-gated, free `estimate_run`/`check_jobs`/`doctor` auto-approve)
  - [x] Async durability for 35-50 min runs (profile `progress: true` + 60m timeout; `check_jobs` polling and resume via the existing MCP task-durability layer; per-call `budget_limit` cap of $5 enforced by `BudgetPropagator`)
  - [x] Quick-mode tool for lighter/faster company context (`quick_lookup`: recon + scrape only, ~5 min)
  - [x] Multi-category absorption (`KnowledgeAbsorber.categorize_primr_response`): recon pre-flight → infrastructure facts, brief/hiring/initiatives → strategic knowledge, each citing the report artifact for provenance

### Phase 3: Routing and Evaluation Confidence

Goal: continuously validate routing quality/cost claims with measurable feedback.

- [x] `deepr providers models` command (model discovery UX): live provider model lists diffed against the registry, scoped by default to newer versions of families already in use, with paste-ready registry stubs (`scripts/discover_models.py`)
- [ ] Stale-model CI checks + provider-family alerting
  - [x] `deepr eval` preflight warns when newer relevant models are missing from the registry
  - [ ] Scheduled CI job that alerts on provider model drift
- [x] Routing preview: `deepr research --preview` shows model choice, estimated cost band, and (in `--auto` mode) routing confidence and reasoning before executing. Works for both explicit `--model/--provider` runs and `--auto` mode. JSON output (`--json`) emits a structured `{preview, executed, provider, model, cost_estimate}` payload for machine consumers. Back-compat: `--dry-run` is preserved as an alias.
- [ ] Eval methodology v2:
  - [ ] Citation quality, grounding, synthesis depth, temporal accuracy
  - [ ] Expert-specific metrics: gap-detection success rate, belief-revision accuracy, citation freshness score, integration quality
  - [ ] Task-level cost-efficiency scoring
  - [ ] Methodology versioning for run comparability
- [ ] A/B shadow mode (opt-in): run shadow query in parallel against baseline for continuous routing comparison

### Phase 4: Expert Intelligence and Quality Loop

Goal: make experts genuinely agentic — self-correcting, strategically autonomous, graph-structured memory.

**Next up (recommended entry points, now unblocked by Phase 2b).** With recon + distillr + primr all integrated, the tightest next increment is the pair that closes the loop on those instruments:

1. **`deepr expert absorb REPORT_ID`** (output-to-knowledge feedback loop, below) — promote good reports/answers into permanent knowledge, verification-gated. Builds directly on the absorption pipeline (`KnowledgeAbsorber.categorize_*`) just extended for distillr/primr.
2. **Dynamic tool selection via gap analysis** (below) — map infrastructure gaps -> recon, academic gaps -> distillr, strategic gaps -> primr. All three target instruments now exist, so the gap-to-tool engine has somewhere to route.

`deepr expert health-check` (knowledge maintenance, read-side, cost-$0) is the natural third step. Reflection loop and graph memory are the larger, higher-risk items and come after.

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
- [ ] Knowledge maintenance loop (the expert keeps its own house in order, building on the staleness + contradiction detection above):
  - [ ] `deepr expert health-check NAME` - read-side audit of the knowledge state in one pass: contradictions between beliefs, orphaned or broken citations, claims missing source provenance, beliefs past their refresh threshold, un-ingested raw material, and suggested new topics + cross-links not yet drawn
  - [ ] Two-phase output: an auditable decision-record report, then an action menu gated by existing approval tiers (AUTO_APPROVE/NOTIFY/CONFIRM); corrective research is opt-in and budget-bounded
  - [ ] Cost-$0 by default (audit only); schedulable so experts self-maintain on a cadence (the scheduled monthly health check, not just scheduled refresh)
  - [ ] For corpus-backed experts, delegate the underlying audit to distillr's `audit` rather than reimplementing link/contradiction/coverage scans; Deepr adds belief-state mapping, confidence, and the action menu on top
- [ ] Output-to-knowledge feedback loop (the compounding flywheel: day-1 basic, day-100 an asset):
  - [ ] `deepr expert absorb REPORT_ID` plus a post-research "integrate this into the expert?" prompt - promote good answers and reports into permanent knowledge with provenance, instead of treating reports as terminal artifacts
  - [ ] Verification-gated by design: every re-ingested answer passes through the existing verify/reflection step before it becomes a belief. This is the safety the naive folder-and-CLAUDE.md version lacks (it warns "the AI writes something slightly wrong, you save it back, the next answer builds on the mistake"); our verify discipline is what makes the loop safe
  - [ ] Dedup against existing beliefs and integrate the delta only (reuses the absorption pipeline); where distillr exposes a corpus-side `ask` verb, consume it and apply verification rather than re-querying raw sources
- [ ] Gap-driven discovery (audit proposes what is missing, not just what the user asked for):
  - [ ] Wire health-check coverage findings into auto-generated discovery queries: "you have 12 sources on X but zero on Y - preview candidates?" This is corpus-gap-driven, complementing the existing goal-driven discovery
  - [ ] Surface as previewable candidates with cost estimate; ingestion stays opt-in and budget-bounded
- [ ] Output style contract for human-read artifacts (distinct from anti-hallucination rules):
  - [ ] A register/anti-slop style guard for briefings and reports (banned filler, em-dash overuse, spelling consistency), separate from the provenance/grounding rules in the research prompts
- [ ] Expert freshness / watch (stay current on a topic over time):
  - [ ] `deepr expert sync NAME` - pull deltas from subscribed sources (distillr refresh, recon delta, primr delta) and integrate only what changed, timestamped
  - [ ] Per-topic refresh cadence and source list, budget-bounded; depends on the Phase 2b distillr freshness path
  - [ ] Schedulable; surfaces a change summary (what is new, what shifted, what to review)
- [ ] Dynamic tool selection via gap analysis:
  - [ ] Gap-to-tool mapping engine (infrastructure gaps → recon, academic gaps → distillr, strategic gaps → primr; instruments delivered in Phase 2b)
  - [ ] Value/cost estimation per gap-fill option
  - [ ] Strategic prioritization: fill highest-value gaps first within budget
- [x] Expert-as-guardrail mode:
  - [x] `validate` tool alongside `research` and `chat` — `deepr expert validate NAME CLAIM` (also `--from-file -` for stdin) and `deepr_expert_validate` MCP tool. Expert applies its existing knowledge as a filter/validator; pure read-side, never mutates the expert.
  - [x] PASS/WARN/FAIL assessment with citations and confidence — claim IDs returned by the validator model are resolved back to canonical `Claim` objects so callers get full citation provenance, not just statements.
  - [x] Useful for downstream agents that need domain validation before acting — structured JSON output (verdict, confidence, reasoning, supporting/contradicting claims, caveats) makes the verdict machine-actionable.
- [ ] Expert manifest diff (`Delta`) and explicit `ExpertPolicy` type
- [ ] Optional `--high-trust-only` mode (primary/secondary sources only)
- [ ] Structured corpus import as first-class skill:
  - [ ] One-command ingest of MD/JSON/JSONL bundles as permanent expert knowledge
  - [ ] Auto-gap detection and citation mapping on imported corpora
  - [ ] Works with any structured output (research reports, synthesis docs, company briefs)
- [ ] Per-expert SKILL.md export (`deepr expert export --format skill NAME`):
  - Generic tool-surface export already exists (`deepr/skills/packager.SkillPackager` -> agentskills.io SKILL.md). The gap is an expert-scoped skill: a SKILL.md whose tools/triggers/instructions are populated from one expert and whose body calls that expert via MCP. This is the distribution play - the validated interoperability direction is Deepr exposed as the MCP server / SKILL.md that hosts (Claude Cowork, Copilot agent mode, Cursor, Goose) *call*, not Deepr delegating execution outward (those hosts consume MCP servers; they are not callable as tools). agentskills.io SKILL.md is now broadly adopted (Claude Code, Codex CLI, Gemini CLI, VS Code Copilot, Cursor, OpenClaw), so one export reaches every major host.
- [ ] Skill auto-generation from research artifacts:
  - [ ] `expert skill make "Topic" --from-report artifact.md` generates skill with tools and triggers
  - [ ] Dependency tracking between generated skills
  - [ ] Efficacy scoring (citations added, gaps closed, cost impact)
  - [ ] Trace-based skill self-improvement: improve generated skills/prompts from real execution traces, gated behind tests + size limits + human-review/PR. Reference approach: GEPA (genetic-Pareto reflective prompt evolution) + DSPy over traces - zero-GPU, API-only, validated (ICLR 2026); composes with the reflection + absorb loop above (the trace is the artifact those loops already produce).
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

#### AI/agentic security (scoped to Deepr's real surface)

Deepr is an orchestration layer over hosted model APIs - it does not train, fine-tune, or serve model weights - so its security work targets *ingested data* and *agentic tool use*, not the model internals. The threats that actually apply:

- [ ] **Indirect prompt-injection defense for ingested/tool content.** Web search results, scraped pages, uploaded docs, and first-party MCP tool output (recon/distillr/primr) are untrusted input that flows into prompts and into expert beliefs. Extend `utils/prompt_security.PromptSanitizer` to the ingestion + tool-result boundary (not just user prompts), delimit/quarantine untrusted spans, and gate belief absorption behind the existing verify/reflection step so a poisoned source cannot silently become a belief. This is Deepr's #1 AI-security risk.
- [ ] **Agentic trust boundaries.** Formalize the existing approval tiers (AUTO_APPROVE/NOTIFY/CONFIRM) + per-MCP-server tool allowlists, rate limits, and egress controls (overlaps Phase 2 elicitation sandboxing); capability-scope what each tool/expert may do, and never auto-approve a paid or write-capable tool.
- [ ] **Output/handoff validation.** Validate MCP/A2A outputs against the published handoff schemas (above) before downstream agents consume them - a compromised expert must not emit malformed/unsafe artifacts.
- [ ] **Agentic red-team suite.** Automated prompt-injection / jailbreak / tool-abuse tests against expert chat and the ingestion paths (the security-flavored sibling of the Phase E fault-injection tests); track attack-success-rate as a metric.
- [ ] **Threat model doc** (MITRE ATLAS-style) for Deepr's actual surface - ingestion, agentic tools, MCP/web/A2A endpoints, secret handling - that records what is explicitly out of scope (see below) so effort stays proportional.
- [ ] Secret hygiene hardening: least-privilege provider keys, no secrets in logs/traces (redaction exists), and secret-scanning in CI.

**Explicit security non-goals** (Deepr does not own the model, so these belong to the providers, not us):

- Training/fine-tuning-time defenses (data poisoning, label-flip, DP-SGD, adversarial training, certified robustness) - Deepr trains nothing.
- Model-weight protection (extraction/inversion/membership-inference defenses, watermarking/fingerprinting, TEEs/enclaves, homomorphic encryption, confidential computing, post-quantum model crypto) - Deepr holds no weights; it calls hosted APIs.
- Inference-layer isolation (confidential VMs / GPU enclaves for serving) - inference runs on the providers' infrastructure under their shared-responsibility model.

### Backlog (Not in Active Sequence)

- [ ] Self-improving routing via expert feedback loops (experts detect poor routing in their own gaps → trigger micro-evals → propose routing-table updates)
- [ ] Azure Foundry durable agent orchestration + HITL (long-running experts that survive restarts, wait for human approval via SignalR/Durable Functions)
- [ ] Expert watch (extension): broaden `deepr expert sync` (Phase 4) beyond first-party tools to arbitrary configured MCP or REST endpoints on schedule
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
  - [ ] Raise per-module coverage on core modules above the 80% global gate

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
| **Platform hygiene & DX** | Deprecations, lint enforcement, test collection stability, secret redaction, version truth, CI signals | High |
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
| v2.10 | Agentic infrastructure core, Grok 4.20 flagship, legacy migration, Azure Foundry parity | In Progress |
| v2.10.1 | MCP client + A2A protocol, agent interoperability, skill portability | Complete |
| v2.10.2-2.10.3 | Security hardening, MCP confirmation gate, 80% coverage gate, 5-round bug-hunt sweep | Complete |
| v2.11.0 | Recon native integration (Phase 2b #1), version centralization, doc_reviewer hardening, MCP/async cancellation correctness | Complete |
| v2.12 | Distillr + Primr integrations delivered (Phase 2b #2 & #3, completing Phase 2b); Phase E engineering-standards foundation (uv + uv.lock, Python 3.12 floor + 3.13/3.14 matrix, mypy + pip-audit CI baselines, Dependabot, py312 syntax modernization); routing preview done | In Progress |
| v2.13 | Expert intelligence: reflection loop, graph memory, knowledge maintenance loop (health-check, absorb, freshness/sync), dynamic tool selection | Planned |
| v2.14 | Autonomous research campaigns, multi-day expert investigations | Planned |
| v2.15 | Ops analytics, anomaly alerts, team/RBAC, security hardening | Planned |
| v3.0+ | Self-improving routing, autonomous learning, campaign orchestration | Future |

---

**Questions?** Open a [GitHub Discussion](https://github.com/blisspixel/deepr/discussions) or check the [documentation](docs/).

[MIT License](LICENSE) · [GitHub](https://github.com/blisspixel/deepr)
