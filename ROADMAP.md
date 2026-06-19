# Deepr Roadmap

> Development priorities and planned features. Model and pricing facts come from the registry (`src/deepr/providers/registry.py`); see [docs/MODELS.md](docs/MODELS.md).

> ## STOP - no brittle junk
>
> Before adding anything here, read [docs/plans/AGENTIC_BALANCE.md](docs/plans/AGENTIC_BALANCE.md)
> (keep it current when a decision moves the boundary). Two failure modes keep
> dragging this project backward, and **both make the product worse**. Most items
> below were audited against them; an item that trips either gets cut, not built.
>
> **1. Brittle rules that encode *meaning*.** Lexical / word-overlap / regex /
> keyword / banned-word checks used as a *verdict* on contradiction, grounding,
> atomicity, dedup, similarity, categorization, or writing quality. These are the
> single most repeated wrong turn in this codebase: they feed false positives
> straight into the experts, so the core gets *worse*. Determinism belongs on
> form and side-effects (schema, types, ranges, spend, writes, flowchartable
> control flow); **model judgment owns meaning**, calibrated before it is trusted.
> A cheap lexical check may *route* into a model check but never *conclude*.
>
> **2. Low-value internal churn dressed as rigor.** Config migrations,
> file-size / complexity / coverage / mutation ratchets, type-strictness sweeps,
> decomposing files for tidiness - work no user feels, that breaks adjacent things
> and diverts effort from the actual product (calibrated experts + the evidence
> layer). When a "mechanical" refactor keeps surfacing breakage, **STOP** - the
> juice is not worth the squeeze.
>
> **The test for any item:** does a user feel it? Is it guarding form/side-effects
> (rule is fine) or encoding meaning (route to the model)? If it is neither of
> those *and* a user does not feel it - **cut it.**

## Quick Links

| Document | Description |
|----------|-------------|
| [Models](docs/MODELS.md) | Provider comparison, costs, model selection |
| [Experts](docs/EXPERTS.md) | Creating and using domain experts |
| [Integrations](docs/INTEGRATIONS.md) | First-party tool integrations (recon, distillr, primr) |
| [Agentic Vision](docs/AGENTIC_VISION.md) | Agentic architecture, A2A, reflection, campaigns |
| [Agentic Balance](docs/plans/AGENTIC_BALANCE.md) | **Read before adding a rule or making something agentic** - what deepr hardcodes vs lets the model decide |
| [Architecture](docs/ARCHITECTURE.md) | Technical details, security, observability |
| [Supported Surface](docs/SUPPORTED_SURFACE.md) | Stable, experimental, planned, and export guarantees |
| [Changelog](docs/CHANGELOG.md) | Release history with migration notes |
| [Vision](docs/VISION.md) | Long-term direction (v3.0+) |

---

## Architecture Layers

Deepr is organized in three layers. When contributing, it helps to know which layer you're working in:

| Layer | What lives here | Examples |
|-------|----------------|----------|
| **Kernel** - reusable agent infrastructure | Task execution, budget enforcement, provider routing, trace/decision logging | `core/`, `observability/`, `providers/`, `queue/`, `routing/` |
| **Primitives** - swappable domain modules | Web search, citation extraction, expert memory, summarization, gap detection | `experts/`, `services/`, `tools/`, `storage/` |
| **Interfaces** - user-facing surfaces | CLI for scripting and experiments, web dashboard for operations and analytics | `cli/`, `web/`, `mcp/` |

The kernel is designed to be embeddable in other agent projects. The primitives are specific to research but follow patterns (belief states, gap backlogs, refresh policies) that generalize. The interfaces are thin wrappers over the lower layers.

**Interoperability model:** Deepr is built to be one role on a larger agent team, not the orchestrator. Experts produce structured, handoff-ready artifacts (reports with citations, belief states, gap backlogs) that downstream agents can consume directly. An external orchestrator assigns work to a Deepr expert the same way it would assign work to any other role - via MCP tool calls with budget contracts and trace IDs that stitch across agent boundaries. This means Deepr doesn't need to know about the full workflow; it just needs to do its job well and hand off cleanly.

---

## Current Status (v2.16.2)

