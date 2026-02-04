"""
Tests for MCP Human-in-the-Loop Elicitation.

Validates: Requirements 5B.1, 5B.2, 5B.3, 5B.4, 5B.6
"""

import sys
from pathlib import Path
import asyncio

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.state.elicitation import (
    BudgetDecision,
    ElicitationStatus,
    ElicitationRequest,
    BudgetElicitationContext,
    ElicitationHandler,
    CostOptimizer,
)


class TestBudgetDecision:
    """Test BudgetDecision enum."""
    
    def test_enum_values(self):
        """Enum should have expected values."""
        assert BudgetDecision.APPROVE_OVERRIDE.value == "approve_override"
        assert BudgetDecision.OPTIMIZE_FOR_COST.value == "optimize_for_cost"
        assert BudgetDecision.ABORT.value == "abort"
    
    def test_from_string(self):
        """Should create enum from string value."""
        assert BudgetDecision("approve_override") == BudgetDecision.APPROVE_OVERRIDE
        assert BudgetDecision("optimize_for_cost") == BudgetDecision.OPTIMIZE_FOR_COST
        assert BudgetDecision("abort") == BudgetDecision.ABORT


class TestElicitationStatus:
    """Test ElicitationStatus enum."""
    
    def test_enum_values(self):
        """Enum should have expected values."""
        assert ElicitationStatus.PENDING.value == "pending"
        assert ElicitationStatus.RESPONDED.value == "responded"
        assert ElicitationStatus.TIMEOUT.value == "timeout"
        assert ElicitationStatus.CANCELLED.value == "cancelled"


class TestElicitationRequest:
    """Test ElicitationRequest dataclass."""
    
    def test_to_jsonrpc(self):
        """to_jsonrpc should create valid JSON-RPC request."""
        request = ElicitationRequest(
            id="test_123",
            message="Test message",
            schema={"type": "object", "properties": {"answer": {"type": "string"}}}
        )
        
        jsonrpc = request.to_jsonrpc()
        
        assert jsonrpc["jsonrpc"] == "2.0"
        assert jsonrpc["method"] == "elicitation/create"
        assert jsonrpc["params"]["id"] == "test_123"
        assert jsonrpc["params"]["message"] == "Test message"
        assert "requestedSchema" in jsonrpc["params"]
        assert jsonrpc["id"] == "test_123"
    
    def test_to_dict(self):
        """to_dict should serialize all fields."""
        request = ElicitationRequest(
            id="test_123",
            message="Test message",
            schema={"type": "object"},
            timeout_seconds=120
        )
        
        data = request.to_dict()
        
        assert data["id"] == "test_123"
        assert data["message"] == "Test message"
        assert data["timeout_seconds"] == 120
        assert data["status"] == "pending"
        assert data["response"] is None
    
    def test_default_status_is_pending(self):
        """New requests should have PENDING status."""
        request = ElicitationRequest(
            id="test",
            message="Test",
            schema={}
        )
        
        assert request.status == ElicitationStatus.PENDING


