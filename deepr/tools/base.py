"""Base classes for tool system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    """Result from tool execution."""

    success: bool
    data: Any
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class Tool(ABC):
    """
    Abstract base class for tools.

    Tools provide capabilities to AI agents (web search, file access, etc.)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for AI context."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON schema for tool parameters."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass

    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert to OpenAI tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_tool(self) -> Dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolExecutor:
    """
    Executes tools and manages tool lifecycle.

    Provides unified interface regardless of provider.
    """

    def __init__(self, tools: Optional[List[Tool]] = None):
        self.tools: Dict[str, Tool] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: Tool):
        """Register a tool for execution."""
        self.tools[tool.name] = tool

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute a tool by name."""
        if tool_name not in self.tools:
            return ToolResult(success=False, data=None, error=f"Tool '{tool_name}' not found")

        try:
            return await self.tools[tool_name].execute(**kwargs)
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Tool execution failed: {e}")

    def get_tool_definitions(self, format: str = "openai") -> List[Dict[str, Any]]:
        """
        Get tool definitions for provider.

        Args:
            format: "openai" or "anthropic"
        """
        if format == "openai":
            return [tool.to_openai_tool() for tool in self.tools.values()]
        elif format == "anthropic":
            return [tool.to_anthropic_tool() for tool in self.tools.values()]
        else:
            raise ValueError(f"Unknown format: {format}")
