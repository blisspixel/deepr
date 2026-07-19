# Security Control Ownership

Status: accepted for incremental implementation, 2026-07-18.

## Context

The July 2026 repository security review found that the highest-leverage
failures are repeated ownership gaps rather than one-off input patterns. Spend
lifecycle state is split across callers. Authenticated identity is sometimes
lost before object access or side effects. Delegated process and network
adapters can inherit authority that their user-facing contract does not name.

The sealed review preserves every candidate, validation receipt, attack path,
and coverage limitation outside the repository. This note records the design
boundary for implementation.

## Decision

Deepr will move three deterministic invariants behind owned boundaries:

1. A metered operation owns explicit paid-capacity authorization, atomic
   reservation, dispatch identity, durable settlement, and terminal financial
   closure. Unknown post-dispatch usage is never silently zero.
2. Sensitive remote operations require an immutable caller capability context.
   Object creation records ownership, and reads, mutation, cancellation,
   resources, rate limits, and budget checks enforce the same context.
3. Delegated execution declares process, environment, native-tool, filesystem,
   network, response-byte, timeout, and cleanup capabilities. Unsupported or
   unverifiable restrictions fail closed.
4. A durable expert-state commit requires producer-owned provenance. A graph
   commit target is nonempty and exact. Sync envelopes are bound to a
   create-once receipt that hashes the envelope and its extraction and
   verification artifacts. Investigation envelopes are bound to the durable
   run artifact index. Caller-selected JSON and self-declared verifier labels
   are proposal data until one of those trusted producer records validates.

Immediate route-level fixes remain in place during migration. Structural work
does not defer a direct fix for a known vulnerable path.

## Agentic Boundary

These controls govern form, authority, spend, tools, network access, and
durable writes, so deterministic code owns them. Models still own semantic
judgment: relevance, contradiction, theory quality, research direction,
synthesis, and dissent. A model may propose a query, tool, hypothesis, or
knowledge update, but its text cannot grant the authority needed to execute
the side effect.

This keeps speculative expert work first class. Facts require appropriate
evidence. Hypotheses, stances, forecasts, and original synthesis instead carry
premises, uncertainty, expected observations, and disconfirming signals.
Lack of online corroboration is not itself a rejection.

## Cost Contract

- A budget is a hard ceiling, not permission to spend.
- Paid capacity requires explicit selection, `allow_metered_api=true`, and a
  separate `confirm_metered_cost=true` at remote boundaries. CLI noninteractive
  execution requires its explicit cost-confirmation flag in addition to the
  budget.
- Local and safety-eligible admitted plan-quota capacity cannot fall through to
  metered API capacity. Explicit plan selection never overrides auth,
  native-tool, overage, or marginal-cost refusals. A plan with optional paid
  extra usage must provide a live provider observation that overage is disabled
  immediately before every call. Model-attempt accounting cannot fabricate that
  observation.
- Every spend source writes the append-only ledger.
- Dispatch without a reservation fails closed.
- A post-dispatch unknown becomes a reconciliation state or conservative
  bounded estimate, never an unrecorded zero.
- Hosted deployment templates cannot use provider secret values as
  CloudFormation parameters, process arguments, or Terraform variables and
  state. AWS and GCP consume pre-created secret references. Azure uses secure
  Bicep parameters through a protected ephemeral file. Hosted metered job
  submission remains disabled until it shares the canonical transaction.

## Compatibility And Rollout

Changes land as small reversible increments:

1. close each known route with a regression test;
2. introduce the owned boundary behind existing interfaces;
3. shadow and compare state or policy decisions;
4. migrate callers one surface at a time;
5. remove compatibility adapters only after parity, failure-injection, and
   recovery tests pass.

For graph commits, legacy unattested envelopes remain readable as inert JSON
but cannot cross the write boundary. This intentionally favors knowledge
integrity over applying an old staged file. The safe migration is to rerun the
zero-cost compiler or investigation stage so Deepr emits a provenance-bound
envelope.

Loopback locality is not authentication. Compatibility modes may expose an
explicitly safe anonymous read surface, but they cannot inherit operator
credentials, paid authority, global resources, or other callers' jobs.

## Rejected Alternatives

### Prompt-only safety

Prompts cannot enforce process, spend, filesystem, or network authority. They
remain useful instructions but never the control.

### Perpetual caller checklists

Direct guards are required now, but a checklist leaves the invariant optional
for every new caller and preserves the root ownership problem.

### Immediate service isolation

A separate spend or execution broker could improve failure isolation, but the
current evidence does not justify its latency and operating cost. In-process
owned boundaries preserve a later isolation seam. Isolation becomes preferable
if multi-tenant untrusted execution grows or a vendor adapter cannot honor the
declared capability contract.

### Semantic keyword gates

Lexical rules may route suspicious content for review, but they cannot decide
whether an expert theory is true, a claim is grounded, or a prompt is safe.
The implementation guards concrete authority and side effects instead.

## Verification

Each mapped finding gets a regression test at its public boundary. Structural
tests additionally cover concurrency, non-finite values, cancellation,
post-dispatch failures, ledger append failures, crash recovery, cross-key and
cross-expert access, inherited secrets, DNS rebinding, redirects, streaming
byte limits, and Windows process behavior.

The migration is complete only when no metered dispatch lacks a reservation,
no sensitive operation lacks a caller context, and no delegated operation
receives undeclared authority.
