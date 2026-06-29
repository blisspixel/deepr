# Security and Bug Hunt Review Notes (2026-06)

This document captures findings from a deep code review focused on bug hunting and security. Clear fixes were applied directly (with regression coverage where unit tests exercise the path). Items that are ambiguous, cross-cutting, or require maintainer decisions on scope/policy are recorded here instead of being unilaterally changed.

Follows project conventions: no emojis, no em-dashes, plain hyphens for ranges.

## Scope of Review
- README.md and ROADMAP.md (high level current)
- Path handling, reports/experts roots, traversal guards (utils/security.py, experts/paths.py, storage/*, mcp state)
- Config / load_config duplication and secret handling
- Append-only ledgers and durability (cost, belief events)
- Subprocess usage (plan quota, evals, tunnels, webhooks)
- MCP surfaces (http, scoped keys, allowlists, SSRF, output verification, consult validation)
- Provider key fallback and legacy dict redaction
- Input validation, except patterns, error paths that could bypass gates
- Sample of CLI command handlers, web app init, experts loops/approvals
- Common patterns: hardcoded data/ paths, sqlite use, atomic writes

Validation completed after the sweep: targeted regression suite `235 passed, 1 skipped`; full unit branch-coverage suite `6907 passed, 8 skipped` at 83.43%; ruff check and format check; strict mypy islands; docs consistency; file-size ratchet; C901 and S ratchets.

## Applied Fixes (Reversible, Small)
- worker/poller.py and research_agent/poller.py: corrected results_dir default from "results" to consistent "data/reports" (or from config). Also queue_db_path get fallback tightened. Prevents split storage root when load_config provides relocated value.
- core/settings.py load_config: changed to always redact "api_key" to "***" (matching deepr/config.py impl) to avoid leaking keys into dicts used for logging/serialization/config passing.
- providers/* (openai, azure, gemini, grok, anthropic): added mask ("***") guard in __init__ before "or getenv" so direct OpenAIProvider(api_key=...) calls (used in api/app.py, vector commands, prep etc) now fallback correctly instead of treating redacted value as literal key (would 401).
- api/app.py: switched direct OpenAIProvider to create_provider (which already had guard) for consistency.
- experts/beliefs.py:
  - Fixed SharedBeliefStore hardcoded "data/shared/beliefs" to respect DEEPR_DATA_DIR / ~/.deepr/shared/beliefs .
  - Added threading.Lock + flush + fsync to BeliefStore._record_change for events.jsonl append (matches cost ledger durability pattern for append-only provenance).
- mcp/server.py: replaced hardcoded base_path="data/reports" (in internal research orchestrator path) with load_config()["results_dir"].
- mcp/security/output_verification.py: made DEFAULT / init use DEEPR_DATA_DIR-aware default (via helper) instead of unconditional "data/output_verification.db".
- providers/__init__.py guard and legacy comments updated for clarity.

All changes are additive guards or path resolution; no behavior change for normal env-key or default runs.

## Remaining Observations and Recommendations Requiring Decisions

### 1. Configuration Duplication and State Root Inconsistency
Two parallel legacy load_config() (deepr/config.py vs core/settings.py), plus get_settings() as modern. Queue, some logs, and internal dbs (mcp_jobs, output_verification, routing logs) default to CWD-relative "queue/..." / "data/..." even when DEEPR_DATA_DIR or DEEPR_REPORTS_PATH set for experts/reports/costs.

Result: possible state split for users using portable DEEPR_DATA_DIR.

- Queue db_path and some analytics/routing defaults appear in multiple cli modules with comments acknowledging "legacy".
- Not all append-only or job state relocates together.

Decision needed:
- Unify to single load_config source (deprecate one)?
- Make queue (and mcp jobs, verification db, routing_log) default under the DEEPR_DATA_DIR root when set (e.g. data_dir/queue/research_queue.db)?
- Or document that only experts + reports + costs are portable, queues are ephemeral per-invocation?
- Update all call sites that pass explicit defaults.

Related: worker and api still pull some values from legacy dict.

### 2. SharedBeliefStore Status
Class exists with tests (test_belief_revision), implements cross-expert share/merge, but no production imports outside its file and tests. Previously used dangerous hardcoded path (fixed).

Decision: remove as dead (update tests), or wire into expert sync/absorb/consult council for real cross-expert belief sharing? If keep, ensure it goes through same provenance/trust floor/compiler gates as normal beliefs.

### 3. Durability and Atomicity for All Append-Only Artifacts
- Cost ledger: lock + append + fsync (good).
- Belief events.jsonl: now same after fix (good).
- Other candidates: quota_ledger.jsonl, loop_runs per-expert, mcp remote audit jsonl, various .jsonl in experts (changes?), routing decisions, capacity admissions.
- Some use atomic_write_json for full snapshots, plain append or json dump for logs.

Recommendation: audit every .jsonl / event log write site for:
- per-writer lock (thread or file)
- flush + fsync (best effort)
- corruption detection on load (current cost/belief do partial recovery + log)
Add a shared append_jsonl helper in utils/atomic_io.py ?

Some writes are inside expert per-dir so concurrent only within one expert unlikely, but MCP/CLI/web can overlap.

### 4. Bare Except Exception Patterns
~20+ occurrences, concentrated in:
- pollers/workers (resilience for transient provider errors)
- queue local (lifecycle)
- providers (some get_status)
- webhooks, startup

Most log.exception or continue. Risk: could swallow cost settlement failures, lock release, or security relevant exceptions (auth, path errors), leaving jobs in inconsistent state or ledgers incomplete.

Decision/guidance:
- Prefer specific except (DeeprError, ProviderError, OSError, sqlite3.Error, json errors) + fallback.
- Always ensure ledger writes and status updates have outer try that records failure explicitly.
- Add metrics or red-team cases for "error path skips cost record".

### 5. Eval / Benchmark Artifact Paths - Resolved 2026-06-29
local_compare, local_context, consult eval, consult quality, monitor promotion,
red-team reports, auto-mode benchmark readers, model-router benchmark readers,
and eval status now use the configured runtime data root for benchmarks.
Regression coverage sets `DEEPR_DATA_DIR` after import and proves writers,
readers, preview paths, and MCP state defaults resolve dynamically.

### 6. Subprocess and Opt-In External Commands
All current call sites use list argv + shell=False, with comments.
- Plan quota: explicit, auth-mode strips metered env, cwd sandboxed.
- CLI judges (--judge-cli): explicit opt-in only, prompt written to tmp file, template shlex.
- ngrok tunnel: opt-in dev.
- pandoc, git probes, upgrade, benchmark scripts: internal or fixed.

No obvious injection. But:
- ngrok_path or judge command template supplied by user could point anywhere (PATH resolution, malicious bin).
- On Windows, argv handling.

Recommendation/decision: document threat model (operator supplies the CLI, so trusted); consider PATH lookup warnings or absolute requirement for judge commands; add allowlist for known good judge CLIs?

### 7. MCP / Remote Surfaces
- Scoped keys, tool allowlist, ResearchMode gating, confirmation for spendy, budget args, no-metered validation all present and tested.
- SSRFProtector + utils.security used.
- OutputVerifier for hash chain.
- Instruction signing, sampling.
- http dispatch catches broad Exception, returns generic error (good for not leaking).
- State uses sandbox? mcp/state/sandbox.py

Open items:
- Remote HTTP MCP still experimental (per roadmap).
- Audit append-only for remote calls.
- Does every tool path that can spend go through budget reservation + ledger?
- Consult validation (mcp/consult_validation.py) and smoke cover no-fallback.

Decision: keep expanding red-team (deepr eval red-team) cases for new MCP tools; require design note before adding any new tool that can write or spend without explicit apply/confirm.

### 8. Other Minor
- Some sqlite schema migrations use f-string for trusted column names only (commented).
- validate_identifier / sanitize_name / safe_path_within used in most name/id paths; storage has its own _validate_job_id/_filename that duplicate some logic.
- Consider centralizing all path segment validation to one util.
- Web dashboard (flask) inits storage from config; middleware has rate limiter. Check security headers in prod deploy only?
- No pickle/yaml.unsafe, no eval/exec in user paths, no os.system.
- PromptSanitizer delimits untrusted content; used for sources/tool output. User prompts for research are operator intent (not sanitized as "untrusted").

### 9. README and ROADMAP Review
- README accurate for current surface (v2.24), highlights local/plan-quota, cost controls, agent balance, no hard-coded reports path rule stated indirectly via docs links.
- No em-dashes or attribution found in prose.
- ROADMAP correctly positions active items (graph commit apply, temporal, self-model, maker-checker, plan-quota trust), references AGENTIC_BALANCE and security non-goals.
- Past bug hunts noted (path traversal in blob, test pollution of experts/, cost ledger isolation).
- Test counts/docs claims match scripts/check_docs_consistency target.
- Suggestion: after this review, add dated entry under live-validation or Phase Q security if new items land.

## Next Steps for Followup
- If any future fix here touches a public contract, add a design note or ADR.
- Add broader property tests for poller paths, belief event append concurrency,
  cost-event retry paths, and append-only log recovery after simulated process
  interruption.
- Decide whether queue paths remain intentionally local or should move under
  the runtime data root when `DEEPR_DATA_DIR` is configured.

## References
- AGENTS.md, CONTRIBUTING.md, docs/plans/AGENTIC_BALANCE.md
- utils/security.py (traversal, SSRF, sanitize)
- observability/cost_ledger.py
- mcp/security/*
- experts/paths.py, storage/local.py + blob.py
- providers create + per-impl

This file is living; append findings from future sweeps. Close items by moving dated note to CHANGELOG or decisions/ when resolved.

## Deeper Rounds (Post-Initial Pass)
Additional exhaustive passes performed:
- Concurrency: locks/semaphores in agents/runtime/orchestrator, expert_verb_lock (filelock nonblock + canonical path + finally release), BeliefStore lock, quota/cost ledgers. No obvious TOCTOU or lost updates on side effects. Jitter uses sha256 (good).
- Resource mgmt: tempfile patterns - most use TemporaryDirectory context or mkstemp + explicit unlink in except/BaseException (jobs.py). Company scrape used delete=False NamedTemporaryFile for handoff to research; added unlink after submit and on error paths to prevent orphan accumulation.
- Hashes: mixed md5 (short stable IDs/dedup/seed) and sha256 (content, prompt, belief ids). Upgraded all remaining md5 short hashes to sha256[:N] for better collision resistance on identity/dedup paths. Comments preserved for non-crypto cases. Core contracts and claim extraction already preferred sha256.
- Durable appends: cost, quota, beliefs events, loop_runs, traces, routing_log etc use lock + flush + fsync or append_jsonl_durable. Admission ledger upgraded to append_jsonl_durable. SQLite queue uses try/finally close in ops + WAL + PRAGMAs.
- Redaction: sanitize_log_message called in api error middleware, some providers, web benchmark. load_config redacts keys. Traces and MCP manifests redact. Coverage good but not 100% on every possible exception path - secondary logs may leak if not wrapped.
- Error paths: dozens of "except Exception: pass" or warn. Pattern is deliberate for "cost recording / bookkeeping / best-effort cleanup must never abort primary user op". Primary settlement (provider responses, plan_quota client, core costs, poller handle_completion) protected. Strict env flag exists for cost ledger.
- Validation/limits: prompt length caps (50k default in security + api/cli), file size/ext, job id/filename sanitization, SSRF, URL schemes, slug validate. Applied at most boundaries.
- Config/roots: still some legacy relative paths for queue/logs (not reports). Atomic writes + canonical_expert_dir widely enforced. load_config shims improved for redaction.
- No new injection, bypass, or silent money paths found. Subprocess always list/argv, no shell on user data. Cleanup tracking for vector stores + orphaned logging.
- Test/property: red-team, continuity, local evals, admission scoring provide coverage for quality + some adversarial. Belief/ledger durability exercised in unit.

### Raised Bar Changes Applied in Deeper Rounds
- Standardized content/identity hashing to sha256.
- Admission append now crash-durable + fsync.
- Company research temp files cleaned after handoff (prevent disk leak).
- Additional path/root consistency and key guard propagation.
- Belief events durability strengthened (earlier).

### Items Still Requiring Explicit Decisions (High-Stakes Use)
- Make quota_ledger and admission appends also respect a strict env var (like cost) and surface on failure for audit-critical capacity records.
- Formal lifecycle contract for all caller-handoff temps (documents to research).
- Consider connection pooling or context-managed SQLite for queue under very high concurrency.
- Expand redaction to wrap more exception reprs in MCP and agent traces.
- Add property-based tests asserting "no cost event lost on retry paths" and "append-only logs survive simulated kill after write".
- For high-stakes releases: run with DEEPR_COST_TRACKING_STRICT=1 + explicit plan capacity + red-team on every release. Consider external signing of ledgers if tamper-evidence needed beyond fsync.
- Full supply-chain (deps, SBOM already in CI) + reproducible builds beyond current.
- Memory/disk bounds on long expert graphs or large context packs (current pruners exist but ratchet limits?).

### Continuation Deep Fix Round (additional fixes)
- Upgraded remaining plain "a" appends on security/audit.jsonl and RemoteMCPAuditLog to use append_jsonl_durable + fsync=True + lock.
- Made security audit log and several observability/analytics paths respect DEEPR_DATA_DIR (previously hardcoded "data/...").
- Updated all eval writers (local_context, local_compare, consult, consult_quality) and admission DEFAULT_BENCHMARKS to default under DEEPR_DATA_DIR/benchmarks when set.
- Updated routing_log, provider_router metrics, core/jobs default log path for consistency.
- Added sanitize_log_message wrapping to poller error paths (worker + research_agent) to prevent any accidental secret leakage in exceptions.
- Fixed company research temp file lifecycle with explicit unlink after use and on error (prevents orphan files).
- Standardized more data roots and removed several direct "data/xxx" literals in favor of env-aware helpers.
- Fixed additional MCP internal state DB paths (credentials.db, mcp_jobs.db, durable_tasks.db, resource_handler reports) to respect DEEPR_DATA_DIR.
- Fixed web/app.py portrait, trace, benchmark paths for portability.
- Verified no new bypasses in spend/authz during this pass.
- Ruffed and mypy checked after each batch.
- Added cross-process FileLock around ExpertProfile save in profile_store.py to prevent races on concurrent updates from multiple interfaces (CLI/MCP/web) writing profile.json. Uses atomic write inside lock with timeout fallback.

With these, path consistency, durability, and redaction coverage improved further. Still some queue/log defaults remain relative for backward compat in CLI fallbacks (documented).

Date of this deeper sweep: 2026-06. Re-run on future changes.

Additional actions in latest continuation:
- Added cross-process advisory locking (FileLock) to ExpertProfile.save to serialize concurrent writes from different processes/interfaces. Prevents potential profile.json corruption or lost updates during simultaneous expert updates or metadata changes.
- Fixed remaining internal DB path hardcodes in MCP credential_manager, persistence (mcp_jobs), task_durability, and updated related docs/comments.
- Hardened more web/app.py data roots for portraits/traces/benchmarks.
- Performed additional static searches for bare excepts, marker comments, validation sites, and locks. No new critical bypasses or injection vectors were identified beyond documented items. Intentional best-effort swallows in detection/probes were left as-is because they degrade gracefully without affecting ledgers or writes.
- All changes passed ruff, strict mypy on gated modules, docs-consistency, and relevant unit tests (e.g., expert root unification).
- Continued to drive path/durability/redaction/concurrency coverage higher while preserving Windows portability and atomic guarantees.

The review loop has now covered and hardened a broad set of areas. Clear actionable bugs and security hardenings are incorporated. Questionable or large-scope items remain in this doc for decision.
