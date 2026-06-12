# Design: Calibration Evidence and Source-Trust Scoring

Target: v2.15. Roadmap: Phase 3 "Eval methodology v2" + panel-review
findings (research-scientist and architect seats, 2026-06-11).
Status: design.

## Problem

Two related trust gaps, found independently by two panel reviewers:

1. **Unvalidated validator.** Absorb-time confidence is the extraction
   model rating itself ("how strongly does THIS REPORT support this
   claim"). Nobody has measured whether 0.8 means ~80% grounded. Until
   measured, the honest claim is "report-grounded candidates with
   confidence-as-signal", never "verified facts".
2. **No source-trust dimension.** A claim from a vendor blog and a claim
   from a peer-reviewed paper can carry identical confidence. This is also
   the ingestion-time prompt-injection hole: a poisoned web result can
   become a high-confidence belief through a well-phrased report.

One mechanism addresses both: measured calibration plus deterministic
trust floors.

## Design

### Part 1: Calibration harness (evidence, not vibes)

A repeatable protocol, run per extraction-model version:

1. **Corpus**: ~100 research reports spanning Deepr's real domains
   (held out, versioned, committed under `tests/data/calibration/`).
2. **Gold labels**: human-annotated per report - which claims are
   actually grounded in the text (the operator can grade in batches; the
   harness tracks inter-run agreement).
3. **Metrics**: extraction precision/recall vs gold; a calibration curve
   (claims rated 0.7 should be ~70% grounded); contradiction-heuristic
   precision/recall on a labeled pair set.
4. **Publication**: results land in `docs/CALIBRATION.md` with the model
   version and date - whatever the numbers say. The README's epistemics
   claims link there.
5. **Gate**: absorb's default `min_confidence` is *derived* from the
   curve (the threshold where measured grounding crosses 80%), not
   hand-picked.

### Part 2: Source-trust tiers with confidence floors

`TrustClass` already exists in `core/contracts.py` (PRIMARY / SECONDARY /
TERTIARY); today it is recorded but never enforced. The enforcement:

- Every absorbed claim carries the trust class of its weakest load-bearing
  source (web search results = TERTIARY by default; official docs /
  first-party instrument output = SECONDARY; operator-supplied primary
  documents = PRIMARY).
- **Floors (deterministic, not model-judged):**
  - TERTIARY-sourced claims cap at 0.6 confidence regardless of
    extraction score.
  - Crossing 0.8 requires at least one SECONDARY+ source, or two
    independent TERTIARY sources absorbed from different reports.
  - Adjudication (`ConflictResolver`) may not raise confidence above the
    floor; only new, better-sourced evidence can.
- This is the deterministic backstop for ingestion-time prompt injection:
  a single poisoned search result cannot mint a high-confidence belief,
  no matter how persuasive the text. (Complements, not replaces, the
  Phase 5 PromptSanitizer extension to the ingestion boundary.)

### Part 3: Eval methodology v2 (the surrounding frame)

Adds the expert-specific metrics the roadmap already names (gap-detection
success, belief-revision accuracy, citation freshness, integration
quality) with versioned methodology so runs compare across time. The
calibration harness is the first concrete v2 metric; A/B shadow mode
follows once metrics exist to compare.

## Literature grounding (distillr corpus `deepr-calibration`, 2026-06-11, ~$0.14)

Four-paper synthesis (arXiv 2601.16555 RRC, 2604.12184 TRUST, 2604.21193
DAVinCI, 2605.11334 VERDI) run through the validated distillr integration:

- **Adopt: selective recalibration** - the corpus thesis is that a
  threshold-triggered *second* check on uncertain claims only beats both
  single-pass scoring and always-on multi-agent aggregation. Mapped to
  absorb: claims landing in an uncertainty band (roughly 0.5-0.75 after
  extraction) get one cheap calibrator call; confident and clearly-weak
  claims skip it. This is a bounded-cost upgrade to the pipeline and slots
  between extraction and the trust floors.
- **Adopt: abstention as a first-class outcome** - DAVinCI overrides
  low-attribution verdicts to "Not Enough Info" rather than guessing;
  TRUST abstains on 70-82% of hard claims. Absorb currently has
  absorbed/rejected/flagged; add an explicit `insufficient_grounding`
  bucket distinct from rejected, so "the report does not really support
  this" stops masquerading as "this is false".
- **Use for threshold derivation**: VERDI's Platt-scaled logistic
  regression over verification-trace features is the cheap post-hoc
  calibrator shape - apply Platt scaling to the calibration-harness
  outputs when deriving absorb's default threshold from the measured
  curve (Part 1 step 4), rather than reading the raw curve.
- **Confirmed caveat**: recalibration thresholds in the literature are
  dataset-specific with unreported search cost. The harness must derive
  thresholds from Deepr's own corpus and re-derive on extraction-model
  changes - both already in the design; the corpus says they are
  load-bearing, not optional.

## Order of operations

1. [x] Wire trust class through absorb (shipped 2026-06-11: `Belief.trust_class`, absorb marks research-derived beliefs tertiary, retroactive tertiary default on load).
2. [x] Enforce floors (shipped 2026-06-11, design refinement: enforcement lives in `Belief.get_current_confidence` - read-time like decay - rather than at the write paths, so the cap holds retroactively and through EVERY path including merge and adjudication; regression-tested incl. the poisoned-0.98-extraction scenario).
3. Build the calibration corpus + grading harness (`deepr eval calibrate`).
4. First calibration run; publish `docs/CALIBRATION.md`; derive absorb's
   default threshold from the curve.
5. Re-run on extraction-model changes (the registry knows the model;
   stale calibration = CI warning, same pattern as stale-model checks).

## Open questions

- Grading burden: 100 reports is hours of human work - possibly
  crowdsourced across contributors with agreement scoring, or seeded with
  a strong-model pre-grade that the human corrects (pre-grade bias must be
  reported if so).
- Whether floors apply retroactively on load (lean: yes, computed at read
  time - confidence is already decay-adjusted at read time).

## Exit criteria

`docs/CALIBRATION.md` exists with real measured numbers; absorb's
threshold cites it; a poisoned-source test proves the 0.6 ceiling holds
through every write path; README epistemics claims link to evidence.
