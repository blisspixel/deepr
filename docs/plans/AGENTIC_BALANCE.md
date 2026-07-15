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
| Budget enforcement, cost ledger, quota ledger, quota snapshots, backend eligibility, daily/monthly caps | **Workflow** (deterministic, gated) | Irreversible spend and quota exhaustion; the audit promise breaks if model-driven. Verified absorb applies one caller ceiling across extraction plus dynamically routed contradiction, dedup, and adjudication calls, with per-dispatch durable holds and aggregate provider-usage settlement. In v2.36, unsafe metered expert profile, curriculum, refresh, synthesis, gap-fill, compiled-sync, corpus-calibration, chat, standalone documentation-analysis, and LLM model-discovery entry points fail closed until each nested call and storage or tool side effect uses the shared durable per-call and parent-run budget transaction. Offline registry display and read-only provider model-list discovery remain available because they generate no model output. Append-only provider/model corrections are schema-validated against one unique earlier charge and affect only derived attribution views; raw events and dollar totals never change. The model still owns each semantic verdict; arithmetic decides only whether another call may run. |
| Budget degradation tiers + value-of-spend gate | **Workflow** (deterministic, gated) | The tier (from monthly-spend fraction) and the benefit-vs-hurdle comparison are arithmetic over caller-supplied numeric estimates; they gate irreversible metered spend and fail safe toward not spending (local/$0 stays available, denials are resumable, never failures). The value factors may be model-estimated upstream, but this gate enforces a numeric threshold, never a semantic verdict. Design: [budget-degradation.md](../design/budget-degradation.md) |
| Belief/knowledge persistence, runtime-state placement, archival, restore | **Workflow** | State writes and storage placement are deterministic; reversibility must be executable, not judged. Thought traces, hierarchical memory, reconstructed documents, graph/RAG state, feedback, prompt optimization, and consolidated knowledge all resolve through the same canonical expert directory as the profile and beliefs unless an explicit storage directory is supplied. `expert migrate-legacy-state` is dry-run by default, exact-profile-name scoped, limited to a closed set of known artifact names plus projected-empty known directories, collision-blocked before writes, and leaves unknown content untouched. A second `expert absorb` for the same expert is rejected by a non-blocking cross-process overlap guard before model construction across CLI and MCP. The guard also covers metered dry-runs because cost settlement updates profile state even when belief writes are disabled. |
| Permission/approval flows, capacity admission | **Workflow** | Gate the irreversible action (spend, exec), not the reasoning (NVIDIA) |
| Unit test network access | **Workflow** | The unit gate blocks outbound sockets and allows loopback fixtures only; this prevents accidental spend, credential leakage, and flaky live-service dependencies without judging test meaning |
| Runtime queue placement and stale-row diagnostics | **Workflow router, operator verdict** | Environment precedence and file placement guard state writes: an explicit queue path wins, then the configured runtime root, then the compatibility default. Unit tests pin the queue below a per-test root. A read-only age, status, and attempt-count query may identify stale lifecycle candidates and show reservation references, but it never concludes abandonment or changes a job or hold; an operator owns that decision. |
| Boundary parsing (provider payloads, config, MCP args, extraction JSON shape) | **Workflow** ("parse, don't validate") | Form is decidable from structure alone |
| Persisted research provider lifecycle | **Workflow** (deterministic, fail-closed) | `ResearchJob.provider` owns status polling, cancellation, terminal settlement, and provider-resource cleanup. Every queue-backed provider POST first restores the persisted reservation metadata and verifies its exact reservation ID, job ID, provider, model, and held maximum against an active job-owned row. The AWS hosted preview remains gated at both API admission and worker dispatch until it can prove the same transaction; its API cannot write a job or queue message, and its worker cannot import or construct a provider. Unsupported adapters and unavailable lifecycle state remain visible for recovery; they never fall through to another provider. Interface-specific provider/model compatibility is checked before spend or provider construction. Design: [research-cost-reservations.md](../design/research-cost-reservations.md) |
| Untrusted ingested/tool content boundaries | **Workflow envelope, agent meaning** | Web, scraped, report, document-preview, campaign-context, team-result, company-intelligence, and tool-result text is delimited and sanitized before prompt use so embedded directives stay source data; extraction, grounding, contradiction, and dedup still rely on calibrated model judgment |
| Capacity waterfall routing + capacity next actions | **Workflow gate over agent work** | Admission, eligibility, selection, numeric quality-floor gates, and next-action hints guard metered spend, quota exhaustion, overage, reserve floors, and task class routing; scheduled local sync, sync-all, route-gaps, and plan-sync local recall embedding use a read-only utilization signal as deterministic flow control, turning confirmed contention into a typed durable wait with bounded retry timing and argument-safe requested-operation argv while leaving unknown platform support visible and non-blocking. Resident VRAM is not a contention verdict, manual local execution remains an override, and no contention path falls through to paid capacity. Evals and model review may produce quality evidence, but workflow code enforces and explains the threshold. Design: [scheduled-local-capacity.md](../design/scheduled-local-capacity.md) |
| Bundled skill research-decision helper | **Workflow router only, no semantic or spend verdict** | Query length and lexical cues may suggest how to frame a preview, but the helper returns `explicit-model-required` with an intentionally unknown cost envelope. It cannot select a paid model, claim semantic complexity, decide budget fit, or authorize dispatch. The current provider/model/tool request preview owns the exact finite envelope and the user owns approval. |
| Plan-quota CLI execution backends (codex/claude/opencode/...) | **Workflow gate over agent work** | Child auth-mode control (known metered API-key env vars are removed before plan launch), fail-closed rejection of metered-at-margin adapters without complete estimate/reserve/settle/ledger support, concurrent stdout/stderr draining under independent 8 MiB raw-byte ceilings, pre-execution Windows Job Object or Linux child-subreaper ownership, refusal on other POSIX platforms until equivalent detached-descendant ownership exists, process-tree and pipe-transport cleanup on overflow, bounded nonce-correlated transcript recovery, error-channel exhaustion handling, OS-backed relative/absolute reset form parsing, typed attempt outcomes with unknown quota usage preserved, redacted tail diagnostics, quota+`$0` cost-ledger writes for every non-metered dispatch, argv/tool lockdown, stdin for long prompts, and the observed-quota auto-routing gate are deterministic no-surprise-bills guards; the CLI's answer and extracted beliefs stay model judgment, passing the same confidence/trust-floor/contradiction/dedup absorb gates as any source. Design: [plan-quota-cli-backends.md](../design/plan-quota-cli-backends.md) |
| Expert consult and council synthesis | **Workflow envelope, agent synthesis** | Expert selection, stored-belief context selection, provider/model routing, Anthropic Messages API request shape, provider completion-reason parsing, output-limit status, and the `deepr-expert-collaboration-v1` roster/role/trace/budget/evidence/dissent contract are bounded context assembly and protocol metadata, not truth verdicts. Local and explicit plan-quota synthesis are owned/prepaid capacity modes and disable live metered expert fallback when stored context is missing. Local council requests disable separate Ollama thinking so the bounded output allowance remains available for a visible answer; this request-shape rule never reaches plan or metered providers. Metered synthesis requires an exact provider/model pricing contract, an exact full-budget reservation below the absolute per-operation ceiling, a serialized-input plus protocol/output ceiling within its synthesis budget slice, exact OpenAI cached-token splits when provider usage exposes them, conservative labels when cache details are absent, disabled retries on every Deepr-created SDK client, and idempotent canonical-ledger-required settlement for every ambiguous post-dispatch failure or cancellation. Deepr's Anthropic request contains no prompt-cache control and cannot select the one-hour cache-write tier. Injected custom clients remain caller-owned and must provide their own retry and request policy. An empty visible answer remains a typed failure or truncation, and private reasoning is never promoted as the answer. The model still owns synthesis meaning and whether perspectives agree; deterministic code owns expert limits, response-shape instructions, budget reservation, cache-bucket cost settlement, ledger writes, context metadata, collaboration metadata, and no-surprise-bills behavior. |
| Bounded expert deliberation | **Workflow envelope, agent meaning** | The host fixes the roster, immutable snapshot hashes, round protocol, provider eligibility, maximum dispatch formula, finite turn/token/context/time/spend ceilings, lineage, idempotency, heartbeats, cancellation, resume, typed stops, trace-only write boundary, and graph-commit prohibition. Models choose which assumption matters, which targeted follow-up is useful, how to answer or revise, what remains uncertain, and which tests or gaps to propose. Schema and cardinality checks never decide whether a challenge is insightful, a citation supports a claim, dissent is meaningful, or a synthesis is true. Those semantic verdicts require human or calibrated, bias-checked review. Design: [bounded-expert-deliberation.md](../design/bounded-expert-deliberation.md) |
| Expert chat backend seam | **Workflow envelope, agent response** | Backend request shape, feature flags, provider routing, unsupported-parameter omission, usage extraction, cost settlement, disabled hidden SDK retries, and no-fallback behavior are deterministic workflow controls. In v2.36 every standalone metered `ExpertChatSession` dispatch and interactive API chat entry fails closed. Legacy task-planning, hosted-vector upload, and knowledge-synthesis helpers carry independent inner gates so slash-command or direct Python invocation cannot bypass the session boundary. Local and explicit plan read-only query remains available. Metered restoration requires durable estimate, reserve, dispatch mark, and settlement for every provider, hosted-storage, and auxiliary call, hard output ceilings, one parent session budget, and serialized turns. The expert answer, tool-use intent, synthesis, uncertainty, and semantic usefulness remain model judgment bounded by budget and tool-policy gates. Design: [expert-chat-capacity-backends.md](../design/expert-chat-capacity-backends.md) |
| Maker-checker grounding checks | **Workflow routing, agent verdict** | `--check-grounding`, `--checker-plan`, vendor diversity, dry-run suppression, and no automatic metered checker path are deterministic controls over cost and execution; whether evidence entails the claim remains a calibrated model judgment. |
| Local model comparison | **Agent meaning, workflow envelope** | A local or explicit CLI judge scores semantic answer quality; deterministic code validates artifact shape, score range, prompt failures, Deepr metered cost `$0`, records latency, requires CLI-judge opt-in, and keeps admission a human-reviewed gate |
| Local context eval | **Agent meaning, workflow envelope** | A local judge scores answer relevance, grounding, and honesty about missing fresh context; deterministic code validates context mode, source counts, citation-label bounds, prompt failures, latency, and Deepr metered cost `$0` |
| Consult-quality calibrated judge | **Agent meaning, workflow envelope** | An explicit local Ollama or explicit non-metered plan-quota judge scores consult answer quality against the published rubric using the local trace answer at command time. The premium API judge implementation is gated in v2.36 until it uses the shared durable call transaction. Deterministic code validates every score, allowed failure label, review decision, cost posture, plan quota metadata, promotion gate, and storage boundary so raw trace answers and raw judge responses do not become durable review artifacts. |
| Hallucination-pattern risk signals | **Workflow router, agent verdict** | Deterministic code may preserve provenance, date fields, context-position metadata, middle-context review-candidate routing, schema-valid risk labels, and review-routing status, but it must not decide that a claim is false, unsupported, sycophantic, hallucinated, or missing middle evidence from lexical rules or position alone. Pattern labels inform prompt variants, retrieval strategy, regression selection, and human or calibrated-model review; they do not block answers or write beliefs by themselves |
| Agentic red-team metrics | **Workflow verifier, agent meaning stays downstream** | `deepr eval red-team` measures prompt-boundary canary leakage, required untrusted-content delimiters, structured tool-spoof neutralization, host-facing MCP read-payload canary leakage, and trust-floor confidence ceilings at `$0`; it can save trend artifacts, but it does not decide semantic truth |
| Sync and topic-learning source artifacts and generation readiness | **Workflow envelope, agent support selection** | Subscription retrieval receives a concise topic plus bounded-focus route while synthesis retains the full answer prompt. Context-bearing sync and `learn-web` answers cannot be generated or absorbed unless a bounded minimum of fetched or cache-validated sources has replayable excerpts and valid content hashes; explicit URL review retains a one-source path, and search candidates that did not fetch remain diagnostic evidence without becoming citations. Under-ready packs persist as retryable no-metered failures before local or plan generation. Topic learning also persists a manifest, source notes, snapshots, and successful report under the configured expert root. The extraction model selects which exact source supports each candidate; deterministic code accepts exact catalog-value membership or exact key membership after removing at most one citation-form bracket pair, stores only the selected replay pointer, and never parses prose evidence, assigns every URL, or makes a lexical support verdict. Freshness advances only after an absorbed or contested write or a replayable source-backed current-sync result. Dry runs, all-rejected absorption, under-ready evidence, failures, and ungrounded no-change markers do not advance it. Event-backed reconciliation may repair profile timestamps only from accepted events for currently live beliefs and regenerates only a Deepr-derived system message. Design: [local-fresh-context.md](../design/local-fresh-context.md) |
| Research processing compiler and compiled wiki | **Workflow envelope, agent meaning** | Source snapshot ids, content hashes, deterministic manifest readiness, source-note refs, prompt/schema versions, response hashes, candidate envelope shape, verifier-decision envelope shape, type-specific policy requirements, verifier-supplied candidate edge references, temporal edge qualifier shape, ISO temporal field validation, explicit `--compile-claims` budget and cost-ledger gates, graph commit envelope schema versions, `apply-graph-commit` idempotency keys, `--stage-compiled-claims` no-write staging, confirmation gates, locks, typed edge writes, verified gap-promotion writes, verified exploration-agenda writes, verified hypothesis writes, verified concept writes, verified stance writes, verified original-idea writes, derived wiki regeneration, and one commit point are deterministic. Candidate-level verifier rejection stays artifact-only and does not veto unrelated verifier-ready operations; top-level schema, kind, response integrity, or any invalid selected operation still blocks the whole selected set before writes. Atomic claim extraction, source support interpretation, semantic edge discovery, contradiction, grounding, deduplication, temporal-scope judgment, temporal edge meaning, gap selection, agenda quality, hypothesis quality, concept quality, stance quality, original-idea quality, and narrative synthesis remain calibrated model judgment. |
| Expert memory card (`EXPERT.md`) | **Workflow view over agent state** | `deepr-expert-memory-card-v1` deterministically renders profile, manifest, belief events, self-model state, explicit perspective tags, open gaps, contradictions, self-research agenda, and agency scope into a derived `EXPERT.md` orientation packet. It costs `$0`, previews by default, writes only on `--write`, and is never canonical memory. Models may later propose theories, stances, original ideas, identity changes, or learning-policy changes, but those enter through verifier, self-model, and review gates rather than by editing the card. |
| Expert next-action navigator | **Workflow router, no semantic verdict** | `deepr expert next` maps claim count, freshness, gap count, contradiction count, and durable loop status onto bounded argument-safe argv plans. Capacity inspection and scheduled execution gates prevent an assumed local backend or silent metered fallback. The `deepr-expert-next-v1` contract is read-only, costs `$0`, and explicitly disallows a semantic maturity verdict or default policy change. Human or calibrated-model evaluation still decides whether the expert's perspective improved. Design: [expert-next-actions.md](../design/expert-next-actions.md) |
| Belief, concept, and original-idea recall | **Workflow router, agent verdict** | Local recall over supplied vectors, concept text, belief text, and original-idea perspective text returns `candidate_only` routing metadata. It is read-only, may use a lexical fallback only as a cheap candidate router, and never decides same-claim, support, contradiction, grounding, confidence, idea quality, or edge writes. Claim verification may carry recall hits in read-only `recall_context`, and the sync verifier can include those hits in its bounded prompt, but the packet cannot change readiness or write graph state. Original-idea hits carry perspective-state authority and a non-factual promotion policy. A verifier or graph commit envelope must make any semantic decision. |
| Expert perspective state | **Agent meaning, workflow envelope** | Concepts, stance, hypotheses, tradeoffs, watchlists, original ideas, and exploration agendas are part of expertise, not second-class facts. Deterministic code labels artifact type, provenance, freshness, uncertainty fields, budgets, and write boundaries; calibrated model judgment owns conceptual fit, relevance, novelty, dissent, and whether a stance is useful. Evidence grounds factual claims; it must not become a brittle checklist that defines expertise. |
| Historically grounded perspectives | **Agent interpretation, workflow provenance envelope** | Deterministic code owns persistent AI disclosure, historical identity and cutoff, source and quotation refs, temporal bridge labels, non-impersonation rules, artifact lanes, and write prohibitions. Calibrated model or qualified human review owns whether a documented method is faithfully interpreted, useful, or caricatured. A perspective lens cannot claim human identity, invent memory, hide uncertainty, or write fictional dramatization into canonical belief state. Design: [historically-grounded-perspectives.md](../design/historically-grounded-perspectives.md) |
| Original ideas and private hypotheses | **Agent meaning, workflow envelope** | A useful idea may not exist online yet. Lack of web evidence is not refutation and should not block the expert from preserving a conjecture, stance, or research direction. Workflow code must label the state as hypothesis, stance, proposal, or original synthesis; record origin, assumptions, rationale, uncertainty, expected observations, disconfirming signals, and review status; and prevent it from being presented as a verified external fact until support exists. |
| Level 5/6 expert self-improvement | **Workflow control plane, agent self-model and proposals** | Experts may mine traces, emit metacognitive monitor proposals, promote reviewed gap/eval proposals through explicit apply-gated commands, write verifier-gated self-model update review records, write outcome-evidence acceptance records, propose research, and propose prompt/tool/skill changes, but workflow code owns rollout stage, budget, sandbox, schema, provenance, regression checks, permission boundaries, and human-review gates. Accepted self-model update records may enter learning transactions only as read-only guidance until measured before/after evidence justifies a concrete policy effect. Self-model changes describe capabilities, limits, goals, calibration, and learning strategy; they do not grant new authority. Design: [level-5-6-expert-maturity.md](../design/level-5-6-expert-maturity.md) |
| Multi-device expert continuity | **Workflow merge envelope, agent meaning** | Sequential synced-folder portability is a file-placement feature, not concurrent replication. The planned device-partitioned event layer owns device ids, event ids, schemas, hashes, causal refs, idempotency, tombstones, deterministic replay, and conflict surfacing. Calibrated model or human review owns semantic merge decisions for concurrent belief, stance, hypothesis, and policy edits. Design: [multi-device-expert-continuity.md](../design/multi-device-expert-continuity.md) |
| ExpertEventV2 and selective forgetting | **Workflow event authority, agent meaning** | Deterministic code owns canonical serialization, hashes, causal and bitemporal fields, replay, projections, tombstones, protected classes, replica convergence, and deletion-policy boundaries. Model or human judgment owns contradiction, semantic revision, usefulness, and whether contested perspectives can be reconciled. Storage convergence never manufactures semantic consensus. Design: [expert-event-memory-v2.md](../design/expert-event-memory-v2.md) |
| Harness run snapshots, approvals, steering, and skill candidates | **Workflow control plane around agent work** | Capability snapshots, prepared approval hashes, budget inheritance, trace lineage, safe steering boundaries, abort restoration, sandbox scope, and promotion gates are deterministic. Models may propose steering responses and candidate skills, but activation requires replay, held-out evaluation, negative-transfer checks, and reviewed approval. Design: [agent-harness-lessons-2026.md](../design/agent-harness-lessons-2026.md) |
| Pre-sync change-detection gate | **Workflow** | HTTP validators and content-hash equality over fetched sources gate paid side-effects (skip absorb when retrieval is byte-identical to the prior sync) and avoid needless body transfer for known URLs. It fails safe toward proceeding, never skips on uncertainty, and a hash matches bytes not meaning so it cannot false-positive on paraphrase; contradiction/grounding/dedup stay calibrated model judgment in the absorb pipeline it gates. Design: [change-detection-gate.md](../design/change-detection-gate.md) |
| Loop admission, ExpertLoopRun state, loop-status, stop reasons, per-verb overlap locks, startup jitter | **Workflow around agent work** | The agent can propose work, but admission, completion, budget/capacity/overlap stops, verifier pass/fail, acceptance metrics, resumability, and side-effect serialization are durable workflow state. Non-dry single-expert sync and each locked sync-all attempt persist RUNNING before engine construction and transition the same run id on completion or caught failure, so a hard termination stays observable instead of becoming untracked work; failures retain settled spend exposed by typed exceptions. |
| OKF export/import | **Workflow envelope, agent meaning** | Markdown/YAML shape and source-trust gates are deterministic; claim extraction and contradiction/grounding stay calibrated model judgment |
| Versioned expert handoff | **Workflow** | Remote consumers need one stable read contract; serialization, payload bounds, schema version, compatibility policy, derived read-payload sanitization, sensitive-read gating, and grounding-assurance counts are deterministic and never semantic verdicts |
| A2A task/result envelopes and host validation | **Workflow** | Agent-to-agent consumers need stable task state; schema version, kind, lifecycle state, timestamps, cost field, attached artifacts, Agent Card discovery paths, and untrusted-result boundaries are deterministic and never semantic verdicts. A2A consult tasks reuse the existing consult artifact; workflow code maps and validates capacity, trace, cost, artifact linkage, and dissent metadata while model judgment still owns synthesis meaning. |
| Remote expert conversations | **Workflow state and authority envelope, agent meaning** | The planned conversation core deterministically owns opaque handles, caller ownership, roster and frozen-snapshot lineage, turn ordering, idempotency, optimistic concurrency, retention, deletion, context and capacity ceilings, lifecycle, protocol mapping, and typed stops. Models own the answer, assumptions, uncertainty, relevance, clarification need, evidence interpretation, revision, agreement, and dissent. A transcript is operational state and cannot authorize spend, tools, downstream actions, or expert-memory writes. MCP receives an explicit application handle and A2A later maps it to `contextId`; neither transport state nor a task id becomes conversation authority. Design: [remote-expert-conversations.md](../design/remote-expert-conversations.md) |
| Published schema registry | **Workflow** | Schema version constants, required fields, additive compatibility policy, and deprecation rules are consumer contracts; they describe structure, not semantic truth |
| Scoped remote MCP keys, hosted templates, registration manifests, and audit review | **Workflow** | Authentication, mode/expert scope, confirmation gates, per-key budget ceilings, fail-closed metered-tool estimate coverage, per-key rate limits, HTTP concurrency caps, argument hashing, response-cost attribution, append-only remote-call audit events, hosted deployment guardrails, token-redacted registration metadata, and local audit-log filters/summaries guard tool access, spend, and observability; they never judge the semantic quality of an expert answer |
| Contradiction / grounding / atomicity / dedup | **Agent** (calibrated model judgment) | Meaning; lexical rules are brittle (checks doc). Contradiction routing may use lexical overlap, but normal detection returns only model verdicts, generic belief insertion cannot persist router hits, and absorb-time contradiction edges require an initial YES plus a fresh-context structured disconfirmation. Deterministic code validates response shape, records verification provenance, and measures provenance coverage separately from semantic accuracy. |
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

