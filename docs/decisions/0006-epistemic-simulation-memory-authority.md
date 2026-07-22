# 0006. Epistemic simulation memory authority

- Status: Proposed
- Date: 2026-07-22

## Context

Deepr may eventually support historical, future-facing, nonhuman, and other
counterfactual reasoning lenses. Such lenses can preserve useful hypotheses and
derive insights from evidence that is private, incomplete, not publicly
searchable, not yet testable, or conditional on an imagined world.

A conventional persona prompt does not define memory authority. A single
undifferentiated graph would allow generated assumptions, repeated dialogue,
or synthetic consensus to become indistinguishable from observations about the
external world. Famous names also create recognition and authority cues that
can look like reasoning quality.

The memory and graph boundary is cross-cutting and expensive to reverse. It
must be settled before adding a public lens catalog, branch learning, or a new
consult contract.

## Decision

1. Represent these constructs as persistently disclosed epistemic simulations,
   not as claims of historical identity, alien or interdimensional origin,
   consciousness, recovered memory, or future observation.
2. Give every durable record exactly one authority lane: factual, perspective,
   simulation, episodic, or governance. Bind each serialized record type to the
   lanes in which that type has authority.
3. Give every counterfactual node, edge, implication, prediction, and episode
   an immutable branch id and scenario-time scope.
4. Permit factual belief only through a provenance-rooted evidence and verifier
   path. Evidence may be public or access-controlled. A simulation, transcript,
   model-generated memory, or multi-agent agreement is not an independent
   evidence root. Protected-evidence inspection must compare the requested
   consumer with a principal established outside the serialized packet.
   Record-valued provenance inherits the same access, lifecycle, and branch
   checks as a directly selected record across its complete, acyclic assumption
   dependency chain.
5. Prohibit direct simulation-to-factual promotion. A simulation may create a
   research question whose separately gathered evidence enters the factual
   pipeline.
6. Preserve meaningful belief changes as prior-to-posterior revision records
   linked to the triggering observation, alternatives, update method, time, and
   branch. Revision chronology must follow both the involved records and its
   trigger observation, and method provenance must resolve to frozen evidence.
   Raw model confidence is not presumed calibrated probability.
7. Treat indexes, probabilistic belief views, prospective implications,
   summaries, and consult packets as rebuildable projections over evidence and
   event history until replay equality proves an authority migration safe.
8. Compile simulation context read-only. Deterministic code owns schema,
   provenance, disclosure, access, branch isolation, bounds, replay, and writes.
   Calibrated models or accountable reviewers own relevance, coherence,
   interpretation, contradiction meaning, usefulness, and proposed tests.
9. Evaluate method packs without identity labels, under paired counterfactuals,
   progressive evidence, belief revision, and held-out outcomes before claiming
   that a lens is exceptional.
10. Preserve dissent. Consensus and majority vote do not create truth or write
    authority.

## Alternatives considered

- **Persona prompts with ordinary expert memory.** Rejected because style and
  identity cues do not isolate method quality or prevent synthetic evidence.
- **One graph with confidence and source fields.** Rejected because a source
  field does not prevent cross-lane authority loss, branch leakage, or a
  generated implication from later appearing observed.
- **Only publicly verifiable web claims may persist.** Rejected because private
  documents, experiments, observations, attestations, and genuinely new
  hypotheses can be valuable. Their auditability and epistemic status must be
  explicit instead.
- **Normalize every hypothesis into one probability distribution.** Rejected
  because open-ended alternatives are rarely exhaustive and raw model
  confidence is not calibrated probability.
- **Let expert consensus promote memory.** Rejected because correlated models
  can repeat one error, identity can skew updates, and agreement is not
  evidence.
- **Adopt a graph database before defining semantics.** Rejected because the
  authority and replay contract is independent of storage technology. JSONL
  events and current projections remain sufficient for the first evidence
  slice.

## Consequences

This decision makes imaginative expertise safer to inspect, evaluate, replay,
and eventually learn from. It permits useful unverified ideas without confusing
them with facts and gives private evidence an honest place in the model.

It also adds explicit lane, branch, provenance, revision, and evaluation
requirements. Context compilation and synthesis become more complex. Full
longitudinal branch memory depends on ExpertEventV2 replay equality. Existing
consult remains the compatibility baseline until the read-only evaluator and
compiler pass held-out gates.

This ADR does not approve a public command, a named lens, model dispatch,
memory writes, a graph database migration, or any default routing change.

Designs:

- [epistemic-simulation-experts.md](../design/epistemic-simulation-experts.md)
- [epistemic-simulation-evaluation.md](../design/epistemic-simulation-evaluation.md)
- [expert-event-memory-v2.md](../design/expert-event-memory-v2.md)