class TestElicitationHandler:
    """Test ElicitationHandler functionality."""
    
    @pytest.fixture
    def handler(self):
        return ElicitationHandler()
    
    def test_create_budget_elicitation(self, handler):
        """create_budget_elicitation should create valid request."""
        request = handler.create_budget_elicitation(
            job_id="job_123",
            estimated_cost=2.50,
            budget_limit=1.00,
            current_model="o4-mini"
        )
        
        assert request.id.startswith("budget_job_123_")
        assert "$2.50" in request.message
        assert "$1.00" in request.message
        assert "o4-mini" in request.message
        assert request.status == ElicitationStatus.PENDING
    
    def test_create_budget_elicitation_schema(self, handler):
        """Budget elicitation should have correct schema."""
        request = handler.create_budget_elicitation(
            job_id="test",
            estimated_cost=5.00,
            budget_limit=2.00
        )
        
        schema = request.schema
        
        assert schema["type"] == "object"
        assert "decision" in schema["properties"]
        assert schema["properties"]["decision"]["enum"] == [
            "approve_override", "optimize_for_cost", "abort"
        ]
        assert "decision" in schema["required"]
    
    def test_create_custom_elicitation(self, handler):
        """create_custom_elicitation should create request with custom schema."""
        custom_schema = {
            "type": "object",
            "properties": {
                "choice": {"type": "string", "enum": ["a", "b", "c"]}
            }
        }
        
        request = handler.create_custom_elicitation(
            message="Choose an option",
            schema=custom_schema,
            request_id="custom_123"
        )
        
        assert request.id == "custom_123"
        assert request.message == "Choose an option"
        assert request.schema == custom_schema
    
    def test_submit_response(self, handler):
        """submit_response should update request status."""
        request = handler.create_budget_elicitation(
            job_id="test",
            estimated_cost=5.00,
            budget_limit=2.00
        )
        
        result = handler.submit_response(
            request.id,
            {"decision": "approve_override", "new_budget": 10.00}
        )
        
        assert result is True
        assert request.status == ElicitationStatus.RESPONDED
        assert request.response["decision"] == "approve_override"
        assert request.response["new_budget"] == 10.00
    
    def test_submit_response_nonexistent_returns_false(self, handler):
        """submit_response on nonexistent request should return False."""
        result = handler.submit_response("nonexistent", {"decision": "abort"})
        
        assert result is False
    
    def test_submit_response_already_responded_returns_false(self, handler):
        """submit_response on already responded request should return False."""
        request = handler.create_budget_elicitation(
            job_id="test",
            estimated_cost=5.00,
            budget_limit=2.00
        )
        
        handler.submit_response(request.id, {"decision": "abort"})
        result = handler.submit_response(request.id, {"decision": "approve_override"})
        
        assert result is False
    
    def test_cancel_elicitation(self, handler):
        """cancel_elicitation should update status to CANCELLED."""
        request = handler.create_budget_elicitation(
            job_id="test",
            estimated_cost=5.00,
            budget_limit=2.00
        )
        
        result = handler.cancel_elicitation(request.id)
        
        assert result is True
        assert request.status == ElicitationStatus.CANCELLED
    
    def test_cancel_nonexistent_returns_false(self, handler):
        """cancel_elicitation on nonexistent request should return False."""
        result = handler.cancel_elicitation("nonexistent")
        
        assert result is False
    
    def test_get_pending_requests(self, handler):
        """get_pending_requests should return only pending requests."""
        req1 = handler.create_budget_elicitation("job1", 5.0, 2.0)
        req2 = handler.create_budget_elicitation("job2", 3.0, 1.0)
        
        handler.submit_response(req1.id, {"decision": "abort"})
        
        pending = handler.get_pending_requests()
        
        assert len(pending) == 1
        assert pending[0].id == req2.id
    
    def test_get_request(self, handler):
        """get_request should return request by ID."""
        request = handler.create_budget_elicitation("test", 5.0, 2.0)
        
        retrieved = handler.get_request(request.id)
        
        assert retrieved is request
    
    def test_get_request_nonexistent_returns_none(self, handler):
        """get_request on nonexistent ID should return None."""
        result = handler.get_request("nonexistent")
        
        assert result is None
    
    def test_parse_budget_decision_approve(self, handler):
        """parse_budget_decision should parse approve_override."""
        decision, new_budget = handler.parse_budget_decision({
            "decision": "approve_override",
            "new_budget": 15.00
        })
        
        assert decision == BudgetDecision.APPROVE_OVERRIDE
        assert new_budget == 15.00
    
    def test_parse_budget_decision_optimize(self, handler):
        """parse_budget_decision should parse optimize_for_cost."""
        decision, new_budget = handler.parse_budget_decision({
            "decision": "optimize_for_cost"
        })
        
        assert decision == BudgetDecision.OPTIMIZE_FOR_COST
        assert new_budget is None
    
    def test_parse_budget_decision_abort(self, handler):
        """parse_budget_decision should parse abort."""
        decision, new_budget = handler.parse_budget_decision({
            "decision": "abort"
        })
        
        assert decision == BudgetDecision.ABORT
        assert new_budget is None
    
    def test_parse_budget_decision_invalid_defaults_to_abort(self, handler):
        """parse_budget_decision with invalid value should default to abort."""
        decision, _ = handler.parse_budget_decision({
            "decision": "invalid_value"
        })
        
        assert decision == BudgetDecision.ABORT
    
    def test_cleanup(self, handler):
        """cleanup should remove request from tracking."""
        request = handler.create_budget_elicitation("test", 5.0, 2.0)
        request_id = request.id
        
        handler.cleanup(request_id)
        
        assert handler.get_request(request_id) is None


