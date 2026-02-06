"""Unit tests for elicitation router."""

import asyncio

import pytest

from deepr.mcp.state.elicitation_router import (
    ElicitationRequest,
    ElicitationResponse,
    ElicitationRouter,
    ElicitationTarget,
    create_cli_handler,
)


class TestElicitationRouter:
    """Tests for ElicitationRouter class."""

    def test_router_initialization(self):
        """Test router initialization."""
        router = ElicitationRouter()

        assert router.default_target == ElicitationTarget.MCP
        assert len(router.handlers) == 0

    def test_router_with_custom_default(self):
        """Test router with custom default target."""
        router = ElicitationRouter(default_target=ElicitationTarget.CLI)

        assert router.default_target == ElicitationTarget.CLI

    def test_register_handler(self):
        """Test registering a handler."""
        router = ElicitationRouter()

        async def mock_handler(request):
            return {"response": "test"}

        router.register_handler(ElicitationTarget.CLI, mock_handler)

        assert ElicitationTarget.CLI in router.handlers
        assert ElicitationTarget.CLI in router.get_available_targets()

    def test_unregister_handler(self):
        """Test unregistering a handler."""
        router = ElicitationRouter()

        async def mock_handler(request):
            return {}

        router.register_handler(ElicitationTarget.CLI, mock_handler)
        router.unregister_handler(ElicitationTarget.CLI)

        assert ElicitationTarget.CLI not in router.handlers


class TestElicitationRouting:
    """Tests for routing elicitation requests."""

    @pytest.mark.asyncio
    async def test_route_to_registered_handler(self):
        """Test routing to a registered handler."""
        router = ElicitationRouter()

        async def mock_handler(request):
            return {"decision": "approve", "handled_by": "mock"}

        router.register_handler(ElicitationTarget.CLI, mock_handler)

        request = ElicitationRequest(
            id="test_request",
            message="Test message",
            schema={"type": "object", "properties": {"decision": {"type": "string"}}},
        )

        response = await router.route(request, preferred_target=ElicitationTarget.CLI)

        assert response.response["handled_by"] == "mock"
        assert response.target == ElicitationTarget.CLI

    @pytest.mark.asyncio
    async def test_route_with_auto_detection(self):
        """Test routing with AUTO target detection."""
        router = ElicitationRouter()

        async def mcp_handler(request):
            return {"source": "mcp"}

        router.register_handler(ElicitationTarget.MCP, mcp_handler)

        request = ElicitationRequest(
            id="test",
            message="Test",
            schema={},
        )

        response = await router.route(request, preferred_target=ElicitationTarget.AUTO)

        assert response.target == ElicitationTarget.MCP

    @pytest.mark.asyncio
    async def test_route_fallback_to_default(self):
        """Test fallback to default response when no handler."""
        router = ElicitationRouter()

        request = ElicitationRequest(
            id="test",
            message="Test",
            schema={
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "enum": ["yes", "no"]},
                },
            },
        )

        response = await router.route(request, preferred_target=ElicitationTarget.CLI)

        assert response.was_default is True
        assert response.target == ElicitationTarget.NONE

    @pytest.mark.asyncio
    async def test_route_with_timeout(self):
        """Test routing with handler timeout."""
        router = ElicitationRouter()

        async def slow_handler(request):
            await asyncio.sleep(10)  # Slow handler
            return {"result": "done"}

        router.register_handler(ElicitationTarget.CLI, slow_handler)

        request = ElicitationRequest(
            id="test",
            message="Test",
            schema={},
            timeout_seconds=0.1,  # Very short timeout
        )

        response = await router.route(request, preferred_target=ElicitationTarget.CLI)

        assert response.was_default is True
        assert response.timeout_used is True


