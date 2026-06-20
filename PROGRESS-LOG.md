# Progress Log

## 2026-06-20 — Plan-quota auto-routing via operator admission (the fleet's "auto" made real)

- `deepr capacity admit-plan <codex|claude|opencode> --task-class <sync|absorb>` (+ `revoke-plan`): explicit, dated, safety-gated operator opt-in to auto-route maintenance onto a subscription. Stored `plan:<id>` in the shared admission store; shown separately in `deepr capacity`.
- Waterfall auto rung rewritten honestly: instead of waiting on a remaining-quota meter the CLIs don't expose, `_choose_plan_quota` auto-selects an installed + plan-authed + **admitted** + not-in-cooldown backend (`require_observed_quota=False`). Reset-aware: an `EXHAUSTED` event with a future `reset_at` blocks; once it passes the backend self-heals. API-key env still refuses the backend as plan capacity; metered stays the budget-gated last resort.
- Local-admission lookup filtered to exclude `plan:*` keys (clean separation).
- Tests rewritten for the admission model (admitted→routes, not-admitted→metered, exhausted-future→metered, exhausted-past-reset→re-routes, api-key→blocked, copilot-not-auto-routable) + admit/revoke CLI round-trip, api-key block, choice restricted to auto-routable. Waterfall 100% coverage; ruff + ratchets baseline; 319 suite green.

## 2026-06-20 — route-gaps --plan parity (gap-fill on prepaid capacity)

- `expert route-gaps --execute` gains `--local` / `--api` / `--plan <id>` / `--plan-model`: gap-fill runs research + verified extraction on owned/prepaid capacity via one client (helper `_build_gap_fill_engine`), default stays metered. Scheduled recurring fills now proceed on owned/prepaid instead of waiting; loop records the real `capacity_source`.
- All three research-bearing maintenance loop-closers (sync, absorb, route-gaps) now support `--plan`. The story holds: scheduled expert maintenance on subscriptions you already pay for, $0 at the margin, no silent metered call.
- Tests: route-gaps `--plan` happy path + loop `capacity_source` assertions; 311 cli+experts+backends green; ruff + C901/S ratchets at baseline.

## 2026-06-20 — Plan-quota fleet view + absorb parity + reset times

- `expert absorb --plan <id>`: extraction parity with sync on prepaid capacity, same safety gate. Tests + CI green.
- `deepr capacity fleet`: one read-only $0 dashboard over all 7 CLIs — installed, auth mode (metered when an API key is set), routability (auto/explicit/metered), and latest observed quota state (active/exhausted/quarantined/unobserved) with reset time. Builder `fleet.build_fleet_status`, versioned `deepr-plan-fleet-v1` payload.
- Reset times made real: `parse_reset_after_seconds` extracts a relative duration from vendor exhaustion messages ("Try again in 3h 42m", "Resets in 2h15m30s") and the chat client records `reset_at` on EXHAUSTED events; monthly pools with no countdown stay honestly unknown.
- Validation ($0): new tests for fleet (11), reset parser (5), absorb --plan (3), reset recording (1), fleet CLI (3); coverage 94.6% on plan_quota; ruff + C901/S ratchets at baseline; full suites green.

## 2026-06-20 — Plan-quota CLI execution backends (ROADMAP Phase 6)

- Shipped plan-quota CLI execution: drive vendor coding/agent CLIs as
  $0-at-margin research backends for expert maintenance, behind a deterministic
  no-surprise-bills gate. New package `src/deepr/backends/plan_quota/`:
  `cli_runner` (safe async subprocess), `safety` (auth-mode + ack gate),
  `adapters` (declarative registry of 7 CLIs from cited June-2026 specs),
  `client` (`PlanQuotaChatClient` CLI-as-chat shim serving research + verified
  extraction, plus `make_plan_quota_research_fn`, `probe_plan_quota`).
- Honesty model: codex/claude/opencode are auto-routable (free-at-margin,
  ToS-clean); kiro/grok/antigravity are explicit-`--plan`-only with printed ToS
  notes; copilot is off-by-default (metered per token since 2026-06-01). An
  API-key-authenticated CLI is refused as plan capacity.
- Waterfall: `BACKEND_PLAN_QUOTA`, extended `BackendChoice`, gated auto rung
  (off until an observed remaining-quota window exists), `choose_plan_quota_backend`
  for explicit selection.
- CLI: `deepr expert sync --plan <id> [--plan-model]` runs the whole sync on
  prepaid capacity (research + extraction via one client, no silent metered
  call); `deepr capacity probe-plan <id>` validates a backend works.
