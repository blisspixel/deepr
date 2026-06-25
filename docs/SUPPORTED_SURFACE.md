# Supported Surface

Status: v2.20.0 current main, 2026-06-25. This document defines what users and host
agents can rely on today, what is experimental, what is planned only, and what
data remains portable if development stops.

## Support Levels

**Stable** means the surface is part of the supported contract. Changes should
be additive, backward compatible, or documented with a migration note.

**Experimental** means the surface works and is tested, but command names,
payload details, or operational guidance may still change before 3.0.

**Visible/read-only** means Deepr can inspect or model the capacity source, but
does not yet execute work through it.

**Planned** means the roadmap describes intent only. It is not shipped UX and
must not be described as usable capacity.

## Stable Today

- Core research commands: `deepr research`, `deepr check`, `deepr learn`.
- Budget ceilings, cost estimates, and the canonical append-only cost ledger.
- Provider routing and fallback when the user supplies provider keys and a
  budget ceiling.
- Local report storage under the configured reports root.
- Expert creation, chat, import/export, and profile storage.
- Portable data root through `DEEPR_DATA_DIR`, with expert and research state
  kept under that root unless a more specific path is configured.
- CLI output modes: `--json`, `--quiet`, `--verbose`, and trace flags where
  documented. The shared `OperationResult` JSON envelope is versioned as
  `deepr-cli-operation-result-v1`.
- The published schema registry under `docs/schemas/`, with additive
  compatibility inside each v1 schema.

## Experimental But Usable

- Web dashboard and dashboard APIs.
- Agentic expert chat, slash commands, councils, task planning, and approval
  flows.
- Expert skills and first-party instruments.
- MCP stdio server and MCP HTTP serve mode.
- Scoped MCP keys, per-key budgets, per-key rate limits, HTTP concurrency caps,
  HTTP smoke checks, registration manifests, and remote-call audit review.
- `deepr_expert_handoff`, `deepr_expert_loop_status`, and adjacent versioned
  handoff contracts. The MCP loop-status tool, the CLI JSON loop-status command,
  and `/api/experts/{name}/loop-status` share the `deepr-loop-status-v1` rollup
  contract. MCP handoff and loop-status outputs fail closed if the published
  schema version, kind, or required envelope fields drift before dispatch.
- A2A task envelopes for create, status, cancel, and result-bearing completed
  tasks. These use `deepr-a2a-task-v1` and fail closed if schema version, kind,
  lifecycle state, cost, timestamps, or metadata drift before dispatch.
- Scheduled expert maintenance JSON contracts for sync capacity gates, gap-fill
  waits, reflection waits, health-check action plans, and health-check archive
  confirmations. These are experimental but schema-versioned and additive.
- Durable `ExpertLoopRun` records.
- Fleet self-maintenance: `deepr fleet status` (read-only `$0` roster-health
  rollup, `deepr-fleet-status-v1`, non-zero exit on a failed latest run),
  `deepr expert sync-all` (one capacity-aware roster pass, `deepr-library-sync-v1`
  roll-up, overlap-locked, per-expert budgets, skip-not-fail), and
  `deepr fleet install-schedule` (emits host scheduler recipes; never
  auto-installs). The off-box heartbeat (`DEEPR_HEARTBEAT_URL`) is opt-in and
  best-effort.
- Pre-sync content-hash change-detection gate, the per-(expert, verb) overlap
  guard + startup jitter, budget degradation tiers + value-of-spend gate, and the
  reservation TTL sweep - deterministic spend/side-effect guards.
- Cross-vendor maker-checker grounding assurance on absorbed beliefs
  (`Belief.grounding_assurance`). `deepr expert absorb` and `deepr expert sync`
  can opt into the checker with `--check-grounding`; `--checker-plan <id>` uses
  a different plan CLI as the checker. The checker is off by default, dry runs
  do not check, and metered API checking is not automatic. Expert handoff
  payloads preserve per-claim `grounding_assurance` and include verified-claim
  counts by assurance level. The verdict is model judgment; vendor diversity and
  spend gates are deterministic routing requirements.
- OKF export and absorb paths. OKF export is a derived view; OKF absorb is an
  ingestion source that still passes through verified extraction.
