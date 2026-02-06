"""
Sandboxed Execution for MCP.

Implements isolated execution contexts for heavy research processing,
preventing context pollution and ensuring security through path isolation.
"""

import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class SandboxStatus(Enum):
    """Status of a sandbox execution context."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CLEANED = "cleaned"


@dataclass
class SandboxConfig:
    """Configuration for a sandbox execution context."""

    sandbox_id: str
    working_dir: Path
    max_tokens: int = 100_000
    allowed_tools: list[str] = field(default_factory=list)
    timeout_seconds: int = 600
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "sandbox_id": self.sandbox_id,
            "working_dir": str(self.working_dir),
            "max_tokens": self.max_tokens,
            "allowed_tools": self.allowed_tools,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SandboxState:
    """Runtime state of a sandbox."""

    config: SandboxConfig
    status: SandboxStatus = SandboxStatus.INITIALIZING
    tokens_used: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    error: Optional[str] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "config": self.config.to_dict(),
            "status": self.status.value,
            "tokens_used": self.tokens_used,
            "tool_call_count": len(self.tool_calls),
            "artifact_count": len(self.artifacts),
            "error": self.error,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class SandboxResult:
    """Result extracted from a completed sandbox."""

    sandbox_id: str
    report: Optional[str] = None
    artifacts: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "sandbox_id": self.sandbox_id,
            "report": self.report,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "success": self.success,
            "error": self.error,
        }


class PathValidator:
    """
    Validates paths to prevent traversal attacks.

    Ensures all file operations stay within sandbox boundaries.
    """

    def __init__(self, sandbox_root: Path):
        """
        Initialize validator with sandbox root.

        Args:
            sandbox_root: Root directory for all sandboxes
        """
        self._root = sandbox_root.resolve()

    def validate(self, sandbox_dir: Path, requested_path: str) -> Optional[Path]:
        """
        Validate and resolve a path within sandbox boundaries.

        This method prevents path traversal attacks by ensuring all resolved
        paths remain within the sandbox directory. It rejects:
        - Absolute paths
        - Paths containing .. that escape the sandbox
        - Paths that resolve outside the sandbox root

        Args:
            sandbox_dir: The specific sandbox directory
            requested_path: Path requested by the operation

        Returns:
            Resolved Path if valid, None if path escapes sandbox

        Security:
            This is a critical security function. All file operations in
            sandboxes MUST use this validation before accessing files.
        """
        # Reject empty paths
        if not requested_path or not requested_path.strip():
            return None

        # Reject absolute paths
        requested = Path(requested_path)
        if requested.is_absolute():
            return None

        # Resolve the full path
        try:
            resolved = (sandbox_dir / requested).resolve()
        except (ValueError, RuntimeError, OSError):
            # Path resolution failed (e.g., invalid characters)
            return None

        # Verify containment within sandbox
        try:
            resolved.relative_to(sandbox_dir.resolve())
            return resolved
        except ValueError:
            # Path escapes sandbox (e.g., ../../etc/passwd)
            return None

    def is_safe_filename(self, filename: str) -> bool:
        """
        Check if a filename is safe (no path separators or special chars).

        Args:
            filename: Filename to validate

        Returns:
            True if safe, False otherwise
        """
        # Reject empty or whitespace-only
        if not filename or not filename.strip():
            return False

        # Reject path separators
        if "/" in filename or "\\" in filename:
            return False

        # Reject parent directory references
        if filename in (".", ".."):
            return False

        # Reject null bytes
        if "\x00" in filename:
            return False

        return True


class SandboxManager:
    """
    Manages sandboxed execution contexts for heavy research.

    Provides:
    - Isolated working directories
    - Path traversal protection
    - Token tracking
    - Result extraction
    """

    # Default allowed tools for research sandboxes
    DEFAULT_RESEARCH_TOOLS = [
        "deepr_search",
        "deepr_analyze",
        "deepr_synthesize",
        "deepr_get_result",
    ]

    def __init__(self, base_dir: Path):
        """
        Initialize the sandbox manager.

        Args:
            base_dir: Base directory for all sandboxes
        """
        self._base_dir = Path(base_dir)
        self._sandboxes: dict[str, SandboxState] = {}
        self._validator = PathValidator(self._base_dir)

    def create_sandbox(
        self,
        job_id: str,
        max_tokens: int = 100_000,
        allowed_tools: Optional[list[str]] = None,
        timeout_seconds: int = 600,
    ) -> SandboxConfig:
        """
        Create a new sandbox for a research job.

        Args:
            job_id: Research job identifier (must be non-empty)
            max_tokens: Maximum tokens allowed in sandbox (must be positive)
            allowed_tools: List of allowed tool names (defaults to research tools)
            timeout_seconds: Sandbox timeout in seconds (must be positive)

        Returns:
            SandboxConfig for the new sandbox

        Raises:
            ValueError: If job_id is empty or parameters are invalid
        """
        # Validate inputs
        if not job_id or not job_id.strip():
            raise ValueError("job_id cannot be empty")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        sandbox_id = f"{job_id}_{uuid.uuid4().hex[:8]}"
        sandbox_dir = self._base_dir / "sandboxes" / sandbox_id

        # Create directory structure
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        (sandbox_dir / "artifacts").mkdir(exist_ok=True)
        (sandbox_dir / "logs").mkdir(exist_ok=True)

        config = SandboxConfig(
            sandbox_id=sandbox_id,
            working_dir=sandbox_dir,
            max_tokens=max_tokens,
            allowed_tools=allowed_tools or self.DEFAULT_RESEARCH_TOOLS.copy(),
            timeout_seconds=timeout_seconds,
        )

        state = SandboxState(config=config, status=SandboxStatus.ACTIVE)
        self._sandboxes[sandbox_id] = state

        return config

    def get_sandbox(self, sandbox_id: str) -> Optional[SandboxState]:
        """Get sandbox state by ID."""
        return self._sandboxes.get(sandbox_id)

    def validate_path(self, sandbox_id: str, path: str) -> Optional[Path]:
        """
        Validate a path within a sandbox.

        Args:
            sandbox_id: Sandbox identifier
            path: Requested path

        Returns:
            Resolved Path if valid, None if invalid or escapes sandbox
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return None

        return self._validator.validate(state.config.working_dir, path)

    def is_tool_allowed(self, sandbox_id: str, tool_name: str) -> bool:
        """
        Check if a tool is allowed in the sandbox.

        Args:
            sandbox_id: Sandbox identifier
            tool_name: Tool to check

        Returns:
            True if allowed, False otherwise
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return False

        return tool_name in state.config.allowed_tools

    def record_tool_call(self, sandbox_id: str, tool_name: str, arguments: dict, tokens_used: int = 0) -> bool:
        """
        Record a tool call in the sandbox.

        Args:
            sandbox_id: Sandbox identifier
            tool_name: Tool that was called
            arguments: Tool arguments
            tokens_used: Tokens consumed by the call

        Returns:
            True if recorded, False if sandbox not found or over limit
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return False

        if state.status != SandboxStatus.ACTIVE:
            return False

        # Check token limit
        if state.tokens_used + tokens_used > state.config.max_tokens:
            state.status = SandboxStatus.FAILED
            state.error = "Token limit exceeded"
            return False

        state.tool_calls.append(
            {"tool": tool_name, "arguments": arguments, "tokens": tokens_used, "timestamp": datetime.now().isoformat()}
        )
        state.tokens_used += tokens_used

        return True

    def write_artifact(self, sandbox_id: str, filename: str, content: str) -> Optional[Path]:
        """
        Write an artifact to the sandbox.

        Args:
            sandbox_id: Sandbox identifier
            filename: Artifact filename (no path separators)
            content: File content

        Returns:
            Path to written file, or None if failed
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return None

        if not self._validator.is_safe_filename(filename):
            return None

        artifact_path = state.config.working_dir / "artifacts" / filename

        try:
            artifact_path.write_text(content, encoding="utf-8")
            state.artifacts.append(filename)
            return artifact_path
        except OSError:
            return None

    def write_report(self, sandbox_id: str, content: str) -> Optional[Path]:
        """
        Write the final report to the sandbox.

        Args:
            sandbox_id: Sandbox identifier
            content: Report content

        Returns:
            Path to report file, or None if failed
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return None

        report_path = state.config.working_dir / "final_report.md"

        try:
            report_path.write_text(content, encoding="utf-8")
            return report_path
        except OSError:
            return None

    def complete_sandbox(self, sandbox_id: str) -> bool:
        """
        Mark a sandbox as completed.

        Args:
            sandbox_id: Sandbox identifier

        Returns:
            True if completed, False if not found
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return False

        state.status = SandboxStatus.COMPLETED
        state.completed_at = datetime.now()

        return True

    def fail_sandbox(self, sandbox_id: str, error: str) -> bool:
        """
        Mark a sandbox as failed.

        Args:
            sandbox_id: Sandbox identifier
            error: Error message

        Returns:
            True if marked, False if not found
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return False

        state.status = SandboxStatus.FAILED
        state.error = error
        state.completed_at = datetime.now()

        return True

    def extract_results(self, sandbox_id: str) -> Optional[SandboxResult]:
        """
        Extract results from a completed sandbox.

        Reads the final report and lists artifacts, discarding
        intermediate state and logs.

        Args:
            sandbox_id: Sandbox identifier

        Returns:
            SandboxResult or None if sandbox not found
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return None

        report_path = state.config.working_dir / "final_report.md"
        report_content = None

        if report_path.exists():
            try:
                report_content = report_path.read_text(encoding="utf-8")
            except OSError:
                pass

        return SandboxResult(
            sandbox_id=sandbox_id,
            report=report_content,
            artifacts=state.artifacts.copy(),
            metadata={
                "tokens_used": state.tokens_used,
                "tool_call_count": len(state.tool_calls),
                "status": state.status.value,
            },
            success=state.status == SandboxStatus.COMPLETED,
            error=state.error,
        )

    def cleanup_sandbox(self, sandbox_id: str, remove_files: bool = True) -> bool:
        """
        Clean up a sandbox and optionally remove files.

        Args:
            sandbox_id: Sandbox identifier
            remove_files: Whether to delete the sandbox directory

        Returns:
            True if cleaned, False if not found
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return False

        if remove_files and state.config.working_dir.exists():
            try:
                shutil.rmtree(state.config.working_dir)
            except OSError:
                pass

        state.status = SandboxStatus.CLEANED

        return True

    def list_active_sandboxes(self) -> list[SandboxState]:
        """List all active sandboxes."""
        return [s for s in self._sandboxes.values() if s.status == SandboxStatus.ACTIVE]

    def get_sandbox_stats(self) -> dict:
        """Get statistics about all sandboxes."""
        by_status = {}
        total_tokens = 0
        total_tool_calls = 0

        for state in self._sandboxes.values():
            status = state.status.value
            by_status[status] = by_status.get(status, 0) + 1
            total_tokens += state.tokens_used
            total_tool_calls += len(state.tool_calls)

        return {
            "total_sandboxes": len(self._sandboxes),
            "by_status": by_status,
            "total_tokens_used": total_tokens,
            "total_tool_calls": total_tool_calls,
        }

    def to_fork_request(self, sandbox_id: str, query: str) -> Optional[dict]:
        """
        Generate a JSON-RPC content/fork request for a sandbox.

        Args:
            sandbox_id: Sandbox identifier
            query: Research query for the fork

        Returns:
            JSON-RPC request dict or None if sandbox not found
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return None

        return {
            "jsonrpc": "2.0",
            "method": "content/fork",
            "params": {
                "job_id": sandbox_id,
                "context": {
                    "type": "research",
                    "query": query,
                    "constraints": {
                        "max_tokens": state.config.max_tokens,
                        "working_dir": str(state.config.working_dir),
                        "allowed_tools": state.config.allowed_tools,
                        "timeout_seconds": state.config.timeout_seconds,
                    },
                },
            },
            "id": sandbox_id,
        }
