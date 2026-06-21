# The expert fleet: always-fresh experts on a monthly reserve, mostly at $0

Status: design note, 2026-06-21. Builds directly on
[expert-library.md](expert-library.md) (the roster vision),
[capacity-waterfall.md](capacity-waterfall.md) (local → plan → metered),
[belief-lifecycle.md](belief-lifecycle.md) (decay, bi-temporal, $0 health-check),
and [verified-expert-loops.md](verified-expert-loops.md) (the loop contract).
Read [AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) and the ROADMAP STOP
banner first — this note must not turn Deepr into an orchestrator or grow an
always-on service. It sharpens *how the roster stays current on its own*.

## The target

A roster of domain experts that an operator (or an agent) keeps **always up to
date as a fleet**, where:

- **Most maintenance is $0** — local Ollama + free web search + the
  comprehensive-then-delta sync model already prove this (see expert-library.md).
- **A monthly reserve (default ~$20) is a pool you mostly don't touch**, not a
  spend target. Routine upkeep never approaches it; metered money is spent only
  for *targeted* reasons.
- **Scheduling belongs to the host** (Task Scheduler / cron / systemd), per the
  standing doctrine "hosts own the schedule, Deepr owns the verbs." Deepr does
  not run a daemon.
- **The operator can see fleet health at a glance** without watching it.

This is the connective tissue that turns "a pile of self-maintaining experts"
into "a fleet that maintains itself well, within a budget, and tells you when it
can't."

