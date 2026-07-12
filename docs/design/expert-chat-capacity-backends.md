# Expert Chat Capacity Backends

Status: design note, refreshed 2026-07-12.

Scope: `deepr expert consult`, `deepr_consult_experts`, `deepr expert chat`,
`deepr_query_expert`, and browser Socket.IO/REST expert chat.

## Purpose

Expert collaboration needs three first-class capacity modes:

1. Local Ollama for true `$0` Deepr dollar cost.
2. Explicit plan-quota CLIs for prepaid or subscription capacity.
3. Paid provider APIs for frontier quality when the operator sets a budget.

These modes must be honest. Local and plan paths may be slower or lower quality,
but they must not fall through to metered APIs. Paid API paths may be stronger,
but every request must estimate, reserve, settle, and append to the canonical
cost ledger.

## Current v2.36 Release Gate

Every standalone metered `ExpertChatSession` dispatch fails closed before the
provider call in v2.36. This includes `deepr expert chat`, browser Socket.IO and
REST chat, and `deepr_query_expert backend=api`. Local and explicit plan
`deepr_query_expert` read-only compiled-context turns remain available. API
council synthesis is a separate bounded surface and is not disabled by this
gate. No metered expert-chat live validation is claimed for v2.36.

Restoration is P1 work. Every provider and auxiliary call must have a durable
estimate, reserve, dispatch mark, and settlement; hard output ceilings; one
parent session budget; and per-session turn serialization. The intended API and
browser contracts below remain design targets and historical implementation
context, not shipped metered capacity in this release.

## Current Code Constraints

- `deepr.experts.consult.build_synthesis_backend` already selects local
  Ollama or explicit plan-quota synthesis for consults and disables live
  metered fallback in those modes.
- `PlanQuotaChatClient` and `ollama_chat_client` already satisfy the narrow
  `client.chat.completions.create(...)` seam used by council synthesis.
- API-backed council synthesis is provider-pluggable for `openai` and
  `anthropic`. The Anthropic path uses the native Messages API and keeps
  prompt-cache controls disabled until explicit cache policy exists.
- `ExpertChatSession` is more coupled than consult. Its constructor requires
  `OPENAI_API_KEY`, stores an `AsyncOpenAI` client, uses the Responses API path
  for retrieval, and routes under an OpenAI provider constraint for vector-store
  compatibility. The primary non-streaming answer-generation chat-completion
  turn, follow-up suggestions, and conversation compaction now go through
  `ExpertChatBackend` with `OpenAIExpertChatBackend`. Quick lookup and the
  standard-research fallback now use the same backend seam while preserving
  their operation-specific budget checks and ledger records. Final OpenAI token
  streaming now uses the backend streaming contract. Deep-research job
  submission still uses the OpenAI Responses API path because it is a
  research-job contract, not one normalized chat turn. `LocalOllamaExpertChatBackend` and
  `PlanQuotaExpertChatBackend` now implement the same normalized backend
  contract for read-only compiled-context turns, declare no tools, no
  streaming, no prompt cache, and no Deepr dollar spend. MCP
  `deepr_query_expert backend=local|plan` selects those adapters for one
  read-only compiled-context turn. `AnthropicExpertChatBackend` now supports
  explicit non-agentic API query chat through the native Anthropic Messages API,
  with native text streaming and final usage settlement. Tools and prompt-cache
  controls remain disabled until those policy gates exist. The shared chat-turn
  helper rejects requested tools before backend dispatch when
  `supports_tools=false` and omits `tool_choice` on no-tool turns.
- MCP `deepr_consult_experts` accepts `synthesis_backend=api|local|plan`.
  MCP `deepr_query_expert` accepts `backend=local|plan` as usable capacity in
  v2.36; `backend=api` is accepted only to return the fail-closed release gate.
  `local` and `plan` compile the expert handoff state into one read-only no-tool chat turn
  through the owned-capacity backend seam, with live metered fallback disabled,
  no research trigger, and a `readonly_chat_artifact` attached to the result.
