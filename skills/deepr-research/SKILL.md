---
name: deepr-research
description: |
  Deep research infrastructure for comprehensive analysis. Activate when users need:
  - Async deep research (5-20 min comprehensive reports vs instant shallow search)
  - Domain expert consultation with persistent knowledge and belief formation
  - Multi-step agentic research workflows with Plan-Execute-Review cycles
  - Cost-aware research decisions with budget tracking and elicitation
  
  Keywords: research, deep research, investigate, analyze, domain expert, 
  comprehensive analysis, async research, expert consultation, multi-step research,
  knowledge synthesis, autonomous learning
version: 1.0.0
---

# Deepr Research Skill

You have access to Deepr, a research operating system that produces cited, comprehensive reports through async deep research, domain experts, and agentic workflows.

## Quick Reference: Research Mode Selection

```
User Need                          -> Mode              -> Cost        -> Time
---------------------------------------------------------------------------
Simple factual question            -> Web Search        -> FREE        -> <5 sec
Current info, moderate analysis    -> Standard Research -> $0.001-0.01 -> 30-60 sec
Comprehensive analysis, decisions  -> Deep Research     -> $0.10-0.50  -> 5-20 min
Multi-step autonomous research     -> Agentic Research  -> $1-10       -> 15-60 min
```

## Tool Discovery Pattern

Deepr uses dynamic tool discovery to minimize context. Start with `deepr_tool_search`:

```
1. Need to perform an action? Search for the tool first.
2. Call: deepr_tool_search(query="<describe what you need>")
3. System returns relevant tool schemas on-demand.
4. Use the returned tool with proper parameters.
```

Examples:
- "submit a research job" -> returns deepr_research
- "check job status" -> returns deepr_check_status  
- "query domain expert" -> returns deepr_query_expert

## Core Workflows

### 1. Async Research Workflow

Deep research runs asynchronously. Use resource subscriptions for efficient monitoring:

```
Step 1: Classify the research need (see Quick Reference)
Step 2: State estimated cost and time to user
Step 3: Get confirmation for operations > $5
Step 4: Submit job via deepr_research tool
        -> Returns: job_id, resource_uri
Step 5: Subscribe to resource URI for progress updates
        -> deepr://campaigns/{job_id}/status
Step 6: Receive push notifications as phases complete:
        - PLANNING: Research plan created
        - EXECUTING: Active research in progress
        - SYNTHESIZING: Combining findings
        - COMPLETE: Results ready
Step 7: Retrieve results via deepr_get_result(job_id)
Step 8: Present results with preserved citations
```

Subscription vs Polling:
- Subscriptions: ~150 tokens per update (preferred)
- Polling: ~500 tokens per check (avoid)
- Token savings: 70% with subscriptions

Plan-Execute-Review Visibility:
- Inspect plan: `deepr://campaigns/{id}/plan`
- Monitor beliefs: `deepr://campaigns/{id}/beliefs`
- Track progress: `deepr://campaigns/{id}/status`

### 2. Expert Consultation Workflow

Domain experts maintain persistent knowledge with belief formation and gap awareness.

```
Step 1: Discover experts
        -> Call deepr_list_experts()
        -> Returns: name, domain, document_count, belief_count, gaps_count

Step 2: Inspect expert before complex queries
        -> Read resource: deepr://experts/{id}/profile
        -> Check beliefs: deepr://experts/{id}/beliefs
        -> Review gaps: deepr://experts/{id}/gaps

Step 3: Query the expert
        -> Call deepr_query_expert(expert_name, question)
        -> Expert answers from synthesized knowledge
        -> Response includes confidence level and source citations

Step 4: Handle knowledge gaps
        -> If expert indicates low confidence or gap
        -> Suggest: "Would you like me to research this topic?"
        -> Enable agentic mode: deepr_query_expert(..., agentic=true)
```

Expert Resources:
| Resource | Content |
|----------|---------|
| `deepr://experts/{id}/profile` | Name, domain, creation date, stats |
| `deepr://experts/{id}/beliefs` | Synthesized knowledge with confidence (0-1) |
| `deepr://experts/{id}/gaps` | Known unknowns with priority ranking |

