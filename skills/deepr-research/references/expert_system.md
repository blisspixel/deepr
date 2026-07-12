# Expert system reference

Deepr experts are persistent structured knowledge roles. Canonical state holds
beliefs, evidence, confidence, contradictions, temporal qualifiers, gaps,
perspective state, and loop records. Digests, memory cards, handoffs, and skill
exports are derived views.

## Read before answering

1. List experts and select a domain-relevant role.
2. Inspect its profile, beliefs, gaps, freshness, and grounding assurance.
3. Use one explicit local or non-metered plan read-only query turn.
4. For cross-domain work, use a bounded council and preserve disagreements.
5. Treat low confidence, stale evidence, and contested beliefs as visible
   uncertainty, not as an instruction to launch paid research automatically.

## Confidence is not truth

Confidence is evidence-conditioned state with trust floors and decay. It can be
useful for routing review, but it does not prove correctness. Report:

- source and observation time;
- whether support is same-vendor, cross-vendor, or unverified;
- contradictions and disconfirming signals;
- missing evidence and known gaps;
- whether semantic answer quality has human or calibrated-model review.

## Read-only consultation

`deepr_query_expert` works in v2.36 only with `backend="local"` or
`backend="plan"`, `agentic=false`, and explicit corresponding capacity. The
turn compiles stored context and cannot write beliefs or start tools.

`deepr_consult_experts` can consult one or several experts. Prefer local or plan
synthesis for no-metered operation. The output includes roster, perspectives,
agreements, disagreements, capacity, cost, trace, and host-action boundaries.
It is advice, not authority to mutate projects or expert state.

## Updating an expert

Use explicit local or documented non-metered plan workflows for setup, sync,
absorb, compiled claim verification, and gap routing. A report is only evidence
input. Permanent changes require the graph-commit verification and explicit
apply boundary; generated artifacts never become canonical by editing them.

Do not claim that conversation alone caused continuous learning. Standalone
metered chat, background synthesis, API resume/refresh, metered gap fill,
metered reflection, API sync, and autonomous research are gated in v2.36.

## Local busy handling

Scheduled local work may persist a waiting result when GPU contention is
confirmed. Preserve the requested command and returned retry time. Deepr uses a
bounded 30-minute, 2-hour, then 6-hour retry cadence and does not sleep inside
the running command or switch capacity silently.

## Safety boundary

Deterministic code owns schemas, budgets, side effects, locks, provenance,
idempotency, and apply operations. Calibrated model or human judgment owns
semantic support, contradiction, deduplication, atomicity, and synthesis. A
lexical check may route a review but cannot decide truth.
