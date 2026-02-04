"""Elicitation router for multi-target user input.

Routes elicitation requests to the appropriate target (CLI, web, MCP client)
based on availability and preference.

Usage:
    from deepr.mcp.state.elicitation_router import ElicitationRouter

    router = ElicitationRouter()

    # Register handlers
    router.register_handler(ElicitationTarget.CLI, cli_handler)
    router.register_handler(ElicitationTarget.MCP, mcp_handler)

    # Route a request
    response = await router.route(request, preferred_target=ElicitationTarget.AUTO)
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable, Awaitable
from enum import Enum


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class ElicitationTarget(Enum):
    """Target for elicitation requests."""
    AUTO = "auto"  # Automatically detect best target
    CLI = "cli"  # Command line interface
    WEB = "web"  # Web dashboard
    MCP = "mcp"  # MCP client (Claude Desktop, etc.)
    NONE = "none"  # No elicitation available


@dataclass
class ElicitationRequest:
    """A request for user input."""
    id: str
    message: str
    schema: Dict[str, Any]
    timeout_seconds: int = 300
    context: Dict[str, Any] = field(default_factory=dict)
    priority: str = "normal"  # normal, high, critical
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "message": self.message,
            "schema": self.schema,
            "timeout_seconds": self.timeout_seconds,
            "context": self.context,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ElicitationResponse:
    """Response from user elicitation."""
    request_id: str
    response: Dict[str, Any]
    target: ElicitationTarget
    responded_at: datetime = field(default_factory=_utc_now)
    was_default: bool = False
    timeout_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "response": self.response,
            "target": self.target.value,
            "responded_at": self.responded_at.isoformat(),
            "was_default": self.was_default,
            "timeout_used": self.timeout_used,
        }


# Type for elicitation handler
ElicitationHandler = Callable[[ElicitationRequest], Awaitable[Optional[Dict[str, Any]]]]


class ElicitationRouter:
    """Routes elicitation requests to appropriate targets.

    Supports multiple targets with fallback and auto-detection.

    Attributes:
        handlers: Dict of target to handler function
        default_target: Default target when AUTO is selected
    """

    def __init__(
        self,
        default_target: ElicitationTarget = ElicitationTarget.MCP,
    ):
        """Initialize the router.

        Args:
            default_target: Default target for AUTO selection
        """
        self.handlers: Dict[ElicitationTarget, ElicitationHandler] = {}
        self.default_target = default_target
        self._available_targets: set = set()

    def register_handler(
        self,
        target: ElicitationTarget,
        handler: ElicitationHandler,
    ) -> None:
        """Register an elicitation handler for a target.

        Args:
            target: Target type
            handler: Async handler function
        """
        self.handlers[target] = handler
        self._available_targets.add(target)

    def unregister_handler(self, target: ElicitationTarget) -> None:
        """Unregister a handler.

        Args:
            target: Target to unregister
        """
        self.handlers.pop(target, None)
        self._available_targets.discard(target)

    async def route(
        self,
        request: ElicitationRequest,
        preferred_target: ElicitationTarget = ElicitationTarget.AUTO,
    ) -> ElicitationResponse:
        """Route an elicitation request.

        Args:
            request: Elicitation request
            preferred_target: Preferred target (AUTO to detect)

        Returns:
            ElicitationResponse with user's response
        """
        # Determine target
        target = self._resolve_target(preferred_target)

        if target == ElicitationTarget.NONE:
            # No handler available, return default response
            return ElicitationResponse(
                request_id=request.id,
                response=self._get_default_response(request),
                target=ElicitationTarget.NONE,
                was_default=True,
            )

        handler = self.handlers.get(target)
        if not handler:
            # Fallback to default response
            return ElicitationResponse(
                request_id=request.id,
                response=self._get_default_response(request),
                target=ElicitationTarget.NONE,
                was_default=True,
            )

        # Try to get response with timeout
        try:
            response = await asyncio.wait_for(
                handler(request),
                timeout=request.timeout_seconds,
            )

            if response is None:
                # Handler returned None, use default
                return ElicitationResponse(
                    request_id=request.id,
                    response=self._get_default_response(request),
                    target=target,
                    was_default=True,
                )

            return ElicitationResponse(
                request_id=request.id,
                response=response,
                target=target,
            )

        except asyncio.TimeoutError:
            # Timeout, use default response
            return ElicitationResponse(
                request_id=request.id,
                response=self._get_default_response(request),
                target=target,
                was_default=True,
                timeout_used=True,
            )
        except Exception as e:
            # Handler error, use default
            return ElicitationResponse(
                request_id=request.id,
                response={
                    "error": str(e),
                    **self._get_default_response(request),
                },
                target=target,
                was_default=True,
            )

    def detect_available_target(self) -> ElicitationTarget:
        """Detect the best available target.

        Returns:
            Best available ElicitationTarget
        """
        # Priority order: MCP > CLI > WEB > NONE
        priority = [
            ElicitationTarget.MCP,
            ElicitationTarget.CLI,
            ElicitationTarget.WEB,
        ]

        for target in priority:
            if target in self._available_targets:
                return target

        return ElicitationTarget.NONE

    def get_available_targets(self) -> List[ElicitationTarget]:
        """Get list of available targets.

        Returns:
            List of available targets
        """
        return list(self._available_targets)

    def _resolve_target(
        self,
        preferred: ElicitationTarget,
    ) -> ElicitationTarget:
        """Resolve actual target from preference.

        Args:
            preferred: Preferred target

        Returns:
            Resolved target
        """
        if preferred == ElicitationTarget.AUTO:
            return self.detect_available_target()

        if preferred in self._available_targets:
            return preferred

        # Fallback to auto-detect
        return self.detect_available_target()

    def _get_default_response(
        self,
        request: ElicitationRequest,
    ) -> Dict[str, Any]:
        """Get default response for a request.

        Args:
            request: Elicitation request

        Returns:
            Default response dict
        """
        schema = request.schema
        response = {}

        # Try to build sensible defaults from schema
        properties = schema.get("properties", {})

        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")

            if "default" in prop_schema:
                response[prop_name] = prop_schema["default"]
            elif "enum" in prop_schema:
                # Use first enum value as default
                response[prop_name] = prop_schema["enum"][0]
            elif prop_type == "boolean":
                response[prop_name] = False
            elif prop_type == "number":
                response[prop_name] = prop_schema.get("minimum", 0)
            elif prop_type == "string":
                response[prop_name] = ""
            elif prop_type == "array":
                response[prop_name] = []
            elif prop_type == "object":
                response[prop_name] = {}

        # Special handling for known request types
        if "decision" in properties:
            # Budget decision - default to abort for safety
            response["decision"] = "abort"
            response["reason"] = "No user input available (timeout or unavailable)"

        return response


# Convenience function for creating CLI handler
def create_cli_handler(
    prompt_func: Callable[[str], str],
) -> ElicitationHandler:
    """Create a CLI elicitation handler.

    Args:
        prompt_func: Function to prompt user for input

    Returns:
        ElicitationHandler function
    """
    async def handler(request: ElicitationRequest) -> Optional[Dict[str, Any]]:
        # Display message
        print(f"\n{request.message}\n")

        schema = request.schema
        response = {}

        for prop_name, prop_schema in schema.get("properties", {}).items():
            prop_type = prop_schema.get("type", "string")
            description = prop_schema.get("description", prop_name)

            if "enum" in prop_schema:
                options = prop_schema["enum"]
                print(f"Options for {prop_name}: {', '.join(options)}")

            try:
                user_input = prompt_func(f"{description}: ")

                if prop_type == "boolean":
                    response[prop_name] = user_input.lower() in ("yes", "y", "true", "1")
                elif prop_type == "number":
                    response[prop_name] = float(user_input) if user_input else 0
                else:
                    response[prop_name] = user_input

            except (EOFError, KeyboardInterrupt):
                return None

        return response

    return handler