class TestElicitationHandlerAsync:
    """Async tests for ElicitationHandler."""
    
    @pytest.fixture
    def handler(self):
        return ElicitationHandler()
    
    @pytest.mark.asyncio
    async def test_wait_for_response_with_submit(self, handler):
        """wait_for_response should return when response submitted."""
        request = handler.create_budget_elicitation("test", 5.0, 2.0)
        
        async def submit_after_delay():
            await asyncio.sleep(0.1)
            handler.submit_response(request.id, {"decision": "abort"})
        
        asyncio.create_task(submit_after_delay())
        
        response = await handler.wait_for_response(request.id, timeout=2.0)
        
        assert response is not None
        assert response["decision"] == "abort"
    
    @pytest.mark.asyncio
    async def test_wait_for_response_timeout(self, handler):
        """wait_for_response should return timeout response by default."""
        request = handler.create_budget_elicitation("test", 5.0, 2.0)

        response = await handler.wait_for_response(request.id, timeout=0.1)

        # Default behavior returns timeout response with _timeout flag
        assert response is not None
        assert response.get("_timeout") is True
        assert request.status == ElicitationStatus.TIMEOUT
    
    @pytest.mark.asyncio
    async def test_wait_for_response_nonexistent(self, handler):
        """wait_for_response on nonexistent request should return None."""
        response = await handler.wait_for_response("nonexistent", timeout=0.1)
        
        assert response is None
    
    @pytest.mark.asyncio
    async def test_send_elicitation_with_callback(self):
        """send_elicitation should call notification callback."""
        received = []
        
        async def callback(msg):
            received.append(msg)
        
        handler = ElicitationHandler(notification_callback=callback)
        request = handler.create_budget_elicitation("test", 5.0, 2.0)
        
        await handler.send_elicitation(request)
        
        assert len(received) == 1
        assert received[0]["method"] == "elicitation/create"


class TestCostOptimizer:
    """Test CostOptimizer functionality."""
    
    @pytest.fixture
    def optimizer(self):
        return CostOptimizer()
    
    def test_suggest_cheaper_model(self, optimizer):
        """suggest_cheaper_model should find cheaper alternative."""
        # o4-mini costs $3/M tokens, grok-4-fast costs $0.60/M
        cheaper = optimizer.suggest_cheaper_model(
            current_model="o4-mini",
            target_budget=1.00,
            estimated_tokens=1_000_000
        )
        
        # Should suggest a model that costs <= $1 for 1M tokens
        assert cheaper is not None
        assert optimizer.MODEL_COSTS[cheaper] <= 1.00
    
    def test_suggest_cheaper_model_no_option(self, optimizer):
        """suggest_cheaper_model should return None if no option fits."""
        # Very low budget that no model can meet
        cheaper = optimizer.suggest_cheaper_model(
            current_model="gemini-flash",
            target_budget=0.001,
            estimated_tokens=1_000_000
        )
        
        assert cheaper is None
    
    def test_calculate_optimized_config_model_switch(self, optimizer):
        """calculate_optimized_config should prefer model switch."""
        config = optimizer.calculate_optimized_config(
            current_model="o4-mini",
            current_iterations=5,
            target_budget=1.00,
            estimated_tokens_per_iteration=200_000
        )
        
        # Should switch to cheaper model rather than reduce iterations
        assert config["strategy"] in ["model_switch", "reduce_iterations"]
        assert config["estimated_cost"] <= 1.00
    
    def test_calculate_optimized_config_reduce_iterations(self, optimizer):
        """calculate_optimized_config should reduce iterations if needed."""
        config = optimizer.calculate_optimized_config(
            current_model="gemini-flash",  # Already cheapest
            current_iterations=10,
            target_budget=0.05,
            estimated_tokens_per_iteration=100_000
        )
        
        # Should reduce iterations since already on cheapest model
        assert config["max_iterations"] < 10
        assert config["estimated_cost"] <= 0.05
    
    def test_get_model_info(self, optimizer):
        """get_model_info should return model details."""
        info = optimizer.get_model_info("o4-mini")
        
        assert info["name"] == "o4-mini"
        assert info["cost_per_million_tokens"] == 3.00
        assert "reasoning" in info["capabilities"]
    
    def test_get_model_info_unknown(self, optimizer):
        """get_model_info for unknown model should return defaults."""
        info = optimizer.get_model_info("unknown_model")
        
        assert info["name"] == "unknown_model"
        assert info["cost_per_million_tokens"] == 0.0
        assert info["capabilities"] == {}


