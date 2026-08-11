# Where Deepr sits, and who it is actually for

Status: analysis, 2026-08-10. Prompted by Boris Cherny's "Steps of AI Adoption"
(2026-07-16), which describes a five-rung ladder from gated tooling to agents
running at a scale of thousands.

Deepr appears on that ladder twice, in two different roles, and confusing them
is the reason the roadmap has been implicitly aimed at the wrong user.

## Role one: Deepr's own expert loop is at step 1

Step 1 is "assisted": one operator, one agent, and the described bottleneck is

> Your attention and the need to inspect each response and code edit. [...] you
> feel you must read everything, so you never look away.

That is the expert loop exactly. Seven stages, each triggered by a human typing
a command, each output read before the next runs.

The stated requirement for reaching step 2 is **a self-verification loop you
trust** - tests, build, lint, end-to-end. Deepr's equivalents exist and were
mostly wired in a single day:

| Coding agent | Deepr |
|---|---|
| tests pass | anchor grounding: does the quoted phrase appear in the retained source |
| build and lint | `stage_contract` / `expert status`: did the stage produce what it promised |
| end-to-end check | `is_formed`: does a position actually reach a passage through a finding |

That mapping is worth stating because the sequencing was arrived at
independently, from consulting Deepr's own harness expert about Deepr's loop,
and it landed on the same prerequisite the ladder names. Two unrelated sources
agreeing on the order of work is weak evidence, but it is evidence.

**The trap the ladder names is the one this roadmap was heading into:**

> Your trap is scaling agent count before the loop has earned widespread trust.

Which is the same conclusion, from a different direction, as the harness
expert's finding that `brief` fails the reversibility test. Do not build the
scheduler yet.

## Role two, and the more important one: Deepr is the 2 to 3 unlock

> **How to get from step 2 to 3: Give Claude a way to pull in context** (let
> Claude read code, wikis, discussions).

That is not a step Deepr climbs. It is a step Deepr *is*. The bottleneck at
that transition is context, and Deepr already exposes 39 MCP tools whose entire
purpose is handing an agent an accumulated, source-anchored view of a subject.

This reframes who the product is for. The user is not primarily a person
consulting an expert between meetings. It is **an orchestrator running five to
ten agents whose limit is what those agents know**, and who needs that context
to be current, traceable, and not re-derived from scratch on every task.

Consequences for what matters:

- **The MCP surface is the product surface**, and the CLI is the maintenance
  surface. Work that improves what a consult returns to an agent outranks work
  that improves what it prints to a terminal.
- **Traceability is a feature for this user, not hygiene.** An orchestrator
  reviewing six streams of output cannot check claims by hand. "This rests on
  that passage" is what makes a context source usable at that speed.
- **Staleness is the failure mode that matters.** An expert that was right in
  June and silently is not any more is worse than no expert, because it is
  consulted at a speed that precludes checking.

## The asymmetry that means Deepr cannot climb this ladder the same way

Every rung is gated on self-verification. That works for coding agents because
verification there is nearly free and nearly objective: the tests pass or they
do not, the build is green or red.

Research has no equivalent. Deepr's own evaluation expert, asked what the loop
is missing:

> Findings, position changes, questions and successful vivas measure activity
> and internal coherence, not whether later inquiry becomes more accurate or
> useful. [...] Zero marginal inference cost does not solve the absence of
> ground truth, independent feedback or consequential outcomes.

So the escalator that carries a coding org from 1 to 4 does not exist here.
The closest available substitute is the falsifier-versus-outcome discrepancy
described in [the-feedback-signal.md](the-feedback-signal.md), and it resolves
over quarters rather than CI runs.

**This is structural, not a gap to close.** A roadmap that plans to reach
"supervised autonomy" by adding verification is planning on a resource this
domain does not have.

## What does not transfer

**Agent count is the wrong metric.** The ladder scales by number of concurrent
agents. Deepr's parallelism is *across* experts; a single study is sequential
by lens, and running a hundred agents does not make one expert better. The
analogous scaling axis is number of subjects held current, which is a different
shape with a different bottleneck (quota, not attention).

**Speed and elapsed time point in opposite directions.** The ladder's unlocks
are all compressions: an afternoon becomes minutes, a quarter-long migration
becomes a workflow you kick off. Deepr's core claim is that an expert which has
existed for six months is better than one built this morning from the same
corpus. That value cannot be compressed - the elapsed time *is* the product.
Both can be true, and it means Deepr should not measure itself in the ladder's
units.

**Deepr is over-guarded for its rung.** It has step 3 and 4 guardrails - paid
API frozen at a hard $0 ceiling, metered keys quarantined out of the process,
native tools stripped at dispatch, per-expert write locks - at step 1
capability. That is deliberate given the operator's spend sensitivity and it is
the right trade, but it locates the blocker precisely: **guardrails are not
what is holding this at step 1. Trust in the loop is.**

## The sentence worth stealing

> "Did you read the code?" becomes "what context was the model missing and how
> do we solve it for next time?"

That is Deepr's thesis, put better than Deepr's own documentation put it. The
viva's reading queue, the gap router and the research practice are all
mechanisms for exactly that question, and none of them said so. Now folded into
[what-an-expert-is.md](what-an-expert-is.md).

## Related

- [the-feedback-signal.md](the-feedback-signal.md) - the substitute for cheap verification
- [autonomy-boundary.md](autonomy-boundary.md) - why the scheduler is not next
- [what-an-expert-is.md](what-an-expert-is.md) - what a context source has to be
