# Design: Plan-Quota and Local Backends (capacity waterfall)

Target: v2.16 (Phase 6). Status: implementation in progress, researched June 2026 (vendor
surfaces verified; re-verify at implementation - this market moves
monthly).

Current implementation: `CostModel`/`BackendKind` types and read-only
`deepr capacity` detection (step 2); the `local-ollama` backend and `--local`
execution (step 4 substrate); and eval-gated **local admission** with automatic
owned-capacity-first selection for expert maintenance - `deepr capacity admit`
/ `admissions` / `revoke`, and `expert sync`/`absorb` auto-routing to an
admitted local model at $0 before metered API (the local rung of step 5, with
`--local`/`--api` overrides); the normalized `ResearchBackend` profile; plus
the append-only `quota_ledger.jsonl` substrate and `deepr capacity`
quota-state visibility; and the pure backend eligibility gate over
`ResearchBackend` plus `QuotaState`; and the pure backend selector that orders
eligible capacity by the waterfall and enforces optional measured quality
floors; `deepr eval local`, a local-Ollama comparison with either a local LLM
judge or an explicitly approved CLI judge for producing review evidence before
admission; `deepr capacity admit --from-eval latest`, which turns saved
zero-cost local eval artifacts into admission records; runtime admitted-score
quality-floor selection for expert maintenance; and `deepr capacity next` for
ranked local setup, admission, eval refresh, and fallback guidance. Not yet
built: the plan-quota CLI adapters, live window/credit probes, adapter writes,
and scheduler integration.

## Problem

Most operators already pay for capacity Deepr never uses: subscription
plans with included quota (Claude Max credit pool, ChatGPT Plus / Codex
5-hour windows, Antigravity weekly compute, Kiro monthly credits) and
owned hardware (RTX-class GPUs running Ollama). Deepr routes everything to
metered APIs. The inversion: metered API should be the *explicit last
resort*, and "I think this is free" must never silently become a bill.

## Design

### Backend abstraction

A `ResearchBackend` sits one level above providers: `api_metered`
(today's path), `plan_quota` (drive a vendor CLI in headless mode under
its subscription auth), `local` (Ollama/opencode). Each backend declares a
`CostModel`: `metered | credit_pool | rolling_window | calendar_window |
owned_hardware`. The router consults backends in waterfall order:

    local (if eval-admitted) -> plan_quota (if window open) -> api_metered (budget-gated)

Measured quality gates are part of selection: a backend is routable only when
its task score clears the floor. The selector enforces numeric evidence; evals
and model-based review produce the score. Free-but-wrong is not a bargain.

### Engine vs capacity (the key abstraction)

Researching the June 2026 CLI field (survey below) surfaced a split the original
single-adapter-per-vendor model missed: most CLIs are either an **execution
engine** or a **capacity source**, and the two are separable.

- **Engines** (Aider, opencode, Crush, Continue `cn`, Cline, Goose) are
  open-source, bring-your-own-key drivers. Most accept an Anthropic- or
  OpenAI-compatible base URL, so one engine can be pointed at *any* endpoint.
- **Capacity sources** are subscriptions with included quota exposed over a
  compatible endpoint (GLM Coding Plan, Qwen/Alibaba Coding Plan, Kimi Code,
  Cursor in Auto mode), or first-party headless CLIs with their own pool
  (Claude Code, Copilot CLI, Kiro).

So the adapter shape is a small matrix - an `engine` (how we drive it) times a
`capacity` endpoint (whose quota pays) - not one bespoke adapter per product.
That is less code, less churn, and lets a single GLM/Qwen/Kimi subscription be
drained through whichever engine is installed. `local-ollama` remains the only
genuine `$0 owned_hardware` source and stays the priority rung.

### Vendor surfaces (verified 2026-06-13; re-verify before building - this churns monthly)

`local-ollama` (genuine $0) ships first. Among prepaid rungs, Copilot CLI and
Cursor (Auto mode) are the most automation-friendly; Claude Code's credit pool
is the cleanest *hard-stoppable* budget. Every first-party CLI below has a
hard-stop-able mode; the mandatory guard is to keep overflow/overage OFF and
never rely on a vendor to stop billing.