- Every call writes `quota_ledger.jsonl` (usage / terminal exhaustion) and a
  `$0` `cost_ledger.jsonl` entry with quota units, so `costs show` and anomaly
  detection see volume even at $0 marginal cost.
- Docs: design note `docs/design/plan-quota-cli-backends.md`; AGENTIC_BALANCE
  surfaces row; ROADMAP Phase 6 + Current Status; README capacity section;
  AGENTS.md capacity-honesty bullet.
- Validation ($0/local): full unit suite 6261 passed / 8 skipped; new-module
  coverage 95% (waterfall 100%); ruff check+format clean; docs-consistency OK.
- Confirmed via research: Anthropic paused the 2026-06-15 headless credit-pool
  change (claude `-p` draws the plan window again); GitHub Copilot moved to
  usage-based billing 2026-06-01 (metered).
- Open follow-ups: live remaining-quota probe to enable auto-routing; capacity
  display id join for kiro/antigravity; opencode per-run provider auth-type
  check; antigravity PTY wrapper for headless capture.

## 2026-06-20

- Refreshed release metadata and documentation for `v2.17.0`, including the
  package version, README badge, changelog release section, roadmap current
  status, supported-surface statement, and current-state analysis.
- Kept the release language honest: durable loops, OKF interchange, hosted MCP
  foundation, and published schema contracts are current; plan-quota adapters,
  live probes, adapter writes, plan-quota scheduler dispatch, auto-mode runtime
  integration, and live third-party host registration remain open.
- Fixed the pushed CI blocker from the code-health ratchet: C901 is back at the
  144 baseline by extracting new loop-run, OKF absorb, MCP HTTP dispatch,
  scoped-key, and remote-call cost branches into smaller helpers.
- Added published scheduler JSON contracts for the remaining recurring
  maintenance payloads beyond sync: scheduled gap-fill waits, scheduled
  reflection waits, scheduled health-check action plans, and scheduled
  health-check archive confirmations. Runtime payloads now include
  `schema_version`, `kind`, and additive compatibility contracts, and the
  schema registry validates those real builders.
- Added runtime MCP output-contract validation for the two published
  host-facing expert reads: `deepr_expert_handoff` and
  `deepr_expert_loop_status` now fail closed with `SCHEMA_VALIDATION_FAILED`
  if their builders drift from required `schema_version`, `kind`, or envelope
  fields before dispatch to a host agent.
- Added `deepr-a2a-task-v1` for A2A task/result envelopes and runtime
  fail-closed validation on create, status, and cancel task responses. The
  validator checks schema version, kind, lifecycle state, cost, timestamps, and
  envelope fields before any task payload leaves the A2A server.
- Resolved the high Dependabot alert for transitive `msgpack` by updating the
  lockfile to `msgpack 1.2.1`; local `pip-audit --skip-editable` now reports no
  known vulnerabilities.
- Prepared the `v2.17.1` patch release metadata so the public release can track
  the post-`v2.17.0` schema-validation work and the `msgpack` security fix.
- Started the indirect prompt-injection defense backlog. Untrusted source text
  now has a reusable prompt wrapper, fresh retrieval context and report
  absorption prompts delimit and sanitize source spans, and first-party tool
  findings sanitize embedded directives before entering expert prompt context.
- Extended indirect prompt-injection boundaries to local document review,
  campaign context summarization, completed-research review, company-intelligence
  reuse, and team-result synthesis. These paths now wrap untrusted source blocks
  before model reuse without changing the semantic verification gates.
- Prepared the `v2.17.2` patch release metadata so the public release tracks
  the completed prompt-boundary hardening slice.
- Added the first local agentic red-team metric slice: `deepr eval red-team`
  now runs `$0` prompt-boundary, tool-spoofing, data-exfiltration, jailbreak,
  and memory trust-floor probes, reports attack-success-rate, and fails if a
  built-in attack succeeds.
- Prepared the `v2.18.0` minor release metadata so the public release tracks
  the red-team metrics command and structured tool-spoof neutralization.
- Added MCP read-path hardening for derived expert handoff and loop-status
  payloads. Host-facing payload strings now sanitize directive and tool-spoof
  canaries before downstream consumption, while canonical expert state remains
  unchanged.
- Extended `deepr eval red-team` with `$0` MCP handoff and loop-status
  read-path canaries. The built-in suite now reports 13/13 blocked cases.
- Prepared the `v2.18.1` patch release metadata so the public release tracks
  the MCP read-boundary hardening slice.
- Added `deepr eval red-team --save`, which writes `$0` attack-success reports
  under `data/benchmarks/red_team_*.json` and includes `saved_to` in JSON
  output for release-to-release trend tracking.