Expert Query Patterns:
- Direct question: "What are the best practices for X?"
- Belief check: "How confident are you about Y?"
- Gap exploration: "What don't you know about Z?"
- Comparative: "Compare A vs B from your knowledge"

When to Use Experts vs Fresh Research:
- Use expert: Domain-specific questions within their knowledge
- Use research: Current events, topics outside expert domain
- Use agentic expert: Complex questions requiring new research

### 3. Agentic Research Workflow

Autonomous multi-step research with Plan-Execute-Review cycles.

```
Step 1: Clarify goal with user
        -> "What specific outcome do you need?"
        -> "What decisions will this inform?"

Step 2: Confirm budget
        -> State estimated cost range ($1-10 typical)
        -> Get explicit confirmation for agentic operations
        -> Set budget limit: deepr_agentic_research(..., budget=5.0)

Step 3: Submit autonomous campaign
        -> Call deepr_agentic_research(goal, budget, sources)
        -> Returns: campaign_id, resource_uri, initial_plan

Step 4: Monitor via subscriptions
        -> Subscribe to: deepr://campaigns/{id}/status
        -> Receive phase notifications:
           - PLANNING: "Creating research plan with 4 tasks"
           - EXECUTING: "Completed 2/4 tasks, $1.20 spent"
           - REVIEWING: "Analyzing findings, planning next phase"
           - SYNTHESIZING: "Combining all findings"

Step 5: Handle budget elicitation
        -> If cost exceeds budget, system pauses
        -> You receive elicitation request with options:
           - APPROVE_OVERRIDE: "Continue, I approve $X more"
           - OPTIMIZE_FOR_COST: "Switch to cheaper models"
           - ABORT: "Cancel and return partial results"
        -> Relay decision to user, submit response

Step 6: Retrieve and present results
        -> Call deepr_get_result(campaign_id)
        -> Present synthesized report with all citations
        -> Include: total cost, time, sources consulted
```

Agentic Mode Benefits:
- Autonomous decomposition of complex goals
- Multi-phase research with context chaining
- Adaptive planning based on intermediate findings
- Sandboxed execution (isolated context, clean results)

Sandboxed Execution:
- Heavy research runs in isolated context
- Intermediate reasoning and debug logs contained
- Only final synthesized report returned
- Prevents context dilution in main conversation

Budget Elicitation Flow:
```
System: "Research paused. Estimated cost $7.50 exceeds budget $5.00"
Options:
  1. APPROVE_OVERRIDE - Continue with $7.50
  2. OPTIMIZE_FOR_COST - Switch to grok-4-fast (~$3.00)
  3. ABORT - Cancel, return partial results

You: [Present options to user, relay their choice]
```

## Cost Awareness

ALWAYS state estimated cost before proceeding with research:

| Operation | Typical Cost | Confirmation Required |
|-----------|-------------|----------------------|
| Web search | FREE | No |
| Standard research | $0.001-0.01 | No |
| Deep research | $0.10-0.50 | If > $5 |
| Agentic research | $1-10 | Always |

When budget limits are exceeded, the system will pause and elicit user decision:
- APPROVE_OVERRIDE: Continue with higher cost
- OPTIMIZE_FOR_COST: Switch to cheaper models
- ABORT: Cancel the operation

## Output Formatting

When presenting research results:
1. Preserve ALL inline citations from source report
2. Structure with clear sections and executive summary
3. Distinguish Deepr findings from your own knowledge
4. Include metadata: cost, time, sources count

## Resource URIs

Monitor async operations via MCP resources:
- `deepr://campaigns/{id}` - Live research status
- `deepr://campaigns/{id}/plan` - Research plan (inspectable)
- `deepr://campaigns/{id}/beliefs` - Synthesized findings
- `deepr://experts/{id}/profile` - Expert metadata
- `deepr://experts/{id}/beliefs` - Expert knowledge with confidence
- `deepr://experts/{id}/gaps` - Known knowledge gaps

## Error Handling

| Error | Action |
|-------|--------|
| Job timeout (>30 min) | Suggest checking later or resubmitting |
| Budget exceeded | Explain limit, offer alternatives |
| Expert not found | List available experts |
| API key missing | Direct to setup instructions |

See `references/` for detailed documentation on each topic.
