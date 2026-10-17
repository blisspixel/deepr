# Expert currency: order of operations

Status: the inspection and explicit world-time write shipped as a read and an
operator admission. Question-time preparation, the baseline comparison, and
any claim that a maintained expert judges better than a fresh read are still
open. This note is the sequence. The
[active roadmap](../../ROADMAP.md#order-of-operations) is the checklist.

## What an expert is

A fact list is the corpus: immutable bytes, a hash, a URL, and a fetch time.
A belief is an induced claim with evidence pointers, a confidence rank, and
recorded contradictions. A temporal record can say when a claim stopped
holding only when an admitted world interval exists. An expert prepares for
the question, studies sources into findings, revises a position while keeping
the previous one, and keeps a hypothesis or a dissent distinct from an
observation.

`beliefs/beliefs.json` is the claim store. Displayed confidence decays from
`updated_at` and is capped by source trust class. That number is a rank.
`BeliefChange.invalidated_at` is the world time a claim stopped holding.
Position `superseded_at` is the record time the store stopped stating a
position. Those clocks are not interchangeable. A missing world end means
unknown. It does not mean the claim is still true.

## Write rules

- Raw corpus bytes stay immutable.
- An observation can be invalidated. It is not erased. The archival snapshot
  keeps the previous claim.
- A world end is admitted only with an aware instant and a basis of
  `observed` or `source_resolved`, plus the evidence that dated it.
- An in-force mark is an operator affirmation. It does not move confidence
  or the decay clock.
- `archive_stale` may hide a low rank. It must not set `invalidated_at`.
- Interpretations, hypotheses, procedures, and recommendations change only
  through reviewed admission.
- A model may judge whether two claims conflict. Time bounds, hashes, spend,
  and the write stay deterministic. Word overlap does not close a claim.
- `resolve-conflicts` stays blocked.
- Consult, schedules, and automatic fallback do not gain metered authority.
- An expert may be asked, locally and at `$0`, what to study next. The
  answer is a proposal. It is not written into beliefs unless the operator
  runs an explicit admission.

## Sequence

1. **Inspection, shipped.** `deepr expert currency` reads live beliefs, the
   event log, corpus fetch times, and the position ledger's record clock.
   It writes nothing. `deepr expert close-claim --yes` and
   `deepr expert affirm-claim --yes` are the explicit admissions.
2. **S0 baseline.** Run the frozen local four-arm rehearsal. Publish the
   record, including failures. Human review happens before unblinding. A
   negative result completes measurement. It does not justify more autonomy.
3. **S1 prepared consultation.** CLI and MCP consult share one packet.
   The packet names the question, the sources and dates actually checked,
   the premises set aside, and the checks that were not done. Canonical
   beliefs, positions, study, and wiki do not change because a question
   arrived. `sync --fresh-context` remains a separate mutating command.
4. **S2 durable ends.** Revisions keep the predecessor addressable. Queries
   use the three-way status: closed at a time, explicitly in force, or
   unknown. Record-time supersession is not copied into world time.
5. **S3 separate layers.** Hypotheses, dissent, and recommendations are not
   retrieved as observations. Dissent stays unresolved until a reviewed
   admission.
6. **S4 held-out proof.** A recommendation that changes after contrary
   evidence, keeps the old recommendation, and beats a fresh read of the
   same sources. Until that exists, the directory has not earned the claim
   that it stayed current.

## What this sequence refuses

A larger belief file, a decay curve, a vendor recall score, sleep-time
overwrite, automatic contradiction resolution, and unattended paid refresh
do not make an expert current. Background study remains available through
the existing local study, absorb, and sync commands. It does not replace
question-time preparation.