The design rests on three research-grounded pillars: **refresh economics** (when
to spend work at all), **budget governance** (what a metered dollar must justify
and how the pool degrades), and **scheduling + observability** (how the host
drives it reliably and how you know it's healthy).

---

## Pillar 1 — Refresh economics: maximize freshness per $0

The expensive step in maintaining an expert is not the fetch — it is the
LLM-mediated extraction/absorb (Deepr's own cited finding: *construction cost
dominates lifecycle cost*, belief-lifecycle.md). The crawler literature is
blunt about the prize: **~60% of naïve re-fetch work finds nothing changed**
(Cho/Garcia-Molina TODS 2003; Fetterly et al.; Elsas et al.). So the single
highest-leverage move is a **$0 "did anything change?" gate that runs before any
model time is spent.**

### 1.1 The pre-sync change-detection gate ($0, the biggest win)

Before a sync invokes the local model, decide *if* there is anything to do,
cheapest signal first:

1. **HTTP conditional requests** — store each tracked source's `ETag` /
   `Last-Modified` from the last sync; send `If-None-Match` / `If-Modified-Since`.
   A `304 Not Modified` is essentially free (no body, no parse, no model) → skip
   the source.
2. **Feeds / sitemaps as hints** — if the expert tracks an RSS/Atom feed or a
   sitemap, read it first and only consider entries whose `lastmod` advanced.
   Treat `lastmod`/`Last-Modified` as a *hint*, never proof (sites lie).
3. **Content hash** — for anything actually fetched, hash the *extracted main
   content* (not raw HTML, which churns on ads/timestamps) against the stored
   hash; absorb only on a real diff.

Only a real diff reaches the expensive extraction/absorb path. All three checks
are $0 and live inside the existing fresh-context/health-check path, preserving
the "$0 read side" invariant. **This is the highest-leverage freshness change
available** and should land first.

### 1.2 Adaptive cadence — sub-linear in volatility, never proportional

Estimate each expert's change rate λ online from the single changed / not-changed
bit each sync already produces (a Poisson-rate estimator; $0, deterministic).
Bucket into tiers — volatile (daily, capped), moderate (weekly), evergreen
(monthly+, mostly health-checked). The crucial, most-violated crawler result:
**under a fixed budget the *uniform* policy beats the *proportional* one** — do
**not** set cadence proportional to λ, because chasing the fastest-changing
sources starves everything else and they go stale again immediately. Cadence
rises *sub-linearly* with λ; sources that change faster than any sustainable
cadence are flagged "inherently volatile — answer with explicit staleness,"
not refreshed harder.

### 1.3 Decay-driven targeting + reinforce-on-confirmation

A due sync targets the beliefs whose decayed, trust-capped confidence has fallen
below a "needs-refresh" floor (above the existing archive floor) *and* that are
still query-relevant. When a sync re-verifies a belief, bump confidence /
`updated_at`; when it contradicts one, cut confidence and set `invalidated_at`.
**Reinforce on confirmation, not on retrieval** — this turns ordinary operation
into a continuous validation signal and avoids the documented "decay-by-age
alone" anti-pattern. Honor existing invariants: usage only *protects* from
archival; contested beliefs are never auto-archived and are **exempt from cadence
throttling** (a contested belief is a standing reason to keep checking).

---

## Pillar 2 — Budget governance: a reserve you mostly don't touch

### 2.1 Three nested tiers (not one knob)

1. **Hard monthly reserve** (default $20) — the fail-closed outer wall;
   `ABSOLUTE_MAX_MONTHLY` remains the never-exceed backstop above it.
2. **Per-expert soft allowance** — a *target* share (`pool_remaining /
   max(active_experts, 1)`), not a hard cap, so an idle expert's unused share
   flows to a busy one. Crossing your own soft allowance doesn't block; it
   downgrades that expert to targeted-spend-only mode and is required before any
   single expert may consume the last ~20% of the pool. This prevents one expert
   starving the roster without static equal-splitting.
3. **Per-run / per-op cap** — the runaway-loop guard (the circuit breaker +
   `ABSOLUTE_MAX_PER_OPERATION`). Stays strict; this is the "$1000 overnight"
   backstop.

The waterfall keeps day-to-day spend at $0, so the $20 is a genuine reserve.

### 2.2 Graceful degradation as the pool depletes (resumable, never fail)

Drive behavior off `monthly_remaining = max_monthly − (monthly_cost +
reserved_monthly)`:

| Pool used | Mode | Behavior |
|---|---|---|
| 0–70 % | **NORMAL** | Waterfall as-is; metered allowed when the spend gate (2.4) passes. |
| 70–90 % | **CONSERVE** | Metered only for urgent / high-value work (raised gate bar); non-urgent metered work deferred + queued; one warning alert. |
| 90–100 % | **LOCAL-ONLY** | Metered API hard-disabled; local/plan rungs only. Eval-admitted local still runs at $0 — the fleet keeps working with reduced capability. |
| ≥ 100 % | **PAUSE-METERED** | All metered work pauses via the existing pausable-limit / resume-message path ("reserve reached; metered paused, resumes next period; local/free continues"). Deferred queue drains at monthly reset. |

This is additive on top of the existing waterfall + `is_pausable_limit` /
`get_resume_message` machinery. Degrade, don't fail.

### 2.3 Concurrency-safe reservations (SHIPPED 2026-06-21)

The reserve-then-settle pattern must count *in-flight* reservations in the cap
projection, or N parallel checks read the same stale total and over-commit. The
daily path already did this; the **monthly path did not** — the primary
over-spend hazard for a low monthly reserve. Fixed: `CostSafetyManager` now
holds a `_reserved_monthly` pool symmetric with `_reserved_daily`, included in
`projected_monthly`, incremented on reserve, and released on settle/refund under
the same lock (regression-tested in `test_cost_safety_reservations.py`).

Remaining hardening (tracked, not yet built): a **reservation TTL/sweeper** —
with a tight $20 pool a leaked reservation (caller forgets to settle/refund)
permanently shrinks the pool until restart; reap reservations older than the max
plausible run time.

### 2.4 The targeted-spend gate — what a metered dollar must justify

Metered spend is reached only *after* the waterfall has exhausted local + plan
capacity. At that point, spend iff:

```
gap_closure × value × urgency × volatility  >  cost_multiple × estimated_cost
```

- `gap_closure ∈ [0,1]` — expected fraction of the open gap this closes (proxy:
  `1 − current_confidence`, or eval-measured score lift).
- `value ∈ [0,1]` — importance of this expert/task to current objectives.
- `urgency ∈ [0,1]` — deadline / is-this-blocking.
- `volatility ∈ [0,1]` — likelihood existing knowledge is stale (the λ / surprise
  proxy from Pillar 1).
- `cost_multiple` — the depletion-tiered hurdle: NORMAL `1.0`, CONSERVE `2.0`,
  LOCAL-ONLY `∞` (never spend).

Refuse metered refresh when `gap_closure < 0.2` or `volatility < 0.2` (already
confident *and* data unlikely to have changed — don't pay to refresh the
mundane). The computed score and decision are written to the append-only cost
ledger so "why did we spend / why did we defer" is always answerable. This
unifies value-of-information, surprise-gating, and urgency weighting into one
comparison and respects AGENTS.md: estimate cost first, budgets are ceilings,
plan-quota stays explicit-only (never auto-routed under pressure).

### 2.5 When you can't win, say so (free) instead of spending more

For inherently volatile topics that exceed any sustainable cadence, the
cost-optimal move is **not** more spend — it's honest staleness. Serve the
decayed answer now with a staleness flag (`stale-while-revalidate`), revalidate
on the next free cycle. Deepr already has the machinery (confidence decay,
bi-temporal world-time, continuity "staleness honesty").

---

## Pillar 3 — Scheduling + observability (no always-on service)

### 3.1 OS scheduler + a thin in-verb guard (not a daemon, not APScheduler)

An in-process scheduler (APScheduler et al.) does **not** remove the daemon
problem — it relocates it into a long-lived Python process you must supervise,
persist, and restart, which *is* the always-on service the project rejects. The
OS scheduler is already supervised by the init system, starts at boot, and logs
centrally; the verb becomes a "run once and exit" program that's trivial to test
and fire manually. So:

- **Overlap guard in the verb, not the host.** Wrap each schedulable verb
  (`expert sync`, `health-check`, `reflect`, future `campaign`) in a
  non-blocking cross-platform `filelock` keyed by `expert + verb`. On contention,
  exit 0 with a recorded skip (previous run still active) rather than failing.
  Cross-platform is required (Windows-primary rules out `flock`) and the lock is
  crash-safe. Belt-and-suspenders: also set Task Scheduler "Do not start a new
  instance."
- **Jitter in the verb** (`--jitter`), since cron/Task Scheduler can't jitter
  natively and a roster firing on the same minute is a thundering herd against
  rate-limited plan-quota CLIs. A stable per-expert offset derived from the name
  is reproducible.
- **Idempotency** — thread an idempotency key (`expert + verb + due-window`, or
  `campaign id + phase index`) through any side-effecting call so a retried or
  duplicated tick resumes rather than re-bills. "Resume is just re-invoking the
  verb."

### 3.2 Design for catch-up, not punctuality (the Win11 sleep reality)

A sleeping Windows 11 laptop **cannot guarantee a job fires at its exact
wall-clock time** — Modern Standby (S0) throttles wake timers, and three Task
Scheduler laptop defaults actively block runs. Therefore Deepr's verbs are
"run whenever, figure out what's due" (delta-driven), and the host recipe must
enable catch-up. The load-bearing **non-default** Task Scheduler settings:

- Trigger: your cadence **+ "Run task as soon as possible after a scheduled start
  is missed"** (`StartWhenAvailable`).
- General: **"Run whether user is logged on or not."**
- Conditions: **uncheck "Start only on AC power"** and **"Stop if switches to
  battery"**; check **"Wake the computer to run this task"** (and enable *Allow
  wake timers* for AC **and** DC in Power Options).
