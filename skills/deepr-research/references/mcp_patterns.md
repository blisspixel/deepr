# MCP Patterns Reference

This document details the advanced Model Context Protocol patterns implemented in Deepr's MCP server. These patterns transform Deepr from a basic tool provider into a sophisticated research platform.

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
Expose a single gateway tool that searches and returns relevant tool schemas on demand.

### Implementation

```python
# Only tool exposed by default
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="deepr_tool_search",
            description="Search Deepr capabilities by natural language query",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of desired capability"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 3,
                        "description": "Maximum tools to return"
                    }
                },
                "required": ["query"]
            }
        )
    ]
```

### Tool Registry with BM25 Search

```python
from rank_bm25 import BM25Okapi
from dataclasses import dataclass

@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict
    tokens: list[str]  # Pre-tokenized for BM25

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSchema] = {}
        self._index: BM25Okapi | None = None
    
    def register(self, tool: ToolSchema) -> None:
        self._tools[tool.name] = tool
        self._rebuild_index()
    
    def search(self, query: str, limit: int = 3) -> list[ToolSchema]:
        if not self._index:
            return []
        
        query_tokens = self._tokenize(query)
        scores = self._index.get_scores(query_tokens)
        
        ranked = sorted(
            zip(self._tools.values(), scores),
            key=lambda x: x[1],
            reverse=True
        )
        return [tool for tool, _ in ranked[:limit]]
    
    def _tokenize(self, text: str) -> list[str]:
        return text.lower().split()
    
    def _rebuild_index(self) -> None:
        corpus = [t.tokens for t in self._tools.values()]
        self._index = BM25Okapi(corpus)
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

### Implementation

```python
from asyncio import Queue
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class Subscription:
    uri: str
    callback: Callable[[dict], None]

class JobManager:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._event_queue: Queue = Queue()
    
    async def subscribe(self, uri: str, callback: Callable) -> str:
        sub = Subscription(uri=uri, callback=callback)
        self._subscriptions.setdefault(uri, []).append(sub)
        return f"sub_{uri}_{len(self._subscriptions[uri])}"
    
    async def emit_update(self, uri: str, data: dict) -> None:
        """Emit resource update to all subscribers."""
        for sub in self._subscriptions.get(uri, []):
            await self._send_notification(sub, data)
    
    async def _send_notification(self, sub: Subscription, data: dict) -> None:
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {
                "uri": sub.uri,
                "data": data
            }
        }
        sub.callback(notification)
```

### Resource URIs

```
deepr://campaigns/{id}/status    # Job status and progress
deepr://campaigns/{id}/plan      # Research plan details
deepr://campaigns/{id}/beliefs   # Accumulated beliefs
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

### Implementation

```python
from enum import Enum
from dataclasses import dataclass

class BudgetDecision(Enum):
    APPROVE_OVERRIDE = "approve_override"
    OPTIMIZE_FOR_COST = "optimize_for_cost"
    ABORT = "abort"

@dataclass
class ElicitationRequest:
    id: str
    message: str
    schema: dict
    timeout_seconds: int = 300

class ElicitationHandler:
    async def request_budget_decision(
        self,
        estimated_cost: float,
        budget_limit: float,
        job_id: str
    ) -> BudgetDecision:
        request = ElicitationRequest(
            id=f"budget_{job_id}",
            message=f"Research estimated at ${estimated_cost:.2f} exceeds budget of ${budget_limit:.2f}",
            schema={
                "type": "object",
                "properties": {
                    "decision": {
                        "type": "string",
                        "enum": ["approve_override", "optimize_for_cost", "abort"],
                        "description": "How to proceed with the research"
                    },
                    "new_budget": {
                        "type": "number",
                        "description": "New budget limit if approving override"
                    }
                },
                "required": ["decision"]
            }
        )
        
        response = await self._send_elicitation(request)
        return BudgetDecision(response["decision"])
```

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

### Decision Handling

```python
async def handle_budget_decision(
    self,
    decision: BudgetDecision,
    job: ResearchJob
) -> None:
    match decision:
        case BudgetDecision.APPROVE_OVERRIDE:
            # Continue with original plan
            await job.resume()
        
        case BudgetDecision.OPTIMIZE_FOR_COST:
            # Switch to cheaper models
            job.config.model = "grok-4-fast"
            job.config.max_iterations = min(job.config.max_iterations, 3)
            await job.resume()
        
        case BudgetDecision.ABORT:
            # Return partial results
            await job.cancel(return_partial=True)
```

## Pattern 4: Sandboxed Execution

### Problem
Deep research generates verbose intermediate reasoning, debug logs, and tool traces that pollute the main conversation context.

### Solution
Use MCP's `content: fork` capability to isolate heavy processing in a sandboxed sub-context.

### Implementation

```python
from pathlib import Path
from dataclasses import dataclass

@dataclass
class SandboxConfig:
    working_dir: Path
    max_tokens: int = 100_000
    allowed_tools: list[str] = None

class SandboxManager:
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._active_sandboxes: dict[str, SandboxConfig] = {}
    
    async def create_sandbox(self, job_id: str) -> SandboxConfig:
        sandbox_dir = self._base_dir / "sandboxes" / job_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        
        config = SandboxConfig(
            working_dir=sandbox_dir,
            allowed_tools=["deepr_search", "deepr_analyze", "deepr_synthesize"]
        )
        self._active_sandboxes[job_id] = config
        return config
    
    def validate_path(self, sandbox_id: str, path: Path) -> bool:
        """Prevent path traversal attacks."""
        config = self._active_sandboxes.get(sandbox_id)
        if not config:
            return False
        
        try:
            resolved = path.resolve()
            return resolved.is_relative_to(config.working_dir)
        except (ValueError, RuntimeError):
            return False
    
    async def extract_results(self, job_id: str) -> dict:
        """Extract final report from sandbox, discarding intermediate state."""
        config = self._active_sandboxes.get(job_id)
        if not config:
            raise ValueError(f"No sandbox for job {job_id}")
        
        report_path = config.working_dir / "final_report.md"
        if report_path.exists():
            return {
                "report": report_path.read_text(),
                "artifacts": self._list_artifacts(config.working_dir)
            }
        return {"report": None, "artifacts": []}
```

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

