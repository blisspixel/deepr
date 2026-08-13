# Deepr approach contract

Status: normative approach document for the open-source tool, 2026-08-01.

| Question | Document |
| --- | --- |
| What is the method? | **This file** |
| What currently runs? | [SUPPORTED_SURFACE.md](SUPPORTED_SURFACE.md) |
| What capacity classes exist? | [CAPACITY.md](CAPACITY.md) (no-surprise-bills) |
| What is active engineering work? | [ROADMAP.md](../ROADMAP.md) |
| What is aspirational only? | [VISION.md](VISION.md) |
| What changed in a release? | [CHANGELOG.md](CHANGELOG.md) |

This document freezes **what Deepr is as a method**: an open-source tool and
approach, not a shipping checklist and not a commercial product plan. If prose
elsewhere conflicts with this contract on claims or refusals, treat this file
as the approach-level source of truth until both are reconciled. If this
contract conflicts with [SUPPORTED_SURFACE.md](SUPPORTED_SURFACE.md) on *what
currently runs*, the supported surface wins for operators and host agents.

---

## 1. What this is

Deepr is an **open-source tool and approach** for turning research work into
**durable, inspectable domain expertise** under **explicit capacity bounds**.

It is:

- a way to compile evidence into structured expert state (beliefs, gaps,
  contradictions, confidence, citations, provenance, temporal edges, stance,
  and related records);
- a capacity model that prefers owned local inference, then proven
  non-metered plan quota, and treats metered APIs as premium, fail-closed
  paths;
- a **role** for larger agent systems: produce handoff-ready artifacts under
  budget and authority contracts, usually via MCP, without claiming to be the
  host orchestrator.

It is not:

- a commercial product strategy, growth funnel, or market positioning deck;
- a guarantee of frontier one-shot answer quality against vendor deep-research
  products;
- a claim of general agent autonomy or consciousness;
- permission to run every command that appears in historical docs or design
  notes.

---

## 2. Core thesis

1. **Research is input; revisable expert state is the asset.** A report or chat
   transcript is evidence or a derived view, not the whole mind of the system.
2. **Cumulative understanding beats one-shot retrieval** when the same domain
   decisions recur over days or months.
3. **Capacity is a proof problem**, not a configuration preference. Presence of
   a CLI, API key, or positive budget is never spend authority.
4. **Determinism guards form and side-effects; model judgment owns meaning.**
   See [plans/AGENTIC_BALANCE.md](plans/AGENTIC_BALANCE.md).
5. **Unknown-wrongness is the hard problem.** Stale state is a prior to
   re-check, not an authority. Freshness, contradiction, and willingness to
   revise are part of the approach, not optional polish.
6. **Context is engineered.** Compact task context is assembled from
   canonical expert state. Raw corpus chunks are evidence inputs, not the
   expert itself.
7. **Consultation is an evidence workflow.** Independent positions, explicit
   uncertainty, and host-owned decisions beat forced consensus and agent-count
   theater.
8. **Derived views are regenerable.** Digests, wikis, and `EXPERT.md` cards
   are not canonical memory.

---

## 3. What the approach claims

When the corresponding surface is **stable** or **experimental but usable**
per [SUPPORTED_SURFACE.md](SUPPORTED_SURFACE.md), the approach claims:

| Claim | Meaning |
| --- | --- |
| Durable expert state | Domain experts can persist structured knowledge with provenance and revision-friendly records. |
| Local-first work | Expert setup, maintenance, evaluation, and consult paths can run on owned local models after endpoint ownership is proven. |
| Plan-quota honesty | Subscription/plan adapters execute only when auth, confinement, remaining quota, and paid-overage posture can be proven. Today only safety-eligible adapters run; others may be visible and blocked. |
| Fail-closed paid paths | Attended metered dispatch requires a typed, expiring $2-or-less total grant plus complete pricing, reservation, exact client, credential, endpoint, model, and transport binding. Unattended dispatch still requires provider account-control evidence. |
| Append-only spend memory | Settled cost events are not silently rewritten; reconciliation uses dispositions and offline billing evidence without inventing authority. |
| Handoff-ready outputs | Experts can emit structured artifacts (reports, beliefs, gaps, consult packets, loop status) suitable for hosts and other tools. |
| MCP as composition | Deepr can act as a tool/server role under MCP, including dual-era protocol support as documented for the release. |
| Separation of concerns | Kernel (execution, budget, routing), primitives (experts, tools, storage), and interfaces (CLI, web, MCP) stay layered so the method can be reused or forked. |

