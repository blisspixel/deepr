# Progress Log

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
- Added the first v2.18 handoff contract: `deepr_expert_handoff` plus `/api/experts/{name}/handoff`, returning the `$0`, read-only `deepr-expert-handoff-v1` payload with bounded expert state, loop status, OKF hints, and additive compatibility.
- Added the first v2.18 scoped-key and remote-audit primitive: local MCP key records with mode, expert allowlist, and budget metadata; HTTP pre-dispatch enforcement for scoped `tools/call`; and append-only remote-call audit records with hashed arguments.
- Added `deepr mcp keys create/list/revoke` so the scoped-key primitive is operable from the CLI without exposing stored hashes or secrets after creation.
- Added scoped HTTP MCP per-key budget enforcement: remote calls now sum audited key spend, block over-budget requests before dispatch, inject remaining budget into budget-aware tools when omitted, and write successful response costs back to the remote audit log.
- Added scoped HTTP MCP per-key rate limits: key records can carry a calls-per-minute ceiling, `deepr mcp keys create --rate-limit` exposes it, and over-limit calls are denied before dispatch with retry metadata and an audited denial.
- Spend so far: `$0.00`.
