# MCP Integration

Model Context Protocol integration for AI agent access to Deepr's research capabilities.

---

## Status

**Implementation Status:** Code complete, not yet tested with actual MCP clients.

- 7 tools implemented and importable
- Server starts without errors
- Not validated with Claude Desktop or Cursor in real scenarios
- No automated tests for MCP functionality
- Error handling untested with malformed requests
- Performance characteristics unknown

**Use at your own risk until validated in production scenarios.**

---

## Overview

Deepr includes an MCP server that exposes research and expert capabilities to AI agents like Claude Desktop and Cursor. This enables agents to:

- Submit long-running research jobs asynchronously
- Check job status and retrieve comprehensive reports
- Query domain experts with optional autonomous research
- Orchestrate multi-step research workflows

Unlike synchronous search tools (Perplexity, Tavily), Deepr provides asynchronous research infrastructure designed for comprehensive analysis rather than quick lookups.

---

## Strategic Positioning

| Feature | Perplexity | Tavily | Deepr |
|---------|-----------|--------|-------|
| Research Model | Sync | Sync | Async |
| Deep Research | No | No | Yes |
| Multi-Step | No | No | Yes |
| Expert System | No | No | Yes |
| Agentic Mode | No | No | Yes |
| Budget Controls | Limited | Limited | Granular |
| Multi-Provider | No | No | Yes |

Deepr fills a unique gap: research infrastructure for AI agents that need comprehensive analysis, not just web search.

---

## Available Tools

### Research Tools (4)

#### 1. deepr_research

Submit single research job with full control.

**Parameters:**
- `prompt` (required): Research question or topic
- `sources` (optional): List of domains to restrict search
- `budget` (optional): Maximum cost in dollars
- `files` (optional): List of file paths to upload as context
- `provider` (optional): AI provider (openai, gemini, grok, azure)
- `model` (optional): Specific model to use

**Returns:**
```json
{
  "job_id": "job_abc123",
  "estimated_time": "5-15 minutes",
  "cost_estimate": "$0.50-$2.00",
  "status": "queued"
}
```

#### 2. deepr_check_status

Poll job status with progress updates.

**Parameters:**
- `job_id` (required): Job identifier from research submission

**Returns:**
```json
{
  "status": "running",
  "progress": "Phase 2 of 3: Analysis",
  "elapsed_time": "8m 32s",
  "cost_so_far": "$1.23"
}
```

**Possible statuses:** queued, running, completed, failed, cancelled

#### 3. deepr_get_result

Retrieve completed research report.

**Parameters:**
- `job_id` (required): Job identifier

**Returns:**
```json
{
  "status": "completed",
  "markdown_report": "# Research Report\n\n...",
  "cost_final": "$2.15",
  "metadata": {
    "citations": 47,
    "sources": 23,
    "provider": "openai",
    "model": "o4-mini-deep-research"
  }
}
```

#### 4. deepr_agentic_research

Submit autonomous multi-step research with goal-driven planning.

**Parameters:**
- `goal` (required): High-level objective
- `sources` (optional): List of allowed domains
- `files` (optional): Context documents
- `budget` (optional): Maximum total cost

**Returns:**
```json
{
  "job_id": "campaign_xyz789",
  "workflow_plan": {
    "phases": 3,
    "estimated_tasks": 8,
    "estimated_time": "45-90 minutes",
    "estimated_cost": "$5-$15"
  }
}
```

### Expert Tools (3)

#### 5. deepr_list_experts

List all available domain experts.

**Parameters:** None

**Returns:**
```json
{
  "experts": [
    {
      "name": "Azure Architect",
      "description": "Azure Landing Zones and Fabric governance",
      "document_count": 15,
      "conversation_count": 8,
      "total_cost": 4.25,
      "last_updated": "2025-01-20T14:22:00Z"
    }
  ]
}
```

#### 6. deepr_query_expert

Query a domain expert with optional autonomous research.

**Parameters:**
- `expert_name` (required): Name of expert to query
- `question` (required): Question to ask
- `agentic` (optional, default: false): Enable autonomous research
- `budget` (optional): Maximum cost for agentic research

