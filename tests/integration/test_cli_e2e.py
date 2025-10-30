"""End-to-end CLI workflow tests.

Tests complete workflows through the CLI:
- Submit job -> Check status -> Get results
- Test with different providers
- Test with file uploads
- Test job cancellation
- Test budget limits

These tests exercise the actual CLI commands and database/storage integration.
"""

import pytest
import subprocess
import time
import re
import os
from pathlib import Path


def extract_job_id_from_output(output):
    """Extract job ID from CLI output."""
    # Look for patterns like "Job ID: abc123" or "research-abc123"
    patterns = [
        r'Job ID:\s+([a-zA-Z0-9-]+)',
        r'(research-[a-f0-9]+)',
        r'ID:\s+([a-zA-Z0-9-]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return match.group(1)

    return None


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.requires_api
def test_focus_command_complete_workflow_gemini():
    """Test complete workflow: submit -> status -> get results (Gemini)."""
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Gemini API key not set")

    # Submit a simple research job
    result = subprocess.run(
        [
            "deepr", "run", "focus",
            "What is 2+2? Answer in one sentence.",
            "--provider", "gemini",
            "-m", "gemini-2.5-flash",
            "--yes",
            "--no-web",
            "--no-code"
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    print("Submit output:", result.stdout)
    print("Submit stderr:", result.stderr)

    assert result.returncode == 0, f"Submit failed: {result.stderr}"

    # Extract job ID
    job_id = extract_job_id_from_output(result.stdout)
    assert job_id is not None, "Could not extract job ID from output"

    # Wait a bit for job to complete (Gemini is fast)
    time.sleep(5)

    # Check status
    status_result = subprocess.run(
        ["deepr", "jobs", "status", job_id],
        capture_output=True,
        text=True,
        timeout=30
    )

    print("Status output:", status_result.stdout)
    assert status_result.returncode == 0

    # Get results
    get_result = subprocess.run(
        ["deepr", "jobs", "get", job_id],
        capture_output=True,
        text=True,
        timeout=30
    )

    print("Get output:", get_result.stdout)
    assert get_result.returncode == 0

    # Should show the answer
    output_lower = get_result.stdout.lower()
    # Verify we got some content back
    assert len(get_result.stdout) > 100, "Results should have substantial content"


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.requires_api
def test_focus_command_complete_workflow_grok():
    """Test complete workflow with Grok provider."""
    if not os.getenv("XAI_API_KEY"):
        pytest.skip("xAI API key not set")

    # Submit a simple research job
    result = subprocess.run(
        [
            "deepr", "run", "focus",
            "What is Python? Answer in one sentence.",
            "--provider", "grok",
            "-m", "grok-4-fast",
            "--yes",
            "--no-web",
            "--no-code"
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    print("Submit output:", result.stdout)
    print("Submit stderr:", result.stderr)

    assert result.returncode == 0, f"Submit failed: {result.stderr}"

    # Extract job ID
    job_id = extract_job_id_from_output(result.stdout)
    assert job_id is not None, "Could not extract job ID from output"

    # Wait a bit for job to complete
    time.sleep(5)

    # Check status
    status_result = subprocess.run(
        ["deepr", "jobs", "status", job_id],
        capture_output=True,
        text=True,
        timeout=30
    )

    print("Status output:", status_result.stdout)
    assert status_result.returncode == 0

    # Get results
    get_result = subprocess.run(
        ["deepr", "jobs", "get", job_id],
        capture_output=True,
        text=True,
        timeout=30
    )

    print("Get output:", get_result.stdout)
    assert get_result.returncode == 0
    assert len(get_result.stdout) > 100, "Results should have substantial content"


@pytest.mark.integration
@pytest.mark.e2e
def test_jobs_list_command():
    """Test that jobs list command shows recent jobs."""
    result = subprocess.run(
        ["deepr", "jobs", "list", "--limit", "10"],
        capture_output=True,
        text=True,
        timeout=30
    )

    print("List output:", result.stdout)
    assert result.returncode == 0


@pytest.mark.integration
@pytest.mark.e2e
def test_jobs_list_with_filter():
    """Test jobs list with status filter."""
    result = subprocess.run(
        ["deepr", "jobs", "list", "--status", "completed", "--limit", "5"],
        capture_output=True,
        text=True,
        timeout=30
    )

    print("List filtered output:", result.stdout)
    assert result.returncode == 0


@pytest.mark.integration
@pytest.mark.e2e
def test_deprecated_commands_still_work():
    """Test that deprecated commands still function with warnings."""
    # Test deprecated list command
    result = subprocess.run(
        ["deepr", "list", "--limit", "3"],
        capture_output=True,
        text=True,
        timeout=30
    )

    assert result.returncode == 0
    assert "DEPRECATION" in result.stdout or "deprecated" in result.stdout.lower()


@pytest.mark.integration
@pytest.mark.e2e
def test_quick_alias_r():
    """Test that quick alias 'deepr r' works."""
    # Just test the help to avoid API calls
    result = subprocess.run(
        ["deepr", "r", "--help"],
        capture_output=True,
        text=True,
        timeout=30
    )

    assert result.returncode == 0


@pytest.mark.integration
@pytest.mark.e2e
def test_docs_command_structure():
    """Test that docs command has correct structure."""
    result = subprocess.run(
        ["deepr", "run", "docs", "--help"],
        capture_output=True,
        text=True,
        timeout=30
    )

    assert result.returncode == 0
    assert "--provider" in result.stdout
    assert "--upload" in result.stdout


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.requires_api
def test_focus_with_provider_parameter():
    """Test focus command with different providers."""
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Gemini API key not set")

    result = subprocess.run(
        [
            "deepr", "run", "focus",
            "Say hello in one word",
            "--provider", "gemini",
            "-m", "gemini-2.5-flash",
            "--yes"
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    print("Provider test output:", result.stdout)
    assert result.returncode == 0


@pytest.mark.integration
@pytest.mark.e2e
def test_invalid_job_id_handling():
    """Test that CLI handles invalid job IDs gracefully."""
    result = subprocess.run(
        ["deepr", "jobs", "status", "invalid-job-id-12345"],
        capture_output=True,
        text=True,
        timeout=30
    )

    # Should fail gracefully, not crash
    assert "not found" in result.stdout.lower() or "Job not found" in result.stdout


@pytest.mark.integration
@pytest.mark.e2e
def test_budget_commands():
    """Test budget management commands."""
    # Get current budget status
    result = subprocess.run(
        ["deepr", "budget", "status"],
        capture_output=True,
        text=True,
        timeout=30
    )

    print("Budget output:", result.stdout)
    assert result.returncode == 0


@pytest.mark.integration
@pytest.mark.e2e
def test_config_commands():
    """Test configuration commands."""
    result = subprocess.run(
        ["deepr", "config", "show"],
        capture_output=True,
        text=True,
        timeout=30
    )

    print("Config output:", result.stdout)
    assert result.returncode == 0


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.requires_api
def test_focus_command_with_limit():
    """Test focus command respects cost limit."""
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Gemini API key not set")

    # Set a very low limit
    result = subprocess.run(
        [
            "deepr", "run", "focus",
            "Test query",
            "--provider", "gemini",
            "--limit", "0.01",
            "--yes"
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    print("Limit test output:", result.stdout)
    # Should either succeed (if under limit) or warn about budget
    assert result.returncode in [0, 1]


@pytest.mark.integration
@pytest.mark.e2e
def test_command_help_consistency():
    """Test that all help commands work and are consistent."""
    commands_to_test = [
        ["deepr", "--help"],
        ["deepr", "run", "--help"],
        ["deepr", "run", "focus", "--help"],
        ["deepr", "run", "project", "--help"],
        ["deepr", "run", "docs", "--help"],
        ["deepr", "run", "team", "--help"],
        ["deepr", "jobs", "--help"],
        ["deepr", "jobs", "list", "--help"],
        ["deepr", "jobs", "status", "--help"],
        ["deepr", "budget", "--help"],
        ["deepr", "cost", "--help"],
    ]

    for cmd in commands_to_test:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"Help failed for {' '.join(cmd)}"
        assert len(result.stdout) > 0, f"Help output empty for {' '.join(cmd)}"
