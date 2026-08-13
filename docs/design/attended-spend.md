# Attended spend: being usable and having no surprise bills

Status: historical v2.47 design, 2026-08-12. Its expiring grant commands and
fixed `$2` maximum were superseded in v2.49 by
[spend-wallet-and-job-ceilings.md](spend-wallet-and-job-ceilings.md). The file
is retained as the decision history for the original attended dispatch path,
not as current operator guidance.

## The original problem, stated plainly

Paid dispatch could not be enabled. It was not merely disabled by default; it
could not be enabled by anyone.

`deepr budget unfreeze` requires `--evidence-id`: a content-addressed
`PaidApiAccountEvidence` document whose schema demands a `source_posture` of
`provider_api` or `cryptographically_verified_provider_export`, an external
`credential_fingerprint`, a `billing_reconciliation_sha256`, and a
`control_mode` proving a hard monthly limit with `overage_enabled: False`, all
bound to the exact freeze id and timestamp.

That evidence can only come from the provider. **No adapter produces it**, so
unattended metered dispatch remains frozen pending a provider-authenticated
account-control adapter.

The operator's actual request was narrower: "I need to be able to use the paid
APIs when I want, I just don't want surprise bills." The original authority
model could not express that attended case.

## The mistake

Two different risk profiles were collapsed into one control.

| | Attended | Unattended |
|---|---|---|
| Who starts it | A person typing a command | An agent loop, a schedule, an MCP call |
| How much | Bounded, small, named up front | Unknown, potentially large, repeated |
| Who is watching | Someone, now | Nobody, for hours |
| What makes it safe | A ceiling they set and a prompt they answer | Proof the *provider* will refuse to bill past a cap |

Provider-side cryptographic proof is the right bar for the right column. It is
absurd for the left one, where the honest control is "you said $2, you typed
$2 to confirm, and the ledger stops you at $2."

The codebase already has most of the left-hand control. Metered commands take
an explicit consent pair - `allow_metered_api` plus `confirm_metered_cost` -
declared as `--confirm-metered-cost` on 15 commands, and the CLI separately
uses interactive confirmation in about 50 places. So an operator saying "yes,
this specific spend, knowingly" is already expressible.

It is unreachable. Budget authority sits above consent and fails closed for
everyone, so the acknowledgement never gets a chance to mean anything.

Note what this control is and is not: a consent acknowledgement is a claim by
the caller, not proof a human saw a number. That is fine for the attended case
and exactly why it is not enough for the unattended one - a loop can pass the
same flag. The grant below is what supplies the ceiling and the expiry that
a boolean cannot.

## What was built

A third authority mode between "frozen" and "provider-verified": an **attended
grant**.

```
deepr budget allow --amount 2.00 --minutes 30
```

- Prints current exposure, unresolved holds and the effective caps first.
- Requires the operator to type the amount back. Not `-y`, not a flag; the
  confirmation is the authority.
- Writes a grant record: amount ceiling, expiry, unique id, and the cost state
  id it was issued against.
- Paid dispatch is permitted up to the ceiling, and re-blocks at exhaustion or
  expiry, whichever comes first.

### The properties that keep "no surprise bills" true

**A hard total ceiling per grant, and a ceiling on the ceiling.** A grant may not
exceed $2. This is a non-configurable safety boundary, not a per-call allowance.
A mistyped `200` cannot authorize two hundred dollars; it is refused, not
clamped, because a silently reduced authorization is its own surprise.

The grant records the canonical total settled cost at issuance. Every later
metered ledger dollar and every active paid hold draws down the grant, regardless
of API provider or UTC day, week, or month rollover. Earlier settled spend does
not consume a new grant. Local work and admitted plan-quota work record `$0`, so
they remain visible without drawing down metered authority.

**Expiry.** A grant is minutes, not forever. A forgotten grant must not become
standing permission, which is precisely how an attended control decays into an
unattended one.

**Per-call consent still applies.** A grant raises the ceiling; it does not
imply `confirm_metered_cost` for any call. Two independent things must agree
before money moves: the operator authorised this much, and this specific call
was acknowledged.

