# Expert Chat Capacity Backends

Status: design note, 2026-06-26.

Scope: `deepr expert consult`, `deepr_consult_experts`, `deepr expert chat`,
and `deepr_query_expert`.

## Purpose

Expert collaboration needs three first-class capacity modes:

1. Local Ollama for true `$0` Deepr dollar cost.
2. Explicit plan-quota CLIs for prepaid or subscription capacity.
3. Paid provider APIs for frontier quality when the operator sets a budget.

These modes must be honest. Local and plan paths may be slower or lower quality,
but they must not fall through to metered APIs. Paid API paths may be stronger,
but every request must estimate, reserve, settle, and append to the canonical
cost ledger.

## Current Code Constraints

- `deepr.experts.consult.build_synthesis_backend` already selects local
  Ollama or explicit plan-quota synthesis for consults and disables live
  metered fallback in those modes.
- `PlanQuotaChatClient` and `ollama_chat_client` already satisfy the narrow
  `client.chat.completions.create(...)` seam used by council synthesis.
- API-backed council synthesis still defaults to `AsyncOpenAI`. It is not yet
  provider-pluggable.
- `ExpertChatSession` is more coupled than consult. Its constructor requires
  `OPENAI_API_KEY`, stores an `AsyncOpenAI` client, uses OpenAI chat
  completions, uses the Responses API path for retrieval, generates follow-ups
  with an OpenAI model, and routes under an OpenAI provider constraint for
  vector-store compatibility.
- MCP `deepr_consult_experts` accepts `synthesis_backend=api|local|plan`.
  MCP `deepr_query_expert` does not yet accept backend, provider, or model
  selection and should be treated as the legacy metered-capable chat path.
- `AnthropicProvider` is a research provider, not a reusable expert-chat
  backend. The generic provider factory also does not currently expose
  `anthropic` in `ProviderType`.

## 2026 Provider Findings

The paid API path cannot be a thin OpenAI wrapper.

- Claude Opus 4.8 uses Anthropic's Messages API. Official examples call
  `client.messages.create(model="claude-opus-4-8", ...)`.
- Claude Opus 4.8 supports adaptive thinking. Manual extended thinking with a
  fixed `budget_tokens` is rejected. Use `thinking={"type": "adaptive"}` when
  thinking is needed.
- Non-default sampling parameters such as `temperature`, `top_p`, and `top_k`
  are rejected on Claude Opus 4.8. The Anthropic adapter must omit them instead
  of passing Deepr's OpenAI-style `temperature=0.3`.
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

References checked:

- Anthropic Claude API primer:
  https://platform.claude.com/docs/en/claude_api_primer
- Anthropic model migration guide:
  https://platform.claude.com/docs/en/about-claude/models/migration-guide
- Anthropic prompt caching:
  https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Anthropic Opus 4.8 announcement:
  https://www.anthropic.com/news/claude-opus-4-8

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
```

The request should carry normalized messages, system instructions, max output,
structured-output requirements, optional tools, and optional provider features.
The result should carry text, usage buckets, stop reason, refusal metadata,
cost, provider request id when available, and whether cost was exact or
estimated.

Backends:

- `LocalOllamaExpertBackend`: OpenAI-compatible local chat client. Cost is
  always `$0` in Deepr. Tool support starts disabled unless explicitly proven.
- `PlanQuotaExpertBackend`: wraps `PlanQuotaChatClient`. Cost is `$0` in Deepr,
  writes quota observations and `$0` ledger events, and never auto-routes
  unless remaining-quota evidence exists.
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

For API chat:

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

Until the expert-chat backend interface lands, only consult should advertise
local and plan synthesis. `deepr_query_expert` remains the legacy
metered-capable chat path.

## Cost And Security Rules

- API backend requires a positive budget and an approved scoped key or local
  operator confirmation.
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
  `$0` scoped key may call local or plan chat, but must reject API chat.
- Generated remote guide files and MCP key stores must remain under ignored
  `data/` paths.

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
2. Add provider and model fields to consult API synthesis, with Anthropic as the
   first non-OpenAI adapter.
3. Add usage and cost regression tests for Anthropic cache buckets, refusal
   stop details, unsupported sampling params, and budget rejection at zero.
4. Extract `ExpertChatBackend` and move current OpenAI chat behind it without
   behavior changes.
5. Add local and plan chat backends in read-only compiled-context mode.
6. Add Anthropic expert chat in non-agentic mode.
7. Add agentic tools per backend only when the backend declares support and the
   tool has explicit cost and safety gates.
8. Add prompt-cache controls only after cache estimation and settlement tests
   prove no silent-money path.