- `AnthropicProvider` is still a research provider. Expert chat uses the
  narrower native `AnthropicExpertChatBackend` because chat turns and text
  streams need a different request/result/cost contract than research jobs.

## 2026 Provider Findings

The paid API path cannot be a thin OpenAI wrapper.

- Claude Sonnet 5 and Opus 4.8 use Anthropic's Messages API. Official examples
  call `client.messages.create(model="claude-sonnet-5", ...)` or
  `client.messages.create(model="claude-opus-4-8", ...)`.
- Claude Sonnet 5 and Opus 4.8 support adaptive thinking. Manual extended
  thinking with a fixed `budget_tokens` is rejected. Use
  `thinking={"type": "adaptive"}` when thinking is needed.
- Claude Sonnet 5 supports the `effort` parameter. The API default is `high`.
  Deepr can omit it unless a user-facing effort policy is added; any future
  policy must be budget-aware and visible before dispatch.
- Non-default sampling parameters such as `temperature`, `top_p`, and `top_k`
  are rejected on Claude Sonnet 5 and Opus 4.8. The Anthropic adapter must omit
  them instead of passing Deepr's OpenAI-style `temperature=0.3`.
- Opus 4.8 has the 1M context window on Claude API, Amazon Bedrock, and Google
  Cloud. Microsoft Foundry launched it with a 200k context window, so platform
  matters.
- Prompt caching has separate usage buckets:
  `input_tokens`, `cache_creation_input_tokens`, and
  `cache_read_input_tokens`. Cost settlement must price each bucket separately.
- Anthropic prompt caching can be automatic through top-level `cache_control`,
  but it has model/platform minimum prompt lengths, TTL behavior, cache write
  cost, cache read cost, and exact-prefix requirements. Deepr must not enable
  cache controls until TTL, cache-key, pre-warm, cache-miss, privacy, and budget
  estimators are explicit.

References checked 2026-06-30:

- Anthropic Claude API primer:
  https://platform.claude.com/docs/en/claude_api_primer
- Anthropic Claude Sonnet 5 model notes:
  https://platform.claude.com/docs/en/about-claude/models/whats-new-sonnet-5
- Anthropic model migration guide:
  https://platform.claude.com/docs/en/about-claude/models/migration-guide
- Anthropic Claude model overview:
  https://docs.anthropic.com/en/docs/about-claude/models/overview
- Anthropic effort control:
  https://platform.claude.com/docs/en/build-with-claude/effort
- Anthropic pricing:
  https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic Opus 4.8 API migration notes:
  https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-8
- Anthropic prompt caching:
  https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Anthropic Opus 4.8 announcement:
  https://www.anthropic.com/news/claude-opus-4-8

## 2026 Multi-Agent Findings

The expert-chat path should follow the same bounded-collaboration pattern as
consult, not grow into an unbounded swarm.

- Anthropic's production multi-agent research writeup validates the
  orchestrator-worker shape for broad, open-ended research: a lead agent plans,
  delegates to specialists with separate context windows, then consolidates
  results. It also warns that multi-agent systems burn many more tokens than
  chat, so fan-out must be value-gated, observable, and bounded.
- OpenAI's Agents SDK documents two useful patterns: specialists as tools when
  one manager should own the final answer and handoffs when a specialist should
  own the next part of the interaction. Deepr consult maps to specialists as
  tools: Deepr experts contribute bounded perspectives, while the host remains
  the orchestrator.
- MCP's current specification centers tools, resources, prompts, consent,
  authorization, and explicit tool safety. For Deepr that means the protocol
  surface must make cost tier, backend choice, and no-fallback behavior visible
  before another agent can call an expert.
- A2A's current specification centers tasks, messages, artifacts, Agent Cards,
  streaming, push updates, and authenticated agent discovery. Deepr should map
  consult outputs to task artifacts, not opaque chat transcripts, so external
  agents can inspect roster, dissent, capacity, cost, and trace refs.