| Surface | Headless invocation | Cost model | Default exhaustion | Build priority |
|---|---|---|---|---|
| `local-ollama` | HTTP `/v1` | owned_hardware ($0) | n/a | 1 (shipped) |
| Claude Code | `claude -p --output-format json` | credit_pool (separate monthly $, API rates, from 2026-06-15) | hard-stop; overflow opt-in, keep OFF | high |
| GitHub Copilot CLI | `copilot -p --allow-all-tools` (`GH_TOKEN`) | credit_pool (monthly) -> admin-capped metered overage | hard-stop, admin-toggle | high |
| Cursor CLI | `cursor-agent -p --output-format json` | credit_pool = plan price; **Auto model is free** | quota | high (Auto = free capacity) |
| Codex CLI | `codex exec --json` (`CODEX_API_KEY`) | sub rolling+weekly; metered via API key | sub: 429; API: uncapped | medium (sub auth ToS-gray) |
| Kimi Code | `kimi -p` | rolling_window (5h, ~$19/mo) | hard-stop | medium |
| GLM Coding Plan | any engine + base-url/key | credit_pool, quarterly reset, no per-token | quota | medium (cleanest endpoint swap) |
| Qwen Code | `qwen` headless + plan key | Coding Plan sub / metered | quota | low (free OAuth tier died 2026-04-15) |
| Kiro | `kiro-cli chat --no-interactive` (`KIRO_API_KEY`) | credit_pool (monthly) + **uncapped** overage $0.04/cr | overage OFF by default; if ON, silent month-end bill | medium (mandatory reserve floor) |
| Grok Build | `grok -p` (`XAI_API_KEY`) | metered (API); consumer-sub OAuth gray-area | spend-based | metered-only (no plan_quota rung) |
| Antigravity (`agy`) | SDK `google.antigravity`; CLI `-p` unconfirmed | rolling (5h) + weekly hard cap; opt-in credit overage | up to 7-day lockout; overage off | low (quota-opaque, interactive auth) |

Dropped from the plan since the first draft: **Gemini CLI** (retired for
consumers 2026-06-18, enterprise-only after); **Amazon Q Developer CLI**
(sunsetting into Kiro, signups blocked 2026-05-15); **Grok consumer
subscriptions** (no sanctioned headless path - xAI's data-sharing API credits
flow through `api_metered` as a price override). **Amp / OpenCode Zen /
Goose+Tetrate** are prepaid-but-metered (zero markup) - no arbitrage over a
plain API key, so not worth a plan_quota adapter. **Warp** has no clean local
headless one-shot. Confidence caveats (each load-bearing claim is sourced in
the 2026-06-13 research): exact quota numbers, subscription prices, and the
gray-area ToS postures move monthly and must be re-checked against
`--version` / vendor docs before being hard-coded.

### Quota ledger

A per-backend ledger (same append-only pattern as the cost ledger)
records: window opens/closes, units consumed (vendor-reported where
available, estimated otherwise), and a *conservative* remaining estimate.
Invariants: when remaining-confidence is low, treat the window as
exhausted; a `plan_quota` backend whose vendor bills overage (Kiro) gets a
hard reserve floor (default 10%) that the waterfall never dips into.

The ledger substrate exists as
`data/capacity/quota_ledger.jsonl` (or `DEEPR_CAPACITY_DATA_DIR`) with typed
events for usage, window sightings, exhaustion, overage state, reset
observations, and quarantine. `deepr capacity` reads and summarizes the latest
local observation per backend/account without invoking vendor CLIs. Remaining
work is adapter-side probes that populate the ledger and scheduler decisions
that consume it.

`evaluate_backend_eligibility` consumes a
`ResearchBackend` and the observed `QuotaState` list before execution. It
blocks unavailable backends, unsupported task classes, metered backends without
an explicit budget gate, missing quota observations, unknown remaining quota,
exhausted windows, quarantines, overage-enabled plan backends, and reserve-floor
breaches. If a backend has multiple account-scoped quota states, the gate
selects an eligible account when one exists; otherwise it returns the
highest-priority block reason for the pool.

`select_capacity_backend` consumes normalized backends, quota states, an
optional task class, and optional per-backend quality scores. It sorts candidates
`local -> plan_quota -> api_metered`, applies eligibility, applies the measured
quality floor, and returns a structured reason plus every candidate gate result.
It performs no I/O, so schedulers can preview and log the decision before any
adapter executes.

### Eval-gated local admission

`local` backends are admitted per task-class only after `deepr eval` runs
against them and the operator accepts the quality report. Models change;
admission expires (configurable, default 90 days) and re-eval is prompted.
No eval, no admission - "it's free" never overrides "it's good enough".

