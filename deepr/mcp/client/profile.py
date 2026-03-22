"""Configurable MCP client profiles.

Named presets for connecting to MCP servers with per-server settings
for transport, auth, retry, timeout, and budget propagation.

Profiles can be defined in config or constructed programmatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPClientProfile:
    """Configuration profile for an MCP server connection.

    Defines how to connect to and interact with a specific MCP server.
    Profiles are reusable — multiple experts/sessions can share one.

    Example::

        profile = MCPClientProfile(
            name="my-tool-server",
            command="python",
            args=["-m", "my_tool_server"],
            env={"API_KEY": "${MY_TOOL_API_KEY}"},
            timeout=60.0,
            max_retries=3,
            budget_limit=5.0,
        )
    """

    # Identity
    name: str
    description: str = ""

    # Transport (stdio)
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    # Connection settings
    timeout: float = 30.0  # Per-call timeout in seconds
    max_retries: int = 3
    retry_delay: float = 1.0  # Base delay for exponential backoff
    connect_timeout: float = 10.0  # Timeout for initial connection

    # Budget / cost
    budget_limit: float = 0.0  # Max spend through this server (0 = unlimited)
    cost_per_call: float = 0.0  # Estimated cost per tool call

    # Health
    circuit_breaker_threshold: int = 5  # Failures before circuit opens
    circuit_breaker_recovery: float = 60.0  # Seconds before retry after circuit opens

    # Metadata
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "command": self.command,
            "args": self.args,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "budget_limit": self.budget_limit,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPClientProfile:
        """Create a profile from a dict (e.g. loaded from config)."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            timeout=float(data.get("timeout", 30.0)),
            max_retries=int(data.get("max_retries", 3)),
            retry_delay=float(data.get("retry_delay", 1.0)),
            connect_timeout=float(data.get("connect_timeout", 10.0)),
            budget_limit=float(data.get("budget_limit", 0.0)),
            cost_per_call=float(data.get("cost_per_call", 0.0)),
            circuit_breaker_threshold=int(data.get("circuit_breaker_threshold", 5)),
            circuit_breaker_recovery=float(data.get("circuit_breaker_recovery", 60.0)),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
