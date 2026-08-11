# Where the autonomy boundary sits, and what moves it

Status: proposed, 2026-08-10. Derived from consulting Deepr's own harness
expert about Deepr's own loop, then applying its test to each step.

## The test

Asked where an unattended expert should be allowed to act, the Agentic Harness
Design expert gave a four-part rule:

> Autonomy should expand only where actions are **observable, reversible,
> sandboxed, and independently verifiable**.

That is better than the usual "automate the safe bits" because each part is
checkable against a specific step rather than argued about. It also produces an
uncomfortable and useful result: the step that most needs to be autonomous is
the one that currently fails the test.

Two further constraints from the same consult, both load-bearing:

> Generation and evaluation should be separated. An expert should not validate
> its own revisions solely through self-assessment.

> There is unresolved tension between frequent autonomous revision and
> epistemic stability. Rapid updating incorporates new evidence sooner, but can
> also amplify noise, source manipulation, or evaluator drift.

**Source manipulation is the one worth pausing on.** An expert that searches
the open web unattended, on questions it publishes in its own practice file,
can be fed material by anyone who reads that file. Nothing in the current
design defends against it. That is a reason to keep acquisition observable
rather than a reason to keep it manual.

## Applying it, step by step

| Step | Observable | Reversible | Sandboxed | Verifiable | Verdict |
|---|---|---|---|---|---|
| `source` | yes | yes | yes | yes | **autonomous** |
| `study` | yes | yes | yes | yes | **autonomous** |
| `graph` | yes | yes | yes | yes | **autonomous** |
| `practice` | yes | yes | yes | partly | **autonomous, bounded** |
| `viva` | yes | yes | yes | yes | **autonomous, budgeted** |
| `profile` | yes | partly | yes | no | **gated** |
| `brief` | yes | **no** | yes | partly | **gated** |

### Why `source` passes

Observable: every URL and every retention is logged. Reversible: the corpus is
content-addressed and append-only, so a bad acquisition is superseded rather
than destructive. Sandboxed: it fetches and writes files, and touches nothing
else. Verifiable: content-addressing plus mechanical anchor checking means a
later stage can prove what was actually read.

The residual risk is the manipulation one, and it is answerable without a
human in the loop for every fetch: log the queries, cap new publishers per
run, and flag a run where the corpus concentration moved sharply.

### Why `study` passes

It is the most expensive step and the most obviously autonomous. It reads a
frozen corpus, writes findings, checkpoints after every lens, and its output is
verifiable by a check the system already performs - whether a quoted anchor
appears in retained text. Nothing about it is destructive: findings are
regenerable from the corpus by construction.

### Why `brief` fails, and what that means

`brief` is not reversible. Every run discards the previous positions - their
likelihood bands, their falsifiers, the dissent they carried - and re-derives
from scratch. There is no prior kept and no history, so a bad autonomous
re-brief silently destroys the best judgement the expert had, with nothing to
roll back to.

It is also only partly verifiable. Citations are checked against the finding id
set, which catches an invented id and not a wrong one.

**So the autonomy roadmap is blocked on the identity-and-time work, and now
there is a reason rather than an assumption.** Once positions have thread
identity and an append-only history, a re-brief becomes a revision rather than
a replacement - it stops being destructive, and it passes the reversibility
test. The order was already right; this is why.

### Why `profile` is gated for now

Its shift history is append-only and safe. Its *standpoint* is overwritten, and
the standpoint is what a consult speaks from. Same fix as `brief`: once a
standpoint version is a record rather than a field, the overwrite becomes a
revision.

## What this changes about the plan

1. **Nothing new is needed for `source`, `study`, `graph` and `viva` to run
   unattended** beyond a scheduler and a budget. They already pass.
2. **`brief` and `profile` stay manual until V2 identity lands.** Not for
   safety theatre - because an autonomous run of either destroys judgement with
   no way back.
3. **Separation of generation and evaluation is already partly built.** `viva`
   examines with a different standpoint than the one under examination, which
   is the separation the expert asked for. It should be what gates an
   autonomous revision, rather than the reviser assessing itself.
4. **Budget before schedule.** Quota exhaustion is not hypothetical: two runs
   died on it in one afternoon, one mid-brief and one mid-consult. An
   unattended loop that does not model remaining quota will fail in the middle
   of the most expensive step and leave the expert half-updated.

## What this deliberately does not decide

The scheduling trigger - time, event, or staleness - is open, and a research
pass is out on it along with the failure and resumption question. The bar for
"speak unprompted without becoming noise" is also open, and it is the one most
likely to be got wrong by building it before it is specified.

## Related

- [expert-v2-identity-and-time.md](expert-v2-identity-and-time.md) - the work this is blocked on
- [what-an-expert-is.md](what-an-expert-is.md) - why a standpoint is the product
