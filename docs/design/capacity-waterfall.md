# Design: Plan-Quota and Local Backends (capacity waterfall)

Target: v2.16 (Phase 6). Status: design, researched June 2026 (vendor
surfaces verified; re-verify at implementation - this market moves
monthly).

Shipped so far (2026-06-13): `CostModel`/`BackendKind` types and read-only
`deepr capacity` detection (step 2); the `local-ollama` backend and `--local`
execution (step 4 substrate); and eval-gated **local admission** with automatic
owned-capacity-first selection for expert maintenance - `deepr capacity admit`
/ `admissions` / `revoke`, and `expert sync`/`absorb` auto-routing to an
admitted local model at $0 before metered API (the local rung of step 5, with
`--local`/`--api` overrides). Not yet built: the plan-quota CLI adapters and
their quota ledger, and per-task-class quality gates beyond the admission flag.

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

Quality gates run *before* the waterfall: a task above the backend's
admitted quality ceiling skips ahead (free-but-wrong is not a bargain -
the eval-gated admission below is what earns a backend its place).

### Vendor adapters (June 2026 surfaces; verify before building)

**Verified 2026-06-13 (re-sequences the adapters):** Anthropic's June 15, 2026
change moves `claude -p` headless + the Agent SDK off the flat subscription onto
a *separate monthly credit pool* ($20 Pro / $100 Max 5x / $200 Max 20x) billed
**at standard API rates**, that stops when exhausted unless overflow billing is
on. So `cli-claude` is bounded-prepaid-at-API-rates, not free, with a real
overflow-to-bill trap. Consequence: **`local-ollama` (genuinely $0) is the
priority adapter** (shipped first); `cli-claude` drops in priority and its
overflow-OFF / hard-stop guard is mandatory, not optional. Re-verify every CLI
plan's headless economics immediately before building its adapter - this churns.

| Adapter | Mechanism | Quota model | Notes |
|---|---|---|---|
| `cli-claude` | `claude -p` headless | Separate credit pool, API rates (from 2026-06-15) | Stops/overflows when pool empties - overflow MUST be off; lower priority than local |
| `cli-codex` | `codex exec` | 5h rolling windows + weekly cap | Sanctioned; window state probeable |
| `cli-antigravity` | `agy` CLI headless | Weekly compute caps per tier | Gemini CLI dies 2026-06-18; re-verify agy after cutover |
| `cli-kiro` | kiro CLI | Monthly credits, overage $0.04/credit | Overage risk: hard-stop before cap, never rely on vendor stop |
| `local-ollama` | HTTP API | Owned hardware | Schedule-aware (shared GPU with work hours) |

Grok consumer plans have no sanctioned headless path - excluded; xAI's
data-sharing API credits flow through `api_metered` as a price override.

### Quota ledger

A per-backend ledger (same append-only pattern as the cost ledger)
records: window opens/closes, units consumed (vendor-reported where
available, estimated otherwise), and a *conservative* remaining estimate.
Invariants: when remaining-confidence is low, treat the window as
exhausted; a `plan_quota` backend whose vendor bills overage (Kiro) gets a
hard reserve floor (default 10%) that the waterfall never dips into.

### Eval-gated local admission

`local` backends are admitted per task-class only after `deepr eval` runs
against them and the operator accepts the quality report. Models change;
admission expires (configurable, default 90 days) and re-eval is prompted.
No eval, no admission - "it's free" never overrides "it's good enough".

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

1. `ResearchBackend` + `CostModel` types; wrap today's provider path as
   `api_metered` (pure refactor, no behavior change).
2. Quota ledger + window/credit probes (read-only `deepr capacity` status
   command - visibility before routing).
3. First adapter: `cli-claude` (cleanest sanctioned surface, the
   operator's own primary plan) behind an explicit opt-in flag.
4. `local-ollama` + eval-gated admission (reuses `deepr eval`).
5. Waterfall routing with per-task-class quality gates; `cli-codex`,
   `cli-antigravity` (post-cutover), `cli-kiro` (with reserve floor).
6. Multi-account pools (N accounts of the same vendor as one pooled
   backend) - last, it multiplies an already-working mechanism.

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
