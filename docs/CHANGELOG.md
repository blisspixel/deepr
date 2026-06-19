# Changelog

All notable changes to Deepr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added the first v2.17 durable loop substrate: schema-versioned
  `ExpertLoopRun` records, an append-only per-expert loop-run store, and
  read-only `deepr expert loop-status`.
- Added `deepr_expert_loop_status`, a read-only MCP tool for host agents to
  inspect durable expert loop runs, stop reasons, budget/capacity source,
  verifier fields, acceptance metrics, and next actions.
- Added `deepr_expert_handoff` and `/api/experts/{name}/handoff`, a `$0`
  read-only `deepr-expert-handoff-v1` payload for downstream agents. It includes
  profile summary, manifest counts, bounded claims/gaps, dashboard telemetry,
  loop-status rollup, OKF interchange hints, and an additive compatibility
  contract, with JSON Schema published under `docs/schemas/`.
- Added `deepr-loop-status-v1`, `deepr-okf-profile-v1`, and
  `docs/schemas/registry.json` so downstream agents can validate durable loop
  status and the OKF mapping contract with an additive compatibility policy.
- Added `deepr-mcp-remote-audit-v1` and registered it in
  `docs/schemas/registry.json` so hosted MCP remote-call audit records have a
  published additive compatibility contract.
- Added the first hosted-MCP scoped-key primitive: `ScopedMCPKeyStore`, HTTP
  transport enforcement for key mode, expert allowlists, confirmation
  requirements, and append-only `deepr-mcp-remote-audit-v1` events for
  authenticated remote tool calls.
- Added `deepr mcp keys create/list/revoke` for local scoped-key management.
  Created secrets are shown once, list output omits secrets and hashes, and
  revoked keys are rejected by the HTTP scoped-key authenticator.
- Added per-key budget enforcement for scoped HTTP MCP calls. The transport now
  sums prior audited key spend, blocks calls whose requested budget or fixed
  estimate exceeds the remaining key budget, injects remaining budget into
  budget-aware tools when omitted, and records successful response costs in the
  remote audit log.
- Added per-key rate limits for scoped HTTP MCP calls. Key records can now carry
  a calls-per-minute ceiling, `deepr mcp keys create --rate-limit` exposes it,
  and the HTTP transport blocks over-limit calls before tool dispatch with
  retry metadata and an audited denial.
- Added `deepr mcp audit list`, a read-only local CLI for reviewing
  `deepr-mcp-remote-audit-v1` remote-call audit records with key, tool, outcome,
  limit, and JSON filters.
- Added `deepr mcp audit summary`, a read-only aggregate view over the same
  remote-call audit log with counts and audited cost grouped by key, tool, and
  outcome.
- Added `deepr mcp serve --http`, a Streamable HTTP/SSE serve mode for the
  existing MCP server. It defaults to loopback and relies on the HTTP
  transport's shared-token or scoped-key gates for reachable binds.
- Added `deepr mcp smoke-http`, a `$0` HTTP MCP endpoint smoke check covering
  health, initialize, tools/list, and free `deepr_tool_search` dispatch for
  local or TLS-proxied endpoints.
- Added `deepr mcp registration-manifest`, a token-redacted
  `deepr-mcp-registration-manifest-v1` endpoint packet for remote host setup
  that can embed the `$0` HTTP smoke result without serializing bearer secrets.
- Added `deploy/mcp-http.md`, a hosted MCP reverse-proxy recipe covering
  scoped keys, loopback service binding, Caddy/nginx TLS termination, smoke
  validation, revocation, and operational guardrails.
- Added `deploy/mcp-http/`, a hosted MCP HTTP container recipe with a dedicated
  Dockerfile, compose service, `.env.example`, scoped-key bootstrap steps,
  loopback-only host publishing, and `$0` smoke validation guidance.
- Added `deploy/mcp-http/azure-container-apps/`, an Azure Container Apps
  template for the hosted MCP HTTP container with persistent `/data` on Azure
  Files, HTTPS-only ingress, scoped-key state, and remote-audit durability.
- Scheduled expert wait and action-plan surfaces now append `ExpertLoopRun`
  snapshots and include a `loop_run` object in JSON output for `sync`,
  `route-gaps`, `reflect`, and `health-check`.
- Successful `deepr expert sync` runs now append completed or failed
  `ExpertLoopRun` snapshots with trigger, budget spent, capacity source, accepted
  change count, and next action for failed topics.
- Non-dry `deepr expert route-gaps --execute` runs now append gap-fill
  `ExpertLoopRun` snapshots with trigger, budget spent, capacity source,
  accepted changes, typed failure stops, and human-gate or budget stop actions
  when routed gaps are deferred or skipped.
- `deepr expert reflect` now appends reflection `ExpertLoopRun` snapshots with
  verifier outcome, score, model version, typed verifier-failed stops, and
  follow-up absorption metrics when `--execute-followups` runs.
- `deepr expert health-check` and confirmed `--archive-stale` runs now append
  health-check `ExpertLoopRun` snapshots with verifier outcome, recommended
  action state, accepted archival counts, and typed stops for critical reports,
  capacity waits, confirmation gates, or no corrective work.
- Added `/api/experts/{name}/loop-status`, a read-only dashboard API rollup over
  durable expert loop runs with latest run, last sync result, waiting scheduled
  action, failure, capacity source, spend, acceptance, and verifier failure
  metrics.
- The loop-status dashboard API now includes `expert_state` telemetry for
  profile freshness, 7-day and 30-day gap velocity, top open gaps, and
  contested/open claim counts from manifest links and belief contradiction
  edges.
- `ExpertLoopRun` now enforces the loop completion contract: completed, failed,
  and cancelled runs require typed stop reasons, and waiting, completed, failed,
  and cancelled states reject stop reasons that do not match their status.
- Added `LoopAdmissionContract` and dashboard `admission_contracts` so loop
  surfaces expose the four admission gates: repeat demand, automated
  verification, explicit budget/capacity, and failure-diagnosis state. Gap-fill
  remains supervised until gap-closure verifier evidence is recorded.
- Added `deepr expert export-okf NAME PATH`, a `$0` regenerated OKF Markdown
  bundle over structured expert state. It writes `index.md`, `log.md`, concept
  pages, citations, typed relations, gaps, contested claims, and optional
  `llms.txt`, with marker-based overwrite protection so the bundle remains an
  interchange view rather than authoritative state.
- Added `deepr expert absorb-okf NAME PATH`, which parses OKF concept Markdown
  and frontmatter into source text for `ReportAbsorber`. The existing
  extraction, grounding, dedup, and contradiction gates decide what enters the
  belief store, so OKF Markdown is never trusted as canonical state.
- Added `deepr expert health-check --scheduled`, which emits a scheduler action
  plan for recommended actions, and made `--archive-stale --scheduled` wait for
  explicit confirmation instead of prompting or mutating unless `--yes` is set.
- Added `deepr expert reflect --scheduled`, which validates the local report
  lookup and then returns a structured wait payload before any reflection
  evaluator or follow-up research can run from a recurring scheduler job.
- Added `deepr expert route-gaps --execute --scheduled`, which returns pending
  routes plus a wait state instead of starting metered gap-fill research from a
  recurring scheduler run.
- Added `deepr expert sync --scheduled`, a scheduler-facing capacity gate that
  waits with structured `capacity next` actions instead of falling through to
  metered API when a due recurring sync lacks owned/prepaid capacity. Explicit
  `--api` remains the operator override.
- Added concrete job previews to `deepr capacity next`: `--expert`,
  `--report-id`, `--context-mode none|fresh|deep`, and `--scheduled` fill the
  suggested command shape and show wait guidance when a fresh/deep scheduled
  sync should wait for cheap local capacity instead of falling through to
  metered API.
- Added `deepr expert make --local`, a provider-free expert creation path that
  records `provider=local`, copies optional seed documents into the expert's
  local documents folder, and prints the next `subscribe` plus
  `sync --local --fresh-context` commands for $0 maintenance.
- Added `deepr capacity next`, a read-only `$0` guidance surface that ranks
  the current capacity block reason, local setup steps, latest usable eval
  artifact admission, eval refresh, and explicit metered fallback for a task
  class.
- Added saved local eval artifact admission:
  `deepr capacity admit --from-eval <path|latest> --task-class <task>` loads
  `deepr eval local --save` output, validates zero Deepr metered cost, score
  ranges, minimum score, model match, and failed prompt results, then records
  the selected model's score and artifact summary in the machine-local
  admission ledger.
- Added free-only fresh retrieval context for local expert sync:
  `deepr expert sync NAME --local --fresh-context` fetches explicit URLs and
  DuckDuckGo results when the optional package is installed, prepends bounded
  source context to the local Ollama prompt, and keeps Deepr metered cost at
  `$0` without invoking API-key search providers.
- Added bounded local deep context for expert sync:
  `deepr expert sync NAME --local --deep-context` runs multi-query free
  retrieval before the local Ollama call, de-duplicates URLs, records source
  pack metadata, supports `DEEPR_SEARXNG_URL` for a self-hosted SearXNG search
  endpoint, and keeps the no-source path as `no_changes` instead of absorbing
  unsupported local claims.
- Added `$0` local context evaluation via `deepr eval local-context`. It
  compares no context, fresh context, and deep context for one local model,
  uses a local model as the judge, records source and citation metadata, and can
  save a JSON artifact under `data/benchmarks` without invoking provider APIs.
- Added source-pack artifacts for context-bearing expert sync runs. Local
  fresh/deep sync now writes a bounded JSON source pack under the expert
  knowledge directory, includes the artifact path and source summary in sync
  outcomes, and blocks absorption if the source trail cannot be persisted.
- Added `$0` local Ollama comparison via `deepr eval local`. It compares local
  models on an agentic-loop prompt set, uses a local model as the judge, reports
  score, latency, winner, and cost, and can save a JSON artifact under
  `data/benchmarks` without invoking provider APIs.
- Added explicit CLI judge support to `deepr eval local`: `--judge-cli grok`
  for the installed Grok CLI shape and `--judge-command` for other headless
  subscription CLIs. CLI judges require `--allow-cli-judge`, receive prompts
  through a temp file, run with shell execution disabled, and are never selected
  implicitly because the external CLI may consume its own quota.
- Added pure backend selection for the capacity waterfall. The selector orders
  normalized backends `local -> plan_quota -> api_metered`, reuses eligibility
  decisions, enforces optional measured quality floors, and returns structured
  candidate reasons without invoking adapters, vendor CLIs, or provider APIs.
- Added pure backend eligibility decisions over `ResearchBackend` plus observed
  `QuotaState`, covering unavailable backends, unsupported task classes,
  metered budget gates, missing or unknown quota, exhausted windows,
  quarantines, overage-enabled plan backends, reserve floors, and
  multi-account eligible-account selection without invoking vendor CLIs or
  provider APIs.

### Changed
- `expert sync --local` now keeps the full maintenance loop local by passing a
  local Ollama-backed absorber into the sync engine. Fresh-context syncs with
  zero retrieved sources now record no changes instead of absorbing the local
  model's uncertainty as beliefs.
- Fresh/deep context flags now require a local sync backend. If no admitted
  local model is available and `--local` was not provided, Deepr stops instead
  of silently falling through to a metered API backend.
- Clarified README, feature docs, roadmap, capacity design, and agent
  instructions so local Ollama, APIs, plan CLIs, and explicit CLI judges are
  described by their current shipped status instead of blended together.
- Automatic local routing now feeds admitted scores into the runtime quality
  floor. Scoreless manual admissions remain visible but no longer take over
  `expert sync` or `expert absorb` automatically; `--local` remains the
  explicit override.
- Aligned the capacity README, roadmap, changelog, and design notes so the
  README stays as the front-door summary, the roadmap stays forward-facing, and
  release history remains in the changelog.

### Fixed
- Corrected the built-in search backend wrapper to pass structured query
  arguments to `WebSearchTool` instead of a positional dict.
- `deepr_query_expert` now passes the caller's budget into `ExpertChatSession`
  for normal expert answers, not only for `agentic=true`, so remote scoped
  budgets and explicit low ceilings cap model-token spend on plain expert
  queries too.
