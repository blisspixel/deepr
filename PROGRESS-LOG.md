# Progress Log

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
