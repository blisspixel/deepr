---
name: deepr-research
description: |
  Deep research infrastructure for comprehensive analysis. Use when users need
  to research a topic in depth, consult domain experts, preview research curricula,
  run async investigations, compare options with citations, or manage research budgets.
  Keywords: research, deep research, investigate, analyze, domain expert, expert plan,
  comprehensive analysis, async research, expert consultation, knowledge synthesis,
  autonomous learning, curriculum, fill gaps, cost estimate
license: MIT
compatibility: |
  Requires python3 and OPENAI_API_KEY. Optional: XAI_API_KEY, GEMINI_API_KEY,
  AZURE_OPENAI_API_KEY. Runs on macOS, Linux, Windows.
allowed-tools: >-
  deepr_tool_search deepr_status deepr_research deepr_check_status
  deepr_get_result deepr_cancel_job deepr_agentic_research
  deepr_list_experts deepr_query_expert deepr_get_expert_info
argument-hint: "[research query or expert command]"
metadata:
  version: "2.8.0"
  author: Nick Seal
---

# Deepr Research Skill

You have access to Deepr — the same deep research APIs behind ChatGPT and Gemini, but callable as tools. It produces cited, comprehensive reports through async deep research, domain experts, and agentic workflows. Use it when you need accurate, current information with sources instead of relying on your training data.

## When to Use Deepr

**Use Deepr when:**
- The user needs current information beyond your training cutoff
- A question requires cited, comprehensive analysis — not a best guess
- You're mid-task and need verified facts (latest API docs, compliance rules, pricing)
- The user explicitly asks for research or to consult a domain expert
- You need to compare options with evidence, not just opinions

**Don't use Deepr when:**
- You're confident in your answer and the user isn't asking for citations
- The question is well-covered by your training data
- The user just needs code written, not researched
- Speed matters more than depth (Deepr takes 30 seconds to 20 minutes)

## Choosing a Mode

| User Need | Mode | Cost | Time |
|-----------|------|------|------|
| Quick current info, moderate analysis | Standard | $0.001-0.01 | 30-60 sec |
| Comprehensive analysis, critical decisions | Deep | $0.10-0.50 | 5-20 min |
| Multi-step autonomous investigation | Agentic | $1-10 | 15-60 min |
| Unsure of complexity | Auto | varies | varies |

**When in doubt, use auto mode.** It analyzes query complexity and routes to the cheapest sufficient model — simple questions go to grok-4-fast ($0.01) instead of o3-deep-research ($0.50). This saves 10-20x on costs.

```
Can I answer this confidently from training data?
  YES → Just answer, skip Deepr
  NO  → Does it need multi-step autonomous exploration?
          YES → Agentic Research (confirm budget first)
          NO  → Is comprehensive, multi-source analysis needed?
                  YES → Deep Research
                  NO  → Standard Research (or auto mode)
```

See `references/research_modes.md` for model details and async workflow patterns.

## Core Pattern: Research-Augmented Work

The most common use case: you're working on a task and hit something you're not sure about. Instead of guessing, research it.

```
1. Recognize uncertainty
   → You're about to make a claim or decision you're not confident about

2. Research it
   → deepr_research(query="your question", mode="auto")
   → Returns: job_id

3. Wait for results
   → Subscribe to deepr://campaigns/{job_id}/status (preferred, 70% fewer tokens)
   → Or poll with deepr_check_status(job_id)

4. Present cited answer
   → deepr_get_result(job_id)
   → Integrate findings into your response with citations preserved
   → Clearly mark what came from research vs your own knowledge
```

## Working With Experts

Domain experts are persistent knowledge entities that synthesize beliefs from documents, track what they don't know, and can research to fill their own gaps. They get smarter over time.

**Query an expert** when the question falls within their domain — it's faster and cheaper than fresh research:

```
deepr_list_experts()           → See what experts exist
deepr_query_expert(name, question)  → Ask a question
deepr_get_expert_info(name)    → Check profile, beliefs, gaps
```

**The expert-research chain** is Deepr's key differentiator. When an expert has low confidence or identifies a knowledge gap, suggest filling it:

```
1. Query expert → expert responds with LOW confidence or identifies gap
2. Tell the user: "The expert doesn't have current info on this.
   Want me to research it? (~$0.15)"
3. User confirms → deepr_research(query="the gap topic")
4. Expert integrates the findings permanently
5. Next time anyone asks, the expert knows
```

This loop — query → gap → research → learn — is how experts improve. Actively suggest it when you see low confidence. Use `deepr_query_expert(..., agentic=true)` to let the expert trigger research autonomously (costs more, needs budget confirmation).

**When to use experts vs fresh research:**
- Expert has the domain knowledge → query the expert (fast, cheap)
- Current events or topic outside their domain → fresh research
- Expert shows low confidence → fill the gap, then re-query

See `references/expert_system.md` for confidence levels, belief formation, and best practices.