Multi-provider research automation with expert system, domain-specific skills, MCP integration, native first-party instruments (Recon + Distillr + Primr; Phase 2b complete), and observability. 5700+ unit tests, 80% branch coverage enforced on Python 3.12/3.13/3.14 (all blocking). Toolchain managed by `uv` (`uv.lock` committed); pre-commit hooks with ruff; type checking (mypy) and dependency audit (`pip-audit`) wired into CI as ratcheting baselines (see [Phase E](#phase-e-engineering-standards-and-code-quality-elevation-foundational-continuous)).

**Current main (v2.16 capacity track):** the evidence layer is available (`deepr eval continuity` + the calibration harness `eval calibrate`, design: [calibration-and-trust.md](docs/design/calibration-and-trust.md)); **$0 local-model execution** (local-only `expert make --local`, Ollama backend, `expert sync`/`absorb --local`, plus `expert sync --local --fresh-context` and `--deep-context` for free-only retrieval context with optional SearXNG), **local comparison** (`deepr eval local` with a local Ollama judge or explicit CLI judge), **local context evaluation** (`deepr eval local-context` comparing no/fresh/deep context), **source-pack sync artifacts** for context-bearing runs, **eval-artifact admission** (`deepr capacity admit --from-eval latest`), **runtime admitted-score quality gating**, **capacity next actions** (`deepr capacity next`), and **capacity visibility** (`deepr capacity`) are wired toward routing on owned/prepaid capacity before metered API, including the normalized `ResearchBackend` profile, append-only `quota_ledger.jsonl` substrate, pure backend eligibility for observed plan-quota state, and pure backend selection with measured quality floors (design: [capacity-waterfall.md](docs/design/capacity-waterfall.md); fresh local context: [local-fresh-context.md](docs/design/local-fresh-context.md)); **portable experts** - one data dir (`DEEPR_DATA_DIR`) relocates experts + research to a synced folder so they follow you across machines ([ADR 0004](docs/decisions/0004-one-experts-root-and-portable-data-dir.md)); routing **quality priors** keep auto mode useful without paid evals; and guided setup (`deepr init`) is stable. Remaining capacity work is plan-quota adapters, live window/credit probes, adapter writes, scheduler integration, auto-mode runtime integration, and scheduler-facing QOL. Next after capacity is a verified expert-loop and OKF interchange release: make the existing loops observable, resumable, and portable without making OKF the source of truth. The cross-cutting principle for what deepr hardcodes vs lets the model decide (workflow vs agent, determinism on side-effects not meaning) is set in [AGENTIC_BALANCE.md](docs/plans/AGENTIC_BALANCE.md); the boundary for which checks specifically are deterministic vs model-based is its instance in [checks-deterministic-vs-agentic.md](docs/design/checks-deterministic-vs-agentic.md).

### Stable (Production-Ready)

These features are well-tested and used regularly:

- **Core research commands**: `research`, `check`, `learn` - reliable across providers
- **Guided setup**: `deepr init` (detect keys, write `.env`, set budget + a portable data dir), `deepr doctor` (diagnostics incl. storage roots, severity-aware so optional/first-run state is not flagged as errors)
- **Cost controls**: Budget limits, canonical cost ledger, cost tracking, `costs show/timeline/breakdown/doctor`
- **Expert creation**: `expert make`, `expert chat`, `expert export/import`
- **Portable experts**: one `DEEPR_DATA_DIR` relocates experts + research to a synced folder (cross-machine); default `data/` unchanged ([ADR 0004](docs/decisions/0004-one-experts-root-and-portable-data-dir.md))
- **CLI output modes**: `--verbose`, `--json`, `--quiet`, `--explain`
- **Context discovery**: `deepr search`, `--context <id>` for reusing prior research
- **Provider support**: OpenAI (GPT-5.5, GPT-5.5-pro, GPT-5.4 family, GPT-5-mini, GPT-4.1, o3/o4-mini-deep-research), Gemini (3.1 Pro Preview, 3.5 Flash, 3 Flash, 2.5 Flash, Deep Research Agent), xAI Grok (4.20 flagship: Reasoning/Non-Reasoning/Multi-Agent; plus 4.3), Anthropic (Claude Fable 5, Opus 4.8/4.7/4.6, Sonnet 4.6/4.5, Haiku 4.5), Azure AI Foundry (o3-deep-research + Bing, GPT-5/5-mini, GPT-4.1/4.1-mini, GPT-4o)
- **Local storage**: SQLite persistence, markdown reports, expert profiles

### Experimental (Works but Evolving)

These features work but APIs or behavior may change:

- **Web dashboard**: Local research management UI - 12 polished pages with WebSocket push, skeleton loading, shadcn/ui components, mobile nav, accessibility
- **Expert skills**: Domain-specific capability packages with Python tools and MCP bridging. 7 built-in skills (incl. native Recon, Distillr, and Primr), CLI management, web API, auto-activation triggers
- **Native Recon instrument** (v2.11.0): auto-discovered when `pip install recon-tool` is present; autonomous cost-$0 domain probe in agentic expert chat; passive infrastructure/email-security intelligence absorbed into expert context
- **Native Distillr instrument** (v2.12): auto-discovered when `pip install distillr` is present (`distill-mcp` on PATH); source ingestion (papers/videos/sites) into a synthesized corpus, absorbed as academic knowledge with provenance; budget-capped and approval-gated (free `find_insights` corpus search first)
- **Native Primr instrument** (v2.12): auto-discovered when `pip install primr` is present (`primr-mcp` on PATH); strategic company deep-dives (positioning, hiring signals, initiatives, tech stack) absorbed across infrastructure + strategic categories with report provenance; long-running, budget-capped, every paid run approval-gated (estimate first, `quick_lookup` for fast context)
- **MCP server**: Functional with 28 tools, but MCP spec itself is still maturing
- **Agentic expert chat**: enabled by default in `expert chat` - autonomous research with slash commands, chat modes, visible reasoning, approval flows, expert council, and task planning. Pass `--no-research` to disable autonomous research triggers.
- **Local-model execution + capacity** (v2.16, in progress): `deepr capacity` (+ `--probe`) shows owned/prepaid capacity (local Ollama, plan CLIs, metered APIs) and summarizes locally observed plan-quota state from `quota_ledger.jsonl`; `expert make --local` creates provider-free local experts; a local Ollama backend runs research at $0 via the injectable seams (`expert sync`/`absorb --local`), with `expert sync --local --fresh-context` adding a free-only retrieval pack and `--deep-context` adding bounded multi-query retrieval before the local model call. The free path can use explicit URLs, a configured SearXNG endpoint (`DEEPR_SEARXNG_URL`), or DuckDuckGo when the optional package is installed; it blocks instead of falling through to metered APIs when a context flag cannot use local capacity. `deepr eval local` compares local Ollama models with a local judge or an explicitly approved CLI judge (`--judge-cli grok` / `--judge-command`) so admission decisions have review evidence before automation; `deepr eval local-context` compares no context, fresh context, and deep context so source envelopes have evidence before schedulers select them. Context-bearing sync runs persist source-pack artifacts and fail closed if provenance cannot be written. The first waterfall rung is wired: eval-gated local **admission** (`deepr capacity admit`/`admissions`/`revoke`, including `--from-eval latest`) plus runtime admitted-score quality gating makes `expert sync`/`absorb` drain a scored, admitted local model at $0 before any metered API call, with `--local`/`--api` overrides. `deepr capacity next` now ranks the current block reason, local setup, latest-artifact admission, eval refresh, and explicit metered fallback. The normalized `ResearchBackend` profile, backend eligibility gate, and backend selector are in place for routing, logging, quota decisions, reserve floors, overage blocking, measured quality floors, and no-observation stops. Still to come: plan-quota CLI adapters, live quota probes, adapter writes, scheduler integration, auto-mode runtime integration, and scheduler-facing QOL. Design: [capacity-waterfall.md](docs/design/capacity-waterfall.md); [local-fresh-context.md](docs/design/local-fresh-context.md)
- **Evidence layer** (v2.15): `deepr eval continuity` (staleness honesty / abstention / contradiction-surfacing / what-changed exactness, measured from stored state at $0) and `deepr eval calibrate` (does extraction confidence track grounding? reliability curve + ECE + Platt threshold; `--from` graded pairs at $0, `--corpus` runs the paid extraction + pre-grade). First curve in [docs/CALIBRATION.md](docs/CALIBRATION.md)
- **Auto-fallback**: Provider failover works, but circuit breaker tuning is ongoing
- **Cloud deployment templates**: AWS/Azure/GCP templates provided but not battle-tested at scale
- **Grok provider**: Grok 4.20 flagship + multi-agent deep research (plus Grok 4.3); legacy models deprecated (retiring May 15, 2026) with auto-migration
- **Anthropic provider**: Uses Extended Thinking + orchestration (no native deep research API)
- **Azure AI Foundry provider**: Agent/Thread/Run pattern with Bing grounding; 7 models (o3-deep-research, gpt-5, gpt-5-mini, gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-4o-mini)

### What Works (Full List)

- Multi-provider support (OpenAI GPT-5.4/5-mini/4.1, Gemini 3.5 Flash/3.1 Pro/Flash-Lite/2.5, Grok 4.20/4.3, Anthropic Claude, Azure, Azure AI Foundry)
- Deep Research via OpenAI API (o3/o4-mini-deep-research) and Gemini Interactions API (Deep Research Agent)
- Semantic commands (`research`, `learn`, `team`, `check`, `make`)
- Expert system with autonomous learning, agentic chat (streaming, 27 slash commands, 4 chat modes, visible reasoning, context compaction, approval flows, expert council, task planning, memory commands), knowledge synthesis, curriculum preview (`expert plan`), guardrail validation (`expert validate`), knowledge maintenance (`expert health-check`), report-to-knowledge absorption (`expert absorb`), report reflection (`expert reflect`), gap-to-tool routing (`expert route-gaps`), per-expert SKILL.md export (`expert export-skill`), domain-specific skills, AI-generated portraits
- Expert skills system: 7 built-in skills, Python + MCP tool types, auto-activation triggers, three-tier storage
- Conversations API for browsing and resuming past chat sessions
- MCP server with 28 tools, persistence, security, multi-runtime configs
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
- Coverage configuration with 80% minimum threshold (`fail_under = 80`; branch coverage enabled - stricter than the prior 80% line gate, ratcheting toward 95)
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

- **No brittle junk (the governing filter - see the STOP banner above).** Reject
  on sight: (a) rules that encode *meaning* (lexical/keyword/regex/banned-word
  verdicts on contradiction, grounding, dedup, similarity, categorization,
  writing quality) - route to a calibrated model instead; and (b) low-value
  internal churn no user feels (config migrations, coverage/complexity/mutation/
  file-size ratchet-chasing, type-strictness sweeps). Every item earns its place
  by user-felt value or by guarding form/side-effects. "Tidiness" and "rigor for
  its own sake" are not justifications. When a refactor keeps breaking adjacent
  things, stop - the juice is not worth the squeeze.
- Prioritize research infrastructure over chat novelty.
- Preserve budgeted autonomy, auditability, and provider portability.
- Ship capabilities that improve measurable quality, cost-efficiency, and reliability.
- Keep orchestration bounded: no unbounded swarms, no opaque autonomy.
- Design for composability: experts are roles that receive input, produce handoff-ready output, and participate in multi-agent teams without owning the workflow.
- Experts are tailored second brains, not one generic vault. The unit of knowledge is the expert: a domain-scoped knowledge base (beliefs, confidence, gaps, citations) that stays current on its topic and deploys as part of an agent team. Deepr gives you second brains with an s, not a single undifferentiated brain, and the value compounds when those brains are consulted as a team.
- Make experts genuinely agentic: they plan, reflect, self-correct, and learn - not just wrap LLM calls.
- Close the loop before widening it (loop engineering): an advisory surface (health-check proposes, route-gaps recommends, reflection emits follow-up queries) is half a loop - the value compounds when it graduates to scheduled, budget-bounded *execution* that persists across process restarts. Prioritize loop closers (expert sync, auto re-research, autonomous gap-fill, durable learner jobs) over adding more advisory surfaces; the trade of tokens for human time is what Phase 6's prepaid/local capacity makes affordable. A Deepr loop is not just `while not done`: it has durable state, a budget/capacity contract, an independent verifier, a resumable run record, a clear stop condition, and acceptance metrics.
- Admit loops only when the harness can prove progress: the task repeats, verification is automated, budget/capacity is explicit, and the agent has the tools/logs/state needed to inspect failures. If any of those are missing, keep the surface advisory, one-shot, or human-gated. The minimum viable Deepr loop is an automation trigger, a reusable expert context package, a durable state file/record, and a verifier gate. Goal loops come before meta/team loops; Deepr widens autonomy only after the closed loop has acceptable acceptance rate, cost per accepted knowledge change, and failure telemetry.
- Treat portable knowledge formats as interchange, not authority. OKF fits Deepr as an export/import contract (Markdown concepts, YAML frontmatter, `index.md`, `log.md`, bundle links) because agents can read it anywhere. It must remain a derived view or an ingestion source: canonical truth stays in the structured belief/event/edge store, and OKF import goes through the same verify/absorb pipeline as any other corpus. Do not let an agent-maintained wiki bypass source trust, contradiction checks, or the generated-artifact regeneration invariant.
- Self-improvement is a verification problem (recursive self-improvement, bounded): Deepr runs improvement loops (knowledge: research -> verified absorb -> beliefs -> reflection -> re-research; routing: evals -> rankings -> picks -> outcomes; self-knowledge: health-check/what-changed/contested), and is the substrate for *other* agents' improvement loops (trusted memory + perspective deltas + contradiction surfacing + inference chains + bounded spend). The governing insight, proven live 2026-06-11 twice: an unverified improvement loop is a degradation loop - saturated eval scores "improved" routing into a nano model; a bypassable budget gate was no gate. The sign of the feedback is set by measurement integrity and gate integrity, so verification machinery is never overhead on the loops - it IS the loops. Unbounded self-modification stays a non-goal; machinery-level self-improvement (trace-based skill/prompt evolution) ships only behind tests, size limits, and human review.
- Speak every protocol: MCP for tools, A2A for agent-to-agent, agentskills.io for portability.
- Autonomy earns trust incrementally: start supervised, prove reliability, then expand bounds.
- Engineering standards are a feature *only where they protect the user*: money-path integrity (no surprise bills, append-only ledger), security/prompt-injection defense, and not shipping broken installs are part of the product. But ratchet-chasing for its own sake - coverage %, mutation score, file-size/complexity caps, whole-tree type-strictness - is the churn trap (Planning Principle 1b); it must never divert from the experts + evidence-layer core, and is explicitly deprioritized below it.

### Phase E: Engineering Standards and Code-Quality Elevation (foundational, continuous)

Goal: hold every line of Deepr to a verifiable, reproducible, secure standard so the kernel is safe to embed and the platform scales across releases without regression. This track runs alongside feature work.

> **Split this track by Planning Principle 1b.** KEEP (protects users, ship it):
> the money-path invariants (no surprise bills, append-only ledger), security /
> prompt-injection defense, dependency audit, not-shipping-broken-installs.
> DEPRIORITIZE (churn, do only when cheap and isolated, never as a goal in
> itself): whole-tree `mypy --strict` sweeps, mutation-score chasing, coverage-%
> ratchets, the full SBOM/supply-chain apparatus. Standards serve the product;
> they are not the product.

The gate targets below are firm commitments, not a soft "raise it when convenient" ratchet. The one sequencing rule is honest: a blocking gate is only switched on once the code already satisfies it (you do not turn a 23k-line codebase red to make a point). So each gate lands in two moves - wire it in non-blocking to record a baseline, then flip it to blocking once the code is clean - and the flip is committed work, not aspiration.

**Adopted standard (the committed end state):**

- **Python**: floor **3.12** (tested on 3.12 / 3.13 / 3.14). Rationale: 3.10 reaches EOL Oct 2026 and 3.11 only Oct 2027, while a 3.12 floor buys security coverage to Oct 2028 and matches ecosystem convergence (most quality libs, base images, and runners have dropped older). Deliberately not single-version-pinned - Deepr is an embeddable kernel and an MCP server other agents `pip install`, so it must stay broadly installable across the supported window.
- **Toolchain**: `uv` is the canonical package and Python-version manager - reproducible `uv.lock`, pinned `.python-version`, `uv pip install` in CI. setuptools stays the build backend so `pip install deepr-research` keeps working for downstream consumers.
- **Lint / format**: Ruff remains the single linter + formatter. Ruleset modernized to the Python 3.12 baseline (PEP 604 unions, `datetime.UTC`); next, complexity caps (C901) and promotion of the security (S) rules from advisory to blocking for new code.
- **Types**: mypy is a blocking `--strict` gate; target is 100% of `deepr/` strict-clean. Wired non-blocking first to record the baseline, then strict-blocking on `core/` + `providers/` + `mcp/` and every new module, ratcheting package-by-package until the whole tree is clean. (Astral's `ty` is a candidate to replace mypy once it stabilizes.)
- **Coverage**: branch coverage enabled; the `fail_under` gate ratchets 80 -> 85 -> 90 -> 95 as branch-covering tests land (80 is the current branch floor; branch is stricter than the old 80% line metric). The justified omit list (LLM-driven and live-provider paths) is preserved, not erased to inflate the number.
- **Security**: `pip-audit` blocking on every push; Dependabot weekly (pip + github-actions + npm); SBOM via `uv export` per release; OpenSSF secure-coding practices (boundary validation with Pydantic v2, no secret logging, exception safety) as review criteria.
- **Architecture discipline** (Power-of-10, adapted to Python): bounded loops, narrowest-scope declarations, small functions, no runtime `eval`/`exec` - enforced where Ruff can (complexity, S-rules) and applied as review guidance where it cannot.
- **Validation & invariants** ("parse, don't validate"): external data is parsed once at the boundary into rich domain types (strict Pydantic v2 with `strict=True, extra='forbid'`, frozen dataclasses, `NewType`s) so illegal states are unrepresentable and core logic never receives raw, possibly-invalid primitives. Safety-critical kernel invariants (budget never overspends, cost ledger stays append-only, every claim carries a citation) are enforced with targeted runtime assertions plus the existing Pydantic models. A further **regeneration invariant** keeps generated artifacts honest: every per-expert SKILL.md export, report, briefing, and expert digest is a derived view, never the source of truth - it must be fully regenerable from the structured belief store and is never hand-edited as authoritative, so a stale or hand-edited artifact can never silently become canonical knowledge (the structured-store-is-canonical, views-are-disposable discipline that lets synthesis happen at compile/query time instead of destructively at ingest). (We evaluated the `deal` Design-by-Contract library and chose plain asserts + Pydantic instead - same guarantees on the paths that matter, no extra dependency or runtime-stripping complexity.)
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

- [x] Raise Python floor to 3.12 (dropped 3.9/3.10/3.11); classifiers + ruff `target-version` (`py312`) + CI matrix updated; `uv.lock` regenerated
- [x] Python 3.14 promoted to a **blocking** CI matrix entry (2026-06-11): the full `[dev,full]` extras install and the entire suite pass on 3.14, so the wheel-availability caveat that kept it non-blocking no longer applies. Full supported window: 3.12 / 3.13 / 3.14, all blocking.
- [x] Modernize syntax to the 3.12 baseline via Ruff autofix (PEP 604 `X | None`, `datetime.UTC`, exception/import aliases)
- [x] Adopt `uv` in CI; commit `uv.lock` + `.python-version`
- [x] Dependabot (pip + github-actions + npm, weekly)
- [x] mypy wired into CI (non-blocking baseline) with `[tool.mypy]` config; baseline is 314 errors across 76 of 262 checked files
- [x] `pip-audit` wired into CI, **blocking** - baseline cleared by bumping flask-cors past CVE-2024-6839/6844/6866; accepted advisories are pinned via `--ignore-vuln` rather than by disabling the gate
- [x] `core/` driven to mypy `--strict`-clean (44 kernel errors fixed) and flipped to a **blocking** gate - the first strict island (budget, cost, contracts, research orchestration)
- [x] `providers/` driven to mypy `--strict`-clean (82 errors fixed across all 7 adapters + `__init__`; included real fixes - grok's vector-store stubs realigned to the base `DeepResearchProvider` contract, optional-import typing) and added to the blocking `mypy --strict deepr/core deepr/providers` gate
- [x] Extend the strict-blocking gate to `mcp/` (216 errors fixed; third strict island, shipped v2.12 - the blocking gate now covers `core/` + `providers/` + `mcp/`)
- [ ] Extend the strict-blocking gate to the rest of the tree, package-by-package (whole-tree `mypy` stays a non-blocking baseline meanwhile)
- [ ] Deferred semantic migrations currently ignored in Ruff: `UP042` (str-enum -> `StrEnum`), `UP047` (PEP 695 generics), and `B905` (explicit `zip(strict=)`) - applied deliberately, not by blanket autofix
- [x] Enable `--cov-branch` (branch baseline 78%, raised to 80% gate); `fail_under = 80`, ratcheting 80 -> 85 -> 90 -> 95 as branch tests land
- [x] `C901` complexity cap (max-complexity 10) and the security `S` rules surfaced as advisory CI signals, then put under a **blocking no-growth ratchet** in Phase Q0 (2026-06-12): the counts (C901 144, S 97) are baselined and CI fails if either grows. Full promotion to blocking `select` (cap to 10, `S` clean) is Phase Q4 as the backlog is refactored down. See [Phase Q](#phase-q-code-health-hardening-foundational-continuous).
- [ ] "Parse, don't validate" pass: strict Pydantic (`strict=True, extra='forbid'`) at boundaries + targeted kernel invariant assertions (budget, append-only ledger, citation provenance, generated-artifact regenerability)
- [x] Mutation testing (mutmut) wired as a scheduled/on-demand non-blocking job over kernel modules (`[tool.mutmut]` scope: core/, cost ledger, cost safety); establish + raise the mutation score next
- [ ] Expand Hypothesis to property-based + stateful tests on kernel lifecycles (budget ledger, expert/belief state, queue)
- [ ] Fault-injection / chaos tests at provider + network boundaries (timeouts, malformed payloads, provider outages) to validate fallback, circuit breakers, and logging
- [x] SBOM generation (`uv export`, hash-pinned) published as a CI build artifact
- [ ] Supply chain (remaining): switch CI installs to `uv sync --frozen`; add a scheduled `uv lock --upgrade` behind review; (if publishing) OIDC trusted publishing + GitHub build-provenance attestation
- [ ] Align tracing with OpenTelemetry semantic conventions; evaluate `structlog` for the logging surface
- [ ] Extract a reusable CI workflow + Copier/template repo so sibling projects (recon, distillr, primr) inherit the same standard from day zero

### Phase Q: Code-Health Hardening (DEPRIORITIZED - this is the churn track)

> **This whole phase is Planning Principle 1b territory: low-value internal work
> no user feels.** Q0 (the un-regressable ratchets) shipped and stays. The rest
> is explicitly *below* the experts + evidence-layer core and must never divert
> from it. Do an item only when it is genuinely cheap and isolated; the moment a
> "tidy" change starts breaking adjacent things, STOP and back out (that is the
> trap - see the STOP banner). Do not chase coverage %, mutation scores, file-size
> or complexity caps as goals in themselves.

Full assessment: [docs/design/code-health.md](docs/design/code-health.md).

- [x] **Q0 - Ratchets (un-regressable first, no behavior change)** - shipped 2026-06-12, blocking in CI, ruff pinned to 0.15.17 so counts are reproducible:
  - [x] Q0.1 File-size guard: `scripts/check_file_sizes.py` fails CI on any new `deepr/*.py` over 1000 lines; the 17 current over-ceiling files are grandfathered at their exact size (may shrink, never grow) - a debt register that only ratchets down
  - [x] Q0.2 Complexity ratchet: `scripts/check_ratchets.py` baselines the 144 C901-over-cap functions; CI fails if the count grows
  - [x] Q0.3 Security ratchet: same script baselines the 97 ruff `S` findings; CI fails on growth (drive toward flipping `S` into the blocking `select` in Q4)
- [ ] **Q1 - One way to do each thing:**
  - **Q1.1 config migration - ABANDONED (2026-06-14) as not worth the churn.**
    Attempted `load_config()` -> `get_settings()`; it repeatedly broke adjacent
    things (singleton caching vs ADR 0001's fresh-read reports-root guarantee,
    file-size cap, property tests) and delivered nothing a user feels - the
    textbook Planning-Principle-1b trap. Reverted. The one real nugget (the two
    config systems default to different providers - openai vs xai) is a one-line
    reconciliation if ever wanted, not a 53-site migration. Do NOT reopen this as
    a migration.
  - [x] Q1.2 Resolve duplicate `cost` vs `costs` commands (2026-06-14): `cost`
    is now a hidden, deprecated alias that emits a warning naming the
    replacement on every use; the one command it had with no `costs` equivalent,
    `estimate`, was ported to `costs estimate` (and a latent dead import was
    fixed - the old `cost estimate` imported a nonexistent
    `deepr.services.cost_estimation` and silently aborted). Kept functional for
    >= 2 releases per the deprecation policy. Regression-tested (warning emitted,
    `costs estimate` canonical, `cost` hidden from `--help`).
  - [x] Q1.3 Single shared `run_async` helper (2026-06-14): the canonical
    `run_async_command` now lives in `deepr/utils/async_runner.py` (a low layer
    both interfaces can import without crossing each other); `deepr/cli/async_runner.py`
    re-exports it for back-compat, and `web/app.py` + `api/app.py` dropped their
    private `def run_async` (the api copy's hand-rolled new-loop variant included)
    in favor of `import ... as run_async`. One implementation, ~70 call sites
    unchanged. (The test-only helper in `test_api/test_endpoints.py` is harness
    scaffolding, left as-is.)
- [ ] **Q2 - Coverage honesty:** characterization tests for the largest coverage-omitted files (`web/app.py`, `experts.py`), then shrink the omit list so the headline number covers the hard parts
- [ ] **Q3 - Decompose the giant files (after Q2 characterization):** `web/app.py` -> Flask blueprints + app factory; `cli/.../experts.py` -> per-area modules; extract cohesive units from `chat.py` and `mcp/server.py` (mcp stays strict-clean)
- [ ] **Q4 - Pay down the backlog:** refactor worst C901 offenders and ratchet the cap to 10 blocking; resolve/justify the `S` findings and flip `S` blocking; add a function-length signal (Google's ~40-line split heuristic) alongside the file-size guard; set a mutation-score target on kernel modules (mutmut is wired) since coverage % is a floor, not proof tests catch faults
- [ ] **Q5 - Staleness defense:** scheduled CI drift checks (dependencies + model registry) and a quarterly standards-review reminder

### Phase 1: Agentic Infrastructure Core

Goal: make the agentic layer production-ready - subagent contracts, role-based handoffs, provider resilience.

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

**The autopilot era validates the interop bet (June 2026 landscape).** Every major platform now ships always-on, long-running autonomous agents: Microsoft "Autopilots" (Scout on the Windows Agent Runtime, Work IQ API, Copilot Frontier), OpenAI AgentKit consolidating onto the Agents SDK + Workspace Agents (Connector Registry takes third-party MCP servers), Google Antigravity 2.0 (desktop/CLI/SDK + Managed Agents in the Gemini API + scheduled tasks), Amazon Bedrock AgentCore (managed harness, Memory, Observability, and *Payments* - agents autonomously paying for MCP servers and other agents), and Anthropic Managed Agents (MCP connectors, scheduled deployments). Deepr's position is unchanged and strengthened: it is the *knowledge role* these autopilots delegate to, never a competing orchestrator. Their persistence is shallow (session/long-term memory stores); a Deepr expert is calibrated epistemic state - which is exactly what an always-on agent checking in periodically needs (`what_changed` deltas, contested claims, gap backlogs). Three consequences for sequencing:

- **Remote MCP becomes strategic, not backlog**: cloud-hosted autopilots cannot call a stdio server on a laptop. A hosted, authenticated Deepr MCP endpoint (Streamable HTTP/SSE) is the price of admission to every platform above - promote from backlog when Phase 4c/5 work allows.
- **Hosts own the schedule, Deepr owns the verbs**: platform-native scheduling (Anthropic scheduled deployments, Antigravity scheduled tasks, Scout's always-on loop) can drive `deepr_expert_sync`/`health-check` instead of Deepr-side cron - consistent with the non-goal of owning the workflow.
- **Handoff schemas and budget contracts gain a consumer**: AgentCore Payments previews agents paying per tool call; Deepr's budget contracts and versioned handoff schemas (Phase 5) map directly onto that - an autopilot paying per consult needs exactly the machine-validated artifacts and cost bounds Deepr already produces.

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

Goal: give experts access to specialized research instruments from sibling projects - grounding facts, source ingestion, and strategic synthesis.

See [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) for the full integration contract and implementation details.

Builds directly on Phase 2 MCP client profiles, budget propagation, and trace ID stitching. Shipped in effort-to-value order (Recon, then Distillr, then Primr). **All three first-party instruments are now integrated** - Phase 2b is complete; remaining sub-items are follow-ons that depend on the sibling tools shipping new verbs (e.g. distillr `ask`/`audit`) or on Phase 4 (`expert sync`).

- [x] (1) Recon integration (`pip install recon-tool`) - **delivered in v2.11.0**:
  - [x] MCP client connection to recon's `lookup_tenant`, `analyze_posture`, `assess_exposure`, `find_hardening_gaps`, `chain_lookup` tools (auto-discovered when the `recon` binary is on PATH)
  - [x] Expert skill with auto-trigger on company domain mentions - autonomous cost-$0 probe in expert chat, findings absorbed into the system prompt for the turn via `KnowledgeAbsorber.categorize_recon_response`
  - [x] Trace ID pass-through for cross-tool observability (recon probes recorded in `reasoning_trace` with timestamp, domain, findings_count, cost)
- [x] (2) Distillr integration (`pip install distillr`) - **delivered in v2.12**:
  - [x] MCP client connection to distillr's ingest and query tools (built-in `distillr` skill + auto-discovered profile when `distill-mcp` is on PATH)
  - [x] Corpus import bridge: distillr output (MD + YAML) → expert permanent knowledge (`KnowledgeAbsorber.categorize_distillr_response`, absorbed as academic findings with synthesis-path provenance)
  - [x] Async handling with progress notifications for long ingestion runs (profile `progress: true`, reusing the existing MCP client `ProgressNotifier`)
  - [x] Budget propagation (cap model spend per ingestion) - per-call `budget_limit` cap enforced by `BudgetPropagator`; only free read-side corpus tools auto-approve, ingestion is approval-gated (tool names re-verified against distillr v0.11.1, 2026-06-11)
  - [x] Freshness engine: consume distillr's refresh/delta tool to re-run a subscribed topic and integrate only new material - this is what powers expert "stay current" (see Phase 4 expert sync)
  - [ ] Topic subscriptions: experts register topics with distillr; scheduled sync pulls deltas over time (lands with Phase 4 `expert sync`)
  - [ ] Consume distillr's corpus-layer verbs as they ship (`ask`, `audit`, gap-driven discover) instead of reimplementing them; Deepr's job is verification, belief integration, and orchestration on top of distillr's corpus primitives
- [x] (3) Primr integration (`pip install primr`) - **delivered in v2.12**:
  - [x] MCP client connection to primr's analyze_company and batch tools (built-in `primr` skill + auto-discovered profile when `primr-mcp` is on PATH; `research_company`, `generate_strategy`; surface re-verified against primr v1.29.3, 2026-06-11 - the v2.12-era `batch_analyze`/`quick_lookup` were removed upstream)
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
  - [x] First-party tool-surface drift check (`scripts/validate_integrations.py`, 2026-06-11): live `tools/list` handshake against installed recon/distillr/primr through Deepr's own MCP client, diffed against the profile approval lists. Built after all three integrations were found silently drifted (primr removed `batch_analyze`/`quick_lookup`; distillr renamed its entire verb surface; recon added five tools). $0; run after upgrading any sibling tool. The live check immediately corrected two errors in the static fix itself - this class of break is only catchable live.
- [x] Routing preview: `deepr research --preview` shows model choice, estimated cost band, and (in `--auto` mode) routing confidence and reasoning before executing. Works for both explicit `--model/--provider` runs and `--auto` mode. JSON output (`--json`) emits a structured `{preview, executed, provider, model, cost_estimate}` payload for machine consumers. Back-compat: `--dry-run` is preserved as an alias.
- [~] Eval methodology v2 (design: [docs/design/calibration-and-trust.md](docs/design/calibration-and-trust.md)):
  - [x] Saturation-aware rankings (2026-06-11): tasks where the question set has no headroom (top-2 tie or top score >= 0.99) are flagged and their best_quality pick uses discriminative quality above a competence floor - plain max() had elected gpt-4.1-nano "best at reasoning" off a mean 1.00 over 896 evals, which auto mode then obeyed. `--regenerate-rankings` rebuilds routing prefs from stored data at $0; 10 of 14 task types were saturated. The harder question set (fixing saturation at the source) remains the v2 core below.
  - [ ] Citation quality, grounding, synthesis depth, temporal accuracy
  - [ ] Expert-specific metrics: gap-detection success rate, belief-revision accuracy, citation freshness score, integration quality
  - [x] Continuity-property metrics, measured from stored expert state at $0 (2026-06-13): `deepr/experts/continuity_metrics.py` + `deepr eval continuity NAME` (`--json`) score staleness honesty, abstention correctness, contradiction surfacing, and what-changed exactness - each against ground truth derived *independently* of the surface it scores (time-based vs confidence-based; recorded edges vs the contested reader; the raw event log vs the what_changed buckets), so a high score means the surfaces agree with reality, not themselves. Methodology-versioned for run comparability; not-applicable metrics are excluded from the overall rather than scored zero. The ATANT audit shows popular memory benchmarks test at most 2 of 7 continuity properties - this measures Deepr's own surface instead of chasing LoCoMo-style scores (see [docs/design/belief-lifecycle.md](docs/design/belief-lifecycle.md))
  - [ ] Task-level cost-efficiency scoring
  - [ ] Methodology versioning for run comparability
- [ ] A/B shadow mode (opt-in): run shadow query in parallel against baseline for continuous routing comparison

### Phase 4: Expert Intelligence and Quality Loop

Goal: make experts genuinely agentic - self-correcting, strategically autonomous, graph-structured memory.

**Status.** The first two knowledge-loop increments shipped in **v2.12**:
`deepr expert health-check` (read-side, cost-$0 audit) and `deepr expert absorb`
(verification-gated output-to-knowledge loop) - both as CLI commands and MCP
tools, reusing the same free contradiction heuristic. **Next up:**

1. **Per-expert SKILL.md export** (Phase 4 skills, below) - the distribution play; the generic packager exists, the expert-scoped export does not.
2. **Dynamic tool selection via gap analysis** (below) - map infrastructure gaps -> recon, academic gaps -> distillr, strategic gaps -> primr. All three target instruments now exist, so the gap-to-tool engine has somewhere to route.

Reflection loop and graph memory are the larger, higher-risk items and come after.

**2026-06-18 loop/OKF research update.** The useful part of the current loop
engineering push is narrower than the hype: long-running agents work when the
harness makes context, reviewer checks, handoff artifacts, stop conditions, tool
execution, and acceptance metrics explicit. OKF v0.1 adds a portable
Markdown/YAML knowledge-bundle shape that other agents can read directly. Deepr
should absorb the pattern, not become a generic orchestrator: experts run
verified knowledge loops, expose machine-readable loop state, and export/import
portable knowledge without letting generated Markdown become authority over the
belief store. Detailed loop contract: [docs/design/verified-expert-loops.md](docs/design/verified-expert-loops.md).

- [ ] Verified expert-loop substrate:
  - [ ] Add a loop admission contract: no surface graduates from advisory to
        autonomous until the task repeats, the verifier is automated, the
        budget/capacity envelope is explicit, and the loop can inspect the
        tools, logs, and state needed to diagnose failures.
  - [ ] Define an `ExpertLoopRun` record for sync, gap-fill, reflection
        follow-ups, health-check actions, and future campaigns: goal, expert,
        triggering surface, budget/capacity source, verifier result, stop
        reason, trace id, resumable queue/job ids, acceptance rate, accepted vs
        rejected knowledge changes, and cost per accepted knowledge change.
  - [ ] Add `deepr expert loop-status NAME` (plus MCP read tool) showing last
        run, due subscriptions, open gaps, stale/contested beliefs, verifier
        failures, next action, and whether the next run can use local/plan
        capacity or requires metered budget.
  - [ ] Make loop completion evidence-based: a run is complete only when its
        verifier passes, no due work remains under the current budget/capacity
        contract, or a stop condition is recorded. Never trust a model's
        self-declared "done" as the terminal state.
  - [ ] Persist compact handoff artifacts between loop iterations so long runs
        survive context resets and process restarts without re-reading every
        report or source.

- [~] Reflection loop (self-correction before delivery):
  - [x] Post-research quality evaluation (v2.13): `ReflectionEngine` scores grounding, completeness, calibration, directness; CLI `deepr expert reflect` + `deepr_reflect` MCP tool. The model scores per dimension; the verdict (accept/revise/re_research) is computed deterministically from thresholds.
  - [x] Reflection metadata in output (per-dimension scores + issues + overall + follow-up queries)
  - [x] Configurable reflection depth (0 = skip, 1 = single pass, 2+ = rigorous)
  - [x] Automatic re-research on the gaps reflection identifies (2026-06-11): `deepr expert reflect NAME REPORT --execute-followups [--budget X]` runs the emitted follow-up queries through the gap-fill engine (same budget discipline: run ceiling, skip-not-fail, verification-gated absorb with contradiction flagging) - reflection stops being advisory exactly when the report needs reinforcement. Opt-in flag + confirmation; never runs as a side effect of plain reflect.
- [ ] Graph-structured expert memory (design: [docs/design/temporal-knowledge-graph.md](docs/design/temporal-knowledge-graph.md)) (the temporal knowledge graph - what makes an expert a *perspective*, not a corpus):
  - Framing: a corpus is what was read; a perspective is what is *believed* - claims with calibrated confidence, provenance, recency, known gaps, and open conflicts. RAG gives a host agent retrieval over content; a Deepr expert gives it an epistemic state it can interrogate. The temporal dimension is what elevates the graph beyond content: beliefs have trajectories (strengthening, decaying, contested, revised), and the graph remembers *when* and *why* each shift happened. That unlocks queries no document store can answer: "why do you believe X" (inference chain), "what changed since I last consulted you" (perspective delta), "what is currently contested" (open contradiction pairs with both sides' evidence), "what would change your mind" (the support/contradict structure around a belief), and "what do you know you don't know" (the gap backlog as negative knowledge - an expert that says "I have nothing on Y" is refusing hallucinated authority).
  - [x] Knowledge graph with typed edges (supports, contradicts, enables, derived_from) - shipped v2.14 (canonical-key dedup, provenance accumulation, symmetric contradicts, idempotent migration of legacy `contradictions_with`). Typed *nodes* stay deliberately implicit (`source_type` already distinguishes fact/signal/inference) until a concrete query needs more.
  - [x] Temporal awareness: confidence trajectories (belief event log, v2.14), staleness detection (health-check), refresh triggers (sync cadence)
  - [x] Inference chains: `deepr expert why` / `deepr_explain_belief` (v2.14) - depth-bounded, cycle-safe walk to evidence roots with confidence trajectory
  - [x] Contradiction detection: new evidence that conflicts with existing beliefs surfaces automatically (contradiction-as-signal absorb path + contested view + health-check merge; conflicts become belief-revision candidates with contradiction edges, not silent drops)
  - [ ] Temporal-graph query surface for host agents (MCP tools, so Claude Code / Copilot / Cursor consult the *perspective*, not just the content):
    - [x] `deepr_what_changed` (v2.13.x) - perspective delta since a timestamp (beliefs added / revised / contested / archived, each with reason + current snapshot); lets a host agent cheaply re-sync with an expert it consulted before instead of re-reading everything. Shipped early as planned - a query layer over `BeliefStore.changes` (honest caveat: the store keeps the last 100 change records; truncation is reported). CLI `deepr expert what-changed NAME --since 7d` + MCP tool.
    - [x] `deepr_contested` (v2.13.x) - open contradiction pairs with both sides' claims, confidence, and provenance (open vs dangling status). Read-side view over `contradictions_with` edges + absorb-time contested records. CLI `deepr expert contested NAME` + MCP tool.
    - [ ] `deepr_explain_belief` - inference chain + provenance + confidence trajectory for one belief. Provenance and history exist today (evidence_refs, belief history); full inference *chains* (trace through supporting beliefs) need the typed-edge graph above, so this one lands with it.
    - Sequencing note: the first two are the autopilot-facing wedge (re-sync + open-conflicts) and should land in v2.14 ahead of the full graph; they also keep the graph work honest by fixing the query contracts first.
    - Rationale: host agents have ephemeral context and monthly-plan economics; the expert is the durable, shared epistemic state across their sessions *and across different agents* - Claude Code and Copilot consulting the same expert get the same calibrated perspective, which is what makes experts organizational knowledge rather than per-tool caches.
- [~] Regenerated expert digest (a browsable view over the structured store, never the source of truth):
  - [x] On-demand "compilation" pass (`deepr expert digest`, v2.14): reads beliefs + typed edges + contradictions and emits a browsable Markdown digest - $0, no LLM, byte-stable for an unchanged store, derived-view marker enforced before overwrite (the Phase E regeneration invariant made executable)
  - [x] Surface the contradiction flags from the contradiction-as-signal path so a reader sees open conflicts rather than a smoothed narrative
  - [ ] Reuse the `expert sync` cadence + scheduled `health-check`; expose as an expert view in the web dashboard
  - Rationale: the structured-store-plus-regenerated-view hybrid gives precise queries and multi-agent read/write on the canonical store with browsable pre-synthesis on top, without the synthesis drift of a hand-maintained wiki. The architectural choice is explicit: synthesis happens at query/compile time over a structured source of truth, not destructively at ingest.
- [~] Knowledge maintenance loop (the expert keeps its own house in order, building on the staleness + contradiction detection above):
  - [x] `deepr expert health-check NAME` (v2.12) - read-side audit in one pass: belief contradictions (free heuristic), claims missing source provenance, beliefs past their confidence/refresh threshold, the open-gap backlog, and documents ingested but not synthesized. CLI + `deepr_expert_health_check` MCP tool. Deferred: orphaned/broken-link citation checks and suggested new topics + cross-links.
  - [x] Two-phase output: findings, then an action menu where each item carries its command, estimated cost, and the approval tier (AUTO_APPROVE/NOTIFY/CONFIRM) that would gate it; corrective research stays opt-in (the audit proposes, it never runs an action)
  - [x] Cost-$0 by default (audit only); schedulable so experts self-maintain on a cadence (the scheduled monthly health check, not just scheduled refresh)
  - [ ] For corpus-backed experts, delegate the underlying audit to distillr's `audit` rather than reimplementing link/contradiction/coverage scans; Deepr adds belief-state mapping, confidence, and the action menu on top
- [~] Belief lifecycle and salience (design: [docs/design/belief-lifecycle.md](docs/design/belief-lifecycle.md)) - memory governance, grounded in the 2026-06 memory-systems corpus review (monotonic accumulation is the literature's documented root failure mode; outcome-driven forgetting converges to true usefulness; contested beliefs are irreducible signal):
  - [x] Bi-temporal valid time (2026-06-12): belief events carry optional world-valid `invalidated_at` distinct from record time, while the event schema is young (Graphiti pattern, adopted in the TKG design)
  - [x] Lossless archival (2026-06-12): archival events carry a full belief snapshot; `restore_belief` rebuilds from the log - reversibility executable, not aspirational
  - [x] Usage salience substrate (2026-06-12): per-belief retrieval counters, recordable only from already-mutating paths (read-side queries stay pure/$0; MCP READ_ONLY depends on that - regression-tested); usage only ever *protects* a belief from archival, never condemns one. First production producer lands with the chat worldview-to-BeliefStore bridge; absorb-merge already protects via `updated_at` movement.
  - [x] Consolidation pass (2026-06-12): health-check surfaces archive candidates (decayed below floor AND long-unevidenced AND unused AND not contested - the Rashomon rule: contested beliefs are never garbage-collected) with an `--archive-stale` action flag; dry-run default, event-logged with snapshot + thresholds; $0
  - [x] Entailment-shaped contradiction screen on the absorb gate (2026-06-14):
    the lexical word-overlap heuristic stays a high-recall router; a cheap model
    entailment verdict now concludes (`ReportAbsorber._verify_contradiction`,
    `verify_contradictions=True` default). A refuted pair (phrasing-level false
    positive) is absorbed normally instead of minting a false contested belief; a
    confirmed pair is flagged `verification="model_confirmed"`; any failure stays
    conservative (`lexical_unverified`, never drops a real contradiction). Reuses
    the extraction client, preserves the existing-belief-never-overwritten safety
    property. This is the brittle lexical-verdict fix the STOP banner demands.
    Remaining: extend the same router->verdict pass to the health-check detection
    surface; calibrate the verdict via the evidence layer.
  - [x] Dedup-merge verdict on the absorb gate (2026-06-14): the sibling brittle
    verdict. `_find_similar`'s >0.7 word-overlap decided merges, so two different
    facts that share words (e.g. "$10/M" vs "$30/M") silently merged into one,
    losing data. Now the overlap routes; in the uncertain band (<= 0.92) a cheap
    model verdict decides SAME vs DIFFERENT fact, and `add_belief(dedup=False)`
    adds distinct claims separately. Cost-bounded, every existing caller
    unchanged. Covers chat + sync (they ingest through `ReportAbsorber.absorb`).
    Only remaining lexical dedup is the low-stakes shared belief store
    (`_find_similar_in_domain`, a no-client cross-expert copy).
  - Atomic claim decomposition at absorb: extraction prompt already enforces
    one-assertion claims (the model does the decomposition - correct). The
    "deterministic atomicity-rate check" that was here is **CUT** - it is the
    brittle-rule-for-meaning anti-pattern (atomicity is meaning; a regex/word
    monitor was tried and removed 2026-06-14). If a cheap atomicity signal is
    ever wanted it must be model-derived or live in the calibration harness, never
    a standalone lexical pass (see AGENTIC_BALANCE.md and the STOP banner).
  - [ ] Outcome attribution (later): the second When-to-Forget counter (did the answer that used this belief succeed?) waits on an outcome signal - reflection verdicts or host-agent feedback as task-success proxy
- [~] Output-to-knowledge feedback loop (the compounding flywheel: every verified output can strengthen the expert):
  - [x] `deepr expert absorb REPORT_ID` (v2.12) - promote a completed report into permanent beliefs with report provenance, instead of treating reports as terminal artifacts. CLI (`--dry-run` preview) + `deepr_expert_absorb` MCP tool. Deferred: the post-research "integrate this?" inline prompt.
  - [x] Verification-gated by design: extraction yields report-grounded candidate claims (each self-rated for report support), weak claims are dropped, and any claim contradicting an existing belief is held back by the same free heuristic health-check uses - so "the model writes something slightly wrong, you save it, the next answer builds on the mistake" cannot happen silently
  - [x] Dedup against existing beliefs and integrate the delta only (reuses `BeliefStore.add_belief`); consuming distillr's corpus-side `ask` verb with verification is the remaining follow-on
  - [~] Contradiction-as-signal (not just rejection): the absorb contradiction gate previously dropped a conflicting candidate outright, which kept a bad claim out but also smoothed away the contradiction, the one thing most worth surfacing. Input-time synthesis (absorb -> beliefs) is the "Wiki" pattern whose known failure mode is turning old syntheses into confident-but-stale claims; keeping contradictions as queryable signals is the structured-store property Deepr's graph memory is meant to provide. **Shipped (v2.13.x)** as the default absorb behavior:
    - [x] Conflicts emit a distinct `FlaggedContradiction` outcome (candidate + the belief it conflicts with + which side is better-sourced; candidate is always newer) in the absorb result, CLI rendering, and MCP payload; never silently discarded (`flag_contradictions=False` restores the legacy drop)
    - [x] Optional `adjudicate=True` routes the pair through the existing `ConflictResolver.resolve` adjudication (a_wins / b_wins / merged / needs_human_review); the verdict is recorded on the flag, advisory only - actual revision stays with `expert resolve-conflicts` and approval
    - [x] Safety property preserved and regression-tested: the new `BeliefStore.add_contested_belief` records the candidate with contradiction edges both ways while bypassing similarity-merge/conflict-resolution strategies, so the existing belief is guaranteed untouched (plain `add_belief` would have rewritten it - negated claims are >0.7 word-similar)
    - [x] Surface flagged contradictions in the health-check action menu (2026-06-11): the audit now merges recorded contested pairs (absorb/sync-time contradiction edges, read from the belief store without creating state) with freshly heuristic-detected ones, deduplicated by id pair; the summary and the adjudicate action distinguish "N recorded, M new". Live-verified: the 4 flags from the first live absorb appear in the audit.
- [ ] Gap-driven discovery (audit proposes what is missing, not just what the user asked for):
  - [ ] Wire health-check coverage findings into auto-generated discovery queries: "you have 12 sources on X but zero on Y - preview candidates?" This is corpus-gap-driven, complementing the existing goal-driven discovery
  - [ ] Surface as previewable candidates with cost estimate; ingestion stays opt-in and budget-bounded
- [~] Output style for human-read artifacts (briefings, reports):
  - **CUT (2026-06-14): the "register/anti-slop style guard" - a banned-filler /
    em-dash-counting / spelling-rule lint - is exactly the brittle-rule-for-meaning
    anti-pattern (writing quality is *meaning*; see the STOP banner and
    AGENTIC_BALANCE.md). A rule list will mangle good prose and miss bad.**
  - [ ] If output register needs improving, do it in the generation prompt (the
    model writes to a stated register) and judge it with the calibrated reflection
    pass - not a post-hoc lint. The house style (no em-dashes/emojis, direct tone)
    already lives in AGENTS.md for *commits/docs the agent writes*, which is form,
    not a quality verdict on model-generated prose.
- [~] Expert freshness / watch (stay current on a topic over time):
  - [x] `deepr expert sync NAME` (v2.13.x) - researches each due subscription with a delta-only freshness prompt ("what changed since <last sync>; if nothing, say so"), absorbs through the verification-gated pipeline (dedup + contradiction flagging), and surfaces the perspective delta via `what_changed`. `subscribe`/`subscriptions` manage topics; `--dry-run` previews at $0; a "no significant changes" answer skips the paid extraction entirely.
  - [x] Per-topic refresh cadence and budget (`--every Nd --budget X`), run-level budget ceiling with skip-not-fail exhaustion, refuse-below-floor preflight; engine takes an injectable research function (unit-tested free)
  - [x] Schedulable: idempotent per cadence window, so cron / host-platform schedulers (Anthropic scheduled deployments, Antigravity tasks) can run it daily and only due topics spend money; change summary printed per run
  - [ ] First-party instrument deltas as sync sources (distillr refresh, recon delta, primr delta) - the generic research-based sync ships first; instrument-specific delta verbs land when the siblings expose them (Phase 2b follow-on)
- [ ] Dynamic tool selection via gap analysis:
  - [x] Gap-to-tool mapping engine (v2.13): `GapRouter` maps each gap to recon/distillr/primr/research by keyword signal, with installed-instrument detection and fallback. CLI `deepr expert route-gaps` + `deepr_route_gaps` MCP tool. Read-only advisory.
  - [ ] **Brittle-heuristic debt (flagged 2026-06-14):** "by keyword signal" is a
    lexical rule deciding *meaning* (which instrument fits a gap). It is tolerable
    only while read-only advisory; it must NOT be the verdict on the `--execute`
    path. Keep keywords as a high-recall prefilter and let the model pick the
    route (or confirm it) before any spend. Do not extend the keyword map - that
    is the trap (see AGENTIC_BALANCE.md).
  - [x] Value/cost estimation per gap-fill option (per-route cost estimate + ev_cost_ratio ordering)
  - [x] Strategic prioritization that actually *executes* (2026-06-11): `deepr expert route-gaps --execute [--budget X] [--dry-run]` runs the highest-value research-route fills (ev_cost_ratio ordering), absorbs findings through the verification-gated pipeline, per-gap budgets inside a run ceiling with skip-not-fail. Bounded autonomy by design: specialist-instrument routes (recon/distillr/primr) are DEFERRED with their command printed - approval-gated multi-minute paid jobs never start as a side effect of a sweep.
- [x] Expert-as-guardrail mode:
  - [x] `validate` tool alongside `research` and `chat` - `deepr expert validate NAME CLAIM` (also `--from-file -` for stdin) and `deepr_expert_validate` MCP tool. Expert applies its existing knowledge as a filter/validator; pure read-side, never mutates the expert.
  - [x] PASS/WARN/FAIL assessment with citations and confidence - claim IDs returned by the validator model are resolved back to canonical `Claim` objects so callers get full citation provenance, not just statements.
  - [x] Useful for downstream agents that need domain validation before acting - structured JSON output (verdict, confidence, reasoning, supporting/contradicting claims, caveats) makes the verdict machine-actionable.
- [ ] Expert manifest diff (`Delta`) and explicit `ExpertPolicy` type
- [ ] Optional `--high-trust-only` mode (primary/secondary sources only)
- [ ] Structured corpus import as first-class skill:
  - [ ] One-command ingest of MD/JSON/JSONL bundles as permanent expert knowledge
  - [ ] Auto-gap detection and citation mapping on imported corpora
  - [ ] Works with any structured output (research reports, synthesis docs, company briefs)
  - [x] OKF bundle import (`deepr expert absorb-okf NAME PATH`): parse
        conformant Markdown/YAML concept documents, preserve frontmatter and
        cross-links as provenance, and route claims through the existing
        verification-gated absorb pipeline rather than trusting the bundle text.
- [x] Per-expert SKILL.md export (v2.13): `deepr expert export-skill NAME` builds `deepr/skills/expert_skill.build_expert_skill` on top of the generic `SkillPackager` - an expert-scoped SKILL.md whose triggers/instructions/tools are populated from one expert and whose body calls that expert via Deepr's MCP tools. The validated interoperability direction: Deepr is the MCP server / SKILL.md that hosts (Claude Cowork, Copilot agent mode, Cursor, Goose, OpenClaw) *call*, not Deepr delegating execution outward. agentskills.io SKILL.md is broadly adopted, so one export reaches every major host.
- [x] OKF expert export (`deepr expert export-okf NAME PATH`):
  - [x] Generate a conformant OKF bundle from the structured belief store:
        one concept file per current belief, YAML frontmatter with
        `type`, `title`, `description`, `tags`, `timestamp`, and Deepr-specific
        confidence/trust extensions, plus `index.md` and `log.md`.
  - [x] Encode citations, support/contradict edges, gaps, and `what_changed`
        history as Markdown sections and bundle-relative links. The export is a
        derived view with the same regeneration marker discipline as expert
        digests.
  - [x] Optionally emit `llms.txt` discovery instructions pointing hosts to the
        exported OKF bundle and to the Deepr MCP tools for live queries.
- [ ] Skill auto-generation from research artifacts:
  - [ ] `expert skill make "Topic" --from-report artifact.md` generates skill with tools and triggers
  - [ ] Dependency tracking between generated skills
  - [ ] Efficacy scoring (citations added, gaps closed, cost impact)
  - [ ] Trace-based skill self-improvement: improve generated skills/prompts from real execution traces, gated behind tests + size limits + human-review/PR. Reference approach: GEPA (genetic-Pareto reflective prompt evolution) + DSPy over traces - zero-GPU, API-only, validated (ICLR 2026); composes with the reflection + absorb loop above (the trace is the artifact those loops already produce).
- [ ] Skill templates + versioning/dependency management
- [ ] Skill format conversion (Claude Skills ↔ OpenClaw Skills ↔ agentskills.io)
- [ ] Keep skill design constrained (focused modules, measurable outcomes)

### Phase 4c: Expert Crews (composable, exportable expert teams)

Goal: let a *named, persistent* set of experts be consulted and shipped as one
composable role - the team-level analogue of a single expert. This is
composition of parts that already exist (`council.py` for bounded multi-expert
consultation, `dspy_pipeline.py` for trace-based optimization, the per-expert
SKILL.md export, `report_absorber`/`metacognition` for the learning loop), not
new infrastructure. Sequenced so the static, auditable core lands first and the
self-improvement lands last, gated.

Naming: do **not** reuse `deepr team` - that already means ephemeral,
multi-persona research teams for a single question (`team analyze`). Use a
distinct surface (`deepr crew ...`, or an `expert crew` sub-namespace).

Design constraint (preserves the non-goal): a crew is itself **one composable
role** that exposes a single handoff surface; internally it is a *bounded
council*, not Deepr orchestrating other vendors' agents. Deepr still does not
own the outer workflow.

- [ ] Crew manifest + persistence: a named crew = a set of expert names + a lead/synthesizer role + a delegation note, stored alongside profiles. Reuses `council.py` for execution.
- [ ] `crew run "<question>"` - bounded council consultation across the crew's experts with budget contract, approvals, and trace IDs (no unbounded fan-out).
- [ ] `crew export` -> TEAM.md (a SKILL.md superset: `roles[]`, delegation note, the existing per-expert tool surface) so a crew installs into an agentskills.io host as one skill. Reuses `skills/packager` + the per-expert exporter.
- [ ] (later, experimental, gated) Trace-fed self-improvement: feed crew-run traces into the existing `dspy_pipeline` + absorb/reflection loop to propose a manifest delta (role add/drop, delegation tweak); every proposal passes `expert validate` + human approval before it is applied. No silent reconfiguration.
- [ ] (optional interop) Export to LangGraph / CrewAI configs; NemoClaw-sandbox-friendly run mode. Nice-to-haves, not core.

### Phase 4b: Autonomous Research Campaigns

Goal: experts that run extended research investigations autonomously within
budget, evidence, and checkpoint bounds. Campaigns are not the first loop
surface; they build on `ExpertLoopRun`, loop-status, capacity routing, and
portable handoff artifacts after those are reliable on sync/gap-fill/reflection.

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

- [~] Structured handoff contracts:
  - [x] Versioned JSON schemas for expert output (claims, confidence, citations, gaps, staleness)
        published as `deepr-expert-handoff-v1`.
  - [x] Versioned loop-status schema (`ExpertLoopRun`, next action, stop reason,
        verifier result, budget/capacity source) so host agents can decide
        whether to consult, wait, retry, or escalate without scraping prose.
        Published as `deepr-loop-status-v1`.
  - [x] Downstream agents can validate handoff artifacts against published schemas
        in `docs/schemas/`.
  - [x] OKF profile: documented mapping from Deepr beliefs/events/edges/gaps to
        OKF concept documents, including which fields are Deepr extensions and
        which parts are derived views. Published as `deepr-okf-profile-v1`.
  - [x] Schema registry with backward compatibility guarantees
        (`docs/schemas/registry.json` and `docs/schemas/README.md`).
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
- [ ] Hosted MCP endpoint (design: [docs/design/hosted-mcp-endpoint.md](docs/design/hosted-mcp-endpoint.md)) (the autopilot on-ramp - promoted from backlog, see Phase 2 landscape note):
  - [x] Versioned read-only expert handoff contract:
        `deepr_expert_handoff` and `/api/experts/{name}/handoff` return
        `deepr-expert-handoff-v1` with bounded expert state, loop status, OKF
        hints, and additive compatibility.
  - [x] Scoped-key and remote-call audit primitive:
        `ScopedMCPKeyStore` authenticates per-key mode, expert allowlist, and
        budget metadata for HTTP MCP calls; the transport enforces mode,
        confirmation, and expert-scope denial before dispatch and writes
        append-only `deepr-mcp-remote-audit-v1` events.
  - [x] Scoped-key CLI:
        `deepr mcp keys create/list/revoke` mints secrets once, lists only
        public metadata, and revokes keys without exposing stored hashes.
  - [x] Per-key budget guard:
        scoped HTTP calls sum prior audited `cost_usd`, block calls whose
        requested budget or fixed estimate exceeds the key's remaining budget,
        inject remaining budget into budget-aware tools when omitted, and record
        successful response costs back to the remote audit log.
  - [x] Per-key rate limits:
        scoped HTTP calls count recent audited calls for the authenticated key,
        block over-limit calls before tool dispatch, return retry metadata, and
        audit the denial.
  - [x] Streamable HTTP/SSE serve path:
        `deepr mcp serve --http` runs the existing MCP server over HTTP/SSE,
        loopback by default, with shared-token fallback or scoped-key auth for
        reachable binds.
  - [x] Local/proxied remote smoke command:
        `deepr mcp smoke-http URL` performs `$0` health, initialize,
        tools/list, and free tool-search checks against a local or TLS-proxied
        HTTP MCP endpoint.
  - [~] Deploy recipe:
        [deploy/mcp-http.md](deploy/mcp-http.md) documents the loopback service
        plus Caddy/nginx TLS reverse-proxy shape. Remaining: container and
        cloud-template variants so a user can stand up "my experts, reachable
        by my cloud agents" in one command.
  - Rationale: cloud-hosted always-on agents (Autopilots, Workspace Agents, Managed Agents, AgentCore) cannot reach a stdio server on a laptop; a reachable endpoint is the price of admission to every host platform, and it is transport + auth around tools that already exist.
- [ ] Team features (auth, workspaces, RBAC, audit log)
- [ ] Permission boundaries (`--allow-write`, tool allowlists, budget policy enforcement)
- [ ] Execution isolation (sandboxed parsing, resource limits, egress controls)
- [ ] Cryptographic verification and execution-proof audit trail (stretch)

#### AI/agentic security (scoped to Deepr's real surface)

Deepr is an orchestration layer over hosted model APIs - it does not train, fine-tune, or serve model weights - so its security work targets *ingested data* and *agentic tool use*, not the model internals. The threats that actually apply:

- [ ] **Indirect prompt-injection defense for ingested/tool content.** Web search results, scraped pages, uploaded docs, and first-party MCP tool output (recon/distillr/primr) are untrusted input that flows into prompts and into expert beliefs. Extend `utils/prompt_security.PromptSanitizer` to the ingestion + tool-result boundary (not just user prompts), delimit/quarantine untrusted spans, and gate belief absorption behind the existing verify/reflection step so a poisoned source cannot silently become a belief. This is Deepr's #1 AI-security risk.
- [ ] **Agentic trust boundaries.** Formalize the existing approval tiers (AUTO_APPROVE/NOTIFY/CONFIRM) + per-MCP-server tool allowlists, rate limits, and egress controls (overlaps Phase 2 elicitation sandboxing); capability-scope what each tool/expert may do, and never auto-approve a paid or write-capable tool.
- [ ] **Output/handoff validation.** Validate MCP/A2A outputs against the published handoff schemas (above) before downstream agents consume them - a compromised expert must not emit malformed/unsafe artifacts.
- [ ] **Agentic red-team suite.** Automated prompt-injection / jailbreak / tool-abuse tests against expert chat and the ingestion paths (the security-flavored sibling of the Phase E fault-injection tests); track attack-success-rate as a metric. Include memory-specific attacks from the 2026 literature: ADAM-style adaptive extraction probing through the MCP read tools, and trust-floor bypass attempts (can a crafted report mint a high-confidence belief?) - the floors are the poisoning backstop and need adversarial verification, not just unit tests.
- [ ] **Threat model doc** (MITRE ATLAS-style) for Deepr's actual surface - ingestion, agentic tools, MCP/web/A2A endpoints, secret handling - that records what is explicitly out of scope (see below) so effort stays proportional.
- [ ] Secret hygiene hardening: least-privilege provider keys, no secrets in logs/traces (redaction exists), and secret-scanning in CI.

**Explicit security non-goals** (Deepr does not own the model, so these belong to the providers, not us):

- Training/fine-tuning-time defenses (data poisoning, label-flip, DP-SGD, adversarial training, certified robustness) - Deepr trains nothing.
- Model-weight protection (extraction/inversion/membership-inference defenses, watermarking/fingerprinting, TEEs/enclaves, homomorphic encryption, confidential computing, post-quantum model crypto) - Deepr holds no weights; it calls hosted APIs.
- Inference-layer isolation (confidential VMs / GPU enclaves for serving) - inference runs on the providers' infrastructure under their shared-responsibility model.

### Phase 6: Plan-Quota and Local Backends (paid plans + owned hardware as bounded-cost research capacity)

Design: [docs/design/capacity-waterfall.md](docs/design/capacity-waterfall.md)

Goal: let Deepr execute research through capacity the user already pays for or owns - subscription agentic CLIs (Claude Code, Codex CLI, Antigravity CLI, Grok Build, GitHub Copilot CLI, Kiro CLI) and local GPUs (Ollama) - treating plans as *bounded prepaid pools* and local inference as truly free at the margin, with hard guarantees that no path can produce a surprise bill.

The routing principle (the **capacity waterfall**): for any job whose quality floor permits it, drain owned/prepaid capacity first - `local` -> `plan_quota`/`credit_pool` -> `api_metered` (budget-gated, last resort). You are paying for the plans anyway; the metered API is only ever reached explicitly, never by accident. A realistic stack (3x Google accounts + Kiro Power + Claude Max + ChatGPT Plus + Grok free API credits + one RTX-class GPU) represents hundreds of dollars of monthly prepaid capacity plus unlimited local tokens before the first metered dollar.

Why this matters: a $20-300/month plan with quota windows or monthly credit pools is often dramatically cheaper than metered API calls for batch research, and Deepr's queue is exactly the workload shape (non-urgent, schedulable) that can soak up quota that would otherwise expire unused. The cost story is the product: "your existing subscriptions become research capacity." The flagship use case is **background expert maintenance**: scheduled `expert sync`, `health-check`, and gap-fill jobs (Phase 4) are non-urgent by definition - route them to plan-quota/local backends by default and experts stay current at ~$0 marginal cost, draining quota that would otherwise expire.

Platform requirement: every adapter must work on Windows, macOS, and Linux (subprocess invocation, auth-profile discovery, and path handling are per-OS; the vendor CLIs themselves are cross-platform). No adapter ships supporting only the dev machine's OS.

Current truth in the product: local Ollama and API-backed research execute today.
Plan CLIs are visible or modeled through `deepr capacity`, but they are not Deepr
execution backends until adapters, live quota probes, and no-surprise-bills
guards ship. The QOL target is a clear route planner: tell the user whether a
job should run locally, wait for plan quota, or use a metered API with an
explicit budget ceiling.

Vendor reality (verified June 2026 - revalidate before implementation, this churns quarterly):

- **Claude Code**: headless `claude -p` / Agent SDK usage bills a *separate monthly credit pool* per plan tier ($20 Pro / $100 Max 5x / $200 Max 20x) as of June 15, 2026; automation stops when the pool empties unless overflow billing is enabled. Bounded and predictable - exactly the no-surprise-bills shape - but Deepr must verify overflow billing is OFF. Interactive sessions draw from 5-hour rolling windows instead.
- **Codex CLI**: usage limits share five-hour local/cloud task windows, extra credits or API-key mode can bill, and `/status` surfaces limits during active CLI sessions. Adapter must distinguish plan usage from API-key metered usage.
- **Google Antigravity CLI** (`agy`): Gemini CLI stops serving consumer/free requests on June 18, 2026; Antigravity CLI is the consumer replacement and supports asynchronous/background workflows. Enterprise/API-key Gemini CLI paths remain separate. Opaque compute units make the observed-quota tracker mandatory here.
- **Kiro CLI**: officially sanctioned for automation ("reviews during CI/CD"); credit plans from Free (50/mo) to Power ($200/mo, 10,000 credits). Caveat: **overage bills automatically at $0.04/credit at month-end** - the adapter must detect/require overage protection off, or cap usage below the credit ceiling, to honor no-surprise-bills.
- **Grok Build**: available in beta for SuperGrok and X Premium Plus subscribers. Treat it as a candidate plan-CLI surface, not shipped Deepr capacity. API-key Grok remains the existing metered provider path unless a bounded credit pool is explicitly configured and observed.
- **Local (Ollama)**: an RTX-class GPU runs open-weight models at genuinely $0 marginal cost - no quota window at all, just hardware availability. Two honest constraints: (1) quality - local models are not deep-research APIs, so local handles the quality-tolerant steps of the expert loop (absorption, summarization, contradiction heuristics, gap detection, draft synthesis) while quality-critical synthesis routes up the waterfall, with eval benchmarks deciding the floor per task type; (2) contention - the GPU is often shared with the user's interactive work (IDE agents, coding), so the adapter needs availability windows (e.g. off-hours) and an optional GPU-utilization probe before dispatch. For scheduled expert maintenance, neither constraint matters: the jobs are quality-tolerant and time-flexible by design.

Design (builds on existing kernel primitives - cost ledger, budget contracts, provider registry, auto-mode routing):

- [~] **Cost-source model**: `CostModel`/`BackendKind`, `backend_id` on detected sources, normalized `ResearchBackend` profiles, the append-only `quota_ledger.jsonl` substrate, backend eligibility decisions, and pure backend selection are in place. Remaining: provider-profile integration and adapter writes that connect real plan-quota executions to those records. Plan-quota and credit-pool backends report marginal cost $0 but consume quota/credit units.
- [~] **Quota window tracker**: per-account `QuotaWindow` (window type: rolling-5h / daily / weekly-compute / monthly-credit-pool; usage observed, never assumed; reset time). Durable observed events, `deepr capacity` summaries, and eligibility stops are in place. Remaining: adapter-side live probes and scheduler decisions that mark exhaustion (429 / vendor error signature) and reschedule instead of failing the job. Vendors do not expose remaining quota reliably - treat limits as observed from exhaustion signals.
- [ ] **Multi-account quota pools**: a user with several plans on one vendor (e.g. three Google accounts - personal + two work) registers one authenticated profile per account; each is an independent QuotaWindow and the scheduler drains across the pool before deferring. Only accounts the user owns/controls, each consuming strictly within its own plan limits - this is using paid seats fully, not circumventing a single account's cap. Per-account credential isolation (no shared auth state).
- [ ] **CLI provider adapters** (each implements the existing `DeepResearchProvider` contract; subprocess invocation in JSON/headless mode; no API keys touched):
  - [ ] `cli-copilot` (programmatic `copilot -p`, strong cross-platform docs and plan-policy surface)
  - [ ] `cli-antigravity` (`agy`; replaces the pre-June-18 consumer `gemini -p` plan)
  - [ ] `cli-claude` (structured output and tool control; must prove plan/credit mode and overflow-off state)
  - [ ] `cli-codex` (5-hour shared local/cloud task windows; must reject API-key metered mode unless explicitly configured as paid)
  - [ ] `cli-grok-build` (SuperGrok/X Premium Plus beta; must prove non-metered subscription execution before plan-quota classification)
  - [ ] `cli-kiro` (`kiro-cli`; monthly credits; requires overage guard)
  - [ ] Grok API credit pool: flag the existing Grok API provider as `credit_pool` when a bounded free-credit program is active and observable, with the monthly credit amount as the bound
- [ ] **Local backend** (`local-ollama`): a `DeepResearchProvider` over the Ollama HTTP API (works identically on Windows/macOS/Linux); `cost_source: local`, no quota window. Availability scheduling instead: configurable time windows (e.g. outside work hours) plus an optional GPU-utilization/VRAM probe before dispatch so background research never fights the user's interactive sessions.
- [x] **Local-first process validation** (early, cheap, before the full backend): `expert make --local` plus the Ollama-backed research function now plug into the engines' existing injectable seams (`expert sync`/`absorb --local`, with `sync --local --fresh-context` for free retrieval). Even where local output quality is below the research floor, the *flow* is fully real - create, subscribe, submit, extract, verify, absorb, contradict, archive - so the whole expert lifecycle can be exercised end-to-end at $0 on owned hardware during development. Paid models are for validating *quality*, not *plumbing*.
- [x] **Eval-gated local admission** (free does not outrank quality): a local model is *not routable* until the user has reviewed local benchmark evidence. `deepr eval local` compares Ollama models with either a local judge or an explicitly approved CLI judge on the agentic-loop prompt set, saved artifacts feed admission through `deepr capacity admit --from-eval latest`, and automatic runtime routing now feeds the admitted score into the measured quality-floor gate. Admission is per model+version - swapping the local model invalidates its eval and drops it from routing until re-benchmarked. Cheap local judges cost $0 at the margin; CLI judges may consume external quota and are opt-in only.
- [~] **Capacity waterfall in auto mode**: the pure selector now orders `local -> plan_quota/credit_pool -> api_metered`, applies eligibility, and enforces measured per-task quality floors; expert maintenance consumes admitted local scores at runtime. Remaining work is feeding it live benchmark scores, scheduler context, and adapter results. Metered is reached only when no free-at-margin source can meet the floor, and is still budget-checked as today.
- [ ] **Auth-mode detection**: adapters verify the CLI is authenticated via subscription login (OAuth profile), not an API key. An API-key-authenticated CLI is metered spend wearing a CLI costume - refuse to classify it as `plan_quota`, route it through the normal budget guards instead.
- [ ] **No-surprise-bills invariants** (kernel-enforced, tested):
  - [ ] A `plan_quota`/`credit_pool` backend never falls back to a metered API without an explicit `--allow-paid-fallback` (or config equivalent); default is queue-until-reset.
  - [ ] Overage/overflow detection per vendor: Claude overflow billing OFF, Kiro overage protection ON (or hard-stop below the credit ceiling) - checked before first use and on a cadence; a backend whose overage state cannot be verified is treated as metered.
  - [ ] Quota events land in the ledger as $0-cost entries with quota units, so `costs show` reflects reality and anomaly detection sees volume spikes even at $0.
- [ ] **Quota-aware scheduling**: the queue learns window math - defer non-urgent jobs to the next reset, drain batches into open windows (overnight = free capacity), interleave across multiple plan backends *and accounts* before touching any metered API. This is the "auto-schedule around it" piece.
- [ ] **Expert maintenance on plan quota** (the compounding payoff): scheduled `expert sync` / `health-check` / gap-fill runs (Phase 4) default to plan-quota backends when available, so a roster of experts stays current in the background on capacity the user already pays for; metered APIs remain reserved for interactive and high-priority work.
- [ ] **Auto-mode integration**: routing treats plan-quota backends as cost-0 candidates weighted by benchmarked quality (eval harness gains CLI-backend support); `--dry-run`/`--preview` show "plan quota (N units, resets HH:MM)" instead of dollars.
- [ ] **ToS guardrail**: ship only backends whose vendors officially document headless plan usage (all three above do today); revalidate at implementation time and per release.
- [~] **Capacity quality-of-life path**: make the cheapest safe path obvious without hiding gates. `deepr capacity next` now gives a ranked action list with the current block reason, local setup, latest usable eval-artifact admission, eval refresh, and explicit metered fallback. Remaining QOL work is dry-run previews that explain why each rung is blocked during a concrete job, plus guided scheduler suggestions for jobs that should wait for local or plan capacity instead of paying now.

Honest caveats (why this is experimental): CLI agents are not deep-research APIs - citation quality and output contracts differ and must be normalized through the existing reflection/verification loop; vendor quota mechanics churn quarterly (the tracker treats limits as *observed*, not configured); subprocess lifecycle on long jobs needs the same async-durability treatment as MCP clients (reuse that layer).

### Panel-Review Findings (2026-06-11, six-persona cold review)

A mock panel (business buyer, indie hacker, enterprise AI architect, research scientist, non-technical user, AI YouTuber) reviewed the repo cold. Convergent findings, ranked by how many seats hit them independently:

- [x] **Simple default surface** (5 of 6 hit this wall; shipped v2.13.x): `deepr --help` now opens with a worked three-command quickstart and lists five core commands (research, expert, costs, doctor, web) before an Advanced section; deprecated commands and single-letter aliases are hidden from the listing but still execute. `.env.example` reduced 179 -> 19 lines (one key + budget ceilings); the full template lives in `.env.example.full`. README gained the plain-language one-liner, the budget-is-a-ceiling note, and a who-this-is-for block.
- [ ] **Confidence calibration evidence** (the scientist's "who validates the validator"): extraction confidence is model self-assessment with no empirical calibration. Add a calibration harness to eval methodology v2 (Phase 3): human-annotated held-out reports -> precision/recall of extraction + calibration curve (does 0.7 confidence mean ~70% grounded?); publish the numbers. Until then the honest claim is "report-grounded candidates with confidence-as-signal", never "verified facts".
- [x] **Source-trust scoring with confidence floors** (architect + scientist independently; shipped 2026-06-11): `Belief.trust_class` (primary/secondary/tertiary, retroactive tertiary default for all pre-floor beliefs) with deterministic read-time ceilings - tertiary single-source caps at 0.60, two independent tertiary sources at 0.80, secondary+ uncapped. Computed at read time like decay, so the cap holds through every write path (absorb, sync, merge, adjudication - regression-tested) and no model judgment can lift it; only new better-sourced evidence raises the ceiling. Absorb marks research-derived beliefs tertiary: the deterministic ingestion-time prompt-injection backstop (a 0.98-extraction-confidence poisoned claim reads <= 0.60 - tested). Follow-on: plumb operator-supplied documents through as primary in expert make/learner.
- [ ] **Expert mutation audit log** (architect): absorb/resolve-conflicts/learn mutate beliefs with no record of who/when/what-changed-state. Append-only audit entries ({timestamp, operation, expert, actor, before/after hash}) - required for any team deployment, cheap now, painful later.
- [ ] **Allowlist enforcement tests** (architect, cheap): parametrized tests asserting every MCP tool x ResearchMode combination is actually gated as the allowlist declares, so a refactor cannot silently drop a confirmation gate.
- [ ] **Circuit-breaker / session-budget coordination audit** (architect, cheap): verify a circuit-breaker trip surfaces as a BLOCKED reason in the session (not a silent failure) and that semantics between the two layers are documented.
- [ ] **README clarity passes** (buyer + non-technical user): "--budget 3" reads as a price, not a cap - say "budget ceiling" at first use; the "layer underneath" sentence loses non-technical readers - one plain-language paragraph up top ("you bring AI accounts; Deepr routes work to the cheapest one that can do the job and builds experts that remember"); add an explicit "who this is for / not for" block (the buyer, the builder, the agent-host user - not the casual ChatGPT user).
- Validated by the panel (no action, keep doing): cost-control architecture (every seat), the belief/gap/perspective model as the genuine differentiator, docs honesty about experimental status, hosted-MCP-endpoint promotion (the architect's #1 blocker matches Phase 5's new item exactly), and the close-the-loop sequencing.

### Backlog (Not in Active Sequence)

- [~] CLI conformance to mid-2026 best practices (audited 2026-06-12 against clig.dev / kubectl / uv / Heroku / no-color.org; deep-research verified). Deepr already does most of it well: tiered `--verbose/--json/--quiet` with mutual-exclusion, `error_code` in JSON output, stderr discipline in quiet mode, no secrets in argv (keys via env only), kebab-case flags, hidden deprecated commands with warnings + model auto-migration, UTF-8 console handling. Shipped 2026-06-12: non-TTY no-args prints help instead of launching interactive (agent/CI safety); `deepr completion <shell>` for tab-completion. Remaining, by ROI:
  - [x] Structured error envelope for agent consumers (RFC 9457 / Cloudflare agent-error pattern), shipped across all four error surfaces (2026-06-12): `DeeprError`, the provider-layer `ProviderError`, the MCP `ToolError` (always-present `category`/`retryable`, `from_exception`), and the CLI `OperationResult` JSON error (`from_exception`) all carry `category` + `retryable` (+ `retry_after`). `ProviderError` auto-classifies from its `original_error` via `classify_provider_exception`, so the envelope is populated on every provider path (all adapters) with no per-site wiring. An agent can classify a failure and drive backoff without scraping prose. Pairs with the Phase 5 handoff-schema work.
  - [x] Progress/spinner stream discipline (2026-06-12): the MINIMAL/VERBOSE spinner and verbose `progress()` messages now render to the stderr `Console` (out-of-band info per clig.dev); result lines stay on stdout. `deepr ... > out` no longer risks spinner control codes in piped output. Regression-tested (progress -> stderr, success line -> stdout).
  - [ ] Versioned, documented `--json` output schema (output-as-contract): publish the schema and commit to additive-only changes within a major version; overlaps the Phase 5 versioned handoff schemas.
  - [ ] `--plain` tabular output for `grep`/`awk` (complements `--json` for `jq`), and a global `--no-color` flag (Rich already honors `NO_COLOR`/non-TTY; this adds the explicit override).
  - [ ] XDG/platform config paths (`$XDG_CONFIG_HOME/deepr`, `%APPDATA%\deepr`) with the current CWD `.deepr/`+`data/` as a documented fallback - invasive (migration + every path reader), so deferred behind a deprecation window.
  - [ ] Published deprecation window for CLI flags/commands (kubectl model: GA elements live >= 2 releases after a warning naming the replacement) - formalizes the existing hidden-but-functional convention.
- [ ] Self-improving routing via expert feedback loops (experts detect poor routing in their own gaps → trigger micro-evals → propose routing-table updates)
- [ ] Azure Foundry durable agent orchestration + HITL (long-running experts that survive restarts, wait for human approval via SignalR/Durable Functions)
- [ ] Expert watch (extension): broaden `deepr expert sync` (Phase 4) beyond first-party tools to arbitrary configured MCP or REST endpoints on schedule
- [ ] Local model support beyond the Phase 6 `local-ollama` backend (DGX Spark, Jetson Orin Nano Super, multi-GPU); the core local backend + budget-exhausted offload now lives in Phase 6's capacity waterfall
- [ ] Edge deployment of the hosted MCP endpoint (Cloudflare Workers etc.; the core hosted endpoint itself is now a Phase 5 item)
- [ ] Skill marketplace and meta-skills
- [ ] Multi-agent swarm support beyond bounded subagent orchestration
- [ ] `deepr ui` Textual dashboard
- [ ] README demo GIF
- [ ] Code quality carry-over:
  - [ ] Profile schema versioning
  - [ ] Provider fallback integration tests
  - [ ] Performance regression tests
  - [ ] Raise per-module coverage on core modules above the 80% global gate
- [ ] New-machine validation findings (2026-06-12, keyless dev setup):
  - [x] `tests/integration/` was not behind the `DEEPR_RUN_LIVE_TESTS=1` double opt-in: on a keyless machine, dozens of integration tests failed by attempting real provider calls and `test_two_phase_curriculum.py` hung *forever* (the learner poll loop only logged `get_status` exceptions, leaving the job pending and retrying a 401 every 30s with no cap, and never recording the failure so the circuit breaker could not trip). Fixed 2026-06-12: (1) `tests/integration/conftest.py` skips the whole tree unless `DEEPR_RUN_LIVE_TESTS=1` (bare `pytest` is now safe); (2) the poller records each `get_status` failure (breaker can trip) and fails the job fast when the error is non-retryable - reading `retryable` off the provider error envelope, the first real payoff of that work; (3) `pytest-timeout` added as a dev dependency. Regression tests cover fail-fast-on-auth and breaker-trips-on-transient.
  - [x] `tests/unit/test_core/test_company_research.py` only passed when `OPENAI_API_KEY` happened to be set (dev .env, or other modules' import-time `os.environ.setdefault` during full-suite collection - an inter-test ordering dependency). Fixed 2026-06-12: autouse fake-key fixture makes the file self-sufficient in any ordering on any machine.
  - [x] `mypy --strict` providers gate broke against current Azure SDK releases (`azure-ai-projects`/`azure-ai-agents` now ship typed clients: the lazily-assigned `self._project_client = None` inferred as `None`-typed, and `project_endpoint: str | None` flowed into `endpoint: str`). Fixed 2026-06-12 with a narrowed endpoint guard and `Any` annotations on the lazy clients - the gate is green against both old (untyped) and new (typed) SDKs.
- [ ] Bug-hunt findings (2026-06-17, async/test sweep):
  - [x] `AsyncTaskDispatcher` leaked coroutine objects when tasks were cancelled before they started (cost guard, dependency failure, timeout, or `cancel_all`), producing unawaited-coroutine warnings and keeping stale handles in results. Fixed by closing unstarted coroutines on every cancellation path, clearing coroutine handles before awaits, assigning timeout reasons after worker cancellation, and adding regressions for cost-guard and dependency-failure cancellation.
  - [x] Blob-backed report storage did not enforce the same `job_id`/`filename` namespace validation as local storage, so slash/traversal segments could confuse blob listing, deletion, and ownership semantics. Fixed 2026-06-17 by validating blob job IDs and filenames before every blob-name or prefix construction, skipping malformed legacy blob names in listings, and tightening local filename rejection for empty, dot-only, and NUL-containing names.
  - [x] Local report lookup used substring matching against human-readable report directory names, so very short or slug-like `job_id` values could resolve to an unrelated report directory. Fixed 2026-06-17 by requiring exact legacy directory matches or stable generated suffix matches only; short custom IDs now save to exact legacy directories instead of unreadable fuzzy-match-only names.
- [ ] Live-validation findings (2026-06-14, $0 CLI walkthrough with real keys):
  - [x] Tests polluted the user's real `data/experts/` (found via `expert list` showing `MagicMock`, `test_expert`, and stray dirs - the smoking gun `MagicMock/Test Expert.name/`). Any test building an expert/belief store/memory with no explicit dir wrote into the real store; `experts_root()` was the one isolation the conftest lacked. Fixed: autouse `_isolate_experts_root` fixture (`DEEPR_DATA_DIR` -> per-test tmp) + regression test; leaked dirs cleaned. Same class as the cost-ledger pollution.
  - [x] `eval continuity` on an expert that exists but has no beliefs yet said "Create or learn an expert first" (misleading - it exists), and probing a typo'd name created an empty belief dir (BeliefStore constructor). Fixed: profile existence check first (read-only); accurate per-case messages ("not found" vs "no beliefs yet, synthesize..."). Regression-tested.
  - [x] `costs doctor` cried wolf: "Cost log exists: FAIL -> Issues found (1/3)" on a healthy ledger-only setup. `cost_log.json` is a derived view (regenerable from the canonical ledger), so its absence is not a failure. Now informational; "All checks passed (3/3)".
  - [x] No-surprise-bills: `ExpertChatSession` did `self.budget = budget or 10.0`, so an explicit `budget=0.0` ("do not spend") silently became a $10 ceiling (0.0 is falsy) - hit a `--budget 0` CLI caller or an agent passing 0. Fixed: distinguish `None` (default $10) from `0.0` (honored); flip MCP `query_expert` default 0.0 -> None so unspecified still defaults sanely. Found via `deepr mcp test`. Regression-tested.
  - [ ] Minor (noted, unfixed): `deepr search "query"` (a group) returns a confusing "No such command"; the canonical form `deepr search query "..."` is in `--help`. `expert list` shows name and description on adjacent indented lines, easy to misread.
- [ ] Live-validation findings (2026-06-12, $0 lifecycle/roster run):
  - [x] `deepr budget safety` crashed with KeyError('percent_used') on every invocation - `get_spending_summary` never carried the fields the renderer reads (contract drift, no rendering test). Fixed at the source with the full contract regression-tested; `CostSafetyManager` limits now also honor the same `DEEPR_MAX_COST_PER_DAY/_MONTH` env caps the research gate reads (one knob, every spender), clamped to the absolute ceilings.
  - [x] Dev .env leaked into the suite: settings/config tests asserted file values that env overrides beat by design; live Azure integration tests ran (and attempted submission) on any machine with credentials configured. Both fixed: suite-wide `_isolate_budget_env` autouse fixture, and live tests now need the explicit `DEEPR_RUN_LIVE_TESTS=1` double opt-in.
  - [x] Daily spend bucketing looked UTC-keyed while ledger timestamps carried local offsets: a 17:50 PDT job showed in the next UTC day's "Today's Spending" inconsistently across dashboard paths. Fixed 2026-06-17: dashboard aggregation now uses a documented UTC convention for daily totals, monthly totals, and date-range filtering, with offset-boundary regressions.
  - [x] Two report roots in active use (found via the result-detail screenshot showing "No report content available" for a completed $3.20 job): config-driven components (CLI run.py, web app) resolved `results_dir` = `data/reports`, while `context_index` defaulted to `reports/` (and `LocalStorage()` no-arg too, used by `prep`/`team`/`retrieve_expert_reports`; `company_research` even fell back to a third root, `results`). Fixed 2026-06-12: every no-arg default now resolves through `load_config()["results_dir"]` (one root, env `DEEPR_REPORTS_PATH` honored everywhere); `deepr migrate consolidate` moves legacy `./reports` content into the configured root (merges dir collisions one level, never overwrites); `ContextIndex` warns when orphaned reports sit under the legacy root; regression tests cover root agreement, env flow, save-then-scan visibility, and web-API retrievability of a saved report.
- [ ] Live-validation findings (2026-06-11, sub-$5 end-to-end run):
  - [x] Learner job durability (corrected severity: the in-process poll/integrate loop does complete and integrate reports; the gap was *interrupted* runs): submitted jobs are now recorded in the local queue (`learn-<id>`, PROCESSING with the provider job id) so `deepr status`/`list` see them and an interrupted run is recoverable; terminal states and cost sync back to the queue record; polling that stops early lists the still-running jobs honestly.
  - [x] Learner summary bookkeeping: the final "Learning Complete" report always said "Completed: 0 topics / 0.0%" because the poll loop never credited `progress.completed_topics`. Job-to-topic mapping (`LearningProgress.job_topics`) now credits completed/failed topics so the summary reflects reality.
  - [x] Learner UX: `generate_curriculum` now refuses budgets below the minimum viable learning budget ($0.15: generation overhead + one focus topic) BEFORE the first paid call, so an unaffordable plan costs $0 instead of ~$0.10-0.30 of generation/discovery spend followed by every topic being skipped.
  - [x] Windows console encoding: fixed globally at the CLI entry point (stdout/stderr reconfigure to UTF-8 with replacement on Windows) - closes both the `costs timeline` crash and the `research -h` crash from the external-agent run below.
  - [x] Contradiction heuristic precision: fixed 2026-06-14 with an entailment-shaped contradiction screen at absorb. The lexical heuristic now routes candidates into a cheap model verdict instead of minting phrasing-level false contested beliefs. Health-check parity and verdict calibration remain tracked under v2.15 evidence work.
- [x] External-agent live validation (2026-06-11, second wave): another app drove deepr headless and surfaced six front-door findings - documented-but-missing `--budget` flag, cp1252 help crash, `--auto` pairing web-search with a tool-rejecting model, zombie QUEUED job after total failure, explicit `-m` silently overridden by routing, and a deprecation warning citing a retirement date that had passed without the retirement. All six fixed with regression tests, plus the no-surprise-bills audit they triggered (the `-y` budget-gate bypass, the uncapped cautious-mode auto-approve, the fail-open web gate). Details in the changelog. The meta-lesson stands: every external live run has found real bugs the suite could not.

---

## Non-Goals

Explicitly out of scope:

- **General-purpose chat** - Expert chat is domain-focused; for open-ended conversation, use ChatGPT, Claude, Gemini, etc.
- **Workflow orchestration** - Deepr experts are roles that participate in multi-agent teams, but Deepr is not the orchestrator. It handles its domain (research, knowledge, gap detection) and hands off cleanly. Workflow coordination belongs to a separate orchestration layer.
- **Real-time responses** - Deep research takes minutes by design; this is a feature, not a bug
- **Sub-$1 comprehensive research** - Deep research requires substantial compute (use `--auto` for simple queries at $0.01)
- **Mobile apps** - CLI and web dashboard cover the use cases
- **Unreliable features** - Nothing ships until it works consistently

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
| v2.10 | Agentic infrastructure core, Grok 4.20 flagship, legacy migration, Azure Foundry parity (live-integration tests tracked as open Phase 1 work) | Complete |
| v2.10.1 | MCP client + A2A protocol, agent interoperability, skill portability | Complete |
| v2.10.2-2.10.3 | Security hardening, MCP confirmation gate, 80% coverage gate, 5-round bug-hunt sweep | Complete |
| v2.11.0 | Recon native integration (Phase 2b #1), version centralization, doc_reviewer hardening, MCP/async cancellation correctness | Complete |
| v2.12 | Distillr + Primr integrations (Phase 2b complete); Phase E: `mcp/` flipped into the blocking `mypy --strict` gate (third strict island); first Phase 4 knowledge-loop increments - `expert health-check` and `expert absorb` (CLI + MCP, 21 tools); routing preview; bug-hunt fixes | Complete |
| v2.13 | Expert intelligence + distribution: reflection loop (`reflect`), gap-to-tool router (`route-gaps`), per-expert SKILL.md export (`export-skill`); MCP 23 tools; second + third bug-hunt sweeps (broken `deepr_get_result`, `/why` crash, conversation path-traversal, naive-datetime/div-zero/fact-id fixes) | Complete |
| v2.13.1 | Claude Fable 5; temporal perspective queries (`what-changed`/`contested`, MCP 25 tools); contradiction-as-signal in absorb; cost-guard hardening (pricing single-source, tiered settlement, ledger test-isolation, `costs doctor --rebuild`); CI coverage gate made blocking; Python 3.14 blocking; live-validation bug sweep ("***" api_key, orphaned learner jobs found) | Complete |
| v2.13.2 | Expert sync (subscribe/subscriptions/sync - the flagship loop-closer); simple default surface (sectioned help, 19-line .env.example, README clarity); durable learner jobs + $0 refusal of unaffordable budgets; web cost/expert APIs read canonical sources; screenshots regenerated from live data; frontend lint bootstrapped + deps verified; repo hygiene (one branch, zero bot-authored commits) | Complete |
| v2.14 | The perspective release: belief event log, typed edges, temporal query trio (what-changed/contested/why), regenerated digest, all five loop-closers (sync, gap-fill --execute, reflect --execute-followups, health-check flag actioning, durable learner jobs) | Complete |
| v2.15 | The evidence release | Complete |
| v2.16 | The capacity release | In progress |
| v2.17 | The loop/interchange release | Planned |
| v2.18 | The reach release | Planned |
| v3.0 | The contract release - defined by criteria, not features | Future |

## Version Plan (logical order, not a calendar)

Versions are sequenced by dependency and risk, never by dates - this is a
spare-time project with no SLA, and pretending otherwise would be the kind
of false promise the rest of this roadmap avoids. Each release has a
*theme* (the question it answers), its contents come from the phases above,
and the order encodes a deliberate logic:

**capability -> evidence -> capacity -> verified loops/interchange -> reach -> contract.**

Close the loops while the surface is small; measure before making claims;
make tokens cheap before running them routinely; make loop state and portable
knowledge exports dependable before inviting always-on consumers; open the
remote door only when what is behind it is measured, affordable, resumable, and
portable; and promise stability last, because a contract freezes everything
underneath it.

### v2.14 - The perspective release ("why do you believe that?")

Completes the epistemic core while the belief store is still easy to
migrate. Design: [docs/design/temporal-knowledge-graph.md](docs/design/temporal-knowledge-graph.md).

1. [x] Belief event log (shipped: append-only `events.jsonl` dual-written with the legacy window; `what_changed` reads the log when present and is exact with no truncation; legacy stores keep the honest caveat)
2. [x] Typed edges + migration (shipped: `Edge` store with canonical-key dedup + provenance accumulation, symmetric `contradicts`, idempotent migration of legacy `contradictions_with` lists, contested/detected write paths route through `add_edge` with the legacy field mirrored for one release; `supports` edges now written for same-polarity related beliefs in the 0.35-0.7 similarity band - the free heuristic family, advisory structure only, never a confidence input)
3. [x] `explain_belief` (`deepr expert why` + MCP `deepr_explain_belief`, tool 26) - the third temporal query, shipped: belief resolution by id or query-coverage text match, evidence roots, confidence trajectory from the event log (legacy fallback), depth-bounded cycle-safe walk over supports/derived_from chains, direct-neighbor contradictions with status. Read-side, cost-$0. Live-validated day one (the symmetric text matcher rejected a real query against the exact belief it described - fixed to query-coverage scoring with prefix tolerance).
4. [x] Regenerated expert digest (`deepr expert digest`, shipped): compile pass over beliefs + typed edges + contradictions into a browsable Markdown view - $0, no LLM (synthesis at compile time over structured truth), byte-stable for an unchanged store (the "as of" stamp derives from the latest belief event, not the clock), open contradictions surfaced with the adjudication pointer, and a derived-view marker the CLI checks before overwriting (a digest without the marker may have been hand-edited - the regeneration invariant made executable)
5. Loop-closer completion: autonomous gap-fill execution (route-gaps
   advises -> executes within budget), auto re-research from reflection
   follow-ups, absorb-time contradiction flags in the health-check menu

### v2.15 - The evidence release ("prove it")

Turns claims into measurements before any wider exposure. Design:
[docs/design/calibration-and-trust.md](docs/design/calibration-and-trust.md).

1. [x] Source-trust floors (shipped 2026-06-11 - see the panel-findings entry; deterministic read-time ceilings, retroactive, regression-tested through every write path)
2. [x] Belief lifecycle substrate (shipped 2026-06-12, design:
   [docs/design/belief-lifecycle.md](docs/design/belief-lifecycle.md)):
   bi-temporal valid time on events, lossless snapshot archival +
   restore, usage-salience counters (protective-only), health-check
   archive candidates + `--archive-stale` consolidation pass - all $0,
   grounded in the memory-systems corpus review (monotonic accumulation
   is the literature's root failure mode)
3. [~] Calibration harness + published `docs/CALIBRATION.md`; absorb threshold
   derived from the measured curve. Shipped 2026-06-13 ($0, tested): the
   measurement engine (reliability curve, ECE, numpy Platt scaling, derived
   threshold), `deepr eval calibrate --from`, and the FActScore/SAFE-shaped
   grading orchestrator (`grade_corpus`). Paid `--corpus` run executed
   2026-06-14 (~$0.69, gpt-5 grader): it reproduced **saturation** - 100%
   grounded, no derivable threshold. An adversarial over-reach probe
   (`tests/data/calibration-hard/`, ~$0.04 extraction-only check) then showed
   *why*: the extractor defuses planted traps by attributing/qualifying (78/78
   grounded), so the saturation is **extraction faithfulness, not a measurement
   gap**. Conclusion (don't chase this): confidence-vs-grounding calibration is
   degenerate here because extraction is good; the trust story is carried by the
   continuity metrics + absorb verdict transparency, not a calibration curve.
   The cheap probe before the expensive grade is the frugal-validation discipline
   working - it caught a doomed full run for $0.04. Details in docs/CALIBRATION.md.
4. [x] Entailment-shaped contradiction screen at absorb (2026-06-14): the
   lexical heuristic routes, a cheap model entailment verdict concludes, so the
   brittle check no longer mints phrasing-level false contested beliefs
   (`verify_contradictions` default on; refuted -> absorbed, confirmed ->
   `model_confirmed`, failure -> conservative). The atomicity half is **CUT** -
   atomic decomposition stays the extraction model's job; a deterministic
   atomicity monitor is the brittle-rule anti-pattern (tried/removed 2026-06-14).
   Boundary in [docs/design/checks-deterministic-vs-agentic.md](docs/design/checks-deterministic-vs-agentic.md);
   see the STOP banner. Remaining: same verdict on the health-check surface,
   and calibrate the verdict via the evidence layer.
5. Eval methodology v2 (expert-specific metrics + continuity-property
   metrics, versioned methodology); A/B shadow mode once there are
   metrics to compare. Continuity-property metrics shipped 2026-06-13
   (`deepr eval continuity`); see Phase 3.
6. Engineering evidence (Phase E continuation): `mcp/` strict gate,
   mutation-score baseline + ratchet, fault-injection tests; [x] frontend
   lint/tsc/build now a blocking CI job (2026-06-11 - previously
   local-only, which is how a type-breaking dangling identifier and a
   missing ESLint config survived for months)

### v2.16 - The capacity release ("stop paying twice")

Phase 6 in full: plans and hardware people already pay for become bounded
research capacity, making always-on freshness affordable. Design:
[docs/design/capacity-waterfall.md](docs/design/capacity-waterfall.md).

Current baseline: `deepr capacity` visibility, `deepr capacity next`, local-only
expert creation, the local Ollama execution path, `deepr eval local` with local
or explicit CLI judges, `deepr eval local-context`, source-pack sync artifacts,
saved-artifact local admission, runtime admitted-score quality gating, routing
quality priors, portable experts/research via one data dir
([ADR 0004](docs/decisions/0004-one-experts-root-and-portable-data-dir.md)),
normalized `ResearchBackend` profiles, the append-only `quota_ledger.jsonl`
substrate, backend eligibility decisions, and backend selection with measured
quality floors are in place. The remaining work connects real plan-quota
adapters to that substrate and teaches schedulers to consume it. Completed
release details live in [docs/CHANGELOG.md](docs/CHANGELOG.md).

1. [~] Backend abstraction + quota ledger + eligibility/selection gates + `deepr capacity` visibility (visibility, `ResearchBackend`, quota ledger, eligibility decisions, backend selection, and local score-gated runtime selection are in place; live vendor probes and adapter writes remain)
2. [x] Local-first process validation (ollama-backed `research_fn` through the injectable seams) - in place, the substrate the rest builds on
3. [~] `expert make --local`, `local-ollama`, and `--local` wiring are in place; local sync now supports `--fresh-context` and `--deep-context` with free-only retrieval, saved local eval artifacts and source-pack run artifacts are in place, and automatic local routing requires a measured admitted score; plan-quota CLI adapter work remains
4. [~] Capacity-waterfall routing with quality gates; local rung, local/CLI comparison, local context eval, fresh/deep-context local sync, source-pack artifacts, eval-artifact admission, runtime admitted-score gating, eligibility gate, and pure selector are in place. Remaining work is adapters, live probes, auto-mode runtime integration, and scheduler integration.
5. [x] Capacity QOL completion: `deepr capacity next` ranked actions, latest-artifact hints, and concrete job previews are in place (`--expert`, `--report-id`, `--context-mode`, `--scheduled`), including wait guidance for fresh/deep scheduled sync jobs that should not fall through to metered API. `deepr expert sync --scheduled` consumes that guidance for due subscription syncs and returns a wait payload instead of spending when owned/prepaid capacity is blocked. `deepr expert route-gaps --execute --scheduled` returns pending routes and waits instead of starting metered gap-fill research. `deepr expert reflect --scheduled` waits before the reflection evaluator or follow-up research can run from recurring jobs. `deepr expert health-check --scheduled` emits a scheduler action plan, and `--archive-stale --scheduled` waits for explicit confirmation before any local mutation unless `--yes` is set. Durable loop-run records move to v2.17.
6. [ ] Multi-account pools last (multiplies a working mechanism)

### v2.17 - The loop/interchange release ("keep it current, prove it, hand it off")

Makes the loop-engineering promise explicit while staying inside Deepr's role:
experts maintain verified knowledge state; they do not become a general-purpose
workflow orchestrator. This release lands after capacity because routine loops
need cheap/default-free execution, and before hosted reach because remote agents
need a stable local contract to consume.

Design: [docs/design/verified-expert-loops.md](docs/design/verified-expert-loops.md).

1. [x] Loop admission contract: no surface graduates from advisory to
   autonomous until the task repeats, the verifier is automated, the
   budget/capacity envelope is explicit, and the loop has tools/logs/state for
   failure diagnosis. The contract is now codified in `LoopAdmissionContract`
   and exposed through the loop-status dashboard API. Sync, reflection, and
   health-check are admitted; gap-fill remains supervised until gap-closure
   verifier evidence is recorded.
2. [x] `ExpertLoopRun` substrate + `deepr expert loop-status` + MCP read tool:
   schema-versioned loop-run records, typed stop reasons, append-only
   per-expert storage, acceptance metrics, cost per accepted change, and
   read-only CLI and MCP status are in place. Scheduled wait and action-plan
   surfaces for sync, gap-fill, reflection, and health-check now append
   loop-run snapshots and return `loop_run` JSON. Successful sync, non-dry
   gap-fill execution, reflection, health-check audit, and confirmed health
   archive runs also record completed, failed, budget-stopped,
   verifier-failed, or human-gated loop snapshots with spend, verifier outcome,
   and accepted-change metrics where applicable. The dashboard API now exposes
   `/api/experts/{name}/loop-status` as a read-only rollup over those records.
3. [x] Loop completion contract: a loop closes only on verifier pass, no due work
   under the current contract, budget/capacity exhaustion, human gate, or a typed
   failure reason. `ExpertLoopRun` now rejects terminal records without a typed
   stop reason and rejects stop reasons that do not match the run status, so
   model self-declared completion cannot enter the durable loop record.
4. [x] Loop dashboard/API surface: `/api/experts/{name}/loop-status` returns the
   latest run, last sync result, next scheduled action, capacity source, spend,
   acceptance metrics, verifier-failure counts, freshness telemetry, 7-day and
   30-day gap velocity, top open gaps, and contested/open claim state.
5. [x] OKF export/import: `export-okf` as a regenerated derived view over the
   belief/event/edge store; `absorb-okf` as a verified ingestion path. Include
   `index.md`, `log.md`, bundle-relative links, citations, gaps, contested claims,
   and optional `llms.txt` discovery. Export is now implemented as a `$0`
   derived bundle with marker-based overwrite protection; `absorb-okf` parses
   OKF concept documents into source text and routes them through the existing
   extraction, grounding, dedup, and contradiction gates.

### v2.18 - The reach release ("callable from anywhere")

Opens the remote door after evidence (2.15), cheap capacity (2.16), and a local
loop/interchange contract (2.17), because a hosted endpoint invites always-on
consumers who will exercise all three. Design:
[docs/design/hosted-mcp-endpoint.md](docs/design/hosted-mcp-endpoint.md).

1. [~] Streamable HTTP transport; scoped API keys (mode/expert/budget/rate);
   tool-call audit log (doubles as the mutation audit trail). `deepr mcp serve
   --http` now runs the existing MCP server over HTTP/SSE, and the
   scoped-key/audit primitive authenticates key records, enforces mode plus
   expert allowlists before tool dispatch, enforces per-key budget ceilings from
   audited spend plus deterministic tool estimates, fails closed for metered
   remote tools that lack an estimate, enforces per-key rate limits from recent
   audited calls, and records append-only remote-call audit events with response
   cost attribution when available. `deepr mcp audit list` and
   `deepr mcp audit summary` now make those local audit records operable with
   filters, JSON output, and aggregate counts/costs by key, tool, and outcome.
   `deepr-mcp-remote-audit-v1` is now published under `docs/schemas/` so the
   append-only audit trail has a stable validation contract.
   `deepr mcp smoke-http` now validates local/proxied endpoints at `$0`, and
   `deepr mcp registration-manifest` now emits token-redacted
   `deepr-mcp-registration-manifest-v1` endpoint packets with optional smoke
   results for remote host setup.
   `deploy/mcp-http.md` documents the TLS reverse-proxy recipe.
   `deploy/mcp-http/` now adds the
   container variant with scoped-key bootstrap, loopback-only host publishing,
   and `$0` smoke validation guidance. `deploy/mcp-http/azure-container-apps/`
   now provides the first cloud-provider template, preserving persistent
   `/data`, scoped-key state, HTTPS-only ingress, and remote-audit durability on
   Azure Container Apps. Remaining work: additional cloud provider templates and
   live registration smoke against a real hosted-agent platform. The key CLI is
   shipped as `deepr mcp keys`.
2. [~] Versioned handoff schemas (downstream agents get stability guarantees):
   `deepr_expert_handoff` and `/api/experts/{name}/handoff` now return the
   `$0`, read-only `deepr-expert-handoff-v1` payload with profile summary,
   manifest counts, bounded claims/gaps, dashboard telemetry, loop-status
   rollup, OKF interchange hints, and an additive compatibility contract.
   JSON Schema is published at `docs/schemas/expert-handoff-v1.json`.
   `deepr-loop-status-v1`, `deepr-okf-profile-v1`, and
   `deepr-mcp-remote-audit-v1`, `deepr-mcp-registration-manifest-v1`, and
   `docs/schemas/registry.json` now publish the adjacent loop, OKF mapping,
   hosted remote-audit, and hosted registration contracts with additive
   compatibility policy.
3. Expert Crews (Phase 4c) + autonomous research campaigns (Phase 4b) -
   the multi-expert deliverables, now consumable remotely
4. Ops analytics: cost-vs-quality frontier, routing-drift and anomaly
   alerts (flying blind ends before 3.0)

### v3.0 - The contract release (criteria, not features)

3.0 is declared when an always-on agent platform can rely on Deepr as
organizational knowledge infrastructure *without the author in the loop*.
The criteria, all measurable:

- [x] Handoff schemas versioned with a published deprecation policy
- [x] Loop-status and OKF profile schemas versioned with backward compatibility
- [ ] Calibration published and current for the shipping extraction model
- [ ] Hosted endpoint with scoped auth, per-key budgets/rate limits, audit log
- [ ] Multi-user safety: RBAC, workspace isolation, mutation audit trail
- [x] A documented supported-surface statement (what is stable, what is
      experimental, what export guarantees exist if the project stops)
- [ ] Zero known silent-money paths (every spend source writes the
      canonical ledger; proven by fault-injection, not assertion)

Anything not on this list ships in a 2.x when ready; nothing waits for 3.0
that does not gate the contract.

### Deliberately unversioned

- **Phase E** (engineering standards), **Phase Q** (code-health hardening),
  and **model-registry currency** are continuous - every release carries its
  share.
- **Bug-hunt sweeps and live validations** happen per release, not as
  versioned features (they have found real bugs every time they have run).
- **Intentionally not planned**: hosted-by-Deepr SaaS, SLAs, enterprise
  SSO before team features exist, full SLSA L3 (see Non-Goals) - listed so
  their absence reads as a decision, not an oversight.

---

**Questions?** Open a [GitHub Discussion](https://github.com/blisspixel/deepr/discussions) or check the [documentation](docs/).

[MIT License](LICENSE) · [GitHub](https://github.com/blisspixel/deepr)