- Settings: **"If the task is already running → Do not start a new instance."**
- Action: `deepr expert sync "<Name>" --scheduled` (already returns structured
  waits; never blind-spends).

Linux/macOS equivalents: cron + a daily catch-up (anacron) or, preferred,
systemd `.timer` with `Persistent=true` (fires once on next boot if a run was
missed) + `RandomizedDelaySec=` for jitter + `WakeSystem=`.

Ship a **`deepr fleet install-schedule`** helper that emits the correct
`schtasks`/XML (Windows), crontab line, and systemd `.timer` — so the operator
doesn't hand-build the non-default settings that are the entire point.

### 3.3 `deepr fleet status` — the cross-expert health surface

The per-expert `loop_status_rollup` (`deepr-loop-status-v1`) and the plan-quota
`capacity fleet` view don't cover roster-wide *agent-run* health; the name
`capacity fleet` is taken, so use **`deepr fleet status`**. It needs **zero new
storage** — it folds the existing per-expert `loop_runs.jsonl` files. Publish as
`deepr-fleet-status-v1` and wire into the web dashboard. One row per expert ×
loop_type:

- **Last run** — timestamp + status + typed `stop_reason`.
- **What changed** — `accepted_changes` / `rejected_changes`, `acceptance_rate`.
- **What it cost** — `budget_spent`, `cost_per_accepted_change`,
  `capacity_source` (owned / prepaid / metered).
