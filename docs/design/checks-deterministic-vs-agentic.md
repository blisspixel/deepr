# Design: Deterministic checks vs agentic checks (what belongs where)

Status: design, 2026-06-13. Cross-cutting; governs the contradiction screen,
claim atomicity, dedup, and grounding checks. Grounded in a cited
literature pass (June 2026). Referenced by
[belief-lifecycle.md](belief-lifecycle.md) (entailment screen, atomicity) and
the Phase E "parse, don't validate" track.

## Problem

deepr makes two kinds of checks, and has been conflating them. Some are
*structural* (is this valid JSON, is confidence in [0,1], is this enum a
known value, is this key a placeholder). Others are *semantic* (do these two
beliefs contradict, does the report support this claim, is this claim a
single assertion, are these two claims the same). Several semantic checks are
currently implemented with lexical heuristics - word-overlap and
negation-word sets:

- `conflict_resolver.beliefs_contradict`: opposite polarity + >2 shared words.
- `beliefs._find_contradictions`: a second, duplicated copy of that heuristic.
- `beliefs._find_similar` / `_find_similar_in_domain`: >0.7 word overlap to
  merge "duplicate" beliefs.

These produce the known false-positive contradiction flags (phrasing-level,
not substantive) recorded in the live-validation backlog and in
belief-lifecycle.md finding 8. The question this note settles: which checks
belong in deterministic code, and which must be delegated to a model.

## Literature grounding (cited research, June 2026)

Adversarially verified (3-vote) findings from the claim-verification and
LLM-evaluation literature:

1. **Lexical overlap is a poor proxy for meaning.** ROUGE-1 and
   named-entity-overlap disagree with both NLI metrics and human judgment for
   hallucination detection, scoring only marginally above a random baseline
   (arXiv 2402.10496). Models that adopt a "lexical overlap heuristic"
   collapse on the controlled HANS adversarial set (arXiv 1902.01007). Our
   word-overlap contradiction/similarity checks are this failure mode.
2. **NLI/entailment is the reliable lightweight semantic verifier** - at
   sentence-level granularity it correlates with human annotation (Pearson
   ~0.49) and often beats supervised and lexical metrics (2402.10496). It
   degrades at atomic-fact granularity, on unverifiable claims, and in
   low-resource languages, where retrieval-grounded judgment is needed.
3. **Atomic claim decomposition should be model-based, not rule-based.** The
   canonical pipelines (FActScore arXiv 2305.14251, SAFE arXiv 2403.18802)
   use an LLM to split text into atomic facts; FActScore finds LM-generated
   atomic facts "effective and close to human." No credible source
   recommends a regex/deterministic decomposer.
4. **Grounding is retrieval-grounded model judgment, not string matching.**
   FActScore retrieves passages and has an evaluator LM decide
   supported/not-supported; SAFE issues search queries and reasons over
   results. Retrieval grounding substantially beats closed-book judging
   (2305.14251).
5. **Decomposition is not a neutral preprocessing step.** Factuality scores
   are sensitive to the decomposition method and error can originate in the
   decomposer itself, so decomposition needs its own quality measurement -
   DecompScore measures atomicity + coverage (ACL StarSem 2024,
   aclanthology 2024.starsem-1.13; corroborated by VeriFastScore
   2505.16973).
6. **LLM-as-judge is not automatically trustworthy.** It has systematic,
   non-random biases - position, length/verbosity, concreteness,
   self-enhancement (survey arXiv 2411.15594; position-bias study
   2406.07791). Reliability requires deliberate validation, calibration, and
   bias mitigation, not off-the-shelf trust. (Caveat: bias magnitudes are
   model-dependent and shrinking in newer judges; calibrate against the
   specific model, do not assume fixed magnitudes.)
7. **Parse, don't validate** for the deterministic side (lexi-lambda 2019;
   schemasafe parser-not-validator doc): a typed parser returns the typed
   value on success and makes parsed-but-unvalidated data unrepresentable -
   this is where structure, types, ranges, and enums belong. deepr already
   does this with strict Pydantic v2 at boundaries (Phase E).

## The boundary

**Deterministic checks own *form*** - anything decidable from structure
alone: JSON shape, types, numeric ranges, enum membership, presence,
placeholder/format detection, path safety. Implement as "parse, don't
validate": parse once at the boundary into a rich typed value (strict
Pydantic v2, frozen dataclasses, NewTypes), so illegal states are
unrepresentable and core logic never sees raw primitives.

**Model-based checks own *meaning*** - entailment, contradiction,
grounding/support, decomposition/atomicity, semantic equivalence/dedup.
These are never decided from lexical overlap. Sentence-level checks use NLI;
atomic-fact and grounding checks use a retrieval-grounded LLM judge.

