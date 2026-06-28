# Evidence Correlation And Hypothesis Memory

Status: design note

This note records how Deepr should adapt correlation math from security-style
evidence engines into expert memory. The useful part is not the security domain.
The useful part is disciplined handling of evidence dependence, time, uncertainty,
hypotheses, and graph structure.

Reference input: <https://github.com/blisspixel/recon/blob/main/docs/correlation.md>

## Decision

Use correlation math as routing, calibration, and prioritization machinery. Do
not use it as a semantic truth verdict.

Deepr experts are not fact books. An expert is a maintained perspective over a
domain: current beliefs, concepts, hypotheses, stance, original ideas, gaps,
contradictions, freshness watchlists, exploration agenda, and known uncertainty. Mathematical
correlation should help decide what to inspect, what to ask a model to judge,
what to refresh, what to cluster, and what to explain. It must not decide what a
claim means or whether it is true.

This follows the agentic-balance boundary:

- Deterministic code owns schemas, provenance, budgets, ranges, write gates,
  source-family accounting, artifact validity, and cost ceilings.
- Model judgment owns meaning: contradiction, grounding, conceptual fit,
  novelty, stance quality, original-idea quality, and whether a hypothesis is useful.
- Correlation scores may route into model judgment. They may not replace it.

## Useful Math

### Evidence graph

Represent observations, sources, claims, concepts, hypotheses, original ideas,
gaps, and stance items as graph nodes. Use typed edges such as `supports`, `contradicts`,
`derived_from`, `enables`, `same_as`, `co_occurs_with`, and `updates`.

Fit for Deepr:

- The temporal knowledge graph already has typed belief edges.
- The corpus-to-expert compiler can emit candidate source-note, claim, concept,
  hypothesis, stance, original-idea, and gap nodes before one verified commit.
- `why`, `what_changed`, and `contested` become richer when they can traverse
  source roots, support chains, contradiction clusters, and hypothesis lineage.

### Temporal weighting

Use recency as a prioritization feature:

```text
temporal_weight = exp(-abs(delta_time) / tau)
```

Useful for:

- freshness watchlists
- stale central concepts
- sync priority
- "what changed" summarization
- contradiction rechecks after new source packs

Temporal weight should not mean "newer is true." It means "this deserves
attention because time changed the evidence posture."

### Evidence dependence and effective source count

Multiple citations are not automatically independent. A press release repeated
by ten sites, a copied report, or model output derived from the same source
family should count as one evidence family for confidence lifting.

Deepr already avoids counting quote excerpts as independent sources. The next
step is explicit source-family accounting:

```text
effective_evidence_count <= raw_evidence_count
```

Useful fields:

- source URL host and canonical URL
- source pack id
- retrieval run id
- report id
- first-party vs secondary vs tertiary trust class
- extractor model and prompt version
- content hash
- quoted window hash
- syndicated or copied-origin marker when available

Confidence ceilings should depend on effective independent families, not raw
citation count.

### Hypothesis updates

For hypotheses, not atomic facts, log-odds updates are a useful internal model:

```text
logit(posterior) = logit(prior) + sum(lambda_i * signed_strength_i)
```

Use this only when:

- evidence families are tracked
- source dependence correction is applied
- trust ceilings still cap final confidence
- the update is explainable as a trajectory
- contradiction and grounding remain model-judged

Hypotheses are allowed to be provisional. They should carry uncertainty,
counterevidence, expected observations, and "what would change my mind" notes.

### Uncertainty mass

Keep unknown separate from true and false. A useful expert can say:

- I believe this.
- I doubt this.
- I do not know.
- I used to believe this, but the evidence posture changed.
- The field may have moved and I have not refreshed enough to know.

This is a better fit than forcing every state into a single confidence number.
It directly supports Deepr's unknown-wrongness principle: stale knowledge is
dangerous because the expert may not know which part is now wrong.

### Mutual information, clustering, and centrality

Use graph statistics to choose attention targets:

- concept clusters for generated wiki pages
- contradiction hotspots
- high-centrality stale beliefs
- weakly connected gaps
- cross-expert overlap for council routing
- low-coverage areas that deserve exploration

Do not use centrality as confidence. Popular, repeated, or highly connected
claims can still be wrong.

### Expected-value priority

Adapt expected-loss scoring into a refresh priority:

```text
priority = decision_impact * uncertainty * freshness_risk * usage_salience / cost
```

This helps schedule bounded expert maintenance. It is especially useful for
local or plan-quota loops where time is cheap but attention still needs ranking.

## What Not To Import

Do not import security-specific attack-path assumptions into Deepr's general
expert memory.

Do not turn lexical overlap, Jaccard similarity, PageRank, centrality, or a
weighted score into a final verdict on meaning.

Do not let Noisy-OR or Bayesian accumulation lift confidence unless source
dependence is modeled. Without dependence correction, repeated derivatives of
one source create false certainty.

Do not make the expert a static fact ledger. A mature expert needs current
concepts, hypotheses, stance, dissent, exploration plans, and learning behavior.

## Implementation Order

1. Add an `EvidenceFamily` or `SourceCluster` primitive.
   - Group evidence by canonical origin, source pack, content hash, report id,
     model/prompt version, and trust class.
   - Expose effective independent source count.
   - Keep this deterministic and `$0`.

2. Add correlation features to the source-pack compiler.
   - Temporal proximity.
   - Source-family overlap.
   - Entity and concept overlap as routing signals.
   - Candidate support, contradiction, same-as, and update edges.
   - No semantic conclusions at this stage.

3. Add first-class hypothesis and perspective candidates.
   - Hypothesis text.
   - Prior, current posterior, uncertainty mass, evidence families, expected
     observations, counterevidence, and "what would change my mind."
   - Stance and exploration agenda records separate from atomic beliefs.

4. Verify before graph writes.
   - Candidate edges route to calibrated model judgment where meaning matters.
   - One commit envelope writes accepted claims, hypotheses, edges, gaps, and
     generated-view invalidation together.
   - Rejected or uncertain candidates remain reviewable artifacts, not canon.

5. Evaluate locally before trusting automation.
   - Source-dependence regression tests.
   - Contradiction-candidate recall tests.
   - Confidence calibration checks.
   - Freshness-priority tests.
   - Consult-trace eval cases for bad or low-context answers.

## Agent-Consult Implication

When another agent chats with Deepr experts, it should ask for the expert's
perspective, not just facts. Good prompts ask:

- What do you currently believe?
- What changed recently?
- What is contested?
- What are the strongest reasons and counter-reasons?
- Which parts might be stale or unknown-wrong?
- What would change your mind?
- What should be explored next?

That is the difference between asking a retrieval system for documents and
asking a Deepr expert for a maintained, inspectable, evolving perspective.
