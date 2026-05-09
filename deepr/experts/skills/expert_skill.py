"""External tool trigger logic for expert skill invocations.

Determines when experts should invoke external MCP tools based on
research context (domain detection, knowledge gaps) and dispatches
calls with retry logic and approval enforcement.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from deepr.mcp.client.errors import MCPErrorCode, StructuredError
from deepr.mcp.client.profile import MCPClientProfile

logger = logging.getLogger(__name__)

# Pattern for detecting company domains in text
_DOMAIN_PATTERN = re.compile(r"\b([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.[a-zA-Z]{2,})\b")

# Error codes that are retryable
_RETRYABLE_CODES = frozenset(
    {
        MCPErrorCode.TIMEOUT,
        MCPErrorCode.CONNECTION_LOST,
        MCPErrorCode.SERVER_ERROR,
    }
)


@dataclass
class ToolInfo:
    """Information about an available external tool."""

    server_name: str
    tool_name: str
    description: str = ""
    categories: list[str] = field(default_factory=list)


@dataclass
class ToolSuggestion:
    """A suggested external tool invocation."""

    server_name: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    estimated_cost: float = 0.0
    requires_approval: bool = False


@dataclass
class KnowledgeGap:
    """A gap in expert knowledge that might be filled by a tool."""

    category: str  # "infrastructure" | "academic" | "strategic"
    description: str
    priority: float = 0.5


@dataclass
class ResearchContext:
    """Context for determining tool triggers."""

    text: str = ""
    domains: list[str] = field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = field(default_factory=list)


# Category-to-tool mapping for knowledge gap matching
_GAP_TOOL_MAP: dict[str, list[str]] = {
    "infrastructure": ["domain_lookup", "batch_lookup", "dns_check"],
    "academic": ["paper_search", "citation_lookup"],
    "strategic": ["company_analysis", "market_data"],
}


class ExpertSkillWrapper:
    """Trigger logic for expert-invoked external tool calls.

    Detects when external tools should be invoked based on research
    context (domain patterns, knowledge gaps) and dispatches calls
    with approval enforcement and retry logic.
    """

    def __init__(self, profile: MCPClientProfile) -> None:
        self._profile = profile

    def should_trigger(
        self,
        context: ResearchContext,
        available_tools: list[ToolInfo],
    ) -> list[ToolSuggestion]:
        """Determine which external tools to suggest.

        Checks for:
        1. Company domains in research text → domain_lookup
        2. Knowledge gaps matching available tool categories
        """
        suggestions: list[ToolSuggestion] = []
        tool_names = {t.tool_name for t in available_tools}

        # Domain detection
        domains = self._detect_domains(context)
        for domain in domains:
            if "domain_lookup" in tool_names:
                suggestions.append(
                    ToolSuggestion(
                        server_name=self._profile.name,
                        tool_name="domain_lookup",
                        arguments={"domain": domain},
                        reason=f"Detected domain: {domain}",
                        requires_approval=self._needs_approval("domain_lookup"),
                    )
                )

        # Knowledge gap matching
        for gap in context.knowledge_gaps:
            matching_tools = _GAP_TOOL_MAP.get(gap.category, [])
            for tool_name in matching_tools:
                if tool_name in tool_names:
                    suggestions.append(
                        ToolSuggestion(
                            server_name=self._profile.name,
                            tool_name=tool_name,
                            arguments={},
                            reason=f"Knowledge gap: {gap.description}",
                            requires_approval=self._needs_approval(tool_name),
                        )
                    )

        return suggestions

    def _detect_domains(self, context: ResearchContext) -> list[str]:
        """Extract company domains from research context text."""
        if context.domains:
            return context.domains
        if not context.text:
            return []
        matches = _DOMAIN_PATTERN.findall(context.text)
        # Filter out common non-company domains
        return [m for m in matches if not m.startswith("e.g")]

    def _needs_approval(self, tool_name: str) -> bool:
        """Check if a tool requires approval based on profile config.

        - In auto_approve → no approval needed
        - In require_approval → approval required
        - In neither → default to requiring approval
        """
        if tool_name in self._profile.auto_approve:
            return False
        if tool_name in self._profile.require_approval:
            return True
        # Default: require approval
        return True

    async def execute(
        self,
        suggestion: ToolSuggestion,
        call_tool_fn: Any,
    ) -> StructuredError | dict[str, Any]:
        """Execute a tool call with one automatic retry for retryable errors.

        Args:
            suggestion: The tool suggestion to execute.
            call_tool_fn: Async callable(server_name, tool_name, arguments) -> result.

        Returns:
            Tool result dict on success, or StructuredError on failure.
        """
        max_attempts = 2  # Initial + one retry
        last_error: StructuredError | None = None

        for attempt in range(max_attempts):
            try:
                result = await call_tool_fn(
                    suggestion.server_name,
                    suggestion.tool_name,
                    suggestion.arguments,
                )
                if isinstance(result, StructuredError):
                    last_error = result
                    if result.retryable and attempt < max_attempts - 1:
                        logger.debug(
                            "Retrying %s/%s (attempt %d): %s",
                            suggestion.server_name,
                            suggestion.tool_name,
                            attempt + 1,
                            result.message,
                        )
                        continue
                    return result
                return result
            except Exception as e:
                last_error = StructuredError(
                    code=MCPErrorCode.SERVER_ERROR,
                    message=str(e),
                    retryable=attempt < max_attempts - 1,
                )
                if attempt < max_attempts - 1:
                    continue

        # All retries exhausted — return last error (never None here)
        assert last_error is not None
        return last_error
