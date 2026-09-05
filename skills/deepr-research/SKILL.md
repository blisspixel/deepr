---
name: deepr-research
description: |
  Use Deepr for bounded deep research, async cited reports, and consultation
  with persistent domain experts. Trigger when a user asks for current sourced
  analysis, a research cost preview, a domain expert or expert council, or
  inspection of durable beliefs, gaps, confidence, and provenance.
metadata:
  deepr-version: "2.50.12"
  deepr-mcp-server: "deepr"
---

# Deepr research

Use Deepr as a bounded research and persistent-expert service. Preserve
citations, budget posture, capacity provenance, uncertainty, and dissent.

## Release-safe operating contract

Treat these as works-now surfaces in the current release:

- Write-free API research previews when the provider, model, tools, token
  ceilings, and price are all known. Production paid dispatch remains blocked.
- Explicit local Ollama or non-metered plan-quota expert workflows.
- Read-only expert state, handoffs, loop status, memory cards, and derived
  exports.
- One-expert or multi-expert consultation through explicit local or eligible
  plan synthesis. Metered council synthesis remains blocked even with approval
  and a positive budget.

Treat these as execution-blocked, even if a tool or flag remains visible:

- `deepr_agentic_research` and other autonomous multi-round metered work.
- `deepr_research` paid execution and metered council synthesis.
- `deepr_query_expert` with `backend="api"` or `agentic=true`.
- Automatic cross-provider metered fallback.
- Metered batch, campaign, team, prepared, or continuation execution.
- Hosted upload, file-search, or vector-store attachment to research.
- Generic metered expert creation, learning, resume, refresh, gap fill,
  reflection, portrait generation, or corpus calibration.

Do not retry a blocked surface with a larger budget or another provider. A
capacity gate means the accounting contract is unavailable, not that the user
asked a bad question.

## Select capacity explicitly

1. Prefer existing expert state when it already covers the question.
2. Prefer `backend="local"` for a true `$0` marginal-cost expert turn when an
   admitted Ollama model is ready.
3. Use `backend="plan"` only with an explicit non-metered plan id. Do not infer
   that CLI presence proves free quota. A visible backend is not proof of
   executable plan capacity.
4. Use the CLI's write-free API research preview to inspect a finite envelope.
   No user budget or approval installs the missing provider account-control
   and credential-identity proof needed for production paid dispatch.
5. Never silently fall through between capacity classes.

## Preview one bounded research job

Use this sequence:

1. State that the budget is a maximum, not a predicted final charge.
2. Inspect the advertised tool schema; a visible metered tool is not executable
   capacity. The CLI supports `deepr research QUESTION --provider PROVIDER
   --model MODEL --preview` without a paid request.
3. Keep hosted files, paid tools, automatic fallback, and inference disabled.
4. Report the estimated maximum and the dispatch block separately. A preview
   produces no submitted job or completed research report.
5. Existing accepted job state and completed reports remain inspectable through
   `deepr_check_status` and `deepr_get_result`.

Do not invent fixed prices or promise a completion time. Model rates, tool
charges, provider latency, and the hard request envelope determine the
admission result. If the envelope exceeds the approved budget, stop and return
the denial rather than weakening the ceiling.

## Consult persistent experts

Start by calling `deepr_list_experts` and, when useful,
`deepr_get_expert_info`. Then choose one of these no-metered paths:

```text
deepr_query_expert(
  expert_name="Security Analyst",
  question="What evidence should guide this decision?",
  backend="local",
  agentic=false,
  budget=0
)
```

```text
deepr_query_expert(
  expert_name="Security Analyst",
  question="What evidence should guide this decision?",
  backend="plan",
  plan="claude",
  agentic=false,
  budget=0
)
```

For several experts, prefer `deepr_consult_experts` with
`synthesis_backend="local"` or `synthesis_backend="plan"`. Keep the roster at
10 or fewer, preserve disagreements, and verify that
`capacity.live_metered_fallback` is `false`.

An expert answer is a perspective over stored state, not ground truth. Surface
confidence, contested beliefs, stale evidence, missing sources, and known gaps.
Do not claim that a fresh research report was permanently absorbed unless a
separate verified write workflow actually completed.

## Handle local capacity defensively

For scheduled local maintenance, treat `busy` as a waiting outcome. Preserve
the returned retry time and do not fall through to plan or API capacity.
Expected retry guidance uses bounded 30-minute, 2-hour, then 6-hour cadence.
Explicit unscheduled local work is an operator override; do not simulate that
override on the user's behalf.

## Present results

- Lead with the answer.
- Preserve every citation marker and source URL returned by Deepr.
- Separate research-derived claims from your own inference.
- Include provider/capacity, actual settled cost, and important limits.
- Preserve council dissent instead of flattening it into false consensus.
- Say when semantic quality is unreviewed. Structural eval success is not proof
  that an answer is true or wise.

## Tool guide

| Tool | Use |
|------|-----|
| `deepr_tool_search` | Discover a current tool schema before calling it |
| `deepr_status` | Inspect service readiness and spending posture |
| `deepr_research` | Visible metered tool; production paid dispatch is blocked |
| `deepr_check_status` | Inspect an accepted job |
| `deepr_get_result` | Retrieve a completed cited report |
| `deepr_cancel_job` | Request cancellation and retain accounting state |
| `deepr_list_experts` | List persistent experts |
| `deepr_get_expert_info` | Inspect expert profile and gaps |
| `deepr_query_expert` | Run one local or plan read-only expert turn |
| `deepr_consult_experts` | Produce a bounded one- or multi-expert consult artifact |

## Error handling

- `BUDGET_EXCEEDED` or `BUDGET_INSUFFICIENT`: report the ceiling and capacity
  block; a larger budget cannot enable quarantined production dispatch.
- `PROVIDER_NOT_CONFIGURED`: identify the missing explicit capacity without
  switching providers.
- `metered_expert_chat_accounting_unavailable` or another capacity block: use
  local/plan read-only consultation or stop.
- Busy local capacity: report the durable wait and retry time.
- Ambiguous provider failure: do not resubmit automatically. The reservation
  may have been conservatively settled.

Read these only when needed:

- [Research modes](references/research_modes.md) for the exact works-now and
  gated research boundary.
- [Expert system](references/expert_system.md) for read-only consultation and
  verified update boundaries.
- [Cost guidance](references/cost_guidance.md) for ceilings and ledger rules.
- [MCP patterns](references/mcp_patterns.md) for discovery, resources, and
  host-agent contracts.
- [Troubleshooting](references/troubleshooting.md) for typed failure handling.
- [Prompt patterns](references/prompt_patterns.md) for bounded research prompts.
