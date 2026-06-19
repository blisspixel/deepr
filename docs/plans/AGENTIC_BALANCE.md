# Agentic balance: workflow vs agent (what deepr hardcodes vs what it lets the model decide)

Status: design principle, 2026-06-13. Cross-cutting; governs how every deepr
surface splits work between deterministic code and model judgment. Grounded in a
cited, adversarially verified literature pass (June 2026). The checks-specific
instance of this principle is
[checks-deterministic-vs-agentic.md](../design/checks-deterministic-vs-agentic.md);
this doc is the general axis it sits under.

**Living doc - keep it current.** This is the reference the roadmap points every
rule-vs-agentic decision at, so it is only useful if it stays accurate. When you
add a surface, change where a determinism boundary sits, or learn something new
about what does or does not belong in a rule, update the surfaces table and the
invariants below in the same change. A stale agentic-balance doc is itself a
brittle rule - it encodes a boundary that no longer matches the code.

## The axis

Anthropic draws the load-bearing distinction. A **workflow** is a system "where
LLMs and tools are orchestrated through predefined code paths." An **agent** is a
system "where LLMs dynamically direct their own processes and tool usage,
maintaining control over how they accomplish tasks." The decision criterion,
verbatim: "workflows offer predictability and consistency for well-defined
tasks, whereas agents are the better option when flexibility and model-driven
decision-making are needed at scale." Their default is to "find the simplest
solution possible, and only increas[e] complexity when needed."
(Anthropic, *Building Effective Agents*, Dec 2024.)

This is not a binary. smolagents frames agency as "a continuous spectrum, as you
give more or less power to the LLM on your workflow" - from "LLM output has no
impact on program flow" through "LLM output controls iteration and program
continuation." Several 2024-2026 taxonomies make the same point as discrete
*levels* you select deliberately:

- NVIDIA: L0 single inference call, L1 deterministic fixed-order pipeline, L2
  weakly autonomous (model decides at fixed decision points), L3 fully
  autonomous (model freely revises its own plan).
- DeepMind *Levels of AGI*: autonomy (AI as Tool / Consultant / Collaborator /
  Expert / Agent) is decoupled from capability - "Increasing capabilities
  unlock new interaction paradigms, but do not determine them," and "lower
  levels of autonomy may be desirable for particular tasks and contexts even as
  we reach higher levels of AGI."
- Feng, McDonald, Zhang, *Levels of Autonomy for AI Agents* (2025): "autonomy
  can instead be a deliberate design decision made by agent developers."

So autonomy is a **dial set per surface**, not a global setting, and choosing a
low setting is a legitimate design decision, not a capability deficit.

## The rule (where determinism belongs)

Three sources that look like they conflict resolve into one principle.

1. **Determinism on the side-effects, not the reasoning.** NVIDIA: "the risk
   associated with these systems lies mostly in the tools or plugins available
   to those systems," and "in the absence of a tool or plugin that can perform
   sensitive or physical actions, the primary risk posed by manipulation of the
   AI component is misinformation, regardless of the degree of complexity of the
   workflow." Gate the irreversible actions (spend, writes, external calls), not
   the model's thinking.

2. **Do not hardcode the meaning.** Anthropic, *Effective Context Engineering*:
   "engineers hardcoding complex, brittle logic in their prompts... creates
   fragility and increases maintenance complexity over time," and "as model
   capabilities improve, agentic design will trend towards letting intelligent
   models act intelligently, with progressively less human curation." Brittle
   lexical/semantic rules are the anti-pattern (this is exactly the word-overlap
   contradiction check in the checks doc).

3. **But keep deterministic control flow where the task is knowable.** The
   honest counter-evidence (below) shows determinism-at-boundaries is necessary
   but not sufficient. smolagents: "if that deterministic workflow fits all
   queries, by all means just code everything! ... it's advised to regularize
   towards not using any agentic behaviour"; agents "are often overkill."

Combined: **determinism moves out of the *meaning* and into the *boundaries,
side-effects, and any control flow you can flowchart in advance*. Model judgment
owns meaning and open-ended control - and is itself calibrated before it is
trusted.**

## The two failure modes this guards against

**Over-determinizing the reasoning.** Hardcoded brittle logic standing in for
judgment (Context Engineering). In deepr: lexical contradiction/dedup heuristics
used as verdicts. Fix: let the model judge meaning; keep the lexical layer only
as a high-recall router into the model check.

**Over-trusting the agent.** Two shapes, both well-evidenced:

