"""
Human-in-the-Loop Elicitation for MCP.

Implements the elicitation/create protocol for requesting structured
user input when decisions require human judgment (e.g., budget overrides).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Callable, Awaitable
from datetime import datetime
import asyncio
import uuid


class BudgetDecision(Enum):
    """User decisions for budget limit scenarios."""
    
    APPROVE_OVERRIDE = "approve_override"
    OPTIMIZE_FOR_COST = "optimize_for_cost"
    ABORT = "abort"


class ElicitationStatus(Enum):
    """Status of an elicitation request."""
    
    PENDING = "pending"
    RESPONDED = "responded"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ElicitationRequest:
    """
    A request for structured user input.
    
    Follows MCP elicitation/create protocol with JSON Schema
    for defining expected response structure.
    """
    
    id: str
    message: str
    schema: dict
    timeout_seconds: int = 300
    created_at: datetime = field(default_factory=datetime.now)
    status: ElicitationStatus = ElicitationStatus.PENDING
    response: Optional[dict] = None
    
    def to_jsonrpc(self) -> dict:
        """Convert to JSON-RPC elicitation/create request."""
        return {
            "jsonrpc": "2.0",
            "method": "elicitation/create",
            "params": {
                "id": self.id,
                "message": self.message,
                "requestedSchema": self.schema
            },
            "id": self.id
        }
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "message": self.message,
            "schema": self.schema,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "response": self.response
        }


@dataclass
class BudgetElicitationContext:
    """Context for a budget decision elicitation."""
    
    job_id: str
    estimated_cost: float
    budget_limit: float
    current_model: str
    alternative_models: list[str] = field(default_factory=list)
    partial_results_available: bool = False


# Type alias for notification callback
NotificationCallback = Callable[[dict], Awaitable[None]]


class ElicitationHandler:
    """
    Handles human-in-the-loop elicitation requests.
    
    Manages the lifecycle of elicitation requests, including:
    - Creating structured input requests
    - Waiting for user responses
    - Handling timeouts
    - Processing budget decisions
    """
    
    # JSON Schema for budget decisions
    BUDGET_DECISION_SCHEMA = {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["approve_override", "optimize_for_cost", "abort"],
                "description": "How to proceed with the research"
            },
            "new_budget": {
                "type": "number",
                "minimum": 0,
                "description": "New budget limit if approving override"
            },
            "reason": {
                "type": "string",
                "description": "Optional reason for the decision"
            }
        },
        "required": ["decision"]
    }
    
    def __init__(self, notification_callback: Optional[NotificationCallback] = None):
        """
        Initialize the elicitation handler.
        
        Args:
            notification_callback: Async function to send JSON-RPC notifications
        """
        self._pending: dict[str, ElicitationRequest] = {}
        self._response_events: dict[str, asyncio.Event] = {}
        self._notification_callback = notification_callback
    
    def create_budget_elicitation(
        self,
        job_id: str,
        estimated_cost: float,
        budget_limit: float,
        current_model: str = "o4-mini",
        timeout_seconds: int = 300
    ) -> ElicitationRequest:
        """
        Create a budget decision elicitation request.
        
        Args:
            job_id: Research job identifier
            estimated_cost: Estimated cost of the research
            budget_limit: Current budget limit
            current_model: Model being used
            timeout_seconds: How long to wait for response
        
        Returns:
            ElicitationRequest ready to send
        """
        request_id = f"budget_{job_id}_{uuid.uuid4().hex[:8]}"
        
        message = (
            f"Research estimated at ${estimated_cost:.2f} exceeds "
            f"budget of ${budget_limit:.2f}.\n\n"
            f"Current model: {current_model}\n"
            f"Options:\n"
            f"  - approve_override: Continue with original plan\n"
            f"  - optimize_for_cost: Switch to cheaper models\n"
            f"  - abort: Cancel and return partial results"
        )
        
        request = ElicitationRequest(
            id=request_id,
            message=message,
            schema=self.BUDGET_DECISION_SCHEMA,
            timeout_seconds=timeout_seconds
        )
        
        self._pending[request_id] = request
        self._response_events[request_id] = asyncio.Event()
        
        return request
    
    def create_custom_elicitation(
        self,
        message: str,
        schema: dict,
        request_id: Optional[str] = None,
        timeout_seconds: int = 300
    ) -> ElicitationRequest:
        """
        Create a custom elicitation request.
        
        Args:
            message: Message to display to user
            schema: JSON Schema for expected response
            request_id: Optional custom ID
            timeout_seconds: How long to wait for response
        
        Returns:
            ElicitationRequest ready to send
        """
        if request_id is None:
            request_id = f"elicit_{uuid.uuid4().hex[:8]}"
        
        request = ElicitationRequest(
            id=request_id,
            message=message,
            schema=schema,
            timeout_seconds=timeout_seconds
        )
        
        self._pending[request_id] = request
        self._response_events[request_id] = asyncio.Event()
        
        return request
    
    async def send_elicitation(self, request: ElicitationRequest) -> None:
        """
        Send an elicitation request via the notification callback.
        
        Args:
            request: The elicitation request to send
        """
        if self._notification_callback:
            await self._notification_callback(request.to_jsonrpc())
    
    async def wait_for_response(
        self,
        request_id: str,
        timeout: Optional[float] = None,
        use_default_on_timeout: bool = True,
    ) -> Optional[dict]:
        """
        Wait for a response to an elicitation request.

        Args:
            request_id: ID of the elicitation request
            timeout: Override timeout (uses request timeout if None)
            use_default_on_timeout: If True, return default response on timeout

        Returns:
            Response dict or None if timeout/cancelled

        Note:
            On timeout, the request status is set to TIMEOUT and resources
            are cleaned up to prevent memory leaks. If use_default_on_timeout
            is True, a sensible default response is returned instead of None.
        """
        request = self._pending.get(request_id)
        if not request:
            return None

        event = self._response_events.get(request_id)
        if not event:
            return None

        wait_timeout = timeout or request.timeout_seconds

        try:
            await asyncio.wait_for(event.wait(), timeout=wait_timeout)
            return request.response
        except asyncio.TimeoutError:
            request.status = ElicitationStatus.TIMEOUT
            # Clean up the event to prevent memory leak
            self._response_events.pop(request_id, None)

            # Return default response if requested
            if use_default_on_timeout:
                default = self._get_default_response(request)
                default["_timeout"] = True
                default["_timeout_seconds"] = wait_timeout
                return default

            return None

    def _get_default_response(self, request: ElicitationRequest) -> dict:
        """
        Get a sensible default response for an elicitation request.

        Used for graceful degradation when user doesn't respond in time.

        Args:
            request: The elicitation request

        Returns:
            Default response dict based on schema
        """
        schema = request.schema
        response = {}

        properties = schema.get("properties", {})

        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")

            # Use explicit default if provided
            if "default" in prop_schema:
                response[prop_name] = prop_schema["default"]
                continue

            # Use first enum value
            if "enum" in prop_schema:
                enum_values = prop_schema["enum"]
                # Prefer safe options like "abort", "skip", "cancel"
                safe_options = ["abort", "skip", "cancel", "no", "deny"]
                for safe in safe_options:
                    if safe in enum_values:
                        response[prop_name] = safe
                        break
                else:
                    response[prop_name] = enum_values[0]
                continue

            # Type-based defaults
            if prop_type == "boolean":
                response[prop_name] = False
            elif prop_type == "number":
                response[prop_name] = prop_schema.get("minimum", 0)
            elif prop_type == "integer":
                response[prop_name] = prop_schema.get("minimum", 0)
            elif prop_type == "string":
                response[prop_name] = ""
            elif prop_type == "array":
                response[prop_name] = []
            elif prop_type == "object":
                response[prop_name] = {}
            else:
                response[prop_name] = None

        # Special handling for known decision types
        if "decision" in properties:
            response["decision"] = "abort"
            response["reason"] = "Timeout - no user response received"

        return response
    
    def submit_response(self, request_id: str, response: dict) -> bool:
        """
        Submit a response to an elicitation request.
        
        Args:
            request_id: ID of the elicitation request
            response: User's response matching the schema
        
        Returns:
            True if response accepted, False if request not found
        """
        request = self._pending.get(request_id)
        if not request:
            return False
        
        if request.status != ElicitationStatus.PENDING:
            return False
        
        request.response = response
        request.status = ElicitationStatus.RESPONDED
        
        event = self._response_events.get(request_id)
        if event:
            event.set()
        
        return True
    
    def cancel_elicitation(self, request_id: str) -> bool:
        """
        Cancel a pending elicitation request.
        
        Args:
            request_id: ID of the elicitation request
        
        Returns:
            True if cancelled, False if not found or already completed
        """
        request = self._pending.get(request_id)
        if not request:
            return False
        
        if request.status != ElicitationStatus.PENDING:
            return False
        
        request.status = ElicitationStatus.CANCELLED
        
        event = self._response_events.get(request_id)
        if event:
            event.set()
        
        return True
    
    def get_pending_requests(self) -> list[ElicitationRequest]:
        """Get all pending elicitation requests."""
        return [
            r for r in self._pending.values()
            if r.status == ElicitationStatus.PENDING
        ]
    
    def get_request(self, request_id: str) -> Optional[ElicitationRequest]:
        """Get an elicitation request by ID."""
        return self._pending.get(request_id)
    
    def parse_budget_decision(self, response: dict) -> tuple[BudgetDecision, Optional[float]]:
        """
        Parse a budget decision response.
        
        Args:
            response: Response dict from user
        
        Returns:
            Tuple of (decision, new_budget or None)
        """
        decision_str = response.get("decision", "abort")
        new_budget = response.get("new_budget")
        
        try:
            decision = BudgetDecision(decision_str)
        except ValueError:
            decision = BudgetDecision.ABORT
        
        return decision, new_budget
    
    def cleanup(self, request_id: str) -> None:
        """
        Clean up resources for a completed elicitation.
        
        Args:
            request_id: ID of the elicitation request
        """
        self._pending.pop(request_id, None)
        self._response_events.pop(request_id, None)


class CostOptimizer:
    """
    Handles OPTIMIZE_FOR_COST decisions by adjusting research parameters.
    """
    
    # Model cost tiers (cost per 1M tokens, approximate)
    MODEL_COSTS = {
        "o3": 15.00,
        "o4-mini": 3.00,
        "grok-4-fast": 0.60,
        "gemini-flash": 0.075,
        "grok-3-mini": 0.30,
    }
    
    # Model capability tiers
    MODEL_CAPABILITIES = {
        "o3": {"reasoning": "excellent", "speed": "slow", "depth": "maximum"},
        "o4-mini": {"reasoning": "good", "speed": "medium", "depth": "high"},
        "grok-4-fast": {"reasoning": "good", "speed": "fast", "depth": "medium"},
        "gemini-flash": {"reasoning": "basic", "speed": "very_fast", "depth": "low"},
        "grok-3-mini": {"reasoning": "basic", "speed": "fast", "depth": "low"},
    }
    
    def suggest_cheaper_model(
        self,
        current_model: str,
        target_budget: float,
        estimated_tokens: int
    ) -> Optional[str]:
        """
        Suggest a cheaper model that fits the budget.
        
        Args:
            current_model: Currently selected model
            target_budget: Budget to stay within
            estimated_tokens: Estimated token usage
        
        Returns:
            Suggested model name or None if no suitable option
        """
        current_cost = self.MODEL_COSTS.get(current_model, 1.0)
        
        # Sort models by cost (cheapest first)
        sorted_models = sorted(
            self.MODEL_COSTS.items(),
            key=lambda x: x[1]
        )
        
        for model_name, cost_per_million in sorted_models:
            if model_name == current_model:
                continue
            
            estimated_cost = (estimated_tokens / 1_000_000) * cost_per_million
            
            if estimated_cost <= target_budget:
                return model_name
        
        return None
    
    def calculate_optimized_config(
        self,
        current_model: str,
        current_iterations: int,
        target_budget: float,
        estimated_tokens_per_iteration: int
    ) -> dict:
        """
        Calculate optimized configuration to fit budget.
        
        Args:
            current_model: Currently selected model
            current_iterations: Current max iterations
            target_budget: Budget to stay within
            estimated_tokens_per_iteration: Tokens per iteration
        
        Returns:
            Dict with optimized model and iterations
        """
        # Try switching to cheaper model first
        total_tokens = current_iterations * estimated_tokens_per_iteration
        cheaper_model = self.suggest_cheaper_model(
            current_model, target_budget, total_tokens
        )
        
        if cheaper_model:
            return {
                "model": cheaper_model,
                "max_iterations": current_iterations,
                "strategy": "model_switch",
                "estimated_cost": self._estimate_cost(
                    cheaper_model, total_tokens
                )
            }
        
        # If no cheaper model works, reduce iterations
        current_cost_per_million = self.MODEL_COSTS.get(current_model, 1.0)
        cost_per_iteration = (
            estimated_tokens_per_iteration / 1_000_000
        ) * current_cost_per_million
        
        if cost_per_iteration > 0:
            max_affordable_iterations = int(target_budget / cost_per_iteration)
            max_affordable_iterations = max(1, max_affordable_iterations)
            
            return {
                "model": current_model,
                "max_iterations": min(max_affordable_iterations, current_iterations),
                "strategy": "reduce_iterations",
                "estimated_cost": max_affordable_iterations * cost_per_iteration
            }
        
        return {
            "model": current_model,
            "max_iterations": 1,
            "strategy": "minimum",
            "estimated_cost": 0.0
        }
    
    def _estimate_cost(self, model: str, tokens: int) -> float:
        """Estimate cost for a model and token count."""
        cost_per_million = self.MODEL_COSTS.get(model, 1.0)
        return (tokens / 1_000_000) * cost_per_million
    
    def get_model_info(self, model: str) -> dict:
        """Get information about a model."""
        return {
            "name": model,
            "cost_per_million_tokens": self.MODEL_COSTS.get(model, 0.0),
            "capabilities": self.MODEL_CAPABILITIES.get(model, {})
        }
