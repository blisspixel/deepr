# MCP Client Mode Architecture

> Design document for Deepr as an MCP tool consumer.
> STATUS: Interface definitions implemented, connections not yet built.

## Overview

Deepr currently acts as an **MCP server** (providing tools to agents). This design adds **MCP client** capability -- Deepr can also consume tools from other MCP servers.

```
                  ┌─────────────────────┐
                  │    Agent (Claude)    │
                  │                     │
                  │  calls Deepr tools  │
                  └─────────┬───────────┘
                            │ MCP (server mode)
                  ┌─────────▼───────────┐
                  │     Deepr Server    │
                  │                     │
                  │  SearchBackend      │──── MCP client ──── Brave Search MCP
                  │  BrowserBackend     │──── MCP client ──── Puppeteer MCP
                  │  SubAgentManager    │──── MCP client ──── Cheap model MCP
                  └─────────────────────┘
```

## Interface Definitions

### SearchBackend Protocol

```python
# deepr/tools/search_backend.py

class SearchBackend(Protocol):
    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]: ...
    async def health_check(self) -> bool: ...
    @property
    def name(self) -> str: ...
```

Implementations:
- `BuiltinSearchBackend` - wraps existing `WebSearchTool` (implemented)
- `MCPSearchBackend` - delegates to MCP search server (stub)

### BrowserBackend Protocol

```python
# deepr/tools/browser_backend.py

class BrowserBackend(Protocol):
    async def fetch_page(self, url: str) -> PageContent: ...
    async def health_check(self) -> bool: ...
    @property
    def name(self) -> str: ...
```

Implementations:
- `BuiltinBrowserBackend` - wraps existing scraper (implemented)
- `MCPBrowserBackend` - delegates to Puppeteer/Playwright MCP (stub)

### MCPClientManager (future)

```python
# deepr/mcp/client.py (not yet created)

class MCPClientManager:
    async def connect(self, config: ServerConfig) -> MCPConnection: ...
    async def discover_tools(self, conn: MCPConnection) -> list[ToolSchema]: ...
    async def call_tool(self, conn: MCPConnection, name: str, args: dict) -> Any: ...
    async def disconnect(self, conn: MCPConnection) -> None: ...
```

## Configuration Design

```yaml
# In deepr config or .env
mcp_client:
  search_backend: "builtin"       # or "brave-mcp", "tavily-mcp"
  browser_backend: "builtin"      # or "puppeteer-mcp", "playwright-mcp"
  connections:
    brave-search:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-brave-search"]
      env:
        BRAVE_API_KEY: "${BRAVE_API_KEY}"
    puppeteer:
      command: "npx"
      args: ["-y", "@anthropic/mcp-puppeteer"]
```

## Migration Path

1. **Current**: `WebSearchTool` called directly in research orchestrator
2. **Phase 1**: Wrap in `BuiltinSearchBackend` (adapter pattern)
3. **Phase 2**: Add `MCPSearchBackend` that connects to MCP servers
4. **Phase 3**: Config-driven backend selection

The adapter pattern ensures no breaking changes to existing code.

## Sub-Agent Composition

For cost optimization, Deepr can offload work to cheaper models:

```
Research Orchestrator
  ├── Expensive model (GPT-5.2) → Planning, synthesis
  ├── Medium model (o4-mini)    → Deep research
  └── Cheap model (grok-4-fast) → Summarization, reading
```

Each model can be exposed as a separate MCP server, and Deepr's orchestrator routes tasks based on complexity.

## Implementation Priority

1. SearchBackend protocol + BuiltinSearchBackend (done)
2. BrowserBackend protocol + BuiltinBrowserBackend (done)
3. MCPClientManager connection lifecycle
4. Brave Search MCP integration
5. Puppeteer MCP integration
6. Sub-agent composition