**The bridge (the only place lexical heuristics belong in a semantic
check): a cheap, high-recall pre-filter that *routes*, never *concludes*.**
The deterministic/lexical layer flags candidate pairs to keep the expensive
model pass bounded (cost + latency); a model makes the verdict on the
flagged (uncertain) band. The cheap layer's job is recall and cost control,
not truth. This is the selective-prediction / cascade pattern, and it is
exactly the two-stage shape `conflict_resolver.detect_contradictions`
already has (heuristic Stage 1, LLM Stage 2) - the bug is that the absorb
and health-check paths call Stage 1 *alone as a verdict*.

**Honesty requirements** that ride along: measure the decomposer (atomicity
+ coverage), calibrate the judge (biases are systematic), and keep read-side
queries $0 where the verdict is not safety-critical.

## Disposition of deepr's current checks

| Check | Today | Disposition |
|-------|-------|-------------|
| Boundary parsing (provider payloads, config, MCP args, extraction JSON shape) | strict Pydantic / dict guards | Deterministic, correct. Keep; continue the parse-don't-validate pass (Phase E). |
| `init` key/placeholder detection, path safety | string/structural | Deterministic, correct (form, not meaning). |
| Contradiction detection (`beliefs_contradict`, duplicated `_find_contradictions`) | lexical negation + overlap | Semantic. Keep lexical only as a high-recall Stage-1 *router*; require an entailment/NLI verdict on the flagged band before recording a contradiction. Consolidate the duplicate into one predicate. (belief-lifecycle.md #5) |
| Belief dedup / merge (`_find_similar`, `_find_similar_in_domain`, >0.7 overlap) | lexical | Semantic. Lexical is a router at best; the merge verdict should use embeddings (cosine, already in `gap_discovery._cosine_similarity`) or NLI, calibration-gated. Lower risk than contradiction; sequence after it. |
| Claim grounding at absorb (report support self-rating) | extraction LLM, report-grounded | Model-based and grounded - correct direction. Strengthen with explicit entailment of claim vs its cited evidence span. |
| Atomic claim decomposition | extraction LLM prompt | Model-based - correct (finding 3). Tighten the prompt (FActScore/SAFE style). Add a DecompScore-style atomicity-rate *monitor* as telemetry and a router signal, explicitly NOT a regex splitter or a gate on storage; the calibration harness validates whether the cheap signal tracks true atomicity before any paid split pass. |
| `validate`, reflection, council, conflict adjudication | LLM-as-judge | Keep, but calibrate and bias-mitigate (position/length/self-enhancement); the calibration harness (v2.15 #3) owns measuring and standardizing these. |

## Consequences for v2.15 #4 (atomicity + entailment screen)

The naive plan (a deterministic regex atomicity checker) is rejected by
finding 3: decomposition is the LLM's job. The corrected shape:

1. **Decomposition stays in the extraction LLM**; tighten the prompt for
   atomic, decontextualized, single-assertion claims.
2. **A $0 atomicity-rate monitor** (DecompScore-style) measures the
   decomposer's output as telemetry and as a router that flags compound
   claims - never as a splitter or a storage gate, and treated as a proxy
   until the calibration harness shows it tracks true atomicity.
3. **The contradiction "screen"** becomes the Stage-2 entailment verdict on
   the Stage-1-routed band (sentence-level NLI first; retrieval-grounded LLM
   where NLI is too coarse), calibration-gated and budget-bounded.

The model-based pieces (2 partially, 3 fully) need provider keys and the
calibration harness; the prompt tightening (1) and the router/consolidation
framing land at $0 first.

## Invariants

- A lexical/word-overlap result is never a semantic *verdict*; at most a
  high-recall router into a model check.
- Structural checks stay deterministic and parse-don't-validate.
- Every model judge is calibrated and bias-checked before its verdict is
  trusted (no off-the-shelf LLM-as-judge trust).
- Read-side queries stay $0 where the verdict is not safety-critical; paid
  model verdicts are budget-bounded and calibration-gated.

## Sources

Lexical brittleness: arXiv 2402.10496, 1902.01007 (HANS). NLI as lightweight
verifier: 2402.10496. LLM decomposition: 2305.14251 (FActScore), 2403.18802
(SAFE), 2024.starsem-1.13 (DecompScore), 2505.16973 (VeriFastScore).
Retrieval-grounded judgment: 2305.14251, 2403.18802. LLM-judge bias +
calibration: 2411.15594, 2406.07791. Parse, don't validate: lexi-lambda
(2019), schemasafe parser-not-validator doc.