- The robust pattern is one or many experts, one bounded artifact. A single
  expert consult is just `deepr_consult_experts` with one explicit expert. A
  multi-expert council is the same contract with several experts and preserved
  dissent. `deepr_query_expert` now exposes a bounded read-only query artifact
  for explicit `backend=local|plan`; the default `backend=api` path remains
  legacy chat until the full backend-neutral runner lands.

Additional references checked 2026-06-28:

- Anthropic multi-agent research system:
  https://www.anthropic.com/engineering/built-multi-agent-research-system
- OpenAI Agents SDK orchestration:
  https://openai.github.io/openai-agents-python/multi_agent/
- Model Context Protocol specification:
  https://modelcontextprotocol.io/specification/2025-06-18
- MCP security best practices:
  https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- Agent2Agent protocol specification:
  https://a2a-protocol.org/latest/specification/

## Target Architecture

Add an `ExpertChatBackend` interface for all model calls used by expert consult
and chat:

```python
class ExpertChatBackend(Protocol):
    provider: str
    model: str
    metered: bool
    supports_tools: bool
    supports_streaming: bool
    supports_prompt_cache: bool

    async def complete(self, request: ExpertChatRequest) -> ExpertChatResult:
        ...

    def stream(self, request: ExpertChatRequest) -> AsyncIterator[ExpertChatStreamChunk]:
        ...
```

The request should carry normalized messages, system instructions, max output,
structured-output requirements, optional tools, and optional provider features.
The result should carry text, usage buckets, stop reason, refusal metadata,
cost, provider request id when available, and whether cost was exact or
estimated.

Backends:

- `LocalOllamaExpertChatBackend`: OpenAI-compatible local chat client. Cost is
  always `$0` in Deepr. Tool support starts disabled unless explicitly proven.
- `PlanQuotaExpertChatBackend`: wraps `PlanQuotaChatClient`. Cost is `$0` in
  Deepr, writes quota observations and `$0` ledger events, and never
  auto-routes unless remaining-quota evidence exists.
- `OpenAIExpertBackend`: keeps current OpenAI chat behavior, but moves cost
  settlement and feature declarations behind the common interface.
- `AnthropicExpertBackend`: native Messages API adapter. It omits unsupported
  sampling params for Opus 4.8, supports adaptive thinking with explicit effort,
  handles refusal stop details, and prices regular input, cache writes, cache
  reads, and output tokens separately.

Separate this from expert memory construction:

- `ExpertContextCompiler`: builds bounded context from profile, handoff,
  beliefs, gaps, contradictions, source packs, self-model focus, and loop state.
- `ExpertTurnRunner`: sends the compiled prompt to the selected backend and
  records usage.
- `ExpertActionExecutor`: handles tools, search, research, absorption, and
  skills only when the backend and mode support them.

This split keeps local and plan modes useful even before full tool parity. A
backend that cannot safely run tools can still answer from compiled expert state
and can return a structured "tool not supported on this backend" result instead
of failing brittlely.

## Public Surface Plan

Consult comes first because it already has the narrowest backend seam:

```json
{
  "name": "deepr_consult_experts",
  "arguments": {
    "question": "...",
    "experts": ["AI Agent Harnesses", "Model Context Protocol"],
    "synthesis_backend": "api",
    "provider": "anthropic",
    "model": "claude-opus-4-8",
    "budget": 1.0,
    "_approved": true
  }
}
```

Expert chat comes next:

```json
{
  "name": "deepr_query_expert",
  "arguments": {
    "expert_name": "AI Agent Harnesses",
    "question": "...",
    "backend": "plan",
    "plan": "claude",
    "budget": 0,
    "_approved": true
  }
}
```

The following API-chat request is rejected by the v2.36 release gate before
provider dispatch. It documents the intended future contract only:

```json
{
  "name": "deepr_query_expert",
  "arguments": {
    "expert_name": "AI Agent Harnesses",
    "question": "...",
    "backend": "api",
    "provider": "anthropic",
    "model": "claude-opus-4-8",
    "budget": 1.0,
    "_approved": true
  }
}
```

