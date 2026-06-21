# Progress Log

## 2026-06-21 — Agentic-harness boundary (dogfood-derived) + new AI Agent Harnesses expert

- **Created + populated "AI Agent Harnesses" expert** (+25, API $0.048), then consulted it with Model Context Protocol + Distributed Systems Reliability on the strategic question "is Deepr an agentic harness?" - dogfooding the now-fixed consult path (3/3 real, convergent answers, $0.024 ledgered).
- **The experts converged on a sharp boundary**, captured in `docs/design/agentic-harness-boundary.md` and used to sharpen the ROADMAP "not the orchestrator" non-goal: **Deepr is agentic only within a single bounded, idempotent knowledge transaction** (decompose -> consult its own experts -> reason -> verify -> one commit point, hard budgets, one calibrated artifact out). It must not own workflow state, cross-call retries/scheduling, or side effects beyond its own knowledge store - it recommends next actions; the calling harness decides and enacts. This retroactively validates the session's design (idempotent absorb, single commit point, bounded councils, host-triggered campaigns).

## 2026-06-21 — Consult now "just works" (adaptive) + Ollama kept warm

- **Consultation reliability traced and verified fixed.** Root cause of the garbage consult was NOT Ollama: `chat.py` wires `ReasoningGraph(llm_client=None)` and its LLM call is a `.generate()` placeholder never connected to a real client, so the ToT path could never reason. Pre-fix it fabricated `Hypothesis N for: <query>` (which didn't contain "unable to generate", so `send_message` returned the garbage). The earlier reasoning fix (degrade honestly to "Unable to generate a confident answer.") means ToT now trips the existing fallthrough at `chat.py:1350` -> standard chat -> a real answer. **Verified live:** a "should...best" (ToT-triggering) consult returned a real, substantive answer at $0.0223 (ledgered). So consult is now adaptive/defensive: degraded reasoning falls through to a working, cost-tracked path instead of silently emitting stubs.
- **Ollama "slowness" was cold-loading, not degradation.** The RTX 4090 (24GB) sits idle; Ollama evicts the 19GB model after ~5 min, so each spaced call paid a full reload (~22-58s). Fix: deepr's local backend now sends `keep_alive` (`DEEPR_OLLAMA_KEEP_ALIVE`, default 30m) on every Ollama request, pinning the model warm. **Verified:** probe 22.4s cold -> 1.8s warm (12x). Local syncs no longer cold-reload between subscriptions. 173 local tests green; lint/ratchets/file-size at baseline.
- Follow-ons identified (not yet built): a native `deepr expert consult` CLI + MCP tool (so consultation isn't a driver script and any harness can call it), capacity-aware consultation routing (fall through to plan-quota CLIs), and wiring ToT to a real client *with* ledgered cost (it currently bypasses cost_safety, so it stays disabled-by-fallthrough rather than reintroducing a silent-spend path).

## 2026-06-21 — Fixed a silent-degradation bug the consulting process surfaced

- **The wider 11-expert consult (incl. 4 new experts: Distributed Systems Reliability, Temporal Knowledge Graphs, Karpathy LLM Wiki, Open Knowledge Format) returned garbage** - every perspective was `Hypothesis 1 for: <prompt>` at $0. Root cause: `ReasoningGraph._generate_hypotheses` had a "fallback" that **fabricated** `num_hypotheses` placeholder hypotheses (`text="Hypothesis N for: <query>"`, confidence 0.7) whenever the LLM call failed or no client was present. `_synthesize` then returned the highest-confidence hypothesis as the answer - so fabricated placeholders surfaced as a confident response. The local model being pathologically slow right now (probe: qwen2.5-coder:32b took 58s for "OK") triggered the failure path.
- **Fix:** removed the synthetic fallback entirely. On no/failed generation the state stays `is_degraded=True` with no hypotheses, and the existing honest path in `_synthesize` emits `"Unable to generate a confident answer."` at 0.0 confidence. Also skip blank-text hypotheses. This is the no-silent-failure discipline applied: a model outage now degrades honestly instead of fabricating confident content. Regression test asserts no `Hypothesis N for:` text and the honest synthesis; updated the one test that had encoded the fabrication; 49 reasoning + 58 chat/reasoning tests green; lint/ratchets/file-size at baseline.
- **GitHub hygiene:** one clean `main` (local + remote, no stray branches); pushed; CI = success, CodeQL = success. Keeping main + build current as work lands.

## 2026-06-21 — Source-independence trust floor (the dogfood experts' #1 risk, fixed)

- **The calibration-integrity bug the expert team unanimously flagged, fixed.** The tertiary trust ceiling rose 0.60 -> 0.80 on `len(set(evidence_refs)) >= 2`. But absorb stores `evidence_refs=[f"report:{id}", *quotes]`, so the `report:` pointer + any quote excerpt = 2 distinct strings -> **0.80 for a single source**, systematically. Live beliefs showed it (the dogfood expert read at 0.80 from one report). This is the "syndicated/same-origin can't corroborate" gap five experts independently raised.
- **Fix (`Belief._independent_source_count`):** count distinct source *identifiers* only - URLs collapsed to host (a syndicated origin counts once), namespaced ids (`report:<id>`) by value - and **skip free-text excerpts** (any ref containing whitespace; quotes ground one source, not new origins). Kept **deterministic** by design and per the user's "no brittle fail patterns" steer: a trust floor is the prompt-injection backstop, so a model verdict (injectable to claim independence) must never set it - this is determinism-on-*form* (AGENTIC_BALANCE), and it **fails safe toward 0.60** (ambiguity lowers, never lifts; never adds/removes beliefs). The existing designed semantics hold (two distinct report runs still corroborate to 0.80).
- **Validation:** 4 new regression tests (quotes don't count, same-host URLs are one source, distinct hosts corroborate, distinct report runs corroborate); 1298 belief/expert/calibration tests green; lint/ratchets at baseline; beliefs.py file-size cap re-baselined +33 with a justifying comment (precedent: the existing `+7 security fix`). Docs updated: ROADMAP item closed (and its earlier "route to a model verdict" framing corrected - a safety floor stays deterministic), calibration-and-trust.md independence definition sharpened.

## 2026-06-21 — Cost-visibility fix: `costs show` now reflects the canonical ledger ($0.05 -> $0.82)

- **The "ohg" bug, run down and fixed.** `deepr costs show` reported month $0.05 / today $0.00 while the canonical `cost_ledger.jsonl` actually held **$0.82** ($0.17 today). Root cause: `CostDashboard._load` read entries from the *derived* `cost_log.json`, which only gets the spend that flows through `dashboard.record()`. The real recorders - `cost_safety.record_cost` (the main one), the research pipeline - write the canonical ledger **directly** and bypass the dashboard, so the derived cache drifts and `costs show` undercounts. The code even documented the drift (`rebuild_from_ledger`'s docstring) but `show` never reconciled.
- **Fix (regeneration-invariant-correct):** the dashboard now treats the **ledger as the source of truth** for reads. `_load` materializes entries from the ledger (new `_entries_from_ledger` helper, shared with `rebuild_from_ledger`); `cost_log.json` supplies only dashboard-owned state (triggered alerts, user-set limits) with a legacy entry fallback when no ledger exists. Extracted `_load_cache_state` to keep `_load` under the C901 ceiling. Live-verified: `costs show` now reads $0.17 today / $0.82 month. Two regression tests (ledger-written-outside-dashboard is visible; a stale/empty cache never masks ledger spend); 161 cost tests green; updated the unicode round-trip test (entries now carry the ledger's provenance `source` key).
- **Bug B fixed too:** expert *chat consultation* (the council's `agentic=False` perspective generations) incurred ~$0.01/expert but wrote **no** ledger entries - chat recorded *research* costs via `cost_safety.record_cost` but the conversational answer-generation path only bumped the in-session `cost_accumulated`, so that spend escaped both the canonical ledger *and* the daily/monthly caps. Fixed with `_account_chat_cost(usage, model)` (accumulate AND `record_cost`, best-effort), replacing the four inline `cost_accumulated +=` sites in `send_message` + `send_message_streaming`. Unit-tested (records to ledger+caps, skips zero cost, swallows ledger-write failure) and **live-verified**: a one-question consult now appends an `expert_chat` ledger entry (0 -> 1). Both no-silent-money gaps are now closed.

## 2026-06-21 — Dogfood: the expert team reviews Deepr (consultation + TKG + council all validated)

- **Validated, end to end, the four things asked:** (1) experts can be talked to (read verbs + chat); (2) TKGs work - `why` returns the inference chain (claim, floored 0.80 confidence, 2 evidence refs with `[S2]` citations, recorded-1.00->effective-0.80 trajectory), `what-changed` and `contested` work; (3) they talk as a **team** - a 5-expert council (AI Agent Memory Systems [$0 local] + Knowledge Graphs/Provenance, AI Cost Optimization, Model Context Protocol, Python Code Quality) produced 5/5 belief-grounded perspectives + a synthesized verdict with agreements/disagreements; (4) they **consulted on Deepr's own direction** and the output is genuinely sharp.
- **The team's convergent verdict on Deepr (real dogfood payoff):** all five independently flagged the **absorption pipeline's evidence/provenance integrity** as Deepr's #1 risk - "calibrated experts vs well-indexed confabulation." Specific asks, assessed against what exists: (a) **source-independence check before the 0.60->0.80 trust-floor bump** - real gap (the floor counts 2+ evidence_refs but not their independence; syndicated copies inflate); (b) **content-addressed, replayable evidence** (snapshot+URL+timestamp+hash, extraction model/prompt) so LLM synthesis never counts as primary evidence - partial today (source packs exist, no hashing/replay guarantee); (c) **memoize verification + circuit-break verification cascades** so the autopilot can't trigger re-check storms into metered APIs. Added (a) and (b) to ROADMAP (belief-lifecycle), credited to the dogfood. Deepr already has the rest they listed (trust floors, contradiction-as-signal, bi-temporal, decay).
- **Operational findings:** (i) rapid *consecutive* local syncs get throttled by free ddgs (2nd/3rd hung) - validates the fleet design's jitter/spacing requirement; switched the team to the API populate path ($0.034-$0.050/expert via the provider's own grounded research, +25 beliefs each). (ii) Council/chat consultation runs on an **API chat model by default** (~$0.01/expert, frontier "knowledge cutoff" phrasing), not the expert's local model - "$0 consult" needs an explicit local flag/config. (iii) `costs show` reports month $0.05 while sync+consult reports summed ~$0.28 - **possible cost-ledger completeness gap** (the chat/council spend path may not write the canonical ledger); flagged to verify against the no-silent-money invariant. (iv) `council.select_experts` ranks by lexical keyword overlap (a brittle router) - passed experts explicitly per AGENTIC_BALANCE; the model-judgment routing upgrade is already roadmapped.
- **Spend this session ~$0.28** (4 API syncs + 2 council runs); lifetime well under the $10 validation cap. Throwaway driver script removed (not committed).

## 2026-06-21 — Dogfooding: 10 project-experts + a real calibration-honesty bug fix

- **Dogfooded the fleet on Deepr itself.** Defined + created 10 experts that help build this project (AI Agent Memory Systems, Model Context Protocol, Python Code Quality, LLM Evaluation and Calibration, Prompt Injection Defense, Knowledge Graphs and Provenance, Agentic Coding Tools, AI Cost Optimization, Deep Research Systems, Local LLM Operations) - all `--local`, $0. Validated creation (`expert list` / `fleet status`: 22 experts), subscription, and population: **AI Agent Memory Systems gained +21 grounded beliefs from 5 sources at $0.000** via local qwen2.5-coder:32b + free search. Consulted it via the $0 read verbs (`what-changed`, `info`) - content is accurate and on-topic (Mem0/Letta/Zep/Graphiti, temporal KGs, memory governance).
- **Quality question answered with research.** For *grounded extraction from provided sources*, 2026 evidence says local 8B-70B models match or beat frontier *reasoning* models on faithfulness (they hallucinate less when kept in-source); the surviving gap is calibration + long/conflicting sources. Documented Pillar 4 (quality validation) in expert-fleet.md and a roadmap item, with the lean A/B over existing eval surfaces (`eval local` $0, `eval calibrate --corpus` paid+guarded).
- **BUG found by dogfooding + fixed: `what-changed` showed `conf 1.00` on web-sourced beliefs.** Root cause: `perspective.what_changed` surfaced the extractor's *raw* `change.new_confidence` instead of the trust-floored `get_current_confidence()`. Every other read surface (digest, okf, perspective, why, health-check) already floors; this host-facing one (CLI + MCP `deepr_what_changed`) didn't - so an agent re-syncing would over-trust a single-web-source claim at 1.00 when the system's actual trusted confidence is capped at 0.60/0.80. Fixed at the source: surface the effective floored confidence when the belief still exists (raw change value only for archived beliefs, which have nothing left to floor). Live-verified: the 21 beliefs now show 0.80 (2 sources), not 1.00. Regression tests added (single-source->0.60, 2-source->0.80, secondary->uncapped); 128 tests across all what_changed consumers green. This is the trust-floor invariant ("research-derived never over-claims") made true in the one surface that had silently bypassed it.

## 2026-06-21 — `deepr fleet status`: roster-wide health at a glance (Phase 4d slice 3)

- **Shipped `deepr fleet status`** — the cross-expert health view the per-expert `loop_status_rollup` and plan-quota `capacity fleet` didn't cover. Read-only, $0, **no new storage**: folds each expert's `loop_runs.jsonl` (latest run, typed stop reason, accepted/rejected, cost + capacity source, last failure, waiting next-action) and `subscriptions.json` (refresh-due via the honest `Subscription.is_due` cadence — no invented intervals). Anomalies sort to the top; roster summary line; `--json` emits `deepr-fleet-status-v1` (sanitized host-facing envelope); **non-zero exit when any latest run failed** so a scheduler can run it as a watchdog.
- **Design**: pure rollup core in `experts/fleet_status.py` with injectable store factories (unit-tested without disk, 11 tests); thin command layer `cli/commands/fleet.py` (monkeypatched rollup, 6 CLI tests covering json/empty/healthy/attention-exit/refresh+waiting/limit-validation). Kept C901 at baseline by extracting `_row_tag`/`_row_detail`/`_print_row_extras` (a branchy renderer hits 11 fast).
- **Live-validated** against the real 16-expert roster: rendered correctly, surfaced that 4 project-relevant experts ("Agentic Coding Tools", "AI Cost Optimization", "Deep Research Systems", "Local LLM Operations") exist but were never synced (empty) — exactly the visibility the command is for. Full lint mirror green; $0 this slice.

## 2026-06-21 — Expert Fleet autopilot: research, design, roadmap + the monthly-reserve correctness fix

- **Strategic alignment check (folded here, not a parallel doc).** Re-read README/ROADMAP/AGENTS/AGENTIC_BALANCE + the fleet/scheduling/budget code. Vision confirmed: a roster of always-fresh experts maintained mostly at $0 (local + free search + plan quota), with a monthly reserve (~$20) that is a pool rarely touched, the host owning the schedule, metered spend only for targeted reasons. Created CURRENT-STATE-ANALYSIS as this entry (CLAUDE.md/AGENTS.md mandate single-source-of-truth, no drift — a standalone analysis file would rot).
- **Three research sweeps ($0, free web)** grounded the design: (1) refresh economics — ~60% of naïve refresh finds nothing changed; the win is a $0 ETag/304 + feed/sitemap + content-hash skip *before* model time; adaptive cadence sub-linear in volatility (never proportional — it starves the roster); reinforce-on-confirmation not on age. (2) Budget governance — reserve + per-expert soft allowance + per-run cap; degradation tiers NORMAL/CONSERVE/LOCAL-ONLY/PAUSE-METERED (degrade, don't fail); a value-of-spend gate (`gap_closure×value×urgency×volatility > cost_multiple×est`). (3) Scheduling — OS scheduler + in-verb `filelock` overlap guard + jitter beats any in-process daemon for a solo project; Win11 Modern Standby can't guarantee punctual wake, so design for catch-up + idempotency; a cross-expert `deepr fleet status` over existing `loop_runs.jsonl` + an off-box dead-man's-switch.
- **Design doc** `docs/design/expert-fleet.md`: the three pillars, every invariant preserved (no daemon, no new datastore, $0 read side, no-surprise-bills, plan-quota explicit-only, contested never throttled), and an 8-step smallest-shippable-first sequence.
- **Roadmap** Phase 4d added (Expert Fleet autopilot), and the 2026-06-20 external-review reconciliation note already records adopt/reject vs the "epistemic OS" proposal.
- **SHIPPED — concurrency-safe monthly reservation.** Confirmed defect: `check_and_reserve` projected daily spend *with* in-flight reservations but monthly *without* (`projected_monthly = monthly_cost + estimated_cost`), so under a low monthly reserve — exactly the $20 fleet case where daily headroom is large — N parallel callers all read the same stale total and over-commit by up to N×. Fixed with a `_reserved_monthly` pool symmetric to `_reserved_daily` (included in the projection; incremented on reserve; released on settle/refund under the one lock). TDD: 3 new regression tests (settle, refund, parallel-monthly-block) + the existing 7; 58 cost_safety tests green. Kept `cost_safety.py` under the 1000-line ceiling by tightening a docstring rather than splitting (splitting for tidiness is the STOP-banner anti-pattern). Full lint mirror green; spend this milestone $0 (research was free), lifetime ~$0.65 of $5.

## 2026-06-20 — Expert portraits, refreshed screenshots, and the expert-library-as-team vision

- **Portraits, consistent + settable style**: `portrait_style()` (`DEEPR_PORTRAIT_STYLE` / `--style`, house default) so a roster shares one look; new `deepr expert portrait [--all|--missing-only]` (own module `expert_portrait.py`) generate->attach->save->ledger. Generated consistent-style portraits for all 15 experts (~$0.56).
- **Dev portrait rendering fixed**: vite now proxies `/portraits` to the backend (was SPA-fallback -> placeholder icons; dev now matches prod).
- **Regenerated all 10 README screenshots** from live data: the expert hub/profile show real portraits + sourced beliefs + `$0.00` spent (verified visually).
- **Expert-library vision** (`docs/design/expert-library.md`): a roster maintained at ~$0 (local/plan), consulted by agents as a *dynamic team*; sequenced refinements - library-wide maintenance, expert routing, a `consult` team-assembly verb.
- **Team dynamic validated live**: one cross-domain question -> 2 relevant experts -> distinct grounded perspectives (Tardigrade cellular survival; Antarctic thermoregulation), 90% confidence each.
- **Red->green discipline**: the portrait command in the capped `experts.py` tripped the file-size ratchet, then (unmasked) the C901 ratchet; fixed by extracting to `expert_portrait.py` with module-level helpers. Recorded the full lint-job mirror in SKILLS so it doesn't recur. All CI-green; spend ~$0.65 of the $5 cap.

## 2026-06-20 — Live $0-expert validation: fixed free web search (ddgs) + benchmark path bug

- **Live validation on a real machine**: `deepr capacity fleet`/`--probe` correctly saw all 7 plan CLIs + Ollama (12 models, qwen2.5-coder:32b admitted); made 5 experts for **$0.00**; auth-mode gate correctly flagged codex/claude/grok as `metered` (API keys in env).
- **Bug: free web search was dead.** The keyless backend imported the deprecated `duckduckgo_search`, whose endpoint now returns 0 results -> every `sync --local --fresh-context` got "no sources" -> no $0 knowledge. Fixed `web_search.py` to prefer the maintained `ddgs` package (legacy fallback), run the blocking query off the event loop, and degrade gracefully on rate-limit/network. Declared `ddgs` as a `search` extra in `[full]`. Regression tests added; the broken-by-install legacy test updated.
- **Validated the $0 knowledge loop end to end**: `expert sync --local --fresh-context` then retrieved 5 sources via ddgs and the local qwen-32b extracted **17 grounded beliefs at $0.000** with a source-pack artifact. Real, sourced, queryable expert knowledge for free.
- **Bug: `--auto --preview` printed "Background eval failed (rc=2)"** - `benchmark_models.py` path computed with wrong `parents[N]` in both `eval.py` and `auto_mode.py` (pointed at nonexistent `src/scripts/`). Fixed both, made the auto-mode eval degrade quietly when the script is absent (pipx installs), kept C901 at baseline by extracting a module-level helper, regression test pins both paths. (commit f9a5902, CI green.)
- **Bug: new experts on evergreen topics never populated.** `sync` is delta-only ("what changed lately"), so a brand-new expert on a stable topic (coffee, castles) correctly found nothing and gained 0 beliefs. Fixed `build_freshness_query`: the FIRST sync (no `last_synced`) now establishes a comprehensive, sourced baseline; later syncs stay delta. Validated live end-to-end: a fresh "Coffee Brewing Methods" expert gained **+23 grounded beliefs at $0.000** on first sync via free ddgs + local qwen (vs 0 before); the fast-moving "Plan-Quota Capacity" expert had already gained +17. All three fixes this round are CI-green on main (eb46650, f9a5902, aaff1bd).
- **Net:** the "$0 experts with real, sourced knowledge on local + free search" loop now works on ANY topic, validated live, with budget guards holding at $0.000 and bounded per-topic runs (no runaway).

## 2026-06-20 — Plan-quota auto-routing via operator admission (the fleet's "auto" made real)

- `deepr capacity admit-plan <codex|claude|opencode> --task-class <sync|absorb>` (+ `revoke-plan`): explicit, dated, safety-gated operator opt-in to auto-route maintenance onto a subscription. Stored `plan:<id>` in the shared admission store; shown separately in `deepr capacity`.
- Waterfall auto rung rewritten honestly: instead of waiting on a remaining-quota meter the CLIs don't expose, `_choose_plan_quota` auto-selects an installed + plan-authed + **admitted** + not-in-cooldown backend (`require_observed_quota=False`). Reset-aware: an `EXHAUSTED` event with a future `reset_at` blocks; once it passes the backend self-heals. API-key env still refuses the backend as plan capacity; metered stays the budget-gated last resort.
- Local-admission lookup filtered to exclude `plan:*` keys (clean separation).
- Tests rewritten for the admission model (admitted→routes, not-admitted→metered, exhausted-future→metered, exhausted-past-reset→re-routes, api-key→blocked, copilot-not-auto-routable) + admit/revoke CLI round-trip, api-key block, choice restricted to auto-routable. Waterfall 100% coverage; ruff + ratchets baseline; 319 suite green.

## 2026-06-20 — route-gaps --plan parity (gap-fill on prepaid capacity)

- `expert route-gaps --execute` gains `--local` / `--api` / `--plan <id>` / `--plan-model`: gap-fill runs research + verified extraction on owned/prepaid capacity via one client (helper `_build_gap_fill_engine`), default stays metered. Scheduled recurring fills now proceed on owned/prepaid instead of waiting; loop records the real `capacity_source`.
- All three research-bearing maintenance loop-closers (sync, absorb, route-gaps) now support `--plan`. The story holds: scheduled expert maintenance on subscriptions you already pay for, $0 at the margin, no silent metered call.
- Tests: route-gaps `--plan` happy path + loop `capacity_source` assertions; 311 cli+experts+backends green; ruff + C901/S ratchets at baseline.

## 2026-06-20 — Plan-quota fleet view + absorb parity + reset times

- `expert absorb --plan <id>`: extraction parity with sync on prepaid capacity, same safety gate. Tests + CI green.
- `deepr capacity fleet`: one read-only $0 dashboard over all 7 CLIs — installed, auth mode (metered when an API key is set), routability (auto/explicit/metered), and latest observed quota state (active/exhausted/quarantined/unobserved) with reset time. Builder `fleet.build_fleet_status`, versioned `deepr-plan-fleet-v1` payload.
- Reset times made real: `parse_reset_after_seconds` extracts a relative duration from vendor exhaustion messages ("Try again in 3h 42m", "Resets in 2h15m30s") and the chat client records `reset_at` on EXHAUSTED events; monthly pools with no countdown stay honestly unknown.
- Validation ($0): new tests for fleet (11), reset parser (5), absorb --plan (3), reset recording (1), fleet CLI (3); coverage 94.6% on plan_quota; ruff + C901/S ratchets at baseline; full suites green.

## 2026-06-20 — Plan-quota CLI execution backends (ROADMAP Phase 6)

- Shipped plan-quota CLI execution: drive vendor coding/agent CLIs as
  $0-at-margin research backends for expert maintenance, behind a deterministic
  no-surprise-bills gate. New package `src/deepr/backends/plan_quota/`:
  `cli_runner` (safe async subprocess), `safety` (auth-mode + ack gate),
  `adapters` (declarative registry of 7 CLIs from cited June-2026 specs),
  `client` (`PlanQuotaChatClient` CLI-as-chat shim serving research + verified
  extraction, plus `make_plan_quota_research_fn`, `probe_plan_quota`).
- Honesty model: codex/claude/opencode are auto-routable (free-at-margin,
  ToS-clean); kiro/grok/antigravity are explicit-`--plan`-only with printed ToS
  notes; copilot is off-by-default (metered per token since 2026-06-01). An
  API-key-authenticated CLI is refused as plan capacity.
- Waterfall: `BACKEND_PLAN_QUOTA`, extended `BackendChoice`, gated auto rung
  (off until an observed remaining-quota window exists), `choose_plan_quota_backend`
  for explicit selection.
- CLI: `deepr expert sync --plan <id> [--plan-model]` runs the whole sync on
  prepaid capacity (research + extraction via one client, no silent metered
  call); `deepr capacity probe-plan <id>` validates a backend works.
- Every call writes `quota_ledger.jsonl` (usage / terminal exhaustion) and a
  `$0` `cost_ledger.jsonl` entry with quota units, so `costs show` and anomaly
  detection see volume even at $0 marginal cost.
- Docs: design note `docs/design/plan-quota-cli-backends.md`; AGENTIC_BALANCE
  surfaces row; ROADMAP Phase 6 + Current Status; README capacity section;
  AGENTS.md capacity-honesty bullet.
- Validation ($0/local): full unit suite 6261 passed / 8 skipped; new-module
  coverage 95% (waterfall 100%); ruff check+format clean; docs-consistency OK.
- Confirmed via research: Anthropic paused the 2026-06-15 headless credit-pool
  change (claude `-p` draws the plan window again); GitHub Copilot moved to
  usage-based billing 2026-06-01 (metered).
- Open follow-ups: live remaining-quota probe to enable auto-routing; capacity
  display id join for kiro/antigravity; opencode per-run provider auth-type
  check; antigravity PTY wrapper for headless capture.

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
- Extended indirect prompt-injection boundaries to local document review,
  campaign context summarization, completed-research review, company-intelligence
  reuse, and team-result synthesis. These paths now wrap untrusted source blocks
  before model reuse without changing the semantic verification gates.
- Prepared the `v2.17.2` patch release metadata so the public release tracks
  the completed prompt-boundary hardening slice.
- Added the first local agentic red-team metric slice: `deepr eval red-team`
  now runs `$0` prompt-boundary, tool-spoofing, data-exfiltration, jailbreak,
  and memory trust-floor probes, reports attack-success-rate, and fails if a
  built-in attack succeeds.
- Prepared the `v2.18.0` minor release metadata so the public release tracks
  the red-team metrics command and structured tool-spoof neutralization.
- Added MCP read-path hardening for derived expert handoff and loop-status
  payloads. Host-facing payload strings now sanitize directive and tool-spoof
  canaries before downstream consumption, while canonical expert state remains
  unchanged.
- Extended `deepr eval red-team` with `$0` MCP handoff and loop-status
  read-path canaries. The built-in suite now reports 13/13 blocked cases.
- Prepared the `v2.18.1` patch release metadata so the public release tracks
  the MCP read-boundary hardening slice.
- Added `deepr eval red-team --save`, which writes `$0` attack-success reports
  under `data/benchmarks/red_team_*.json` and includes `saved_to` in JSON
  output for release-to-release trend tracking.
- Prepared the `v2.19.0` release metadata so the public release tracks saved
  red-team trend artifacts.
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
