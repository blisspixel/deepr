# The feedback signal, and why the loop does not yet have one

Status: proposed, 2026-08-10. Derived from consulting Deepr's own evaluation
and harness experts about what Deepr is missing.

## The question

Everything in the expert loop runs at zero marginal cost on prepaid quota or
local models. An expert retains a corpus, reads it through lenses, forms
positions that each state what would overturn them, writes its own standpoint
with an append-only history, keeps a practice of live questions, and gets
examined by a viva. Runs can repeat indefinitely for nothing.

So what stops that from being self-improving?

## The answer, and it is sharper than "add an eval"

The evaluation expert:

> Findings, position changes, questions, and successful vivas measure
> **activity and internal coherence**, not whether later inquiry becomes more
> accurate or useful. [...] Zero marginal inference cost does not solve the
> absence of ground truth, independent feedback, or consequential outcomes.

That is the whole trap named in two sentences. Every number the system
currently produces goes up when it works harder. None goes up only when it
gets *better*. A loop optimising those improves its metabolism, not its
judgement.

The harness expert then ruled out each candidate signal individually:

> Consult traces are inputs and reasoning records, **not feedback**. They show
> what the system considered, not whether it was right.
>
> The unread outcomes log contains **potential ground truth**, but it becomes a
> feedback signal only when compared with prior, falsifiable expectations.
>
> "What would overturn this position" is an **evaluation rule**, not feedback
> by itself.
>
> **The useful signal is the discrepancy between an ex ante position and a
> later externally grounded outcome.**

None of the three things Deepr already has is feedback. The signal is not any
of them - it is the **pairing**. A falsifier is the rule, an outcome is the
observation, and the signal is the gap between them.

That reframes the work from "build an eval harness" to "join two records the
system already writes and currently never compares."

## Why this particular signal is worth having

**It is contamination-proof by construction.** The falsifier is registered
*before* the material that resolves it arrives. There is no way to score well
by having read the answer, which is the failure mode that makes most
self-evaluation worthless. Nothing else available here has that property.

**It is free.** No judge model, no labelled set, no human. The expert already
writes the falsifier as part of forming a position; the corpus already grows;
the resolution is a comparison.

**It separates generation from evaluation**, which both experts asked for
independently. The position was written by one pass with no knowledge of what
would later arrive. Nothing judges its own output.

**It fails informatively.** A falsifier that can never fire is a decorative
one, and `falsifier_is_decorative` already detects that shape. A position whose
falsifier repeatedly fires and is repeatedly ignored is an entrenched one. Both
are visible without any new measurement.

## What is missing, precisely

| Piece | State |
|---|---|
| Positions register what would overturn them | **exists** (`would_change_my_mind`, with a decorative-falsifier check) |
| An append-only outcomes log | **exists**, operator-attested, **zero consumers** |
| Durable position identity so a falsifier survives a re-brief | **partly** - `position_thread_id` is wired into the graph only |
| A resolution *criterion* and a resolution *date* on each falsifier | **missing** |
| Anything that checks whether a falsifier fired | **missing** |
| A rule for what a fired falsifier does to the position | **missing** |

The third row is why this is blocked on the identity work rather than
independent of it. A falsifier registered against `position-3` is worthless the
moment a re-brief makes `position-3` a different question, and until today that
is exactly what happened on every run.

## The smallest mechanism that closes it

1. **Freeze the falsifier when the position is formed.** Add a resolution
   criterion (what observation counts) and a resolution date (when to look).
   Immutable once written; a falsifier that can be edited after the evidence
   arrives is not a prediction.
2. **Resolve mechanically on acquisition.** When new material lands, check the
   registered criteria against it. Deterministic where the criterion is
   checkable, and otherwise a single bounded model call whose job is only "did
   this observation occur", never "was the position good".
3. **Record the discrepancy, do not act on it yet.** The first release writes
   the pairing and nothing else. A system that starts adjusting confidence
   before anyone has seen whether the resolutions are sane is optimising
   against an unvalidated signal.
4. **Then, and only then, let it move confidence** - and only through the
   existing shift machinery, so every adjustment lands as a recorded change of
   mind with its cause attached rather than as a silent edit.

## What this deliberately does not claim

The experts named the open questions and they are real:

> Whether improvement should mean better prediction of later-observed facts,
> better decisions and actions, or better epistemic process. These targets
> overlap but are not interchangeable.

> No evidence establishes the best update algorithm, confidence threshold,
> exploration policy, or degree of automation.

So this specifies the *signal*, not the controller. Step 3 exists precisely
because the controller is unknown, and building one now would be choosing an
update rule with no evidence for it.

There is also a scale problem worth stating: a research corpus produces few
resolvable predictions per month. This will be a slow signal measured over
quarters, not a dashboard. That is a reason to start the clock now rather than
a reason to wait.

## The honest prior

The one production system built entirely around belief revision gained about
6.5% on the benchmark category that tests it - its smallest improvement of any
category. Expect this to show up as better calibration and better abstention
long before better factual correctness. The existing eval pilot already found
that shape: the only nonzero delta across four arms was uncertainty
calibration.

## Related

- [expert-v2-identity-and-time.md](expert-v2-identity-and-time.md) - the identity work this is blocked on
- [autonomy-boundary.md](autonomy-boundary.md) - why generation and evaluation stay separate
- [what-an-expert-is.md](what-an-expert-is.md) - why a falsifier is what makes a position a position
