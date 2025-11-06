"""Cross-platform path resolution utilities."""

import os
from pathlib import Path
from typing import List, Union
import glob as glob_module


def resolve_path(path_str: str) -> Path:
    """Resolve a path string to an absolute Path object.

    Handles:
    - Windows paths (C:\\Users\\..., C:/Users/...)
    - Unix paths (~/Documents/...)
    - Relative paths (./file.txt, ../file.txt)
    - Paths with spaces (properly quoted or not)
    - Environment variables (%USERPROFILE%, $HOME)

    Args:
        path_str: Path string in any format

    Returns:
        Absolute Path object

    Raises:
        FileNotFoundError: If path doesn't exist
    """
    # Strip quotes if present
    path_str = path_str.strip('"').strip("'")

    # Expand environment variables
    path_str = os.path.expandvars(path_str)

    # Expand user home directory (~)
    path_str = os.path.expanduser(path_str)

    # Convert to Path object and resolve to absolute
    path = Path(path_str).resolve()

    return path


def resolve_file_path(path_str: str, must_exist: bool = True) -> Path:
    """Resolve a file path and optionally check existence.

    Args:
        path_str: Path string
        must_exist: If True, raise error if file doesn't exist

    Returns:
        Absolute Path object

    Raises:
        FileNotFoundError: If must_exist=True and file doesn't exist
    """
    path = resolve_path(path_str)

    if must_exist and not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    return path


def resolve_glob_pattern(pattern: str, must_match: bool = False) -> List[Path]:
    """Resolve a glob pattern to list of matching files.

    Handles:
    - Simple globs (*.txt, file*.pdf)
    - Recursive globs (**/*.py)
    - Windows and Unix paths
    - Paths with spaces

    Args:
        pattern: Glob pattern string
        must_match: If True, raise error if no matches

    Returns:
        List of absolute Path objects

    Raises:
        FileNotFoundError: If must_match=True and no files match
    """
    # Strip quotes
    pattern = pattern.strip('"').strip("'")

    # Expand environment variables and user home
    pattern = os.path.expandvars(pattern)
    pattern = os.path.expanduser(pattern)

    # Use glob to find matches
    matches = glob_module.glob(pattern, recursive=True)

    if must_match and not matches:
        raise FileNotFoundError(f"No files match pattern: {pattern}")

    # Convert to Path objects and resolve
    return [Path(m).resolve() for m in matches]


def normalize_path_for_display(path: Union[str, Path]) -> str:
    """Normalize path for display (use forward slashes, show relative if possible).

    Args:
        path: Path string or Path object

    Returns:
        Normalized path string for display
    """
    path_obj = Path(path) if isinstance(path, str) else path

    try:
        # Try to make relative to current directory
        rel_path = path_obj.relative_to(Path.cwd())
        return str(rel_path).replace('\\', '/')
    except ValueError:
        # Not relative to cwd, use absolute with forward slashes
        return str(path_obj).replace('\\', '/')


def get_safe_filename(filename: str) -> str:
    """Convert a string to a safe filename (remove/replace invalid chars).

    Args:
        filename: Original filename

    Returns:
        Safe filename string
    """
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    safe_name = filename

    for char in invalid_chars:
        safe_name = safe_name.replace(char, '_')

    # Remove leading/trailing spaces and dots
    safe_name = safe_name.strip(' .')

    # Limit length
    if len(safe_name) > 255:
        safe_name = safe_name[:255]

    return safe_name


def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path

    Returns:
        Absolute Path object
    """
    dir_path = Path(path) if isinstance(path, str) else path
    dir_path = dir_path.resolve()
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path