**Returns:**
```json
{
  "answer": "Based on my knowledge base...",
  "sources": [
    {
      "document": "azure-lz-best-practices.md",
      "section": "3.2 Hub-and-Spoke Topology",
      "confidence": "high"
    }
  ],
  "research_triggered": false,
  "cost": 0.02
}
```

With agentic mode enabled:
```json
{
  "answer": "I researched this topic and found...",
  "sources": [
    {
      "type": "research",
      "job_id": "job_abc123",
      "section": "2.1 Workspace Isolation"
    }
  ],
  "research_triggered": true,
  "cost": 0.17
}
```

#### 7. deepr_get_expert_info

Get detailed expert metadata and capabilities.

**Parameters:**
- `expert_name` (required): Name of expert

**Returns:**
```json
{
  "name": "Azure Architect",
  "description": "Azure Landing Zones and Fabric governance",
  "domain": "cloud architecture",
  "vector_store_id": "vs_abc123",
  "document_count": 15,
  "capabilities": {
    "agentic_research": true,
    "quick_lookup": true,
    "standard_research": true,
    "deep_research": true
  },
  "created_at": "2025-01-15T10:30:00Z",
  "last_updated": "2025-01-20T14:22:00Z"
}
```

---

## Setup

### Prerequisites

1. Python 3.9+ with Deepr installed
2. At least one AI provider API key configured
3. MCP-compatible client (Claude Desktop, Cursor, etc.)

### Configuration for Claude Desktop

Location: `C:\Users\<USER>\AppData\Roaming\Claude\claude_desktop_config.json` (Windows)
or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

```json
{
  "mcpServers": {
    "deepr": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "GEMINI_API_KEY": "...",
        "XAI_API_KEY": "..."
      }
    }
  }
}
```

### Configuration for Cursor

Location: Cursor settings (MCP section)

```json
{
  "mcpServers": {
    "deepr": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "GEMINI_API_KEY": "...",
        "XAI_API_KEY": "..."
      }
    }
  }
}
```

### Restart Client

After adding configuration:
1. Close Claude Desktop or Cursor completely
2. Restart application
3. Check that Deepr tools are available

---

## Usage from AI Agents

### Example: Research Task

Agent workflow for competitive analysis:

```
Agent: "I need deep research on competitor X's strategy"

1. Agent calls: deepr_research(
     prompt="Competitor X market strategy, product positioning, and growth plans",
     budget=5.0
   )

2. Receives: {job_id: "job_123", estimated_time: "10-15 min"}

3. Agent continues other work...

4. Periodically calls: deepr_check_status(job_id="job_123")
   Returns: {status: "running", progress: "Phase 2: Analysis"}

5. When complete, calls: deepr_get_result(job_id="job_123")
   Returns: {status: "completed", markdown_report: "# Analysis...", cost: 3.25}

6. Agent uses comprehensive report to inform recommendations
```

### Example: Expert Query

Agent workflow for technical question:

```
Agent: "Quick - what's the latest on Azure Fabric security?"

1. Agent calls: deepr_query_expert(
     expert_name="Azure Architect",
     question="Latest Azure Fabric security best practices",
     agentic=false
   )

2. Receives immediate answer from knowledge base with citations

If knowledge base lacks info:

1. Agent calls: deepr_query_expert(
     expert_name="Azure Architect",
     question="Azure Fabric security for multi-tenant SaaS",
     agentic=true,
     budget=2.0
   )

2. Expert triggers research automatically

3. Returns answer with both knowledge base and fresh research
```

### Example: Multi-Step Research

Agent workflow for strategic analysis:

```
Agent: "Analyze market entry strategy for European expansion"

1. Agent calls: deepr_agentic_research(
     goal="Comprehensive European market entry analysis with regulatory, competitive, and financial considerations",
     budget=15.0
   )

2. Deepr orchestrates multi-phase workflow:
   - Phase 1: Research market landscape, regulations, competitors
   - Phase 2: Analyze findings, identify gaps
   - Phase 3: Synthesize strategic recommendations

3. Agent polls status until complete

4. Retrieves comprehensive multi-phase analysis
```