### Security: Path Validation

```python
def validate_path(self, sandbox_id: str, requested_path: str) -> Path | None:
    """
    Validate and resolve path within sandbox boundaries.
    Returns None if path would escape sandbox.
    """
    config = self._active_sandboxes.get(sandbox_id)
    if not config:
        return None
    
    # Normalize and resolve
    requested = Path(requested_path)
    if requested.is_absolute():
        return None  # Reject absolute paths
    
    resolved = (config.working_dir / requested).resolve()
    
    # Check containment
    try:
        resolved.relative_to(config.working_dir)
        return resolved
    except ValueError:
        # Path escapes sandbox (e.g., ../../etc/passwd)
        return None
```

## Multi-Agent Collaboration

Multiple Claude instances or AI agents can collaborate on research by subscribing to the same campaign resources. Each agent receives identical updates and can interpret them through their specialized lens.

### Multiple Subscribers

The subscription manager supports unlimited subscribers per resource:

```python
class SubscriptionManager:
    async def emit(self, uri: str, data: dict) -> int:
        """Emit to ALL subscribers of a URI."""
        notified = 0
        for sub in self._get_matching_subscriptions(uri):
            await sub.callback(self._build_notification(uri, data))
            notified += 1
        return notified
    
    def subscribers_for(self, uri: str) -> int:
        """Count active subscribers for a resource."""
        return len(self._get_matching_subscriptions(uri))
```

### Use Case: Tech + Finance Agents

Two specialized agents collaborate on a strategic analysis:

```
Research Campaign: "Should we migrate to Kubernetes?"

Agent A (Tech Focus):
  - Subscribes to: deepr://campaigns/k8s-analysis/status
  - Interprets updates through technical lens
  - Focuses on: architecture, scalability, complexity
  - Asks follow-up: "What about service mesh options?"

Agent B (Finance Focus):
  - Subscribes to: deepr://campaigns/k8s-analysis/status
  - Interprets updates through financial lens
  - Focuses on: TCO, licensing, team training costs
  - Asks follow-up: "What's the 3-year cost projection?"

Both receive identical phase notifications:
{
  "phase": "EXECUTING",
  "task": "Analyzing infrastructure costs",
  "progress": 0.45
}

Each interprets through their expertise.
```

### Coordination Patterns

Pattern 1: Parallel Interpretation
- All agents subscribe to same campaign
- Each processes updates independently
- Results synthesized by orchestrator

Pattern 2: Sequential Handoff
- Agent A initiates research
- On completion, Agent B receives results
- Agent B triggers follow-up research

Pattern 3: Specialized Subscriptions
- Agent A subscribes to technical resources
- Agent B subscribes to financial resources
- Each receives only relevant updates

### Implementation Example

```python
# Agent A subscribes
sub_a = await manager.subscribe(
    uri="deepr://campaigns/analysis-123/status",
    callback=tech_agent_handler
)

# Agent B subscribes to same resource
sub_b = await manager.subscribe(
    uri="deepr://campaigns/analysis-123/status",
    callback=finance_agent_handler
)

# When status updates, both receive notification
await manager.emit(
    uri="deepr://campaigns/analysis-123/status",
    data={"phase": "COMPLETE", "cost": 2.50}
)
# Returns: 2 (both agents notified)
```

### Subscriber Count in Notifications

Notifications include subscriber count for coordination awareness:

```json
{
    "jsonrpc": "2.0",
    "method": "notifications/resources/updated",
    "params": {
        "uri": "deepr://campaigns/abc/status",
        "data": {
            "phase": "COMPLETE",
            "subscriber_count": 3
        },
        "timestamp": "2026-01-30T10:15:00Z"
    }
}
```

## Transport Layer

### Stdio Transport (Local)

```python
import sys
import json

class StdioTransport:
    async def read_message(self) -> dict:
        line = sys.stdin.readline()
        return json.loads(line)
    
    async def write_message(self, message: dict) -> None:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()
```

Benefits:
- Research data never leaves local process
- No network latency
- Simpler security model

### Streamable HTTP Transport (Cloud)

```python
from aiohttp import web

class HttpTransport:
    async def handle_request(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        response.content_type = "application/json"
        await response.prepare(request)
        
        async for chunk in self._process_stream(request):
            await response.write(chunk.encode() + b"\n")
        
        return response
```

Benefits:
- Cloud deployment capability
- Chunked transfer for long-running operations
- Load balancing support

## Pattern Selection Guide

| Scenario | Pattern | Benefit |
|----------|---------|---------|
| Many tools available | Dynamic Discovery | 85%+ context reduction |
| Long-running jobs | Resource Subscriptions | 70% token savings |
| Cost decisions needed | Elicitation | User control preserved |
| Heavy processing | Sandboxed Execution | Clean conversation |
| Multiple agents | Multi-subscriber | Parallel collaboration |
