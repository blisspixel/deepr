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

    deepr expert perspective "Provenance and Belief Revision" "how should we design flat-pack furniture"

## The question an expert exists to answer

There is a reframe from the agent-adoption literature that states this
project's purpose better than this document previously did. Describing what
changes as a team's agents get good enough to trust:

> "Did you read the code?" becomes "what context was the model missing and how
> do we solve it for next time?"

That second question is the one Deepr exists to answer. Once output arrives
faster than anyone can review it line by line, the leverage moves from
inspecting answers to fixing what the answerer did not know - permanently,
rather than by pasting more into a prompt.

Read that way, several parts of the system stop looking like separate features:

- A **viva** finds what an expert could not answer *and that material exists to
  answer*, which is a specific, actionable statement of missing context.
- The **gap router** turns that into acquisition rather than a note.
- The **practice** keeps the resulting questions as an agenda, so the next
  acquisition differs from the last.
- The **evidence graph** answers "what did this rest on", which is the check a
  reader performs when they cannot re-derive the claim themselves.

All four are mechanisms for "what was missing, and how is it not missing next
time". None of them said so, and naming it makes it obvious which work belongs
in this system and which does not.

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

## The word "expert" is carrying the wrong half of the idea

"Expert" points at authority. An expert is someone who knows, whose job is to
be correct, and who is finished - the credential marks the end of the learning,
not the middle of it. Almost none of that describes what is actually being
built here, and the word quietly pulls the design toward the fact list every
time it is used.

What the thing actually is: **a standpoint that accumulates**. An expert on
philosophy answers philosophically. Not because it holds philosophy facts, but
because a long time spent in that material shaped how it comes at anything put
in front of it. The way of coming at things is the product. Depth of knowledge
is what produced it and what keeps it honest, and it is downstream.

Read that way, several things stop being surprising:

- **A frame travels and a credential does not.** If what an expert has is a way
  of seeing, lending it to furniture design is the normal case, not a trick.
- **Growth is the point, not the maintenance cost.** A standpoint that has
  taken in six months of material and six months of hard questions is a
  different standpoint. An authority that has done the same is just an
  authority with a longer bibliography.
- **Not knowing is not a defect.** A perspective that keeps reading is supposed
  to have a frontier. A credentialed authority with a frontier looks like a bad
  credential.

The name in the code stays `expert`, because renaming across a stored fleet,
the CLI and the MCP surface would cost more than it returns. But when the two
readings disagree, the growing-standpoint reading is the correct one, and the
authority reading is the bug.

### What has to be true for that name to be earned

Growth cannot be a description; it has to be something that happened to a file.
Two halves, and today only one of them works:

**The corpus grows from interactions, and this is real.** A consult that cannot
answer records the gap in its trace, `gap_router` scores it, and acquisition
goes and gets material. Ask a question the expert cannot answer and you have
made it better at answering that question next time, without anyone deciding to
do so.

**The standpoint barely does, and that is the gap.** Every study recomputes the
brief from the corpus. Nothing about the brief carries forward. So an expert
that has existed for six months has *read* more than a new one without the
brief having *changed its mind* about anything, and the recomputation cannot
tell a view held all along from one arrived at by being argued out of an
earlier one.

Two things now write to that second half, and both are narrow:

- `deepr expert profile` keeps an append-only standpoint. When a re-read moves
  it, the old reading is kept alongside what moved it. That history is the only
  thing in an expert's directory that cannot be regenerated from the corpus,
  which is why the command refuses to write at all rather than replace it with
  an empty one.
- `deepr expert viva` records `positions_that_moved`: a view revised under
  questioning, with the question that did it. One real run moved nine.

Both are artifacts rather than a mechanism. Nothing yet *uses* a prior
standpoint to constrain the next brief, so the recomputation still happens and
the history sits beside it. The general version is tracked in
[skills-as-learning-systems.md](skills-as-learning-systems.md).

## Examination without an answer key

The per-subject tests above all need something to check against: a withheld
document, a known-absent fact, an invented entity. That covers a lot and it
does not cover the thing most worth knowing, which is whether the thinking
under a position is load-bearing or whether it stops one question past the
summary.

A doctoral viva is the format that answers this, and the reason it works is the
part that looks like a flaw: **the examiners frequently do not know the answer
either.** They are not marking against a key. They probe - why this and not the
alternative, which part is weakest, you lean on this and never mention that,
what would change your mind - and what emerges is whether the candidate has
thought it through. Both sides come out knowing more, which a graded exam
structurally cannot do.

Three properties follow, and they are why this is a mode rather than another
metric:

**The examiners should be other experts, from other subjects.** They do not
need the subject; they need somewhere to stand. An expert on provenance asks
different questions than one on evaluation design, and neither is asking as a
specialist. Same property that makes cross-domain consulting work: a frame
built elsewhere notices what an insider has stopped seeing.

**An unanswered question is the output.** Some are genuinely open and the right
answer is that nobody knows. Others are answerable from material that exists
and the expert has not read it - which is a reading list someone else wrote for
free. Telling those apart is most of the value, and it is the one judgement the
examiner is well placed to make without knowing the field.

**There is no score.** A viva produces a judgement, work to go and do, and
occasionally the discovery that a position does not survive a good question.
Compressing that to a letter would discard the part worth having.

That last outcome is the one to watch. A position lost in an examination is a
position that was going to be lost anyway, found before somebody relied on it.

    deepr expert viva "Agentic Harness Design" --plan claude --markdown

### What running it actually taught

Three things, none of which the design predicted and none of which a unit test
would have found.

**The reading queue started out permanently empty.** The first real run
returned twelve questions, twelve answered, nothing to go and read. The
examiners were probing the brief's *reasoning*, and a reasoning question can
always be answered by introspection - "no, I did not run that check" is honest,
useful, and not a knowledge gap. Nothing was asking about substance the corpus
might not cover, so the loop back into acquisition could never fire. Examiners
now spend at least a third of their questions naming something specific a
serious practitioner would expect to see, and asking about it directly.

**The judge was scoring candour instead of substance.** Asked whether aviation
human-factors research on alarm fatigue had been consulted, the expert said no
and explained what it had used instead - a model answer to a coverage question,
and a textbook gap. It was marked "answered" for being direct and well
reasoned. The fix is to make the verdict mechanical and put it *before* any
judgement of quality: does the reply contain the substance, or explain its
absence? How gracefully the second is written does not turn it into the first.

**Over-correcting produced a queue nobody could act on.** Entries like "the
expert explaining its own confidence methodology" appeared, which no amount of
reading fills - the expert already holds everything needed and simply did not
say. A gap must now name material *outside* the expert. Those belong in a
re-brief, not an acquisition queue.

The pattern across all three: the design was right about what a viva is for and
wrong about every default that decides what comes out of one. Only running it
against a real brief distinguished those.

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
| test against an answer key | examine, where nobody has one |
| an authority who knows | a standpoint that accumulates |

The last row is the one Deepr has least of today. The corpus accumulates and
the understanding is recomputed on every pass, so an expert that has existed
for six months has read more than a new one without having learned more. That
gap is tracked in the roadmap and in
[skills-as-learning-systems.md](skills-as-learning-systems.md).

## Related

- [consultable-expert-brief.md](consultable-expert-brief.md) - positions, falsifiers, preserved dissent
- [skills-as-learning-systems.md](skills-as-learning-systems.md) - what would make elapsed time matter
- [expert-v2-architecture.md](expert-v2-architecture.md) - corpus, study, and the layers underneath
- [viva.py](../../src/deepr/experts/viva.py) - examination by questioning, and the reading list it produces
