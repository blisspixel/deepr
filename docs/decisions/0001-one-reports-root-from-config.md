# 0001. One reports root, sourced from config

- Status: Accepted
- Date: 2026-06-12

## Context

A completed $3.20 job rendered "No report content available" in the web UI.
Investigation found three reports roots in active use: config-driven writers
(CLI `run`, web app) saved under `data/reports`, but `ContextIndex` scanned
`./reports`, a no-arg `LocalStorage()` (used by `prep`, `team`,
`retrieve_expert_reports`) wrote to `./reports`, and `company_research` fell
back to a third root, `results`. A report written under one root was
invisible to components reading another - search, absorb, and the dashboard
could all silently miss reports.

## Decision

There is exactly one reports root, and every component resolves it the same
way: `load_config()["results_dir"]` (env `DEEPR_REPORTS_PATH`, default
`data/reports`). No component hardcodes a path or carries its own default.

## Alternatives considered

- **Pass the path explicitly everywhere.** Rejected: every call site is a
  chance to diverge again; the bug was precisely divergent defaults.
- **Pick `./reports` as canonical** (matches the old `LocalStorage`
  default). Rejected: the config and the writers already used `data/reports`;
  moving the canonical root would migrate more data than necessary.

## Consequences

- No-arg `LocalStorage()` and `ContextIndex()` now read the configured root;
  the hardcoded fallbacks are gone.
- `deepr migrate consolidate` moves any legacy `./reports` content into the
  configured root (merges dir collisions one level, never overwrites), and
  `ContextIndex` warns when it finds orphaned reports under the legacy root.
- A cross-component regression test asserts a saved report is retrievable
  through the web API, closing the original failure.
