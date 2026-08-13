# Implementation plan: living expert research stack

Status: active plan, 2026-08-05.
**Order of operations is mandatory.** Later steps assume earlier steps are done
or explicitly skipped with a written reason.

| Related doc | Role |
|---|---|
| [../design/living-expert-research-stack.md](../design/living-expert-research-stack.md) | Research: Distillr, Learny, capacity honesty, gaps |
| [../design/diverse-expert-council.md](../design/diverse-expert-council.md) | Research + design: diverse mock councils beyond default domains |
| [../design/exceptional-expert-quality.md](../design/exceptional-expert-quality.md) | Living expert / wiki quality bar |
| [../INTEGRATIONS.md](../INTEGRATIONS.md) | Recon / Distillr / Primr independence model |
| [../CAPACITY.md](../CAPACITY.md) | What capacity is executable today |

No calendar or "days of work" estimates. Sequencing is by dependency only.

---

## End state (what "done" means for this track)

An operator can:

1. Describe an **idea or project** (or point at README/roadmap text).
2. Get a **diverse council plan** (not only the obvious domain roles).
3. **Make** those experts local.
4. **Deepen** each with Distill (and optional Learny export) under honest $0 API
   or proven plan capacity.
5. **Absorb** corpus into the expert TKG with correct trust classes.
6. **Regenerate** wiki digests and **score** structural quality.
7. **Consult** the council (including challenge/dissent framing).
8. **Improve** continuously (gaps, sync, re-deepen).

Experts are not bags of confidence facts. They hold research memory, stance,
fail patterns, elite bar, open questions - structured in the store, browsable
as derived wiki views, temporal via the TKG.

---

## Capacity invariants (never reorder past these)

1. Local Ollama is the default $0 API path for Deepr absorb/sync/consult.
2. Distill analysis under `--cost-mode no-metered` is the default $0 API path
   for corpus building (local model + public fetch). Plan-quota CLIs inside
   Distill are **not live** until Distill proves them.
3. Deepr plan execution is Claude Code only when paid-overage-off is proven.
   Codex, Grok, Antigravity, Copilot remain blocked until their proofs exist.
4. Distill/Learny artifacts never write Deepr beliefs without `expert absorb`.
5. Metered API production dispatch stays frozen until account-control verifiers
   ship. Do not plan features that require silent paid spend.

---

## Order of operations (build sequence)

Complete each step (or mark N/A with reason) before starting the next.

### Step 0 - Documentation and sequencing (foundation)

| ID | Work | Done when |
|---|---|---|
| 0.1 | Design: living stack | This plan + living-expert-research-stack.md exist and match capacity truth |
| 0.2 | Design: diverse council | diverse-expert-council.md exists |
| 0.3 | ROADMAP points here | Unreleased section links design + plan; no loose "next" without order |
| 0.4 | INTEGRATIONS points here | Living-expert paragraph present |

**Depends on:** nothing.
**Status:** done for 0.1-0.4 once this revision lands.

### Step 1 - Inventory honesty and trust (so depth is not wasted)

| ID | Work | Done when |
|---|---|---|
| 1.1 | Claims shown, not only Documents | `expert list` / MCP list expose claim_count |
| 1.2 | Trust class on absorb | `--trust-class`; file default secondary |
| 1.3 | Corroboration merge | Multi-source raises tertiary ceiling; secondary/primary uncapped |
| 1.4 | Quality scorecard | `expert quality` grades circularity, multi-source, origins |
| 1.5 | Improve orchestrator | `expert improve` emits ordered operator steps |

**Depends on:** Step 0.
**Status:** done (prior work in this track).

### Step 2 - Deepen path recipes (corpus before more features)

| ID | Work | Done when |
|---|---|---|
| 2.1 | Deepen plan CLI | `expert deepen-plan NAME` emits Distill no-metered + absorb secondary |
| 2.2 | Wiki digest partitions | Stance / multi-source / secondary / tertiary / sources / domain inventory |
| 2.3 | Improve points at deepen-plan | Operator-required steps include deepen-plan + digest |
| 2.4 | Tests | Unit tests for digest sections + deepen-plan |

**Depends on:** Step 1.
**Status:** done for 2.1-2.4.

### Step 3 - Diverse council composition (this slice)