These claims are **method claims**. They do not assert that every listed
design note is implemented, or that every experimental surface is stable.

---

## 4. What the approach refuses

The approach deliberately refuses the following, even when convenient:

| Refusal | Why |
| --- | --- |
| Silent paid fallback | Automatic metered fallback hides capacity class and spend. |
| Budget as permission | A ceiling is a maximum, not authorization to dispatch. |
| Environment flags as spend authority | `DEEPR_*` allow flags do not replace hard cost proofs. |
| Lexical verdicts on meaning | Word-overlap, keyword, or regex checks may route; they must not conclude contradiction, grounding, quality, or similarity as truth. |
| Wiki or digest as canon | Generated prose is a view; writes go through verified absorb. |
| Graph size as quality | Count of nodes, reports, or self-confidence is not held-out proof. |
| Orchestrator monopoly | Deepr does not need to own the full agent workflow. |
| Phenomenal consciousness claims | Functional continuity and inspectable self-models only. |
| Unproven plan CLIs as plan capacity | Visibility is not executability. |
| Network side-effects when marginal cost is unknown | SearXNG, off-box heartbeats, and similar remain blocked until cost can be proven. |
| Impersonation or invented memory for historical lenses | Sourced method lenses only; no fake lived memory. |

If a future change violates a refusal, it must update this contract in the
same change and state what was traded away.

---

## 5. Capacity classes (approach-level)

Three classes. Execution always requires class-specific proof.

1. **Owned local** - preferred for expert lifecycle when the endpoint is owned
   and zero-dollar at the model-provider margin can be established.
2. **Prepaid plan quota** - allowed only with stored auth class, tool
   confinement, remaining-quota evidence where required, and live proof that
   paid extra usage is off for that dispatch.
3. **Metered API** - preview, accounting, and offline reconciliation are
   available. A narrow attended CLI surface may dispatch only under a typed,
   expiring $2-or-less total grant, complete durable reservation, explicit
   per-call consent, and an exact Deepr-owned client binding. MCP, schedules,
   loops, automatic fallback, and other unattended work stay blocked until
   authenticated account-control and credential-identity proofs bind to the
   exact request.

Unknown, partial, or conflicting evidence **blocks**. Clean billing
reconciliation does not, by itself, unfreeze paid capacity.

---

## 6. Epistemic state (what "expert" means here)

An expert is **durable epistemic state plus bounded knowledge verbs**, not a
chat persona and not a static FAQ.

| Kind of state | Requirement |
| --- | --- |
| Factual claim | Provenance and grounding expectations |
| Interpretive stance | Rationale and uncertainty |
| Hypothesis | Predicted observations or disconfirming signals |
| Gap / learning agenda | Why it is worth exploring |
| Contradiction | Model-judged under calibrated checks, not keyword theater |
| Temporal edge | When something was learned or changed, not only what |

Self-report from a model is evidence to interpret, never sole proof of
correctness, maturity, or consciousness.

---

## 7. Determinism vs judgment

Normative rule (full argument in
[plans/AGENTIC_BALANCE.md](plans/AGENTIC_BALANCE.md)):

- **Code owns:** schemas, types, ranges, spend, writes, process confinement,
  flowchartable control flow, receipt identity, reservation lifecycle.
