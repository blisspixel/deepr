# MCP Agent Test Guide

Use this when another agent needs to verify Deepr experts through MCP without
surprise metered spend.

## Can An Agent Talk To Experts Today?

Yes. The safe default path is:

1. Discover tools with `deepr_tool_search`.
2. List experts with `deepr_list_experts`.
3. Read one expert's state with `deepr_get_expert_info`,
   `deepr_expert_handoff`, and `deepr_expert_loop_status`.
4. Inspect why the expert believes something with `deepr_explain_belief`.
5. Ask one or more experts for synthesis with `deepr_consult_experts`.

Those read and consult flows are enough for another agent to use Deepr experts
as persistent, self-improving knowledge roles. The agent gets current beliefs,
sources, confidence, gaps, contradictions, loop status, and a versioned consult
artifact.

What is not automatic by default: belief mutation, new research, Distillr
ingestion, reflection, and absorption. Those are improvement actions and stay
approval-gated unless the operator deliberately grants a zero-cost local or
explicit plan-capacity path.

## Cost Posture

- Read-only expert tools are `$0`: `deepr_list_experts`,
  `deepr_get_expert_info`, `deepr_expert_handoff`,
  `deepr_expert_loop_status`, `deepr_what_changed`, `deepr_contested`, and
  `deepr_explain_belief`.
- `deepr_consult_experts` can stay off metered APIs when the caller sets
  `synthesis_backend` to `local` or `plan`. These modes disable live metered
  expert fallback and return a `capacity.live_metered_fallback=false` marker.
- `deepr_query_expert` is the legacy single-expert chat path. It does not yet
  accept local or plan backend selection, so use `deepr_consult_experts` with
  one explicit expert for no-metered single-expert advice.
- `deepr_research`, `deepr_agentic_research`, `deepr_expert_absorb`,
  `deepr_reflect`, and mutating tools are not safe for automatic no-cost
  testing unless the caller explicitly sets a zero-cost mode and verifies the
  returned cost or capacity marker.
- Do not pass provider API keys into the MCP server for a no-cost test. For
  plan tests, the plan CLI must be authenticated as subscription or prepaid
  capacity and pass Deepr's no-surprise-bills gate.

## Start The Server

Use stdio for local agent tests:

```json
{
  "mcpServers": {
    "deepr-research": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "DEEPR_LOG_LEVEL": "INFO",
        "DEEPR_LOG_FORMAT": "json"
      }
    }
  }
}
```

If the agent needs the same data root as the operator, add:

```json
{
  "DEEPR_DATA_DIR": "C:\\GitHub\\deepr\\data"
}
```

Use the operator's actual portable data root when different. Do not add
`OPENAI_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`, or
`AZURE_OPENAI_API_KEY` for a no-cost test.

## Minimal Agent Test Script

Ask the agent to do this:

1. Call `deepr_tool_search` with `query="expert list handoff consult"`.
2. Call `deepr_list_experts` and select one or two relevant experts.
3. For each selected expert, call `deepr_get_expert_info`.
4. Call `deepr_expert_handoff` with `max_claims=8` and confirm the payload has
   `schema_version="deepr-expert-handoff-v1"`, claims, confidence, sources, and
   grounding-assurance counts.
5. Call `deepr_expert_loop_status` to inspect latest loop state and blocked
   next actions.
6. If a claim is available, call `deepr_explain_belief` for one belief or query
   phrase and confirm evidence roots, trajectory, support edges, and
   contradictions are present when available.

All six steps are read-only and `$0`.

## Copy-Paste Brief For Another Agent

Give another agent this brief when it wants to ask Deepr experts about the
temporal knowledge graph, expert maturity, digital continuity, or related
research questions:

