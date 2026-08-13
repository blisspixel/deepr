# ADR 0007: Separate cumulative wallet credits from per-job ceilings

Date: 2026-08-13

Status: Accepted

## Context

The attended paid path shipped with one non-configurable `$2` total grant. The
grant was simultaneously cumulative authority and the largest job Deepr could
run. That prevented surprises, but also prevented an operator from knowingly
authorizing a larger research job or a reusable `$50` pool.

## Decision

Use a persistent, operator-funded Deepr wallet for cumulative metered authority
and a separate finite reservation ceiling for every attended job. Funding is
additive and explicit. Settlement draws actual API cost from the wallet. Unused
reservation returns to available capacity. There is no automatic top-up or
overdraft.

Explicit day, week, and month caps remain calendar windows. Their rollover does
not recreate wallet credits, and pre-funding spend in the current window still
counts against a separately configured calendar ceiling.

Provider-side prepaid credits or a provider-enforced hard stop with paid
overage disabled are a mandatory independent boundary for dispatch. Deepr
wallet funding is local authorization only and must never be represented as
moving or verifying provider funds. Both layers apply, and the tighter limit
wins.

The wallet remains unusable by unattended surfaces. Every metered path requires
provider-authoritative account controls; unattended surfaces remain blocked
until their additional execution envelope is also proven.

## Alternatives rejected

- Keep `$2` as a universal maximum. Safe but too limiting for deep research.
- Make every `$2` grant renewable automatically. This is an unbounded loop
  disguised as a small cap.
- Treat the wallet balance as the per-job ceiling. One mistake could reserve
  the entire pool, and the operator would not have named the job exposure.
- Reuse monthly limits as wallet credits. Calendar rollover would recreate
  authority without an explicit top-up.
- Auto-migrate a live v2 grant. Removing its expiry would silently widen spend
  authority.

## Consequences

Commands and status payloads distinguish wallet balance from job limits. The
reservation store remains the concurrency authority. Existing old grant files
fail closed, so the operator must explicitly fund the new wallet after upgrade.
