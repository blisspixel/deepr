# Semantic Recall Evidence Contract

Status: accepted for implementation
Date: 2026-07-09
Scope: local recall evaluation and explicit sync preference evidence

## Context

Deepr compares a lexical candidate router with indexed vector recall over operator-labeled cases. The comparison is routing evidence only. It does not decide whether a belief is true, supported, contradictory, current, or useful.

The first report contract allowed vector preference evidence after three cases when vector retrieval won hit@k and mean reciprocal rank and the requested vector index was complete. That gate was useful for wiring the end-to-end path, but it is not strong enough for operator validation. Three cases can produce an unstable point estimate, hit@k ignores additional relevant results after the first hit, and MRR considers only the first relevant rank.

The runtime currently has no accumulated recall libraries. Tightening the contract now therefore has no known local production migration cost.

## Decision

### Retrieval metrics

Each route reports these deterministic metrics against operator-supplied binary relevance labels:

- hit@k: whether at least one relevant belief appears in the first `k` results
- reciprocal rank: inverse rank of the first relevant belief
- precision@k: distinct relevant results divided by `k`
- recall@k: distinct relevant results divided by the number of labeled relevant beliefs
- average precision@k: precision at each newly retrieved relevant rank, divided by `min(relevant_total, k)`
- NDCG@k: binary discounted cumulative gain divided by the ideal gain for `min(relevant_total, k)` results

Duplicate candidate ids count at most once as relevant. Missing result positions remain non-relevant for precision@k. The report retains mean relevant results per case as a descriptive compatibility metric.

### Paired uncertainty

The evaluator compares lexical and vector results for the same cases. It uses a deterministic paired percentile bootstrap:

- 9,999 resamples
- 95 percent two-sided confidence intervals
- case-pair resampling with replacement
- one input-derived seed recorded in the report
- the explicit NumPy PCG64 bit generator, evaluated in bounded-memory chunks
- mean vector-minus-lexical difference for each route metric

Identical case results produce identical intervals. The report records both the method and bit generator. The method is deliberately labeled `paired_percentile_bootstrap`; it is not presented as BCa, a significance test, or proof that the case library represents future traffic.

### Preference eligibility

An explicit vector preference is eligible only when all of these conditions hold:

1. Both routes were evaluated on at least 30 paired cases.
2. Every belief vector is current for the requested embedding-model label.
3. Vector point estimates beat lexical point estimates on hit@k, mean reciprocal rank, mean recall@k, and mean NDCG@k.
4. For each required metric, the 95 percent paired bootstrap lower bound for the mean vector-minus-lexical difference is greater than zero.
5. The report carries the read-only, routing-evidence-only contract.

The 30-case minimum is a conservative operating floor, not a statistical sufficiency claim. Case representativeness, label quality, query diversity, and temporal drift remain operator responsibilities and need separate validation workflow support.

Eligible reports bind the requested embedding model to a SHA-256 digest of the current belief ids, claim hashes, domains, and usable vector values. They also bind the evaluated `top_k`, expert-domain filter, and minimum score. Explicit sync recomputes the digest from live local state and rejects a report after any retrieval-relevant belief or vector drift.
The source-pack recall path repeats the digest check immediately before using the preference. If state changes after CLI validation, vector preference fails closed to ordinary lexical-fallback routing.
It also requires the live recall request to match the evaluated retrieval parameters exactly, so evidence measured globally or at another cutoff cannot activate a different runtime route.

### Versioning and migration

The strengthened report is `deepr-recall-eval-report-v2`. A v1 report cannot establish the new eligibility conditions and is rejected at the explicit sync boundary with guidance to rerun the local `$0` eval. Report v2 additions are deterministic and do not require provider calls.

The scheduler default remains lexical-first. An eligible report can be used only when an operator explicitly supplies it to compiled sync for the same expert and embedding model. Vector failure or an empty vector result still falls back to lexical recall.

## Deterministic and agentic boundary

Deterministic code owns input shape, rank calculations, paired resampling, confidence bounds, thresholds, vector-index completeness, report consistency, and the explicit sync boundary. A human or calibrated model owns the meaning of relevance labels. Lexical overlap may route candidates but cannot create labels or decide semantic correctness.

## Alternatives rejected

- Keep the three-case gate: too unstable for preference evidence.
- Increase the case count but keep point estimates: sample count alone does not express uncertainty.
- Add SciPy as a runtime dependency: unnecessary for a small deterministic paired percentile bootstrap and would widen the installation surface.
- Use a model judge for ranking metrics: this would put deterministic measurement behind a paid or nondeterministic semantic call.
- Change default routing from an eligible report: this would overstate what a finite labeled case library proves.

## Consequences

- Existing v1 reports must be regenerated before explicit preference use.
- Strong vector improvements may remain ineligible until the case library reaches the operating floor and its paired intervals clear zero.
- Operators get more informative failure reasons and standard retrieval metrics.
- Case-library quality and representativeness become the next explicit workflow problem after this contract is enforced.

## Current external guidance

- Sentence Transformers `InformationRetrievalEvaluator` reports MRR, NDCG, accuracy, precision, recall, and MAP at configurable cutoffs. Official documentation accessed 2026-07-09: https://www.sbert.net/docs/package_reference/sentence_transformer/evaluation.html#sentence_transformers.evaluation.InformationRetrievalEvaluator
- MTEB evaluates embedding retrieval across datasets, tasks, languages, and domains, reinforcing that one small query set is not general capability evidence. Official repository accessed 2026-07-09: https://github.com/embeddings-benchmark/mteb
- SciPy 1.17 documents paired bootstrap confidence intervals, reproducible random-generator control, confidence levels, and explicit resample counts. Official documentation accessed 2026-07-09: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html

## Acceptance criteria

- Formula-level tests cover multiple relevant labels, missing hits, duplicate candidates, and rank discounting.
- Determinism tests prove identical paired inputs yield identical bootstrap evidence.
- Weak, tied, incomplete-index, too-small, and statistically inconclusive comparisons remain ineligible.
- A sufficiently large, consistently superior paired comparison becomes eligible.
- The explicit sync boundary rejects v1, missing, inconsistent, or non-superior confidence evidence before loading expert state.
- No provider call, graph write, belief write, vector write, or default routing change is introduced.