## Cost Rules

1. **Always state the estimated cost** before research that costs more than $0.01
2. **Get explicit confirmation** before any operation over $5
3. **Always confirm** agentic research — it's $1-10+
4. **Prefer auto mode** when the right depth is unclear
5. **Mention cumulative cost** if you've run multiple research operations in one session
6. When the system **pauses for budget**, relay the three options to the user:
   - APPROVE_OVERRIDE — continue at higher cost
   - OPTIMIZE_FOR_COST — switch to cheaper model
   - ABORT — cancel, return partial results

See `references/cost_guidance.md` for pricing tables, budget tiers, and optimization strategies.

## Presenting Results

1. **Preserve all inline citations** — [1], [2] etc. are the whole point of using Deepr
2. **Lead with the answer** — executive summary first, details after
3. **Distinguish sources** — clearly mark what came from Deepr vs your own knowledge
4. **Include metadata** — cost, time, number of sources consulted
5. **Structure for scannability** — sections, bullets, tables where appropriate

## Tool Discovery

Deepr uses dynamic tool discovery to minimize context window usage. If you need a capability and don't see the right tool, search for it:

```
deepr_tool_search(query="what you need to do")
→ Returns matching tool schemas on demand
```

## Conversation Examples

### Mid-task research

```
User: Set up a VPC with private subnets for ECS Fargate

You: I'll set up the VPC. Let me check the current AWS recommendations
     for Fargate networking to make sure this follows best practices.

     [calls deepr_research("AWS ECS Fargate VPC networking best practices 2026")]
     [receives result in ~45 seconds]

You: Based on current AWS documentation [1][2], here's the recommended setup:
     - Use at least 2 AZs with private subnets for tasks...
     [continues with cited infrastructure code]

     Research cost: $0.005 · 8 sources
```

### Comprehensive analysis

```
User: Compare Kubernetes vs ECS for our microservices migration

You: This needs comprehensive analysis across cost, complexity, ecosystem,
     and team readiness. Deep research will take 10-20 minutes and cost
     ~$0.30-0.50. Want me to proceed?

User: Yes

You: Starting deep research now. I'll let you know when results are ready.

     [calls deepr_research(query="...", mode="deep")]
     [subscribes to status updates]
     [~14 minutes later, result is ready]

You: Research complete ($0.35, 23 sources). Here's what I found:

     ## Executive Summary
     [structured findings with all citations preserved]
     [clearly attributes everything to Deepr research, not own knowledge]
```

### Expert with gap filling

```
User: Ask the security expert about OWASP API Top 10 changes for 2026

You: [calls deepr_list_experts() → finds "Security Analyst"]
     [calls deepr_query_expert("Security Analyst", "OWASP API Top 10 2026 changes?")]

You: The Security Analyst has medium confidence here and flagged a knowledge
     gap around the 2026 updates specifically. Want me to research the latest
     changes so the expert can learn them? (~$0.15)

User: Sure

You: [calls deepr_research("OWASP API Security Top 10 2026 changes and updates")]
     [expert integrates findings]

You: Here's what changed in the 2026 OWASP API Security Top 10: [1][2][3]
     [presents findings with citations]

     The Security Analyst now has this information for future queries.
```

## Available Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_tool_search` | Search available capabilities by description | Free |
| `deepr_status` | System health, active jobs, spending summary | Free |
| `deepr_research` | Submit research job (standard, deep, or auto mode) | $0.001-0.50 |
| `deepr_check_status` | Check job progress | Free |
| `deepr_get_result` | Retrieve completed research results | Free |
| `deepr_cancel_job` | Cancel a running job | Free |
| `deepr_agentic_research` | Autonomous multi-step research campaign | $1-10 |
| `deepr_list_experts` | List available domain experts | Free |
| `deepr_query_expert` | Query an expert (optionally with agentic research) | Low |
| `deepr_get_expert_info` | Detailed expert profile and stats | Free |

## Error Handling

Tools return structured errors with `error_code`, `message`, and optional `retry_hint` / `fallback_suggestion`.

| Error | What to Do |
|-------|------------|
| `BUDGET_EXCEEDED` | Tell user the limit was hit, offer alternatives or suggest daily reset |
| `JOB_NOT_FOUND` | Double-check the job_id |
| `EXPERT_NOT_FOUND` | Run `deepr_list_experts` and suggest available experts |
| `PROVIDER_NOT_CONFIGURED` | Tell user which API key is needed |
| `BUDGET_INSUFFICIENT` | Suggest increasing the budget parameter |

See `references/` for detailed documentation on [MCP patterns](references/mcp_patterns.md), [cost guidance](references/cost_guidance.md), [research modes](references/research_modes.md), [expert system](references/expert_system.md), and [troubleshooting](references/troubleshooting.md).

The `scripts/` directory contains Python modules for Deepr's MCP server (result formatting, query classification) — reference implementations, not used by the skill directly.