- **Model owns:** meaning inside bounded frames - contradiction, grounding,
  atomicity, semantic dedup, synthesis judgment - after calibration where
  required.
- **Lexical signals may route.** They must not conclude.

---

## 8. Composition model

Deepr is designed to be **one specialist role**:

- Hosts (humans, IDEs, orchestrators) call tools or CLI with budget and
  authority envelopes.
- Deepr returns structured results, not permanent control of the outer loop.
- Natural language may carry intent inside a typed envelope; natural language
  is not the protocol of record.
- Default is shared process and shared contracts, not one OS process and
  recursive subagent stack per expert.

---

## 9. Surface classes (how to read the tree)

| Class | Meaning |
| --- | --- |
| **Stable** | Approach contract plus supported surface: rely on it; breakages need migration notes. |
| **Experimental but usable** | Works and is tested; names or envelopes may still move before 3.0. |
| **Visible / read-only** | Inspectable or modeled; not an execution promise. |
| **Gated / fail-closed** | Code or docs may describe the path; runtime refuses until proofs exist. |
| **Design-only** | ROADMAP or `docs/design/` intent; not a claim of current capability. |

Operators and host integrators should read
[SUPPORTED_SURFACE.md](SUPPORTED_SURFACE.md) before assuming a path runs.

---

## 10. Core loop of the approach

The method, independent of any single UI:

1. **Define** an expert with purpose and scope.
2. **Ingest** evidence (research, absorb, sync) under explicit capacity.
3. **Compile** into canonical state (beliefs, gaps, edges, stance, ...).
4. **Consult** with frozen or bounded context; preserve uncertainty and
   dissent where relevant.
5. **Revise** when new evidence or contradiction warrants it.
6. **Refresh** against unknown-wrongness (staleness, watchlists, re-checks).
7. **Evaluate** with held-out or process measures where available; do not
   substitute graph size for proof.
8. **Hand off** structured artifacts to a human or host agent.

Any implementation that skips capacity proof, provenance, or revision
discipline is not following this approach even if it reuses the package name.

---

## 11. How to judge whether the approach is holding

The approach is holding when:

- the same domain can be revisited with **inspectable state change** over time;
- spend and capacity class are **reconstructible** from durable records;
- meaning judgments are not smuggled in as brittle string rules;
- hosts can compose Deepr without Deepr owning their workflow;
- docs distinguish **runs today** from **designed later**;
- unknown-wrongness is treated as a first-class loop (refresh, contradiction,
  revision), not an afterthought.

The approach is failing when:

- gated or design-only paths are described as general capability;
- ledgers, freezes, or capacity proofs are weakened for convenience;
- mechanical churn displaces evidence quality and calibration;
- derived prose becomes the only memory;
- "more agents" substitutes for better evidence and clearer authority.

This section is a quality bar for the method. It is not a growth metric and
not a release gate.

---

## 12. Related documents

| Document | Role |
| --- | --- |
| [SUPPORTED_SURFACE.md](SUPPORTED_SURFACE.md) | What currently runs and is portable |
| [CAPACITY.md](CAPACITY.md) | Capacity ladder and no-surprise-bills contract |
| [plans/AGENTIC_BALANCE.md](plans/AGENTIC_BALANCE.md) | Determinism vs model judgment |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical layout |
| [security/THREAT_MODEL.md](security/THREAT_MODEL.md) | Trust boundaries |
| [VISION.md](VISION.md) | Aspirational direction (not current capability) |
| [../ROADMAP.md](../ROADMAP.md) | Active work and design backlog |
| [../README.md](../README.md) | Entry point for the tool |

---

## 13. Change rule

Update this file when:

- a refusal is relaxed or added;
- the capacity proof model changes;
- the expert-state thesis changes;
- composition (role vs orchestrator) changes.

Do not use this file as a feature dump. Do not treat roadmap items as
approach claims until they land in [SUPPORTED_SURFACE.md](SUPPORTED_SURFACE.md)
or an explicit revision of this contract.
