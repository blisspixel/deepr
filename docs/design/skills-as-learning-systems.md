# Skills as reviewed procedural memory

Status: design updated 2026-10-29. Reconciles the earlier proposal with current
position history, experience projection, evaluation, and execution gates.
[ROADMAP](../../ROADMAP.md#persistent-expert-agent-delivery) owns delivery;
[persistent expert agents](persistent-expert-agent.md) owns the connected design.

## Purpose

An expert learns both what to believe and how to investigate or solve problems.
A reusable method records when to act, which assumptions to check, what
observations distinguish alternatives, and when the method is unsuitable.
Procedural learning belongs in the first supervised expert workflow, rather
than being reduced to claim extraction or deferred entirely to optimization.

Markdown can explain a method and export it to a host. It is not a second
canonical store. A procedure needs versioned ownership before an exported
skill can be described as learned expert capability.

## Existing substrate and missing behavior

| Existing seam | What it provides | What remains planned |
| --- | --- | --- |
| `consult_context.py` and `consult_prompt.py` | Bounded delivery of retained understanding | On-demand method and episode inspection in an adaptive session. |
| `position_ledger.py` | Position versions and record-time reads | Full justification fidelity and consistent finding/source history selection. |
| `consult_traces.py`, `outcomes.py`, `experience.py` | Trace/outcome records and read-only experience joins | Reviewed interpretation of an outcome into a scoped procedure revision. |
| `research_practice.py` | Research agenda and practice representation | Evidence-backed method selection and improvement, with negative transfer tests. |
| Skill inventory, scaffolding, export | Packaging and discoverability | Runtime execution remains gated; inventory is not execution authority. |
| S0 evaluation and local trial | Retained operational and answer evidence | Controlled proof that a learned method helps future work. |

Earlier claims that Deepr has no evaluation, no surviving position history,
or no experience readback are obsolete. Existing mechanisms still do not prove
improvement. A position surviving many corpus changes can indicate stability,
inattention, or repeated copying; survival count cannot establish competence.

## Procedure candidate contract

Before implementation, extend the existing research-practice/skill owner with
an additive versioned contract rather than another method registry. Include:

- Purpose, applicable task/environment, required inputs, and exclusions.
- Steps and decision points, with observations that could change the approach.
- Original episode, exact evidence, result, and failure references.
- Positive examples, counterexamples, uncertainty, and unsupported extensions.
- Parent method revision, proposed change/rationale, review disposition,
  rollback target, and retirement conditions.

Execution success is insufficient. Review whether the method contributed,
whether a simpler approach would work, and how success depends on environment.
Keep inconclusive outcomes. Compare like tasks; usage frequency and unadjusted
success rates reward selection bias.

## Authority and lifecycle

`observation -> candidate method -> review -> admitted version -> scoped reuse
-> outcome -> proposed revision`

First delivery uses explicit supervised review. Model critique helps formulate
a candidate; it cannot independently authorize its own method. Loading
instructions and executing code named by those instructions are different
capabilities. Neither bypasses spend, network, filesystem, identity, or writes.

Procedural review does not prohibit reasoned perspective. An expert can offer a
well-explained judgment or labeled analogy before it becomes a procedure. Both
still need faithful attribution and useful uncertainty; canonical perspective
writes retain separate admission.

Generated SKILL.md exports bind to admitted method revisions. Host edits return
as proposals. Imported skills are untrusted. Rejection or rollback preserves
prior usable state and records why the newer method was not kept.

## Validation and sequencing

Use the preserved retry experiment to distinguish a scoped finding from a
general method. New cases test whether the procedure selects useful experiments,
transfers appropriately, corrects misleading premises, and stops applying when
assumptions change. Review useful work and explanation, not expected phrases.

S1 development can expose method candidates without writes. S2 owns lineage and
apply integrity; S3 owns reviewed procedural reuse and inquiry; S4 compares
later outcomes and resources with a fresh baseline. These belong to one
supervised workflow with separate promotion gates. Autonomous optimization,
RL, marketplaces, and fleet propagation remain deferred.

The [research assessment](../research/expert-agent-systems-2026-10-29.md)
compares Hermes, ACE, AgeMem, LangMem, and other references. No new dependency
or graph database is required for the first method-learning connection.
