"""CLI input validation utilities."""

from pathlib import Path
from typing import Optional

import click

from deepr.utils.paths import PathHandler
from deepr.utils.security import InvalidInputError, validate_file_extension, validate_file_size, validate_prompt_length

# Allowed file extensions for uploads
ALLOWED_DOCUMENT_EXTENSIONS = [
    ".pdf",
    ".txt",
    ".md",
    ".markdown",
    ".doc",
    ".docx",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".java",
    ".cpp",
    ".c",
    ".go",
    ".rs",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".csv",
    ".html",
    ".htm",
]

# Maximum file size (100MB default)
MAX_FILE_SIZE_MB = 100


def validate_upload_files(
    files: tuple[str, ...], max_size_mb: int = MAX_FILE_SIZE_MB, allowed_extensions: Optional[list[str]] = None
) -> list[Path]:
    """
    Validate uploaded files for security and size constraints.

    Uses PathHandler for cross-platform path normalization, supporting:
    - Windows paths (C:\\Users\\..., C:/Users/...)
    - Unix paths (~/Documents/...)
    - Paths with spaces (properly quoted or not)
    - Environment variables

    Args:
        files: Tuple of file paths from CLI
        max_size_mb: Maximum file size in megabytes
        allowed_extensions: List of allowed extensions (uses default if None)

    Returns:
        List of validated Path objects

    Raises:
        click.UsageError: If validation fails
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_DOCUMENT_EXTENSIONS

    validated_files = []

    for file_path in files:
        try:
            # Use PathHandler for cross-platform path normalization
            # This handles Windows/Unix paths, quotes, env vars, and ~ expansion
            path = PathHandler.normalize(file_path)

            # Validate path exists
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            # Validate extension
            validate_file_extension(path, allowed_extensions)

            # Validate size
            validate_file_size(path, max_size_mb=max_size_mb)

            validated_files.append(path)

        except InvalidInputError as e:
            raise click.UsageError(f"File validation failed for '{file_path}': {e}")
        except FileNotFoundError:
            # Provide helpful error message with shell-escaped path for copy-paste
            escaped_path = PathHandler.escape_for_shell(PathHandler.normalize(file_path))
            raise click.UsageError(f"File not found: {escaped_path}")
        except PermissionError:
            raise click.UsageError(f"Permission denied: '{file_path}'")

    return validated_files


def validate_prompt(prompt: str, max_length: int = 50000, field_name: str = "prompt") -> str:
    """
    Validate prompt length.

    Args:
        prompt: The prompt to validate
        max_length: Maximum prompt length in characters
        field_name: Name of field for error message

    Returns:
        The validated prompt

    Raises:
        click.UsageError: If prompt is too long
    """
    try:
        validate_prompt_length(prompt, max_length=max_length)
        return prompt
    except InvalidInputError as e:
        raise click.UsageError(f"{field_name} validation failed: {e}")


def validate_expert_name(name: str) -> str:
    """
    Validate expert name.

    Args:
        name: Expert name to validate

    Returns:
        The validated name

    Raises:
        click.UsageError: If name is invalid
    """
    if not name or not name.strip():
        raise click.UsageError("Expert name cannot be empty")

    if len(name) > 100:
        raise click.UsageError("Expert name too long (max 100 characters)")

    # Allow alphanumeric, spaces, hyphens, underscores
    import re

    if not re.match(r"^[a-zA-Z0-9 _-]+$", name):
        raise click.UsageError("Expert name can only contain letters, numbers, spaces, hyphens, and underscores")

    return name


def validate_budget(
    budget: float, min_budget: float = 0.0, warn_threshold: float = 10.0, confirm_threshold: float = 25.0
) -> float:
    """
    Validate budget value with warnings for high amounts.

    This doesn't hard-block high budgets - users can spend what they want.
    But it warns/confirms to prevent accidental overspending.

    Args:
        budget: Budget amount
        min_budget: Minimum allowed budget
        warn_threshold: Show warning above this amount (default $10)
        confirm_threshold: Require confirmation above this amount (default $25)

    Returns:
        The validated budget

    Raises:
        click.UsageError: If budget is below minimum
        click.Abort: If user declines confirmation for high budget
    """
    if budget < min_budget:
        raise click.UsageError(f"Budget cannot be less than ${min_budget:.2f}")

    # Warn for moderately high budgets
    if budget > warn_threshold and budget <= confirm_threshold:
        click.echo(f"[WARN] Budget ${budget:.2f} is above typical usage (${warn_threshold:.2f})")

    # Require confirmation for high budgets
    if budget > confirm_threshold:
        click.echo(f"\n[WARN] High budget: ${budget:.2f}")
        click.echo(f"This is above the typical limit of ${confirm_threshold:.2f}")
        if not click.confirm("Are you sure you want to proceed?", default=False):
            raise click.Abort()

    return budget


def confirm_high_cost_operation(estimated_cost: float, threshold: float = 5.0, skip_confirm: bool = False) -> bool:
    """
    Confirm high-cost operations with user.

    Args:
        estimated_cost: Estimated operation cost
        threshold: Cost threshold for confirmation
        skip_confirm: If True, skip confirmation prompt

    Returns:
        True if user confirms or skip_confirm is True

    Raises:
        click.Abort: If user cancels
    """
    if skip_confirm or estimated_cost < threshold:
        return True

    click.echo("\n[WARN] High Cost Warning")
    click.echo(f"Estimated cost: ${estimated_cost:.2f}")
    click.echo()

    if not click.confirm("Do you want to proceed?", default=False):
        raise click.Abort()

    return True
