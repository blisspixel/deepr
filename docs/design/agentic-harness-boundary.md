# The agentic-harness boundary: agentic within a knowledge transaction, not across the task lifecycle

Status: design note, 2026-06-21. Dogfood-sourced - this framing came from
consulting Deepr's own experts (AI Agent Harnesses, Model Context Protocol,
Distributed Systems Reliability), which converged independently. Sharpens the
ROADMAP "not the orchestrator" non-goal. Read with
[AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) and
[expert-library.md](expert-library.md).

## The tension

Deepr is a callable knowledge role (experts consulted via MCP/A2A), with an
explicit non-goal: it is **not** a workflow orchestrator. Yet internally it runs
real agentic loops - tree-of-thoughts reasoning, bounded expert councils,
verification-gated absorb, autonomous sync. So *is* Deepr an "agentic harness"?
The honest answer is **yes, but only within a bounded scope** - and naming that
scope precisely is what keeps Deepr adaptive and "just works" without drifting
into the orchestrator role it rejects.

## The line: the "knowledge transaction"

Deepr may be fully agentic **inside a single, synchronous knowledge transaction**
(a "knowledge RPC"): one invocation that

- autonomously decomposes the query, consults/coordinates its own experts,
  reasons, and verifies/critiques - "micro-orchestration that is strictly
  epistemic";
- runs under **hard budgets** (time / tokens / iterations / council fan-out) with
  an auditable trace;
- has a **single commit point** - it either absorbs the result into its own
  knowledge store (through the verification gate) or it does not; and
- is **idempotent from the caller's perspective** - safe to retry, no partial
  external side effects.

It returns **one calibrated artifact**: `{answer, confidence, citations,
contradictions/dissent, missing_info, suggested_next_actions, verification_status}`.

## What stays outside the line (the external harness owns it)

Deepr must **not**:

- own multi-step **workflow state** or execute "do X then Y" plans across calls;
- run **durable cross-call** retries, scheduling, or task progression over
  minutes/hours on behalf of a user/business workflow;
- make **side-effecting** external tool calls beyond read-only retrieval and
  writing its **own** knowledge store (no repo edits, ticket creation, UI driving,
  arbitrary downstream services);
- coordinate **other vendors' agents** or own the outer task graph.

Those belong to the calling harness (Claude Code, Cursor, an autopilot). Deepr
produces the calibrated knowledge and *recommends* next actions; the harness
*decides and enacts*.

## Reconciling the roadmap

- **Internal loops (council, ToT, absorb, reflection)** are in-bounds: they are
  epistemic micro-orchestration inside one transaction. Adaptive/defensive
  behavior (degrade honestly, fall through to a working path) is *required*, not
  orchestration.
- **The fleet autopilot / campaigns** are the edge case: they run over time. They
  stay in-bounds only because they coordinate Deepr's **own knowledge
  maintenance** (sync/absorb of its own experts), are host-triggered ("hosts own
  the schedule, Deepr owns the verbs"), idempotent, and budget-bounded - never
  driving external tools or other agents. If a campaign ever reached outside
  Deepr's own knowledge store, it would cross the line.
- **Native consultation** (`deepr expert consult` + an MCP `consult_experts`
  tool, planned) is the canonical knowledge transaction: it should expose exactly
  the calibrated artifact above so any harness can call it.

## The test

For any proposed agentic behavior, ask: *does it complete within one bounded,
idempotent, single-commit knowledge transaction, with no external side effects
beyond Deepr's own knowledge store?* If yes, it is in-bounds agentic. If it owns
workflow state, schedules/retries across calls, or enacts external side effects,
it belongs to the harness - Deepr recommends, the harness enacts.