| ID | Work | Done when |
|---|---|---|
| 3.1 | Design: diverse council axes | Axes documented (domain, adversary, ops, legal, outsider, extreme user, ...) |
| 3.2 | `expert council-plan` | From idea/README text: propose diverse roles, make argv, deepen queries, consult prompt |
| 3.3 | Local composition | `--local` uses Ollama when available; else structural scaffold (no fake diversity) |
| 3.4 | Diversity contract | Plan requires multi-axis roles, not N clones of the same domain |
| 3.5 | Tests | Schema + diversity constraints + CLI smoke |

**Depends on:** Step 2 (operators can deepen after make).
**Status:** done for 3.1-3.5 (`expert council-plan`, diversity gate, design, tests).

### Step 3.5 - Decide the ingestion shape (**blocking gate, decide before 4.1**)

Absorb emits atomic `Belief` objects and nothing else
(`report_absorber.py:930-955`, `:522-537`). If `absorb-dir` ships as a
beliefs-only batch loop, every Distill and Learny corpus it ingests is
permanently flattened to single-sentence facts, and the insight layer has to
re-read all of it later. Design: [../design/expert-insight-layer.md](../design/expert-insight-layer.md).

**Operator decisions, 2026-08-05 (settled, do not re-open without new evidence):**

1. **Corpus retention: retain, content-addressed.** Sources are copied under the
   expert directory at `corpus/sources/<sha256>.md` with a `corpus/index.jsonl`
   carrying origin key, url, publisher, fetched_at, sha256, and trust class.
   Deduped across the fleet by hash. Accepted cost: tens of MB per expert.
   Rationale: an expert that cannot re-read its own sources cannot be studied
   through a second lens, cannot show a passage, and cannot be re-derived when
   the frame changes. Pointers into the operator's Distill library were rejected
   because they break on move, prune, or rename, and leave no self-contained
   expert export.
2. **Absorb routes through the source-pack pipeline.** `absorb --file` builds a
   one-source pack, then `claim_extraction` -> `claim_verification` ->
   `graph_commit_envelope` -> `apply`, emitting beliefs **and** typed shapes.
   Cost is one extra model call per absorb, $0 on `--local`. Widening the
   absorber's own prompt was rejected: its gates are a `min_confidence` float
   and two lexical routers, none of which can enforce `requires_external_support`
   or `requires_disconfirming_signals`, so typed records would be admitted
   through a gate never designed for them.

| ID | Work | Done when |
|---|---|---|
| 3.5a | Absorb routes through the source-pack pipeline | `absorb --file` emits typed shapes as well as beliefs; per-kind policy gates enforced; `--local` path stays $0 |
| 3.5b | Typed-state provenance | `evidence_refs` persist **on** the record, not into `uncertainty_log` (`metacognition.py:473-483`); `ExpertStance` and siblings carry the field |
| 3.5c | Typed-state revision | `revise_*` / `retire_*` beside the existing `promote_*`; today a duplicate title is silently refused (`metacognition.py:468-470`) and nothing can be corrected. Must land **before** the first insight is written |
| 3.5d | Tracker path fix | `MetaCognitionTracker._get_expert_dir` (`metacognition.py:188-192`) reimplements slugging instead of calling `canonical_expert_dir`, the exact split-directory bug `beliefs.py:432-437` documents |

**Depends on:** Step 3. **Blocks:** 4.1.

### Step 4 - Batch absorb and corpus attach

| ID | Work | Done when |
|---|---|---|
| 4.0a | `absorb-okf --trust-class` | A directory absorb path already exists (`expert_okf.py:185-274`) and passes no trust class, so every corpus through it caps at 0.60. Default `secondary` |
| 4.0b | **Corpus retention** | `corpus/index.jsonl` + `corpus/sources/<sha256>.md` written on every absorb, content-addressed and fleet-deduped, under `validate_path` containment. `expert corpus list` / `show <sha>` read it back at $0. This is prerequisite zero: without it a second study lens has nothing to read |
| 4.1 | `expert absorb-dir` | Batch secondary absorb of a Markdown corpus tree, with **publisher-collapsed origin identity** (see below), a run manifest for idempotent re-absorb on Distill's refresh cadence, per-origin chunking, and resume after partial failure |
| 4.2 | Doctor: distill on PATH | Advisory, `info` severity, `distill --version` only. Never shell out to `distill doctor`: it makes live provider network calls and would break `--skip-connectivity` |
| 4.3 | Quality attaches corpus origins | Distinct origins rise after absorb-dir, **and a regression test pins that a 40-file single-host tree counts as one origin** |

