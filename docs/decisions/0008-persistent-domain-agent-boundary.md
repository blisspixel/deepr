# ADR 0008: Persistent domain agents with bounded research episodes

Status: Accepted as architectural direction, 2026-10-29. Runtime delivery and
promotion remain gated by ROADMAP S1-S4; this decision enables no execution.

## Context

The expert product requires continuity of knowledge, experience, methods,
perspective, and work. A single synchronous knowledge transaction is a useful
invocation boundary, but an inadequate definition of the expert's lifetime.
Existing investigations already persist artifacts and distinguish research,
checking, synthesis, and separately admitted learning. The local learning trial
completed those kinds of operations under supervision but failed subsequent
evidence use. Neither more storage nor another orchestration platform alone
establishes the missing behavior.

## Decision

Deepr owns persistent domain expertise and may own a resumable, bounded research
episode over that expertise. Each invocation has explicit authority, finite
resources, durable observations, and a recoverable terminal or waiting state.
Resuming does not renew its cumulative budget or replay an uncertain action.
Conversation continuity, episode progress, and admitted expert memory are
different records with different write rules.

The model may choose admitted knowledge tools, inquiry, and candidate revisions.
The runtime enforces form, identity, capacity, resource bounds, and writes.
Canonical factual, perspective, procedural, and identity updates retain their
own admission requirements. An episode checkpoint is not knowledge admission.

The host owns general business workflows, scheduling triggers, external
workspaces, and external actions. Deepr may request a bounded experiment and
consume its attributed result. Arbitrary shell, browser, remote-control, or
skill execution is not granted by this decision. Existing blocked paths stay
blocked. CLI and MCP must share the same domain service and authority.

## Alternatives and consequences

- Retaining a strictly synchronous expert definition would leave investigation
  continuity to glue scripts and make reviewed learning difficult to resume.
- Building a general team/company orchestrator would duplicate host concerns.
  Paperclip is a useful external-host reference, not the expert memory owner.
- Adopting Pi or Hermes wholesale would introduce another execution and memory
  authority before a demonstrated integration need. Adapt their patterns first.
- Moving all state to a new graph/event database would increase migration risk
  before the existing history and evidence-use defects are repaired. Strengthen
  temporal query semantics through existing stores first.
- Treating all transcripts or model-generated skills as trusted memory would
  allow mistakes to become persistent behavior. Capture observations promptly;
  admit interpretations and procedures separately.

The cost of this choice is an explicit episode lifecycle and context contract.
The benefit is a coherent expert workflow without requiring a general agent OS.
It supersedes the synchronous-only design restriction, not earlier validation
results or provider, permission, and storage contracts.

## Delivery

[Persistent expert design](../design/persistent-expert-agent.md) defines the
memory and runtime contracts. [ROADMAP](../../ROADMAP.md#persistent-expert-agent-delivery)
owns active work; [living expertise](../plans/living-expertise.md) owns promotion
gates. No new command or schema is public merely because this ADR is accepted.
