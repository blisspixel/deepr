# Advice representation diagnostic, 2026-10-27

This record covers a frozen local before/after diagnostic of the 2026-10-27
evidence representation repairs. It is a small, partially completed,
model-reviewed diagnostic. It is not semantic acceptance, not human-calibrated
review, not default-on authority for preparation, and not evidence that an
expert got better. Default consultation remains stored-context-only.

## What was compared

- BEFORE: v2.51.0 (`60c6754b`).
- AFTER: candidate `ccd360f4`, the evidence-delivery and prepared-packet
  repairs as first implemented. Review fixes made after collection began (verified
  excerpt containment and fencing, projection compaction, the synthesis-cap
  refusal, the final-release listing field and stored-source label scoping)
  are not covered by these results.
- Answering model: local `qwen3.6:27b`, digest `bcbdbd4bcf86`, on an AMD
  Phoenix integrated GPU (about 8 generated tokens per second). The
  2026-10-25 trials used digest `a50eda8e` on an RTX 4090. The model and
  hardware are therefore disclosed substitutions, and both arms were
  regenerated. Shipped answer options were used. Preparation time limits were
  scaled by 13.333 through a harness-only clock shim recorded in every
  receipt.
- Inputs: the retained 2026-10-25 S1-002 fixture and its official PyPI bytes
  for `filelock` 4.2.4. This case is exposed, because the defects were
  diagnosed on it. A held-out `httpx` 0.28.1 question was fixed before one
  bounded public PyPI capture: 2 requests, both 200, 83,362 decoded bytes.
  The protocol also defined a negative control and a held-out brief replay
  on S0 world 1.

The protocol, rubric, per-case omission checklists and decision rule were
frozen before generation. The manifest SHA-256 is `0179dc4d...`, after one
pre-generation binding amendment that is recorded in the protocol. Reviewer
inputs were hash-frozen before review, and the arm alignment was sealed by
hash and verified on unsealing.

## Collection outcome

Of 12 planned cells, 6 completed:
- P-EXP: two repeats per arm.
- P-HO: one repeat per arm.

Each of those cells kept its fixture unchanged and made no canonical writes.
Every completed call stopped normally with known usage.

At 18:52:41Z another local process stopped the shared Ollama service. One
held-out AFTER answer was cut off mid-generation; it is retained, and its
usage is unknown. The negative control, the brief replay and one held-out
BEFORE cell never started. No retry, resume or second collection was run,
so the brief rendering repair and the negative control produced no evidence.
Stored-source dates were not exercised, by design.

## Review

Two independent Claude reviewers on different model versions reviewed each
packet blind. Neither reviewer wrote the code or produced the answers. They
checked claims against the retained PyPI bytes. The frozen rule counts AFTER
as improved on a case only if both reviewers prefer it on support or harmful
unsupported claims and neither rates it worse on material omissions.

| Case | Label | Frozen rule: AFTER improved? |
| --- | --- | --- |
| P-EXP repeat 1 | exposed | No. Both reviewers preferred AFTER on omissions; neither preferred it on support or harmful claims |
| P-EXP repeat 2 | exposed | Yes. Both preferred AFTER on support and harmful claims |
| P-HO repeat 1 | held-out | No. Both preferred AFTER on support, but one reviewer rated its omissions worse |

Both reviewers could guess the arm from format, because AFTER answers cite
observation ids and raw hashes as the repaired text requests. They recorded
that suspicion and did not use it in scoring, but the blinding was partially
broken.

## Defects found

- **Both arms:** called `httpx` 0.28.1 "not current" because only pre-releases
  (1.0.dev1 to 1.0.dev6) rank above it. Neither held-out answer mentioned yank
  status or scoped the digest to one named archive. A later fix adds the
  highest final, non-yanked listed version; it is untested here.
- **BEFORE:** invented "newer 4.x versions exist" for `filelock`, although the
  index lists 4.2.4 as the highest version. It also called the `httpx` index
  "truncated", which is false.
- **AFTER:** told the user fetch times were unrecorded, although the
  preparation observations carry their own times. The delivered prompts show
  the cause: the new "fetch time unrecorded" label on stored passages was
  read as applying to the whole context. It became an unchecked preparation
  assumption and then reached the answer. This scope ambiguity came from the
  repair itself. Labels are now scoped to stored expert sources, a fix that
  is not covered by these results.

## Conclusion

One exposed repeat met the frozen rule; the other exposed repeat and the one
held-out pair did not. The sample is very small, the model was substituted,
the blinding was partly broken, and the negative control and brief case
produced no evidence. No improvement claim follows. Both arms still give
materially defective advice. The prepared-advice qualification, brief
judgment and default-on gates remain open. The repairs ship as repairs to
representation and reliability.

## Collection 002 (same day, shipped v2.51.1)

A separately frozen collection 002 was set up to finish the cells that never
ran: the negative control and the held-out brief replay, comparing
`60c6754b` with shipped v2.51.1 (`4a0508e1`). Collection 002 used the same
fixtures, options, bounds and rubric, fresh reviewers were planned, and no
attempted cell was rerun. Its dry run found that, with a prepared layer
present, v2.51.1 dropped the expert's only stored position from the final
prompt while delivering an uncited reference passage. That is a delivery
priority defect; v2.51.2 fixes it.

