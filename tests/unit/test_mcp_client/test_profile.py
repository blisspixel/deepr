"""Tests for MCP client profiles and fail-closed budget propagation."""

from unittest.mock import MagicMock

import pytest

from deepr.mcp.client.budget_propagator import BudgetPropagator
from deepr.mcp.client.profile import MCPClientProfile


class TestMCPClientProfile:
    def test_defaults(self):
        p = MCPClientProfile(name="test")
        assert p.name == "test"
        assert p.timeout == 30.0
        assert p.max_retries == 1
        assert p.budget_limit == 0.0
        assert p.free_tools == []
        assert p.circuit_breaker_threshold == 5

    def test_to_dict(self):
        p = MCPClientProfile(name="my-server", command="python", args=["-m", "server"])
        d = p.to_dict()
        assert d["name"] == "my-server"
        assert d["command"] == "python"
        assert d["args"] == ["-m", "server"]

    def test_from_dict(self):
        data = {
            "name": "test-server",
            "command": "node",
            "args": ["server.js"],
            "timeout": 60.0,
            "max_retries": 5,
            "budget_limit": 10.0,
            "tags": ["production"],
        }
        p = MCPClientProfile.from_dict(data)
        assert p.name == "test-server"
        assert p.command == "node"
        assert p.timeout == 60.0
        assert p.max_retries == 5
        assert p.budget_limit == 5.0
        assert p.tags == ["production"]

    def test_from_dict_defaults(self):
        p = MCPClientProfile.from_dict({"name": "minimal"})
        assert p.timeout == 30.0
        assert p.max_retries == 1
        assert p.env == {}

    def test_roundtrip(self):
        original = MCPClientProfile(
            name="round",
            command="python",
            timeout=45.0,
            budget_limit=5.0,
            free_tools=["health"],
        )
        restored = MCPClientProfile.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.timeout == original.timeout
        assert restored.budget_limit == original.budget_limit
        assert restored.free_tools == ["health"]


class TestMCPBudgetPropagation:
    def setup_method(self):
        self.propagator = BudgetPropagator(MagicMock(), MagicMock())

    def test_zero_profile_budget_permits_only_zero_dollar_call(self):
        profile = MCPClientProfile(name="zero")

        assert self.propagator.check_budget(profile, 0.0, 5.0).allowed
        assert not self.propagator.check_budget(profile, 0.01, 5.0).allowed
        assert self.propagator.get_budget_param(profile, 5.0) == 0.0

    def test_negative_budget_values_fail_closed(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            MCPClientProfile(name="invalid", budget_limit=-1.0)