**Origin identity is the crux of 4.1.** Absorb records one provenance token per
belief (`expert_maintenance.py:268`, `report_absorber.py:526`), and two
downstream measures read it: `Belief._independent_source_count`
(`beliefs.py:139-158`), which lifts the tertiary ceiling from 0.60 to 0.80 at
two or more origins, and `build_quality_scorecard`'s `distinct_origin_count`
(`quality_scorecard.py:173-177`). Distill emits many files per source. A naive
per-file loop over a 40-page docs crawl would report 40 independent origins and
lift claims to the corroborated ceiling on one publisher's authority. Origin
keys must collapse to publisher through the existing `_canonical_url_source_key`
(`beliefs.py:27-48`), which already encodes exactly this rule. Getting it wrong
makes `expert quality` lie, which is worse than not shipping the feature.

**Depends on:** Step 3.5.

### Step 5 - Close Distillr / Learny instrument loops

Deepr cannot reserve against Distill's provider account, so "spend carefully" is
not an available posture. Only "prove it cannot spend, then prove it did not" is.

| ID | Work | Done when |
|---|---|---|
| 5.1 | Distill preflight verifier + `--print-command` | Pure $0 decision function: binary identity (no `.cmd` shim), version pin, `no-metered` in the adapter contract, env stripped of provider keys, cost-mode asserted twice (flag and env), subcommand allowlist that **denies `synthesize` and `research-brief`** (their own help names hosted metered models), argv-injection guard, output-path confinement, before/after `distill --json costs` zero-delta attestation. Recommendation: **do not ship Deepr-side invocation in Step 5** - emit the proven-safe command and let the operator run it. Invocation moves to Step 7 alongside Distill's own adapter proofs |
| 5.2 | Learny export absorb recipe | Documented; absorb-dir handles the tree with a provenance prefix. Deepr never invokes `learny`. Its export layout is unverified from this repo, so the recipe stays layout-agnostic |
| 5.3 | Specialist routes carry the verdict | Routes stay DEFERRED, but now with a verified-safe command and a spend detector rather than "figure it out yourself". CAPACITY.md gains a third-party-instrument section stating plainly that Deepr cannot see Distill's invoices |

**Verified on the validation host (distill 0.19.36):** `distill doctor
--adapters --json` reports `no_metered_ready: []`, with every CLI adapter
`no_metered_eligible: false` and `support_statement: planned`. Plan-quota CLIs
inside Distill are confirmed **not live**. Do not plan as if they are.

**Depends on:** Step 4.

### Step 6 - Spawn and stay-current

| ID | Work | Done when |
|---|---|---|
| 6.1 | `expert spawn` | idea -> council-plan -> make --local -> deepen-plan stubs. **Dry-run is the default**; `--apply` requires `-y` or interactive confirmation naming every expert to be created, is refused when the diversity gate fails, and is permitted only on the $0 local path. A run record is written before the first create so `--resume` can finish a partial run |
| 6.2 | Seed subscriptions | From council-plan roles and deepen queries, **not** from `expert plan` (which is metered-gated at `experts.py:456-459` and would put a metered dependency inside a $0 step). Seed `budget=0.0`, not the 0.50 default: five roles at 0.50 is $2.50 of latent metered intent per cycle for any `sync` without `--local` |
| 6.3 | Challenge consult mode | **Packet selection first, output schema second, prompt last.** Reserve packet slots for contradiction counterparts (the store already records `contested with N belief(s)` and never shows the counterpart claim, `council.py:298-300`), uncorroborated stance, corroborated evidence the confidence sort crowded out, and open gaps. Render belief ids. Compute `no_dissent_found` from the packet **before** dispatch, so a thin store reports thinness instead of being dressed up as adversarial review. Check cited ids for exact packet membership. The prompt never instructs the model to disagree |

**Depends on:** Steps 3-5.

**Why the packet comes first in 6.3:** a model told to be contrarian produces
theater. Grounded dissent already exists in the store as contradiction pairs,
retired claims, uncorroborated stance, and open gaps, and none of it reaches the
packet today. Note also that packet selection sorts by overlap then effective
confidence (`council.py:268-271`) while stance is uncapped at 1.00 and tertiary
domain evidence caps at 0.60/0.80 (`beliefs.py:118-137`), so absorbed project
intent structurally outranks corroborated evidence for the eight slots. Fixing
that ordering is part of the work, not a side effect.