`deepr eval local` is the first cheap eval path for this: candidate Ollama
models answer a small prompt set, and a judge scores each answer against a
rubric. The default judge is another local Ollama model. An operator may also
use a CLI judge with `--judge-cli grok` or `--judge-command`, but only with
`--allow-cli-judge`; Deepr cannot prove whether a vendor CLI is backed by
subscription quota, prepaid credits, or metered credentials. The judge decides
semantic quality; Deepr validates JSON shape, score range, latency, Deepr
metered cost, prompt failures, and artifact output. The score is evidence for a
human admission decision and later for measured quality floors.

`deepr capacity admit --from-eval` closes the manual evidence handoff. It loads
a saved local comparison artifact, chooses the named model or the artifact
winner, rejects nonzero-cost artifacts, enforces score ranges and a default
minimum score, rejects failed prompt attempts, and writes the score plus artifact
summary into the machine-local admission ledger only after the operator accepts
the admission. `--from-eval latest` is the convenience path for the newest
`data/benchmarks/local_compare_*.json` artifact.

Automatic expert-maintenance routing consumes the admitted score at runtime.
Each live admission becomes a normalized local `ResearchBackend`; the waterfall
selector receives the admission score as measured quality evidence and enforces
the same default floor (`0.70`). Scoreless manual admissions remain visible for
audit, but they do not silently take over `expert sync` or `expert absorb`.
`--local` remains the explicit operator override.

`deepr capacity next` is the first quality-of-life surface over those gates. It
does not run research or make provider calls; it ranks the current local-routing
block reason, Ollama setup, latest usable eval-artifact admission, eval refresh,
and explicit metered fallback for a task class.

### No-surprise-bills invariants

1. Every backend declares its cost model; only `api_metered` may produce
   a nonzero ledger charge.
2. A `plan_quota` adapter that detects it has fallen back to metered
   billing (vendor-side changes) aborts the call and quarantines itself.
3. Waterfall decisions are logged with the same trace IDs as research
   jobs: "why did this run on X" is always answerable.
4. Kiro-class overage: hard-stop at reserve floor; overage requires an
   explicit per-run `--allow-overage`.

## Order of operations

Steps 1-7 are shipped or substantially built (see Status at top); adapter and
scheduler work remains.

1. `CostModel`/`BackendKind` types + read-only `deepr capacity` detection. (done)
2. `local-ollama` execution via the injectable seams + `--local`. (done)
3. Eval-gated **local admission** + automatic owned-capacity-first selection
   for `expert sync`/`absorb` (`deepr capacity admit`). (done - the local rung)
4. `ResearchBackend` abstraction: wrap today's provider path as `api_metered`,
   and model the `engine` x `capacity` matrix (one BYO-base-url engine driver,
   many capacity endpoints) rather than one adapter per vendor. (done)
5. Quota ledger substrate + `deepr capacity` quota-state visibility. (done)
   Window/credit probes per capacity source remain.
6. Backend eligibility gate over `ResearchBackend` and observed `QuotaState`.
   (done)
7. Backend selector over eligibility plus measured quality floors. (done)
8. Local comparison with a local LLM judge or explicit CLI judge for admission
   evidence. (done)
9. Saved local eval artifacts feed admission with deterministic gates. (done)
10. Feed admitted local scores into runtime quality-floor selection. (done)
11. Capacity quality-of-life path: ranked next actions and latest-artifact
   hints are in place. Remaining: concrete job block-reason previews and
   scheduler suggestions.
12. First plan_quota rungs, in priority order from the vendor survey: the
   highest-confidence first-party CLIs and endpoint-backed coding plans, each
   behind an explicit opt-in and a "sanctioned as of <date>" kill switch.
13. Multi-account pools (N accounts of one vendor as one pooled backend) - last,
   it multiplies an already-working mechanism.

## Open questions

- Output-quality normalization: plan CLIs return chat-style answers, not
  deep-research reports; how much re-synthesis is worth the savings (lean:
  plan backends serve sync/freshness/extraction tiers, not campaign-grade
  deep research).
- ToS drift: each adapter ships with a "sanctioned as of <date>" note and
  a kill switch.

## Exit criteria

`deepr capacity` shows live window/credit state across configured
backends; a sync run drains plan quota before touching metered API; the
cost ledger shows $0 for plan-served work; quarantine + reserve-floor
paths covered by fault-injection tests.
