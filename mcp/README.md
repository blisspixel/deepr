# MCP Integration Guide

**Status**: Complete - 7 tools implemented and ready for use

Deepr exposes research and expert capabilities via Model Context Protocol (MCP) for AI agents like Claude Desktop and Cursor.

---

## Quick Start

### 1. Configure Claude Desktop

Create/edit `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "deepr": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### 2. Restart Claude Desktop

### 3. Test

Ask Claude: **"What MCP tools do you have access to?"**

You should see 7 Deepr tools available.

---

## Available Tools

### Research Tools

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `deepr_research` | Submit single research job | `prompt`, `model`, `provider` |
| `deepr_check_status` | Check job progress | `job_id` or `workflow_id` |
| `deepr_get_result` | Get completed report | `job_id` or `workflow_id` |
| `deepr_agentic_research` | Autonomous multi-step research | `goal`, `expert_name`, `budget` |

### Expert Tools

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `deepr_list_experts` | List domain experts | None |
| `deepr_query_expert` | Ask an expert | `expert_name`, `question`, `agentic` |
| `deepr_get_expert_info` | Get expert details | `expert_name` |

### Expert Tool Usage

**List Available Experts:**
```
User: "What domain experts are available in Deepr?"
Claude: Uses deepr_list_experts() to show all experts with their domains and knowledge counts.
```

**Query an Expert:**
```
User: "Ask the AWS expert about Lambda cold start optimization"
Claude: Uses deepr_query_expert(expert_name="AWS Expert", question="...", agentic=false)
Returns: Answer with confidence score, sources, and cost.
```

**Agentic Expert Query (with research):**
```
User: "Ask the AWS expert about the latest Lambda features, and have it research if needed"
Claude: Uses deepr_query_expert(expert_name="AWS Expert", question="...", agentic=true, budget=5.0)
Returns: Answer that may include newly researched information.
```

**Get Expert Details:**
```
User: "Tell me about the quantum computing expert"
Claude: Uses deepr_get_expert_info(expert_name="Quantum Expert")
Returns: Domain, knowledge count, beliefs, last updated, and capabilities.
```

---

## Usage Examples

### Simple Research
```
User: "Use deepr_research to analyze quantum computing trends"

-- Returns job_id
-- Wait 5-10 minutes
-- Check status with deepr_check_status(job_id)
-- Get results with deepr_get_result(job_id)
```

### Autonomous Multi-Step Research
```
User: "List experts, then use deepr_agentic_research with the quantum expert to do comprehensive market analysis with $10 budget"

-- Returns workflow_id
-- Expert autonomously conducts multiple research jobs
-- Synthesizes findings into comprehensive report
-- All within $10 budget
```

### Query an Expert
```
User: "Ask the agentic_digital_consciousness expert about reflection patterns in AI agents"

-- Returns answer with sources and cost
```

---

## Parameter Reference

### `deepr_research()`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | *required* | Research question |
| `model` | string | `o4-mini-deep-research` | Model name |
| `provider` | string | `openai` | openai/azure/gemini/grok |
| `budget` | float | `null` | Cost limit ($) |
| `files` | array | `null` | File paths |

**Returns**: `job_id`, `status`, `estimated_time`, `cost_estimate`

### `deepr_agentic_research()`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `goal` | string | *required* | High-level research goal |
| `expert_name` | string | *optional* | Expert for agentic reasoning |
| `budget` | float | `5.0` | Total workflow budget |

**Returns**: `workflow_id`, `status`, `expert_name`, `budget_allocated`

---

## Model Selection

| Model | Cost | Time | Use Case |
|-------|------|------|----------|
| `o4-mini-deep-research` | $0.10 | 5-10 min | Quick research, cost-sensitive |
| `o3-deep-research` | $0.50 | 10-20 min | Deep analysis, critical decisions |

---

## Provider Options

Add the appropriate API key to config:
- `openai`: `OPENAI_API_KEY`
- `azure`: `AZURE_OPENAI_API_KEY`
- `gemini`: `GEMINI_API_KEY`
- `grok`: `XAI_API_KEY`

---

## Troubleshooting

**Server not starting:**
- Check Python in PATH: `python --version`
- Verify Deepr installed: `pip show deepr`
- Try absolute Python path in config
- Check Claude Desktop logs: Help - View Logs

**API key issues:**
- Verify key in config JSON (no extra quotes/spaces)
- Check environment variable is set
- Try setting in `.env` file as fallback

**Job not found:**
- MCP server restarts lose in-memory tracking
- Jobs still exist on provider side
- Check provider API directly if needed

---

## Security

Following OpenAI MCP security guidelines:

- API keys in config only (never in code)
- Use budget limits for cost control
- Start with o4-mini for testing
- Monitor costs with `deepr budget status`
- Read-only operations (safe for `require_approval: never`)

---

## What Makes This Unique

**Deepr is the only async research infrastructure for AI agents.**

| Feature | Perplexity | Tavily | Deepr |
|---------|-----------|--------|-------|
| Research Model | Sync | Sync | **Async** |
| Multi-Step | No | No | **Yes** |
| Expert System | No | No | **Yes** |
| Agentic Mode | No | No | **Yes** |

When agents need comprehensive research (not just quick web search), they call Deepr.

---

## Example Prompts for Claude

```
# Discovery
"What MCP tools do you have access to?"
"Show me the Deepr research tools"

# Simple Research
"Use deepr_research to analyze renewable energy trends"
"Research quantum computing with o3-deep-research model"

# Agentic Research
"List experts, then start autonomous research on AI agents with $10 budget"
"Use deepr_agentic_research with quantum expert for market analysis"

# Expert Queries
"What domain experts are available?"
"Ask the agentic expert about metacognition patterns"

# Monitoring
"Check status of job [job_id]"
"Get the results for my research"
```

---

## Implementation Details

**Location**: `deepr/mcp/server.py`

**Transport**: stdio-based (lightweight, no dependencies)

**Architecture**:
- Async Python with `asyncio`
- JSON-RPC style messaging
- In-memory job tracking
- Provider API for status checks

**Job Tracking**:
- In-memory per session (lost on restart)
- Jobs persist on provider side
- Use provider API as source of truth

---

## Next Steps

1. Install Claude Desktop or Cursor
2. Copy config to MCP settings location
3. Add your API key
4. Restart the AI assistant
5. Test: "What MCP tools do you have?"
6. Start researching!

---

**Implementation Date:** November 11, 2025
**Status:** Production-ready
**Tools:** 7 (4 research + 3 expert)
