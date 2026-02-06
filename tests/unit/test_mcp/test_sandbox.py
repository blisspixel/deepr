"""
Tests for MCP Sandboxed Execution.

Validates: Requirements 6B.1, 6B.2, 6B.3, 6B.5, 6B.6
"""

import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Add deepr to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.state.sandbox import (
    PathValidator,
    SandboxConfig,
    SandboxManager,
    SandboxResult,
    SandboxStatus,
)


class TestSandboxStatus:
    """Test SandboxStatus enum."""

    def test_enum_values(self):
        """Enum should have expected values."""
        assert SandboxStatus.INITIALIZING.value == "initializing"
        assert SandboxStatus.ACTIVE.value == "active"
        assert SandboxStatus.COMPLETED.value == "completed"
        assert SandboxStatus.FAILED.value == "failed"
        assert SandboxStatus.CLEANED.value == "cleaned"


class TestSandboxConfig:
    """Test SandboxConfig dataclass."""

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        config = SandboxConfig(
            sandbox_id="test_123",
            working_dir=Path("/tmp/sandbox"),
            max_tokens=50000,
            allowed_tools=["tool1", "tool2"],
            timeout_seconds=300,
        )

        data = config.to_dict()

        assert data["sandbox_id"] == "test_123"
        # Path serialization is platform-dependent, just check it's a string
        assert "sandbox" in data["working_dir"]
        assert data["max_tokens"] == 50000
        assert data["allowed_tools"] == ["tool1", "tool2"]
        assert data["timeout_seconds"] == 300


class TestSandboxResult:
    """Test SandboxResult dataclass."""

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        result = SandboxResult(
            sandbox_id="test_123",
            report="# Report\n\nContent here",
            artifacts=["data.json", "chart.png"],
            metadata={"tokens_used": 5000},
            success=True,
        )

        data = result.to_dict()

        assert data["sandbox_id"] == "test_123"
        assert data["report"] == "# Report\n\nContent here"
        assert data["artifacts"] == ["data.json", "chart.png"]
        assert data["success"] is True


class TestPathValidator:
    """Test PathValidator security."""

    @pytest.fixture
    def validator(self, tmp_path):
        return PathValidator(tmp_path)

    @pytest.fixture
    def sandbox_dir(self, tmp_path):
        sandbox = tmp_path / "sandboxes" / "test_sandbox"
        sandbox.mkdir(parents=True)
        return sandbox

    def test_valid_path(self, validator, sandbox_dir):
        """Valid relative path should be accepted."""
        result = validator.validate(sandbox_dir, "artifacts/report.md")

        assert result is not None
        assert result == sandbox_dir / "artifacts" / "report.md"

    def test_absolute_path_rejected(self, validator, sandbox_dir):
        """Absolute paths should be rejected."""
        result = validator.validate(sandbox_dir, "/etc/passwd")

        assert result is None

    def test_parent_traversal_rejected(self, validator, sandbox_dir):
        """Parent directory traversal should be rejected."""
        result = validator.validate(sandbox_dir, "../../../etc/passwd")

        assert result is None

    def test_hidden_traversal_rejected(self, validator, sandbox_dir):
        """Hidden traversal attempts should be rejected."""
        result = validator.validate(sandbox_dir, "artifacts/../../secret.txt")

        assert result is None

    def test_safe_filename(self, validator):
        """Safe filenames should be accepted."""
        assert validator.is_safe_filename("report.md") is True
        assert validator.is_safe_filename("data_2024.json") is True
        assert validator.is_safe_filename("file-name.txt") is True

    def test_unsafe_filename_with_slash(self, validator):
        """Filenames with slashes should be rejected."""
        assert validator.is_safe_filename("path/to/file.txt") is False
        assert validator.is_safe_filename("..\\secret.txt") is False

    def test_unsafe_filename_dot_dot(self, validator):
        """Parent directory references should be rejected."""
        assert validator.is_safe_filename("..") is False
        assert validator.is_safe_filename(".") is False

    def test_unsafe_filename_empty(self, validator):
        """Empty filenames should be rejected."""
        assert validator.is_safe_filename("") is False
        assert validator.is_safe_filename("   ") is False

    def test_unsafe_filename_null_byte(self, validator):
        """Null bytes should be rejected."""
        assert validator.is_safe_filename("file\x00.txt") is False