- Corrected the built-in browser backend to use the existing scraper fetcher and
  content extractor instead of a missing `scrape_url` helper.

## [2.16.2] - 2026-06-17

Capacity-ledger and CI reproducibility patch release.

### Added
- Added the append-only capacity quota ledger
  (`data/capacity/quota_ledger.jsonl`, overrideable with
  `DEEPR_CAPACITY_DATA_DIR`) and surfaced the latest observed quota state in
  `deepr capacity` / `deepr capacity --json` without invoking vendor CLIs or
  provider APIs.

### Fixed
- Prevented the web background poller from starting under Flask `TESTING`
  mode, so the unit suite does not leave a daemon poller running during
  interpreter shutdown.
- Added the PyYAML type stub package to dev dependencies so the documented
  strict mypy gate is reproducible from a fresh dev install.

## [2.16.1] - 2026-06-17

Bug and security hardening patch release.

### Fixed
- Prevented rapid back-to-back belief events from being skipped on
  filesystems or clocks with equal timestamp granularity by making event
  timestamps monotonic per store.
- Normalized offset-aware cost ledger timestamps to UTC before daily, monthly,
  and custom range bucketing.
- Closed unstarted dispatcher coroutines on dependency failure, cancellation,
  timeout, and fanout shutdown so cancelled task graphs do not leak runtime
  warnings.
- Corrected stale docs and CLI references from deprecated `deepr cost` to
  `deepr costs`.

### Security
- Hardened Azure blob storage report paths by validating job IDs and filenames
  before blob name construction and skipping malformed legacy blob names during
  listing.
- Tightened local report storage filename validation and removed
  substring-based report directory lookup so unrelated readable report names
  cannot be selected by crafted IDs or prompt slugs.

## [2.16.0] - 2026-06-16

Packaging, repo-hygiene, and security release.

### Changed
- Adopted the canonical PyPA **src layout**: the package now lives at
  `src/deepr/` (import name `deepr` unchanged). This prevents accidentally
  importing the package from the working directory instead of the installed
  one. Packaging, CI, code-health scripts, and docs updated accordingly.

### Fixed
- Corrected `.mailmap`, which was reversed and relabelled the maintainer's own
  commits as a third-party GitHub user on the contributor graph. Automation/AI
  emails now coalesce onto the maintainer; no bot appears as a contributor.
- Security: `BeliefStore` now containment-checks the expert name before using
  it as a path component (it is constructed directly from MCP tool args), so a
  traversal name cannot escape the experts root.
- Security: web/API error responses no longer echo exception text to clients
  (generic message client-side, detail logged server-side).

### Security
- Triaged all open CodeQL alerts (multi-agent triage + adversarial
  verification): real findings fixed with tests, false positives dismissed with
  documented reasons. Added `validate_identifier` + `safe_path_within` helpers
  in `utils/security.py`.
- Hardened GitHub Actions with least-privilege `permissions: contents: read`
  on the CI and mutation workflows; all actions pinned to commit SHAs.

## [2.15.1] - 2026-06-16

Security and maintenance release. No functional changes.

### Security
- Cleared all 9 npm advisories in the web frontend (0 vulnerabilities
  remaining): Vite 5 -> 8 with esbuild (GHSA-67mh-4wv8-2f99,
  GHSA-gv7w-rqvm-qjhr), react-syntax-highlighter 15 -> 16 with prismjs
  (GHSA-x7hr-w5r2-h6wg), ws 8.21 (GHSA-96hv-2xvq-fx4p), @babel/core 7.29.7
  (GHSA-4x5r-pxfx-6jf8), and form-data 4.0.6 (GHSA-hmw2-7cc7-3qxx).
- Python security bumps: aiohttp 3.13.5 -> 3.14.1, cryptography 48.0.0 ->
  48.0.1.

### Changed
- Frontend dependency refresh, verified green (lint/tsc/build):
  @vitejs/plugin-react 6, TypeScript 6, framer-motion 12, sonner 2,
  tailwind-merge 3, zustand 5. Dropped the deprecated tsconfig `baseUrl`
  (TS 6 resolves `paths` without it). Routine pip bumps: openai,
  azure-cosmos, flask-limiter, rich, google-genai, react-markdown.

### Build
- Pinned all GitHub Actions to commit SHAs and normalized setup-uv to v7
  (supply-chain hardening). Documented the branch, merge, and hygiene
  policy in CONTRIBUTING.

## [2.15.0] - 2026-06-14

### Changed
- Absorb contradiction and dedup are now agentic, not brittle. The free
  word-overlap heuristics only *route*; a cheap model verdict concludes
  (`AGENTIC_BALANCE.md`). A phrasing-level false contradiction is absorbed
  normally instead of recorded as a false contested belief, and two different
  facts that merely share words (e.g. "$10/M" vs "$30/M") are no longer silently
  merged into one (data loss). The verdict is authoritative for the graph too (no
  lexical contradiction edge is re-created behind it), and the absorb result
  reports how many false positives the verdicts caught (`contradictions_refuted`,
  `merges_blocked`). Cost-bounded (uncertain band only), reuses the extraction
  client, every existing caller unchanged.
- Removed a regex "atomicity monitor" that classified claim atomicity with
  word-markers: atomicity is meaning, the extraction model's job, not a lexical
  rule (the brittle-rule-for-meaning anti-pattern).

### Fixed
- No-surprise-bills: `ExpertChatSession` did `budget or 10.0`, so an explicit
  `budget=0.0` ("do not spend") silently became a $10 ceiling (0.0 is falsy). A
  `deepr expert chat --budget 0` caller, or an agent passing 0, got a real
  budget. Now `None` means default ($10) and `0.0` is honored; the MCP
  `query_expert` default flips `0.0 -> None` so unspecified still defaults sanely.
- Tests polluted the user's real `data/experts/` (leaking `MagicMock`,
  `test_expert`, and stray expert dirs): the experts root was the one isolation
  the suite lacked. Added an autouse fixture pinning `DEEPR_DATA_DIR` to a
  per-test tmp dir.
- `eval continuity` on an expert that exists but has no beliefs yet wrongly said
  "Create or learn an expert first", and a typo'd name created an empty belief
  dir. Now checks the profile exists first (read-only) with accurate per-case
  messages.
- `costs doctor` reported "Issues found (1/3)" on a healthy ledger-only setup
  because the *derived* `cost_log.json` view did not exist. The view is
  regenerable from the canonical ledger, so its absence is informational, not a
  failure.
- Unified the reports root across every component. Config-driven writers
  (CLI `run`, web app) saved under `data/reports`, but `ContextIndex`
  scanned `./reports`, a no-arg `LocalStorage()` (used by `prep`, `team`,
  `retrieve_expert_reports`) wrote to `./reports`, and `company_research`
  fell back to a third root (`results`) - so a completed job could render
  "No report content available" in the web UI, and search/absorb could
  not see reports written elsewhere. Every no-arg default now resolves
  through `load_config()["results_dir"]` (one root, env
  `DEEPR_REPORTS_PATH` honored everywhere; default `data/reports`).
  Regression tests cover root agreement, env flow, save-then-scan
  visibility, and end-to-end web-API retrievability of a saved report.
- `mypy --strict` providers gate (blocking CI) broke against current
  Azure SDK releases: `azure-ai-projects` / `azure-ai-agents` now ship
  typed clients, so the lazily-assigned `self._project_client = None`
  inferred as `None`-typed and `project_endpoint: str | None` flowed into
  a `str` parameter. Narrowed the endpoint guard and annotated the lazy
  clients as `Any`; the gate is green against both old (untyped) and new
  (typed) SDKs.
- `tests/unit/test_core/test_company_research.py` only passed when
  `OPENAI_API_KEY` happened to be set (a dev `.env`, or another module's
  import-time `os.environ.setdefault` during full-suite collection - an
  inter-test ordering dependency). An autouse fake-key fixture makes the
  file self-sufficient on any machine and in any test ordering.

### Added
- Guided setup and a portable data directory (UX-first onboarding):
  - `deepr init` detects existing provider keys, writes `.env`, sets a
    budget ceiling, and can point storage at a synced folder. Scriptable
    and CI-safe: `--yes`, `--budget`, `--data-dir` (writes `DEEPR_DATA_DIR`
    / `DEEPR_EXPERTS_PATH` / `DEEPR_REPORTS_PATH`), no prompts required.
  - `deepr doctor` gains a severity model (ok / info / warning / error), a
    one-line `_summarize()` verdict, a storage-locations check, and a
    ranked "next step" so the most actionable fix is always surfaced.
  - One experts root: `config.experts_root()` is the single source of
    truth (`DEEPR_EXPERTS_PATH`, else `DEEPR_DATA_DIR/experts`, else
    `data/experts`), so setting one data dir relocates experts + research
    to a synced folder and they follow you across machines. ~12 experts
    modules were centralized onto it; a guard test prevents split-store
    regressions. Cost ledger, queue, and traces stay machine-local
    ([ADR 0004](decisions/0004-one-experts-root-and-portable-data-dir.md)).
  - `numpy` moved to core dependencies (it is imported at startup) with a
    CI `core-install` smoke job, so a base `pip install` no longer crashes
    on first run.
