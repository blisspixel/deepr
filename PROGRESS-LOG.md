# Progress Log

Working log only. Keep the latest five cycles plus the active cycle here; older
completed milestones are summarized in `docs/CHANGELOG.md`.

## 2026-06-26 - Cycle 2 - Consult trace candidate review

- Added sanitized `deepr-consult-trace-candidates-v1` review for failed or
  low-context consult traces.
- Added `deepr expert consult-traces` as a read-only local review command. The
  JSON payload includes trace ids, question hashes/previews, failed/warning
  checks, gap candidates, and eval-case candidates, without local trace file
  paths or raw trace payloads.
- Extended `deepr eval consult` with a `$0` candidate contract case.
- Published and registered `docs/schemas/consult-trace-candidates-v1.json`.
- Validation passed: 12 focused trace-candidate tests; `ruff check src/deepr/`;
  `ruff format --check src/deepr/`; strict mypy gate for
  `core/providers/mcp`; docs consistency; file-size ratchet;
  complexity/security ratchets; full unit suite
  `6688 passed, 8 skipped`, branch coverage `82.96%`.
- Maker-checker score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.

## 2026-06-26 - Cycle 1 - Persisted consult traces

- Startup gate passed: `README.md` and `ROADMAP.md` are present and non-empty;
  no architecture-from-scratch change or HITL architecture review is required.
- Re-read the active roadmap edge, consult docs, schema conventions, and relevant
  consult/MCP/eval code. The next atomic task is the Level 5 consult trace and
  semantic quality flywheel.
- Added `deepr-consult-trace-v1` as a local append-only consult trace record.
  CLI and MCP consults now record the question, requested experts, selected
  context metadata, capacity posture, output artifact, checks run, and synthesis
  failure events.
- Extended `deepr eval consult` with a `$0` consult trace contract case.
- Published and registered `docs/schemas/consult-trace-v1.json`.
- Validation passed: 42 focused consult/schema tests; `ruff check src/deepr/`;
  `ruff format --check src/deepr/`; strict mypy gate for
  `core/providers/mcp`; docs consistency; file-size ratchet;
  complexity/security ratchets; full unit suite
  `6682 passed, 8 skipped`, branch coverage `82.97%`.
- Maker-checker score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled: none

## 2026-06-26 - Free-web retrieval hardening + repo hygiene

- Added bounded retry/backoff around DDGS so one transient keyless-search failure
  no longer starves `$0` expert maintenance.
- Kept the retry helper injectable for tests and avoided new security-ratchet
  debt.
- Removed one-off session scripts, added `QUALITY-RUBRIC.md`, updated
  `docs/CHANGELOG.md`, and committed accumulated work on a feature branch.
- Validation: focused web-search tests, ratchets, ruff, and format.
- Spend: `$0.00`.

## 2026-06-26 - Agent QOL discovery + LAN validation

- Fixed plan-quota false exhaustion by scanning the answer body never, stderr on
  successful runs, and full output only on failed runs.
- Added `deepr_capabilities`, a free versioned MCP discovery map over roster,
  tools, cost tiers, structured errors, and owned/prepaid synthesis paths.
- Validated HTTP MCP LAN access with token auth: authorized calls pass,
  unauthenticated calls are rejected.
- Filled additional project experts through plan capacity after windows reset.
- Spend: `$0.00`.

## 2026-06-25 - Multi-plan headless capacity

- Made Codex and Claude use stdin, Grok use `--prompt-file`, and Antigravity use
  transcript recovery for headless plan execution.
- Validated plan probes and fills end to end; Antigravity remains explicit-only
  and ToS gray-zone.
- Added regression coverage for delivery modes and transcript recovery.
- Spend: `$0.00`.

## 2026-06-25 - Expert-quality dogfood

- Audited live expert beliefs and fixed extraction prompt failures that produced
  source-pointer claims or model-disclaimer beliefs.
- Preserved the boundary: prompt-level model extraction owns meaning; no brittle
  lexical stripper was added.
- Raised consult auto-fan-out to 10 with a relevance floor and fixed Claude
  plan synthesis on Windows by moving prompts to stdin.
- Spend: `$0.00`.
