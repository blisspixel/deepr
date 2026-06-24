# Budget degradation tiers + value-of-spend gate

Status: design note, 2026-06-24. Implements the Phase 4d "budget degradation
tiers + targeted-spend gate" item. Additive over the existing
`CostSafetyManager` (`experts/cost_safety.py`) - and deliberately *not* inside
it, because that file sits at the 1000-line file-size cap. Read
[AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) first: this is a deterministic
workflow gate on spend, never a semantic verdict.

## Problem

`CostSafetyManager` already enforces hard daily/monthly caps (a request that
would breach the cap is denied) and a circuit breaker. That is a cliff: under
the cap everything is allowed at full cost; at the cap everything stops. For a
fleet running on a small monthly reserve (the `$20/month` roster), the useful
behavior is a **graded** one - spend freely early in the month, get pickier as
the pool drains, fall back to local-only before the cap, and pause (resumably)
at the cap - and to spend metered dollars only when the expected value of the
result justifies the cost. This is the 2026 FinOps consensus for agentic spend:
graceful degradation and real-time value-gating of expensive calls, not a single
hard ceiling.

## Tiers (graceful degradation off monthly drain)

`drain = monthly_spent / monthly_cap`:

| Tier | Drain | Behavior |
|---|---|---|
| `NORMAL` | `< 0.70` | Metered allowed (after the waterfall) for spend that clears the value gate at the normal hurdle. |
| `CONSERVE` | `0.70-0.90` | Metered only for genuinely high-value/urgent work; the value hurdle rises, so mid-value spend defers. |
| `LOCAL_ONLY` | `0.90-1.00` | Metered hard-off; local/$0 still runs. |
| `PAUSE_METERED` | `>= 1.00` | Metered hard-off, resumable pause; never errors. Local/$0 still runs. |

Local and plan-quota ($0-at-margin) capacity are **never** gated by this policy -
it governs only metered dollars, which the waterfall reaches last.

## Value-of-spend gate (NORMAL / CONSERVE)

A metered op clears the gate when

```
benefit  >=  hurdle
benefit  =  clamp01(gap_closure) * clamp01(value) * clamp01(urgency) * clamp01(volatility)
hurdle   =  cost_multiple(tier) * (est_cost / reference_cost)
```

The four benefit factors are caller-supplied estimates in `[0, 1]` (how much a
gap would close, how valuable the topic is, how urgent, how volatile/likely to
have changed); their product is a strict "all must be high" benefit. The hurdle
**rises as the pool drains** (`cost_multiple(CONSERVE) > cost_multiple(NORMAL)`)
and **rises with the estimated cost** (`est_cost / reference_cost`), so a drained
pool demands more value per dollar. Defaults are calibrated so a default-value
(`0.5` across the board), reference-cost op clears `NORMAL` but defers in
`CONSERVE`; all constants are explicit `SpendPolicyConfig` fields and tunable.

The factors may be estimated by a model upstream, but this module only does the
arithmetic and the threshold comparison - it never derives the factors with a
lexical rule, and it never judges semantic truth. That keeps it on the workflow
side of AGENTIC_BALANCE (determinism on the side-effect: spend).

## Fail-safe direction: toward not spending, resumably

Every denial is **pausable** (defer / use local / wait), never a hard failure,
and the function never raises. Fail-safe toward *not* spending is the correct
direction here precisely because the gate sits after the capacity waterfall:
local/$0 is always still available, so a wrong "deny" costs at most a deferred
metered refresh (the expert can still update locally or next window), while a
wrong "allow" spends real money the operator may not have wanted. This matches
the money-waste-first posture and the "never disable, degrade gracefully"
guidance.

Unknown/garbage inputs fail safe: missing factors default to `0.5`, factors are
clamped to `[0, 1]`, a non-positive cap is treated as "no governance"
(`NORMAL` - the absolute caps in `CostSafetyManager` still protect), and a
non-positive `est_cost` (a free op) clears the gate.

## What ships now vs next

- **Now:** the pure policy (`experts/spend_policy.py`), fully unit-tested, and
  the **tier hard-off wired into `expert sync-all`** - a roster pass that would
  spend metered defers when the tier is `LOCAL_ONLY`/`PAUSE_METERED`, protecting
  the monthly pool on the bulk spender. The current tier is surfaced read-only.
- **Next (documented, not yet wired):** the per-op value gate needs callers to
  produce the four benefit estimates (the scheduler / gap-fill ranker is the
  natural source); wiring it into single `expert sync` and gap-fill, and
  ledgering each defer decision to a dedicated decision log, are follow-ons.