### Step 7 - Capacity expansion (only after proofs)

| ID | Work | Done when |
|---|---|---|
| 7.1 | Additional Deepr plan adapters | Each clears doctor + overage-off + tool confinement + ledger |
| 7.2 | Distill plan adapters | Distill ships proof; Deepr documents interoperability |
| 7.3 | Shared membership capacity notes | Single place operators read what is free vs blocked |

**Depends on:** external proofs; do not block Steps 3-6 on this.

### Step 8 - Calibration and eval (quality meaning)

**This step was mis-scoped and its original done-condition is already met and
vacuous.** The harness is shipped (`src/deepr/experts/calibration.py`,
`deepr eval calibrate`), it ran on 2026-06-13, and `docs/CALIBRATION.md` records
a model and a date. That run produced **one populated bin** (n=59, grounded rate
98.3%) and an ECE of 0.002, which reads as "nearly perfectly calibrated" and
means nothing: a reliability diagram with one bin is not a reliability diagram.
The file then converts that null into a positive quality claim and a decision to
stop measuring. That sentence is the most misleading line in the docs tree.

Measured on the live fleet (38 experts, 1975 claims):

| Signal | Value |
|---|---|
| Claims at **exactly** 0.60 effective confidence | 1529 (77.4%) |
| Claims at exactly 1.00 | 191 (9.7%) |
| Raw extraction confidence >= 0.9 | 1799 (91.1%) |
| Raw extraction confidence < 0.7 | **1 claim** |
| Claims with 2+ independent origins | 68 (3.4%) |

The displayed number is `min(trust_ceiling, raw * exp(-0.01 * age_days))`. For
77% of the fleet it is the policy constant 0.60, carrying no information about
that specific claim. **More labels cannot fix this.** The predictor has no
variance, so any sample size reproduces a single bin.

| ID | Work | Done when |
|---|---|---|
| 8.1 | Resolution gate | The harness refuses to emit ECE, Platt parameters, or a derived threshold unless >= 3 bins each hold >= 30 samples, and reports `insufficient_resolution` with the reason instead. The current `n < 30` total warning is far too lenient |
| 8.2 | Rewrite `docs/CALIBRATION.md` | Separates the three things called calibration: C1 extraction faithfulness (measured, degenerate), C2 belief truth in the world (**no harness exists; this is what the operator is actually asking about**), C3 answer usefulness (pilot ran, all four arms tied at n=5). Retains the 2026-06-13 run as the canonical example of a **refused** result |
| 8.3 | Confidence UX honesty | Where effective confidence equals its trust ceiling, render the reason (`capped: single tertiary source`) rather than two decimals of false precision. Carry `confidence_calibrated: false` into MCP results and the consult packet, since agents are the readers most likely to over-read the number. Suppress `avg_confidence` until the distribution has variance |
| 8.4 | Third-party labels at $0 | Bridge the existing HaluBench adapter (`src/deepr/evals/benchmark_adapters.py`) to produce `(extractor_confidence, gold_label)` pairs. This is the only external label source available with metered dispatch frozen, and it needs an operator-supplied export |
| 8.5 | Fix the gameable metrics | `circularity_risk` is defeated by `git mv`: it substring-matches filenames (`quality_scorecard.py:18-25`) and is reported as a graded blocker. Source it from an `origin_role` recorded at absorb time instead. `verified_learning_loops` has no time window and `expert improve` hardcodes it to 0 in both before and after scorecards (`expert_quality.py:286,328`), so the improve loop is blind to its own effect |
| 8.6 | Anti-gaming tests | A bulk trust-class reclassify that adds no new origins improves confidence spread but must **not** improve the letter grade. Absorbing project intent as `--trust-class primary` must not improve the grade either - `expert improve` currently recommends exactly that (`expert_quality.py:355-357`), which deepens the echo chamber the scorecard exists to detect |

**Not in scope here, but named:** the root cause is single-pass self-rated
extraction confidence. Semantic entropy over N local extractions is the $0-at-margin
fix that would give the predictor variance worth measuring. Calibrating a
constant is not worth operator grading hours.

**Depends on:** multi-source corpora from Steps 4-5. 8.1 through 8.3 do not
depend on corpus and can land immediately; they are honesty fixes, not
measurements.