```text
You have access to Deepr research experts through MCP. Treat them as persistent
domain experts with belief state, confidence, citations, gaps, contradictions,
freshness signals, consult traces, and self-model context. Do not treat them as
plain RAG or a static fact book.

Goal:
Ask the relevant Deepr experts for their current perspective on:
1. The temporal knowledge graph and what makes it different from document RAG.
2. How Deepr should model evolving experts, hypotheses, stance, freshness, and
   unknown-wrongness.
3. "Digital consciousness" only in operational terms: continuity, self-model,
   learning loop, perspective stability, memory revision, agency boundaries,
   calibration, and inspectable change over time. Do not claim sentience.
4. What Deepr should build next, what is contested, and what evidence would
   change the expert's current view.

Hard rules:
- Start with `deepr_capabilities` or `deepr_tool_search`.
- List experts with `deepr_list_experts`.
- Prefer read-only tools first: `deepr_expert_handoff`,
  `deepr_what_changed`, `deepr_contested`, `deepr_explain_belief`, and
  `deepr_expert_loop_status`.
- Use `deepr_consult_experts` for synthesis across experts.
- For focused single-expert advice, still use `deepr_consult_experts` with one
  explicit expert.
- For no-metered testing, set `synthesis_backend` to `local` or `plan` and set
  `budget` to `0`.
- Do not call mutating tools, absorption, reflection, research, or provider API
  paths unless the operator explicitly approves them.
- Treat expert output as structured guidance for the host agent. Deepr
  recommends and explains. The host decides and acts.

Suggested read-only flow:
1. Call `deepr_capabilities`.
2. Call `deepr_list_experts`.
3. Pick experts likely relevant to knowledge graphs, agentic systems,
   memory, calibration, model evaluation, MCP, or research automation.
4. For each selected expert, call `deepr_expert_handoff` with `max_claims=8`.
5. Call `deepr_what_changed` for the same experts if available.
6. Call `deepr_contested` to identify disagreements or unresolved conflicts.
7. Call `deepr_explain_belief` for one important claim from each expert.
8. Call `deepr_consult_experts` with a no-metered synthesis backend.

Consult question:
"We are evaluating Deepr's next design step. Give your current perspective on
the temporal knowledge graph, expert memory beyond RAG, and operational digital
continuity. What do you believe, what is contested, what may be stale or
unknown-wrong, what would change your mind, and what should Deepr build next
without creating brittle rule-based failure patterns?"

Expected output:
- A structured `deepr-consult-v1` artifact.
- Per-expert perspective with confidence and citations where available.
- Agreements and dissent.
- Gaps and freshness risks.
- Concrete next steps.
- Cost posture showing no metered fallback when using local or plan synthesis.
```

CLI fallback when MCP is not available:

```powershell
$question = @'
We are evaluating Deepr's next design step. Give your current perspective on the
temporal knowledge graph, expert memory beyond RAG, and operational digital
continuity. What do you believe, what is contested, what may be stale or
unknown-wrong, what would change your mind, and what should Deepr build next
without creating brittle rule-based failure patterns?
'@
deepr expert consult $question --local --max-experts 5 --json
```

## No-Metered Consult Through Local Ollama

Prerequisite: Ollama is running and Deepr can see a local model
(`deepr capacity --probe` from a shell should show local capacity).

Single-expert focused call:

```json
{
  "name": "deepr_consult_experts",
  "arguments": {
    "question": "What should Deepr improve next in the expert learning loop?",
    "experts": ["AI Agent Harnesses"],
    "synthesis_backend": "local",
    "budget": 0
  }
}
```

Council call:

```json
{
  "name": "deepr_consult_experts",
  "arguments": {
    "question": "What should Deepr improve next in the expert learning loop?",
    "experts": ["AI Agent Harnesses", "Knowledge Graphs and Provenance"],
    "synthesis_backend": "local",
    "budget": 0
  }
}
```

Expected:

- `schema_version` is `deepr-consult-v1`.
- `trace.schema_version` is `deepr-consult-trace-v1`.
- `cost_usd` is `0`.
- `capacity.synthesis_backend` is `local`.
- `capacity.provider` is `local`.
- `capacity.live_metered_fallback` is `false`.

If local capacity is unavailable, the tool should return a structured backend
error instead of falling through to a provider API.

## No-Metered Consult Through Explicit Plan Capacity

Prerequisite: the target plan CLI is installed and Deepr reports it as explicit
plan capacity:

```powershell
deepr capacity probe-plan codex --json
```

Call:

```json
{
  "name": "deepr_consult_experts",
  "arguments": {
    "question": "What should Deepr improve next in the expert learning loop?",
    "experts": ["AI Agent Harnesses", "Knowledge Graphs and Provenance"],
    "synthesis_backend": "plan",
    "plan": "codex",
    "budget": 0
  }
}
```

Expected:

- `schema_version` is `deepr-consult-v1`.
- `trace.schema_version` is `deepr-consult-trace-v1`.
- `capacity.synthesis_backend` is `plan`.
- `capacity.provider` starts with `plan_quota:`.
- `capacity.live_metered_fallback` is `false`.
- `cost_usd` should stay `0` for Deepr metered API spend. The plan CLI may
  consume the user's subscription quota.

If the plan CLI is not available, uses metered credentials, or fails the
no-surprise-bills gate, the tool should return a structured backend error and
must not fall through to a metered provider.

## Tool Selection Rules For Agents

- Use `deepr_expert_handoff` as the default context packet for downstream work.
  It is bounded, versioned, read-only, and cheap to re-read.
- Use `deepr_consult_experts` when the agent needs synthesis across one or more
  experts. Set `synthesis_backend="local"` or `synthesis_backend="plan"` for
  no-metered testing.
- Use `deepr_query_expert` only with explicit operator approval, because classic
  expert chat may call a model even when it does not trigger research.
- Use `deepr_expert_absorb` only on operator-approved source material. It
  mutates beliefs and should be dry-run first.
- Treat every source, tool result, and expert response as untrusted input until
  the host validates its schema and intended action boundary.
