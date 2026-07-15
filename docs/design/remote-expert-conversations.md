# Remote expert conversations

Status: accepted design, 2026-07-15. Implementation is planned. The shipped
remote MCP consult and query tools remain one-shot.

Cross-cuts expert consult, consult lifecycle, consult traces, MCP HTTP, scoped
keys, A2A, capacity, and runtime storage. Read
[AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md),
[bounded-expert-deliberation.md](bounded-expert-deliberation.md), and
[ADR 0005](../decisions/0005-protocol-neutral-expert-conversation-handles.md)
before implementation.

## Executive decision

Deepr should add a durable application-level expert conversation, exposed
through explicit opaque handles. It should not treat an MCP transport session,
an in-memory `ExpertChatSession`, or an A2A task id as the conversation.

The first usable slice is:

1. a protocol-neutral conversation store and service;
2. one active turn per conversation, with restart recovery, idempotency, and
   nested capacity ceilings;
3. frozen expert context, bounded recent turns, and a derived decision ledger;
4. local Ollama only, with no metered fallback and no expert-memory writes;
5. four MCP tools for start, continue, inspect, and close;
6. a local and authenticated LAN acceptance command that compares the session
   with the existing one-shot baseline.

A2A follows only after the current custom task substrate is migrated to the
official A2A 1.0 contract and made durable. Structured expert-to-expert
deliberation follows only after its separate evaluator shows a real quality
gain. One-shot consult remains the simple default.

## Why this is the right part of specialist-agent composition

The useful part of the domain-specific-agent argument already fits Deepr:

- experts have bounded domains and persistent state;
- a host agent chooses when to consult them;
- each expert exposes a smaller knowledge boundary than a general agent with
  every tool and instruction loaded;
- scoped keys and expert allowlists can limit authority;
- separate consultations can run in parallel when the host needs them;
- local and plan capacity can be selected explicitly for a narrow task.

The argument does not justify turning every expert into an autonomous agentic
loop or automatically fanning every question out to a panel. More agents add
coordination calls, correlated errors, conflict resolution, latency, and a
harder evaluation surface. Claims such as 80 percent token savings or reliable
small-model substitution are hypotheses Deepr must measure on its own tasks,
not product promises.

The product direction is therefore composition at a typed service boundary:
the host remains the orchestrator, Deepr remains the knowledge role, and an
expert conversation remains proposal-only.

## Research basis

### Protocol direction