`deepr_query_expert` local and plan modes return the normal query shape plus
`capacity` and `readonly_chat_artifact`, set `research_triggered=0`, reject
`agentic=true`, and never fall through to metered APIs. API mode is gated in
v2.36. Its intended future contract defaults to OpenAI and can be pinned to
non-agentic Anthropic chat with `provider=anthropic` and an Anthropic model only
after the P1 restoration criteria pass.

### Browser Socket.IO contract

The gated browser chat is a distinct public boundary because one
Socket.IO connection owns interactive session state across turns. Its current
request shape is intentionally narrower than MCP query chat, but v2.36 rejects
it before provider dispatch:

```json
{
  "expert_name": "AI Agent Harnesses",
  "message": "What changed?",
  "session_id": "optional-saved-conversation-id",
  "backend": "api",
  "chat_mode": "research",
  "budget": 0.5,
  "allow_metered_api": true,
  "confirm_metered_cost": true
}
```

- `backend="api"` is required. Browser `local` and `plan` modes are rejected
  explicitly until the UI can represent their read-only, no-tool, and
  no-streaming capability limits without implying interactive parity.
- `budget` is a required finite positive per-session ceiling bounded by
  the configured web per-job limit and
  `CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION`. It is never defaulted from a
  hardcoded browser allowance, and browser chat fails closed when the configured
  ceiling is unavailable.
- Both metered fields must be the boolean value `true`. A configured API key,
  an existing conversation, or a prior browser visit is not approval to spend.
- `chat_mode` must be one of `ask`, `research`, `advise`, or `focus`. The server
  applies the selected mode before every turn and rejects unknown values before
  provider construction.
- The first accepted turn creates one session for the Socket.IO client. Normal
  follow-up turns and slash commands reuse that session and its original
  approved ceiling. A second turn while one is running is rejected rather than
  dispatched concurrently.
- The session is removed on `/quit`, disconnect, or a terminal setup or turn
  failure. `chat_stop`, explicit end, and disconnect cancel the active asyncio
  task on its owning event loop, which propagates cancellation into the active
  provider request where the SDK and transport support it. A cancelled turn
  never emits `chat_complete`; its provider client and cost session close before
  the terminal cancellation event. Normal `chat_complete` keeps the session
  alive.
- Follow-up payloads must repeat the same backend, acknowledgement, and approved
  budget. Changing the ceiling requires ending the session and making a new
  explicit approval. `/budget` may inspect or reduce the ceiling, but it cannot
  raise it above the browser-approved amount.
- The REST fallback enforces the same API-only budget and acknowledgement
  contract. It remains one-shot and does not advertise persistent slash-command
  state.
- Each browser turn holds a durable ceiling before model dispatch. A successful
  turn releases that hold after ordinary usage accounting. Cancellation after a
  provider dispatch conservatively settles the unaccounted remainder; a turn
  cancelled before dispatch refunds it. If durable closure fails, the hold
  remains active and the cancellation event reports pending reconciliation
  instead of implying the cost is known.
- Optional follow-up suggestion generation is a separate bounded auxiliary
  call with at most 200 output tokens. It atomically reserves a conservative
  estimate against the same session ceiling, skips generation when that bound
  does not fit, and settles provider usage or the full estimate after an
  ambiguous provider failure. It never dispatches as untracked presentation
  work.
- A provider exception returned through the legacy session string interface is
  also exposed as typed terminal-turn state. Browser Socket.IO and REST treat
  that state as failure, settle the outer hold conservatively, and do not save
  or publish the error string as a successful answer.
- Browser streaming has no short wall-clock timeout. Agentic research can take
  5-20 minutes, so the UI remains attached while Socket.IO status and token
  events are healthy and offers an explicit Stop action. Transport disconnect
  ends the streaming state and cancels server work; it does not present a
  timeout as provider failure.

This is a workflow safety envelope around model-owned conversation meaning.
Retry behavior is fail-closed: no automatic provider retry or capacity fallback
is introduced here. The per-client in-flight guard prevents duplicate turns;
conversation persistence remains the existing explicit save after a successful
turn. Session cleanup closes provider clients on a best-effort basis and never
changes expert belief state.

