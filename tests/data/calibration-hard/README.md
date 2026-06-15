# Extraction-faithfulness probe (adversarial corpus)

These four reports are **not** a normal calibration corpus. Each one deliberately
plants over-reach *traps*: a striking factual statement that is undercut by its
own surrounding context - a retracted benchmark number, a refuted "the bottleneck
is CPU" assumption, an unproven trial result (p = 0.18), a hypothetical sharding
gain, a debunked "$0.001/query" estimate, speculation about price cuts. A naive
extractor would pull the bare claim and produce an *ungrounded* belief.

## Why this exists

The clean calibration corpus (`../calibration/`) saturates - every extracted
claim grades as grounded, so no absorb threshold can be derived (see
`docs/CALIBRATION.md`). This probe was built to find out whether that saturation
is a corpus weakness or a real property of the extractor.

## Finding (2026-06-14, ~$0.04 extraction-only probe)

The absorb extractor (`gpt-5-mini`) **defused every trap** by attributing and
qualifying instead of asserting:

- "$0.001/query" -> "a widely shared estimate *put* cost at $0.001 ... *understates* real cost"
- "the intervention reduces errors" -> "this trial *did not show* that the intervention reduces errors"
- "the bottleneck is CPU" -> "profiling showed the CPU assumption was *wrong*"

Result: **78 of 78 claims grounded**; only one claim fell below 0.85 confidence
(a hypothetical, correctly down-weighted to 0.30). So the calibration saturation
reflects **extraction quality, not a measurement gap** - the extractor does not
hallucinate or over-reach even on adversarial input.

## Implication

Confidence-vs-grounding calibration is degenerate here *because the extractor is
faithful*; do not spend on a calibration curve to "fix" it. The trust story is
carried by the **continuity metrics** (`deepr eval continuity`, $0) and the
absorb verdict transparency, not by a saturated calibration curve. This corpus
can back a future **faithfulness eval**: extract from these reports, assert no
over-reach (no bare retracted/refuted/speculative claim is emitted).