The official [MCP 2026-07-28 release candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
makes the protocol core stateless, removes the protocol session and
`Mcp-Session-Id`, and recommends explicit application handles passed as normal
tool arguments. The final specification is scheduled for 2026-07-28, so Deepr
must treat the release candidate as a migration target until it is final. The
architecture should not depend on either the old or new transport session.

The official [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
uses an OAuth resource-server model, protected-resource metadata, audience
binding, per-request authorization, and least-privilege scopes. The official
[MCP security guidance](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
also calls out confused-deputy, token-passthrough, SSRF, DNS-rebinding, origin,
and local-server risks. Existing scoped API keys are a reasonable LAN pilot,
but OAuth/OIDC remains required before broad hosted claims.

The official [A2A specification](https://github.com/a2aproject/A2A/blob/main/docs/specification.md)
defines `contextId` as the opaque grouping handle for related tasks and
messages. A task is one stateful unit of work. A client can start a new task in
an existing context, or continue a task that is `input-required`. The
[A2A 1.0 changes](https://a2a-protocol.org/latest/whats-new-v1/) include breaking
operation and data-model changes. Deepr's current `/tasks` model is useful
prototype code, but it is not the contract on which to launch a public A2A
listener.

### How strong expert consultation works

Structured expert elicitation is more disciplined than asking several experts
to discuss until they sound aligned:

- EFSA's [expert knowledge elicitation guidance](https://www.efsa.europa.eu/en/methodology/evidence)
  emphasizes problem framing, expert selection, uncertainty elicitation,
  aggregation, and complete documentation when empirical evidence is limited.
- The [IDEA protocol](https://research.monash.edu/en/publications/investigate-discuss-estimate-aggregate-for-structured-expert-judg/)
  uses independent investigation and initial judgment, structured discussion,
  private revision, and transparent aggregation. Its
  [practical guide](https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.12857)
  is explicit that discussion is for sharing evidence and resolving ambiguity,
  not forcing consensus.
- The CIA's [structured analytic techniques primer](https://www.cia.gov/resources/csi/static/955180a45afe3f5013772c313b16face/Tradecraft-Primer-apr09.pdf)
  recommends making key assumptions explicit, challenging why they must hold,
  and recording what evidence would cause revision.

These practices support structured independence, uncertainty, dissent, and
revision. They do not support majority vote, hidden model confidence as truth,
or performance weighting without task-specific calibration evidence.

### Agent-runtime lessons

The [OpenAI Agents SDK session guidance](https://openai.github.io/openai-agents-python/sessions/)
uses explicit session ids for persisted history, and its
[tracing guidance](https://openai.github.io/openai-agents-python/tracing/)
separates a trace for one run from a grouping id for a conversation. Anthropic's
[multi-agent research system report](https://www.anthropic.com/engineering/multi-agent-research-system)
supports orchestrator-worker separation and artifact references, but also
reports that coordination and asynchronous state introduce their own failure
modes. Deepr should adopt explicit grouping, clean context boundaries, and
artifact lineage without assuming multi-agent execution is automatically
better.

## Current Deepr truth

What works now:

- MCP stdio and experimental HTTP can list experts, inspect handoffs and state,
  and run one-shot `deepr_query_expert` or `deepr_consult_experts` calls.
- Scoped HTTP keys enforce mode, expert allowlist, budget, rate limit, and
  append-only remote audit behavior.
- Local and explicit plan query and consult paths disable metered fallback.
- Consults have durable lifecycle events and final traces with capacity, cost,
  context-selection, and collaboration lineage.
- `deepr-consult-v1` preserves roster, evidence metadata, agreements, dissent,
  cost, capacity, and host action boundaries.
- The A2A package has an Agent Card generator, an in-memory task manager, an
  HTTP server class, consult-task mapping, and offline or remote host
  validation.

What does not work yet:

- MCP query and consult have no durable conversation handle.
- The legacy MCP API chat path creates an in-memory session keyed from one
  question and removes it after the call. It is not continuation.
- Saved `ExpertChatSession` JSON is a user-facing chat export, not a
  cross-process transactional service store.
- The A2A task manager is process-local and bounded in memory. Restart loses
  tasks.
- There is no shipped `deepr a2a serve` command.
- The current A2A data model predates the official 1.0 contract.
- Current council participants contribute independently selected packets of
  stored state. They do not make independent question-specific judgments, and
  the synthesis model produces the displayed agreement and disagreement lists.
- `deepr eval deliberation` validates a future bounded round structure, but no
  live multi-round surface is shipped.

## Consulting practice compared with Deepr

| Practice for hard problems | Deepr today | Change that earns its cost |
|---|---|---|
| Frame the decision, scope, stakes, and output need | A free-form question is sufficient | Add an optional decision brief. Do not block ordinary questions. |
| Explain why expert judgment is needed and what evidence already exists | The question and stored state are available | Record supplied evidence, known constraints, and the decision owner in the conversation intake. |
| Select relevant and meaningfully diverse experts | Explicit rosters or a disclosed lexical candidate router | Keep explicit rosters first-class. Treat automatic selection as routing only and expose its basis. |
| Elicit initial judgments independently | Stored perspective packets are selected independently, but are not question-specific judgments | Add a later panel mode with sealed first positions. Do not relabel today's packets as judgments. |
| State assumptions, evidence, uncertainty, and disconfirming conditions | Evidence and confidence metadata exist, but the final answer contract is uneven | Add structured answer fields while leaving their semantic content to the model and evaluator. |
| Discuss to exchange evidence and challenge assumptions, not force consensus | One synthesizer compares stored perspectives | Use targeted challenge only in the evaluated panel mode. Preserve original and revised positions. |
| Revise privately after discussion | Not shipped | Add only after the deliberation evaluator clears live execution. |
| Aggregate transparently and preserve dissent | Agreements and disagreements are returned, but synthesized by one model | Label provenance and method. Never treat majority or self-reported confidence as truth. |
| Track outcomes and calibration | Consult trace review exists; task-specific expert performance weighting does not | Add outcome-linked eval cases before any expert weighting or routing promotion. |
| Stop when the decision is supported or a real evidence gap is reached | One-shot calls end; future loops have typed-stop design | Give every turn and conversation explicit capacity and semantic stop reasons. |

## Goals

1. Let an agent on this machine or a trusted LAN host ask follow-up questions
   against the same bounded expert context.
2. Survive process restarts without replaying completed model work.
3. Make every turn independently authenticated, authorized, budgeted, traced,
   cancellable, and idempotent.
4. Keep context growth bounded and measurable.
5. Preserve exact prior artifacts and dissent when compaction occurs.
6. Keep the conversation separate from canonical expert memory.
7. Map one core cleanly to MCP explicit handles and A2A `contextId`.
8. Measure whether continuation improves answer quality or efficiency over
   repeated one-shot calls.

## Non-goals

- Deepr does not become the global orchestrator.
- A conversation does not grant research, tool, write, or spend authority.
- A transcript does not become a belief, graph edge, skill, or expert profile.
- The first slice does not use metered APIs or automatic fallback.
- The first slice does not run autonomous expert-to-expert debate.
- The first slice does not dynamically add experts, change backend class, or
  widen authority inside an existing conversation.
- MCP transport ids and A2A task ids do not authorize access.
- Natural language is not the only integration contract. Every public result
  has a versioned structured envelope.

## Architecture

```text
Host agent
  -> MCP tool or A2A message adapter
  -> authentication and conversation ownership gate
  -> protocol-neutral ExpertConversationService
  -> durable conversation store and per-conversation turn lease
  -> bounded context builder
  -> existing one-shot consult/query execution seams
  -> versioned answer artifact, trace, usage, and typed stop
```

The adapters translate protocol shapes only. They do not own model history,
expert selection, budget arithmetic, or lifecycle state.

### Conversation identity

`conversation_id` is a server-generated opaque value with at least 128 bits of
randomness. It is a locator, never a credential. The first remote slice binds
it to the creating scoped-key `key_id`. A later OAuth implementation binds it
to the validated subject, resource audience, and tenant or workspace.

The conversation pins:

- owner identity and authorization mode;
- canonical expert names and order;
- a frozen context snapshot id and per-expert snapshot hash;
- consultation mode and answer-contract version;
- backend class, model selection, and no-fallback posture;
- total turn, model-call, input-token, output-token, elapsed-time, and dollar
  ceilings;
- retention policy and expiry;
- prompt, schema, and context-builder versions.

Changing the roster, authority, backend class, or frozen snapshot creates an
explicit fork with lineage. It never mutates the original conversation in
place.

### Conversation state

Conversation states:

- `open`: accepts a new turn;
- `input_required`: the last turn needs caller clarification and accepts only a
  matching continuation;
- `waiting_capacity`: resumable when the selected local or plan capacity is
  available;
- `closed`: normal terminal state;
- `expired`: retention or idle ceiling reached;
- `cancelled`: operator or owner terminated it;
- `failed`: durable state cannot safely continue.

Turn states:

- `accepted`;
- `running`;
- `input_required`;
- `waiting_capacity`;
- `completed`;
- `cancelled`;
- `budget_exhausted`;
- `verifier_failed`;
- `failed`.

Only `input_required` and `waiting_capacity` are resumable without starting a
new logical turn. A completed idempotency key returns the recorded result. It
does not dispatch again.

### Durable records

The smallest robust local store is one SQLite database under the configured
runtime root, using WAL mode, foreign keys, explicit transactions, and bounded
busy timeouts. It contains:

- an append-only conversation event table as lifecycle authority;
- a rebuildable conversation projection;
- immutable turn rows and result artifact references;
- immutable frozen expert-context snapshots;
- idempotency keys unique within owner and conversation;
- a per-conversation version used for optimistic concurrency;
- content records with retention and deletion state.

The append-only audit event retains hashes, ids, state changes, capacity, and
lineage. Raw user and model content is separate so retention or deletion can
remove content while preserving a minimal non-sensitive audit skeleton. The
default server policy must be finite and visible. The implementation design
must choose and test the exact default before shipping; no transcript is
silently permanent.

This operational database belongs under `runtime_data_path(...)`, not inside
one expert's canonical directory. A multi-expert conversation is not expert
knowledge and must not become portable authority merely because an expert was
consulted.

### Serialization and idempotency

Only one turn may execute for a conversation at a time. Different
conversations may run concurrently within existing global backpressure limits.

Every start or continue request includes a caller-generated `idempotency_key`
and, after creation, `expected_version`:

- first receipt atomically records the request before backend construction;
- a duplicate completed request returns the same result;
- a duplicate running request returns current status and does not dispatch;
- a reused key with different input fails;
- a stale version returns a typed conflict;
- an abandoned running attempt becomes `interrupted` only through explicit
  recovery evidence, then may resume under the same turn id and a new attempt
  id.

The existing consult lifecycle journal remains the provider-work lifecycle for
each executing turn. The conversation store groups those turn traces and adds
ownership, ordering, and continuation state. It does not replace the canonical
cost ledger or consult trace.

## Context contract

The core must not replay an ever-growing raw transcript on every turn.

### Frozen expert context

Start creates `deepr-expert-context-snapshot-v1` for each pinned expert. A
snapshot contains a bounded structured packet and exact hashes or event
positions for the state used. Later turns retrieve only from that frozen
packet. This keeps follow-ups coherent and replayable even if the live expert
learns something new.

Fresh expert state requires an explicit fork or refresh operation that records
old and new snapshot ids. A model may propose that fresh evidence is needed,
but deterministic code must not infer semantic staleness from keyword overlap.

### Turn context

Each turn receives, within hard ceilings:

1. the original decision brief;
2. pinned expert snapshot excerpts selected for this turn;
3. a bounded number of recent exact turns;
4. exact prior artifact references explicitly named by the caller or context
   builder;
5. a derived decision ledger with source turn ids;
6. current remaining capacity and applicable stop rules.

The decision ledger is a derived view with fields such as assumptions,
evidence references, open questions, preserved dissent, proposed decisions,
and host-confirmed decisions. Every entry links to exact source turns. A model
may propose ledger updates, but schema validation only checks form. A proposed
decision does not become host-confirmed without an explicit host action.

Compaction is a counted model call when a model performs it. It cannot erase
the exact artifacts, original positions, or dissent that future turns cite.
Context selection records ids and hashes so the answer can be replayed and
evaluated.

## Consultation tiers

The service should expose progressively stronger modes rather than one
unbounded agent swarm:

1. `focused`: one expert, one turn. Existing query semantics.
2. `council`: one or more stored expert snapshots, one synthesis turn. Existing
   consult semantics and the initial conversation default.
3. `structured_panel`: independent question-specific first positions,
   targeted challenge, private revision, and transparent synthesis. Planned
   only after the deliberation evaluator passes.
4. `deep`: panel participants may propose bounded research or learning work.
   Planned only after verification, parent-budget, and write gates exist.

The service should select the lowest tier that the caller explicitly requests.
It must not infer high stakes or escalate autonomy using lexical rules.

## Answer contract

`deepr-expert-conversation-turn-v1` should contain:

- direct answer;
- consultation mode and experts consulted;
- assumptions, including which are host-supplied or model-proposed;
- evidence and expert-state references actually used;
- calibrated uncertainty or intervals where the question supports them;
- agreements and preserved dissent with provenance;
- decision implications, clearly labeled as proposals;
- what evidence or observation would change the judgment;
- unresolved gaps and recommended next question;
- semantic status such as `answered`, `input_required`, or
  `evidence_required`, supplied by the model and labeled as model judgment;
- deterministic lifecycle stop reason;
- per-turn and remaining conversation capacity;
- conversation id, turn id, trace id, version, snapshot id, and artifact hash;
- host-action boundary stating that Deepr did not enact downstream work.

Schema checks validate presence, types, bounds, ids, and references. They do not
decide whether an assumption is important, evidence supports a claim, experts
truly agree, uncertainty is calibrated, or the answer is good.

## MCP surface

Add new tools instead of adding an optional session argument to the existing
one-shot tools:

- `deepr_start_expert_conversation`
- `deepr_continue_expert_conversation`
- `deepr_get_expert_conversation`
- `deepr_close_expert_conversation`

An explicit later `deepr_fork_expert_conversation` is preferable to hidden
in-place roster or snapshot changes.

Start accepts the first question, optional decision brief, explicit or routed
roster, mode, local model or explicit plan backend, hard ceilings,
idempotency key, and retention choice. Continue accepts the opaque handle,
expected version, idempotency key, and one caller message. Get returns bounded
status and artifact metadata, with transcript content behind the same sensitive
read gate. Close records a terminal event and applies the retention policy.

The handle is an ordinary tool argument. It must not use `Mcp-Session-Id` or
assume sticky routing. W3C trace context from MCP metadata should link the host
span to each Deepr turn trace without storing raw prompts in telemetry.

## A2A mapping

After A2A 1.0 conformance work:

| Deepr core | A2A 1.0 |
|---|---|
| `conversation_id` | server-generated opaque `contextId` |
| one consultation turn | one new Task in the same context |
| turn needs clarification | Task state `input-required` |
| `turn_id` and trace | Task id plus Deepr artifact lineage |
| answer and evidence packet | Task artifact |
| idempotency key | Message id plus Deepr request hash |
| close or expiry | Deepr context lifecycle, documented in Agent Card |

The adapter must reject mismatching context and task ids, authorize every
request against the caller, and ensure task reads are caller-scoped. Polling is
the first delivery mode. Streaming follows only after durable event replay and
disconnect recovery pass. Push notifications are later because they add SSRF,
callback authentication, and retry state.

## Security and privacy

The first LAN release requires:

- loopback by default;
- a scoped key for every non-loopback request;
- TLS through a documented reverse proxy outside a trusted isolated LAN;
- per-request authentication and current-scope revalidation;
- conversation ownership bound to key id;
- expert allowlist intersection checked on every turn;
- nested conversation, key, and global capacity ceilings;
- opaque ids and not-found responses that do not reveal another owner's state;
- no downstream token passthrough;
- origin and host validation appropriate to remote HTTP and DNS-rebinding risk;
- request-body, turn, context, output, and concurrency bounds;
- secret redaction before traces, audits, and errors;
- no raw prompt, answer, chain-of-thought, or secret in default telemetry;
- finite transcript retention, inspect, export, and deletion behavior;
- cancellation that owns child-process cleanup and records ambiguous outcomes;
- no automatic transcript-to-memory path.

OAuth/OIDC with protected-resource metadata, audience-bound tokens, subject and
tenant isolation, PKCE where applicable, and least-privilege scopes is a later
hosted gate. One shared bearer token is not sufficient for hosted multi-user
claims.

## Capacity and cost

The first slice supports local Ollama only. The next explicit slice may support
plan-quota capacity after the existing auth-mode, process-ownership, quota, and
no-surprise-bills gates are reused. Neither slice may fall through to a metered
API.

Every conversation has hard maximums for:

- turns;
- model calls, including compaction and judging;
- input and output tokens;
- elapsed execution time;
- context bytes and stored content;
- concurrent work;
- dollar cost, fixed at zero for the local-only pilot.

Metered APIs remain gated until each call has a durable reservation, dispatch
mark, exact or conservative settlement, canonical cost-ledger idempotency, and
one parent conversation ceiling. A failure never selects a different paid
provider automatically.

A successful live check on this development machine showed that an explicitly
pinned `qwen2.5:14b` local consult can satisfy the current one-shot MCP contract
more responsively than the default 32B model. That is machine-local operational
evidence, not a product default. Model promotion requires the conversation eval
on the target hardware and task set.

## Observability

Use three distinct identifiers:

- `conversation_id` groups all turns;
- `turn_id` identifies one logical caller interaction;
- `trace_id` identifies one execution attempt lineage.

Each turn records status, phase, latency, context size, input and output usage,
capacity posture, selected snapshot and artifact hashes, stop reason, and cost.
OpenTelemetry can use the conversation id as a trace-group attribute while one
turn remains one trace. Sensitive content is opt-in and off by default.

Operational views must answer:

- which conversations are open, waiting, stale, or over retention;
- which turn is active and who owns it;
- what capacity remains;
- whether a retry is a replay or a new dispatch;
- which context and expert snapshots affected an answer;
- whether a key was revoked or its scope narrowed;
- whether cleanup completed.

## Evaluation and promotion gates

Create `deepr eval conversation` before the network tools. It runs frozen
structural cases at `$0` and can optionally run local semantic comparisons.

### Structural suite

The structural suite must pass with no model or network dependency:

- start, continue, inspect, close, expire, cancel, and fork state transitions;
- append-before-dispatch and restart recovery;
- duplicate request replay and changed-input idempotency rejection;
- stale-version and two-writer conflict handling;
- no cross-key or cross-conversation reads;
- key revocation and expert-scope narrowing;
- frozen snapshot and artifact hash integrity;
- bounded context construction and deterministic ceiling stops;
- transcript deletion while audit hashes remain;
- no belief, graph, profile, skill, project, or tool side effects;
- no metered fallback;
- protocol adapter parity for the same core result.

Any security, isolation, spend, replay, or write-boundary failure blocks
promotion. These are zero-tolerance invariants.

### Held-out semantic suite

Compare the conversation path with repeated current one-shot calls using the
same model, expert snapshots, and total capacity. Cases should cover:

- pronoun and reference resolution;
- constraint carry-forward;
- caller correction of an earlier premise;
- evidence and citation follow-up;
- preserved dissent across turns;
- explicit assumptions and disconfirming evidence;
- a topic shift that should request a fork or fresh context;
- adversarial transcript text and prompt-boundary canaries;
- insufficient evidence and honest stopping;
- quantitative uncertainty where appropriate.

Measure blind pairwise preference, task completion, unsupported-claim rate,
evidence-reference validity, dissent retention, constraint retention, latency,
tokens, context growth, and model-call count. Do not use the same judge to
generate and score an answer. Human-reviewed anchor cases calibrate any local or
plan judge.

Before live execution, preregister the case set, model, context ceiling, and
promotion thresholds. Promotion requires no regression in grounding or dissent
retention, a material improvement in follow-up task completion or efficiency,
and bounded context growth. Do not claim a token-efficiency percentage or
smaller-model parity until this report demonstrates it.

### Consulting-quality suite

The later `structured_panel` mode has an additional gate:

- first positions are produced without seeing other positions;
- discussion questions cite the position they challenge;
- original positions remain immutable;
- revisions are private until all are complete;
- synthesis distinguishes original, revised, and unresolved positions;
- aggregation method is explicit;
- self-reported confidence does not create hidden expert weights;
- performance weighting is disabled until held-out, task-specific outcome
  evidence exists.

The existing `deepr eval deliberation` remains the structural precursor for
this mode. It is not a prerequisite for basic host-to-expert continuation.

## Delivery plan

### Stage 0: contract and evaluator

- Publish this design and ADR 0005.
- Add versioned JSON Schemas for conversation, turn, event, context snapshot,
  and error envelopes.
- Add `deepr eval conversation` frozen structural fixtures and a one-shot
  comparison manifest.
- Fix capability docs so one-shot MCP and library-only A2A are not described as
  durable conversation services.

Exit: schemas and evaluator fixtures can express every invariant before a live
model is called.

### Stage 1: protocol-neutral local core

- Add a named conversation service and SQLite store under the runtime root.
- Reuse consult lifecycle and trace seams per turn.
- Implement ownership, idempotency, optimistic concurrency, retention,
  deletion, and frozen snapshots.
- Use an injected fake turn executor for exhaustive unit and property tests.
- Rebuild the codegraph before choosing module boundaries and run the
  fragmentation scan. Extract only named seams, not files created to satisfy a
  size metric.

Exit: restart, replay, concurrency, isolation, and cleanup pass without a model.

### Stage 2: local MCP conversation

- Implement start, continue, get, and close tools on the shared core.
- Add local Ollama execution with no metered fallback.
- Add `deepr mcp validate-conversation` for loopback and authenticated HTTP.
- Validate on this machine and one separate LAN client, including restart,
  duplicate delivery, token redaction, key revocation, and expiry.
- Run the held-out comparison before calling the surface usable.

Exit: an external agent can safely continue a conversation through MCP, and
the eval shows why continuation is better than repeating one-shot calls.

### Stage 3: explicit plan capacity

- Reuse the plan-quota auth-mode and process-tree ownership gates.
- Bind all plan calls to conversation ceilings and per-turn lifecycle records.
- Add plan transport cases to the live validator.

Exit: selected plan capacity works with `$0` Deepr cost, honest unknown vendor
quota accounting, and no metered fallback.

### Stage 4: A2A 1.0 service

- Replace or version the custom A2A model against official A2A 1.0 operations,
  states, Agent Card, media types, and security fields.
- Back tasks and contexts with durable protocol-neutral state.
- Map `contextId` to conversation id and one task to one turn.
- Ship `deepr a2a serve` only after conformance, caller-scoped authorization,
  restart recovery, and polling pass.
- Add streaming after event replay works. Defer push notifications.

Exit: a separate A2A 1.0 client passes discovery, auth, multi-turn, restart,
cancel, and artifact validation against a real listener.

### Stage 5: hosted authorization and registration

- Add OAuth/OIDC protected-resource metadata and subject or tenant isolation.
- Complete TLS, origin, host, and reverse-proxy hardening.
- Validate registration and multi-turn use from a real third-party host.

Exit: hosted claims are based on a live external registration, not a local
fixture.

### Stage 6: structured panel

- Reuse bounded-deliberation artifacts for independent first positions,
  targeted challenge, private revision, and synthesis.
- Run the consulting-quality suite against the council one-shot baseline.
- Promote only if quality improves within the same total capacity envelope.

Exit: panel mode has measured value and preserves dissent. Until then, it stays
an evaluator-only design.

### Stage 7: metered capacity and deep work

- Complete the parent conversation reservation and exact per-call settlement
  contract.
- Keep research, tools, and expert-memory writes separately authorized.
- Admit deep fan-out only through loop verification and explicit capacity.

Exit: every possible paid or side-effecting call is reserved, bounded, settled,
and attributable before the surface widens.

## Rejected alternatives

- **Use the MCP transport session as conversation state.** Rejected because the
  incoming MCP protocol is stateless and application state must survive
  transport changes and load balancing.
- **Reuse the current in-memory MCP `sessions` dictionary.** Rejected because it
  is process-local, question-keyed, API-chat-specific, and intentionally
  discarded after one request.
- **Treat saved chat JSON as the service database.** Rejected because it lacks
  transactional concurrency, ownership, idempotency, and restart semantics.
- **Add optional `session_id` to existing one-shot tools.** Rejected for the
  first slice because it makes one contract serve two lifecycle models and
  encourages accidental state. New tools keep compatibility and authorization
  clearer.
- **Let MCP and A2A maintain separate histories.** Rejected because behavior,
  budgets, retention, and security would drift.
- **Use A2A task id as the conversation.** Rejected because A2A distinguishes a
  context from a task, and one conversation can contain several tasks.
- **Always send the full transcript.** Rejected because cost and distraction
  grow without bound and deletion or compaction becomes unsafe.
- **Automatically write good conversation content into expert memory.**
  Rejected because model output is untrusted proposal text until the normal
  evidence, verifier, and graph-commit gates accept it.
- **Default every question to a multi-agent panel.** Rejected because
  coordination cost and correlated errors are not justified without a measured
  gain.
- **Use majority vote or confidence-weighted consensus.** Rejected because
  agreement is not truth and self-reported confidence is not calibration.
- **Launch the current A2A server class as public protocol support.** Rejected
  because its task store is in memory and its contract predates A2A 1.0.

## Open implementation decisions

These must be resolved in Stage 0 or Stage 1, before a public tool schema is
frozen:

- exact default transcript retention and maximum operator override;
- whether content deletion is immediate or uses a short recoverable grace
  period;
- bounded recent-turn count and context-byte defaults;
- initial local model admission threshold on supported hardware;
- whether a fork is in the first public schema or follows start and continue;
- how OAuth subject continuity works when a scoped key is rotated.

None of these questions changes the accepted protocol-neutral handle decision.
