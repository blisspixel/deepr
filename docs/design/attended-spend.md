# Attended spend: being usable and having no surprise bills

Status: proposed, 2026-08-12. Not built.

## The problem, stated plainly

Paid dispatch cannot be enabled. Not "is disabled by default" - cannot be
enabled at all, by anyone, today.

`deepr budget unfreeze` requires `--evidence-id`: a content-addressed
`PaidApiAccountEvidence` document whose schema demands a `source_posture` of
`provider_api` or `cryptographically_verified_provider_export`, an external
`credential_fingerprint`, a `billing_reconciliation_sha256`, and a
`control_mode` proving a hard monthly limit with `overage_enabled: False`, all
bound to the exact freeze id and timestamp.

That evidence can only come from the provider. **No adapter produces it**, which
`SUPPORTED_SURFACE.md` records accurately: metered dispatch has been frozen
since v2.40 pending a provider-authenticated account-control adapter.

So the operator's actual request - "I need to be able to use the paid APIs when
I want, I just don't want surprise bills" - is unmet in both directions. They
cannot spend, and the reason they cannot spend has nothing to do with whether a
given spend would have surprised them.

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

## What to build

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

**A hard ceiling per grant, and a ceiling on the ceiling.** A grant may not
exceed `DEEPR_MAX_ATTENDED_GRANT_USD` (default $25). A mistyped `200` cannot
authorize two hundred dollars; it is refused, not clamped, because a silently
reduced authorization is its own surprise.

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

**Unattended work cannot use one.** Anything reached through MCP, a schedule,
or a loop runner is refused regardless of an active grant. That path keeps
requiring provider evidence, because nobody is watching it. This is the whole
point of the split and it must be enforced at the call site, not by convention.

**Every grant is recorded.** Issued, consumed, expired, and by whom, in the
append-only ledger. "How did that get spent" must remain answerable.

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
