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
- Spend so far: `$0.00`.