- Indirect prompt-injection boundaries for fresh retrieval context, report
  absorption, first-party tool findings, local document review previews,
  campaign context summarization, completed-research review, company-intelligence
  reuse, and team-result synthesis. These delimit and sanitize untrusted source
  text before model prompts, while semantic acceptance still depends on the
  existing verification and trust-floor gates.
- Host-facing MCP expert handoff and loop-status payloads sanitize derived
  string fields before downstream host consumption. The structured expert store
  remains canonical.
- Local Ollama expert maintenance, local evals, local context evals, local
  red-team attack-success-rate metrics including MCP read-path canaries and
  saved trend artifacts, and scored local admission.
- Explicit plan-quota CLI execution for expert maintenance:
  `deepr expert sync --plan <id>`, `deepr expert absorb --plan <id>`, and
  `deepr capacity probe-plan <id>` run through deterministic auth-mode and
  no-surprise-bills guards. Codex, Claude Code, and OpenCode are eligible for
  operator admission; Kiro, Grok Build, Antigravity, and GitHub Copilot remain
  explicit-only.
- Codex quota metadata refresh: `deepr capacity refresh-quota codex` reads local
  Codex session `rate_limits` metadata and records a conservative quota-ledger
  event without running a model call.
- Hosted MCP deployment recipes, including the local container, Azure Container
  Apps template, AWS ECS Fargate template, GCP Cloud Run template, and
  Cloudflare Worker edge ingress recipe.

## Visible Or Planned Only

- Automatic routing to plan-quota CLIs remains gated until Deepr has trusted
  live remaining-quota signals for the candidate backend. Codex has the first
  metadata probe; Claude, Grok, Antigravity, and other sources remain planned or
  explicit-only. Explicit `--plan` is still the works-now path and automatic
  plan dispatch must stay opt-in and conservative.
- Multi-account capacity pools are planned after a single-account mechanism is
  complete.
- Live hosted-agent registration smoke against a real third-party platform is
  still open.
- OAuth/OIDC, team RBAC, and workspace isolation are planned team features.
- Hosted-by-Deepr SaaS, SLAs, and enterprise SSO are non-goals for this project
  shape.

## Export Guarantees

If development stops, users keep these portable artifacts:

- Markdown research reports and their adjacent metadata under the configured
  reports root.
- Expert profiles, belief stores, event logs, edge stores, gap manifests, and
  loop-run records under the configured data root.
- OKF bundles generated by `deepr expert export-okf`, including `index.md`,
  `log.md`, concept pages, citations, gaps, and contested claims.
- Published JSON Schemas under `docs/schemas/` for handoff, loop status, OKF
  profile mapping, A2A task envelopes, remote audit events, MCP registration
  manifests, capacity guidance, sync capacity gates, scheduled maintenance
  payloads, and the shared CLI operation-result envelope.
- Cost ledger JSONL and remote MCP audit JSONL records.
- Scoped MCP key metadata, excluding plaintext secrets. Created key secrets are
  shown once and cannot be recovered from stored hashes.

Generated digests, OKF bundles, reports, and registration manifests are derived
views or handoff artifacts. The structured store remains authoritative unless a
specific command explicitly says it is importing external source text through
the verified absorb path.

## Compatibility Rules

- Published v1 schemas are additive within the same schema version.
- Removing a required field, changing required semantics, or changing the kind
  of a record requires a new schema file and schema version.
- Stable commands should keep existing flags working or document a migration in
  `docs/CHANGELOG.md`.
- Experimental commands may change, but changes should preserve data safety:
  no silent spend, no silent mutation, and no secret disclosure.
- Planned capacity must stay labeled as planned or visible/read-only until the
  adapter, quota probe, budget guard, and tests are present.

## Operator Responsibilities

- Provider API keys are user-owned credentials. Deepr enforces budget ceilings,
  but users choose when to provide keys and when to allow paid tools.
- Local Ollama capacity is only as available as the local machine and admitted
  model evidence.
- Remote MCP endpoints must use HTTPS outside loopback, scoped keys per agent,
  budget ceilings, deterministic estimates for metered tools, rate limits, and
  concurrency caps, plus audit review before widening key mode.
- Edge ingress recipes must stay stateless pass-through guards. Scoped-key
  enforcement, budgets, rate limits, audit logs, and provider credentials stay
  on the Deepr origin.
- Cloud templates are deployment artifacts. Creating cloud resources can incur
  infrastructure cost even when Deepr itself makes no provider API calls.