class TestDefaultResponses:
    """Tests for default response generation."""

    @pytest.mark.asyncio
    async def test_default_response_for_budget_decision(self):
        """Test default response for budget decision."""
        router = ElicitationRouter()

        request = ElicitationRequest(
            id="budget_test",
            message="Budget exceeded",
            schema={
                "type": "object",
                "properties": {
                    "decision": {
                        "type": "string",
                        "enum": ["approve_override", "optimize_for_cost", "abort"],
                    },
                    "reason": {"type": "string"},
                },
            },
        )

        response = await router.route(request, preferred_target=ElicitationTarget.CLI)

        # Default should be abort for safety
        assert response.response.get("decision") == "abort"

    @pytest.mark.asyncio
    async def test_default_response_for_boolean(self):
        """Test default response for boolean field."""
        router = ElicitationRouter()

        request = ElicitationRequest(
            id="bool_test",
            message="Confirm action",
            schema={
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean"},
                },
            },
        )

        response = await router.route(request, preferred_target=ElicitationTarget.CLI)

        # Default boolean should be False for safety
        assert response.response.get("confirm") is False

    @pytest.mark.asyncio
    async def test_default_response_for_enum(self):
        """Test default response uses first enum value."""
        router = ElicitationRouter()

        request = ElicitationRequest(
            id="enum_test",
            message="Select option",
            schema={
                "type": "object",
                "properties": {
                    "option": {"type": "string", "enum": ["option_a", "option_b"]},
                },
            },
        )

        response = await router.route(request, preferred_target=ElicitationTarget.CLI)

        assert response.response.get("option") == "option_a"


class TestTargetDetection:
    """Tests for target detection."""

    def test_detect_available_target_priority(self):
        """Test that detection follows priority order."""
        router = ElicitationRouter()

        async def handler(request):
            return {}

        # Register CLI and WEB, not MCP
        router.register_handler(ElicitationTarget.CLI, handler)
        router.register_handler(ElicitationTarget.WEB, handler)

        detected = router.detect_available_target()

        # CLI has higher priority than WEB
        assert detected == ElicitationTarget.CLI

    def test_detect_no_available_target(self):
        """Test detection with no handlers."""
        router = ElicitationRouter()

        detected = router.detect_available_target()

        assert detected == ElicitationTarget.NONE

    def test_get_available_targets(self):
        """Test getting list of available targets."""
        router = ElicitationRouter()

        async def handler(request):
            return {}

        router.register_handler(ElicitationTarget.CLI, handler)
        router.register_handler(ElicitationTarget.MCP, handler)

        targets = router.get_available_targets()

        assert ElicitationTarget.CLI in targets
        assert ElicitationTarget.MCP in targets
        assert len(targets) == 2


class TestElicitationRequest:
    """Tests for ElicitationRequest dataclass."""

    def test_request_creation(self):
        """Test creating an ElicitationRequest."""
        request = ElicitationRequest(
            id="test_id",
            message="Please provide input",
            schema={"type": "object"},
            timeout_seconds=60,
            context={"job_id": "job123"},
            priority="high",
        )

        assert request.id == "test_id"
        assert request.message == "Please provide input"
        assert request.timeout_seconds == 60
        assert request.context["job_id"] == "job123"
        assert request.priority == "high"

    def test_request_to_dict(self):
        """Test serializing ElicitationRequest."""
        request = ElicitationRequest(
            id="test",
            message="Test",
            schema={"type": "object"},
        )

        data = request.to_dict()

        assert data["id"] == "test"
        assert data["message"] == "Test"
        assert "schema" in data
        assert "created_at" in data


class TestElicitationResponse:
    """Tests for ElicitationResponse dataclass."""

    def test_response_creation(self):
        """Test creating an ElicitationResponse."""
        response = ElicitationResponse(
            request_id="req123",
            response={"decision": "approve"},
            target=ElicitationTarget.CLI,
        )

        assert response.request_id == "req123"
        assert response.response["decision"] == "approve"
        assert response.target == ElicitationTarget.CLI
        assert response.was_default is False

    def test_response_to_dict(self):
        """Test serializing ElicitationResponse."""
        response = ElicitationResponse(
            request_id="req123",
            response={"value": 42},
            target=ElicitationTarget.MCP,
            was_default=True,
        )

        data = response.to_dict()

        assert data["request_id"] == "req123"
        assert data["response"]["value"] == 42
        assert data["target"] == "mcp"
        assert data["was_default"] is True


class TestCLIHandler:
    """Tests for CLI handler creation."""

    def test_create_cli_handler(self):
        """Test creating a CLI handler."""

        def mock_prompt(msg):
            return "user_input"

        handler = create_cli_handler(mock_prompt)

        assert callable(handler)

    @pytest.mark.asyncio
    async def test_cli_handler_processes_input(self):
        """Test that CLI handler processes user input."""
        responses = iter(["test_value"])

        def mock_prompt(msg):
            return next(responses)

        handler = create_cli_handler(mock_prompt)

        request = ElicitationRequest(
            id="test",
            message="Enter value",
            schema={
                "type": "object",
                "properties": {
                    "value": {"type": "string", "description": "A value"},
                },
            },
        )

        result = await handler(request)

        assert result["value"] == "test_value"