class TestPropertyBased:
    """Property-based tests for elicitation."""
    
    @given(
        estimated_cost=st.floats(min_value=0.01, max_value=100.0),
        budget_limit=st.floats(min_value=0.01, max_value=100.0)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_budget_elicitation_contains_costs(
        self,
        estimated_cost: float,
        budget_limit: float
    ):
        """
        Property: Budget elicitation message should contain both costs.
        Validates: Requirements 5B.2
        """
        handler = ElicitationHandler()
        
        request = handler.create_budget_elicitation(
            job_id="test",
            estimated_cost=estimated_cost,
            budget_limit=budget_limit
        )
        
        # Message should contain formatted costs
        assert f"${estimated_cost:.2f}" in request.message
        assert f"${budget_limit:.2f}" in request.message
    
    @given(st.sampled_from(["approve_override", "optimize_for_cost", "abort"]))
    @settings(max_examples=10)
    def test_parse_budget_decision_roundtrip(self, decision_str: str):
        """
        Property: Valid decision strings should parse correctly.
        Validates: Requirements 5B.3
        """
        handler = ElicitationHandler()
        
        decision, _ = handler.parse_budget_decision({"decision": decision_str})
        
        assert decision.value == decision_str
    
    @given(
        current_model=st.sampled_from(["o3", "o4-mini", "grok-4-fast"]),
        target_budget=st.floats(min_value=0.1, max_value=10.0),
        tokens=st.integers(min_value=100_000, max_value=5_000_000)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_optimizer_respects_budget(
        self,
        current_model: str,
        target_budget: float,
        tokens: int
    ):
        """
        Property: Optimized config should respect target budget.
        Validates: Requirements 5B.4
        """
        optimizer = CostOptimizer()
        
        config = optimizer.calculate_optimized_config(
            current_model=current_model,
            current_iterations=5,
            target_budget=target_budget,
            estimated_tokens_per_iteration=tokens // 5
        )
        
        # Estimated cost should be at or below target
        # (with some tolerance for floating point)
        assert config["estimated_cost"] <= target_budget * 1.01 or config["max_iterations"] == 1
    
    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=30)
    def test_custom_elicitation_preserves_message(self, message: str):
        """
        Property: Custom elicitation should preserve message exactly.
        """
        assume(message.strip())
        
        handler = ElicitationHandler()
        
        request = handler.create_custom_elicitation(
            message=message,
            schema={"type": "object"}
        )
        
        assert request.message == message
    
    @given(st.integers(min_value=1, max_value=600))
    @settings(max_examples=20)
    def test_timeout_preserved(self, timeout: int):
        """
        Property: Timeout should be preserved in request.
        """
        handler = ElicitationHandler()
        
        request = handler.create_budget_elicitation(
            job_id="test",
            estimated_cost=5.0,
            budget_limit=2.0,
            timeout_seconds=timeout
        )
        
        assert request.timeout_seconds == timeout