**Settlement is unchanged.** Grants are consumed by the existing durable
reservation and settlement path, so `audit_spend_integrity` and orphaned-spend
detection keep working exactly as they do now. A grant is authority, not
accounting.

**One switch, not two.** A live grant also releases the metered keys that
`key_quarantine` moves out of the environment at startup, for exactly the
grant's lifetime. Without this an operator who authorized $2 would find every
call failing on a missing key and would reach for a global
`DEEPR_ALLOW_METERED_KEYS=1` - a permanent, unexpiring hole opened to solve a
bounded, expiring problem. When the grant expires or is revoked, the next
process quarantines the keys again.

**Unattended work cannot use one.** Anything reached through MCP, a schedule,
or a loop runner is refused regardless of an active grant. That path keeps
requiring provider evidence, because nobody is watching it. This is the whole
point of the split and it must be enforced at the call site, not by convention.

**Every paid call is recorded.** Reservations, dispatch marks, settlement, and
provider identifiers remain in the append-only money records. The grant record
binds those calls to its id and issue-time baseline, so "how did that get
spent" remains answerable.

## What shipped

`deepr budget allow --amount 2.00 --minutes 30` prints current exposure and
unresolved holds, requires the amount typed back, and writes a grant bound to
the current cost-state id. `deepr budget revoke` ends it immediately.

Verified end to end on a frozen install: `frozen=True` before, `frozen=False`
with `monthly=$2.00` during - the grant's ceiling, not the configured monthly
limit - still frozen for a provider the grant was not scoped to, and
`frozen=True` again after revoking. Keys follow the same lifetime: `doctor`
reports the OpenAI key "Not configured" with no grant and "Configured" with
one.

MCP tool dispatch runs inside an unattended spend scope that ignores attended
grants. Scheduled sync, roster sync, and gap-fill commands refuse `--api` and
continue to use only admitted local or plan-quota capacity. The loop runners
reuse those scheduled entry points, so a grant cannot become their metered
fallback.

The attended OpenAI absorb client is constructed inside Deepr and bound to the
live grant, exact credential fingerprint, official endpoint, exact priced
model, retry count, redirect policy, and proxy policy. Injected clients remain
blocked. The binding is rechecked immediately before every paid request.

On 2026-08-12, a $2 OpenAI grant improved the Knowledge System Evaluation
expert from 0 to 20 canonical claims. One extraction and five short semantic
checks settled to $0.011031 in the canonical ledger, left no active or
unresolved hold, and left $1.988969 of the single grant unconsumed. The grant
was then revoked and paid dispatch returned to frozen.

## What this does not do

It does not remove the provider-evidence path. Unattended dispatch stays
blocked until the account-control adapter exists, and that adapter remains the
right long-term unblock for anything running without a person.

It does not make Deepr spend by default. Frozen stays the default; a grant is
an explicit act with a short life.

It does not replace a provider-side cap. The strongest protection available is
still a hard monthly limit with overage disabled configured directly on the
provider account, because that one holds even if this code is wrong. The doc
recommending it should say so plainly, and this feature is not a reason to skip
it.

## Why this is worth doing before the adapter

The adapter is real work against provider APIs that differ per vendor, and it
unblocks the case nobody is asking for yet. Attended spend unblocks the case
the operator is asking for now, is a day of work rather than a project, and
leaves the strict path intact for when unattended work arrives.

There is also a self-honesty argument. A control that cannot be satisfied is
not a control, it is a wall, and a wall gets routed around - by exporting a key
and calling the provider directly, outside the ledger, where none of the
accounting this project has built can see it. A usable, bounded, recorded path
is safer than an unusable one.

## Related

- [where-deepr-sits.md](where-deepr-sits.md) - attended versus unattended is
  the same distinction that separates the CLI from the MCP surface
- [autonomy-boundary.md](autonomy-boundary.md) - what an unattended run must
  prove before it is allowed to act
- `docs/SUPPORTED_SURFACE.md` - the current freeze and what it is waiting on