- **What failed** — `last_failure` + `failure_reason`.
- **Overdue / stale** — the load-bearing column:
  `last_run.finished_at + expected_interval + grace < now → OVERDUE`.
  `expected_interval` is the one new piece of per-expert/verb config (a small
  `schedule.json`); without it Deepr can't tell "idle" from "broken." Default to
  `interval × 3` when unset.
- **Next action** — the typed `waiting_for_capacity` / `waiting_for_confirmation`
  next-action so the operator sees what's blocking.
- **Roster summary** — `N experts · X overdue · Y waiting · Z failed · $TOTAL
  (window)`; anomalies first, green boring.

`--json` for the versioned payload; human table by default; **non-zero exit when
anything is overdue or failed** so the scheduler can run `fleet status` itself as
a cheap watchdog.

### 3.4 The dead-man's-switch (the one thing a local command can't do)

A local `fleet status` only reports trouble *when you run it* — if the laptop is
asleep, nothing runs it, and a same-host monitor dies with the jobs. Close that
gap with an **optional, off-by-default outbound heartbeat**: on a successful
scheduled verb, POST a run summary (Healthchecks-compatible: `/start`, success,
`/fail`) to a user-configured URL on a **free off-box tier** (healthchecks.io /
Dead Man's Snitch). Off-box is the point — it catches "the laptop never woke up,"
the failure a single-laptop fleet is most exposed to. No self-hosted monitor on
the same laptop; no new always-on service in Deepr.

---

## Boundaries (so this stays Deepr's role)

- **No always-on Deepr daemon, no APScheduler** — hosts own the schedule; Deepr
  owns "run once and exit" verbs. The research is unambiguous that a daemon is
  both heavier and *less* reliable for a solo project.
- **No new datastore** — `fleet status` is a read-rollup over existing
  `loop_runs.jsonl`; the only new persisted bits are per-verb `expected_interval`
  and an optional heartbeat URL.
- **$0 read side preserved** — change-detection, λ-estimation, decay targeting,
  `fleet status`, and the spend gate's inputs are all free.
- **No-surprise-bills preserved** — metered only after the waterfall, only
  through the targeted-spend gate, only under the reserve, always ledgered;
  plan-quota stays explicit-only and is treated as best-effort (vendors don't
  expose remaining quota), so degradation never silently leans on it.
- **Epistemic invariants preserved** — contested beliefs never throttled or
  auto-archived; contradiction-as-signal; trust-floor-capped confidence on every
  emitted claim; the wiki/digest stays a derived view.
- **Not the orchestrator** — the fleet maintains Deepr's *own* experts on a
  schedule the host triggers; it never drives other vendors' agents.

---

## Sequenced slices (smallest shippable first)

1. **[SHIPPED 2026-06-21]** Concurrency-safe monthly reservation (Pillar 2.3) —
   the confirmed correctness defect, fixed with regression tests.
2. **Pre-sync change-detection gate** (Pillar 1.1) — ETag/IMS → 304 skip, feed/
   sitemap hint, content-hash; the highest-leverage freshness-per-$0 change.
3. **`deepr fleet status`** (Pillar 3.3) — cross-expert rollup over existing
   `loop_runs.jsonl`, `deepr-fleet-status-v1`, overdue detection, non-zero exit.
4. **In-verb overlap guard + `--jitter`** (Pillar 3.1) — cross-platform
   `filelock`, recorded skip on contention.
5. **`deepr fleet install-schedule`** (Pillar 3.2) — emits the correct
   non-default Task Scheduler / cron / systemd recipe.
6. **Library-wide maintenance pass** (`expert sync-all`, from expert-library.md)
   — one roll-up `ExpertLoopRun` over due experts through the waterfall.
7. **Budget degradation tiers + targeted-spend gate** (Pillar 2.2 / 2.4) — wire
   the reserve modes and the value-of-spend comparison; ledger the decision.
8. **Reservation TTL/sweeper** (Pillar 2.3) and **optional off-box heartbeat**
   (Pillar 3.4) — the last hardening.

## What NOT to build

- An always-on scheduler/daemon or APScheduler-as-core.
- A same-laptop self-hosted uptime monitor (dies with the host).
- A new datastore for fleet state (fold the existing ledgers).
- Proportional-to-volatility cadence (starves the roster).
- Auto-routed plan-quota under budget pressure (vendors hide remaining quota).
- Any promise of punctual wake-from-sleep on Win11 (OS limitation; design for
  catch-up + idempotency instead).
