"""
Tests for MCP Tool Registry and Dynamic Tool Discovery.

Validates: Requirements 1B.1, 1B.2, 1B.3, 1B.5
"""

import sys
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.search.gateway import GatewayTool
from deepr.mcp.search.registry import (
    BM25Index,
    ToolRegistry,
    ToolSchema,
    create_default_registry,
)


class TestToolSchema:
    """Test ToolSchema dataclass."""

    def test_schema_tokenizes_on_creation(self):
        """Schema should auto-tokenize description."""
        schema = ToolSchema(
            name="test_tool", description="This is a test tool for research", input_schema={"type": "object"}
        )
        assert len(schema.tokens) > 0
        assert "test" in schema.tokens
        assert "research" in schema.tokens

    def test_schema_to_mcp_format(self):
        """Schema should convert to MCP format correctly."""
        schema = ToolSchema(
            name="my_tool", description="Does something", input_schema={"type": "object", "properties": {}}
        )
        mcp = schema.to_mcp_format()

        assert mcp["name"] == "my_tool"
        assert mcp["description"] == "Does something"
        assert "inputSchema" in mcp


class TestBM25Index:
    """Test BM25 search index."""

    def test_empty_corpus(self):
        """Empty corpus should return empty scores."""
        index = BM25Index()
        index.fit([])
        scores = index.get_scores(["test"])
        assert scores == []

    def test_single_document(self):
        """Single document should get non-zero score for matching query."""
        index = BM25Index()
        index.fit([["research", "deep", "analysis"]])
        scores = index.get_scores(["research"])
        assert len(scores) == 1
        assert scores[0] > 0

    def test_ranking_order(self):
        """More relevant documents should score higher."""
        index = BM25Index()
        index.fit(
            [["cat", "dog", "pet"], ["research", "analysis", "deep"], ["research", "research", "study", "analysis"]]
        )
        scores = index.get_scores(["research", "analysis"])

        # Third doc has more research terms, should score highest
        assert scores[2] > scores[1]
        # First doc has no matches, should score lowest
        assert scores[0] == 0


class TestToolRegistry:
    """Test ToolRegistry functionality."""

    def test_register_and_get(self):
        """Should register and retrieve tools."""
        registry = ToolRegistry()
        tool = ToolSchema(name="test_tool", description="A test tool", input_schema={"type": "object"})
        registry.register(tool)

        retrieved = registry.get("test_tool")
        assert retrieved is not None
        assert retrieved.name == "test_tool"

    def test_search_returns_relevant_tools(self):
        """Search should return tools matching query."""
        registry = ToolRegistry()
        registry.register_many(
            [
                ToolSchema("research_tool", "Submit research jobs", {"type": "object"}),
                ToolSchema("expert_tool", "Query domain experts", {"type": "object"}),
                ToolSchema("status_tool", "Check job status", {"type": "object"}),
            ]
        )

        results = registry.search("research")
        assert len(results) > 0
        assert any(t.name == "research_tool" for t in results)

    def test_search_respects_limit(self):
        """Search should respect limit parameter."""
        registry = create_default_registry()

        results = registry.search("tool", limit=2)
        assert len(results) <= 2

    def test_count(self):
        """Count should return number of registered tools."""
        registry = ToolRegistry()
        assert registry.count() == 0

        registry.register(ToolSchema("t1", "desc", {"type": "object"}))
        assert registry.count() == 1

        registry.register(ToolSchema("t2", "desc", {"type": "object"}))
        assert registry.count() == 2

    def test_all_tools(self):
        """all_tools should return all registered tools."""
        registry = ToolRegistry()
        registry.register_many(
            [
                ToolSchema("t1", "desc1", {"type": "object"}),
                ToolSchema("t2", "desc2", {"type": "object"}),
            ]
        )

        all_tools = registry.all_tools()
        assert len(all_tools) == 2


