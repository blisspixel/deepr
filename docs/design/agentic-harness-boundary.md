# The agentic harness boundary: bounded domain work with continuity

Status: architecture direction updated 2026-10-29 by
[ADR 0008](../decisions/0008-persistent-domain-agent-boundary.md). Replaces the
June 21 synchronous-only restriction. This document grants no new runtime,
spend, external-action, or memory-write authority.

## The boundary

Deepr owns persistent domain expertise and bounded research episodes. An expert
can have a continuing identity, knowledge, perspective, research agenda,
experience, and reviewed methods. It should explain, investigate, learn, and
resume useful work. The [persistent expert design](persistent-expert-agent.md)
specifies the target; [Supported Surface](../SUPPORTED_SURFACE.md) says what runs.

An invocation remains bounded by explicit authority and resource ceilings.
An episode may span invocations and retain working state. Resumption revalidates
authority, uses durable observations, and retains cumulative usage. It does not
reset the budget, repeat uncertain side effects, or silently replace the
evidence snapshot. A checkpoint records work, not admitted truth.

The earlier single knowledge transaction remains a useful fast path for simple
questions. It is no longer the definition of every expert interaction. Keeping
an episode across calls is compatible with acting as a specialist role.

## Who owns what

| Concern | Owner and boundary |
| --- | --- |
| Research intent, subquestions, evidence inspection, hypothesis comparison | Deepr's bounded domain session; model judgment chooses useful admitted steps. |
| Episode state, observations, progress and recovery | Existing investigation/runtime owners, with compatibility work before extension. |
| Canonical knowledge, perspective, history, reviewed procedures | Deepr's owning stores and admission service. Consultation stages; admission applies. |
| Personality and relationship preferences | Scoped profile/identity authority, separate from factual conclusions and permissions. |
| General business workflow, organization, cross-project task graph | External host, such as a human workflow or qualified team orchestrator. |
| Scheduling and unattended wakeups | Host triggers; Deepr validates each operation. Broader autonomy remains S5-gated. |
| Arbitrary code execution, computer/browser work, external writes | Separately authorized host/adapter. Proposing an experiment is not execution permission. |
| Capability and spending enforcement | Existing shared boundaries, irrespective of the calling host. |

Research teams inside a bounded investigation remain in scope when they inherit
parent limits, cancellation, evidence contracts, and separate write admission.
This does not require a supervisor for every query or make a fleet the first
delivery unit. Correlated agreement is not independent support.

## Recovery and composition

Expose partial, waiting, failed, and completed outcomes; do not disguise missing
evidence as a complete answer. A caller can inspect a checkpoint or continue
under current authority. Portable expert identity is independent of a host's
conversation handle. CLI and MCP share the service.

Host messages, tool outputs, edited wikis, and saved skills cannot bypass
admission. Imported observations retain executor/source identity and limits.
Failed and cancelled attempts remain visible. Existing skill execution and
production plan adapters remain blocked as documented.

## Delivery rule

A behavior can belong in Deepr across calls when it serves a named domain
episode, has finite cumulative bounds, owns recoverable state, and respects
side-effect and memory gates. Managing unrelated business tasks or external
resources belongs to the host. Domain responsibility and authority define the
boundary; persistence alone does not.

[ROADMAP](../../ROADMAP.md#persistent-expert-agent-delivery) sequences delivery
through S1-S4. [AGENTIC_BALANCE](../plans/AGENTIC_BALANCE.md) keeps semantic
judgment with models/reviewers and enforcement with code.
