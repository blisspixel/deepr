# Progress Log

Working log only. Keep the latest five cycles plus the active cycle here; older
completed milestones are summarized in `docs/CHANGELOG.md`.

## 2026-06-26 - Cycle 9 - README and docs clarity pass

- Reworked README into a concise front door: product framing, quick start, what
  works now, core workflows, agentic-balance guardrails, cost controls,
  supported-surface summary, and documentation links.
- Moved detailed local, plan-quota, metered API, scheduler, and cost-accounting
  operations into new `docs/CAPACITY.md`.
- Refined the ROADMAP next-order language so verifier-gated self-model updates
  are explicitly reviewable evidence-backed proposals, not autonomous
  self-mutation or authority expansion.
- Clarified the research-processing compiler boundary: deterministic code owns
  source snapshots, hashes, prompt/schema versions, commit points, and
  regenerated views; calibrated model judgment owns meaning.
- Added a costing deep dive to `docs/CAPACITY.md` from current provider docs:
  cached-token buckets, server-side tool costs, exact provider settlement,
  tier modifiers, and why cache controls wait for TTL/cache-key/pre-warm
  estimators.
- Ran a Markdown cleanup for emoji markers and AI-attribution-shaped phrases,
  plus a repository-wide literal em/en dash cleanup in tracked text files.
- Validation passed: repository-wide literal em/en dash scan; Markdown emoji
  and AI-attribution scans; `ruff check src/deepr/`; `ruff format --check
  src/deepr/`; docs consistency; file-size ratchet; complexity/security
  ratchets; strict mypy gate for `core/providers/mcp`; frontend `npm run lint`,
  `npx tsc --noEmit`, and `npx vite build`; full unit suite `6726 passed, 8
  skipped`, branch coverage `83.20%`.
- Maker-checker target score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.

## 2026-06-26 - Cycle 8 - Provider cost settlement audit

- Audited the money paths the user called out: local Ollama still reports
  `$0`, explicit plan-quota execution strips metered API-key env vars before
  subprocess launch and records quota usage separately from dollar cost, and
  API provider calls now settle from provider usage after completion.
- Added cached-input usage fields and registry pricing so OpenAI, Azure, and
  xAI cached input tokens no longer price as ordinary input or disappear from
  ledger metadata.
- Added Anthropic cache creation and cache read bucket accounting, including
  Opus 4.5 registry coverage, so cache writes and reads settle at provider
  cache rates instead of being folded into base input.
- Fixed Gemini large-context settlement to apply the published input tier to
  input and the published output tier to output.
- Updated Grok 4.20 rates and alias settlement, including cached input rates,
  so dotted provider model ids and hyphenated registry ids hit the same pricing
  record.
- Changed research submission accounting to reserve estimated cost before
  provider dispatch, refund on submit failure, and settle the append-only cost
  ledger from provider-reported usage on completion.
- Extracted registry pricing lookup logic to `registry_pricing.py`, keeping
  `registry.py` below its grandfathered file-size cap while preserving existing
  public imports.
- Updated roadmap, model docs, changelog, current-state analysis, quality
  rubric, and skills with the cost-safety lessons from the audit.
- Validation passed: 196 focused provider/core cost tests with 1 skipped;
  `ruff check src/deepr/`; `ruff format --check src/deepr/`; strict mypy gate
  for `core/providers/mcp`; docs consistency; file-size ratchet;
  complexity/security ratchets; full unit suite `6726 passed, 8 skipped`,
  branch coverage `83.20%`.
- Maker-checker score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.

## 2026-06-26 - Cycle 7 - Reviewed monitor promotion

- Ran the cycle-7 maintenance sub-goal before feature work: dependency audit
  found no known vulnerabilities, the local agentic red-team verifier blocked
  13/13 attacks at `$0`, and security/complexity ratchets stayed at baseline.
