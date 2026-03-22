"""Permission boundaries for tool execution and budget enforcement.

Defines PermissionPolicy (what's allowed) and PermissionEnforcer (checks
before every tool/research operation). Supports tool allowlists, budget
caps, and write controls.

Usage::

    policy = PermissionPolicy(
        tool_allowlist=["search_knowledge_base", "standard_research"],
        budget_per_session=10.0,
        allow_write=False,
    )
    enforcer = PermissionEnforcer(policy)

    result = enforcer.check("deep_research", estimated_cost=0.50)
    if not result.allowed:
        print(f"Blocked: {result.reason}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PermissionPolicy:
    """Defines what operations are permitted.

    A policy with empty allowlist permits everything (open mode).
    A policy with explicit allowlist only permits listed tools.
    """

    # Tool access
    tool_allowlist: list[str] = field(default_factory=list)
    tool_denylist: list[str] = field(default_factory=list)

    # Budget
    budget_per_session: float = 0.0  # 0 = unlimited
    budget_per_operation: float = 0.0  # 0 = unlimited

    # Write controls
    allow_write: bool = True  # File writes, expert modifications
    allow_external_requests: bool = True  # Outbound HTTP, MCP calls
    allow_code_execution: bool = False  # Python code_interpreter tools

    # Provider restrictions
    allowed_providers: list[str] = field(default_factory=list)  # Empty = all
    blocked_models: list[str] = field(default_factory=list)

    # Metadata
    name: str = "default"
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tool_allowlist": self.tool_allowlist,
            "tool_denylist": self.tool_denylist,
            "budget_per_session": self.budget_per_session,
            "budget_per_operation": self.budget_per_operation,
            "allow_write": self.allow_write,
            "allow_external_requests": self.allow_external_requests,
            "allow_code_execution": self.allow_code_execution,
            "allowed_providers": self.allowed_providers,
            "blocked_models": self.blocked_models,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionPolicy:
        return cls(
            name=data.get("name", "default"),
            description=data.get("description", ""),
            tool_allowlist=data.get("tool_allowlist", []),
            tool_denylist=data.get("tool_denylist", []),
            budget_per_session=float(data.get("budget_per_session", 0.0)),
            budget_per_operation=float(data.get("budget_per_operation", 0.0)),
            allow_write=bool(data.get("allow_write", True)),
            allow_external_requests=bool(data.get("allow_external_requests", True)),
            allow_code_execution=bool(data.get("allow_code_execution", False)),
            allowed_providers=data.get("allowed_providers", []),
            blocked_models=data.get("blocked_models", []),
        )

    @classmethod
    def restrictive(cls) -> PermissionPolicy:
        """Create a restrictive policy — read-only, no external requests, no code."""
        return cls(
            name="restrictive",
            description="Read-only, no external requests, no code execution",
            tool_allowlist=["search_knowledge_base"],
            allow_write=False,
            allow_external_requests=False,
            allow_code_execution=False,
            budget_per_session=1.0,
            budget_per_operation=0.10,
        )

    @classmethod
    def open(cls) -> PermissionPolicy:
        """Create an open policy — everything allowed."""
        return cls(name="open", description="All operations permitted")


@dataclass
class PermissionCheckResult:
    """Result of a permission check."""

    allowed: bool
    reason: str = ""
    policy_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "policy_name": self.policy_name,
        }


class PermissionEnforcer:
    """Checks operations against a PermissionPolicy.

    Call ``check()`` before tool execution, ``check_budget()`` before
    cost-incurring operations, and ``check_provider()`` before routing.
    """

    def __init__(self, policy: PermissionPolicy):
        self.policy = policy
        self._session_spent: float = 0.0

    def check_tool(self, tool_name: str) -> PermissionCheckResult:
        """Check if a tool is permitted by the policy."""
        p = self.policy

        # Denylist takes precedence
        if tool_name in p.tool_denylist:
            return PermissionCheckResult(
                allowed=False,
                reason=f"Tool '{tool_name}' is in denylist",
                policy_name=p.name,
            )

        # Allowlist (if set) must contain the tool
        if p.tool_allowlist and tool_name not in p.tool_allowlist:
            return PermissionCheckResult(
                allowed=False,
                reason=f"Tool '{tool_name}' not in allowlist: {p.tool_allowlist}",
                policy_name=p.name,
            )

        # Code execution check
        if not p.allow_code_execution and tool_name in ("code_interpreter", "skill_tool_call"):
            return PermissionCheckResult(
                allowed=False,
                reason="Code execution not permitted by policy",
                policy_name=p.name,
            )

        return PermissionCheckResult(allowed=True, policy_name=p.name)

    def check_budget(self, estimated_cost: float) -> PermissionCheckResult:
        """Check if an operation fits within budget constraints."""
        p = self.policy

        if p.budget_per_operation > 0 and estimated_cost > p.budget_per_operation:
            return PermissionCheckResult(
                allowed=False,
                reason=f"Cost ${estimated_cost:.2f} exceeds per-operation limit ${p.budget_per_operation:.2f}",
                policy_name=p.name,
            )

        if p.budget_per_session > 0:
            remaining = p.budget_per_session - self._session_spent
            if estimated_cost > remaining:
                return PermissionCheckResult(
                    allowed=False,
                    reason=f"Cost ${estimated_cost:.2f} exceeds session remaining ${remaining:.2f}",
                    policy_name=p.name,
                )

        return PermissionCheckResult(allowed=True, policy_name=p.name)

    def check_provider(self, provider: str, model: str = "") -> PermissionCheckResult:
        """Check if a provider/model is permitted."""
        p = self.policy

        if p.allowed_providers and provider not in p.allowed_providers:
            return PermissionCheckResult(
                allowed=False,
                reason=f"Provider '{provider}' not in allowed list: {p.allowed_providers}",
                policy_name=p.name,
            )

        if model and model in p.blocked_models:
            return PermissionCheckResult(
                allowed=False,
                reason=f"Model '{model}' is blocked by policy",
                policy_name=p.name,
            )

        return PermissionCheckResult(allowed=True, policy_name=p.name)

    def check_write(self) -> PermissionCheckResult:
        """Check if write operations are permitted."""
        if not self.policy.allow_write:
            return PermissionCheckResult(
                allowed=False,
                reason="Write operations not permitted by policy",
                policy_name=self.policy.name,
            )
        return PermissionCheckResult(allowed=True, policy_name=self.policy.name)

    def check_external(self) -> PermissionCheckResult:
        """Check if external requests (HTTP, MCP) are permitted."""
        if not self.policy.allow_external_requests:
            return PermissionCheckResult(
                allowed=False,
                reason="External requests not permitted by policy",
                policy_name=self.policy.name,
            )
        return PermissionCheckResult(allowed=True, policy_name=self.policy.name)

    def record_spend(self, cost: float) -> None:
        """Record actual spending against session budget."""
        self._session_spent += cost

    @property
    def session_spent(self) -> float:
        return self._session_spent

    @property
    def session_remaining(self) -> float:
        if self.policy.budget_per_session <= 0:
            return float("inf")
        return max(0.0, self.policy.budget_per_session - self._session_spent)
