# Local Working Skills

This file captures repo-specific operating lessons from autonomous work cycles.

## Code-health ratchets (the red-CI traps)

- `experts.py` and 16 other files are at grandfathered **file-size caps** (Phase Q). New CLI commands do NOT go in `experts.py` - put them in their own module (`expert_portrait.py`, `expert_maintenance.py`, ...) and register via the bottom-of-`experts.py` `from ... import X as _X  # noqa: F401` pattern. Adding to `experts.py` trips the BLOCKING file-size ratchet.
- There are TWO ratchet scripts: `scripts/check_file_sizes.py` AND `scripts/check_ratchets.py` (C901 + S). Run BOTH, full output - never `head` the C901 line off. A file-size failure (CI runs `bash -e`) masks the later C901 check in the same step, so fixing one can unmask the other (two red pushes in a row if you only fix what you see).
- Before pushing, run the **full lint-job mirror** locally: `ruff check src/deepr/` + `ruff format --check src/deepr/` + `check_file_sizes.py` + `check_ratchets.py` + `check_docs_consistency.py` + `mypy --strict ... core providers mcp`. CI's "lint" job is exactly these; reproducing them avoids red-main ping-pong. (`ruff` is pinned to 0.15.17 so counts match CI.)
- A new click command that resolves targets + confirms + runs a batch easily hits C901 11. Extract target resolution and the batch runner into module-level helpers - ruff rolls a nested function's branches into its parent, so a nested `async def _run()` inflates the command's complexity.

## Free $0 expert knowledge (local + agentic)

- $0 sourced expert knowledge = local Ollama model + free web search + the comprehensive first-sync baseline. All three are required: without sources the absorb gates correctly refuse to record the model's unsourced guesses ("no changes").
- Free web search uses `ddgs` (the maintained successor to the deprecated `duckduckgo_search`, whose endpoint returns nothing). It's an optional `[search]` extra; without it, fresh-context returns 0 sources.
- `expert sync` is a delta tool ("what changed"). The FIRST sync establishes a comprehensive baseline; only later syncs are deltas. Evergreen topics gain nothing from a delta-only first sync.
- Driving a chat seam from raw `python -c` on Windows hits cp1252 emoji crashes (the CLI sets UTF-8 at entry). Use `PYTHONUTF8=1` for ad-hoc scripts.
- The web dev server (vite) must proxy `/portraits` (and any backend static route) or `<img>` tags get the SPA index.html (200, wrong type) and fall back silently. Dev must mirror the prod static routes.

## Plan-quota CLIs: headless prompt delivery and per-CLI quirks

- Long prompts (a synthesis prompt with several experts' perspectives, a research
  prompt with fetched page text) must NOT be passed as a command-line argument to
  a plan CLI. Two distinct Windows failures result: cmd.exe mangles a multi-line
  arg to a `.cmd` shim (the CLI sees an empty task and answers conversationally at
  $0 - a silent quality failure, not an error), and a very long arg trips
  `WinError 206` (command line too long). Use stdin or a prompt file.
- Per-CLI delivery (set on the adapter, resolved by `client._build_invocation`):
  Codex `codex exec -` (stdin), Claude `claude -p -` (stdin), Grok
  `--prompt-file <path>` (file - it has no stdin path: `grok -p` requires the
  prompt as the flag value, and `-p -` reads interactively). Short-prompt CLIs
  keep plain argv.