- Added `deepr-metacognitive-promotion-v1`, a preview/apply result contract for
  reviewed monitor proposal promotion.
- Added idempotent metacognition gap candidate promotion so re-running the same
  reviewed proposal does not keep bumping the gap backlog.
- Added `deepr expert promote-monitor NAME PROPOSAL_ID`, defaulting to preview
  and requiring `--apply` before writing a metacognition gap, a local eval-case
  artifact under `data/benchmarks`, or both.
- Updated monitor `gap_or_eval_candidate` proposals to recommend the exact
  promotion command with the stable proposal id.
- Published and registered `docs/schemas/metacognitive-promotion-v1.json`.
- Updated README, roadmap, expert docs, features, supported surface, schema
  docs, design note, changelog, current-state analysis, and quality rubric to
  mark reviewed gap/eval promotion as shipped while keeping self-model updates
  gated.
- Validation passed: 37 focused monitor promotion, monitor, CLI, and schema
  tests; `ruff check src/deepr/`; `ruff format --check src/deepr/`; strict
  mypy gate for `core/providers/mcp`; docs consistency; file-size ratchet;
  complexity/security ratchets; full unit suite `6718 passed, 8 skipped`,
  branch coverage `83.08%`.
- Maker-checker target score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.

## 2026-06-26 - Cycle 6 - Metacognitive monitor proposals

- Added `deepr-metacognitive-monitor-v1`, a read-only monitor artifact that
  converts self-model blockers, calibration risks, failed loop runs, capacity
  waits, and sanitized consult trace candidates into `review_required`
  proposals.
- Added `deepr expert monitor NAME` with `--json`, `--limit`,
  `--max-proposals`, and optional `--trace-path`.
- Kept the monitor non-mutating: proposals do not apply goal, strategy, gap,
  eval, prompt, tool, or skill changes.
- Added expert-specific consult trace filtering for monitor input.
- Published and registered `docs/schemas/metacognitive-monitor-v1.json`.
- Fixed Windows malformed UNC-like path normalization discovered during full
  validation, so drive-less forms such as `\\0` normalize to the current drive
  root instead of a non-absolute `WindowsPath('//0')`.
- Updated README, roadmap, expert docs, features, supported surface, schema
  docs, changelog, current-state analysis, and quality rubric to mark the
  monitor proposal artifact as shipped while keeping promotion and self-model
  updates gated.
- Validation passed: 30 focused monitor, CLI, and schema tests; focused path
  property regression tests; `ruff check src/deepr/`; `ruff format
  --check src/deepr/`; strict mypy gate for `core/providers/mcp`; docs
  consistency; file-size ratchet; complexity/security ratchets; full unit suite
  `6711 passed, 8 skipped`, branch coverage `83.02%`.
- Maker-checker target score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.

## 2026-06-26 - Cycle 5 - Sync self-model run context

- Added one shared compact self-model context builder and refactored council
  consults to use it, eliminating duplicate shaping logic.
- Added additive `ExpertLoopRun.run_context` metadata and kept `next_action`
  action-only.
- Attached bounded read-only `self_model` metadata to completed sync loop
  records, overlap-locked sync records, scheduled sync capacity waits, and sync
  capacity blocks when an expert profile exists.
- Updated loop-status and sync-capacity schemas with optional additive fields.
- Updated README, roadmap, expert docs, features, supported surface, schema
  docs, changelog, current-state analysis, and quality rubric to mark
  learning-run self-model context as shipped while keeping metacognitive
  mutation as the next gated step.
- Validation passed: 66 focused self-model, loop-run, council, and maintenance
  tests; `ruff check src/deepr/`; `ruff format --check src/deepr/`; strict mypy
  gate for `core/providers/mcp`; docs consistency; file-size ratchet;
  complexity/security ratchets; full unit suite `6702 passed, 8 skipped`,
  branch coverage `83.04%`.
- Maker-checker score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled: loop run context metadata
