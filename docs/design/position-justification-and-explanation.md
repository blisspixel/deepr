# Position justification and explanation

Status: planned refinement of the existing Position and PositionLedger. A
first-class Argument store remains evaluation-gated.

## Outcome

The flagship read should be:

```text
deepr expert explain-position NAME POSITION
```

It should answer:

- what does this expert currently think;
- which admitted beliefs support that judgment;
- which counterevidence and dissent remain;
- which assumptions matter;
- how confident is the expert in the basis;
- what observation would change the position;
- when and why did the position change;
- where is the exact source evidence.

This is a durable justification object, not private chain of thought. The
explanation stores and renders concise, externally useful rationale,
assumptions, evidence, uncertainty, and revision conditions.

## Why refine Position before adding Argument

Deepr already has an argument-shaped object. `Position` carries a question,
stance, reasoning, supporting findings, likelihood, confidence,
confidence basis, unresolved dissent, resolution, and a falsifier.
`PositionLedger` gives it durable identity and record-time history.

Adding a second canonical Argument object now would duplicate authority before
the product has shown that separately reusable arguments improve decisions.
The smallest useful next step is to preserve the full Position contract across
versions and expose it as a traversable read.

There is a concrete fidelity defect to close first: the current
`PositionVersion` and its content identity do not preserve `reasoning`,
`confidence_basis`, `resolution`, `supporting_documents`, or `distinct_roots`.
A justification-only change can therefore disappear from durable history, and
a historical read cannot reconstruct the brief that was actually shown.

## Position V2 contract

An additive Position ledger version should preserve every decision-relevant
field:

```text
identity
  thread_id
  version_id
  question

judgment
  stance
  reasoning_summary
  resolution
  likelihood
  confidence
  confidence_basis

support
  premise_refs
  counterevidence_refs
  supporting_documents
  distinct_roots

revision
  assumptions
  unresolved_dissent
  would_change_my_mind
  expected_observations
  disconfirming_signals

history
  recorded_at
  superseded_at
  superseded_by
  supersession_reason
  corpus_fingerprint
  corroborated_over
```

`premise_refs` should become typed references rather than overloaded strings.
The first supported types can be existing finding and belief identities. A
later source-assertion reference is valid only after the exact-evidence design
lands. Run-local finding IDs remain readable for compatibility but must not be
misrepresented as stable cross-run evidence identities.

Assumptions and counterevidence are structured collections because users need
to inspect and compare them. Whether an assumption is important, evidence is a
counterexample, or premises justify the stance remains model or qualified
human judgment.

The version identity must include all decision-relevant content. Changing the
rationale, confidence basis, resolution, assumptions, counterevidence,
disconfirmers, or source-independence basis creates a new version even when the
stance text is unchanged.

## Read contract

`explain-position` is a derived, read-only projection. It does not generate a
new position, call a provider, mutate belief state, or imply semantic quality.

The structured output should contain:

```json
{
  "schema_version": "deepr-position-explanation-v1",
  "expert": "...",
  "position": {},
  "supporting_beliefs": [],
  "counterevidence": [],
  "assumptions": [],
  "unresolved_dissent": [],
  "evidence_roots": [],
  "confidence_history": [],
  "position_history": [],
  "would_change_my_mind": "...",
  "coverage": {
    "premise_refs_resolved": 0,
    "premise_refs_total": 0,
    "exact_anchors_resolved": 0,
    "exact_anchors_total": 0
  },
  "semantic_assurance": "recorded_state_only"
}
```

The human rendering leads with the current position and then walks backward:

```text
Question
Current position
Likelihood and confidence basis
Concise rationale
Assumptions
Supporting beliefs
Counterevidence and unresolved dissent
What would change the position
Version history
Exact evidence anchors when available
```

Missing links remain visible as coverage gaps. The command must not invent a
rationale, silently substitute lexical matches, or hide an unresolved
reference. Until EvidenceAnchor ships, evidence roots stop honestly at the
best current source reference.

## Argument graduation gate

Introduce a separate canonical Argument only if a held-out evaluation shows at
least one capability Position V2 cannot supply cleanly:

1. one argument is reused across multiple independent positions;
2. arguments compose into inspectable premise-to-conclusion structures;
3. an argument needs revision history independent of every position using it;
4. argument-linked gaps measurably improve decision-relevant research;
5. users resolve a judgment faster or more accurately with the separate
   object;
6. the new object reduces duplication without creating conflicting authority.

If the gate passes, an Argument must contain a conclusion, typed premises,
assumptions, counterevidence, uncertainty, expected observations,
disconfirming signals, decision relevance, status, and version lineage. It
stores concise justification, never hidden reasoning traces.

## Evaluation

Run a `$0` fixture evaluation against current Position reads and Position V2.
Measure:

- exact reconstruction of every versioned field;
- ability to identify the source roots of each premise;
- counterevidence and dissent visibility;
- falsifier visibility;
- stale and unresolved reference reporting;
- explanation stability under input-order permutation;
- reviewer time to answer "why does the expert think this?";
- false claims of source or semantic coverage.

A renderer passing schema tests is not evidence that the position is good. A
human or calibrated semantic review owns usefulness, premise fit, and whether
the stated evidence supports the conclusion.

## Delivery sequence

1. Add regression fixtures proving the current ledger fidelity loss.
2. Freeze an additive Position ledger schema and migration contract.
3. Preserve all decision-relevant fields and include them in version identity.
4. Add typed premise and counterevidence references without removing readable
   legacy references.
5. Ship the `$0`, read-only explanation contract with honest coverage.
6. Connect exact evidence anchors after their independent staging and
   verification gates pass.
7. Run the Argument graduation evaluation before designing a canonical store.
8. Attach gaps to position sensitivity first. Generalize to ArgumentGap only
   if first-class Argument graduates.

## Rejected alternatives

- **Store private reasoning traces.** Rejected because inspectable
  justification does not require chain of thought.
- **Add Argument as a synonym for Position.** Rejected because duplicate names
  and stores create ambiguous authority without new user value.
- **Generate explanations from prose on every read.** Rejected because the
  explanation must expose durable state and missing links, not reconstruct a
  plausible story.
- **Treat a falsifier as decorative text.** Rejected because revision signals
  need observable criteria and immutable prediction time.
- **Mark a position supported because references exist.** Rejected because
  reference integrity is structural while support remains semantic judgment.
