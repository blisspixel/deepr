# Local Working Skills

This file captures repo-specific operating lessons from autonomous work cycles.

## Capacity QOL Work

- Treat capacity planning as deterministic workflow state. It can inspect local ledgers, admissions, model availability, and command shape, but it must not make semantic quality claims beyond measured numeric floors.
- `deepr capacity next` is a read-only `$0` surface. It may suggest commands, waits, setup, probes, evals, admission, or explicit metered fallback. It must not run research, probe paid APIs, write quota observations, or spend.
- Fresh/deep local sync context is a local-capacity contract. If local capacity is blocked, the safe scheduled action is to wait or unblock local capacity, not silently fall through to metered API.
- Scheduler-facing CLI work should consume the same deterministic capacity preview object that `deepr capacity next` prints. That keeps human guidance and automation behavior aligned, and makes blocked recurring jobs an explicit wait state instead of an error or surprise spend.
- When a recurring maintenance surface has no cheap execution backend yet, do not fake readiness through the capacity preview. Return a structured wait with pending work and make the operator rerun without `--scheduled` if they intentionally want the metered path.
- Reflection follow-ups cannot be scheduled safely after the model verdict because the reflection evaluator is the first possible spend. Put `--scheduled` before evaluator construction and return pending reflection plus follow-up work.
- Free local writes still need their approval tier honored. In scheduled health-check loops, a reversible archive is $0 but confirm-gated, so scheduled mode reports `waiting_for_confirmation` unless `--yes` is explicit.
- Append-only loop-run storage records snapshots. Collapse by `run_id` to the latest snapshot before filtering by status, or stale intermediate states will look current.
- Scheduled wait/action-plan commands should include a `loop_run` object in JSON and append through the shared recorder. CLI tests should stub the recorder so command tests do not write to the real expert data directory.
- MCP state reads that expose expert goals, gaps, loop runs, or next actions are sensitive even when they cost `$0`. Register them in the allowlist as `SENSITIVE`, blocked in read-only mode and confirmation-gated in standard mode.
- Completed sync loop records should be written only after `ExpertSyncEngine.sync` returns. Skip dry runs, include budget spent and accepted changes, and add a concrete inspect action when topic outcomes fail.
- Completed gap-fill loop records should be written only after `GapFillEngine.execute` returns. Skip dry runs, derive accepted changes from absorbed plus flagged counts, and use typed stop reasons for failed, deferred, or budget-skipped outcomes.
- Completed reflection loop records should be written after `ReflectionEngine.reflect` returns and after any requested follow-up execution or human gate. Store verifier outcome and score separately from follow-up accepted-change counts.
- Completed health-check loop records should reuse the scheduled action-plan classifier so manual and scheduled audits agree on capacity, confirmation, no-work, ready-action, and critical-report states. Archive records count local archival changes as accepted changes.
- Dashboard and API loop-status views should build from `build_loop_status_rollup` instead of reimplementing counters. Keep it read-only, windowed by `limit`, and honest about metrics that are absent from the loop-run schema.
- Dashboard expert-state telemetry should count existing structured fields only: profile staleness details, manifest gap timestamps, manifest `contradicts` links, and belief contradiction edges. Do not run fresh contradiction or gap detection just to render a dashboard.
- Terminal `ExpertLoopRun` records must have status-compatible stop reasons. Completed means `verifier_passed` or `no_due_work`; failed means a typed failure; waiting means budget, capacity, or human gate; cancelled means `cancelled`.
- Loop admission is a workflow contract, not a semantic verdict. Expose the four gates explicitly, and keep a surface supervised when any gate is missing instead of implying full autonomy.
- OKF export is an interchange view. Generate it from `BeliefStore` plus the expert manifest, protect overwrites with a derived-view marker, and keep OKF import on the verified absorb path instead of trusting bundle Markdown.
- OKF import should parse concept Markdown into absorber source text, not write beliefs directly. Preserve frontmatter and links in the source text so the verifier sees provenance, then let extraction, grounding, dedup, and contradiction gates decide.
- Remote-read contracts should have one shared serializer behind every surface. Keep MCP and web handoff payloads on `build_expert_handoff`, clamp payload sizes at the boundary, and treat detailed expert state as sensitive even when the call is read-only and `$0`.
- Remote MCP exposure should be wrapped by transport-level scoped keys before server dispatch. Key mode, expert allowlists, confirmation gates, and append-only audit records are deterministic workflow controls; per-key semantic trust still belongs to verified expert outputs.
- Key-management CLIs should show a remote API secret exactly once, list only public metadata, and revoke by changing key state rather than deleting audit-relevant records.
- Remote scoped-key budgets should be enforced before dispatch from deterministic inputs: prior audited `cost_usd`, caller budget ceilings, fixed small-tool estimates, and response cost fields. Inject remaining budget only for tools that already accept a budget argument.
- Remote scoped-key rate limits should use the append-only remote audit log as the source of recent-call truth. Block before dispatch, include retry metadata, and audit the denial so repeated abuse stays visible.
- Remote HTTP serve paths should keep stdio as the default, bind HTTP to loopback by default, and refuse reachable binds unless a shared token or active scoped key is configured.
