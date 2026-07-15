# 0005. Protocol-neutral handles for expert conversations

- Status: Accepted
- Date: 2026-07-15

## Context

Deepr's MCP query and consult tools are one-shot. A remote agent needs an
explicit way to ask a follow-up against the same bounded expert context, with
restart recovery, ownership, idempotency, retention, and one capacity ceiling.

The current MCP server has an in-memory legacy chat-session dictionary, and the
current A2A prototype has an in-memory task manager. Neither is a durable
cross-protocol conversation store. The MCP `2026-07-28` release candidate also
removes transport-level sessions and recommends ordinary application handles.
A2A 1.0 separately defines `contextId` as the grouping id across tasks and
messages.

## Decision

Deepr will represent a remote expert conversation with a server-generated,
opaque, protocol-neutral `conversation_id` owned by the application core.

- MCP passes it as a normal tool argument. It is never coupled to
  `Mcp-Session-Id` or sticky transport state.
- A2A maps it to a server-generated `contextId`; one consultation turn maps to
  one task.
- The durable core owns authentication binding, roster and frozen-context
  lineage, versioning, idempotency, retention, turn ordering, capacity, and
  typed stops.
- One-shot query and consult contracts remain unchanged.
- Conversation content is operational state, not canonical expert memory.
  Transcript content has finite retention and deletion behavior, while a
  minimal append-only audit record can retain ids, hashes, lifecycle, and cost.
- The first execution surface is local-only and cannot fall through to a
  metered API.

Detailed contracts and rollout gates are in
[remote-expert-conversations.md](../design/remote-expert-conversations.md).

## Alternatives considered

- **MCP transport session:** rejected because protocol sessions are disappearing
  and application state must survive reconnection and load balancing.
- **A2A task id:** rejected because A2A distinguishes a conversational context
  from one stateful task.
- **Protocol-specific stores:** rejected because MCP and A2A behavior, security,
  budgets, and retention would drift.
- **Legacy `ExpertChatSession` persistence:** rejected because it is a chat
  implementation and export shape, not a transactional multi-owner service
  contract.
- **Optional session behavior inside the existing one-shot tools:** rejected for
  the initial version because it would mix two lifecycle and authorization
  models in one compatibility contract.

## Consequences

MCP and A2A adapters stay thin and can evolve with their protocols without
moving conversation authority. The core requires a new durable store,
concurrency control, retention policy, and evaluator before the feature is
usable. It also makes the boundary explicit: a conversation can inform a host
or propose future expert learning, but it cannot silently spend, use tools, or
mutate expert state.
