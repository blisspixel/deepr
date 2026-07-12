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
not truth. This is the selective-prediction / cascade pattern. Live dogfood on
2026-07-11 showed that the implementation did not fully honor it: normal
`conflict_resolver.detect_contradictions` copied Stage-1 router hits directly
into its return value, and generic `BeliefStore.add_belief` persisted router
hits as typed `contradicts` edges. Both paths now fail closed on meaning.
Normal detection returns only model-selected pairs, generic insertion never
persists lexical contradiction candidates, and the cost-$0 health path labels
router hits advisory. Report absorption requires an initial model YES plus a
second fresh-context structured disconfirmation pass before recording a
`model_confirmed` edge. Verification provenance is surfaced separately from
semantic correctness.

**Honesty requirements** that ride along: measure the decomposer (atomicity
+ coverage), calibrate the judge (biases are systematic), and keep read-side
queries $0 where the verdict is not safety-critical.

## Disposition of deepr's current checks

| Check | Today | Disposition |
|-------|-------|-------------|
| Boundary parsing (provider payloads, config, MCP args, extraction JSON shape) | strict Pydantic / dict guards | Deterministic, correct. Keep; continue the parse-don't-validate pass (Phase E). |
| `init` key/placeholder detection, path safety | string/structural | Deterministic, correct (form, not meaning). |
| Contradiction detection (`beliefs_contradict`, `_find_contradictions`, `detect_contradictions`) | lexical router plus model verdict | **Closed 2026-07-11:** `beliefs_contradict` is routing-only; normal detection returns only model-selected pairs; generic belief insertion cannot persist router hits; absorption requires a second fresh-context disconfirmation after an initial YES. Stored edges expose verification provenance, and continuity scores structural surfacing separately from verification coverage. Model confirmation still needs calibration and does not become independent semantic ground truth. |
| Belief dedup / merge (`_find_similar`, >0.7 overlap) | lexical router + model verdict (absorb path) | **Done on absorb (2026-06-14):** the >0.7 overlap is now a router; in the uncertain band (`<= 0.92`) `ReportAbsorber._verify_same_claim` decides SAME vs DIFFERENT fact, and `add_belief(dedup=False)` adds distinct claims separately instead of merging (no more "$10/M vs $30/M" data loss). Covers chat and sync too - they ingest through `ReportAbsorber.absorb`, not a direct `add_belief`. Remaining is only the low-stakes **shared** belief store (`_find_similar_in_domain` / `import_shared_beliefs`, a no-client cross-expert copy) and calibrating the verdict. |
| Claim grounding at absorb (report support self-rating) | extraction LLM, report-grounded | Model-based and grounded - correct direction. Strengthen with explicit entailment of claim vs its cited evidence span. |
| Atomic claim decomposition | extraction LLM prompt | Model-based - correct (finding 3). Tighten the prompt (FActScore/SAFE style). Atomicity is *meaning*, so per AGENTIC_BALANCE.md it is an Agent surface: **do NOT add a standalone lexical/regex atomicity detector, even as "telemetry"** - a word-marker scan for "and/but/;" is exactly the brittle-rule anti-pattern (a 2026-06-14 attempt added one and it was removed). If a cheap atomicity signal is wanted, derive it from the model (have the extractor self-tag each claim's atomicity in the same call, $0 extra) or measure it in the calibration harness; never a separate regex pass on this surface. |
| `validate`, reflection, council, conflict adjudication | LLM-as-judge | Keep, but calibrate and bias-mitigate (position/length/self-enhancement); the calibration harness (v2.15 #3) owns measuring and standardizing these. |
| ToT reasoning grounding + contradiction (`reasoning_graph`) | was lexical: 30% keyword-overlap "verified"; negation-word + hardcoded antonym-pair contradiction with `confidence = word_overlap` | **Fixed 2026-06-24.** Replaced the two lexical methods with `_analyze_claims`: one bounded model call returns grounding + contradictions, parsed deterministically (parse-don't-validate; unknown ids dropped; same-hypothesis pairs filtered as a form rule). With **no model it asserts nothing** (nothing verified, no contradictions) - the honest no-conclusion, never a keyword guess. Aligned with the file's existing "no synthetic fallback, degrade honestly" pattern. (Also fixed a latent `_emit_thought(evidence_refs=...)` TypeError the model path now reaches.) |
| Research-phase context contradictions (`context_chainer._detect_contradictions`) | regex on discourse markers ("however...contradicts", "in contrast", "on the other hand") labeled "contradictions" | **Audit finding (2026-06-24), lower severity, open.** Lexical-on-meaning, but it enriches the *next research phase's context* (ephemeral handoff), not the belief store, and the whole module is lexical context-structuring (entities = capitalized phrases, etc.). It mislabels discourse markers as contradictions. Fix when the phase-handoff structuring is made model-based; until then it is context enrichment, not a trust verdict. Tracked in ROADMAP. |

## Consequences for v2.15 #4 (atomicity + entailment screen)

The naive plan (a deterministic regex atomicity checker) is rejected by
finding 3: decomposition is the LLM's job. The corrected shape:

1. **Decomposition stays in the extraction LLM**; tighten the prompt for
   atomic, decontextualized, single-assertion claims.
2. **Atomicity measurement is model-derived, never a standalone lexical/regex
   pass.** Atomicity is meaning (an Agent surface in AGENTIC_BALANCE.md), so a
   "$0" monitor must not be a word-marker scan ("and/but/;") - that is the
   rejected naive regex checker wearing a telemetry costume (tried and removed
   2026-06-14). If a cheap signal is wanted, get it from the model that already
   ran: have the extraction LLM self-tag each claim's atomicity in the same
   call ($0 extra), or measure atomicity in the calibration harness against
   ground truth. No separate deterministic detector on this surface.
3. **The contradiction "screen"** is model judgment over the Stage-1-routed
   band, budget-bounded and recorded with provenance. An initial YES receives a
   fresh-context structured disconfirmation pass with statement order reversed;
   only two agreeing judgments create a model-confirmed edge. Deterministic code
   checks response shape only. Calibration remains required before treating the
   judge as an accuracy guarantee.

The model-based pieces (2 partially, 3 fully) need provider keys and the
calibration harness; the prompt tightening (1) and the router/consolidation
framing land at $0 first.

## Invariants

- A lexical/word-overlap result is never a semantic *verdict*; at most a
  high-recall router into a model check.
- One weak model YES is not sufficient to write an authoritative contradiction
  edge. Confirmation provenance describes the process used, not truth.
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