## Rollout and Versioning Discipline

Agentic surfaces move through explicit rollout stages:

1. **Prototype** - manual or local-only, no unattended writes or spend.
2. **Shadow** - runs beside the baseline and records deltas, without changing
   state or routing production work.
3. **Pilot** - opt-in for a bounded user, expert, tool, or task class with
   tighter budgets and extra telemetry.
4. **Limited production** - default for a narrow surface after verifier,
   recovery, and cost metrics are stable.
5. **Full production** - broad default only after regression evidence and CI
   coverage prove the verifier and recovery path hold.

Prompts, tool specs, schemas, eval sets, memory policies, and orchestration
graphs are versioned when a host, user, scheduler, or stored artifact depends on
them. Versioning is not ceremony: it makes failures bisectable, lets agents hand
off state safely, and keeps prompt or graph changes testable against the same
golden and adversarial cases.

State-changing surfaces must document retry behavior, idempotency keys or
deduplication strategy, and rollback or compensation behavior before moving past
pilot. Planning and irreversible execution stay separated; the workflow decides
when a proposed action is authorized to spend, write, publish, modify
permissions, or call an external side-effecting tool.

## Invariants

- Determinism guards side-effects and flowchartable control flow; it never
  stands in for semantic judgment (no hardcoded meaning).