class TestDefaultRegistry:
    """Test default registry creation."""

    def test_default_registry_has_tools(self):
        """Default registry should have standard Deepr tools."""
        registry = create_default_registry()
        assert registry.count() >= 5

    def test_default_registry_has_research_tools(self):
        """Default registry should have research tools."""
        registry = create_default_registry()
        assert registry.get("deepr_research") is not None
        assert registry.get("deepr_check_status") is not None
        assert registry.get("deepr_get_result") is not None

    def test_default_registry_has_expert_tools(self):
        """Default registry should have expert tools."""
        registry = create_default_registry()
        assert registry.get("deepr_list_experts") is not None
        assert registry.get("deepr_query_expert") is not None


class TestGatewayTool:
    """Test Gateway Tool for dynamic discovery."""

    def test_gateway_schema_is_valid(self):
        """Gateway schema should be valid MCP format."""
        schema = GatewayTool.get_gateway_schema()

        assert "name" in schema
        assert schema["name"] == "deepr_tool_search"
        assert "description" in schema
        assert "inputSchema" in schema

    def test_gateway_search_returns_tools(self):
        """Gateway search should return matching tools."""
        registry = create_default_registry()
        gateway = GatewayTool(registry)

        result = gateway.search("research")

        assert "tools" in result
        assert "count" in result
        assert result["count"] > 0

    def test_gateway_search_empty_query(self):
        """Gateway should handle empty query gracefully."""
        registry = create_default_registry()
        gateway = GatewayTool(registry)

        result = gateway.search("")

        assert "error" in result
        assert result["tools"] == []

    def test_gateway_search_limit_clamped(self):
        """Gateway should clamp limit to valid range."""
        registry = create_default_registry()
        gateway = GatewayTool(registry)

        # Too high
        result = gateway.search("tool", limit=100)
        assert result["count"] <= 10

        # Too low
        result = gateway.search("tool", limit=0)
        assert result["count"] >= 0


class TestContextReduction:
    """Test context reduction from gateway pattern."""

    def test_context_savings_calculated(self):
        """Should calculate context savings."""
        registry = create_default_registry()
        gateway = GatewayTool(registry)

        savings = gateway.estimate_context_savings()

        assert "all_tools_tokens" in savings
        assert "gateway_only_tokens" in savings
        assert "savings_percentage" in savings

    def test_gateway_reduces_context(self):
        """Gateway pattern should reduce context significantly."""
        registry = create_default_registry()
        gateway = GatewayTool(registry)

        savings = gateway.estimate_context_savings()

        # Gateway should be much smaller than all tools
        assert savings["gateway_only_tokens"] < savings["all_tools_tokens"]
        # Should achieve some savings (at least 20% with small registry)
        assert savings["savings_percentage"] > 20


class TestPropertyBased:
    """Property-based tests for registry."""

    @given(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()))
    @settings(max_examples=50)
    def test_search_never_crashes(self, query: str):
        """
        Property: Search should never crash regardless of query.
        Validates: Requirements 1B.3
        """
        registry = create_default_registry()
        result = registry.search(query)

        assert isinstance(result, list)

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=30)
    def test_search_respects_any_limit(self, limit: int):
        """
        Property: Search should respect any positive limit.
        """
        registry = create_default_registry()
        result = registry.search("tool", limit=limit)

        assert len(result) <= limit

    @given(
        st.text(min_size=3, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz"),
        st.text(min_size=10, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyz "),
    )
    @settings(max_examples=30)
    def test_registered_tool_is_searchable(self, name: str, description: str):
        """
        Property: Any registered tool should be findable by its description.
        """
        assume(name.strip() and description.strip())
        # Ensure description has words longer than 2 chars (tokenizer filter)
        words = [w for w in description.strip().split() if len(w) > 2]
        assume(len(words) > 0)

        registry = ToolRegistry()
        tool = ToolSchema(
            name=name.strip().replace(" ", "_"), description=description.strip(), input_schema={"type": "object"}
        )
        registry.register(tool)

        # Search by a word from description (must be > 2 chars)
        results = registry.search(words[0], limit=10)
        # Should find the tool we just registered
        assert any(t.name == tool.name for t in results)
