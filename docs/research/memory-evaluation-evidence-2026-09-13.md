# Memory and longitudinal evaluation evidence

Research checked: September 13, 2026. Scope: the v2.51 four-arm pilot,
persistent expert value, temporal degradation, transfer, and review validity.
This is a research note, not a pilot result or execution authorization. No
model, embedding, or paid API evaluation was run.

The next valuable result is evidence that a maintained expert improves a
recurring decision, including the work needed to maintain it. The
[README](../../README.md#direction),
[active release plan](../../ROADMAP.md#active-release-plan), and
[pilot protocol](../design/expert-purpose-and-value-loop.md#v251-pilot-protocol)
already identify the right dependency. Current research strengthens that
choice. It also argues for explicit temporal and reviewer failure cases before
trusting a favorable mean. It does not establish that Deepr's existing memory
representation helps.

## Evidence that changes the next experiment

Memory success is task dependent. Memora's full results show substantial
improvements in remembering for some memory systems, while reasoning remains
difficult and longer, more mutation-heavy histories often degrade performance.
The abstract's description of marginal improvement should not be read as a
universal finding that memory is useless. Deepr should expose recall,
decision correctness, and invalidated-memory reuse separately.
[Memora, sections 5.2-5.3](https://arxiv.org/html/2604.20006v1).

Recall benchmarks cannot substitute for repeated decisions. MemoryArena couples
earlier actions and feedback to later tasks and finds that strong long-context
memory scores do not ensure success there. LongMemEval-V2 adds dynamic state,
workflow knowledge, environment gotchas, and false premises, but evaluates
context gathering for questions in customized web environments. These are
useful case-design references, not evidence of expert judgment in Deepr's
target domains.
[MemoryArena](https://arxiv.org/abs/2602.16313),
[LongMemEval-V2](https://arxiv.org/abs/2605.12493).

Two recent studies add specific failure probes. Repeated compression can lose
constraints, and changing the model that reads or writes memory can change
performance asymmetrically. Preserve original evidence and record the complete
writer, reader, embedding, and context configuration. Diagnose whether an
answer failed because evidence was never stored, not retrieved, not delivered,
or misread before deciding to replace the model or memory architecture.
[Compaction Cliff](https://arxiv.org/abs/2608.22752),
[memory portability study](https://arxiv.org/abs/2609.05339).

Blinding and a rubric are necessary controls, not proof that the judge measures
the intended property. Recent rubric probes identify answer-independent
predictive signals and failures to change verdicts after counterfactual
changes. Separate work shows that calibration differences can reverse a model
comparison. The pilot should anchor semantic judgments to human review and
inspect disagreement by failure type.
[Rubric artifacts](https://arxiv.org/abs/2609.02942),
[judge bias and uncertainty](https://arxiv.org/abs/2605.06939).

## Recommended pilot clarifications

These are methodological recommendations for operator review, not new runtime
rules, semantic classifiers, or changes to the accepted protocol.

1. **Carry the existing arm policy into the value report.** The
   [local rehearsal policy](../design/local-four-arm-rehearsal.md) already
   defines fresh per-case study, cumulative raw history, a compiled checkpoint
   frozen at world 1, and a maintained copy updated before worlds 2 and 3.
   Every final answer receives the same complete current-world sources. Keep
   that distinction explicit: maintained versus compiled measures the effect
   of updating inherited state while current evidence is also available to
   both. It does not compare incremental maintenance against independently
   rebuilding the expert at every world. Full source packets also mean this
   small experiment cannot establish retrieval scalability.

2. **Resolve the model baseline explicitly.** The general longitudinal design
   mentions fresh frontier research; the v2.51 pilot requires the same model
   across arms. A same-model local pilot estimates the contribution of state
   under that local model. It cannot establish superiority over frontier deep
   research. Preserve the rehearsal's frozen model, effective context,
   generation settings, source access, retry policy, and resource ceilings,
   and describe the claim at that scope. Equal ceilings are not equal compute:
   preprocessing differs by treatment and needs separate accounting. Current
   paid-dispatch restrictions remain in force.

3. **Freeze the estimands and stopping rule before answers.** Primary contrasts
   should be maintained versus fresh and maintained versus frozen compiled
   state, reported separately for decision correctness, stale reuse,
   false support, completion, and human effort. Predeclare what practical
   benefit would justify a larger study and what harm would prevent expansion.
   Do not choose the favorable contrast after review. The 12-case, 48-cell
   pilot ends after its declared cells and review are complete, not when a
   desirable result appears.

4. **Make blinding testable without rewriting answers.** Hide arm names, model
   labels, local paths, and run metadata in review packets. Preserve raw answer
   bytes and bind any neutral display wrapper separately. Randomize packet
   order with a saved assignment key and keep the key unavailable until labels
   freeze. Ask reviewers to record whether they inferred an arm and why.
   Stylistic cues can defeat opaque identifiers; this is a limitation to
   report, not a reason to paraphrase responses after seeing them.

5. **Use a separate calibration set.** Before pilot review, use examples with
   decisive support, a relevant but non-supporting citation, a reversed claim,
   and correct abstention. A reviewer must respond to the evidential change,
   not just the rubric wording. For this small pilot, direct human review of
   every answer is preferable to making a model judge the unvalidated scoring
   authority. Independently double-review the same prespecified subset across
   all arms, report disagreements, and preserve adjudication history. Any
   model-assisted label remains a draft until the accepted review process.

6. **Distinguish independent evidence from repeated measurements.** Forty-eight
   cells are four measurements of 12 cases in three source worlds, not 48
   independent decisions. Related cases share source evidence and expert
   state. Report per-case paired deltas and per-world trajectories; explain
   that the existing case-bootstrap intervals do not establish uncertainty
   across domains or independent expert histories. Three worlds are too few
   to make a cluster analysis persuasive. Repeated seeds help measure runtime
   variation, but do not create new independent domain cases.

7. **Preserve the complete denominator and cost boundary.** Count failed
   updates, timeouts, empty answers, and exhausted local capacity. Record
   construction, maintenance, consultation, and reviewer minutes separately.
   Zero marginal API dollars does not mean zero human effort, energy, or
   hardware cost. If all arms have zero recorded API cost, a dollar break-even
   result cannot establish economic advantage; use measured effort and latency
   and label any monetization assumptions explicitly.

8. **Protect the held-out loop.** Development fixtures may reveal structural
   bugs. Review labels and future-world evidence must stay out of earlier arm
   state, prompts, and maintenance decisions. Fix discovered defects and
   rerun development checks, but a pilot used for tuning becomes development
   evidence. A fresh held-out replication is required before a learning-policy
   or routing-default change. Real downstream outcomes remain separate from
   simulated answer quality.

## Falsification and follow-up

| Observation | What it means | Next action |
| --- | --- | --- |
| Maintained state adds no useful paired correctness or effort benefit | This configuration has not supported the product claim | Inspect failure traces and simplify or repair the measured bottleneck; do not expand autonomy on that result |
| Benefit vanishes when fresh and compiled arms receive the same evidence and resource ceiling | Evidence access or extra computation may explain the apparent gain | Repair the comparison and run a new held-out study |
| Stale reuse, false support, or loss of previously correct knowledge increases | Maintenance may be harmful even when another metric improves | Keep defaults unchanged; inspect source retention, invalidation, context assembly, and reading separately |
| Answers are polished but reviewers disagree on factual support | The measurement is not yet reliable enough | Improve the independent rubric calibration and adjudicate without revealing arm identity |
| Source bytes, assignment bindings, model state, or chronology cannot be reconstructed | The experiment is invalid, regardless of its scores | Repair structural preparation before interpreting a value result |
| The first pilot looks favorable | There is a reason to replicate, not a general superiority result | Test a new held-out history and later a second domain; model migration is a separate intervention |

Operational success and a scientifically favorable result are different. A
well-run negative pilot can satisfy the need for usable evidence and redirect
the roadmap. It must not be relabeled as product improvement. No combined
score should override a harmful stale-memory or false-support finding.

## Primary source register

Dates below are publication or version dates shown by the primary source,
checked on September 13, 2026. Repository and project pages were inspected as
read-only supporting material; their evaluation programs were not executed.

| Source and version | Useful evidence | Applicability limits |
| --- | --- | --- |
| [LongMemEval](https://arxiv.org/abs/2410.10813v2), v1 October 14, 2024; v2 March 4, 2025; ICLR 2025 | Separates extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention; distinguishes indexing, retrieval, and reading | Primarily chat-history question answering, not longitudinal decision utility; included as a foundational control taxonomy rather than the newest result |
| [MemoryArena](https://arxiv.org/abs/2602.16313v1), February 18, 2026; [original project](https://memoryarena.github.io/) | Evaluates interdependent sessions where earlier experience must support later action; external memory is not uniformly beneficial | Human-crafted benchmark environments and specific agent implementations; published success rates do not measure Deepr |
| [Memora](https://arxiv.org/abs/2604.20006v1), April 21, 2026; accepted ACL 2026 Findings per arXiv; [original repository](https://github.com/geniesinc/Memora) | Repeated updates and invalidations across weekly, monthly, and quarterly histories; scores both required memory and obsolete memory misuse | Generated persona conversations and model-based criterion judgments; its combined FAMA score should not replace Deepr's separate harm measures |
| [LongMemEval-V2](https://arxiv.org/abs/2605.12493v1), May 12, 2026; [original project](https://xiaowu0162.github.io/longmemeval-v2/) | Environment experience, dynamic state, premise awareness, and accuracy-latency tradeoffs | Marked work in progress; compact context gathering for web-agent questions, not proof of real downstream outcomes |
| [Bias and Uncertainty in LLM-as-a-Judge Estimation](https://arxiv.org/abs/2605.06939v1), May 7, 2026 | Analytical and simulated calibration failure, with an MMLU-Pro sign-reversal case; motivates checking calibration across compared conditions | Does not estimate Deepr judge error; small pilot human review is more defensible than importing a correction estimator without calibration data |
| [The Compaction Cliff in Long-Running AI Agent Memory](https://arxiv.org/abs/2608.22752v1), August 24, 2026; CIKM 2026 reference; [original implementation](https://github.com/searchsim-org/cikm26-knowledge-triage) | Tests repeated compression and preservation of operational constraints; motivates checking fidelity after maintenance or context compaction | Guarantees require accurate classification and a feasible budget. Public configuration corpora and tested workflows do not establish semantic correctness of expert beliefs; no lexical verdict policy should be imported |
| [Judging LLM-as-a-Judge: Concerning Rubric Artifacts](https://arxiv.org/abs/2609.02942v1), August 31, 2026; accepted EMNLP 2026 per arXiv | Rubric-only prediction and counterfactual response/criterion tests motivate reviewing whether labels follow evidence | Main judge is Qwen2.5-7B-Instruct on HealthBench and ResearchRubrics; probes do not establish a universal failure rate or the complete causal mechanism |
| [Does Your Agent's Memory Survive a Model Upgrade?](https://arxiv.org/abs/2609.05339v1), September 4, 2026; under review | Separates writer, reader, embeddings, and repair; exposes direction-specific failures and the value of retaining original source history | Forty-eight synthetic histories and two similarly sized models under 10B parameters; fixed-schema graph success is workload-specific. The signed study plan is described as an internal analysis lock, not full preregistration |

The newer papers support targeted failure probes and careful attribution. They
do not justify adding a new memory subsystem before the current four-arm pilot
produces interpretable evidence. The immediate implementation work remains the
already planned equal source inventory preparation and answer-to-review
assignment binding, building on the existing nested-source preflight.
