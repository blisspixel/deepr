# Progress Log

Working log only. Keep the latest five cycles plus the active cycle here; older
completed milestones are summarized in `docs/CHANGELOG.md`.

## 2026-06-27 - Cycle 15 - MCP consult validation harness

- Added `deepr mcp validate-consult`, a no-metered validation harness for
  external-agent expert consult. It supports offline fixture validation,
  in-process live local or explicit plan capacity, and HTTP endpoint validation.
- Published `deepr-consult-v1` and `deepr-mcp-consult-validation-v1` schemas.
  MCP `deepr_consult_experts` now advertises an output schema and JSON-object
  tool results return `structuredContent` while preserving text JSON.
- Validation checks cover schema/kind, trace linkage, collaboration metadata,
  cost ceiling, no-metered fallback posture, dissent preservation, host action
  boundary, result artifact refs, and secret redaction. They do not judge answer
  meaning.
- Updated README, ROADMAP, MCP guide, agent test guide, expert docs, feature
  docs, supported-surface docs, schema registry, changelog, current-state
  analysis, quality rubric, and skills.
- Validation so far: focused consult-validation, MCP CLI, MCP JSON-RPC, and
  schema tests `78 passed`; offline CLI validation passed at `$0`.
- Spend: `$0.00`.

## 2026-06-27 - Cycle 14 - Reviewed consult-quality scoring

- Added `deepr expert review-consult-quality`, a `$0` preview-first command for
  scoring one sanitized consult quality case from a trace candidate.
- Added `deepr-consult-quality-review-v1`, a published review artifact that
  records human or calibrated-model rubric scores, reviewer identity, failure
  labels, acceptance policy, promotion eligibility, and no-belief-write gates.
- Wired safe promotion from accepted reviews into metacognition gaps and local
  eval-case artifacts. Policy-blocked, rejected, or needs-improvement reviews
  can still be recorded but cannot promote.
- Preserved the agentic boundary: reviewer or calibrated model owns semantic
  scoring; Deepr validates shape, policy, cost, and writes only.
- Validation so far: focused consult quality, CLI, and schema tests `37 passed`;
  focused ruff checks passed.
- Spend: `$0.00`.

## 2026-06-27 - Cycle 13 - Consult semantic quality review cases

- Researched current primary guidance on multi-agent orchestration, trace-first
  improvement loops, MCP tool boundaries, and A2A task artifacts. The usable
  pattern for Deepr remains one or many experts, one bounded consult artifact,
  with deterministic gates around cost, schemas, credentials, and writes.
- Added `deepr-consult-quality-eval-case-v1`, a published `$0` review-case
  packet emitted from failed or low-context consult trace candidates. It carries
  sanitized trace refs, capacity posture, structural failure signals, rubric
  dimensions, failure labels, and an acceptance policy for human or calibrated
  model judging. It is read-only, non-verdict, and cannot write beliefs.
- Extended `deepr eval consult` to methodology v1.1 with eight cases, including
  collaboration capacity posture, dissent preservation, trace candidate shape,
  and semantic review-case boundaries. No lexical or keyword check scores answer
  meaning.
- Updated README, ROADMAP, features, supported surface, schema docs, changelog,
  current-state analysis, quality rubric, and skills so docs now say review
  cases are shipped while judged scoring and reviewed promotion remain next.
- Validation passed: focused consult eval, consult trace, CLI eval, and schema
  tests `46 passed`; full unit suite `6797 passed, 8 skipped`; `ruff check`;
  `ruff format --check`; strict mypy gate for `core/providers/mcp`; docs
  consistency; file-size ratchet; complexity/security ratchets; diff
  whitespace check; changed-file punctuation, emoji, and attribution scans; and
  Gitleaks full-history scan.
- Maker-checker score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.
## 2026-06-27 - Cycle 12 - MCP expert consult contract hardening

- Researched current multi-agent orchestration patterns from Anthropic,
  OpenAI Agents SDK, MCP, and A2A, then folded the findings into the
  expert-chat backend design note: one or many experts, one bounded artifact,
  preserved dissent, visible capacity posture, and no silent fallback.
- Clarified README, ROADMAP, MCP README, supported-surface docs, and
  `docs/MCP_AGENT_TEST_GUIDE.md` so no-metered one-expert or multi-expert
  external-agent tests use `deepr_consult_experts` with local or explicit plan
  synthesis, while `deepr_query_expert` remains labeled as legacy
  metered-capable chat until backend-neutral chat lands.
- Fixed legacy expert chat so zero-budget sessions are denied before the first
  direct model path in both normal and streaming chat. Extracted the reusable
  budget and routing-trace helpers into `experts/chat_turns.py` so the
  grandfathered `experts/chat.py` file-size ratchet stays green.
- Validation passed: focused regression tests, full unit suite `6796 passed, 8
  skipped`, `ruff check`, `ruff format --check`, strict mypy gate for
  `core/providers/mcp`, docs consistency, file-size ratchet, diff whitespace
  check, added-line punctuation and attribution scan, and Gitleaks full-history
  scan. A separate directory scan found findings only in ignored local files
  (`.venv` and `data/security`), with zero tracked or unignored files affected.
- Maker-checker score: correctness 5/5, security 5/5, performance 5/5,
  maintainability 5/5, simplicity 5/5, testability 5/5.
- Spend: `$0.00`.

## 2026-06-27 - Cycle 11 - Expert thought boundary clarification

- Clarified that externally factual claims need support checks, while original
  ideas, hypotheses, stances, proposals, and exploration agendas are first-class
  expert state.
- Updated the roadmap and agentic-balance boundary so absence from the live web
  is not treated as refutation. Novel ideas must carry origin, rationale,
  assumptions, uncertainty, review status, expected observations, and
  disconfirming signals instead of masquerading as verified external facts.
- Validation passed: docs consistency, whitespace diff check, punctuation and
  attribution scan, and Gitleaks full-history scan.
- Spend: `$0.00`.
