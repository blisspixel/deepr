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

## Order of operations

1. Wire trust class through absorb (recording only - no behavior change;
   backfill existing beliefs as TERTIARY unless provenance says better).
2. Enforce floors in `BeliefStore.add_belief`/`add_contested_belief` +
   tests proving a TERTIARY claim cannot exceed its cap through any path
   (absorb, sync, merge, adjudication).
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
