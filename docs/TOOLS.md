# Deepr Tool System

Unified tool architecture for AI agents across providers.

## Overview

Deepr's tool system provides **real, executable capabilities** to AI agents during research:
- Web search (Brave, Tavily, DuckDuckGo)
- Future: Document analysis, code execution, database queries, MCP servers

**Key Insight:** OpenAI's Deep Research is turnkey (submit → wait → results). Anthropic's Extended Thinking requires **we manage the agentic loop ourselves**. Tools enable that.

## Architecture

### Tool Interface

```python
from deepr.tools import Tool, ToolResult

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "What this tool does"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        # Execute and return result
        return ToolResult(success=True, data=result)
```

### Tool Executor

Manages tool lifecycle and execution:

```python
from deepr.tools import ToolRegistry

# Get default tools
executor = ToolRegistry.create_executor(
    web_search=True,
    backend="auto"  # brave, tavily, duckduckgo, auto
)

# Execute a tool
result = await executor.execute("web_search", query="Latest AI news")
```

### Provider Integration

Tools work with both OpenAI and Anthropic:

```python
# OpenAI format
tools = executor.get_tool_definitions(format="openai")
# Returns: [{"type": "function", "function": {...}}]

# Anthropic format
tools = executor.get_tool_definitions(format="anthropic")
# Returns: [{"name": "...", "description": "...", "input_schema": {...}}]
```

## Web Search Tool

Multi-backend web search with automatic fallback.

### Backends

1. **Brave Search** (recommended)
   - Most accurate, fast
   - Requires API key: `BRAVE_API_KEY`
   - Get key: https://brave.com/search/api/

2. **Tavily** (alternative)
   - Good quality, research-focused
   - Requires API key: `TAVILY_API_KEY`
   - Get key: https://tavily.com/

3. **DuckDuckGo** (free fallback)
   - No API key needed
   - Install: `pip install duckduckgo-search`
   - Lower quality but works everywhere

### Configuration

```bash
# .env file
BRAVE_API_KEY=your_brave_key_here
TAVILY_API_KEY=your_tavily_key_here

# Or use DuckDuckGo (free)
pip install duckduckgo-search
```

### Usage

```python
from deepr.tools import WebSearchTool

tool = WebSearchTool(backend="auto")  # Try all backends
result = await tool.execute(query="Latest AI research", num_results=5)

if result.success:
    for item in result.data:
        print(f"{item['title']}: {item['url']}")
```

## Anthropic Provider Integration

Anthropic provider uses tools for **agentic research workflow**:

1. **Extended Thinking** - Claude plans research approach
2. **Tool Calls** - Claude searches web for info
3. **Synthesis** - Claude integrates findings into report

Example workflow:

```
User: "Research latest AI trends"

Turn 1:
  Claude (thinking): "I need current information. Let me search."
  Claude (action): web_search("AI trends 2025")
  System: Returns 5 search results

Turn 2:
  Claude (thinking): "Good overview, but need more on specific companies"
  Claude (action): web_search("OpenAI Anthropic Google AI 2025")
  System: Returns 5 search results

Turn 3:
  Claude (thinking): "Now I have enough info to synthesize"
  Claude (output): Comprehensive report with sources
```

This is **explicit agentic control** - we see every tool call, every decision.

## Observability

Tool calls are logged for transparency:

```markdown
## Tool Usage
<details><summary>View tool calls</summary>

1. **web_search**
   - Input: `{"query": "AI trends 2025"}`
   - Success: true

2. **web_search**
   - Input: `{"query": "OpenAI Anthropic Google AI 2025"}`
   - Success: true
</details>
```

This supports "Glass Box Transparency" principle - show ALL work.

## Future: MCP Integration

**Model Context Protocol (MCP)** servers provide local tools:
- Claude Code's WebFetch, Bash, FileSystem tools
- Custom MCP servers for domain-specific tasks
- Standardized protocol for tool discovery

```python
# Future implementation
from deepr.tools import MCPWebSearchTool

tool = MCPWebSearchTool()  # Uses local MCP server
result = await tool.execute(query="...")
```

## Adding New Tools

1. Create tool class implementing `Tool` interface
2. Register in `ToolRegistry`
3. Update provider to expose tool

Example - Database query tool:

```python
class DatabaseTool(Tool):
    @property
    def name(self) -> str:
        return "query_database"

    @property
    def description(self) -> str:
        return "Query the research database for prior findings"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query"}
            }
        }

    async def execute(self, query: str) -> ToolResult:
        # Execute query
        results = await db.execute(query)
        return ToolResult(success=True, data=results)
```

## Why This Matters

**OpenAI approach:** Turnkey but opaque
- Submit prompt → wait → get report
- No visibility into search process
- Can't control tool execution

**Deepr approach:** Transparent and controllable
- See every tool call
- Control tool availability
- Audit decision process
- Supports "Design for Trust" principles

This aligns with philosophy: **Trust through transparency, free speech for AI perspectives.**
