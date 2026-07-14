# Metered Expert Chat Re-enable Review

Status: design note, 2026-07-14.

Scope: deliberate flip of ``METERED_EXPERT_CHAT_EXECUTION_ENABLED`` from
``False`` to ``True``, still behind ``DEEPR_ALLOW_METERED_EXPERT_CHAT=1``.

## Purpose

Live metered expert chat is intentionally fail-closed. Durable admission
substrate for complete, stream, research, embed, and allowlisted skill-tool
paths is largely present. Re-enable is a *review and evidence* problem, not a
boolean flip. This note is the checklist that must clear before the flag moves.

## Dual confirmation (non-negotiable)

1. Code flag: ``METERED_EXPERT_CHAT_EXECUTION_ENABLED``
2. Operator env: ``DEEPR_ALLOW_METERED_EXPERT_CHAT`` in ``{1,true,yes,on}``

Missing either signal refuses dispatch before provider construction (or before
embed/skill-tool side effects that share the same gate). Local Ollama and
explicit plan-quota backends never require either signal.

## Path inventory

Each row must prove: estimate, reserve, dispatch mark, settle or conservative
full-bound, canonical ledger write, no double session ledger, and unit
regression coverage.

| Path | Module | Durable helper | Gate | Status |
| --- | --- | --- | --- | --- |
| OpenAI complete | `chat_backends` | `execute_metered_chat_provider_call` | `require_expert_chat_dispatch` | substrate ready |
| OpenAI stream | `chat_backends` | `execute_metered_chat_provider_stream` | same | substrate ready |
| Anthropic complete/stream | `chat_backends` | same | same | substrate ready |
| Quick lookup / follow-up / compact | chat turns | same complete helper + ceiling | same | substrate ready |
| Grok standard research | `chat_research_ops` | complete helper | metered=True | substrate ready |
| Deep research submit | `chat_research_ops` | complete helper | metered=True | substrate ready |
| Deep research final usage | `chat_research_ops.reconcile_deep_research_job` | idempotent ledger observe + session delta | N/A (post-dispatch recon) | substrate ready |
| Embed document / query | `embedding_cache` | complete helper | metered=True | substrate ready |
| Skill tools (paid tier) | `skills.executor` | `execute_reserved_fixed_cost_async_call` | `allow_metered_tools` | substrate ready when allowlisted; chat keeps False |
| Session spend UX | `chat_metered.mirror_chat_session_spend` | no second ledger write | N/A | substrate ready |

## Re-enable criteria

Before flipping ``METERED_EXPERT_CHAT_EXECUTION_ENABLED``:

1. **Inventory complete.** No metered chat side path reaches a provider SDK
   without the dual gate. Grep for ``embeddings.create``, ``chat.completions``,
   ``messages.create``, ``responses.create``, and skill MCP spawn under
   `experts/` and confirm each either is owned-capacity or gated.
2. **Double-count audit.** Sample complete, stream, research, embed, and
   skill-tool success paths: exactly one canonical ledger event per settled
   job id; session totals move only via mirror helpers where applicable.
3. **Failure matrix.** Cancellation, mark failure, missing usage, soft tool
   error, hard raise, and ledger write failure all leave no open hold and no
   silent money path (unit coverage required for each class).
4. **Ceiling binding.** Multi-call tool loops pass
   ``min(estimate, session_remaining)``; output token caps derive from the hold
   when caller omits ``max_tokens``.
5. **Operator story.** Docs and CLI/web errors mention both signals and the
   safe alternatives (local / plan). No marketing language that claims live
   metered chat works without the env.
6. **Explicit review commit.** The flip is a one-line change with a dated
   ROADMAP note and CHANGELOG entry that points at this checklist. Do not
   bundle unrelated work into the flip commit.

## Out of scope for this flag

- Lifecycle surfaces under ``METERED_EXPERT_MUTATIONS_ENABLED`` (make, refresh,
  reflect, fill-gaps, portraits, etc.) - separate P1.
- Multi-call research parent envelopes (campaign, auto-batch, hosted files).
- Legacy direct metered interfaces (`check`, `make docs`, agentic research).

## Default decision

Leave the flag **false** until every inventory row is green and a human
maintainer signs the review in the flip commit message body (no AI
attribution). The env confirmation alone is not enough to ship spend.
