# MCP Patterns Reference

This document details the advanced Model Context Protocol patterns implemented in Deepr's MCP server.

## Contents

- [Pattern 1: Dynamic Tool Discovery](#pattern-1-dynamic-tool-discovery)
- [Pattern 2: Resource Subscriptions](#pattern-2-resource-subscriptions)
- [Pattern 3: Human-in-the-Loop Elicitation](#pattern-3-human-in-the-loop-elicitation)
- [Pattern 4: Sandboxed Execution](#pattern-4-sandboxed-execution)
- [Pattern 5: Multi-Agent Collaboration](#pattern-5-multi-agent-collaboration)
- [Pattern Selection Guide](#pattern-selection-guide)

## Architecture Overview

```
Host (Claude Desktop / IDE)
    |
    v
MCP Client (manages connections)
    |
    v
Deepr MCP Server (implements patterns)
    |
    +-- Tool Registry (Dynamic Discovery)
    +-- Job Manager (Resource Subscriptions)
    +-- Elicitation Handler (Human-in-the-Loop)
    +-- Sandbox Manager (Isolated Execution)
```

## Pattern 1: Dynamic Tool Discovery

### Problem

Exposing all 40+ Deepr tools in `list_tools` consumes ~77,000 tokens of context, leaving minimal room for actual conversation.

### Solution

Expose a single gateway tool (`deepr_tool_search`) that searches and returns relevant tool schemas on demand using BM25 ranking over pre-tokenized tool descriptions.

### How to Use

```
1. Need to perform an action? Search for the tool first.
2. Call: deepr_tool_search(query="<describe what you need>")
3. System returns relevant tool schemas on-demand.
4. Use the returned tool with proper parameters.
```

### Context Reduction

| Approach | Tokens | Reduction |
|----------|--------|-----------|
| All tools exposed | ~77,000 | baseline |
| Gateway only | ~8,700 | 89% |
| After search (3 tools) | ~9,500 | 88% |

## Pattern 2: Resource Subscriptions

### Problem

Polling for job status wastes tokens and creates poor UX. Each poll requires a tool call and response.

### Solution

Use MCP's `resources/subscribe` to receive push notifications when job state changes.

### Resource URIs

```
# Campaign resources (live job tracking)
deepr://campaigns/{id}/status    # Job state, progress, cost
deepr://campaigns/{id}/plan      # Research plan details
deepr://campaigns/{id}/beliefs   # Accumulated beliefs

# Report artifacts (completed research)
deepr://reports/{id}/final.md    # Full research report (markdown)
deepr://reports/{id}/summary.json # Report metadata (cost, model, sources)

# Log artifacts (provenance/debugging)
deepr://logs/{id}/search_trace.json # Search queries and results
deepr://logs/{id}/decisions.md      # Human-readable decision log

# Expert resources (persistent knowledge)
deepr://experts/{id}/profile     # Expert metadata
deepr://experts/{id}/beliefs     # Expert knowledge base
deepr://experts/{id}/gaps        # Knowledge gaps
```

### Event Payload

```json
{
    "jsonrpc": "2.0",
    "method": "notifications/resources/updated",
    "params": {
        "uri": "deepr://campaigns/abc123/status",
        "data": {
            "phase": "executing",
            "progress": 0.65,
            "active_tasks": ["Analyzing market trends"],
            "cost_so_far": 0.12,
            "estimated_remaining": "2 minutes"
        }
    }
}
```

### Token Savings

| Approach | Tokens per update | 10 updates |
|----------|-------------------|------------|
| Polling | ~500 | ~5,000 |
| Subscription | ~150 | ~1,500 |
| Savings | 70% | 70% |

## Pattern 3: Human-in-the-Loop Elicitation

### Problem

When research exceeds budget, the server cannot unilaterally decide to continue, abort, or optimize. The decision requires human input.

### Solution

Use MCP's `elicitation/create` to request structured input from the user, reversing the typical control flow.

### JSON-RPC Request

```json
{
    "jsonrpc": "2.0",
    "method": "elicitation/create",
    "params": {
        "id": "budget_abc123",
        "message": "Research estimated at $2.50 exceeds budget of $1.00",
        "requestedSchema": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["approve_override", "optimize_for_cost", "abort"]
                },
                "new_budget": {
                    "type": "number"
                }
            },
            "required": ["decision"]
        }
    },
    "id": 1
}
```

### Decision Options

| Decision | Effect |
|----------|--------|
| `approve_override` | Continue with original plan at higher cost |
| `optimize_for_cost` | Switch to cheaper models (e.g., grok-4-fast) and reduce iterations |
| `abort` | Cancel and return partial results |

See `references/cost_guidance.md` for detailed elicitation handling and model switching chain.

## Pattern 4: Sandboxed Execution

### Problem

Deep research generates verbose intermediate reasoning, debug logs, and tool traces that pollute the main conversation context.

### Solution

Use MCP's `content: fork` capability to isolate heavy processing in a sandboxed sub-context. Only the final synthesized report is returned to the main conversation.

### Fork Request

```json
{
    "jsonrpc": "2.0",
    "method": "content/fork",
    "params": {
        "job_id": "abc123",
        "context": {
            "type": "research",
            "query": "Analyze competitive landscape",
            "constraints": {
                "max_tokens": 100000,
                "working_dir": "/sandboxes/abc123"
            }
        }
    },
    "id": 1
}
```

Key properties:
- Research data never leaves the sandbox until extraction
- Path validation prevents traversal attacks (absolute paths rejected, containment checked)
- Intermediate reasoning and debug logs are discarded
- Only final report and artifacts are returned

## Pattern 5: Multi-Agent Collaboration

Multiple Claude instances or AI agents can collaborate on research by subscribing to the same campaign resources. Each agent receives identical updates and can interpret them through their specialized lens.

### Example: Tech + Finance Agents

```
Research Campaign: "Should we migrate to Kubernetes?"

Agent A (Tech Focus):
  - Subscribes to: deepr://campaigns/k8s-analysis/status
  - Focuses on: architecture, scalability, complexity

Agent B (Finance Focus):
  - Subscribes to: deepr://campaigns/k8s-analysis/status
  - Focuses on: TCO, licensing, team training costs

Both receive identical phase notifications.
Each interprets through their expertise.
```

### Coordination Patterns

| Pattern | Description |
|---------|-------------|
| Parallel Interpretation | All agents subscribe to same campaign, each processes independently |
| Sequential Handoff | Agent A initiates research, on completion Agent B receives results and triggers follow-up |
| Specialized Subscriptions | Each agent subscribes only to resources relevant to their domain |

## Pattern Selection Guide

| Scenario | Pattern | Benefit |
|----------|---------|---------|
| Many tools available | Dynamic Discovery | 85%+ context reduction |
| Long-running jobs | Resource Subscriptions | 70% token savings |
| Cost decisions needed | Elicitation | User control preserved |
| Heavy processing | Sandboxed Execution | Clean conversation |
| Multiple agents | Multi-subscriber | Parallel collaboration |