- *Self-declared done.* Anthropic, *Effective Harnesses for Long-Running
  Agents*: the agent's "tendency to mark a feature as complete without proper
  testing" - it reports success without end-to-end verification. The fix is
  ground-truth verification, not a self-reported flag.
- *Compounding error over long horizons.* Success decays roughly exponentially
  with task length: METR measures current models succeeding "<10% of the time on
  tasks taking [humans] more than around 4 hours," and notes the 80%-reliability
  horizon is far shorter than the headline 50% horizon. Ord models "an
  exponentially declining success rate with the length of the task." Sinha et
  al. find **self-conditioning** - "as models make mistakes, they become more
  likely to make more mistakes" - though dedicated thinking models resist it.
  The mitigation is deterministic decomposition into short, checkpointed,
  validated steps - a workflow wrapping the agentic parts.

And model judgment is not free of bias: Ye et al. catalog 12 systematic
LLM-as-judge biases (position worst, plus verbosity and self-enhancement), more
pronounced on subjective/meaning-laden tasks. So "let the model judge meaning"
holds only with a calibration loop and bias controls - an uncalibrated judge is
itself a hidden nondeterminism.

## deepr's surfaces on the axis

| Surface | Setting | Why |
|---|---|---|
| Budget enforcement, cost ledger, quota ledger, backend eligibility, daily/monthly caps | **Workflow** (deterministic, gated) | Irreversible spend and quota exhaustion; the audit promise breaks if model-driven |
| Belief/knowledge persistence, archival, restore | **Workflow** | State writes; reversibility must be executable, not judged |
| Permission/approval flows, capacity admission | **Workflow** | Gate the irreversible action (spend, exec), not the reasoning (NVIDIA) |
| Boundary parsing (provider payloads, config, MCP args, extraction JSON shape) | **Workflow** ("parse, don't validate") | Form is decidable from structure alone |
| Capacity waterfall routing + capacity next actions | **Workflow gate over agent work** | Admission, eligibility, selection, numeric quality-floor gates, and next-action hints guard metered spend, quota exhaustion, overage, reserve floors, and task class routing; evals and model review may produce quality evidence, but workflow code enforces and explains the threshold |
| Local model comparison | **Agent meaning, workflow envelope** | A local or explicit CLI judge scores semantic answer quality; deterministic code validates artifact shape, score range, prompt failures, Deepr metered cost `$0`, records latency, requires CLI-judge opt-in, and keeps admission a human-reviewed gate |
| Local context eval | **Agent meaning, workflow envelope** | A local judge scores answer relevance, grounding, and honesty about missing fresh context; deterministic code validates context mode, source counts, citation-label bounds, prompt failures, latency, and Deepr metered cost `$0` |
| Sync source-pack artifacts | **Workflow** | Context-bearing sync answers cannot be absorbed unless the bounded source pack is written as a durable run artifact; the artifact records form and provenance, not semantic truth |
| Loop admission, ExpertLoopRun state, loop-status, stop reasons | **Workflow around agent work** | The agent can propose work, but admission, completion, budget/capacity stop, verifier pass/fail, acceptance metrics, and resumability are durable state |
| OKF export/import | **Workflow envelope, agent meaning** | Markdown/YAML shape and source-trust gates are deterministic; claim extraction and contradiction/grounding stay calibrated model judgment |
| Versioned expert handoff | **Workflow** | Remote consumers need one stable read contract; serialization, payload bounds, schema version, compatibility policy, and sensitive-read gating are deterministic and never semantic verdicts |
| Scoped remote MCP keys and audit | **Workflow** | Authentication, mode/expert scope, confirmation gates, argument hashing, and append-only remote-call audit events guard tool access and observability; they never judge the semantic quality of an expert answer |
| Contradiction / grounding / atomicity / dedup | **Agent** (calibrated model judgment) | Meaning; lexical rules are brittle (checks doc) |
| What to research next, gap selection, council adjudication | **Agent** | Open-ended; cannot be flowcharted in advance |
| Completion / "is this expert current" | **Agent verified by workflow** | Never a self-declared flag; the evidence layer measures ground truth |

## How this connects to deepr's existing direction

- **Budgeted autonomy** (README) *is* the workflow half of this axis: spend,
  stop conditions, audit trail are deterministic and gated. This doc names why
  that must stay deterministic even as experts get more agentic.
- **The evidence release** (v2.15: calibration + continuity) is deepr's direct
  answer to the self-declared-done failure. Calibration asks whether a reported
  `confidence: 0.9` actually means ~90% grounded; continuity asks whether an
  expert honestly declares its own staleness. Both replace a self-reported flag
  with measured ground truth - exactly what the long-running-harness guidance
  prescribes.