class TestSandboxManager:
    """Test SandboxManager functionality."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SandboxManager(tmp_path)

    def test_create_sandbox(self, manager):
        """create_sandbox should create config and directories."""
        config = manager.create_sandbox(job_id="job_123", max_tokens=50000, timeout_seconds=300)

        assert config.sandbox_id.startswith("job_123_")
        assert config.working_dir.exists()
        assert (config.working_dir / "artifacts").exists()
        assert (config.working_dir / "logs").exists()

    def test_create_sandbox_default_tools(self, manager):
        """create_sandbox should include default research tools."""
        config = manager.create_sandbox(job_id="test")

        assert "deepr_search" in config.allowed_tools
        assert "deepr_analyze" in config.allowed_tools
        assert "deepr_synthesize" in config.allowed_tools

    def test_create_sandbox_custom_tools(self, manager):
        """create_sandbox should accept custom tool list."""
        config = manager.create_sandbox(job_id="test", allowed_tools=["custom_tool"])

        assert config.allowed_tools == ["custom_tool"]

    def test_get_sandbox(self, manager):
        """get_sandbox should return sandbox state."""
        config = manager.create_sandbox(job_id="test")

        state = manager.get_sandbox(config.sandbox_id)

        assert state is not None
        assert state.config.sandbox_id == config.sandbox_id
        assert state.status == SandboxStatus.ACTIVE

    def test_get_sandbox_nonexistent(self, manager):
        """get_sandbox on nonexistent ID should return None."""
        result = manager.get_sandbox("nonexistent")

        assert result is None

    def test_validate_path(self, manager):
        """validate_path should validate paths within sandbox."""
        config = manager.create_sandbox(job_id="test")

        valid = manager.validate_path(config.sandbox_id, "artifacts/file.txt")
        invalid = manager.validate_path(config.sandbox_id, "../../../etc/passwd")

        assert valid is not None
        assert invalid is None

    def test_is_tool_allowed(self, manager):
        """is_tool_allowed should check tool permissions."""
        config = manager.create_sandbox(job_id="test", allowed_tools=["allowed_tool"])

        assert manager.is_tool_allowed(config.sandbox_id, "allowed_tool") is True
        assert manager.is_tool_allowed(config.sandbox_id, "forbidden_tool") is False

    def test_record_tool_call(self, manager):
        """record_tool_call should track tool usage."""
        config = manager.create_sandbox(job_id="test", max_tokens=10000)

        result = manager.record_tool_call(
            config.sandbox_id, tool_name="deepr_search", arguments={"query": "test"}, tokens_used=500
        )

        assert result is True

        state = manager.get_sandbox(config.sandbox_id)
        assert state.tokens_used == 500
        assert len(state.tool_calls) == 1

    def test_record_tool_call_exceeds_limit(self, manager):
        """record_tool_call should fail when exceeding token limit."""
        config = manager.create_sandbox(job_id="test", max_tokens=1000)

        result = manager.record_tool_call(config.sandbox_id, tool_name="deepr_search", arguments={}, tokens_used=2000)

        assert result is False

        state = manager.get_sandbox(config.sandbox_id)
        assert state.status == SandboxStatus.FAILED
        assert "Token limit" in state.error

    def test_write_artifact(self, manager):
        """write_artifact should write file to sandbox."""
        config = manager.create_sandbox(job_id="test")

        path = manager.write_artifact(config.sandbox_id, filename="data.json", content='{"key": "value"}')

        assert path is not None
        assert path.exists()
        assert path.read_text() == '{"key": "value"}'

        state = manager.get_sandbox(config.sandbox_id)
        assert "data.json" in state.artifacts

    def test_write_artifact_unsafe_filename(self, manager):
        """write_artifact should reject unsafe filenames."""
        config = manager.create_sandbox(job_id="test")

        path = manager.write_artifact(config.sandbox_id, filename="../../../etc/passwd", content="malicious")

        assert path is None

    def test_write_report(self, manager):
        """write_report should write final report."""
        config = manager.create_sandbox(job_id="test")

        path = manager.write_report(config.sandbox_id, content="# Final Report\n\nContent here")

        assert path is not None
        assert path.name == "final_report.md"
        assert path.exists()

    def test_complete_sandbox(self, manager):
        """complete_sandbox should mark as completed."""
        config = manager.create_sandbox(job_id="test")

        result = manager.complete_sandbox(config.sandbox_id)

        assert result is True

        state = manager.get_sandbox(config.sandbox_id)
        assert state.status == SandboxStatus.COMPLETED
        assert state.completed_at is not None

    def test_fail_sandbox(self, manager):
        """fail_sandbox should mark as failed with error."""
        config = manager.create_sandbox(job_id="test")

        result = manager.fail_sandbox(config.sandbox_id, "Test error")

        assert result is True

        state = manager.get_sandbox(config.sandbox_id)
        assert state.status == SandboxStatus.FAILED
        assert state.error == "Test error"

    def test_extract_results(self, manager):
        """extract_results should return sandbox results."""
        config = manager.create_sandbox(job_id="test")

        manager.write_report(config.sandbox_id, "# Report")
        manager.write_artifact(config.sandbox_id, "data.json", "{}")
        manager.complete_sandbox(config.sandbox_id)

        result = manager.extract_results(config.sandbox_id)

        assert result is not None
        assert result.report == "# Report"
        assert "data.json" in result.artifacts
        assert result.success is True

    def test_extract_results_failed_sandbox(self, manager):
        """extract_results should indicate failure."""
        config = manager.create_sandbox(job_id="test")

        manager.fail_sandbox(config.sandbox_id, "Error occurred")

        result = manager.extract_results(config.sandbox_id)

        assert result is not None
        assert result.success is False
        assert result.error == "Error occurred"

    def test_cleanup_sandbox(self, manager):
        """cleanup_sandbox should remove files and mark cleaned."""
        config = manager.create_sandbox(job_id="test")
        working_dir = config.working_dir

        result = manager.cleanup_sandbox(config.sandbox_id, remove_files=True)

        assert result is True
        assert not working_dir.exists()

        state = manager.get_sandbox(config.sandbox_id)
        assert state.status == SandboxStatus.CLEANED

    def test_list_active_sandboxes(self, manager):
        """list_active_sandboxes should return only active ones."""
        config1 = manager.create_sandbox(job_id="job1")
        config2 = manager.create_sandbox(job_id="job2")

        manager.complete_sandbox(config1.sandbox_id)

        active = manager.list_active_sandboxes()

        assert len(active) == 1
        assert active[0].config.sandbox_id == config2.sandbox_id

    def test_get_sandbox_stats(self, manager):
        """get_sandbox_stats should return statistics."""
        config1 = manager.create_sandbox(job_id="job1")
        config2 = manager.create_sandbox(job_id="job2")

        manager.record_tool_call(config1.sandbox_id, "tool", {}, 1000)
        manager.record_tool_call(config2.sandbox_id, "tool", {}, 500)
        manager.complete_sandbox(config1.sandbox_id)

        stats = manager.get_sandbox_stats()

        assert stats["total_sandboxes"] == 2
        assert stats["total_tokens_used"] == 1500
        assert stats["total_tool_calls"] == 2
        assert stats["by_status"]["completed"] == 1
        assert stats["by_status"]["active"] == 1

    def test_to_fork_request(self, manager):
        """to_fork_request should generate valid JSON-RPC."""
        config = manager.create_sandbox(job_id="test", max_tokens=50000)

        request = manager.to_fork_request(config.sandbox_id, "Analyze market trends")

        assert request is not None
        assert request["jsonrpc"] == "2.0"
        assert request["method"] == "content/fork"
        assert request["params"]["context"]["query"] == "Analyze market trends"
        assert request["params"]["context"]["constraints"]["max_tokens"] == 50000


class TestSandboxValidation:
    """Test defensive validation in SandboxManager."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SandboxManager(tmp_path)

    def test_create_sandbox_rejects_empty_job_id(self, manager):
        """create_sandbox should reject empty job_id."""
        with pytest.raises(ValueError, match="job_id cannot be empty"):
            manager.create_sandbox(job_id="")

    def test_create_sandbox_rejects_whitespace_job_id(self, manager):
        """create_sandbox should reject whitespace-only job_id."""
        with pytest.raises(ValueError, match="job_id cannot be empty"):
            manager.create_sandbox(job_id="   ")

    def test_create_sandbox_rejects_negative_max_tokens(self, manager):
        """create_sandbox should reject negative max_tokens."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            manager.create_sandbox(job_id="test", max_tokens=-100)

    def test_create_sandbox_rejects_zero_max_tokens(self, manager):
        """create_sandbox should reject zero max_tokens."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            manager.create_sandbox(job_id="test", max_tokens=0)

    def test_create_sandbox_rejects_negative_timeout(self, manager):
        """create_sandbox should reject negative timeout_seconds."""
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            manager.create_sandbox(job_id="test", timeout_seconds=-60)

    def test_create_sandbox_rejects_zero_timeout(self, manager):
        """create_sandbox should reject zero timeout_seconds."""
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            manager.create_sandbox(job_id="test", timeout_seconds=0)

    def test_path_validator_rejects_empty_path(self, manager):
        """PathValidator should reject empty paths."""
        config = manager.create_sandbox(job_id="test")

        assert manager.validate_path(config.sandbox_id, "") is None
        assert manager.validate_path(config.sandbox_id, "   ") is None