The live run completed one cell (negative control, BEFORE). The host's
low-memory safeguard then stopped the run while the AFTER negative-control
cell was generating. The local model was resident alongside a concurrent
full test suite and other sessions' work. That cell is retained with unknown
usage. The brief cells never started. No retry was made, so there is still
no evidence for the negative control comparison or the brief rendering
repair.

## Collection 003 (2026-10-28, shipped v2.51.2)

The operator asked for the open evaluation work to be finished, so a third
collection was frozen before any generation. It compared `60c6754b` with
shipped v2.51.2 (`bf5d1943`) and used the same fixtures, options, bounds,
rubric and decision rule. The manifest SHA-256 is `ec66ec40...`. No attempted
cell from an earlier collection was reused. Before the run, the dry run
confirmed that v2.51.2 now delivers the expert's stored position (the
collection-002 finding). The parent ran no heavy jobs during the run, and the
other sessions on the host agreed to reduce load.

**Cells.** Three cells completed with known usage, normal stops, unchanged
fixtures and no canonical writes: negative control BEFORE, negative control
AFTER, and brief AFTER. The host's low-memory safeguard then stopped the
brief BEFORE cell mid-generation. It is retained with unknown usage and was
not retried, so the brief case still has no comparison.

**Negative-control review.** Two fresh Claude reviewers on different model
versions reviewed the pair blind. Neither had seen earlier packets. The arm
alignment was sealed by hash, and review inputs and outputs were hash-frozen
before unsealing. The parent read the alignment file while preparing packets;
the parent is not a reviewer and passed no arm information.

| Reviewer | Support | Omissions | Harmful claims | Usefulness |
| --- | --- | --- | --- | --- |
| 1 | same | BEFORE better | AFTER better | AFTER better |
| 2 | BEFORE better | BEFORE better | AFTER better | AFTER better |

The frozen rule is **not met**. Both reviewers preferred AFTER on harmful
claims, but both rated it worse on omissions. AFTER kept the filelock
evidence apart from the httpx question and recommended real checks on 3.14,
yet never used the retained httpx lockfile hashes.

**Cause (mechanical record, never shown to reviewers).** The AFTER final
prompt delivered the stored position but omitted the stored `uv.lock`
passage, the finding and the study limitations. The prepared view used most
of the 16,000-character prompt. BEFORE delivered the passage and omitted the
position. So each arm lost a different piece of the expert's own context to
the shared budget, and a reviewer cannot attribute the answer differences to
representation alone. Filed as #299. After unblinding, the parent noted that
the "Origin not recorded" text both reviewers could not trace was in
BEFORE's delivered prompt. AFTER's statement that the httpx data was omitted
from its prompt was accurate. Ratings were not changed.

**Conclusion.** No improvement claim. The negative control shows that
preparation can still displace stored evidence (#299). The brief rendering
repair is still unmeasured. The prepared-advice qualification, brief judgment
and default-on gates remain open.

Evidence asset: `advice-representation-2026-10-27-collection-003.zip`
(unblinded: protocol, harness, manifests, run receipts with delivered prompts
and raw responses, mechanical record, packets, sealed alignment, both reviews),
attached to the v2.51.2 release with its SHA-256.

## Collection 004 (2026-10-28, brief replay pair)

A fourth collection, frozen before generation, ran only the held-out brief
replay pair: `60c6754b` versus v2.51.2 (`bf5d1943`). The brief path is
unchanged since. The manifest SHA-256 is `d269e8e6...`. It ran with no
concurrent heavy work on the host. Both cells completed with known usage and
normal stops. Two fresh Claude reviewers on different model versions reviewed
the pair blind, under the same sealing and freezing steps.

| Reviewer | Support | Omissions | Harmful claims | Usefulness |
| --- | --- | --- | --- | --- |
| 1 | BEFORE better | AFTER better | same | AFTER better |
| 2 | same | AFTER better | same | AFTER better |

The frozen rule is **not met**: neither reviewer preferred AFTER on support or
harmful claims, although both preferred it on omissions and usefulness. Both
arms stated "at-least-once" delivery without labelling it as inference, and
both used falsifiers that only ask for a document.

**Defect found in AFTER.** Both reviewers flagged citations such as "S2" that
match no source. After unblinding, the parent traced them to the prompt-local
excerpt keys added in v2.51.1. The model copied the keys into the brief, and
a saved brief has no legend to resolve them. v2.51.3 keys excerpts by a
retained-corpus sha prefix (`corpus:<12 hex>`), which resolves without the
prompt. A harness dry run delivers all 40 keyed excerpt lines, none withheld.
That shows delivery only.

Mechanically, AFTER delivered 11 of 11 first anchors and BEFORE 3 of 11.
Neither delivered source dates, because the retained corpus records none.

**Conclusion.** No improvement claim. The brief representation repair
delivers more source text, and model reviewers judged the resulting brief
more complete, but not better supported. Brief judgment quality remains
open.

Evidence asset: `advice-representation-2026-10-27-collection-004.zip` on
the v2.51.3 release.

Reproduction asset: `advice-representation-2026-10-27-repro.zip` on the
v2.51.1 release. It is unblinded and contains the protocol, harness, frozen
manifests, fixtures, the held-out capture, every run receipt with its
delivered prompt and raw response, mechanical receipts, packets, sealed
alignment and both reviewers' outputs. SHA-256 is recorded in the release
`SHA256SUMS`.
