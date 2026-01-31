# Research Modes Reference

This document details the research modes available in Deepr and when to use each.

## Mode Comparison

| Mode | Model | Cost | Time | Best For |
|------|-------|------|------|----------|
| Quick Lookup | Web Search | FREE | <5 sec | Simple facts, definitions |
| Standard | grok-4-fast | $0.001-0.01 | 30-60 sec | Current info, moderate analysis |
| Deep Mini | o4-mini-deep-research | $0.10-0.30 | 5-10 min | Comprehensive analysis |
| Deep Full | o3-deep-research | $0.30-0.50 | 10-20 min | Critical decisions, novel problems |
| Agentic | Multi-model orchestration | $1-10 | 15-60 min | Multi-step autonomous research |

## Decision Flowchart

```
START: What does the user need?
    |
    v
Is it a simple factual question?
    |-- YES --> Quick Lookup (FREE)
    |-- NO
        |
        v
    Does it need current/recent information?
        |-- YES --> Standard Research ($0.001-0.01)
        |-- NO
            |
            v
        Is it comprehensive analysis or a critical decision?
            |-- YES --> Is budget > $0.50 acceptable?
            |           |-- YES --> Deep Full ($0.30-0.50)
            |           |-- NO --> Deep Mini ($0.10-0.30)
            |-- NO
                |
                v
            Does it require multiple research phases?
                |-- YES --> Agentic Research ($1-10)
                |-- NO --> Standard Research
```

## Mode Details

### Quick Lookup (Web Search)

**When to use:**
- Simple factual questions ("What is the capital of France?")
- Definitions and basic explanations
- Quick verification of known facts

**Characteristics:**
- Instant results
- No cost
- Limited depth
- May not have latest information

**Example queries:**
- "What is PostgreSQL?"
- "Define machine learning"
- "Who founded Tesla?"

### Standard Research (grok-4-fast)

**When to use:**
- Current events and recent developments
- Moderate analysis requiring multiple sources
- Technical documentation lookups
- Market trends and news

**Characteristics:**
- Fast turnaround (30-60 seconds)
- Low cost ($0.001-0.01)
- Good breadth, moderate depth
- Includes citations

**Example queries:**
- "Latest developments in quantum computing 2026"
- "Compare React vs Vue for enterprise apps"
- "Current FDA approval process timeline"

### Deep Research Mini (o4-mini-deep-research)

**When to use:**
- Comprehensive analysis needed
- Complex technical topics
- Strategic planning inputs
- Due diligence research

**Characteristics:**
- Thorough multi-phase research
- Plan-Execute-Review cycle
- 5-10 minute execution
- Detailed citations and sources
- Cost: $0.10-0.30

**Example queries:**
- "Analyze PostgreSQL connection pooling strategies for high-traffic applications"
- "Compare HIPAA, HITECH, and state privacy laws for telehealth"
- "Evaluate build vs buy decision for data platform"

### Deep Research Full (o3-deep-research)

**When to use:**
- Critical business decisions
- Novel problem-solving
- Comprehensive market analysis
- Technical architecture decisions

**Characteristics:**
- Maximum depth and rigor
- Extended reasoning chains
- 10-20 minute execution
- Highest quality synthesis
- Cost: $0.30-0.50

**Example queries:**
- "Strategic analysis: Should we enter the European market?"
- "Design a fault-tolerant distributed system for financial transactions"
- "Comprehensive competitive analysis of AI code editors"

### Agentic Research (Multi-model)

**When to use:**
- Multi-step research goals
- Autonomous exploration needed
- Building domain expertise
- Complex investigations

**Characteristics:**
- Fully autonomous execution
- Multiple Plan-Execute-Review cycles
- Can spawn sub-research tasks
- 15-60 minute execution
- Cost: $1-10 depending on scope

**Example queries:**
- "Build comprehensive knowledge base on Kubernetes networking"
- "Research and synthesize best practices for MCP server development"
- "Investigate market opportunity for AI-powered research tools"

## Async Workflow Pattern

For Deep and Agentic research, use the async workflow:

```
1. Submit research job
   -> Receive campaign_id and resource URI

2. Subscribe to resource for updates
   -> deepr://campaigns/{id}

3. Monitor progress via notifications
   -> Phase updates, task completion, cost tracking

4. Retrieve results when complete
   -> Formatted report with citations
```

### Detailed Async Workflow Example

```
Step 1: Submit Job
-----------------
Call: deepr_research(prompt="Analyze PostgreSQL connection pooling strategies")
Response: {
  "job_id": "job-abc123",
  "resource_uri": "deepr://campaigns/job-abc123",
  "estimated_time": "5-10 minutes",
  "estimated_cost": "$0.15-0.25"
}

Step 2: Subscribe to Updates
----------------------------
Subscribe to: deepr://campaigns/job-abc123/status

Step 3: Receive Progress Notifications
--------------------------------------
Notification 1: {
  "phase": "PLANNING",
  "message": "Creating research plan",
  "elapsed": "0:30"
}

Notification 2: {
  "phase": "EXECUTING",
  "message": "Researching: PgBouncer configuration",
  "tasks_complete": 1,
  "tasks_total": 4,
  "elapsed": "2:15"
}

Notification 3: {
  "phase": "SYNTHESIZING",
  "message": "Combining findings",
  "cost_so_far": "$0.18",
  "elapsed": "6:45"
}

Notification 4: {
  "phase": "COMPLETE",
  "message": "Research complete",
  "final_cost": "$0.21",
  "elapsed": "7:30"
}

Step 4: Retrieve Results
------------------------
Call: deepr_get_result(job_id="job-abc123")
Response: {
  "status": "completed",
  "markdown_report": "# PostgreSQL Connection Pooling...",
  "citations": 23,
  "sources": 12,
  "cost": "$0.21"
}
```

### Resource URIs for Inspection

During async research, inspect these resources:

| Resource | Purpose |
|----------|---------|
| `deepr://campaigns/{id}/status` | Current phase and progress |
| `deepr://campaigns/{id}/plan` | Research plan (tasks, dependencies) |
| `deepr://campaigns/{id}/beliefs` | Synthesized findings so far |

### Subscription vs Polling

PREFERRED: Resource Subscriptions
- Event-driven updates (~150 tokens per notification)
- No wasted API calls
- Real-time progress visibility
- 70% token savings vs polling

AVOID: Polling
- Burns tokens on repeated status checks (~500 tokens per poll)
- Clutters conversation history
- Higher latency for updates
- Unnecessary API costs

Token Comparison (10-minute research job):
- Polling every 30 seconds: ~10,000 tokens
- Subscriptions: ~3,000 tokens
- Savings: 70%

## Cost Optimization Tips

1. Start with Standard research for initial exploration
2. Use Deep research only when comprehensive analysis is needed
3. Set explicit budgets for Agentic research
4. Monitor cumulative session costs
5. Use OPTIMIZE_FOR_COST when elicited for budget decisions
