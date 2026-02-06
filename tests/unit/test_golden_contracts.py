"""Golden contract tests for CLI output and MCP schema stability.

These tests ensure that CLI output and MCP schemas remain stable
across versions, preventing breaking changes to user-facing interfaces.

Usage:
    pytest tests/unit/test_golden_contracts.py -v

    # Update golden files (when intentional changes are made):
    pytest tests/unit/test_golden_contracts.py --update-golden
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

# Golden file directory
GOLDEN_DIR = Path(__file__).parent.parent / "data" / "golden"


def load_golden(filename: str) -> str:
    """Load a golden file."""
    path = GOLDEN_DIR / filename
    if not path.exists():
        pytest.skip(f"Golden file not found: {path}")
    return path.read_text(encoding="utf-8")


def save_golden(filename: str, content: str):
    """Save content to a golden file."""
    path = GOLDEN_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def normalize_output(output: str) -> str:
    """Normalize output for comparison (strip trailing whitespace, normalize newlines)."""
    lines = output.strip().split("\n")
    return "\n".join(line.rstrip() for line in lines)


class TestCLIGoldenContracts:
    """Golden contract tests for CLI output stability."""

    def test_help_output_structure(self):
        """Test that main help output has expected structure."""
        from deepr.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0

        # Check for essential commands
        essential_commands = [
            "research",
            "expert",
            "config",
            "help",
        ]

        for cmd in essential_commands:
            assert cmd in result.output, f"Missing essential command: {cmd}"

    def test_config_show_structure(self):
        """Test that config show has expected structure."""
        from deepr.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show"])

        # Should not error
        assert result.exit_code == 0

        # Should contain configuration sections
        assert "provider" in result.output.lower() or "config" in result.output.lower()

    def test_help_verbs_structure(self):
        """Test that help verbs has expected structure."""
        from deepr.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["help", "verbs"])

        assert result.exit_code == 0

        # Should contain intent categories
        intent_keywords = ["research", "learn", "make", "expert"]
        found = sum(1 for kw in intent_keywords if kw in result.output.lower())
        assert found >= 2, "Help verbs should contain intent categories"


class TestMCPSchemaGoldenContracts:
    """Golden contract tests for MCP schema stability."""

    def test_mcp_tools_schema_structure(self):
        """Test that MCP tools schema has expected structure."""
        golden = load_golden("mcp_tools_schema.json")
        schema = json.loads(golden)

        # Verify schema structure
        assert "tools" in schema
        assert isinstance(schema["tools"], list)

        # Verify each tool has required fields
        for tool in schema["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert "type" in tool["inputSchema"]

    def test_essential_mcp_tools_present(self):
        """Test that essential MCP tools are present."""
        golden = load_golden("mcp_tools_schema.json")
        schema = json.loads(golden)

        tool_names = {tool["name"] for tool in schema["tools"]}

        essential_tools = [
            "research",
            "list_experts",
            "query_expert",
        ]

        for tool in essential_tools:
            assert tool in tool_names, f"Missing essential MCP tool: {tool}"

    def test_mcp_tool_input_schemas_valid(self):
        """Test that MCP tool input schemas are valid JSON Schema."""
        golden = load_golden("mcp_tools_schema.json")
        schema = json.loads(golden)

        for tool in schema["tools"]:
            input_schema = tool["inputSchema"]

            # Must have type
            assert "type" in input_schema

            # If object type, should have properties
            if input_schema["type"] == "object":
                assert "properties" in input_schema

    def test_mcp_schema_version_present(self):
        """Test that MCP schema has version for compatibility tracking."""
        golden = load_golden("mcp_tools_schema.json")
        schema = json.loads(golden)

        assert "schema_version" in schema, "MCP schema should have version"
        # Version should be semver format
        version = schema["schema_version"]
        parts = version.split(".")
        assert len(parts) == 3, f"Version should be semver format: {version}"

    def test_mcp_tool_required_fields_valid(self):
        """Test that required fields in tool schemas are valid."""
        golden = load_golden("mcp_tools_schema.json")
        schema = json.loads(golden)

        for tool in schema["tools"]:
            input_schema = tool["inputSchema"]

            if "required" in input_schema:
                required = input_schema["required"]
                properties = input_schema.get("properties", {})

                # All required fields must be defined in properties
                for field in required:
                    assert field in properties, f"Tool {tool['name']}: required field '{field}' not in properties"

    def test_research_tool_schema_stability(self):
        """Test that research tool schema maintains backward compatibility."""
        golden = load_golden("mcp_tools_schema.json")
        schema = json.loads(golden)

        # Find research tool
        research_tool = None
        for tool in schema["tools"]:
            if tool["name"] == "research":
                research_tool = tool
                break

        assert research_tool is not None, "Research tool must exist"

        # Verify essential properties exist
        props = research_tool["inputSchema"]["properties"]
        assert "query" in props, "Research tool must have 'query' property"

        # Query must be required
        required = research_tool["inputSchema"].get("required", [])
        assert "query" in required, "Query must be required for research tool"

    def test_query_expert_tool_schema_stability(self):
        """Test that query_expert tool schema maintains backward compatibility."""
        golden = load_golden("mcp_tools_schema.json")
        schema = json.loads(golden)

        # Find query_expert tool
        query_tool = None
        for tool in schema["tools"]:
            if tool["name"] == "query_expert":
                query_tool = tool
                break

        assert query_tool is not None, "query_expert tool must exist"

        # Verify essential properties exist
        props = query_tool["inputSchema"]["properties"]
        assert "expert_name" in props, "query_expert must have 'expert_name' property"
        assert "question" in props, "query_expert must have 'question' property"

        # Both must be required
        required = query_tool["inputSchema"].get("required", [])
        assert "expert_name" in required, "expert_name must be required"
        assert "question" in required, "question must be required"


class TestQualityMetricsGoldenContracts:
    """Golden contract tests for quality metrics stability."""

    def test_evaluation_result_structure(self):
        """Test that EvaluationResult has expected fields."""

        from deepr.observability.quality_metrics import EvaluationResult

        result = EvaluationResult(
            example_id="test_001",
            category="simple_factual",
            citation_precision=1.0,
            citation_recall=1.0,
            citation_f1=1.0,
            answer_relevance=0.9,
            contains_expected=True,
            confidence=0.95,
            is_correct=True,
            brier_score=0.0025,
            quality_score=0.95,
        )

        # Verify to_dict has all expected fields
        d = result.to_dict()

        expected_fields = [
            "example_id",
            "category",
            "citation_precision",
            "citation_recall",
            "citation_f1",
            "answer_relevance",
            "contains_expected",
            "confidence",
            "is_correct",
            "brier_score",
            "quality_score",
            "timestamp",
        ]

        for field in expected_fields:
            assert field in d, f"Missing field in EvaluationResult: {field}"

    def test_metrics_summary_structure(self):
        """Test that MetricsSummary has expected fields."""
        from deepr.observability.quality_metrics import QualityMetrics

        metrics = QualityMetrics()

        # Add a sample result
        metrics.evaluate_response(
            example_id="test_001",
            category="simple_factual",
            response="Paris is the capital of France.",
            expected_contains=["Paris"],
            actual_citations=["wiki.md"],
            expected_citation_count=1,
            confidence=0.95,
            is_correct=True,
        )

        summary = metrics.get_summary()
        d = summary.to_dict()

        expected_fields = [
            "total_examples",
            "avg_citation_precision",
            "avg_citation_recall",
            "avg_citation_f1",
            "avg_answer_relevance",
            "contains_expected_rate",
            "avg_brier_score",
            "calibration_error",
            "avg_quality_score",
            "by_category",
        ]

        for field in expected_fields:
            assert field in d, f"Missing field in MetricsSummary: {field}"


class TestTraceSchemaGoldenContracts:
    """Golden contract tests for trace schema stability."""

    def test_span_structure(self):
        """Test that Span has expected fields."""
        from deepr.observability.traces import TraceContext

        ctx = TraceContext.create()

        with ctx.span("test_operation") as span:
            span.set_attribute("test_key", "test_value")
            span.set_cost(0.01)

        d = span.to_dict()

        expected_fields = [
            "span_id",
            "trace_id",
            "parent_span_id",
            "name",
            "start_time",
            "end_time",
            "status",
            "duration_ms",
            "attributes",
            "events",
            "cost",
        ]

        for field in expected_fields:
            assert field in d, f"Missing field in Span: {field}"

    def test_trace_context_structure(self):
        """Test that TraceContext has expected fields."""
        from deepr.observability.traces import TraceContext

        ctx = TraceContext.create()

        with ctx.span("parent") as parent:
            with ctx.span("child") as child:
                pass

        d = ctx.to_dict()

        expected_fields = ["trace_id", "spans", "total_cost", "total_duration_ms"]

        for field in expected_fields:
            assert field in d, f"Missing field in TraceContext: {field}"


# Pytest fixture for updating golden files
@pytest.fixture
def update_golden(request):
    """Fixture to check if golden files should be updated."""
    return request.config.getoption("--update-golden", default=False)


def pytest_addoption(parser):
    """Add --update-golden option to pytest."""
    parser.addoption(
        "--update-golden", action="store_true", default=False, help="Update golden files with current output"
    )
