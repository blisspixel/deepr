# Skills as learning systems: what maps to Deepr, and what does not yet

## The idea being evaluated

A skill should not be a document telling an agent what to do. It should be a
persistent structure that records what it knows how to do, remembers attempts,
measures outcomes, and revises its own procedures. Markdown becomes the
manifest; a bi-temporal graph becomes the implementation; MCP stays the I/O.

The claim worth taking seriously is not "graphs are better than files." It is
that **elapsed time should make a capability better, and today it does not.**
That is the same gap this project keeps running into from the other direction:
a Deepr expert that has existed for six months has read more than a new one but
has not learned more, because the corpus accumulates and the understanding is
recomputed and overwritten on every pass.

## What Deepr already has that maps

Worth stating first, because it changes what is actually missing.

| The frame calls it | Deepr has | State |
|---|---|---|
| graph-to-context compiler | `consult_context.py` | built, wired |
| episodic capture | consult traces, study runs | written, never read back |
| bi-temporal facts | `BeliefChange.invalidated_at` vs `timestamp` | exists, nothing queries it |
| provenance to source | anchors, `corpus_shas`, finding ids | built, verified per finding |
| trust classes on inputs | `primary` / `secondary` / `tertiary` | on sources only |
| supersede rather than delete | `CorpusStore.supersede` | exists, **zero callers** |
| promotion gate | "study proposes, absorb admits" | stated, no bridge built |
| constraints that cannot be learned away | paid-API freeze, tool confinement | enforced in code and CI |

The compiler point is worth dwelling on. The argument that you cannot put a
large graph in a context window and must compile an ephemeral view per
invocation is exactly what `consult_context` does: orientation always present,
positions ranked to the question, findings pulled by the positions that
survived, source passages behind those. It was built from a different
argument and arrived at the same place, which is mild evidence the shape is
right.

## The three ideas worth taking now

### 1. Trust classes with different runtime authority

The frame proposes T0 observed, T1 inferred, T2 empirically supported, T3
validated, T4 maintainer approved, T5 invariant, where the runtime *behaves
differently* per class and **T5 cannot be overridden by the learner**.

Deepr has trust classes on sources and nothing equivalent on its own
conclusions. It also has genuine invariants - paid API frozen at a $0.00
ceiling, native tools stripped before dispatch, admission separate from
reading - that are currently protected by tests and guards rather than by a
declared class. Any self-revising layer must be structurally incapable of
relaxing them, not merely unlikely to.

This is the piece to take first, because it is cheap and it is the thing that
makes everything after it safe.

### 2. Position survival as accumulated evidence

A position that has sat through six months of new sources arriving and still
holds is a different object from one formed yesterday, even with identical
wording and identical citations. That difference is what experience is, and
Deepr throws it away on every `brief` rebuild.

Every part needed already exists: positions are typed, falsifiers are
registered before the evidence arrives, and `corpus_fingerprint` now makes
"the evidence changed underneath this" detectable. Nothing connects them.

Concretely: keep prior briefs rather than overwriting, diff positions on
rebuild, and record `first_held`, `survived_n_corpus_changes`, and
`falsifier_still_unobserved`. Then an old expert can say *"I have held this
since January, across four rounds of new sources, and the observation that
would overturn it still has not appeared"* - which is worth more than the same
sentence from a day-old expert and is exactly what you want from someone who
has been watching a field.

### 3. Counterfactual evaluation, because the naive version lies

The sharpest practical warning in the material: procedure A used 900 times at
90% and procedure B used 100 times at 72% does not mean A is better. It may
mean A gets chosen for the easy cases. Comparing them requires retaining
enough context to compare like with like.

Deepr has no evaluation at all yet, so the useful consequence is a constraint
on the one it builds: **record the context alongside the outcome from the
start**, because retrofitting it is how a measurement system ends up
confidently wrong. This sits directly on the unbuilt evaluation work, and it
pairs with the control-arm requirement already established: without a base
model with no corpus and a placebo expert on an unrelated corpus, no number
Deepr reports is interpretable.

## The risk, stated plainly

> Without a promotion pipeline, a self-improving skill becomes an automated
> superstition generator.

This is the correct objection to the whole idea and it applies to Deepr today,
not hypothetically. The brief already forms positions from findings. If a
future version revised itself from its own consult outcomes with no gate, it
would manufacture confident procedure from noise, and its own provenance trail
would make the superstition look well-sourced.

Two Deepr-specific versions of the same hazard:

- **Regeneration destroys judgment.** `card_pass --rebuild` overwrites in
  place. If a card carries a correction, rebuilding erases it. The consult on
  this said it directly: *overwrite is the wrong default for valued history;
  close the old record's interval and keep prior state queryable.* Deepr does
  exactly that for sources and not for anything derived from them.
- **Metrics get gamed.** Any scalar handed to an optimizing loop gets
  optimized, including the ones that were proxies. Faithfulness is the obvious
  trap here: a system that only ever restates retrieved spans scores near
  perfect and is useless to consult.

## What is premature, and why

Most of the rest. Not because it is wrong, but because of sequencing.

The RL layer (Skill-R1, GRPO, contextual bandits over procedure variants), the
skill marketplace with published performance history, federated cross-org
learning, and skill composition with cross-skill transfer all assume something
Deepr has not established: **that the simple version works and can be
measured.** As of today the consult path was wired yesterday, one expert has
been validated end to end, and a control arm against a bare prompt was close on
the one topic tested.

Adding a six-layer memory architecture with policy optimization to a system in
that state would be the exact failure this project has been correcting all
along - more machinery instead of proof and use. The honest order is: make the
thing measurably better, then make it learn from being used, then consider
whether the learning needs to be optimized.

One narrower reservation. The frame treats the base model as a fixed reasoning
CPU with expertise accumulating outside it, and offers portability across
vendors as a benefit. That is genuinely attractive. But it also assumes
learned procedure transfers across model generations, and a procedure tuned to
one model's failure modes may be dead weight or actively wrong on the next.
The material's own advice applies to itself: scaffolding is temporary; design
so it can be removed when models improve.

## What would have to be true first

In order, each gating the next:

1. **Measurement exists.** Control arms, ground-truth-free evaluation, context
   recorded alongside outcomes. Without this, "the skill improved" is an
   opinion.
2. **Nothing derived is destroyed on rebuild.** Supersede rather than
   overwrite, for cards, briefs, and positions - the discipline the corpus
   already has and nothing above it does.
3. **Consultation leaves a trace.** Every "I hold nothing on this" is a
   precisely specified gap generated free by a real question. Three happened in
   one afternoon and all three scrolled past.
4. **Invariants are declared, not implied.** T5 in code, so a learner cannot
   reach them.

Position survival (idea 2) is worth building before all of these, because it is
small, it needs no new subsystem, and it converts elapsed time into evidence -
which is the whole claim under examination.

## Related

- `docs/design/consultable-expert-brief.md` - positions, falsifiers, dissent
- `docs/design/temporal-knowledge-graph.md` - the bi-temporal substrate
- `docs/design/belief-lifecycle.md` - contested-as-first-class, reversible archival
- `docs/design/capacity-policy.md` - the invariants a learner must not reach
