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

Reproduction asset: `advice-representation-2026-10-27-repro.zip` on the
v2.51.1 release. It is unblinded and contains the protocol, harness, frozen
manifests, fixtures, the held-out capture, every run receipt with its
delivered prompt and raw response, mechanical receipts, packets, sealed
alignment and both reviewers' outputs. SHA-256 is recorded in the release
`SHA256SUMS`.