- **The capacity waterfall** (v2.16) is a textbook application: deterministic
  gates sit on spend, quota, selection, and numeric quality thresholds, while
  research and quality judgment stay model-driven and calibrated.
- **checks-deterministic-vs-agentic.md** is this principle applied to the
  data-quality layer (the lexical-router-then-model-verdict pattern).

## Decision checklist (per surface)

Use a **workflow** (deterministic) when any of these hold:

1. The task is flowchartable - the steps are knowable before the model runs.
2. It is long-horizon and reliability-critical (compounding error; decompose
   into short, checkpointed steps).
3. It produces an irreversible side-effect (spend, write, external call) - gate
   that step deterministically regardless of how the reasoning is done.
4. You need reproducibility, auditability, or tight cost/latency.

Use an **agent** (model-driven) when the task is genuinely open-ended and cannot
be hardcoded without becoming brittle - and then keep the deterministic gates on
its side-effects, calibrate any judgment on the critical path, and prefer the
least autonomy that solves the task.

Use a **loop** only when all four are true:

1. The task repeats often enough that automation removes recurring human work.
2. Verification is automated and independent of the agent's self-report.
3. Budget/capacity is explicit, capped, and observable before work starts.
4. The agent has the tools, logs, and state needed to inspect failures.

If any condition is missing, keep the surface advisory, one-shot, or
human-gated. The minimum viable loop is an automation trigger, a reusable context
package, durable state, and a verifier gate. Goal loops come before meta/team
loops; Deepr only widens autonomy after the smaller loop has acceptance metrics
and failure telemetry.

## Invariants

- Determinism guards side-effects and flowchartable control flow; it never
  stands in for semantic judgment (no hardcoded meaning).
- No self-declared "done" or "confident" on the critical path is trusted without
  ground-truth measurement (calibration, continuity, end-to-end verification).
- No loop is admitted without a verifier gate, a budget/capacity envelope,
  durable state, and a typed stop condition.
- Acceptance rate and cost per accepted knowledge change are workflow metrics;
  if the loop rejects most attempted changes, it stays supervised while prompts,
  tools, or verifiers improve.
- Every model judge is calibrated and bias-checked before its verdict is trusted.
- Autonomy is set per surface at the lowest level that solves the task; raising
  it is a deliberate, reversible decision with the side-effect gates intact.
- Generated portable artifacts (OKF bundles, digests, reports, skills) are
  derived views or ingestion sources, never authoritative state.

## Sources

Workflow vs agent + start-simple: Anthropic, *Building Effective Agents*
(anthropic.com/research/building-effective-agents, Dec 2024). Hardcoded-logic
fragility + "less structure, more model": Anthropic, *Effective Context
Engineering for AI Agents*
(anthropic.com/engineering/effective-context-engineering-for-ai-agents, 2025).
Self-declared-done: Anthropic, *Effective Harnesses for Long-Running Agents*
(anthropic.com/engineering/effective-harnesses-for-long-running-agents, 2025).
Gate-the-tools-not-the-reasoning + autonomy levels: NVIDIA, *Agentic Autonomy
Levels and Security* (developer.nvidia.com/blog/agentic-autonomy-levels-and-security/,
Feb 2025). Autonomy decoupled from capability: Morris et al., *Levels of AGI*
(arXiv 2311.02462). Autonomy as deliberate design: Feng, McDonald, Zhang,
*Levels of Autonomy for AI Agents* (arXiv 2506.12469, 2025). Regularize toward
least autonomy: HuggingFace smolagents, *Introduction to Agents*
(huggingface.co/docs/smolagents/en/conceptual_guides/intro_agents). Long-horizon
reliability: METR, *Measuring AI Ability to Complete Long Tasks* (Mar 2025) and
*time horizon limitations* note (Jan 2026); Ord, *Is there a half-life for the
success rates of AI agents?* (arXiv 2505.05115); Sinha et al., *The Illusion of
Diminishing Returns: Measuring Long Horizon Execution in LLMs* (arXiv 2509.09677).
LLM-as-judge bias: Ye et al., *Justice or Prejudice?* (arXiv 2410.02736).
Structure-improves-reliability counterweight: AgentSpec, *Customizable Runtime
Enforcement for Safe and Reliable LLM Agents* (ICSE 2026).

Confidence: workflow/agent framing, autonomy-level taxonomies, long-horizon
decay, and judge-bias findings are high-confidence (primary sources). The exact
80%-vs-50% horizon multiple (~5x) is approximate (METR 80% curve via secondary
analysis). Quotes were taken from live pages on 2026-06-13; re-verify before
relying on any single line in print.
