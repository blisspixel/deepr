"""Human-in-the-loop approval flows for expert chat operations.

Provides tiered cost approval:
- AUTO_APPROVE: free/cheap operations proceed immediately
- NOTIFY: show cost estimate, proceed unless budget critically low
- CONFIRM: block until user explicitly approves or denies
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ApprovalTier(Enum):
    AUTO_APPROVE = "auto"
    NOTIFY = "notify"
    CONFIRM = "confirm"


@dataclass
class ApprovalRequest:
    """A pending approval request."""

    tool_name: str
    query: str
    estimated_cost: float
    budget_remaining: float
    tier: ApprovalTier
    request_id: str = ""


@dataclass
class ApprovalResponse:
    """User's response to an approval request."""

    approved: bool
    request_id: str = ""


# Default policies: (tool_name, tier, cost_threshold_for_upgrade)
DEFAULT_POLICIES: list[tuple[str, ApprovalTier, float]] = [
    ("search_knowledge_base", ApprovalTier.AUTO_APPROVE, 0.0),
    ("standard_research", ApprovalTier.AUTO_APPROVE, 0.0),
    ("deep_research", ApprovalTier.NOTIFY, 1.0),  # CONFIRM if cost > $1
]


class ApprovalManager:
    """Manages approval tiers for tool operations."""

    def __init__(self, policies: list[tuple[str, ApprovalTier, float]] | None = None):
        self._policies: dict[str, tuple[ApprovalTier, float]] = {}
        for tool_name, tier, threshold in policies or DEFAULT_POLICIES:
            self._policies[tool_name] = (tier, threshold)

        # For blocking on CONFIRM tier
        self._pending: dict[str, threading.Event] = {}
        self._responses: dict[str, bool] = {}

    def check_approval(
        self,
        tool_name: str,
        estimated_cost: float = 0.0,
        budget_remaining: float = float("inf"),
    ) -> ApprovalTier:
        """Determine the approval tier for a tool call.

        Returns the effective tier after applying cost-based escalation.
        """
        base_tier, threshold = self._policies.get(tool_name, (ApprovalTier.AUTO_APPROVE, 0.0))

        # Escalate NOTIFY to CONFIRM if cost exceeds threshold
        if base_tier == ApprovalTier.NOTIFY and estimated_cost > threshold:
            return ApprovalTier.CONFIRM

        # Escalate NOTIFY to CONFIRM if budget critically low
        if base_tier == ApprovalTier.NOTIFY and budget_remaining < estimated_cost * 2:
            return ApprovalTier.CONFIRM

        return base_tier

    def create_request(
        self,
        tool_name: str,
        query: str,
        estimated_cost: float,
        budget_remaining: float,
    ) -> ApprovalRequest:
        """Create an approval request."""
        import uuid

        tier = self.check_approval(tool_name, estimated_cost, budget_remaining)
        request_id = uuid.uuid4().hex[:12]

        req = ApprovalRequest(
            tool_name=tool_name,
            query=query,
            estimated_cost=estimated_cost,
            budget_remaining=budget_remaining,
            tier=tier,
            request_id=request_id,
        )

        if tier == ApprovalTier.CONFIRM:
            self._pending[request_id] = threading.Event()

        return req

    def wait_for_response(self, request_id: str, timeout: float = 60.0) -> bool:
        """Block until the user responds to a CONFIRM request.

        Returns True if approved, False if denied or timed out.
        """
        event = self._pending.get(request_id)
        if event is None:
            return True  # Not a CONFIRM request, auto-approve

        got_response = event.wait(timeout=timeout)
        self._pending.pop(request_id, None)

        if not got_response:
            logger.warning("Approval request %s timed out", request_id)
            self._responses.pop(request_id, None)  # Clean up stale responses
            return False

        return self._responses.pop(request_id, False)

    def respond(self, request_id: str, approved: bool) -> None:
        """Submit a user response to a pending CONFIRM request."""
        self._responses[request_id] = approved
        event = self._pending.get(request_id)
        if event:
            event.set()

    def get_cost_estimate(self, tool_name: str) -> float:
        """Get a rough cost estimate for a tool."""
        estimates = {
            "search_knowledge_base": 0.0,
            "standard_research": 0.0,
            "deep_research": 0.20,
        }
        return estimates.get(tool_name, 0.0)
