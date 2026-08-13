# Metered spend wallet and independent job ceilings

Status: accepted design, 2026-08-13. Supersedes the fixed-dollar portion of
[attended-spend.md](attended-spend.md).

## Decision

Deepr models attended metered API authority as two independent limits:

1. A persistent operator-funded wallet is the maximum cumulative metered spend
   Deepr may settle after the wallet was created. Funding adds authorization;
   it does not transfer money to a provider.
2. Every attended job names its own finite maximum charge before dispatch. The
   durable reservation system holds that ceiling against the wallet, then
   settlement consumes actual cost and returns unused capacity.

The effective limit is always the narrowest of the job ceiling, the uncommitted
wallet balance, any explicit environment ceiling, and any provider-verified
account control. There is no automatic top-up, overdraft, retry allowance, or
metered fallback.

## Protection hierarchy

The required external control is money that cannot be charged: provider-side
prepaid credits, or a provider-enforced hard cap with paid overage disabled.
Deepr must verify that boundary before any metered dispatch. A provider alert,
soft budget, or ordinary postpaid account is not a hard stop and remains
execution-blocked.

The Deepr wallet is a second, independent safety layer for attended work. It
limits what Deepr may authorize across providers, but it cannot prevent a
provider from charging outside Deepr or prove that an account is prepaid. The
CLI and status APIs must label these facts separately:

1. provider prepaid or hard-stop state, including whether Deepr verified it;
2. Deepr wallet authorized, settled, reserved, and available amounts;
3. the separately confirmed ceiling for the current job.

Funding a wallet must never be presented as adding provider credits. An open
postpaid account remains blocked even when Deepr has a local wallet.

## Why the old contract was wrong

The v2.47 attended grant made one value do three jobs: cumulative authorization,
per-job budget, and a non-configurable safety maximum. Its `$2` total limit did
prevent runaway spend, but it also made legitimate deep research impossible and
forced repeated revocation and re-issuance.

Zero surprise spend does not require an arbitrary product-wide dollar maximum.
It requires the operator to choose the total exposure, each job to choose a
narrower exposure, and accounting to prevent either value from being exceeded.

## Wallet contract

`deepr budget fund --amount 50` asks the operator to type `50.00`, then adds
exactly `$50.00` of Deepr spend authorization. The wallet records:

- a unique wallet id;
- the canonical cost-state id;
- the all-time settled ledger baseline at creation;
- total operator-authorized credits;
- creation and last-funding timestamps;
- an optional reason.

Authorized value is stored as integer cents. This avoids silently rounding a
typed amount or accumulating binary floating-point error during top-ups.

Wallet spend is:

```text
all-time settled cost - wallet baseline
```

Available capacity is:

```text
authorized credits - wallet spend - active durable holds
```

Optional day, week, and month caps retain their own UTC calendar windows. They
do not become wallet drawdown, and the wallet does not refill when those
windows roll over. Admission checks both ledgers independently: current-window
settlement against the applicable calendar cap, and all settlement since
funding against the cumulative wallet.

Local and admitted prepaid-plan work settles at `$0` and therefore does not
consume wallet capacity. Funding is additive, never automatic, and serialized
with reservation admission. A top-up keeps the same wallet id and baseline, so
active reservations and every earlier wallet-funded settlement remain in one
drawdown history.

The wallet has no ordinary safety-dollar maximum. The implementation only
rejects values above the largest amount whose cents are exactly representable
in the stored numeric format. That is a data-integrity boundary, not a spending
recommendation.

## Job contract

Wallet funding alone cannot dispatch a request. An attended metered entry point
must also provide:

- current authenticated provider prepaid-no-overage or hard-stop evidence;
- an exact provider and priced model;
- a finite positive job or parent-run ceiling;
- a displayed worst-case request envelope;
- the existing explicit metered-cost confirmation;
- one durable reservation for the whole possible charge before provider work;
- settlement or an unresolved hold if provider work may have run.

A default job ceiling may make a command convenient, but it is never a hidden
extra allowance. Operators may raise a job ceiling above `$2` when the wallet
has enough uncommitted capacity. Retries, tools, and child calls must fit inside
the same reserved parent ceiling. Surfaces without a complete parent envelope
remain blocked.

## Attended and unattended remain different

The wallet is ignored inside unattended spend scope. Every metered path requires
provider-authoritative account controls and credential identity; MCP, A2A,
schedules, background loops, and automatic routing remain blocked until their
full execution envelope is also proven. Expert consult remains local or
safety-eligible plan quota by default and has no metered fallback.

This is deliberate. A persistent balance is safe for attended work only because
every actual run has an independently confirmed ceiling. It is not standing
permission for an autonomous process to decide when or why to spend.

## Failure behavior

- Missing, corrupt, wrong-schema, or wrong-cost-state wallet data means zero
  metered authority.
- A manual freeze written after the latest wallet funding blocks attended work.
  Adding confirmed credits later is a new attended authorization. Billing
  divergence, evidence-storage failure, and cost-ceiling divergence freezes
  remain blocking until their underlying safety invariant is repaired.
- An old v2 `$2` attended grant is not auto-migrated into a persistent wallet.
  Silent migration would widen its lifetime.
- Unknown final usage consumes the reservation ceiling or remains unresolved.
- Concurrent jobs cannot reserve more than the remaining wallet balance.
- Clearing the wallet blocks new reservations. Reservations for another wallet
  id cannot be dispatched under a later wallet.
- Ledger rollback below the wallet baseline freezes paid work.

## Presentation

Status surfaces use `wallet`, `funded`, `spent`, `reserved`, and `available`.
They do not say Deepr has prepaid the provider. Screenshots may use a synthetic
ledger event and synthetic wallet only inside an isolated cost-state root, with
no credentials or provider dispatch.

## Interoperability

The wallet and reservations are host policy, not expert knowledge. Agent Plugin
manifests may declare budget-aware tools, but cannot grant authority. OKF 0.2
exports may carry spend provenance as execution metadata, but the canonical
ledger and wallet stay outside the derived expert bundle.