- No self-declared "done" or "confident" on the critical path is trusted without
  ground-truth measurement (calibration, continuity, end-to-end verification).
- No loop is admitted without a verifier gate, a budget/capacity envelope,
  durable state, and a typed stop condition.
- Expert conversation is proposal-only. Deterministic orchestration owns
  roster, frozen snapshots, dispatch bounds, lineage, cancellation, resume,
  trace-only writes, and typed stops; model output cannot authorize spend,
  tools, graph commits, or expert-state writes.
- Acceptance rate and cost per accepted knowledge change are workflow metrics;
  if the loop rejects most attempted changes, it stays supervised while prompts,
  tools, or verifiers improve.
- Every model judge is calibrated and bias-checked before its verdict is trusted.
- Autonomy is set per surface at the lowest level that solves the task; raising
  it is a deliberate, reversible decision with the side-effect gates intact.
- Factual belief support gates do not apply unchanged to original ideas,
  hypotheses, or stances. Those states need provenance of thought, uncertainty,
  review status, and disconfirmation hooks, not online-source vetoes.
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
Harness engineering and loop practice checked again on 2026-06-25:
OpenAI, *Harness engineering: leveraging Codex in an agent-first world*
(openai.com/index/harness-engineering/, Feb 2026); Anthropic, *Harness design
for long-running application development*
(anthropic.com/engineering/harness-design-long-running-apps, Mar 2026);
OpenAI Cookbook, *Build an Agent Improvement Loop with Traces, Evals, and
Codex* (developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop,
May 2026); OpenAI Cookbook, *Build iterative repair loops with Codex*
(developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex,
May 2026); OpenAI Cookbook, *Building Reliable Agents with Memory and
Compaction*
(developers.openai.com/cookbook/examples/agents_sdk/building_reliable_agents_memory_compaction,
May 2026). The useful update for Deepr is that traces, feedback, evals,
context packs, and explicit handoffs are now the core loop artifact, while
provider-specific harness assumptions must remain swappable as models improve.
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