---

## Architecture

### Communication Protocol

- **Transport:** stdio-based JSON-RPC
- **Format:** JSON messages via stdin/stdout
- **Session:** In-memory job tracking per session
- **Persistence:** Jobs persist on provider side (OpenAI, etc.)

### Security

- **API Keys:** Environment variables only (not in MCP messages)
- **Budget Controls:** Per-job and per-session limits enforced
- **Job Ownership:** Jobs isolated per session
- **Rate Limiting:** Planned (not yet implemented)

### Error Handling

All tools return structured error responses:

```json
{
  "error": {
    "code": "BUDGET_EXCEEDED",
    "message": "Job cost estimate ($5.50) exceeds budget limit ($5.00)",
    "details": {
      "estimated_cost": 5.50,
      "budget_limit": 5.00
    }
  }
}
```

Common error codes:
- `INVALID_PARAMETER` - Missing or malformed parameter
- `BUDGET_EXCEEDED` - Cost exceeds budget limit
- `EXPERT_NOT_FOUND` - Requested expert doesn't exist
- `JOB_NOT_FOUND` - Job ID not found
- `PROVIDER_ERROR` - AI provider API error

---

## Known Limitations

1. **Job Tracking:** In-memory only (lost on server restart)
2. **Testing:** No automated tests for MCP functionality
3. **Error Handling:** Not validated with malformed requests
4. **Performance:** Not tested under concurrent load
5. **Rate Limiting:** Not yet implemented
6. **Authentication:** No multi-user support

---

## Validation Checklist

Before considering production-ready:

- [ ] Test with Claude Desktop installation
- [ ] Validate all 7 tools work end-to-end
- [ ] Test error scenarios (invalid params, budget exceeded)
- [ ] Test concurrent requests from multiple agents
- [ ] Add automated integration tests
- [ ] Document observed performance characteristics
- [ ] Implement rate limiting
- [ ] Add authentication/multi-user support

---

## Use Cases

### Due Diligence Automation

Agent assisting with M&A due diligence:
1. Submit research on target company financials
2. Query expert for industry-specific considerations
3. Request multi-phase analysis of risks and opportunities
4. Compile findings into recommendation memo

### Technical Research Assistant

Agent helping developers with architecture decisions:
1. Query expert for current best practices
2. Trigger research on emerging technologies
3. Compare trade-offs between approaches
4. Generate technical decision document

### Market Intelligence

Agent monitoring competitive landscape:
1. Submit periodic research on competitor activities
2. Query expert for historical context
3. Synthesize trends and strategic implications
4. Alert on significant market changes

---

## Troubleshooting

### Server won't start

Check Python environment and API keys:
```bash
python -m deepr.mcp.server --version
echo $OPENAI_API_KEY
```

### Tools not appearing in client

1. Verify configuration file location is correct
2. Check JSON syntax in config file
3. Restart client completely
4. Check client logs for MCP connection errors

### Jobs failing silently

Check Deepr logs:
```bash
deepr jobs list
deepr doctor
```

Verify provider API keys are valid:
```bash
deepr doctor --skip-connectivity
```

### High costs

Review job costs before submission:
```bash
deepr cost summary
deepr analytics report
```

Set stricter budget limits in MCP calls.

---

## Future Enhancements

- Streaming progress updates via server-sent events
- Persistent job tracking (database-backed)
- Multi-user authentication and authorization
- Rate limiting and quota management
- Job cancellation support
- Webhook notifications for job completion
- Expert council mode (multi-expert deliberation)
- Temporal knowledge graph integration

---

See also:
- [mcp/README.md](../mcp/README.md) - MCP server implementation details
- [mcp_implementation_recommendations.md](mcp_implementation_recommendations.md) - Architecture decisions
- [EXPERT_SYSTEM.md](EXPERT_SYSTEM.md) - Expert capabilities and usage