- Prepared the `v2.19.0` release metadata so the public release tracks saved
  red-team trend artifacts.
- Spend so far: `$0.00`.

## 2026-06-19

- Read the project-owned Markdown instruction and design set, excluding vendored dependency docs under `.venv` and `node_modules`.
- Created `CURRENT-STATE-ANALYSIS.md` to capture current alignment and the immediate next slice.
- Selected the next atomic implementation target: concrete `deepr capacity next` job previews for `v2.16` capacity QOL.
- Implemented the first capacity-preview slice: `--expert`, `--report-id`, `--context-mode`, and `--scheduled` for `deepr capacity next`, with local-required wait guidance for fresh/deep sync jobs.
- Continued into scheduler integration: added `deepr expert sync --scheduled` so due recurring sync jobs consume `capacity next` guidance and wait with structured next actions instead of falling through to metered API when cheap capacity is blocked.
- Extended the scheduler contract to `deepr expert route-gaps --execute --scheduled`, returning pending routes plus a wait state instead of starting metered gap-fill research from recurring runs.
- Extended the scheduler contract to `deepr expert reflect --scheduled`, returning a wait payload before reflection evaluation or follow-up research can spend from recurring runs.
- Extended the scheduler contract to `deepr expert health-check --scheduled`, returning action-plan statuses and making scheduled archive-stale wait for explicit confirmation before local mutation.
- Started the v2.17 loop substrate with `ExpertLoopRun`, typed stop reasons, append-only per-expert loop-run storage, and read-only `deepr expert loop-status`.
- Instrumented scheduled expert wait/action-plan surfaces to append durable `ExpertLoopRun` snapshots and return `loop_run` JSON for sync, gap-fill routing, reflection follow-ups, and health-check action plans.
- Added the `deepr_expert_loop_status` MCP read tool so host agents can inspect durable loop runs, stop reasons, filters, and next actions.
- Instrumented successful `deepr expert sync` runs to append completed or failed loop-run snapshots with budget spent, capacity source, accepted changes, and failure next actions.
- Instrumented non-dry `deepr expert route-gaps --execute` runs to append gap-fill loop-run snapshots with budget spent, accepted changes, failures, human-gated deferred routes, and budget exhaustion stops.
- Instrumented `deepr expert reflect` runs to append reflection loop-run snapshots with verifier outcome, verifier score, follow-up absorption metrics, human gates, and verifier-failed stops.
- Instrumented `deepr expert health-check` and confirmed `--archive-stale` runs to append health-check loop-run snapshots with verifier outcome, action state, no-work stops, and accepted archive counts.
- Added the read-only `/api/experts/{name}/loop-status` dashboard API rollup with latest run, last sync result, waiting scheduled action, failure, capacity source, spend, acceptance, and verifier failure metrics.
- Extended the dashboard API rollup with `expert_state` telemetry for freshness, 7-day and 30-day gap velocity, top open gaps, and contested/open claim counts from manifest links and belief contradiction edges.
- Enforced the loop completion contract in `ExpertLoopRun`: terminal records require typed stop reasons, and waiting/completed/failed/cancelled records reject stop reasons that do not match their status.
- Codified the loop admission contract in `LoopAdmissionContract` and exposed `admission_contracts` through the dashboard rollup; gap-fill stays supervised until gap-closure verifier evidence exists.
- Added `deepr expert export-okf NAME PATH`, a `$0` regenerated OKF bundle over structured expert state with `index.md`, `log.md`, concept pages, citations, typed relations, gaps, contested claims, optional `llms.txt`, and marker-based overwrite protection.
- Added `deepr expert absorb-okf NAME PATH`, which parses OKF concept Markdown/frontmatter into source text and runs it through the existing verified absorb pipeline instead of trusting generated bundle text.
- Added the hosted handoff contract: `deepr_expert_handoff` plus `/api/experts/{name}/handoff`, returning the `$0`, read-only `deepr-expert-handoff-v1` payload with bounded expert state, loop status, OKF hints, and additive compatibility.
- Added the hosted scoped-key and remote-audit primitive: local MCP key records with mode, expert allowlist, and budget metadata; HTTP pre-dispatch enforcement for scoped `tools/call`; and append-only remote-call audit records with hashed arguments.
- Added `deepr mcp keys create/list/revoke` so the scoped-key primitive is operable from the CLI without exposing stored hashes or secrets after creation.
- Added scoped HTTP MCP per-key budget enforcement: remote calls now sum audited key spend, block over-budget requests before dispatch, inject remaining budget into budget-aware tools when omitted, and write successful response costs back to the remote audit log.
- Hardened scoped HTTP MCP budget coverage: metered remote tools now require deterministic estimates before dispatch, missing estimates fail closed, and `deepr_expert_validate` is advertised as low-cost instead of free.
- Added scoped HTTP MCP per-key rate limits: key records can carry a calls-per-minute ceiling, `deepr mcp keys create --rate-limit` exposes it, and over-limit calls are denied before dispatch with retry metadata and an audited denial.
- Added a global HTTP MCP concurrency cap: `deepr mcp serve --http` now defaults to 32 simultaneous POST requests, exposes `--max-concurrency`, returns 429 when full, and wires the same setting through the container and Azure templates.
- Added `deepr mcp serve --http` so the existing MCP server can run over HTTP/SSE on loopback by default, with reachable binds protected by shared-token or scoped-key authentication.
- Added `deepr mcp smoke-http`, a `$0` local/proxied endpoint smoke command for HTTP MCP health, initialize, tools/list, and free tool-search dispatch.
- Added `deploy/mcp-http.md`, documenting scoped-key setup, loopback service binding, Caddy/nginx TLS reverse proxying, smoke validation, revocation, and operational guardrails for hosted MCP.
- Published `deepr-loop-status-v1`, `deepr-okf-profile-v1`, and `docs/schemas/registry.json` with additive compatibility rules for downstream agent contracts.
- Added `deploy/mcp-http/`, a containerized hosted MCP HTTP recipe with a dedicated Dockerfile, compose service, scoped-key bootstrap, loopback-only host publishing, and `$0` smoke validation guidance.
- Added `deepr mcp audit list`, a read-only local review surface for hosted MCP remote-call audit records with key, tool, outcome, limit, and JSON filters.
- Added `deepr mcp audit summary`, a read-only aggregate view over hosted MCP remote-call audit records with counts and audited cost by key, tool, and outcome.
- Published `deepr-mcp-remote-audit-v1` under `docs/schemas/` and registered it so hosted MCP remote-call audit records have an additive validation contract.
- Added `deploy/mcp-http/azure-container-apps/`, the first hosted MCP cloud-provider template, with Azure Container Apps, Azure Files-backed `/data`, scoped-key state, HTTPS-only ingress, and remote-audit durability.
- Added `deploy/mcp-http/aws-ecs-fargate/`, the second hosted MCP cloud-provider template, with ECS Fargate, HTTPS ALB ingress, EFS-backed `/data`, scoped-key state, remote-audit durability, and the same max-concurrency guardrail.
- Added `deploy/mcp-http/gcp-cloud-run/`, the third hosted MCP cloud-provider template, with Cloud Run, Cloud Storage FUSE-backed `/data`, scoped-key state, remote-audit durability, optional public invoker binding, and single-writer defaults for object-backed key and audit files.
- Added `deepr mcp registration-manifest` plus `deepr-mcp-registration-manifest-v1`, a token-redacted hosted MCP endpoint packet with optional `$0` smoke results for remote host setup.
- Added `docs/SUPPORTED_SURFACE.md`, documenting stable, experimental, visible/read-only, planned, export, and compatibility guarantees.
- Added `deploy/mcp-http/cloudflare-worker/`, a Cloudflare Worker edge ingress recipe that requires an HTTPS MCP origin, proxies only `/mcp` paths, caps request bodies, forwards scoped-key auth headers, and keeps scoped-key enforcement, budgets, rate limits, audit logs, and provider keys on the origin side.
- Added MCP allowlist enforcement contract tests across visible registry tools, dispatcher-only tools, every `ResearchMode`, scoped-key authorization, and JSON-RPC pre-dispatch gates.
- Audited expert chat circuit-breaker/session-budget coordination: session circuit trips block before fallback provider calls, deep research preserves session-budget metadata on preflight denials, and regression tests cover the blocked response paths.
- Fixed the live-validation CLI polish item: `deepr search "query"` now dispatches to the query subcommand with options intact, and `deepr expert list` labels name and description fields for clearer roster scans.
- Published `deepr-cli-operation-result-v1` for the shared CLI `OperationResult` JSON envelope, added schema-version/kind fields to runtime output, and validated success/error payloads against the registry schema.
- Unified loop-status JSON output across CLI and MCP with the published `deepr-loop-status-v1` rollup payload, preserving MCP status and loop-type filters.
- Published `deepr-capacity-next-v1` for read-only `$0` capacity guidance, added schema-version/kind fields to `deepr capacity next --json`, and reused the same payload under scheduled sync waits.
- Published `deepr-sync-capacity-gate-v1` for read-only sync capacity wait/block payloads, including nested capacity guidance and optional loop-run records.
- Spend so far: `$0.00`.