- Validate a plan CLI by reading its real `--help` on the target machine before
  trusting an adapter argv - vendor CLIs churn quarterly. `grok --help` revealed
  `--prompt-file` and `--output-format json`; `agy --help` revealed `--print` has
  a 5m default `--print-timeout` (Deepr's 60s probe undershoots it).
- Antigravity (`agy -p`) drops stdout under a non-TTY pipe (exit 0, empty
  output) and is not fixable by a flag. The headless answer is persisted to
  `~/.gemini/antigravity-cli/brain/<conv-id>/.system_generated/logs/transcript.jsonl`
  as the last `PLANNER_RESPONSE` record; Deepr recovers it there
  (`antigravity_transcript.recover_answer`, adapter `answer_from_transcript`),
  validated end to end. Pick the newest transcript touched at/after the run start
  so an older conversation is never mistaken for this run's.
- The no-surprise-bills gate strips the metered key (`OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`) from the child env, so the
  CLI falls back to plan/subscription auth. To reproduce a plan run in a raw
  shell, `unset` that key first or you get "Invalid API key".
- Plan windows are real and opportunistic: a few probes plus a couple of `learn`
  runs exhausted Codex's 5h window. Rotate fills across the plans the operator has
  (codex/claude/grok) so no single window drains; treat plan capacity as a pool,
  not a single backend.

## Expert learning is processing, not warmup

- Adding docs, source packs, or refreshed context to an expert does not by
  itself improve the expert. Improvement happens when the system processes the
  material into canonical state: atomic beliefs, provenance refs, typed temporal
  graph edges, contradiction signals, and a gap agenda.
- Keep three layers distinct: raw/source artifacts, canonical structured belief
  state, and derived wiki/digest/handoff views. Derived views are regenerated
  and never authoritative.
- A "fresh" timestamp is weak evidence. Measure quality through populated
  beliefs, cited sources, grounding assurance, open contradictions, gap closure,
  and replayable eval traces.
- Expert self-models should start as read-only derived contracts over the
  profile and manifest. Capabilities, limits, goals, calibration, risks, and
  current-focus packets are safe to expose before they are safe to mutate. Wire
  mutation later through reviewed metacognitive proposals and verifier gates.
- Treat schema-adjacent model output as expected. If a model returns one
  `evidence` string despite the requested array, preserve it as one excerpt.
  Splitting it into characters corrupts provenance and can falsely lift
  tertiary source-trust ceilings.

## One expert = one directory (resolve through paths.canonical_expert_dir)

- An expert's profile, beliefs, loop-runs, subscriptions, conversations, and documents must ALL live under one directory. Resolve it through `deepr/experts/paths.py:canonical_expert_dir(name)` (slug = `sanitize_name(name).lower()`, containment-checked) - never build `experts_root() / name` with the raw display name. The original bug: `ExpertStore` slugified but `BeliefStore`/`loop_runs` used the raw name, splitting one expert across `ai_expert/` (profile) and `AI Expert/` (beliefs); `expert list` then showed phantom-empty experts. The display name lives in `profile.json`, not the path.
- `deepr expert cleanup` repairs legacy split dirs (merge display->slug) and deletes empty experts; it backs up the experts root before `--apply`. If you add a new per-expert store, route its path through `canonical_expert_dir` so it can't reintroduce the split.

## Source-trust floor: count identifiers, not quotes (and keep it deterministic)

- The tertiary ceiling 0.60->0.80 hinges on "2+ independent sources". `evidence_refs` from absorb is `[f"report:{id}", *quote_excerpts]`, so a naive `len(set(evidence_refs))` counts the report pointer + each quote as separate sources -> systematic inflation to 0.80 for one source. Count distinct source **identifiers** only (`_independent_source_count`): URLs by host (syndication counts once), namespaced ids by value, and **skip any ref containing whitespace** (that's a quote excerpt grounding one source, not a new origin).
- A trust floor MUST be deterministic form, never a model verdict: it's the prompt-injection backstop, and a model could be injected to claim "independent corroboration" to lift it. Determinism-on-form here is correct AGENTIC_BALANCE, not a violation. Make it **fail safe toward the lower ceiling** (ambiguity lowers confidence; it must never lift or add/remove beliefs).

## Belief confidence: always surface the floored effective value

- A belief stores the extractor's *raw* `confidence` (often 1.0 from a local model), but the trusted value is `belief.get_current_confidence()` - decay x source-trust ceiling (tertiary single-source 0.60, tertiary 2+ 0.80, secondary/primary uncapped). **Every host-facing or human-facing surface that shows confidence MUST call `get_current_confidence()`, never the raw `confidence` field or a change-record's `new_confidence`.** Dogfooding caught `perspective.what_changed` (CLI `what-changed` + MCP `deepr_what_changed`) rendering raw 1.00 on web-sourced beliefs while digest/okf/why/health-check all correctly floored - an agent re-syncing would over-trust. The trust-floor invariant is only real if no surface bypasses it.
- When showing a *delta* over a still-existing belief, the honest "what you believe now" is the floored current confidence, not the value recorded at change time. Fall back to the recorded value only for archived beliefs (no live belief left to floor).

## Budget / cost-safety invariants

- The reserve-then-settle pattern in `CostSafetyManager.check_and_reserve` only prevents over-commit if the cap *projection* counts in-flight reservations. Every cap (daily AND monthly) needs its own `_reserved_*` pool included in the projection, incremented on reserve, released on both settle (`record_cost`) and `refund_reservation`, all under the one `_budget_lock`. Asymmetry is a real bug: the monthly projection omitted reservations while daily included them, so a *low monthly* reserve (the $20/month fleet) over-committed under parallelism even though daily looked fine. When you touch one cap's reservation accounting, mirror it in the other.
- Test the concurrency guard by making the *other* cap roomy and the cap-under-test binding (e.g. `max_daily=100, max_monthly=5`), then assert the second parallel `check_and_reserve` is rejected and names the right limit. Same shape for daily.
- `cost_safety.py` sits right at the 1000-line file-size ceiling. Necessary functional lines win; claw back the budget by tightening prose/docstrings, NOT by splitting the file for tidiness (STOP-banner: low-value churn). A net +1 line trips the BLOCKING ratchet.
- Council synthesis is still a paid model call when expert perspectives come
  from stored beliefs. Settle the council reservation with `record_cost` and
  write source `expert_council.synthesis`; do not rely on the consult payload's
  returned `cost_usd` as accounting.

## Expert consult grounding

- `expert consult` perspectives should prefer the expert's stored `BeliefStore`
  before starting a live expert chat session. Live chat is a fallback for empty
  or missing stores, not the default when durable beliefs exist.
- Query-token overlap may select which beliefs enter the context packet, but it
  must never conclude truth, contradiction, completeness, or agreement. The
  selected context still carries confidence, sources, and contested flags into
  synthesis.
- Consult perspective context metadata is a replay/debug surface, not a verdict:
  include source, selection reason, included and available belief counts, and
  matched terms when known, but keep semantic acceptance in the verifier and
  synthesis layers.
- Parse synthesis sections by heading prefix, checking `DISAGREEMENTS` before
  `AGREEMENTS`. Substring checks invert the result because `DISAGREEMENTS`
  contains `AGREEMENTS`.
- Dogfood consult failures should become local eval cases: routing to the wrong
  expert, generic prior instead of stored beliefs, parser drift, and missing
  ledger writes are harness failures, not prompt anecdotes.
- `deepr eval consult` is the `$0` seed for those harness failures. Add cases
  there when a consult bug can be reproduced through deterministic contracts;
  reserve model-judged cases for semantic quality after the trace artifact is
  persisted.
- Consult synthesis should be capability-adaptive through the existing
  chat-completions seam. Inject `ollama_chat_client()` for `--local` and
  `PlanQuotaChatClient` for `--plan`; do not create a second orchestration path.
- Owned-capacity consult modes must disable live metered expert fallback unless
  there is an explicit API choice. Stored beliefs are safe to read at `$0`; a
  missing belief store should produce no-context output, not an accidental paid
  chat session.
- Once owned-capacity consult modes disable live metered fallback, they should
  also skip paid-budget reservations. Cost safety should still guard the default
  metered path, but an exhausted API budget must not block a genuinely `$0`
  local or explicit plan synthesis path.
- Treat synthesis backend failures as trace-quality work. A plan CLI returning
  exhaustion should leave the consult at `$0` with an unavailable synthesis
  result, never fall through to metered API. The next improvement is a durable
  trace event and eval case, not a hidden fallback.
- Persist consult traces as local artifacts, not host payload dumps. The host
  gets a safe `trace` reference with schema, kind, trace id, status, and checks
  run; the local JSONL record gets the replay material: question, requested
  experts, selected context metadata, capacity posture, output artifact, checks,
  and first-class synthesis failure events.
- A trace is a workflow artifact, not a semantic verdict. It can say which
  context was selected, which capacity path ran, which structural checks passed,
  and whether synthesis failed; answer quality still belongs to evals and model
  judgment.
- Mine traces into candidates through structural signals only. Failed status,
  failed checks, and missing selected context can route a trace into a gap/eval
  candidate; do not let word overlap or phrasing checks conclude answer quality.
  Host-facing review payloads should include trace ids, hashes, short previews,
  checks, and candidate metadata, not raw trace files.
- Local model synthesis often uses Markdown emphasis in bullets. Parse one
  bullet marker explicitly, then normalize harmless bold labels; broad `lstrip`
  can delete the opening `**` and leave a dangling closing marker.
- Current 2026 harness guidance is a fit for Deepr when translated into
  artifacts: selected context packs, durable traces, reusable eval cases,
  explicit handoff files, and deterministic gates around spend, writes, and
  permissions. It does not imply turning Deepr into the outer orchestrator.

## Plan-quota CLI backends

- Run the value-prop honesty test before building any "plan capacity" CLI: is the next headless call free at the margin on a flat subscription, or metered per use? A metered CLI (Copilot post-2026-06-01) is the API in a costume - `enabled_by_default=False`, never marketed as free. The check belongs in the adapter spec, not in prose.
- Quotabot's reusable lesson is the quota snapshot contract: provider-specific probes should emit normalized windows, mark stale cache explicitly, compute headroom from the most constrained window, treat passed reset times as fresh, and then write one conservative ledger event through `snapshot_to_ledger_event`. Do not let each vendor probe invent routing semantics.
- Codex has the first trusted metadata path: `deepr capacity refresh-quota codex` reads newest local `~/.codex/sessions/**/rollout-*.jsonl` files for a nested `rate_limits` object, maps primary to 5h and secondary to weekly, then writes a quota-ledger event. This is a local metadata read, not a model call.
- Claude Code quota refresh is a live metadata call, not a generation call:
  `deepr capacity refresh-quota claude` reads the current user's
  `.credentials.json` from `CLAUDE_CONFIG_DIR` or `~/.claude`, uses the OAuth
  access token only for the read-only usage endpoint, maps `five_hour`,
  `seven_day`, and `seven_day_opus` windows into `QuotaSnapshot`, and never
  persists credential material. Keep it explicit because the endpoint is
  reported to rate-limit aggressive polling.
- Grok quota refresh is also metadata-only:
  `deepr capacity refresh-quota grok` reads the current user's
  `auth.json` from `GROK_CONFIG_DIR` or `~/.grok`, uses the bearer token only
  for Grok billing metadata, parses the gRPC-web response into a monthly
  `QuotaSnapshot`, and never persists credential material. Keep Antigravity
  passive-first until its metadata surface is verified.
- Provider prompt caching is a metered cost-control feature, not free capacity.
  Treat cache writes, long TTLs, cache keys, and pre-warm requests as billable
  until the provider usage record proves otherwise. For Anthropic in
  particular, do not enable automatic pre-warming or 1-hour TTLs without an
  estimator, actual `cache_creation_input_tokens` / `cache_read_input_tokens`
  ingestion, and an explicit user budget ceiling.
- Two execution seams exist. For maintenance, the light `research_fn` `(query, budget) -> {answer, cost}` / chat-client seam is correct; the API-shaped `DeepResearchProvider` is wrong for a subprocess CLI. `expert sync` needs research AND extraction, so expose the CLI as a minimal `client.chat.completions.create -> .choices[0].message.content` shim (like `ollama_chat_client`) and use ONE instance for both - otherwise extraction silently falls back to metered.
- The shim must ignore the caller's model name: Deepr's internal ids (gpt-5-mini) are meaningless to a vendor CLI and would be passed as a bad `--model`. Use the operator's `--plan-model` or the plan default.
- No-surprise-bills is deterministic and lives before the subprocess: remove backend-specific metered API-key variables from the child environment, evaluate the sanitized child env, and include the sanitization in the safety reason. Do not require the operator to mutate a normal API-capable shell just to run an explicit plan command.
- Auto-routing requires an *observed remaining* quota window. Do not infer headroom from an installed CLI. Codex, Claude Code, and Grok metadata observations can satisfy that gate for their own backend; unobserved backends stay `QUOTA_UNKNOWN`. Explicit `--plan` is the works-now path for every registered CLI.
- Drive the agentic CLI safely: explicit argv (never shell), read-only sandbox / `--deny-tool shell,write`, a scratch cwd so it can't wander the repo, and a hard timeout that kills the process.
- Record both ledgers per call: `quota_ledger.jsonl` (usage / terminal exhaustion) and a `$0` `cost_ledger.jsonl` entry with quota units, so `costs show` and anomaly detection see volume even at $0. Both writes are best-effort (never break a run).
- Test the subprocess runner with real hermetic subprocesses via `sys.executable` (cross-platform, $0); mock the runner for adapter/shim tests.
- Fetched context can contain NUL bytes even when every upstream guard was
  "text" shaped. Normalize argv parts before `create_subprocess_exec`, drop env
  entries with invalid names, `None`, or NUL values, and keep the launcher
  structured. This is a form guard that prevents process-launch failure, not a
  semantic content filter.

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
- Metered remote MCP tools need explicit deterministic estimate coverage. If a budgeted scoped-key call targets a metered tool without an estimate, fail closed before handler dispatch and fix the tool metadata or estimator.
- Remote scoped-key rate limits should use the append-only remote audit log as the source of recent-call truth. Block before dispatch, include retry metadata, and audit the denial so repeated abuse stays visible.
- Remote HTTP concurrency is a workflow guard, not scheduling policy. Cap simultaneous POST dispatch before reading the body or entering handlers, return 429 with retry metadata, and expose one default setting across CLI, compose, and cloud templates.
- Remote HTTP serve paths should keep stdio as the default, bind HTTP to loopback by default, and refuse reachable binds unless a shared token or active scoped key is configured.
- Remote HTTP smoke tests should stay structural and `$0`: health, initialize, tools/list, and a free read-only tool dispatch are enough to prove reachability, auth, JSON-RPC routing, and dispatch without touching provider APIs.
- Hosted MCP deployment should terminate TLS at a reverse proxy and keep the Python MCP process bound to loopback. Production docs should lead with scoped keys, per-agent secrets, rate limits, revocation, and audit review before widening key mode or budget.
- Published downstream-agent schemas should be additive within a schema version. Add optional fields freely, but changing or removing required semantics needs a new schema_version and a new schema file.
- Hosted MCP container recipes should publish only loopback on the host, mount a single Deepr data directory, and require scoped-key bootstrap before `up`. The container can bind `0.0.0.0` internally only because the host port stays loopback and the transport refuses startup without an active key.
- Remote audit review is a workflow surface. Keep it read-only, local, and filter/summary-based over append-only JSONL records; never re-run a tool call or infer semantic quality from the audit log.
- Remote audit records are a downstream contract. Add fields only additively within `deepr-mcp-remote-audit-v1`; required-field or meaning changes need a new schema version and a new schema file.
- Cloud templates for hosted MCP must preserve the same workflow guardrails as the local container: durable `/data`, scoped-key state, audit-log durability, HTTPS-only ingress, and no provider keys unless paid tools are intentionally enabled behind a key budget.
- AWS hosted MCP packaging should use EFS for `/data`, an HTTPS ALB listener, scoped-key bootstrap guidance, and local contract tests. Keep provider API keys out of the CloudFormation template until a scoped key budget intentionally allows paid tools.
- GCP hosted MCP packaging can use Cloud Storage FUSE for `/data` only with single-writer defaults. Keep `max_instances=1` and `max_concurrent_requests=1` while scoped-key and audit files live on the object-backed mount; require tests and docs to say why.
- Hosted MCP registration artifacts must be token-redacted. Run `$0` smoke checks before emitting setup metadata when possible, but never serialize the bearer secret or imply live platform registration has passed until an actual host calls the endpoint.
- Supported-surface docs are contract docs. Keep works-now, experimental, visible/read-only, planned, and export guarantees separate so roadmap intent is never mistaken for shipped capacity.
- Hosted MCP edge ingress should stay stateless. It may enforce transport-shaped guards such as HTTPS origin, path allowlists, body size caps, and forwarded headers, but scoped-key enforcement, budgets, rate limits, audit logs, provider keys, and semantic decisions stay on the origin.
- MCP allowlist regressions should test the union of visible registry tools and dispatcher-only tools. Check declared policy, scoped-key authorization, and JSON-RPC pre-dispatch gates across every `ResearchMode`, not just isolated tool config entries.
- Expert chat cost-safety tests should distinguish global cost denials from session denials. Session budget exhaustion and session circuit breakers need blocked responses with session metadata before any provider or fallback provider call.
- CLI shortcuts need dispatch-level regression tests. A shorthand that is only shown in help can still hit Click's generic error path, so test the root command route and its option parsing without invoking the expensive command body.
- Published CLI JSON schemas should validate real runtime payloads, not hand-written examples. Add `schema_version` and `kind` additively, then test success and error outputs against the registry schema.
- When a published JSON schema already has a shared serializer, route every surface through that serializer before adding another schema. CLI, MCP, and web payloads should not drift into separate ad hoc shapes.
- Scheduler-facing guidance payloads should carry their own schema version even when nested inside a larger wait response. Preserve the existing nested key, but make the reusable object validate independently.
- For scheduled wait envelopes, version both layers when they carry different contracts: the outer wait/block reason and the reusable nested guidance object.
- Indirect prompt-injection defense belongs at prompt boundaries and tool-result boundaries, not as a truth verdict. Delimit untrusted source spans as data, sanitize obvious embedded directives, and let extraction, grounding, contradiction, dedup, and trust-floor gates decide what becomes belief state.
- Keep source-pack artifacts useful for audit. Sanitize the prompt context that models see, but preserve original source excerpts in durable artifacts unless a schema explicitly says the stored field is sanitized.
- Tool-output findings can sanitize text in `AbsorbedFinding.__post_init__` so first-party parsers keep their structured behavior while malicious strings do not enter expert prompt context as live instructions.
- Multi-step research surfaces reuse earlier outputs as prompt context. Treat document previews, report summaries, completed task results, company intelligence, and team findings as untrusted source blocks whenever they feed a later model call.
- Red-team metrics are workflow checks over shipped boundaries. Track canary leakage, required delimiters, structured tool-spoof neutralization, and trust-floor ceilings as attack-success-rate, but do not let those lexical canaries become semantic truth verdicts.
- Host-facing expert read payloads are derived views. Sanitize directive and tool-spoof canaries in MCP handoff or loop-status JSON before host consumption, but keep the structured expert store canonical and unchanged.
- Red-team trend artifacts should save the report dictionary as JSON under `data/benchmarks` and keep Deepr metered cost at `$0`. They are release evidence, not an admission gate or semantic proof.

## Fleet scheduling + change-detection (2026-06-23)

- **Change-detection gate fails safe toward *proceeding*, never skipping.** The content-hash gate (`fresh_sources_unchanged`) only skips the paid absorb on positive proof of no-change (current hashes a subset of prior). No prior pack / no hashable content / any new hash -> run the pipeline. A wrong "unchanged" would silently freeze an expert; a wrong "changed" only wastes one already-gated call. Skip-on-uncertainty is the dangerous direction.
- **A per-(expert, verb) lock must key the FILENAME, not just the directory.** TDD caught this: with the default per-expert `.locks/` dir it worked, but a shared `lock_dir` collided across experts because the file was named only by verb. `filelock` detects same-process contention between two `FileLock` instances on one path, so the overlap guard is unit-testable without spawning processes. Newer `filelock` removes the lock file on release, so assert existence *while held*, not after.
- **Scheduled verb wiring tests should prove no side-effect path is built on lock contention.** For `expert sync`, the regression stubs `expert_verb_lock` to yield `False` and makes `build_sync_engine` explode; the command must return a skipped `SyncResult`, append a waiting `ExpertLoopRun` with `stop_reason=overlap_locked`, and never construct the engine. This is the pattern to copy for health-check, reflect, and other mutating scheduled verbs.
- **Windows Task Scheduler XML: declare `encoding="UTF-8"` to match the file you write, and XML-escape every command-derived value.** A `<?xml encoding="UTF-16"?>` header on a UTF-8 file makes `schtasks /Create /XML` reject it, and a `--command` containing `&`/`<`/`>` produces malformed XML. Parse-verify generated XML with `ET.fromstring` in a test, not just string asserts. `MultipleInstancesPolicy=IgnoreNew` is the scheduler-level overlap guard; `StartWhenAvailable`/`Persistent=true` are catch-up (Modern Standby can't guarantee an exact-time wake).
- **Promote a transitive dep to a direct dependency before importing it in core.** `filelock` was only transitively present; using it in `experts/` means declaring it in `pyproject.toml` then `uv lock` (minimal diff - it also corrected a stale `2.19.0 -> 2.20.0` version drift in `uv.lock`).
- **Skill guidance: a `tools/` script must never be a meaning-verdict.** Deterministic skill tools do calculations/extraction/formatting (the AGENTIC_BALANCE workflow side); quality judgments route to a calibrated model. The highest-leverage skill type is a *verifier* (the evidence layer), and every skill carries a `## Gotchas` section seeded from real failures. See `docs/design/skill-authoring.md`.
- **A net-new CLI command's registration line trips the `experts.py` grandfathered cap.** The command body goes in its own lean module (good), but the bottom-of-`experts.py` `import ... as _x  # noqa: F401` that runs the decorator is +1 line on a file pinned at its exact cap (3338). For a net-new command (nothing extracted to offset it), register via a sibling under-cap module instead - e.g. `expert sync-all` registers from the bottom of `expert_maintenance.py` (itself imported by `experts.py`, so the decorator still runs). Only `# noqa: F401` is valid here; `E402` is not enabled, so `# noqa: E402` is itself a RUF100 error. Run `scripts/check_file_sizes.py` before pushing - the file-size guard has pytest mirrors (`test_code_health_guards.py`) that fail the suite, not just CI.

## Cross-vendor maker-checker (live-validated 2026-06-24)

- **Validated live on OpenAI + xAI**: the fresh-context disconfirm/entailment checker (`experts/maker_checker.py`) correctly marks a grounded claim SUPPORTED and the planted "$30 vs evidence-says-$10" claim UNSUPPORTED, on both vendors. A clearly-unsupported claim is caught by both; a *borderline* entailment ("Deepr auto-mode routes X" vs claim "Deepr routes X") got SUPPORTED from one vendor and UNSUPPORTED from the other - real cross-vendor disagreement on the borderline, which is exactly why the design escalates to a 2nd checker only on disagreement. The disconfirm prompt is intentionally strict (errs toward flagging weak entailment); that is the point, not a bug.
- **The registry model name is NOT the vendor's API model id.** The registry has `xai/grok-4-20-non-reasoning` (`model="grok-4-20-non-reasoning"`), but the live xAI API rejects that and serves `grok-4.20-0309-non-reasoning` (dots + date suffix). When wiring the checker to a real cross-vendor OpenAI-shaped client, resolve the actual API id (list via `/v1/models` or go through the provider adapter that translates) - do not pass the registry's internal name to a raw `AsyncOpenAI(base_url=...)`. xAI is OpenAI-compatible (`base_url="https://api.x.ai/v1"`), so it drops straight into the maker-checker's OpenAI-shaped client; Anthropic is not OpenAI-shaped and needs a wrapper.
- **Fail-safe confirmed in production**: a wrong model id surfaced as `supported=None` (could-not-verify) with reason "check failed", never a false refutation - the conservative contract held on a real error.

## Maker-checker CLI wiring (2026-06-25)

- `expert_maintenance.py` is under the 1000-line ceiling but close enough that new flags should first move support code out. `expert_sync_support.py` now owns sync capacity waits, loop records, context builders, and overlap locking; keep future sync helper growth there.
- Grounding checks must remain explicit. `--check-grounding` is the switch; `--checker-plan <id>` chooses a different plan CLI checker. Do not create a metered API checker automatically just because the maker path is metered.
- For local/plan sync with a different `--checker-plan`, avoid constructing the same-backend default checker client. The checker helper ignores default clients when a checker plan is supplied, but Python still evaluates the argument first.
- Preserve constructor compatibility by passing `grounding_checker` only when it is non-None. Many CLI tests patch `ReportAbsorber` with narrow constructor stubs, and default behavior should keep the old argument shape.
- Dry-run absorb/sync previews should not call the checker. The checker verifies claims about to be written, not preview output.
- Handoff assurance should flow from canonical state, not a side channel. Preserve `Belief.grounding_assurance` through `Belief.to_claim()` and `Claim.to_dict()`, then summarize it in `build_expert_handoff`; keep `deepr-expert-handoff-v1` additive and schema-tested.

## Agentic Surface Rollout

- Before widening autonomy, name the rollout stage: prototype, shadow, pilot, limited production, or full production. A loop without verifier metrics and recovery evidence should stay shadow or pilot.
- Version prompts, tool specs, schemas, eval sets, memory policy, and orchestration graphs once any host, scheduler, or stored artifact depends on them. Versioning makes failures bisectable and lets old handoffs remain interpretable.
- State-changing agentic paths need documented retry behavior plus idempotency keys, deduplication, rollback, or compensation before they move beyond pilot. Planning and irreversible execution stay separated by deterministic workflow gates.

## Plan-quota expert bootstrap

- Windows plan CLI execution must resolve through `PATHEXT` while keeping `shell=False`. Resolve the executable with `shutil.which` before subprocess launch so `codex` finds `codex.cmd`.
- Explicit plan capacity should sanitize metered API-key variables in the child environment instead of requiring the user to mutate their shell. Record the sanitization in the safety reason, then run the CLI with the sanitized environment.
- Long Codex prompts should go through stdin with prompt argument `-`; fresh-context and topic learn or learn-web prompts can exceed the Windows command-line length if passed as argv.
- Local and plan-backed `ReportAbsorber` callers must pass `estimated_cost=0.0`. The default extraction estimate is correct only for the metered API path; owned/prepaid capacity still records `$0` events through the canonical ledger.
- Web-grounded `$0` expert bootstrap should default to keyless retrieval. Do not use `WebSearchTool(backend="auto")` in a no-surprise-bills path because hidden Brave or Tavily keys can become silent spend.
