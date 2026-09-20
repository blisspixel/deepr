# Living expertise: research assessment, September 2026

Reviewed: 2026-09-20. Research and implementation assessment, not a shipped
feature declaration. This is a selected review of recent primary papers on
temporal memory, evolving understanding, and agent harnesses, with an older
autonomy taxonomy for terminology. It is not an exhaustive literature review.
The experiments below have not been reproduced in Deepr.

The active implementation sequence remains in
[the active release plan](../../ROADMAP.md#active-release-plan), with contracts
in the [delivery plan](../plans/living-expertise.md). The code assessment was
reconciled with current main on 2026-09-20, including prediction registration,
experience projection, and source-world preflight already added since August.
[Supported surface](../SUPPORTED_SURFACE.md) governs capability claims.

## Assessment

Deepr's architecture addresses several questions being investigated in current
research. It has retained sources, position history, evidence and perspective
graphs, research pursuits, bounded context, maintenance, and review artifacts.
It has not yet demonstrated the complete living-expertise loop or established
comparative performance against current research systems.

The next result to demonstrate is an expert that prepares for a consultation,
uses accumulated understanding, investigates a material change, revises or
defends its perspective, and gives useful guidance with traceable reasons.
Its experience should improve later inquiry. A larger memory, a generated wiki,
or an additional reflection pass does not establish that result.

## Papers and their limits

Dates are first submission dates. These are research reports; reported results
apply to their stated tasks and experimental settings.

| Primary source | Finding relevant to Deepr | Limit on the inference |
| --- | --- | --- |
| [A Graph-Native Bitemporal Memory Store for Conversational AI Agents](https://arxiv.org/abs/2607.26520), 2026-07-29 | Immutable identities and versioned content separate when something applied from when it was recorded. Historical retrieval also exposes a failure: retrieving similar versions and then filtering by time can leave too few eligible results. | Evaluation samples 60 LongMemEval questions and measures retrieval. It does not demonstrate expert reasoning, and the historical subset is small. It supports testing temporal selection, not a storage rewrite. |
| [AdaTKG: Adaptive Memory for Temporal Knowledge Graph Reasoning](https://arxiv.org/abs/2605.07121), 2026-05-08 | Entity representations accumulate observed interactions through adaptive memory, including for newly encountered entities. | Its task is temporal link prediction. Learned entity-vector updates do not establish evidence-grounded belief revision or useful consultation. Retain this as a research reference; there is no demonstrated need to add its learned updater to Deepr. |
| [Harness-1: Reinforcement Learning for Search Agents with State-Externalizing Harnesses](https://arxiv.org/abs/2606.02373), 2026-06-01 | Search works over explicit candidates, curated evidence, verification records, and bounded working memory. The environment preserves state while the model chooses research actions. | Results combine a trained policy and its harness. Component ablations show uneven effects. A generic model wrapped in the same bookkeeping is not guaranteed the reported gains. |
| [Risk-Constrained Freshness-Aware Semantic Caching for Open-Web Retrieval-Augmented LLMs](https://arxiv.org/abs/2607.04281), 2026-07-05 | FreshCache treats reuse as a freshness-risk decision across answer, URL, and content caches. It distinguishes changed content from changes that affect an answer. | Snapshot windows, query repetition, and judged changes constrain the results. Its reported savings and stale rates are not guarantees for new domains or Deepr's preparation packets. |
| [EvoSCM: Scientific Belief Revision Through Causal Model Evolution and Experimentation](https://arxiv.org/abs/2609.01526), 2026-09-01 | Explicit competing explanations, predictions, and discriminating experiments let new evidence revise a model of how something works. | The submission is preliminary and studies controlled physics environments. It does not show that causal models can be reliably inferred from arbitrary web research. |
| [HarnessEvolve: Learning from Reference Trajectories for Reliable Agent Self-Evolution](https://arxiv.org/abs/2609.00829), 2026-09-01 | Separates execution, evaluation, proposed changes, and acceptance. Uses reference trajectories, checks for shortcuts, and tests candidate updates against recent cases and validation data. | Reference generation uses known answers, and judgment still depends on evaluators. Open research rarely supplies comparable ground truth. A plausible successful trace does not prove the cause of a failure. |
| [One Recipe, Many Harnesses: What Self-Evolution Encodes Across Languages and Models](https://arxiv.org/abs/2608.10178), 2026-08-10 | Evaluates harness evolution across eight programming languages and three models. Improvements depend on the execution defects of each setting; some settings show no benefit. | The authors interpret detectable gains primarily as compensation for execution defects. Coding-task results do not establish stronger research understanding or universal transfer between models. |
| [Levels of Autonomy for AI Agents](https://arxiv.org/abs/2506.12469), 2025-06-14 | Defines levels by the human's role. Its Level 5 places the human in an observer role with emergency intervention. | This is an autonomy framework, not an intelligence score or a test of continuous learning. It is different from Deepr's internal Level 5 and Level 6 definitions. |

## Where Deepr stands

This assessment follows the documented executable paths and inspected code;
it does not infer a working product loop from module names.

| Area | Existing foundation | Remaining gap |
| --- | --- | --- |
| Preparation and currency | [Fresh-context maintenance](local-fresh-context.md) retrieves bounded source packs. [Consult context](../../src/deepr/experts/consult_context.py) assembles orientation, positions, findings, and source passages. | Normal consultation does not yet own the default preparation workflow. Reuse needs question, environment, version, and coverage validation. |
| Temporal understanding | [Position ledger](../../src/deepr/experts/position_ledger.py) preserves revisions and provides historical position reads. [Identity and time](expert-v2-identity-and-time.md) defines record-time snapshots and sparse validity metadata. | Findings still rebuild into the latest study. Full historical expert reads and time-aware selection throughout consultation remain unfinished. The consult assembler currently ranks supplied positions by token overlap. |
| Perspective and experience | [Perspective graph](../../src/deepr/experts/perspective_graph.py) connects standpoints, encounters, shifts, commitments, and pursuits. [Research practice](../../src/deepr/experts/research_practice.py) maintains pursuits, watches, and interests. | Preserve and reuse synthesized understanding across repeated study, then show better explanations, insights, and decisions on new questions. The graph records a viewpoint's development; its existence is not evidence of its quality. |
| Improving how the expert learns | Traces, quality reviews, and [self-model update records](../../src/deepr/experts/self_model_updates.py) support reviewed proposals and outcome references. | Accepted updates remain read-only guidance. Measured research-strategy effects and validated harness changes are outstanding. |
| Predictions and experience | Prospective criteria and dates are preserved in position versions. The read-only experience view joins positions, consult traces, and operator-attested outcomes. | Reviewed resolution and useful strategy changes remain unproven. Registration and joining records are existing foundations, not new implementation tasks. |
| Evidence of value | [Expert-value protocol](expert-purpose-and-value-loop.md) defines four comparison arms and aggregates a bound review workbook. | That evaluator does not execute the four arms. Trials and calibrated review still have to establish benefit, regressions, cost, and transfer. |

## Changes to prioritize

The following are Deepr-specific design inferences from the research and code
review. They are planned experiments, not claims that the papers validate Deepr.
The numbered mechanisms below are research priorities; S0-S5 in the active
roadmap governs delivery. Preserve the existing baseline before comparative
claims, and isolate preparation effects from the contribution of memory.

1. **Make preparation part of consultation.** Extend existing acquisition and
   study components with a bounded work record: the question, target setting,
   assumptions to check, consulted sources, unresolved checks, and stop reason.
   The model decides which inquiry matters; code enforces access, capacity,
   time, context, and write limits. Preserve enough evidence for the answer and
   subsequent learning without carrying the whole search transcript. Validate
   reused packets against the new question. Measure missed answer-changing
   developments as well as unnecessary refreshes and latency. A page hash or
   age threshold alone cannot decide whether guidance remains sound.

2. **Complete temporal retrieval and revision.** Preserve findings with stable
   lineage, then carry record-time and applicability constraints through
   selection of positions, findings, and supporting passages. Distinguish
   "what the expert knew then" from "what it now knows about that period."
   Publication, observation, substantive review, and validity dates have
   different meanings; unknown validity must stay unknown. Evaluate whether
   temporal filtering and result caps discard the relevant version. A recent
   source does not automatically override an older one or apply to a caller's
   pinned software environment. Reuse existing stores and temporal primitives.

3. **Let reflection determine the next useful investigation.** Connect
   competing explanations to their support, counterevidence, and the observation
   that could distinguish them. Use the existing pursuit and falsifier records
   to propose the next bounded inquiry. For example, an expert may need to
   determine whether a changed recommendation follows from a runtime change,
   library behavior, or a difference in workload. A controlled comparison may
   help when available; otherwise keep the uncertainty explicit. Preserve the
   resulting conceptual understanding and its reasoning in canonical state;
   regenerate the wiki from it. Similarity edges alone do not establish causes.

4. **Prove accumulated expertise through repeated use.** Run the existing
   four-arm protocol across initial evidence, a correction, and incomplete or
   distracting later material. Add preparation enabled/disabled at the same
   expert revision and declared resources. Test explanation, transfer, sound
   retention, changed guidance, and insight as well as answer correctness.
   Freeze development and held-out cases separately. Structural verification
   and a judge's agreement are not substitutes for calibrated review.

5. **Then improve the research strategy and harness.** Begin with shadow
   proposals tied to concrete failure traces and a predicted measurable effect.
   Test each change against both the failure and retained capabilities. Keep
   independent evaluation, model and harness version records, context growth
   limits, rollback, and checks for embedded benchmark answers. Preserve cases
   with no benefit or negative transfer. A model change requires revalidation.
   Evidence-backed changes to learning policy come after these results;
   telemetry and accepted advice cannot silently change that policy.

These additions preserve the existing
[agentic balance](../plans/AGENTIC_BALANCE.md): semantic judgment proposes
interpretation and research direction; deterministic controls enforce structure
and side effects. The initial experiments use admitted owned-local capacity and
permitted retrieval, with no paid fallback. All production plan adapters are
currently blocked. Attended one-shot paid research is a separate surface.

## Prepared-consultation acceptance cases

For the S1 preparation comparison, use one Python expert and frozen source
snapshots. This does not replace S0's selected expert or arm policies. Record
the target runtime and dependency versions in each consultation, without assuming that newest is
the correct deployment choice.

| Case | Required observation |
| --- | --- |
| A relevant release or advisory appears after the expert's last study | Default preparation finds it and explains its effect on the answer. |
| A release does not apply to the caller's pinned environment | The expert retains applicable guidance and explains the scope difference. |
| Later evidence corrects an earlier conclusion | The new answer changes with a preserved chain of evidence and revisions. |
| Evidence arrives late about an earlier period | A historical knowledge snapshot excludes information not yet recorded; a present-day retrospective can include it. |
| An unchanged foundational explanation remains relevant | Newer distractors do not displace sound understanding. |
| Two explanations remain plausible | The expert proposes a discriminating check and retains uncertainty. |
| Retrieval fails or the packet only covers part of the question | The answer exposes the unchecked dependency and cannot claim full currency. |
| A follow-up asks a new question that uses earlier reasoning | The expert transfers the relevant understanding, with supporting work and limits. |

These are prospective acceptance cases. No score, benefit, or currentness claim
is awarded until the runs and reviews exist. Frozen-world results must also be
distinguished from later prospective outcomes in the live field.

## Maturity language

[Deepr's Level 5 and Level 6](level-5-6-expert-maturity.md) are internal product
targets: bounded improvement of an expert, then governed improvement of its
harness. Describe the gates actually passed. Do not infer autonomy,
intelligence, or state-of-the-art performance from the label.

The immediate milestone is demonstrated current, cumulative expertise in one
supported consultation flow. Wider autonomous operation follows evidence that
the loop improves guidance and preserves useful understanding.