class TestPropertyBased:
    """Property-based tests for sandbox security."""

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_path_traversal_always_blocked(self, path_component: str):
        """
        Property: Path traversal attempts should always be blocked.
        Validates: Requirements 6B.6
        """
        with tempfile.TemporaryDirectory() as tmp:
            validator = PathValidator(Path(tmp))
            sandbox_dir = Path(tmp) / "sandbox"
            sandbox_dir.mkdir()

            # Try various traversal patterns
            traversal_paths = [
                f"../{path_component}",
                f"../../{path_component}",
                f"artifacts/../../../{path_component}",
                f"..\\{path_component}",
            ]

            for malicious_path in traversal_paths:
                result = validator.validate(sandbox_dir, malicious_path)

                # If result is not None, it must be within sandbox
                if result is not None:
                    try:
                        result.relative_to(sandbox_dir)
                    except ValueError:
                        pytest.fail(f"Path escaped sandbox: {malicious_path} -> {result}")

    @given(st.integers(min_value=1, max_value=100000))
    @settings(max_examples=30)
    def test_token_limit_enforced(self, max_tokens: int):
        """
        Property: Token limits should always be enforced.
        Validates: Requirements 6B.2
        """
        with tempfile.TemporaryDirectory() as tmp:
            manager = SandboxManager(Path(tmp))
            config = manager.create_sandbox(job_id="test", max_tokens=max_tokens)

            # Try to exceed limit
            result = manager.record_tool_call(
                config.sandbox_id, tool_name="test", arguments={}, tokens_used=max_tokens + 1
            )

            assert result is False

            state = manager.get_sandbox(config.sandbox_id)
            assert state.status == SandboxStatus.FAILED

    @given(
        st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-.", min_size=1, max_size=20),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=30)
    def test_artifacts_tracked(self, filenames: list[str]):
        """
        Property: All written artifacts should be tracked.
        Validates: Requirements 6B.3
        """
        with tempfile.TemporaryDirectory() as tmp:
            manager = SandboxManager(Path(tmp))
            config = manager.create_sandbox(job_id="test")

            written = []
            for filename in filenames:
                # Skip unsafe filenames
                if "/" in filename or "\\" in filename or filename in (".", ".."):
                    continue

                path = manager.write_artifact(config.sandbox_id, filename, "content")
                if path is not None:
                    written.append(filename)

            state = manager.get_sandbox(config.sandbox_id)

            # All successfully written files should be tracked
            for filename in written:
                assert filename in state.artifacts

    @given(st.lists(st.sampled_from(["deepr_search", "deepr_analyze", "custom_tool"]), min_size=1, max_size=5))
    @settings(max_examples=20)
    def test_tool_permissions_consistent(self, allowed_tools: list[str]):
        """
        Property: Tool permissions should be consistently enforced.
        """
        with tempfile.TemporaryDirectory() as tmp:
            manager = SandboxManager(Path(tmp))
            config = manager.create_sandbox(job_id="test", allowed_tools=allowed_tools)

            # Allowed tools should be allowed
            for tool in allowed_tools:
                assert manager.is_tool_allowed(config.sandbox_id, tool) is True

            # Non-allowed tools should be blocked
            assert manager.is_tool_allowed(config.sandbox_id, "definitely_not_allowed") is False
