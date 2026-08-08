# What a Deepr expert is, and what it is not

## Not a fact list

This is the thing most easily got wrong about Deepr, and getting it wrong
produces a worse product at every layer.

A fact list answers questions it has facts about and is silent otherwise. Its
value scales with coverage, its failure mode is a gap, and the only sensible
thing to do with it is look things up. If that were what an expert is, the
right design would be a search index with citations, and most of this codebase
would be unnecessary.

An expert is something else. It has read a body of material and formed a way
of seeing it: distinctions it now makes that it did not before, failure modes
it looks for first, a sense of what is usually the real problem underneath
what people ask about. That frame is the asset. The facts are what produced
it and what keeps it honest, but they are not the thing itself.

Two consequences follow, and both are load-bearing.

## Consequence one: an expert holds views, not only facts

Much of what an expert knows is perspective rather than fact. On many
questions there is no single reading of the evidence to converge on, and two
experts reading one corpus can legitimately differ. An expert that reports
only what is settled has thrown away the part worth consulting.

So Deepr experts take positions. A position states where it lands, what would
overturn it, and what it did not resolve. That last part is what separates a
view from an assertion, and the type will not let a position exist without a
falsifier.

This is not the same as being unmoored. The guard against a system that
invents confident procedure from noise belongs on **anything that acts** -
anything that could change what the system does without a human deciding. It
does not belong on perspective that informs. An expert too timid to land
anywhere is a worse product than one that lands and says what would move it.

The five perspective lenses exist for the same reason. Economic, operational,
human/cultural, adversarial and institutional are five legitimate readings of
one corpus, not four wrong ones and a right one.

## Consequence two: a frame travels where facts do not

If what an expert has is a way of seeing, then it can be brought to a subject
it knows nothing about.

A furniture designer consulting an expert on Chinese writing gets nothing from
"what do your sources say about chairs." They get something worth having from
"you have spent years on a system where meaning is carried by stroke order,
radical composition and the negative space inside a character - what does that
make you notice here."

This is not a party trick. Deepr's `Provenance and Belief Revision` expert,
asked about designing self-assembly furniture, produced this without knowing
anything about furniture:

> The hard problem is not holding a belief, it is knowing what else depends on
> it so you know what to retract when it turns out wrong. Assembly
> instructions are a dependency chain the same way: step 11 being wrong
> because of a mistake at step 4 is a justification failure, and the real
> design question is whether the instructions let someone identify and undo
> just the dependent steps, or whether the physical build has already erased
> that dependency structure.

> An assembled subunit is like a derived belief - its correctness rests
> entirely on earlier steps, so a design that lets subunits be built in a way
> that visually looks fine but is not actually verifiable is deferring
> falsification to a point where the origin of the error is no longer
> traceable.

A fact list cannot produce that. It has no facts about furniture, so it has
nothing to say. An expert with a formed frame has plenty to say, because the
frame is what it is lending.

### The rule that keeps this honest

Cross-domain readings are **analogy, and every rendering says so**. The
expert's sources say nothing about the asked subject; carried across, its
findings are a way of looking, not evidence. An analogy presenting as evidence
is fabrication with a citation attached, which is worse than an obvious guess.

Two structural requirements, both enforced in `cross_domain.py`:

- **Every observation names the mapping it rests on.** "Both involve
  composition" is a word. "In my subject the meaning lives in the order of
  construction, not the finished form, so I would ask whether the order of
  assembly here carries information nobody is reading" is an insight, because
  someone can go and check whether the mapping holds.
- **Every reading says where the analogy breaks.** An analogy with no stated
  limit is being offered as a fact, and the places it fails are usually where
  it would have misled someone.

An expert whose frame genuinely does not reach a subject should say so. A
forced analogy is worse than none.

### Why this is a separate mode

The normal consult path forbids exactly this, correctly. Positions are ranked
against the question, dropped when they do not match, and an expert with no
bearing evidence reports `uncovered` rather than answering from adjacent
material. That rule exists because answering outside your evidence while
sounding evidenced is the failure the whole system is built against.

Cross-domain is a different mode, not a relaxation of that one. It never
claims coverage. It claims a frame.

## An expert that is glad to be asked

An expert that cannot answer should still want to. "I hold nothing on this" is
honest and leaves the asker exactly where they started.

So an uncovered consult names what the expert is already working on, what it
already knows it does not know, and the route that would turn the no into a
yes. Refusing usefully is still helping, and it is the only way a refusal
becomes work the expert can go and do rather than a dead end.

## An open cup

An expert holding no unresolved dissent, naming no open questions and
admitting no weakness is not finished. It is closed, and a closed expert has
stopped being able to learn the subject it claims to know - which is the point
at which it stops being worth consulting, whatever its corpus looks like.

So certainty lowers the grade in `expert_health` rather than raising it, and
the top tier requires all of: deep and independently sourced, current, holding
a perspective of its own, and still naming what it does not know.

**But the obvious way to measure this is wrong, and the first version got it
wrong.** In the largest forecasting tournament measured, frequency of belief
revision correlated with accuracy at r = -.49 while self-reported actively
open-minded thinking managed r = -.10, and dropped out entirely once ability
and knowledge were controlled. Self-reported humility also correlates with
social desirability and is documented as easy to fake. For a system writing
its own profile that is not social desirability but *rubric* desirability,
where the gradient is explicit and satisfying it costs one JSON field.

Asking an expert to declare its open questions grades the weakest channel in
that literature. So declared openness is necessary and not sufficient, and the
signal that carries weight is behavioural: did the contention lens find
disagreement in the corpus, and did the brief carry it forward? That is a
comparison between two artifacts, neither of which is the expert describing
itself.

**And certainty is correct in some subjects.** Expert intuition is valid where
the environment is regular and feedback is available. On a frozen protocol
specification there is no live dissent, and an expert manufacturing some is
worse than one reporting none. A uniform penalty on certainty punishes correct
calibration - and the measured failure of real expert organizations runs the
other way: across 1,514 strategic intelligence forecasts the miscalibration was
*under*confidence, worst on the hardest and most consequential questions.

So the closed-expert penalty now applies only where the corpus itself shows the
subject is contested. A settled subject with honest silence reaches the top
tier. A contested one whose brief carried none of the disagreement forward does
not, and is told exactly that.

**One warning worth keeping in view.** Where outcomes cannot be checked,
whatever posture a rubric rewards drives credibility *and reduces verification
effort*. A humility ritual can launder unverified claims as effectively as a
confident tone. That is the argument for measuring behaviour and calibration
rather than grading prose, and for the parts of this rule that are still
declared rather than observed being treated as the weakest evidence available.

## What this means for building

The design pressure runs one way throughout:

| Fact-list thinking | Expert thinking |
|---|---|
| coverage is the goal | a formed reading is the goal |
| a gap is a failure | a named gap is information |
| certainty is quality | certainty is a warning |
| answer only in-domain | a frame travels, labeled as analogy |
| more documents is better | more independent origins is better |
| overwrite with the latest | keep what changed, and why |

The last row is the one Deepr has least of today. The corpus accumulates and
the understanding is recomputed on every pass, so an expert that has existed
for six months has read more than a new one without having learned more. That
gap is tracked in the roadmap and in
[skills-as-learning-systems.md](skills-as-learning-systems.md).

## Related

- [consultable-expert-brief.md](consultable-expert-brief.md) - positions, falsifiers, preserved dissent
- [skills-as-learning-systems.md](skills-as-learning-systems.md) - what would make elapsed time matter
- [expert-v2-architecture.md](expert-v2-architecture.md) - corpus, study, and the layers underneath
