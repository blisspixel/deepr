# Correction survival diagnostic, first mock runs, 2026-10-19

Scope: issue #259, first increment. Mock answers only: no model was called and
no answer was reviewed. This records transport, stage receipts and accounting.
It is not an answer-quality result, a memory-value claim or part of S0.

Historical record: these statements describe the original v1 collection.
Subsequent blinded review found source/fixture inconsistencies and completed
its labels without changing the original run. The prospective v2 fixture has
a different identity; inspect v1 with the retained compatible v2.50.43
implementation and its explicit original recipe pin. Current code correctly
refuses that old case set.

## Runs

`deepr eval correction-survival` over case set `correction-survival-v1`
(11 cases, 3 worlds, 3 arms, one case repeated for 2 cycles), at `$0`.

| Distractors per world | Attempts (scheduled / recorded / failed) | Production retrieval | Production delivery | Historical isolation |
|---|---|---|---|---|
| 0 | 36 / 36 / 0 | 18 of 18 selected | 18 of 18 delivered | 3 of 3 isolated |
| 60 | 36 / 36 / 0 | 17 of 18 selected, 1 missed | 17 delivered, 1 never assembled | 3 of 3 isolated |

Historical isolation holds by construction here: world 1 contains only the
v2 manual. The check is a guard against future world or arm changes, not a
measured property of retrieval. The oracle arm delivered all 18 source-backed
obligations in both runs. The
two remaining obligations (`defer-macos`, `no-later-knowledge`) have no
source by design and are judged only at review. The repeated case kept the
same study fingerprint and identical per-position provenance counts across
both cycles, so repetition added no apparent corroboration.

## Stage-localized miss

With 60 on-topic distractors, `near-match-version` ("On Tern 2 Windows agents,
are idempotency keys on by default?") lost obligation `v2-default` at
retrieval. The finding was represented in the study and presented to brief
synthesis, but `build_consult_context` did not select it, so it was never
assembled into the prompt; the oracle arm delivered it.

The cause is mechanical. Consult ranks findings by literal token overlap. The
filler shares four tokens with the question (`tern`, `agents`, `idempotency`,
`keys`); the v2 finding shares three, because it says "agent platform", not
"agents". The world-3 brief's retry position cites the 3.0 findings, so
nothing carries the v2 finding in as position support, and the 24-finding cap
fills with filler. This is the near-match weakness the issue predicted. It is
recorded as a routing gap, not fixed here: changing the router needs its own
measurement, and a lexical score may route but never decide relevance.

## First local answers

`deepr eval correction-survival --local-model qwen3.8:27b --model-digest
aaee06c39dcf...` (digest `aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`,
Q4_K_M), no distractors, at `$0`. Each answer is one call through the
production consult system prompt and native local dispatch, with the digest
attested per call.

| Arm | Attempts completed | Median seconds | Prompt tokens | Output tokens | Median answer chars |
|---|---|---|---|---|---|
| production | 12 of 12 | 98 | 28,790 | 7,368 | 2,449 |
| oracle_packet | 12 of 12 | 78 | 9,791 | 6,564 | 2,278 |
| fresh_sources | 12 of 12 | 113 | 13,822 | 8,007 | 3,073 |

All 36 calls stopped normally; none was truncated or failed, and the digest
never changed. The completed run verifies under `load_run` against the current
case set and recipe. The stage receipts match the mock run (18 of 18
source-backed obligations delivered in every arm). These are mechanical facts
only: no answer has been labelled, so nothing here says whether a correction
was used, ignored or misapplied.

A blinded review packet (36 answers under opaque ids, 60 obligation rows, the
frozen rubric and a label template) was generated with the arm key in a
separate folder. Answer style can still hint at an arm, and the run directory
names arms, so a reviewer should work from the packet only. The run, packet
and key are retained under `.agent/correction-survival-2026-10-19/`.

## Limits

The worlds are tiny, synthetic and authored for this diagnostic. The brief
synthesis is frozen fixture output, so no briefing-stage loss from a real
model is measured. The fresh arm receives sources in corpus order; the
fixture's real origins sort before the filler, which favours it here. Mock
answers say nothing about whether a correction would be used, ignored or
misapplied. The local answers above still need blinded reviewer labels.
