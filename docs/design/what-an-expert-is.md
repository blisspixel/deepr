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

An open one is the opposite: informed, opinionated about its subject, and
still going. It has read a lot and wants to read more. It will tell you what
it thinks and where it is unsure without treating the second as a failure of
the first.

## What cannot be measured, and what the grade actually does

There is a strong pull, when building this, toward turning an expert into a
score. It should be resisted, because it produces a different and worse
product.

The forecasting literature is where the pull comes from, and it is the wrong
literature. Those studies measure **resolvable predictions**: will this event
occur by this date, scored against what happened. Brier decomposition,
calibration indices and discrimination curves are the right instruments for
that, and they are excellent.

An expert on writing systems, or on how a codebase should be structured, or on
where a field's real disagreements lie, is not making resolvable predictions.
Most of what it offers never resolves. It reads a body of material, forms a way
of seeing it, and helps someone think. Scoring that with forecasting
instruments measures the wrong object and, worse, quietly redefines the goal as
the thing the instruments can see.

So `expert_health` is deliberately narrow, and it is worth saying plainly what
it is:

**It is artifact hygiene, not quality.** Does this expert have a retained
corpus. Did anything read it. Did the reading land anywhere. Is the corpus one
publisher wearing several hats. Are its claims traceable to a passage. Those
are answerable from files on disk, they are worth knowing across a fleet of
fifty, and none of them is a judgement about whether the expert is any good.

**It cannot tell you whether an expert is worth talking to.** An expert can be
perfectly well-formed and confidently wrong about everything; a corpus of five
mutually-agreeing bad sources scores identically to five good ones. The grade
has no opinion about whether the material was any good, only about how it is
shaped. Nothing on disk reaches insight, and pretending otherwise would be the
same overclaim this project keeps correcting elsewhere.

**Its one job is triage.** With fifty experts, "which three need work and what
do they need" is a real question with a cheap answer. Every grade ships with
one next action for exactly that reason. Read it as a maintenance queue, not a
ranking of minds.

The openness rule sits inside that limit rather than escaping it. It does not
measure whether an expert is open-minded, which is not a thing a directory
listing knows. It compares two artifacts: did the contention lens find
disagreement in the corpus, and did the brief carry any of it into a position.
When the answer is "found fifteen, carried none," that is a specific and
checkable observation about a specific brief. It is not a personality
assessment, and the earlier version of this section - which reached for
tournament statistics to justify it - was making exactly the category error
this section now exists to name.

## The real test is a test, and it has to be built per subject

The grade is not the measurement. If someone set an exam on this subject, a
good expert should do well on it - and that exam would look nothing like the
exam for another subject, because the thing being examined is different.

That sounds like it makes evaluation impossible for a system that has to work
on any topic. It does not, because the *method* can be general while the
*test* is generated per subject, from that subject's own corpus. Three that
work this way, none of which needs a human to know the field:

**Hold a source back.** Take a document out before studying, then ask the
expert what it would say about the question that document answers. An expert
who has understood the field predicts it; one who has memorised its sources is
surprised by it. Generated entirely from the corpus, and the answer key is the
withheld document.

**Ask what the corpus cannot answer.** Build questions the material genuinely
does not cover, alongside ones it does. A good expert distinguishes them. A
system that answers both equally has been fluent rather than informed. The
useful score is the pair, because always refusing wins a one-sided version.

**Ask about something that does not exist.** Invent a plausible entity in the
subject - a specification revision, a technique, a named result - and see
whether the expert claims to know it. This costs nothing, cannot be satisfied
by careful phrasing, and catches the failure a well-formed artifact hides best.

None of these produces a letter. They produce evidence about a particular
expert on a particular subject, which is the only form an answer to "is this
expert any good" can honestly take. The letter grade is for finding which
three of fifty need attention this week; the test is for finding out whether
one of them knows anything. They are different questions and should not share
a scale.

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
