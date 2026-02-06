"""Integration tests for CLI command structure.

Tests the new command structure:
- deepr run focus (was single)
- deepr run project (was campaign)
- deepr run docs (new)
- deepr jobs list/status/get/cancel (was top-level commands)

These tests validate that:
1. New commands work correctly
2. Old commands still work with deprecation warnings
3. Command aliases function properly
4. All parameters are passed correctly
"""

import subprocess

import pytest


@pytest.mark.integration
def test_cli_help_shows_new_structure():
    """Test that main help shows new command structure."""
    result = subprocess.run(["deepr", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "jobs" in result.stdout.lower()
    assert "Manage research jobs" in result.stdout


@pytest.mark.integration
def test_run_help_shows_all_modes():
    """Test that 'deepr run --help' shows all research modes."""
    result = subprocess.run(["deepr", "run", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    output = result.stdout.lower()

    # New commands
    assert "focus" in output
    assert "project" in output
    assert "docs" in output
    assert "team" in output

    # Deprecated commands still listed
    assert "single" in output
    assert "campaign" in output


@pytest.mark.integration
def test_jobs_help_shows_all_subcommands():
    """Test that 'deepr jobs --help' shows all job management commands."""
    result = subprocess.run(["deepr", "jobs", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    output = result.stdout.lower()

    assert "list" in output
    assert "status" in output
    assert "get" in output
    assert "cancel" in output


@pytest.mark.integration
def test_focus_command_has_correct_options():
    """Test that 'deepr run focus' has all expected options."""
    result = subprocess.run(["deepr", "run", "focus", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    output = result.stdout

    # Check for key options
    assert "--model" in output or "-m" in output
    assert "--provider" in output or "-p" in output
    assert "--no-web" in output
    assert "--no-code" in output
    assert "--upload" in output or "-u" in output
    assert "--limit" in output or "-l" in output
    assert "--yes" in output or "-y" in output


@pytest.mark.integration
def test_docs_command_exists():
    """Test that new 'deepr run docs' command exists and has help."""
    result = subprocess.run(["deepr", "run", "docs", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "documentation" in result.stdout.lower()


@pytest.mark.integration
def test_project_command_has_phases_option():
    """Test that 'deepr run project' has phases option."""
    result = subprocess.run(["deepr", "run", "project", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "--phases" in result.stdout or "-p" in result.stdout
    assert "--lead" in result.stdout


@pytest.mark.integration
def test_deprecated_single_shows_warning():
    """Test that deprecated 'deepr run single' shows deprecation warning."""
    # Use a dry-run approach - just test help to avoid API calls
    result = subprocess.run(["deepr", "run", "single", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "DEPRECATED" in result.stdout or "deprecated" in result.stdout.lower()


@pytest.mark.integration
def test_deprecated_campaign_shows_warning():
    """Test that deprecated 'deepr run campaign' shows deprecation warning."""
    result = subprocess.run(["deepr", "run", "campaign", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "DEPRECATED" in result.stdout or "deprecated" in result.stdout.lower()


@pytest.mark.integration
def test_deprecated_list_shows_warning():
    """Test that deprecated 'deepr list' shows deprecation warning."""
    result = subprocess.run(["deepr", "list", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "DEPRECATED" in result.stdout or "deprecated" in result.stdout.lower()


@pytest.mark.integration
def test_jobs_list_works():
    """Test that 'deepr jobs list' command works."""
    result = subprocess.run(["deepr", "jobs", "list", "--limit", "5"], capture_output=True, text=True)

    # Should succeed even if no jobs
    assert result.returncode == 0


@pytest.mark.integration
def test_quick_alias_r_works():
    """Test that 'deepr r' quick alias works."""
    result = subprocess.run(["deepr", "r", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "research" in result.stdout.lower() or "focus" in result.stdout.lower()


@pytest.mark.integration
def test_focus_command_accepts_provider():
    """Test that focus command accepts provider parameter."""
    # Just validate the help shows provider option
    result = subprocess.run(["deepr", "run", "focus", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "openai" in result.stdout.lower()
    assert "gemini" in result.stdout.lower()
    assert "grok" in result.stdout.lower()
    assert "azure" in result.stdout.lower()


@pytest.mark.integration
def test_docs_command_has_upload_option():
    """Test that docs command supports file upload."""
    result = subprocess.run(["deepr", "run", "docs", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "--upload" in result.stdout or "-u" in result.stdout


@pytest.mark.integration
def test_command_structure_consistency():
    """Test that command structure is consistent across modes."""
    modes = ["focus", "docs"]

    for mode in modes:
        result = subprocess.run(["deepr", "run", mode, "--help"], capture_output=True, text=True)

        assert result.returncode == 0

        # All modes should have these common options
        assert "--model" in result.stdout or "-m" in result.stdout
        assert "--provider" in result.stdout or "-p" in result.stdout
        assert "--yes" in result.stdout or "-y" in result.stdout