---

## Operator order of operations (runtime, not build)

When using the system on a real idea (example: NephMesh README review):

1. **Compose** diverse council
   `deepr expert council-plan --from-file README.md --local`
   (or paste goal text)
2. **Review** roster axes (must span more than "domain expert x N")
3. **Make** each expert
   `deepr expert make "..." --local -d "..."`
4. **Deepen** each (or critical subset first)
   `deepr expert deepen-plan "..." --query "..."`
   then Distill no-metered + absorb secondary
5. **Stance** (optional project intent)
   absorb intent as **primary** only on hybrid/stance roles
6. **Digest + quality**
   `digest` + `quality` until multi-source up, circularity down
7. **Consult** with explicit roster and a **challenge** question
   include diverse perspectives; ask what README/roadmap miss
8. **Improve**
   `improve` -> fill gaps -> re-deepen -> re-consult

Do not consult before step 4 if you need non-generic depth. Empty or
intent-only experts produce moderate, mushy synthesis.

---

## Non-goals

- Day-count or calendar estimates in this plan
- Reimplement Distill or Learny inside Deepr
- Auto-write beliefs from Distill/Learny without absorb
- Pretend plan CLIs are free without proofs
- Lexical maturity scores as gates (AGENTIC_BALANCE)
- Replacing one-shot consult with unbounded multi-turn debate without a
  separate design (see bounded deliberation)

---

## Current checkpoint

Revised 2026-08-05 after a code-grounded research pass. Several rows moved
because the previous checkpoint recorded intent rather than verified state.

| Step | Status |
|---|---|
| 0 Documentation | Done |
| 1 Trust / inventory / quality | Done, with corrections: no reclassify command exists; `absorb-okf` still has no `--trust-class`; the four new CLI commands (`quality`, `improve`, `deepen-plan`, `council-plan`) have **zero CLI tests**, and `expert improve` has no test of any kind |
| 2 Deepen-plan + wiki digest | Done |
| 3 Diverse council-plan | Done. Plan previously claimed "CLI smoke" under 3.5; that smoke test does not exist |
| **3.5 Ingestion-shape decision** | **Next, and blocking.** Absorb can only emit atomic facts. Decide this before 4.1 or every corpus ingested is permanently flattened |
| 4 Batch absorb / corpus attach | After 3.5. Origin identity is the crux |
| 5 Distill / Learny instrument close | After 4. Recommendation: verifier + printed command, no Deepr-side invocation |
| 6 Spawn + challenge mode | After 3-5. Challenge mode is a packet change first, a prompt change last |
| 7 Plan-quota expansion | Blocked on external proofs. Confirmed on the host that Distill's own plan adapters are not live |
| 8 Calibration / eval | Re-scoped. 8.1-8.3 are honesty fixes that can land now and do not depend on corpus |

### Why the ingestion-shape decision comes before Step 4

The previous checkpoint said the bottleneck was throughput: getting Markdown
trees into experts efficiently. That is true and still the immediate build.

But throughput alone does not produce what the operator is asking for. Absorb's
extraction prompt requires atomic single-fact claims and its only output type is
`Belief` (`report_absorber.py:930-955`, `:522-537`). A batch loop over that
produces a larger fact ledger, not an expert with stance, fail patterns, named
tensions, and open questions. Meanwhile the typed perspective state that would
hold those already exists in `core/contracts.py` and is completely inert: zero
production readers, zero populated across 39 experts, write-once, and its
`evidence_refs` are discarded on write.

So Step 4 is still next to *build*, but 3.5 is next to *decide*, because the
decision changes what 4.1 must emit. Design:
[../design/expert-insight-layer.md](../design/expert-insight-layer.md).

### Corrections to earlier "done" claims

Recorded so the checkpoint stays trustworthy:

| Claim | Reality |
|---|---|
| "reclassify path" closed | No such command. Re-absorb with `--trust-class` is the only route |
| Step 3.5 done via "CLI smoke" | No CLI test exists for `council-plan` |
| `expert improve` is a shipped $0 loop | It exists and registers, but has zero tests, re-enters the CLI through `CliRunner` in production, and its `--execute` path calls `discover-gaps`, which is metered-gated and takes no `--local` |
| Calibration harness unbuilt / unrun | Built, ran 2026-06-13, produced a degenerate single-bin result that the docs then read as evidence of quality |
