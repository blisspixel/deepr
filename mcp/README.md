# MCP Integration Guide

**Status**: 16 tools, dynamic discovery, resource subscriptions, prompt templates

Deepr exposes research and expert capabilities via Model Context Protocol (MCP) for AI agents including OpenClaw, Claude Desktop, Cursor, VS Code, and Zed.

---

## Setup by Runtime

### OpenClaw

Copy `mcp/openclaw-config.json` to your OpenClaw MCP configuration:

```json
{
  "mcpServers": {
    "deepr-research": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "DEEPR_LOG_LEVEL": "INFO",
        "DEEPR_LOG_FORMAT": "json"
      },
      "autoAllow": [
        "deepr_tool_search", "deepr_status", "deepr_list_experts",
        "deepr_get_expert_info", "deepr_check_status", "deepr_get_result"
      ]
    }
  }
}
```

The `autoAllow` list includes read-only tools that don't incur costs. Cost-incurring tools (`deepr_research`, `deepr_agentic_research`, `deepr_query_expert`) require approval.

For Docker deployment, use `mcp/openclaw-docker-config.json` instead.

### Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).

Use the template from `mcp/mcp-config-claude-desktop.json`:

```json
{
  "mcpServers": {
    "deepr-research": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key-here"
      }
    }
  }
}
```

Restart Claude Desktop after saving.

### Cursor

Edit Cursor MCP settings. Use the template from `mcp/mcp-config-cursor.json` (same format as Claude Desktop).

### VS Code

Add to your VS Code MCP settings (`.vscode/mcp.json` or user settings). Use the template from `mcp/mcp-config-vscode.json`:

```json
{
  "servers": {
    "deepr-research": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key-here"
      }
    }
  }
}
```

### Zed

Add to `~/.config/zed/settings.json` under `"language_models"` -> `"mcp"`:

```json
{
  "language_models": {
    "mcp": {
      "deepr-research": {
        "command": "python",
        "args": ["-m", "deepr.mcp.server"],
        "env": {
          "OPENAI_API_KEY": "your-openai-key-here"
        }
      }
    }
  }
}
```

---

## Available Tools

### System Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_tool_search` | Dynamic tool discovery via BM25 search | Free |
| `deepr_status` | Health check (version, uptime, active jobs, spending) | Free |

### Research Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_research` | Submit deep research job | $0.10-0.50 |
| `deepr_check_status` | Check job progress | Free |
| `deepr_get_result` | Get completed report | Free |
| `deepr_cancel_job` | Cancel running job | Free |
| `deepr_agentic_research` | Autonomous multi-step research | $1-10 |

### Expert Tools

| Tool | Purpose | Cost |
|------|---------|------|
| `deepr_list_experts` | List domain experts | Free |
| `deepr_query_expert` | Query expert with question | Low |
| `deepr_get_expert_info` | Expert details and stats | Free |

### Dynamic Discovery

Deepr uses a gateway pattern for context efficiency. By default, `tools/list` returns only `deepr_tool_search`. Agents search for capabilities by description:

```
deepr_tool_search(query="submit research job")  -> returns deepr_research schema
deepr_tool_search(query="expert knowledge")     -> returns expert tool schemas
```

This reduces initial context by ~85%.

---

## Resource URIs

Subscribe to resources for push notifications instead of polling (70% token savings):

### Campaign Resources (live)
| URI | Content |
|-----|---------|
| `deepr://campaigns/{id}/status` | Job phase, progress, cost |
| `deepr://campaigns/{id}/plan` | Research plan |
| `deepr://campaigns/{id}/beliefs` | Accumulated findings |

### Report Artifacts (completed)
| URI | Content |
|-----|---------|
| `deepr://reports/{id}/final.md` | Full research report |
| `deepr://reports/{id}/summary.json` | Report metadata |

### Log Artifacts (provenance)
| URI | Content |
|-----|---------|
| `deepr://logs/{id}/search_trace.json` | Search query history |
| `deepr://logs/{id}/decisions.md` | Decision log |

### Expert Resources (persistent)
| URI | Content |
|-----|---------|
| `deepr://experts/{id}/profile` | Expert metadata |
| `deepr://experts/{id}/beliefs` | Knowledge with confidence |
| `deepr://experts/{id}/gaps` | Known knowledge gaps |

---

## Prompt Templates

Three prompt templates available via `prompts/list`:

| Prompt | Description |
|--------|-------------|
| `deep_research_task` | Comprehensive research with executive summary |
| `expert_consultation` | Domain expert Q&A with gap handling |
| `comparative_analysis` | Multi-option comparison with decision matrix |

---

## Structured Errors

All tools return structured errors for agent retry/fallback:

```json
{
  "error_code": "BUDGET_EXCEEDED",
  "message": "Research blocked by cost safety: daily limit reached",
  "retry_hint": "Wait for daily limit reset",
  "fallback_suggestion": "Daily spent: $45.00"
}
```

Common error codes: `BUDGET_EXCEEDED`, `JOB_NOT_FOUND`, `EXPERT_NOT_FOUND`, `PROVIDER_NOT_CONFIGURED`, `BUDGET_INSUFFICIENT`, `EXPERT_REQUIRED`, `TOOL_NOT_FOUND`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for research |
| `XAI_API_KEY` | No | xAI/Grok API key |
| `GEMINI_API_KEY` | No | Google Gemini API key |
| `AZURE_OPENAI_API_KEY` | No | Azure OpenAI API key |
| `DEEPR_LOG_LEVEL` | No | Logging level (default: INFO) |
| `DEEPR_LOG_FORMAT` | No | `text` or `json` (default: text) |

---

## Architecture

```
StdioServer (JSON-RPC transport)
    -> Method dispatch (initialize, tools/*, resources/*, prompts/*)
        -> DeeprMCPServer (business logic)
            -> MCPResourceHandler (resource reads, subscriptions)
            -> JobManager (job lifecycle, notifications)
            -> GatewayTool + ToolRegistry (BM25 dynamic discovery)
            -> ResearchOrchestrator (research execution)
            -> ExpertStore (expert management)
```

**Transport**: stdio (JSON-RPC 2.0 over stdin/stdout)
**Job Tracking**: In-memory with SQLite persistence (`data/mcp_jobs.db`)
**Logging**: Structured JSON to stderr (for OpenClaw log aggregation)

---

## Troubleshooting

**Server not starting:**
- Verify Python 3.9+: `python --version`
- Verify Deepr installed: `pip show deepr` or `deepr --version`
- Try absolute Python path in config
- Check logs in your runtime (Claude Desktop: Help -> View Logs)

**API key issues:**
- Verify key in config JSON (no extra quotes/spaces)
- For OpenClaw, use `${OPENAI_API_KEY}` syntax for env injection
- Test with `deepr doctor` from CLI

**"No tools found":**
- Deepr uses dynamic discovery. Ask: "Search for research tools" to trigger `deepr_tool_search`
- Or use `deepr_status` to verify the server is running

**Job not found after restart:**
- Jobs are persisted in SQLite but provider instances are lost
- Check `data/mcp_jobs.db` for job history
- Re-submit if needed

---

**Tools:** 10 (3 system + 4 research + 3 expert)
**Resources:** 10 URI schemes across 4 resource types
**Prompts:** 3 templates