- Capacity visibility and $0 local-model execution (toward routing on
  owned/prepaid capacity before metered API):
  - `deepr capacity` (`--json`, `--probe`) reports detected capacity -
    local Ollama, plan-based CLIs, metered APIs - with a cost model, so you
    can see what runs for free before paying per token.
  - A local Ollama backend (`deepr/backends/local.py`) targets the
    OpenAI-compatible `/v1` endpoint and plugs into the injectable research
    seams; `deepr expert absorb --local` and `deepr expert sync --local`
    run extraction and sync at $0. Expert maintenance (absorb + sync) was
    extracted into its own module to keep file-size ratchets honest.
  - Routing **quality priors** (`deepr/routing/quality_priors.py`) seed
    provisional model rankings from published benchmark indices, so auto
    mode routes sensibly without every user paying for evals first.
  - Eval-gated local **admission** + automatic owned-capacity-first routing
    for expert maintenance: `deepr capacity admit <model> --task-class
    sync|absorb` records the operator's dated acceptance (default 90-day
    expiry; `admissions` / `revoke` to inspect and withdraw). Once a model
    is admitted, `deepr expert sync`/`absorb` run on it automatically at $0
    before any metered API call - the first wired rung of the waterfall.
    `--local` forces local with no admission; the new `--api` forces
    metered. The chosen backend and the reason are printed ("why did this
    run on X"). Admissions are machine-local (`DEEPR_CAPACITY_DATA_DIR`),
    not in the portable experts dir, since local capacity is per-machine.
    Selection is admission-driven and verified against live availability: the
    waterfall uses an admitted model only if Ollama currently has it loaded
    (checked via a new `available_local_models()`), so it is robust to model
    list order and does not depend on `DEEPR_LOCAL_MODEL` (which now only
    breaks ties among several admitted+available models). Validated end to end
    on a local 80B MoE (`qwen3-coder-next`): $0 context-grounded claim
    extraction, admit -> auto-route -> local, admitted-but-unloaded ->
    metered fallback.
  - `deepr capacity` now also detects **GitHub Copilot CLI** (`copilot`) and
    **Cursor CLI** (`cursor-agent`) as plan-quota sources, alongside Claude
    Code / Codex / Antigravity / Kiro.
  Design: [capacity-waterfall.md](design/capacity-waterfall.md).
- Evidence layer - making expert trust measurable rather than asserted:
  - `deepr eval continuity` scores staleness honesty, abstention,
    contradiction-surfacing, and what-changed exactness from stored belief
    state at $0.
  - `deepr eval calibrate` answers "does extraction confidence track
    grounding?" - reliability curve, expected calibration error, and a
    numpy Platt-scaling threshold (Newton-Raphson, no sklearn). `--from`
    grades existing pairs at $0; `--corpus` runs the paid extraction +
    strong-model pre-grade (FActScore/SAFE-style atomic decomposition,
    `--grader-model`, `--sample`, `--max-cost`, `--yes`). First measured
    curve committed in [docs/CALIBRATION.md](CALIBRATION.md).
  - The deterministic-vs-agentic check boundary is documented in
    [checks-deterministic-vs-agentic.md](design/checks-deterministic-vs-agentic.md)
    (deterministic for structure/types/ranges; model judgment for semantic
    grounding, contradiction, and atomicity).
- Install / update QOL, matching modern CLI tooling (claude / codex / grok):
  - `deepr upgrade` self-updates to the latest released version, detecting
    how deepr was installed (pipx / pip / editable source checkout) and
    running the right command. `deepr upgrade --check` reports whether a
    newer version exists (via the PyPI JSON API) without installing;
    degrades gracefully offline and for editable installs (prints git
    steps). No new dependencies (urllib + subprocess).
  - The install one-liners (`scripts/install.ps1`, `scripts/install.sh`)
    are now idempotent: re-running updates an existing install instead of
    failing, report the installed version, and support uninstall
    (`-Uninstall` / `-- --uninstall`). `scripts/install.bat` is modernized
    to delegate to install.ps1 (was stale: referenced Python 3.9).
- Agent-classifiable error envelope across every error surface (RFC 9457 /
  agent-error pattern), so a consumer can classify a failure and drive
  backoff without scraping the message:
  - `DeeprError` carries `category` (provider / auth / budget / config /
    storage / validation / internal) and a boolean `retryable`; `to_dict()`
    surfaces them plus `retry_after` (seconds, when known). Transient
    provider failures (timeout, unavailable, rate-limit) are retryable;
    auth/budget/config/validation are actionable and not.
  - The provider-layer `ProviderError` gains the same fields + `to_dict()`,
    plus a `classify_provider_exception()` helper that maps a raw provider-
    SDK exception to (category, retryable, retry_after) by class name
    (works across openai/anthropic/gemini/xai/azure without importing each).
    `ProviderError` auto-classifies from its `original_error` when the
    envelope is not set explicitly, so every adapter's existing
    `raise ProviderError(..., original_error=e)` gets correct classification
    with no per-site changes - the envelope is populated on every provider
    path, not just one adapter.
  - The MCP `ToolError` always emits `category` + `retryable` (and
    `retry_after` when known) and gains `ToolError.from_exception(...)`;
    `_make_error()` accepts the classification.
  - The CLI `OperationResult` JSON error output always carries `category` +
    `retryable` (+ `retry_after`), with `OperationResult.from_exception(...)`.
  Fully additive everywhere: existing keys (error/error_code/message/
  details, retry_hint/fallback_suggestion) are unchanged.
- CLI best-practices refinements (audited against clig.dev / kubectl / uv /
  Heroku conventions, mid-2026):
  - `deepr` with no arguments now prints help and exits 0 when stdin is not
    a TTY (a script, CI, or an AI agent driving the CLI), and only launches
    interactive mode on a real terminal. Previously it always tried
    interactive mode, which is meaningless to a non-interactive caller.
  - `deepr completion <bash|zsh|fish>` emits a shell tab-completion script
    to stdout (install hint to stderr, so `eval "$(deepr completion bash)"`
    and redirection stay clean). Surfaces Click's native completion behind
    a documented, discoverable verb.
- `deepr migrate consolidate` moves reports left under a legacy `./reports`
  root into the configured root (merges directory collisions one level
  deep, never overwrites a file; `--dry-run` previews). `ContextIndex`
  now logs a warning when it finds orphaned reports under the legacy root
  so they are not silently invisible to search and the dashboard.
- `AGENTS.md` at the repo root: the canonical, vendor-neutral agent guide
  (dev setup, test/lint/type commands, hard rules). `CLAUDE.md` is a thin
  pointer to it so Claude Code picks it up without content drift.
- Belief lifecycle and salience substrate (design:
  `docs/design/belief-lifecycle.md`), grounded in a nine-corpus review of
  the 2026 agent-memory and claim-verification literature (the documented
  root failure mode of agent memory is monotonic accumulation - deepr
  shared it with 17 of 20 surveyed systems):
  - Bi-temporal valid time: belief events carry an optional world-valid
    `invalidated_at` (when the fact stopped being true) distinct from the
    event timestamp (when the store learned it) - the Graphiti pattern,
    added while the event schema is young. Old event lines parse
    unchanged.
  - Lossless archival: archival events embed a full belief snapshot and
    `restore_belief` rebuilds from the log alone - reversibility is
    executable, not aspirational. Pre-snapshot archival events honestly
    return None.
  - Usage salience: per-belief `retrieval_count`/`last_retrieved_at` +
    `BeliefStore.record_retrieval`, recordable only from already-mutating
    surfaces - the read-side query surface (validate, why, digest,
    contested, what-changed) stays pure/$0, regression-tested. Usage only
    ever protects a belief from archival; absence never condemns one.
  - Consolidation pass: health-check gains an `archive_candidates`
    finding and an `--archive-stale` action ($0, no LLM). Candidates must
    pass every gate - decayed below 0.2, unevidenced 90+ days, no
    recorded usage, and not contested (contested beliefs are signal,
    never garbage - the Rashomon rule). Dry-listed with confirmation;
    every archival event-logged with snapshot and thresholds.
  Live-validated end to end at $0: inject stale belief, audit flags it,
  CLI archives it, snapshot restores it.
- Roadmap absorbs the rest of the corpus review: entailment-shaped
  contradiction screen and atomic claim decomposition (v2.15, from the
  claim-verification corpus), continuity-property metrics for eval
  methodology v2 (the ATANT audit shows popular memory benchmarks test
  at most 2 of 7 continuity properties), and ADAM-style memory
  extraction/poisoning cases for the Phase 5 red-team suite.
- Abstention as a first-class absorb outcome (`insufficient` bucket).
  Candidates the report supports weakly (extraction confidence in
  [0.4, min_confidence)) are no longer lumped into "rejected": they
  render as "insufficient grounding - abstained, not refuted", natural
  re-research targets that may well be true. The DAVinCI/TRUST
  "Not Enough Info" pattern from the calibration literature corpus;
  noise below 0.4 stays rejected. CLI summary and MCP payload carry
  insufficient_count.
- Source-trust confidence ceilings (v2.15 evidence release, panel finding
  shipped). `Belief.trust_class` (primary/secondary/tertiary; retroactive
  tertiary default for all pre-floor beliefs) with deterministic caps
  applied at read time like decay: tertiary single-source reads at most
  0.60, two independent tertiary sources at most 0.80, secondary+
  uncapped. Because enforcement is read-time, the cap holds through every
  write path (absorb, sync, merge, adjudication) and no model judgment
  can lift it - only new better-sourced evidence raises the ceiling.
  Absorb marks research-derived beliefs tertiary, making this the
  deterministic ingestion-time prompt-injection backstop: a poisoned
  report claiming 0.98 extraction confidence stores a belief that reads
  <= 0.60 (regression-tested). Honest framing: extraction confidence
  means report support, never truth probability - measured calibration
  is the harness, next.
- Frontend checks are a blocking CI job (lint with zero warnings, tsc,
  production build on Node 22 with npm cache). Previously the React
  frontend was verified only by hand - which is how a type-breaking
  dangling identifier and a missing ESLint config survived for months.
  First item of the v2.15 evidence release.

## [2.14.0] - 2026-06-11

### Added
- Auto re-research from reflection (`deepr expert reflect ...
  --execute-followups [--budget X]`). The last advisory half-loop closed:
  the follow-up queries reflection emits for weak reports now actually
  run, through the same gap-fill engine (run-ceiling budget,
  skip-not-fail, verification-gated absorb with contradiction flagging).
  Opt-in with confirmation - plain reflect stays read-only. With this,
  every v2.14 loop-closer is shipped: sync, gap-fill execution,
  reflection follow-ups, and health-check actioning of absorb-time flags.
- Autonomous gap-fill execution (`deepr expert route-gaps --execute`).
  The gap-to-tool router graduates from advisory to action: the
  highest-value research-route fills run (ordered by the router's
  value-per-dollar signal), findings absorb through the
  verification-gated pipeline (dedup + contradiction flagging), and the
  sweep is budget-bounded (per-gap inside a run ceiling, skip-not-fail,
  --dry-run at $0, confirmation with an upper-bound estimate). Bounded
  autonomy deliberately: specialist-instrument routes (recon/distillr/
  primr) are deferred with their exact command printed - approval-gated
  multi-minute paid jobs must not start as a side effect of a sweep.
- Health-check now surfaces absorb/sync-time contradiction flags. The
  contradictions check merges recorded contested pairs (the contradiction
  edges that absorb and sync write when a conflicting claim arrives) with
  freshly heuristic-detected ones, deduplicated by id pair - previously
  the audit re-ran the heuristic only and the recorded flags never
  reached the action menu. Summary and the adjudicate action distinguish
  "N recorded, M new". The read path is genuinely read-only: the audit
  no longer creates belief-store directories as a side effect
  (regression-tested - same CWD-pollution class as the cost-ledger bug).
- Regenerated expert digest (`deepr expert digest NAME [--print] [--force]`).
  The Phase E regeneration invariant made executable: a compile pass over
  the canonical belief store (beliefs + typed edges + open contradictions)
  emits a browsable Markdown digest - $0, no LLM call, deterministic and
  byte-stable for an unchanged store (the "as of" stamp derives from the
  latest belief event, not the wall clock). Open contradictions are
  surfaced with both sides and the resolve-conflicts pointer, never
  smoothed; contested beliefs are flagged inline. The CLI refuses to
  overwrite a digest that lost its derived-view marker (possible
  hand-edit) unless --force - a stale or edited artifact can never
  silently become canonical knowledge.
- explain_belief - the introspection query (TKG step 4, third temporal
  tool). `deepr expert why NAME BELIEF` and MCP `deepr_explain_belief`
  (tool 26): resolves a belief by id or claim text (query-coverage match
  with prefix tolerance), then returns evidence roots (provenance), the
  confidence trajectory from the append-only event log, supporting/
  derived-from chains walked depth-bounded and cycle-safe over the typed
  belief graph, and open contradictions with status. Read-side, cost-$0,
  SENSITIVE-tier in the MCP allowlist like the other perspective queries.
  Live-validated day one: the original symmetric text matcher rejected
  "dynamic tool discovery" against the exact belief describing it
  (short query vs long claim); rescoring by query coverage fixed it.

## [2.13.3] - 2026-06-11

### Added
- **Belief event log (TKG step 1).** Every belief change (created/updated/
  revised/archived/contested/merged) appends to `events.jsonl` - the
  cost-ledger pattern applied to knowledge. Written at change time (not
  deferred to save), so events survive mid-operation failures.
  `what_changed` reads the log when present and is exact with no
  truncation caveat (proven: a 120-belief delta returns complete past the
  old 100-record window); legacy stores keep the honest truncation
  report. Design: docs/design/temporal-knowledge-graph.md.
- **Typed belief-graph edges (TKG step 2).** `Edge(src, dst, type,
  provenance[], created_at)` with supports/contradicts/enables/
  derived_from; `contradicts` is symmetric (A-B == B-A); re-asserting a
  relationship accumulates provenance instead of duplicating. Legacy
  `contradictions_with` lists migrate idempotently on first load with the
  legacy field mirrored for one release, so every existing reader keeps
  working. Conflict detection and contested-absorb route through
  `add_edge`; same-polarity related beliefs (0.35-0.7 similarity band)
  now get `supports` edges - the structure `explain_belief` will walk.
- **First-party integrations re-verified + live drift check.** All three
  sibling integrations had silently drifted since v2.12: primr v1.29.3
  removed `batch_analyze`/`quick_lookup` (still referenced in profile,
  skill pack, and prompt), distillr v0.11.1 renamed its entire verb
  surface (the one auto-approved tool, `query_library`, no longer
  existed - the free corpus path was dead), recon v2.1.18 added five
  tools. Profiles, skill packs, prompts, and tests rebuilt on the real
  surfaces (recon 22/22, distillr 21/21, primr 17/17 declared-vs-live).
  New `scripts/validate_integrations.py`: $0 `tools/list` handshake
  through Deepr's own MCP client diffing reality against the profiles -
  its first run corrected two errors in the static fix itself.
- **Budget gate hardening (no-surprise-bills audit).** Three holes found
  and closed: (1) `-y` short-circuited the monthly budget gate entirely -
  every headless run could spend past the budget unchecked; `-y` now
  skips confirmation, never the gate, and refuses when the gate wants a
  human. (2) Cautious mode's under-$1 auto-approve had no cumulative cap
  (a loop of $0.99 jobs was unbounded); now capped at $25/month of
  ledger-verified spend. (3) The web submit gate failed open when the
  limit check itself errored; now fail-closed. Budget decisions read
  max(side counter, canonical ledger) so no entry point can make the
  month look cheaper than it was.
- **Saturation-aware eval rankings + $0 regeneration.** The benchmark's
  routing-preference generation used plain max() over per-task scores; on
  tasks where the question set has no headroom (gpt-4.1-nano scored a
  mean 1.00 over 896 reasoning evals), the "best" pick degenerated to
  iteration order - which is how auto mode came to route reasoning
  queries to a nano model. Tasks are now flagged saturated (top-2 tie
  within 0.02, or top score >= 0.99) and their best_quality pick is
  chosen by discriminative quality (mean score across tasks that DO
  discriminate) among models above a competence floor. New
  `--regenerate-rankings` rebuilds routing_preferences.json from stored
  benchmark data with zero API calls - the entire fix was validated and
  deployed without spending anything (10 of 14 task types were
  saturated; reasoning now elects gpt-5.2). A paid eval run is only
  needed when a new model must be benchmarked (`--new-models` with the
  $1 preflight cap) or when the harder question set ships (eval
  methodology v2, planned v2.15).

### Fixed
- **Six live findings from an external agent driving deepr headless**
  (2026-06-11) - the most valuable bug report class, all front-door issues:
  - `deepr research` now accepts `--budget/-b` (alias of `--limit/-l`) -
    the README documented a flag the CLI did not have.
  - Windows cp1252 consoles no longer crash on CLI output containing
    arrows/box characters (`deepr research -h` raised UnicodeEncodeError):
    stdout/stderr are reconfigured to UTF-8 with replacement at entry.
    Also closes the earlier `costs timeline` encoding finding.
  - `--auto` no longer pairs the web-search tool with models that reject
    it (gpt-4.1-nano took the tool, errored, and burned every fallback):
    nano-tier models drop the tool up front, and the submit loop retries
    the same model once without the tool on a tool-rejection error.
  - A run that fails on every provider now marks its queue job FAILED -
    previously it exited with the job still QUEUED, leaving a zombie the
    user had to cancel manually.
  - An explicit `-m` is never overridden by routing: previously
    `-m o4-mini-deep-research` without `--provider` was silently replaced
    by the pinned default (which also made the cheaper deep-research
    model unselectable). The provider is now inferred from the registry
    for explicitly requested models.
  - The o3-deep-research deprecation warning cited a retirement date
    (2026-03-26) that passed without the model retiring (alias
    live-verified still served). The entry is informational now, and
    date-less entries no longer warn on every run.
- **Deep-research pricing drift** (live pricing page, 2026-06-11):
  o3-deep-research corrected $11/$44 -> $10/$40 per MTok;
  o4-mini-deep-research corrected $1.10/$4.40 (the plain o4-mini rate,
  copied by mistake) -> $2/$8. Registry remains the single pricing
  source, so estimates and settlement both pick up the corrections.
  Full four-provider sweep verified everything else current (gpt-5.5/
  5.5-pro, grok-4.3/4.20, gemini-3.5-flash, claude-opus-4-8/fable-5
  all present and correctly priced; gemini-2.0-flash retired upstream
  June 1 and was already absent).

## [2.13.2] - 2026-06-11

### Added
- **Expert sync - scheduled freshness with delta-only integration.** The
  flagship loop-closer: `deepr expert subscribe NAME TOPIC [--every Nd]
  [--budget X]` registers what an expert stays current on;
  `deepr expert sync NAME` researches only due subscriptions with a
  delta-only freshness prompt ("what changed since <last sync>; if nothing
  meaningful, say exactly so"), absorbs through the verification-gated
  pipeline (dedup + contradiction-as-signal), and reports the perspective
  delta via `what_changed`. Per-topic budgets inside a run ceiling,
  skip-not-fail exhaustion, `--dry-run` at $0; "no significant changes"
  answers skip the paid extraction. Idempotent per cadence window, so cron
  or host-platform schedulers can run it daily and only due topics spend.
- **Simple default surface** (top finding of a six-persona cold review,
  hit by 5 of 6 reviewers): `deepr --help` opens with a worked
  three-command quickstart and lists five core commands (research, expert,
  costs, doctor, web) before an Advanced section; deprecated commands and
  single-letter aliases hidden but functional. `.env.example` reduced
  179 -> 19 lines (one key + budget ceilings; full template in
  `.env.example.full`). README gained a plain-language one-liner,
  budget-is-a-ceiling note, and a who-this-is-for block.
- **Durable learner jobs.** Every `expert learn` research submission is
  recorded in the local queue (`learn-<id>`, PROCESSING with the provider
  job id) so interrupted runs are recoverable via `deepr status`/`list`;
  terminal states and actual cost sync back. The completion summary now
  credits completed/failed topics (was always "Completed: 0 topics").
- **Frontend lint actually runs.** No ESLint config existed, so
  `npm run lint` had failed on every invocation since the frontend was
  built. Added `.eslintrc.cjs` (vite react-ts baseline) and fixed every
  violation it surfaced.

### Fixed
- **Web cost endpoints read the canonical ledger.** `/api/cost/summary`,
  `/api/cost/trends`, and `/api/cost/breakdown` computed spend from queue
  job costs - a third parallel money source that missed every CLI / MCP /
  expert spend path (dashboard showed "TODAY $0.00" against real ledger
  spend). All three now read the append-only cost ledger fresh per
  request; the daily-limit preflight counts cross-process spend.
- **Expert stats tell the truth in the web UI.** List/detail endpoints
  read legacy profile fields, showing "2 docs, 0 findings" for an expert
  with 7 documents and 24 beliefs; the Claims tab omitted the belief
  store entirely, so absorbed beliefs (the expert's actual perspective)
  never appeared. Counts now come from the profile document counter, the
  canonical belief store, and the manifest gap backlog; Claims merges
  belief-store beliefs with confidence decay and contradiction edges.
- **Unaffordable learn budgets refused at $0.** `generate_curriculum`
  raises before its first paid call when the budget cannot fund even the
  cheapest plan (previously spent ~$0.10-0.30 on generation/discovery and
  then skipped every topic).
- **research-studio file upload crash.** A refactor left dangling
  `finalFiles` references; the frontend had not type-checked since.

### Changed
- **README screenshots regenerated from live data** (all 11 assets,
  1440x900) via the improved `screenshot-qa.mjs` (dynamic job/expert
  selection from the API, `--viewport` mode); the capture run doubles as
  a web-layer regression check - it is what surfaced the cost and expert
  API bugs above.
- **Frontend dependencies updated with real verification** (CI does not
  build the frontend, so PR checks alone proved nothing):
  typescript-eslint 7.18 -> 8.61 (plugin + parser together), date-fns 4,
  immer 11, lucide-react 1.17, react-query/axios/socket.io-client/radix
  minors - lint, tsc, and production build verified locally.
- **CI actions updated**: actions/checkout v6, actions/upload-artifact v7,
  astral-sh/setup-uv v7 with `activate-environment: true` (v7 stopped
  auto-creating the venv - the bumped action fails without it).
- **Roadmap** records the six-persona panel review findings (calibration
  evidence, source-trust scoring with confidence floors, mutation audit
  log, allowlist enforcement tests) and marks the shipped items.

## [2.13.1] - 2026-06-11

### Added
- **Claude Fable 5 support.** Anthropic's new frontier tier (`claude-fable-5`,
  $10/$50 per MTok, 1M context) registered in the model registry, provider
  `SUPPORTED_MODELS`, pricing tables, and docs/MODELS.md. The registry entry is
  itself a budget guard: an unregistered model silently bills at the o4-mini
  default rate (~10x under for Fable). Opt-in only - premium price, new
  tokenizer (~30% more tokens), safety classifiers, 30-day retention.
- **Temporal perspective queries (`what-changed`, `contested`).** The first two
  tools of the TKG query surface (the autopilot wedge), shipped ahead of the
  full graph as read-side, cost-$0 layers over structures the belief store
  already persists. `deepr expert what-changed NAME --since 7d|ISO` buckets
  belief changes into added / revised / contested / archived with reasons and
  current snapshots (re-sync with an expert instead of re-reading everything);
  `deepr expert contested NAME` lists open contradiction pairs with both sides'
  claims, confidence, and provenance. CLI + MCP (`deepr_what_changed`,
  `deepr_contested`); MCP surface now 25 tools.
- **Contradiction-as-signal in `expert absorb`.** A candidate claim that
  contradicts an existing belief is no longer silently dropped: by default it
  is recorded as a *contested* belief via the new
  `BeliefStore.add_contested_belief` - contradiction edges both ways, queryable
  by health-check / `resolve-conflicts` / `contested`, never lost. The safety
  property is preserved and regression-tested: `add_contested_belief` bypasses
  similarity merging and conflict-resolution strategies entirely, so the
  existing belief is guaranteed untouched. Optional `adjudicate=True` runs
  `ConflictResolver.resolve` per conflict (advisory; verdict recorded on the
  flag, never applied). `flag_contradictions=False` restores the legacy drop.
- **`deepr costs doctor --rebuild`.** Regenerates the cost dashboard view from
  the canonical append-only ledger (the regeneration invariant applied to
  money) - repairs the ledger-vs-dashboard drift the doctor already detects.
- **`DEEPR_COST_DATA_DIR`.** Env override for the cost-state directory, honored
  by both the canonical ledger and the dashboard.

### Fixed
- **Anthropic provider sent `budget_tokens` thinking unconditionally**, which
  returns a 400 on Opus 4.7/4.8 (and Fable 5) - models the registry already
  recommended. The provider now selects thinking per model: adaptive for
  4.6+/Fable, omitted for Haiku, legacy enabled+budget for older models.
  Fable 5 safety-classifier refusals surface as a `ProviderError` instead of an
  empty billed report. Default model: `claude-opus-4-5` -> `claude-opus-4-8`.
- **Pricing single-sourcing.** `CostEstimator` delegates to the registry
  instead of its stale 4-model table, which priced every unlisted model at
  o3-deep-research rates (o3-deep-research itself was ~5x underpriced at $2/$8
  vs the registry's $11/$44). Tiered pricing (Gemini 3.x Pro >200K input: 2x
  input / 1.5x output) now applies at settlement, not just estimates, so the
  ledger records what the provider bills. Unknown-model pricing fallback logs
  a warning. `CostSession.can_proceed` enforces the $10 absolute per-operation
  ceiling previously checked only in `check_and_reserve`.
- **`load_config()`'s redacted `"***"` api_key passed through to providers.**
  ~30 CLI call sites handed the masked placeholder to `create_provider`,
  overriding every provider's env-var fallback and 401-ing at the first real
  call (caught by live validation - `expert make` was broken). The factory and
  the two direct constructors (curriculum learn loop, ContextBuilder) now treat
  `"***"`/empty as not-provided.
- **Unit tests polluted the real cost ledger.** The ledger and dashboard
  default to CWD-relative paths, so tests run from the repo root appended
  ~1,200 fabricated cost events (~$860 phantom spend) to the developer's real
  canonical ledger over the project's life. An autouse conftest fixture now
  isolates every test via `DEEPR_COST_DATA_DIR`.
- **The CI coverage gate was silently non-blocking.** pytest-cov printed
  "FAIL Required test coverage not reached" on the 3.12/3.13 jobs without
  failing the step (HEAD was green at 79.75% against an 80% gate; only the
  3.14 job propagated the failure). CI now runs an explicit
  `coverage report` gate step (reads `fail_under` from pyproject, fails
  version-independently). The CI-vs-local coverage gap was also structural:
  benchmark-rankings loaders read CWD-relative `data/benchmarks/*.json` that
  exist only on dev machines - now covered by synthetic-fixture tests.

### Changed
- **Python 3.14 promoted to a blocking CI matrix entry.** The full
  `[dev,full]` extras install and the entire suite pass on 3.14; supported
  window 3.12/3.13/3.14, all blocking.
- ruff 0.15 modernization autofixes (datetime.UTC, PEP 604 optionals) across
  51 files; generic Claude model-name mappings updated (opus -> 4-8,
  sonnet -> 4-6, new fable); retired `claude-sonnet-3-7` removed.

## [2.13.0] - 2026-06-01

### Added
- **Expert-as-guardrail (`deepr expert validate NAME CLAIM`,
  `deepr_expert_validate`).** The expert applies its existing knowledge as a
  read-only validator: PASS/WARN/FAIL verdict with confidence, reasoning,
  supporting/contradicting claims (resolved to canonical `Claim` objects with
  full citation provenance), and caveats. `--from-file -` reads the claim from
  stdin; structured JSON output makes the verdict machine-actionable for
  downstream agents that need domain validation before acting. Never mutates
  the expert. (Shipped 2026-05-27; entry added retroactively during the
  roadmap/changelog reconciliation.)
- **Per-expert SKILL.md export (`deepr expert export-skill NAME`).** Packages a
  single expert as an installable agentskills.io skill for any compatible host
  (Claude Code, Codex CLI, Gemini CLI, VS Code Copilot, Cursor, OpenClaw): the
  generated SKILL.md triggers on the expert's domain and instructs the host to
  consult exactly this expert through Deepr's MCP tools. Packages a pointer
  (calls routed over MCP at run time), not a copy of the knowledge. Builds on
  the generic `SkillPackager`; CLI-only (`--print` to preview, `-o` for output
  dir). This is the distribution play - one export reaches every major host.
- **Gap-to-tool router (`deepr expert route-gaps NAME`, `deepr_route_gaps`).**
  Read-only, cost-$0 dynamic tool selection: maps each open gap to the best
  instrument - recon (infrastructure), distillr (academic), primr (strategic),
  or general research (default) - by keyword signal, flags which instruments are
  installed (`shutil.which`), estimates cost, and gives a rationale. Advisory:
  it recommends, it does not fill. Falls back to general research when the
  specialist is not installed.
- **Reflection loop (`deepr expert reflect NAME REPORT_ID`, `deepr_reflect`).**
  Self-evaluates a research report against its question on four dimensions -
  grounding, completeness, calibration, directness - and returns a verdict
  (accept / revise / re_research) with concrete issues and follow-up queries.
  The model scores; the verdict is computed deterministically from thresholds.
  `--depth 0` skips, `1` single pass, `2+` rigorous. A natural pre-step to
  `expert absorb`. MCP surface now 23 tools.

### Fixed
- **`/why` and `/decisions` crashed** (`AttributeError`): the handlers read
  `.decision`/`.reasoning` on `DecisionRecord`, which exposes `.title`/
  `.rationale`. Reachable from both CLI (`\why`) and web (`/why`) once any
  decision was recorded.
- **Path traversal in expert-conversation GET/DELETE** (`/api/experts/<name>/
  conversations/<session_id>`): `session_id` flowed into a file path unvalidated
  (the sibling restore path was already guarded). Now rejected with 400 unless
  it matches `^[\w-]+$` - closes an arbitrary `.json` read/delete vector when
  the API runs without an API key.
- **Temporal fact-ID collision**: two facts on the same topic within the same
  wall-clock second got the same ID, overwriting one in `facts_by_id` and
  undercounting temporal stats. IDs now include microseconds.
- **`update_cost_limits` accepted booleans** (`bool` is an `int` subclass), so
  `{"per_job": true}` silently set the limit to 1.0; now rejected with 400.

### Roadmap
- Added **Phase 4c: Expert Crews** (composable, exportable expert teams) -
  composition of existing parts (council, dspy_pipeline, per-expert SKILL.md,
  absorb/reflection), scoped as `crew` (not the existing `team`), with the
  static core first and gated self-improvement last; a crew is one composable
  role (a bounded council internally), preserving the non-orchestrator stance.

## [2.12.0] - 2026-06-01

### Added
- **Expert health-check (Phase 4, knowledge maintenance loop).**
  ``deepr expert health-check NAME`` runs a read-side, cost-$0 audit of an
  expert's knowledge state - freshness, belief contradictions (free heuristic,
  no LLM), claims missing source provenance, beliefs decayed below the
  confidence threshold, the open-gap backlog, and documents ingested but never
  synthesized. Output is two-phase: findings (each with a severity) plus a
  recommended-action menu where every corrective step carries its CLI command,
  estimated cost, and the approval tier that would gate it. The audit only
  proposes; it never mutates or spends. Exposed as the ``deepr_expert_health_check``
  MCP tool (SENSITIVE: blocked in read-only, confirm in standard/extended).
- **Expert absorb (Phase 4, output-to-knowledge feedback loop).**
  ``deepr expert absorb NAME REPORT_ID`` promotes a completed research report
  into an expert's permanent beliefs, verification-gated: one extraction call
  turns the report into atomic, report-grounded candidate claims; weak claims
  and any that contradict existing beliefs are rejected (the contradiction gate
  reuses the same free heuristic as health-check); survivors are integrated via
  ``BeliefStore.add_belief`` (deduped) with the report id as provenance.
  ``--dry-run`` previews without writing. Exposed as the ``deepr_expert_absorb``
  MCP tool (WRITE: mutating + paid, gated accordingly). MCP surface now 21 tools.
- **Native Distillr integration (first-party instrument, Phase 2b #2).** When
  the ``distill-mcp`` binary is on ``PATH`` (``pip install distillr``), Deepr
  auto-discovers and mounts the distillr MCP server with no user
  configuration, alongside recon. Built-in skill (``deepr/skills/distillr/``)
  exposes ``query_library`` (free corpus search), ``discover``,
  ``ingest_papers`` / ``ingest_youtube`` / ``ingest_sites``, and ``refresh``
  (delta re-ingest, the freshness engine behind "stay current").
- **Corpus absorption.** ``KnowledgeAbsorber.categorize_distillr_response``
  parses distillr's ingestion/query output into academic findings that cite
  the corpus synthesis artifact for provenance, integrating only the first
  non-empty result set to avoid double counting.
- **Budget-capped, approval-gated ingestion.** Unlike free recon, the distillr
  profile carries a per-call ``budget_limit`` (default $2) enforced by
  ``BudgetPropagator``; only the free ``query_library`` auto-approves, and
  ``progress: true`` reuses the existing MCP ``ProgressNotifier`` for long runs.
- **Native Primr integration (first-party instrument, Phase 2b #3).** When the
  ``primr-mcp`` binary is on ``PATH`` (``pip install primr``), Deepr
  auto-discovers and mounts the primr MCP server. Built-in skill
  (``deepr/skills/primr/``) exposes ``estimate_run`` (free pre-flight),
  ``quick_lookup`` (fast recon+scrape context), ``research_company``,
  ``generate_strategy``, ``batch_analyze``, and ``check_jobs``. Primr is the
  heaviest instrument (35-50 min, paid), so every cost-incurring tool is
  approval-gated, the per-call ``budget_limit`` is $5, the timeout is 60m, and
  long runs stream progress and resume via the existing task-durability layer.
- **Multi-category company absorption.**
  ``KnowledgeAbsorber.categorize_primr_response`` is the first parser to emit
  across categories: the recon pre-flight becomes infrastructure facts (higher
  confidence) while the brief, hiring signals, and strategic initiatives become
  strategic knowledge, each citing the report artifact for provenance.
  This completes Phase 2b (recon + distillr + primr all integrated).

- **Engineering standards foundation (Phase E).** New continuous
  code-quality track in the roadmap with firm, blocking gate targets. This
  release lands the foundation:
  - **Python baseline raised to 3.12** (``requires-python >=3.12``); CI matrix
    now 3.12 / 3.13 (blocking) + 3.14 (non-blocking until optional-dep wheels
    are confirmed). 3.9/3.10 (EOL / test-collection failures) and 3.11
    (supported only to Oct 2027) dropped; a 3.12 floor holds security coverage
    to Oct 2028. ``ruff target-version`` is ``py312``.
  - **``uv`` adopted as the canonical toolchain**: ``uv.lock`` and
    ``.python-version`` committed for reproducible dev/CI/container
    environments; CI installs via ``uv pip install``. setuptools remains the
    build backend so ``pip install`` keeps working downstream.
  - **Syntax modernized to the 3.12 baseline** via Ruff autofix: PEP 604
    unions (``X | None``), ``datetime.UTC``, exception/import aliases
    (~1.6k mechanical, test-verified changes). ``ruff target-version`` is now
    ``py312``.
  - **mypy** wired into CI as a non-blocking baseline (``[tool.mypy]`` config
    added; baseline 314 errors / 76 files), ratcheting toward a blocking
    ``--strict`` gate. **Strict islands shipped:** ``deepr/core`` (44 kernel
    errors) and ``deepr/providers`` (82 errors across all adapters - including
    realigning grok's vector-store stubs to the base provider contract) are now
    ``mypy --strict``-clean and enforced by a **blocking**
    ``mypy --strict deepr/core deepr/providers deepr/mcp`` CI step. ``deepr/mcp``
    was driven strict-clean and **flipped into the blocking gate this release**
    (the third strict island); the migration also fixed a latent bug where the
    expert-info MCP tools used dict-subscript access on ``ExpertProfile`` objects.
  - **pip-audit** wired into CI and already **blocking**: the baseline it
    surfaced was cleared immediately (see Security), so a new known
    vulnerability now fails the build.
  - **Dependabot** enabled (pip + github-actions + npm, weekly).
  - **Branch coverage** enabled (stricter than line coverage): the gate is now
    ``fail_under = 78`` over branch coverage (was 80 line), ratcheting toward 95.
  - **C901 complexity cap** (max-complexity 10) surfaced as an advisory CI
    signal alongside the S-rules; 134 over-cap functions tracked for refactor.
  - **Mutation testing** (mutmut) wired as a scheduled / on-demand non-blocking
    workflow over the kernel (budget, cost ledger, cost safety), with config in
    ``[tool.mutmut]``.
  - **SBOM** (hash-pinned dependency bill of materials via ``uv export``)
    published as a CI build artifact.
  - **Python floor raised again to 3.12** (from the 3.11 set earlier this
    cycle): 3.11 is supported only to Oct 2027; a 3.12 floor holds security
    coverage to Oct 2028. ``ruff target-version = "py312"``, CI matrix 3.12/3.13
    + 3.14 (non-blocking), Dockerfile base ``python:3.12-slim``.

### Security
- **flask-cors bumped 4.x -> 6.x**, clearing CVE-2024-6839, CVE-2024-6844, and
  CVE-2024-6866 (all fixed in 6.0.0). The old ``<5.0.0`` pin held the project
  on the vulnerable 4.0.2; the new pip-audit CI gate caught it on its first
  run. Deepr's usage (``CORS(app, origins=...)``) is unchanged across the bump.

### Changed
- ``ConfigLoader.load()`` first-party auto-discovery generalized from
  recon-only to a table (recon, distillr, primr); user-defined profiles still
  take precedence over any auto-discovered one of the same name.
- ``scripts/check_docs_consistency.py`` (CI) now also guards the built-in
  skill count against ``deepr/skills/``.

### Fixed
- **Runaway knowledge-graph edge growth (multi-GB `edges.json`).**
  `EdgeBuilder.build_edges` created a co-occurrence edge for every pair of
  concepts in a section (O(C^2)), and the concept extractor emits a concept for
  every 2-5 word n-gram, so a single large section generated millions of edges;
  with `min_pmi=0.0` nothing was pruned. One expert's `edges.json` reached
  26 GB (51k concepts). The builder now pairs only the top
  `max_concepts_per_section` (default 40) concepts - headings/key-phrases first
  - and `KnowledgeGraph` enforces a hard `max_edges` safety cap (default 1M)
  that drops further new edges with a one-time warning while still merging
  existing ones. Re-index affected experts to rebuild a healthy graph.
- Stale recon **integration** tests (not run by CI, which executes only
  ``tests/unit/``) updated to the shipped ``RECON_PROFILE_TEMPLATE`` tool
  names and modern ``asyncio.run`` (the deprecated ``get_event_loop`` form
  raised on Python 3.11+). Count-based config-loader unit tests are now
  isolated from host-installed first-party binaries.
- **``expert learn --resume`` crashed** - ``do_resume()`` built
  ``LearningTopic`` without the required ``description``/``priority`` fields and
  ``LearningCurriculum`` without ``generated_at``, a guaranteed ``TypeError``
  whenever resume ran. All required fields are now passed.
- **``expert refresh`` crashed on a never-refreshed expert** - the stats display
  called ``.strftime()`` on ``last_knowledge_refresh`` (``datetime | None``)
  unconditionally. Guarded; shows "never" when unset.
- **``expert absorb`` crashed on malformed model output** - an extraction
  response of ``{"claims": null}`` (or a non-list value) hit ``None[:n]``.
  Non-list ``claims`` now degrades to zero candidates.
- **Date-dependent test flake** - ``test_reset_if_needed_daily`` set
  ``last_reset`` to "yesterday", so on the 1st of any month the monthly bucket
  also reset (correct production behaviour), failing CI on those dates. Pinned
  to a mocked mid-month ``now``.
- Replaced the remaining deprecated ``datetime.utcnow()`` calls across the test
  suite with ``datetime.now(UTC)`` (production code was already clean).

---

## [2.11.0] - 2026-05-27

First-party native integration of Recon, the passive domain intelligence
tool, plus a follow-on hardening / version-centralization sweep.

### Added
- **Native Recon integration (first-party instrument).** When the
  ``recon`` binary is on ``PATH`` (``pip install recon-tool``), Deepr now
  auto-discovers and mounts the recon MCP server with no user
  configuration. Built-in skill (``deepr/skills/recon/``) covers the real
  shipped tool surface: ``lookup_tenant``, ``analyze_posture``,
  ``assess_exposure``, ``find_hardening_gaps``, ``chain_lookup``,
  ``get_posteriors``, ``explain_dag``.
- **Autonomous recon probe in expert chat.** When an expert is in
  ``agentic`` mode and the user message contains a domain, Deepr fires
  ``lookup_tenant`` at cost $0 and surfaces high-confidence
  infrastructure findings (services, related domains, tenant/provider,
  email-security posture) directly into the system prompt for that turn.
  ``KnowledgeAbsorber.categorize_recon_response`` is a specialized parser
  that emits >= 0.8 confidence findings from the real recon response
  shape.
- **`deepr doctor` Native Instruments check** reports whether recon is
  available and suggests ``pip install -U recon-tool`` when missing.
- **CI advisory security lint** via ``ruff check --select S`` (Bandit-
  equivalent) runs on every push with ``continue-on-error: true`` so
  findings show up in the log without retroactively gating on legacy
  ``try/except/pass`` and partial-executable-path findings.

### Changed
- **Single source of truth for version.** ``AgentCardGenerator``,
  ``MCPClient`` clientInfo, ``SkillPackager`` default, and the web
  ``/health`` endpoint now import ``deepr.__version__`` instead of
  hardcoded ``"2.10.0"`` / ``"2.9.0"`` strings (and matching tests
  updated to assert against ``DEEPR_VERSION``). This closes a recurring
  silent-drift bug class.
- **ExpertSkillWrapper gap-tool map** updated for the real recon tool
  names (``lookup_tenant``, ``analyze_posture``, ``chain_lookup``) with
  legacy ``domain_lookup`` retained as a fallback for user-defined
  skills.

### Security
- **`doc_reviewer.scan_docs` symlink/traversal hardening.** Rejects
  symlinks, uses ``validate_path`` + realpath containment, and skips
  files larger than 2 MB before any content is read.
- **`config.load_config` no longer leaks provider API keys** in its
  return dict; callers needing real keys must go through the provider
  factory or environment variables. Removes an accidental cross-context
  key disclosure path.
- **`bin/deepr-api`** documents that ``DEEPR_ALLOW_PUBLIC_BIND=1`` is
  acknowledgement of a real risk (data disclosure + provider-spend
  abuse), not a routine convenience flag.
- **Documentation hardening** in ``deepr/api/app.py`` and
  ``deepr/web/app.py`` makes the local-dev-only nature of the
  unauthenticated default explicit.

### Fixed
- **MCP / async exception handling.** ``MCPClientProxy.call_tool`` and
  ``SkillExecutor`` now re-raise ``CancelledError``, ``SystemExit``, and
  ``KeyboardInterrupt`` instead of swallowing them into a generic
  ``{"error": ...}``. Remaining broad ``except`` blocks now carry an
  intent-explaining comment.
- **`assert` replaced with explicit logging + safe return** in
  ``StdioTransport._read_loop``, ``LiveShimmerStatus._run``, and
  ``ExpertSkillWrapper.execute`` (asserts are stripped under ``python
  -O``; the previous code could fall off the end with ``None`` in
  pathological cases).
- **`AzureFoundryProvider.__del__`** clean-up swallow is now explicitly
  documented as intentional (must not raise during interpreter
  shutdown).
- **`ConfigLoader.load`** no longer raises ``FileNotFoundError`` when
  the integrations config is absent; it returns auto-discovered profiles
  (recon if installed) and an empty list otherwise.

### Tests
- Patch ``discover_recon_profile`` in two config-loader tests so they
  do not depend on whether the ``recon`` binary happens to be installed
  on the dev / CI machine.
- ``test_a2a_integration`` and ``test_packager`` now assert against
  ``DEEPR_VERSION`` so future version bumps don't break tests.
- Replace ``assert False`` with ``raise AssertionError`` (ruff B011).
- Remove unused locals across A2A / MCP / services coverage tests.
- ``tests/integration/test_grok_search.py`` moved to
  ``grok_search_demo.py`` - it was a manual demo, not a pytest test, so
  it no longer triggers collection errors when ``xai_sdk`` is missing.

### Roadmap
- Phase 2b first-party instrument sequencing made explicit:
  Recon (1) -> Distillr (2) -> Primr (3). Recon is now the pilot
  delivered.

---

## [2.10.3] - 2026-05-17

Five-round bug-hunt sweep covering cost/budget, async/concurrency, storage
durability, provider correctness, auth, skill subsystem, CLI flag validation,
deploy templates, MCP client + transports, frontend accessibility, and
documentation accuracy. ~360 fixes across ~190 files. All 4,341+ unit tests
pass. Coverage threshold raised from 60% to 75%.

### Security
- **Skill executor RCE closed.** Skill ``module``/``function`` fields are
  now resolved with ``importlib.util.spec_from_file_location`` against a
  path inside the skill directory; ``module: os, function: system`` is
  refused. Function names are validated as public identifiers; dunders
  blocked. ``sys.path`` is never modified.
- **Skill MCP subprocess allowlist.** ``server_command`` must be on a
  per-skill allowlist (built-ins only by default; opt in via
  ``DEEPR_SKILL_ALLOW_MCP_COMMANDS=*``). MCP subprocesses no longer
  inherit the full host environment - only ``server.env`` keys, plus a
  minimal ``PATH``/``HOME`` set.
- **Skill path traversal closed.** ``prompt_file`` rejects absolute paths
  and any path that resolves outside the skill directory.
  ``SkillManager(expert_name=...)`` sanitises the expert name through
  ``deepr.utils.security.sanitize_name``.
- **Webhook server fail-closed.** Refuses anonymous POSTs when
  ``DEEPR_WEBHOOK_SECRET`` is unset; refuses to start on a non-loopback
  bind without a secret. Adds a 1 MiB body cap.
- **A2A server bearer-auth gate.** ``POST /tasks`` and
  ``POST /tasks/{id}/cancel`` now require ``DEEPR_A2A_TOKEN`` when set.
  Refuses non-loopback bind without a token unless
  ``DEEPR_A2A_ALLOW_PUBLIC=1``. 1 MiB body cap, header / body read
  timeouts.
- **MCP HTTP transport bearer over plain HTTP** now emits a warning at
  subscribe time when the URL is non-loopback. Body cap set explicitly.
- **`deepr templates show/delete/use`** sanitise the template name  - 
  ``../`` no longer reads or deletes arbitrary files.
- **MCP confirmation gate** strips the ``_approved`` kwarg before
  dispatch so handlers without that parameter no longer crash with
  ``TypeError``.
- **Shared cloud `security.py`** uses ``hmac.compare_digest`` with
  ``TypeError`` catch (was raw ``==``).
- **`InstructionSigner` convenience helpers** now share a singleton so
  ``sign_instruction`` / ``verify_instruction`` actually round-trip when
  ``DEEPR_SIGNING_KEY`` is unset.
- **Azure**: legacy unauthenticated ``deploy/azure/function_app/``
  directory removed; cancel_job uses Cosmos ETag (``If-Match``) with
  retry loop; documents now write a top-level ``job_id`` field matching
  the container's ``/job_id`` partition key.
- **GCP**: cancel_job wrapped in a Firestore transactional decorator.

### Cost correctness
- **`CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION`** + ``ABSOLUTE_MAX_DAILY``
  + ``ABSOLUTE_MAX_MONTHLY`` class attributes added (round-2 patch fixed
  a swallowed AttributeError; this exposes the constants the MCP server
  + CLI reference).
- **Reservation pattern.** ``cost_safety.check_and_reserve()`` returns
  a reservation_id; ``record_cost(reservation_id=...)`` settles the
  reservation. N-way parallel fan-out (council, task planner, batch
  executor) can no longer over-commit against the daily cap.
- **`services/research_api.py`** ``cost_limit`` semantics fixed: when
  the model's estimate exceeds the caller's cap we now reject upfront
  instead of treating the cap as the spend.
- **`services/batch_executor.py`** + **`services/research_api.py`** now
  call ``record_cost`` after successful submission so daily / monthly
  spend doesn't drift below reality.
- **`services/batch_auto.py`** ``execute_batch`` enforces a
  ``cost_safety.check_operation`` gate against the total routing-cost
  estimate (previously a 100-query batch could spend $100+ unchecked).
- **`experts/chat.py`** ``_deep_research`` uses ``get_cost_estimate``
  from the registry (was hardcoded ``$0.20`` for a ``$2.00`` model).
  Multi-round tool loops re-check ``cost_session.can_proceed`` between
  rounds. ``_quick_lookup`` gets a pre-flight check and registry-driven
  pricing; cached-token discount honoured.
- **`mcp/client/pool.py`** clamps server-reported cost so a malicious
  server returning ``cost=0`` cannot bypass spend tracking and ``-1``
  cannot credit budget back.
- **`web/app.py`** ``POST /api/jobs`` enforces ``CostController.check_cost_limit``;
  ``/api/experts/council`` clamps caller budget against
  ``ABSOLUTE_MAX_PER_OPERATION``; ``/api/experts/chat`` clamps against
  daily remaining.
- **`core/costs.py`** ``record_cost`` now calls ``reset_if_needed()``
  first so a job recorded just after UTC midnight lands in the new
  day's bucket.

### Correctness
- **`agents/orchestrator.py`** no longer drops subtasks beyond
  ``len(workers)``; workers are picked round-robin via
  ``idx % len(workers)``. Output keys sort numerically so ``worker-10``
  lands after ``worker-2``.
- **`observability/routing_log.py`** ``get_events`` returns the LAST N
  rows, not the FIRST N - every analytics query in this module was
  silently analysing the oldest history slice.
- **`observability/circuit_breaker.py`** OPEN → HALF_OPEN transition
  now holds ``self._lock`` so concurrent callers can't both fire a
  probe.
- **`observability/traces.py`** ``TraceContext.get_current`` uses a
  ``contextvars.ContextVar`` instead of ``threading.local`` so async
  coroutines on the same thread see their own context.
- **`research_agent/poller.py`** treats ``cancelled``, ``canceled``,
  ``expired`` as terminal; adds exponential backoff (capped 5 min) on
  persistent errors. ``queued`` is a recognised no-op.
- **`core/research.py`** ``_temporal_trackers`` is popped on
  ``cancel_job`` and ``process_completion`` so long-running orchestrators
  don't leak one entry per job.
- **`core/company_research.py`** constructor + ``submit_research`` call
  now use the real ``ResearchOrchestrator`` API. Previously every call
  crashed at init.
- **`providers/anthropic_provider.py`** for-else on the multi-turn
  tool loop now surfaces a truncation note when ``max_turns`` is hit
  without convergence; usage is accumulated across turns and ``get_status``
  returns the stored response (previously every call recorded $0).
- **`providers/registry.py`** ``get_token_pricing`` normalises Grok's
  dot/hyphen aliases (was an 80% undercharge on multi-agent); cached
  token discount applied; partial-match candidates sorted by length so
  ``flash-lite`` doesn't match ``flash``.
- **`providers/openai_provider.py`** rate-limit fallback uses
  ``dataclasses.replace`` instead of mutating the caller's request.
- **`providers/gemini_provider.py`** reads ``chunk.usage_metadata``
  for real token counts (including thinking tokens) instead of
  ``len(text)//4`` estimates.
- **`providers/azure_provider.py`** adds retries on transient errors;
  defends against ``response.model = None``.

### Durability
- **`deepr/utils/atomic_io.py`** introduced (``atomic_write_bytes``,
  ``atomic_write_text``, ``atomic_write_json``, ``append_jsonl_durable``).
  ~17 storage call sites migrated.
- **Cost ledger** appends now ``flush() + os.fsync()`` so the last
  event survives a crash.
- **`queue/local_queue.py`** runs in WAL mode; ledger event is written
  BEFORE the SQLite commit so a crash between the two can't leave a
  job marked completed without a billing row. Partial UNIQUE index on
  ``provider_job_id`` blocks double-billing on submit-retry races.
- **`mcp/state/persistence.py`** ``save_job`` is atomic via
  ``with self._conn:`` - all three INSERTs commit together.

### Async / lifecycle
- **`mcp/transport/stdio.py`** ``stop()`` drains in-flight handler
  tasks with a 5-second grace; ``_in_flight`` initialised in
  ``__init__`` rather than lazily in the read loop.
- **`mcp/transport/http.py`** ``HttpClient.subscribe()`` cancels any
  prior subscription task before creating a new one (was leaking
  zombie SSE streams). ``_handle_post`` returns a generic 500 instead
  of echoing exception text. SSE subscriber dict overwrite now signals
  the old handler to exit cleanly.
- **`mcp/client/base.py`** spawns a background ``_drain_stderr`` so
  a chatty MCP server doesn't fill the ~64 KB pipe buffer and hang.
  Reconnect backoff has full jitter. Timeout in ``_send_request``
  forces a reconnect to prevent JSON-RPC framing corruption.
- **`mcp/state/async_dispatcher.py`** waits for dependencies BEFORE
  acquiring the concurrency semaphore - fixes a deadlock on chains
  longer than ``max_concurrent``.
- **`experts/task_planner.py`** parallel ``_run_step`` coroutines
  serialise through an ``asyncio.Lock`` on the shared session;
  ``ExpertChatSession`` is no longer concurrently mutated.
- **`a2a/server.py`** writer cleanup uses ``await writer.wait_closed()``.
- **`a2a/task_manager.py`** bounded eviction of terminal tasks.
- **`mcp/security/output_verification.py`** chain head primed from DB
  on init (was breaking chains on every restart).

### CLI
- **`deepr templates`** sanitises template name via ``sanitize_name``.
- **`deepr jobs cancel`** routes by ``job.provider``, not the global
  config default.
- **`deepr interactive`** maps model names to providers correctly
  (was routing Grok / Claude to ``gemini``).
- **`--cost-limit`** accepts ``FloatRange(min=0.0)``; **``--phases``**
  accepts ``IntRange(1, 10)``; **``--perspectives``** accepts
  ``IntRange(1, 12)`` - runaway-spend bypasses closed.
- **`deepr team`** uses ``web_search_preview`` for OpenAI providers
  (was using the unknown name ``web_search``).
- **`deepr search --keyword-only`** is now respected (precedence bug
  ``not keyword_only or True`` evaluated to ``True``).
- **`deepr costs limits`** now persists daily / monthly limits to
  ``cost_data.json`` and validates ``>= 0``.

### Round 4 - auto-mode, emitter, agent budgets, frontend safety
- **`research/auto_mode.py`** fallback model selection no longer crashes
  when the configured model is missing from the registry; falls back to
  a sane default.
- **`observability/metadata_emitter.py`** per-job temporal tracker
  replaces the shared field - fixes the race where parallel jobs
  clobbered each other's elapsed-time accounting.
- **`agents/budget.py`** ``AgentBudget.check`` propagates parent
  remaining downward correctly when a worker spawns a sub-worker so
  bounded fan-out no longer over-spends its slice.
- **Frontend safety**: result-detail citation rendering no longer
  crashes on malformed URLs (``new URL`` wrapped in try/catch);
  budget sliders debounced (was firing mutations on every pixel drag);
  cost-intelligence utilisation handles zero-denominator division.

### Round 5 - cost gates, MCP stability, frontend a11y
- **LLM cost-safety gates** added to seven previously uncovered call
  sites that could otherwise drive unbounded spend on long inputs:
  ``experts/citation_validator``, ``gap_discovery``, ``conflict_resolver``,
  ``curriculum``, ``map_reduce`` (map + reduce), ``multi_pass``
  (extract/cross-ref/synthesise), ``synthesis`` (synthesize + extract),
  ``task_planner`` (decompose + synth), ``embedding_cache`` (per-doc +
  query).
- **`experts/skills/executor.py`** MCPClientProxy now drains stderr in a
  background task so a chatty MCP subprocess can't fill the pipe buffer
  and deadlock.
- **`experts/skills/definition.py`** trigger-regex compilation protected
  from ReDoS - pattern length capped at 256 chars, nested-quantifier
  backtracking patterns rejected.
- **`mcp/client/pool.py`** terminal ``ProgressEvent`` now emitted on
  tool completion (the ``_progress_notifier`` was stored but never
  triggered - subscribers saw zero events).
- **`storage/findings_store.py`** in-memory index mutations now guarded
  by ``threading.RLock``.
- **`cli/commands/research.py`** ``cancel`` merges nested
  ``asyncio.run()`` calls into a single event loop so lookup + cancel
  share the same loop.
- **Frontend a11y**: htmlFor/id pairing on settings + research-studio
  inputs; aria-label on search and slider widgets; aria-valuemin/max/now
  on cost-intelligence slider; responsive sidebar hiding
  (trace-explorer ``<lg``, expert-profile ``<md``).
- **Dead frontend code removed**: ``use-local-storage`` /
  ``use-media-query`` hooks, ``activity-feed`` /
  ``memory-indicator`` components.

### Documentation
- This file. CHANGELOG was empty for v2.10.3 (3 commits' worth of work
  had no release notes).
- ``--agentic`` flag references removed - flag doesn't exist; agentic
  is the default, ``--no-research`` disables.
- ``deploy/azure/README.md`` + ``deploy.sh`` corrected to ``functions/``
  (the ``function_app/`` directory was removed).
- MCP tool count: 16 → 18 in ``README.md`` and ``mcp/README.md``.
- Test count: 4300+ → 4341+ in ``README.md``, ``ROADMAP.md``,
  ``SECURITY.md``, ``docs/VISION.md``.
- Coverage threshold: 60% → 75% in ``CONTRIBUTING.md`` and ``ROADMAP.md``.

---

## [2.10.2] - 2026-05-13

Security and hardening patch. No breaking changes for default operation;
adds explicit opt-out flags for previously implicit unsafe behavior.

### Security
- **Web dashboard refuses unsafe Werkzeug binds.** `python -m deepr.web.app`
  now refuses to start the Werkzeug development server on any non-loopback
  host, drops `allow_unsafe_werkzeug=True`, and requires either
  `DEEPR_API_KEY` or `DEEPR_ALLOW_PUBLIC_BIND=1` to bind beyond `127.0.0.1`.
- **MCP confirmation gate enforced.** Tools that require confirmation in
  the current research mode now return `CONFIRMATION_REQUIRED` instead of
  being dispatched silently. Callers must pass `arguments._approved=true`
  or set `DEEPR_MCP_AUTO_APPROVE=1` to opt back into the legacy
  log-and-continue behavior.
- **MCP tool allowlist covers the real surface.** Registered
  `deepr_research`, `deepr_agentic_research`, `deepr_cancel_job`,
  `deepr_expert_manifest`, `deepr_rank_gaps`, `deepr_query_expert`, and
  six read-only Deepr tools with explicit categories so allowlist
  decisions reflect the actual exposed tools instead of treating each as
  "unknown".
- **Bearer-token compare handles non-ASCII headers.** Both
  `deepr/api/app.py` and `deepr/web/app.py` now catch the `TypeError`
  that `hmac.compare_digest` raises for non-ASCII `str` inputs and
  return `401 Unauthorized` instead of letting it escape into the
  generic 500 handler.
- **`POST /api/experts` validates string fields.** `description` and
  `domain` must be strings and are truncated to 1000/200 characters,
  preventing persisted objects/arrays from tripping the React Expert
  Hub error boundary across all clients.
- **`POST /api/jobs` (modular API) enforces guards before provider call.**
  Added 1 MB body cap, 50K prompt-length cap, model allowlist, and
  pre-submit `CostController.check_cost_limit()` check.
- **`/api/demo/clear` gated behind `DEEPR_DEMO=1`** plus an explicit
  `{"confirm": "DELETE_ALL_DATA"}` body. Returns 403/400 otherwise.
- **`/api/benchmarks/estimate` cannot fan out subprocesses.** Per-route
  6/min rate limit, module-level execution lock, and a 2-minute
  per-(tier, quick, no_judge) result cache so concurrent estimates
  serialize on a single Python child.
- **Portrait endpoint records cost and is rate-limited.** Cooldown +
  provider allowlist already shipped; v2.10.2 adds a 5/hour route
  limiter and writes generated portraits to the canonical cost ledger
  via `CostSafetyManager.record_cost`.
- **Citation-validation GET caches results.** Per-expert mtime-keyed
  10-minute TTL cache prevents dashboard polling from re-fanning out
  paid LLM validation batches.
- **AWS worker reads cancellation from DynamoDB.** Worker now consults
  the API's `JobsTable` instead of an S3 `metadata.json` the API never
  creates; status/cost/completion updates flow back via `UpdateItem`,
  and reports are written under `results/{job_id}/report.md` so the API
  `get_result` endpoint can serve them.
- **Grok multi-agent budget pre-flight.** `AgentBudget.check()` runs
  before each worker chat-completion call and synthesis is skipped when
  the operation budget has been exhausted.
- **Removed dead `deepr/api/routes/` submodule.** The never-imported
  modular routes (job/result/cost/config blueprints) shipped with stale
  `check_job_limit`/`to_dict()` calls and would have been an
  unauthenticated provider-spend surface if wired in.

### Changed
- **GPT-5.2 chat sessions cost at registry rates.** `ExpertChatSession`
  now computes token cost via a `_chat_token_cost(usage, model)` helper
  that pulls input/output prices from the model registry instead of
  hard-coding the legacy GPT-5 $1.25/$10 per-1M rates. GPT-5.2 sessions
  accumulate at the correct $1.75/$14 per-1M.
- **Gemini Deep Research priced from the registry.** `gemini-deep-research`
  and `deep-research` aliases now resolve to
  `deep-research-pro-preview-12-2025` ($2.50/job) in both
  `get_cost_estimate()` and `MODEL_COST_ESTIMATES`, so orchestrator and
  MCP budget guards no longer approve $1+ jobs against the $0.20
  unknown-model default.
- **Gemini 3.x Pro tiered pricing.** `_calculate_cost` applies the 2x
  multiplier for prompts above 200K input tokens; `get_cost_estimate()`
  accepts an optional `input_tokens` hint so pre-flight budget checks
  reflect the tier.
- **Consensus engine Gemini cost.** Bumped provider budget estimate to
  $0.20 (Gemini 3.1 Pro Preview base) and replaced the flat $0.05
  placeholder with token-accurate cost from `usage_metadata` including
  the tiered multiplier.
- `CostDashboard.record` and buffered cost recording now emit canonical
  ledger events.
- `DEEPR_COST_TRACKING_STRICT=1` enables fail-fast behavior when ledger
  writes fail in cost dashboard/safety paths.

### Added
- Canonical append-only cost ledger at `data/costs/cost_ledger.jsonl`
  with idempotency-key support (`deepr/observability/cost_ledger.py`).
- `deepr costs doctor` command for zero-cost tracker integrity checks
  (ledger writable + drift vs dashboard totals).
- Queue cost persistence records positive cost deltas with idempotency
  metadata to avoid duplicate attribution.
- `CostSafetyManager.record_cost` writes canonical ledger events for
  non-queue spend paths (used by the portrait endpoint).
- Rich animated ASCII startup banner with cross-platform fallbacks
  (compact/narrow terminals, legacy Windows, non-UTF output).
- Startup banner env controls: `DEEPR_BANNER_MODE=off|static|light|full`
  and `DEEPR_BANNER_DURATION=<seconds>`.

---
## [2.9.1] - 2026-02-16

### Added
- `deepr web` CLI command to start the web dashboard (replaces `python deepr/web/app.py`)
  - `--host`, `--port` / `-p`, `--debug` options
  - Graceful error if web dependencies are not installed

### Changed
- Documentation updated to use `deepr web` instead of `python deepr/web/app.py`

---

## [2.9.0] - 2026-02-16

### Added

**Agentic Expert Chat**
- Streaming expert chat over WebSocket (Socket.IO) with real-time token delivery, tool call visibility, and follow-up suggestions
- 27 slash commands organized by category (Mode, Session, Reasoning, Control, Management, Utility) with `/` prefix in web and `\` prefix in CLI
- Command registry (`deepr/experts/commands.py`) with shared parsing for CLI and web, alias resolution, and category grouping
- 4 chat modes: ASK (quick answers, KB-only tools), RESEARCH (default, all tools), ADVISE (consulting-style structured recommendations), FOCUS (always-on chain-of-thought reasoning)
- Mode switching via `/ask`, `/research`, `/advise`, `/focus` commands; mode badge displayed in chat header
- Visible reasoning: ThoughtStream callbacks pipe real-time thinking steps to frontend via `chat_thought` WebSocket events; collapsible ThinkingPanel shows planning, search, evidence, and decision steps with confidence indicators
- Context compaction: `/compact` summarizes earlier messages while preserving recent context, enabling longer sessions without token budget exhaustion; auto-suggest banner after 30+ messages or 80K+ estimated tokens
- Human-in-the-loop approval flows: `ApprovalManager` with three tiers (auto-approve, notify, confirm) based on operation cost and budget; inline confirmation dialog in chat for expensive operations
- Expert council: `/council` command queries multiple experts in parallel on cross-domain questions, synthesizes agreements and disagreements; also available as `POST /api/experts/council` REST endpoint
- Hierarchical task decomposition: `/plan` command breaks complex queries into subtasks with dependency graph, executes independent subtasks in parallel with live progress per step
- Memory commands: `/remember` pins facts to session, `/forget` removes them, `/memories` lists all; pinned memories included in system prompt
- Session management: `/clear` resets chat, `/new` starts fresh session, `/save` and `/load` for named sessions, `/export` to markdown or JSON
- Reasoning commands: `/trace` shows full reasoning chain, `/why` explains last decision, `/decisions` lists all decisions, `/thinking on/off` toggles verbose reasoning display
- Control commands: `/model` switches model, `/tools` lists available tools, `/effort` adjusts reasoning depth, `/budget` shows remaining budget, `/status` shows session stats
- Conversations API: `GET/POST /api/experts/<name>/conversations` for listing and loading past chat sessions
- Expert portrait generation: AI-generated SVG portraits based on expert domain and description, cached per expert, displayed in profile header
- Web slash command autocomplete: floating menu triggered by `/` in chat input, grouped by category, keyboard navigable
- Frontend chat components: `ThinkingPanel`, `ConfirmDialog`, `CompactBanner`, `PlanDisplay`, `MemoryIndicator`, `SlashCommandMenu`, `MessageActions`, `ToolCallBlock`

**Expert Skills System**
- Domain-specific capability packages that give experts unique tools and reasoning
- `SkillDefinition` format: `skill.yaml` manifest + `prompt.md` overlay + Python/MCP tools
- Three-tier storage: built-in (`deepr/skills/`), user global (`~/.deepr/skills/`), expert-local (`data/experts/{name}/skills/`)
- `SkillManager`: discovery across all tiers, keyword/regex trigger matching, domain-based suggestion
- `SkillExecutor`: Python tool execution via importlib, MCP bridging via JSON-RPC stdio proxy
- Progressive disclosure in expert chat: skill summaries always in system prompt, full prompt loaded only on activation
- Tool namespacing (`skill_name__tool_name`) prevents conflicts across skills
- Budget tracking per skill with cost tier estimates (free/low/medium/high)
- Profile schema migration v2→v3 adding `installed_skills` field (backward compatible)
- 4 built-in skills shipping in `deepr/skills/`:
  - `web-search-enhanced`: structured data extraction from research text
  - `code-analysis`: dependency audit + cyclomatic complexity analysis
  - `financial-data`: financial ratio calculations (P/E, P/B, debt-to-equity, ROE, margins)
  - `data-visualization`: markdown table generation + ASCII bar charts
- CLI: `deepr skill list/install/remove/create/info` command group
- CLI: `deepr expert run-skill` for direct tool execution
- Web API: `GET/POST/DELETE /api/experts/<name>/skills/<skill>`, `GET /api/skills`
- MCP: `deepr_list_skills` and `deepr_install_skill` tools
- Frontend: Skills tab (6th tab) in Expert Profile with install/remove buttons
- 124 new unit tests for skills definition, manager, and executor

**Expert Intelligence**
- Multi-provider consensus gap-filling (`--consensus` flag)
- Semantic citation validation (`SupportClass` enum, `--validate-citations` flag)
- Multi-pass gap-filling pipeline (`--deep` flag)
- Automated gap discovery via claim clustering (`deepr expert discover-gaps`)
- Conflict resolution agent with multi-provider adjudication (`deepr expert resolve-conflicts`)

### Changed
- Shared constants module (`deepr/experts/constants.py`) centralizes model names, tool identifiers, and budget fractions across council, task planner, command handlers, and WebSocket events
- `_run_in_thread()` helper in WebSocket events replaces duplicated asyncio event loop boilerplate
- Frontend: extracted reusable `SkillCard` and `EmptyState` components, reducing expert-profile.tsx bundle by 1.5KB
- Frontend: replaced 4 inline empty state patterns and 2 inline skill card renderings with shared components

### Fixed
- Removed unused imports `AppConfig` and `create_provider` in `experts.py` discover-gaps command
- Removed unused import `KnowledgeSynthesizer` and unused variable `do_validate` in `app.py` fill-gaps endpoint
- ThinkingPanel showed "Thought for " with empty duration when timestamps were identical (now shows "<1s")
- Compact toast showed "undefined messages" when backend omitted count (added fallback)
- Chat auto-scroll: `userScrolledRef` was never set to true (added `onScroll` handler)
- Duplicate React keys in active tool call list (key now includes `startedAt` timestamp)
- Chat mode was not sent to backend `startChat()` (added mode parameter to WebSocket emit)
- Unsafe `(data as any).mode` cast in chat complete handler replaced with proper typed field
- Dead `setChatInput(fu)` in follow-up handler removed (was immediately overwritten)
- Clipboard copy in message actions now has try/catch for environments where `navigator.clipboard` is unavailable
- Confirm dialog cost display uses `formatCurrency()` for consistent formatting
- Council synthesis missing newline separators between expert perspectives
- Task planner result truncation was slicing a list instead of truncating the joined string
- Removed unused `_PROVIDERS` constant in portraits module
- Removed redundant alias entries in command handlers (registry already resolves aliases)
- Moved lazy imports (`uuid`, `os`, `AsyncOpenAI`) to top level in approval and council modules

---

## [2.8.1] - 2026-02-14

### Added

**Models & Benchmarks Page**
- New web page (`/models`) with model registry browser showing all registered models grouped by provider
- Benchmark results viewer with quality rankings by tier (chat/news/research), quality bar charts, and per-task-type radar charts
- Run benchmarks from the UI with tier, quick/full, judge toggle, and budget controls
- Cost estimation (dry-run) before starting a benchmark run
- Benchmark history file selector to load and compare different runs
- Routing configuration display showing current auto-mode preferences
- Provider key status indicators (configured vs not set)
- Backend APIs: `GET /api/benchmarks`, `GET /api/benchmarks/latest`, `GET /api/benchmarks/<filename>`, `POST /api/benchmarks/start`, `POST /api/benchmarks/estimate`, `GET /api/benchmarks/status`, `GET /api/benchmarks/routing-preferences`
- Model registry API: `GET /api/registry`

**Help Page**
- New web page (`/help`) with API key setup guide linking to all provider consoles
- CLI quick reference with common commands
- Model tier explanations (research, news, chat) with strengths and cost guidance
- "When to use Deepr" section comparing against single-vendor tools
- Free tier callouts for providers that offer free API access

**Demo Data Endpoint**
- `POST /api/demo/load` backend endpoint that creates sample experts and research jobs
- "Load Demo Data" button in Settings page Environment section
- Populates the UI with sample data for exploring the dashboard without a running research pipeline

**UX Improvements**
- Cost Intelligence accuracy disclaimer banner (costs are Deepr-internal estimates, check provider billing consoles)
- Standardized error states across all 10+ pages: muted icon, "Unable to load [thing]", consistent backend-down messaging, retry buttons
- Loading skeleton on Cost Intelligence page (was showing $0 values during load)
- Expert Profile tabs overflow scroll on mobile (5 tabs: Chat, Claims, Gaps, Decisions, History)
- Overview empty state no longer references CLI commands - links to web-native budget controls instead
- Expert Hub error state copy improvement
- `deepr config set` now supports CLI UX aliases:
  - `cli.animations` -> `DEEPR_ANIMATIONS` (`off|light|full`)
  - `cli.branding` -> `DEEPR_BRANDING` (`off|on|auto`)
  - Unknown `cli.*` keys now fail with explicit validation errors

### Fixed
- Removed dead code: `api/activity.ts`, `api/traces.ts`, `components/shared/stat-card.tsx` (never imported)
- Added `p-6` padding to Help page wrapper (missing from all other pages' pattern)
- Export dropdown in Result Detail now closes on Escape key press
- "Submit Research" → "New Research" button text consistency in Results Library
- Unsafe type assertion in Expert Profile history query replaced with proper `ExpertHistoryEvent` interface
- Gemini provider import hardening:
  - provider initialization now degrades safely when `google-genai` is present but incompatible
  - clear runtime errors are retained for unavailable Gemini client operations
  - prevents unrelated command/test breakage from optional SDK import failures

**Background Job Polling + WebSocket Push**
- Flask-SocketIO initialization with `cors_allowed_origins="*"` and threading async mode
- Background poller thread that checks PROCESSING jobs every 15 seconds via provider API
- WebSocket events: `job_created` on submit, `job_completed`/`job_failed` on poller detection
- `to_dict()` method on `ResearchJob` dataclass (enum, datetime, Path serialization)
- `POST /api/jobs/cleanup-stale` endpoint to mark stuck/orphaned jobs as failed
- `socketio.run()` replaces `app.run()` for WebSocket support
- Frontend already handled all events via `use-websocket.ts` - now actually connected

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
- 300+ new tests (3100+ total)

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
