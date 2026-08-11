# What AI Proxy teaches Deepr

Status: notes, 2026-08-11. Read from the sibling project's README with the
owner's access; AI Proxy is private, so nothing here quotes more than the
concepts by name.

## Why the comparison is worth making

AI Proxy is a self-hosted digital-twin platform: expert replicas of an
organisation's people, deployed in the customer's own Azure tenant. Deepr is a
local-first research tool whose experts hold positions over a retained corpus.
Different products, different buyers, different infrastructure.

They converged anyway, independently, on four ideas:

| Idea | AI Proxy | Deepr |
|---|---|---|
| Facts are true *during* an interval | "Temporal Knowledge Graph: remembers WHEN facts were true" | closed-open intervals on one total axis, `record_time.py` |
| Opinions change and the change is the record | "tracks how opinions and strategies evolve over time" | position ledger, `supersession_reason`, perspective graph |
| Every claim carries where it came from | "source attribution with full provenance tracking" | position -> finding -> anchor -> retained source |
| The expert improves from use, not retraining | "self-improving: gets smarter from usage patterns" | the stated goal, and **the one Deepr has not built** |

Two systems arriving at temporal validity and provenance-per-claim from
different directions is the strongest evidence available that those
abstractions are load-bearing rather than taste. Neither borrowed them.

## The one thing AI Proxy has that Deepr does not

**Memory consolidation as a scheduled pass.** AI Proxy runs nightly processing
that "extracts lasting knowledge from conversations", against a memory divided
into working, episodic and semantic layers.

Deepr has the raw material and no such pass:

- Consult traces are written on every consult and, per
  [the-feedback-signal.md](the-feedback-signal.md), have **zero consumers**.
- The corpus grows only when a human or a `learn` run adds to it. Nothing an
  expert learns *from being used* ever reaches it.
- `expert_health` reads consult traces for exactly one purpose: how many days
  since anyone asked. Recency, not content.

So Deepr's experts accumulate from **reading** and never from **being
consulted**, which is half of how a person becomes experienced. The gap is not
a missing feature so much as a missing direction of flow.

This is worth being careful about rather than copying directly. Deepr's whole
argument is that a position must trace to a passage in retained text, and a
consolidation pass that promotes "what came up in conversation" into the
corpus would manufacture claims with no source behind them - the exact failure
[what-an-expert-is.md](what-an-expert-is.md) is built to prevent. The safe
shape is narrower:

1. **Consolidate questions, not answers.** What was asked repeatedly and
   answered badly is a gap, and gaps already have a home
   (`research_practice` pursuits, `expert practice`). A question is not a
   claim, so promoting one invents nothing.
2. **Consolidate against the falsifier, not the transcript.** A consult where
   the expert's stated position met a contradicting observation is precisely
   the ex-ante/outcome pairing the feedback-signal design is waiting for.
3. **Never let a conversation write a finding.** Findings are anchored in
   retained text by construction, and consolidation must not become a second,
   unanchored path into the ledger.

That reframes an item already on the roadmap: "resolve falsifiers and record
the discrepancy" is the consolidation pass, restricted to the one input that
cannot be contaminated.

## Three smaller borrowings

**Per-expert tool permissions.** AI Proxy gates tools per expert - restrict
CRM, block Deep Research. Deepr gates capacity (local / plan quota / metered)
globally and per run, but an expert cannot be told what it may reach for.
Worth having once experts act unattended, because the blast radius of an
unattended expert is the set of tools it can call.

**Layered memory as an explicit distinction.** Deepr has the layers without
naming them: `corpus/` is semantic, consult traces are episodic, the study
pass's working set is working memory. Naming them would make it obvious that
nothing is promoted between layers, which is the finding above.

**Background work as a first-class state.** AI Proxy treats a 30-minute deep
research run as a background task with a status surface. Deepr's studies run
tens of minutes and its UI has no honest representation of long-running work -
`research-live` invents progress denominators (`tokens/50000`, `cost/5`) rather
than showing the step it is on.

## What Deepr has that AI Proxy does not, and should keep

Stating this so the comparison does not read as one-directional.

- **A falsifier per position.** AI Proxy tracks how opinions evolve; Deepr
  requires each position to state what would overturn it *before* the evidence
  arrives. That is what makes a later discrepancy contamination-proof.
- **A cost posture that fails closed.** Metered dispatch is frozen and unknown
  state blocks. AI Proxy's model is "your Azure, your bill" - explicitly the
  customer's problem to bound.
- **An expert that authors itself.** Chosen name, standpoint, what it is glad
  to be asked, what it is weak on, how it wants to be depicted. AI Proxy's
  personas replicate a *real person*, so their identity is given rather than
  formed. Deepr's is derived from the reading, which is why it can change.
- **Grading that admits what it does not measure.** `expert health` is
  documented as artifact hygiene rather than quality.

## Related

- [the-feedback-signal.md](the-feedback-signal.md) - why consult traces are not
  yet feedback, and what pairing would make them so
- [what-an-expert-is.md](what-an-expert-is.md) - why a claim must reach a passage
- [expert-v2-identity-and-time.md](expert-v2-identity-and-time.md) - the temporal
  axis both projects arrived at