## Cost And Security Rules

- API backend requires a positive budget and an approved scoped key or local
  operator confirmation. Anthropic API query chat supports non-agentic text
  streaming, but remains non-agentic until tool support has explicit backend
  capability checks.
- Local and plan backends allow `budget=0` and must set
  `live_metered_fallback=false`.
- No backend may fall through to another capacity tier without an explicit
  caller setting.
- Anthropic usage settlement must include `input_tokens`,
  `cache_creation_input_tokens`, `cache_read_input_tokens`, and `output_tokens`.
- Prompt-cache controls stay off until Deepr can estimate cache write/read
  costs, TTL, pre-warm calls, exact-prefix hit behavior, and privacy posture.
- Plan capacity must keep stripping known metered API-key env vars from child
  processes.
- Scoped MCP keys must estimate `deepr_query_expert` by requested backend. A
  `$0` scoped key may call local or plan query mode, but must reject API chat.
- Generated remote guide files and MCP key stores must remain under ignored
  `data/` paths.
- Browser API chat must validate its explicit backend, bounded positive budget,
  metered acknowledgement, expert identity, and mode before constructing an API
  session. A connected socket is transport state, not spend authorization.

## Agentic Balance

Deterministic workflow code owns backend choice, auth mode, budget checks,
quota checks, cache policy, request-shape compatibility, usage settlement,
ledger writes, schema validation, and no-fallback behavior.

Model judgment owns synthesis, contradiction interpretation, stance, novelty,
tradeoff analysis, and whether an expert perspective is useful.

Do not implement quality gates as lexical verdicts. Local quality admission,
consult evals, and paid backend selection can use model-judged eval artifacts,
but deterministic code should only enforce measured numeric thresholds and
side-effect policy.

## Rollout Order

1. Correct docs so only consult advertises local and plan synthesis today.
   (done)
2. Add provider and model fields to consult API synthesis, with Anthropic as the
   first non-OpenAI adapter. (done 2026-06-30)
3. Add usage and cost regression tests for Anthropic cache buckets, refusal
   stop details, unsupported sampling params, and budget rejection at zero.
   (done for consult API synthesis 2026-06-30)
4. Add local and plan query modes without metered fallback.
   (done; originally shipped through a one-expert consult adapter, then moved
   to direct read-only compiled-context chat backend routing on 2026-06-30)
5. Extract `ExpertChatBackend` and move current OpenAI chat behind it without
   behavior changes. (partial 2026-06-30: primary non-streaming
   answer-generation chat-completion turns, streaming setup/tool rounds,
   follow-up suggestions, conversation compaction, quick lookup, and
   standard-research fallback now use `OpenAIExpertChatBackend`; updated
   2026-06-30: final OpenAI token streaming now uses the backend streaming
   contract)
6. Add local and plan chat backends in read-only compiled-context mode.
   (done 2026-06-30: `LocalOllamaExpertChatBackend` and
   `PlanQuotaExpertChatBackend` implement the backend protocol with tools,
   streaming, and prompt cache disabled, and MCP `deepr_query_expert
   backend=local|plan` selects them for read-only compiled-context turns)
7. Add Anthropic expert chat in non-agentic mode.
   (done 2026-06-30: MCP `deepr_query_expert backend=api
   provider=anthropic` selects a native Anthropic Messages backend, omits
   OpenAI-only sampling params, disables tools and prompt-cache controls,
   supports native non-agentic text streaming with final usage settlement,
   rejects `agentic=true`, and records Anthropic usage buckets through the
   chat cost ledger)
8. Add agentic tools per backend only when the backend declares support and the
   tool has explicit cost and safety gates. (partial 2026-06-30: the shared
   chat-turn helper now enforces declared tool support before dispatch and
   strips `tool_choice` from no-tool turns)
9. Add prompt-cache controls only after cache estimation and settlement tests
   prove no silent-money path.
