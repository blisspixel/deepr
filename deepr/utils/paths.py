"""Cross-platform path resolution utilities with shell-specific quoting.

This module provides:
- Path normalization across Windows/Unix
- Shell-specific quoting for safe command execution
- Glob pattern resolution
- Path validation utilities

Shell Matrix Support:
- Windows CMD: double quotes, escape internal quotes with ""
- Windows PowerShell: single quotes, escape internal ' with ''
- macOS zsh / Linux bash: single quotes preferred, or escape special chars
"""

import os
import platform
import re
from pathlib import Path
from typing import List, Union, Optional
from enum import Enum
import glob as glob_module


class ShellType(Enum):
    """Supported shell types for quoting."""
    CMD = "cmd"
    POWERSHELL = "powershell"
    BASH = "bash"
    ZSH = "zsh"


class PathHandler:
    """Cross-platform path handling with shell-specific quoting.
    
    Satisfies the shell matrix requirement:
    - Windows CMD: double quotes, escape internal quotes with ""
    - Windows PowerShell: single quotes, escape internal ' with ''
    - macOS zsh / Linux bash: single quotes preferred, or escape special chars
    """
    
    # Characters requiring quoting per shell
    CMD_SPECIAL = set(' &()[]{}^=;!\'%')
    PS_SPECIAL = set(' `$(){}[]@#')
    POSIX_SPECIAL = set(' \\!*?[]{}();<>&|#~\'\"$`')
    
    @staticmethod
    def detect_shell() -> ShellType:
        """Detect current shell from environment.
        
        Detection order:
        1. DEEPR_SHELL env var (explicit override for testing)
        2. PSModulePath presence (PowerShell)
        3. SHELL env var (Unix)
        4. ComSpec (Windows CMD fallback)
        """
        # Explicit override for deterministic testing
        override = os.environ.get("DEEPR_SHELL", "").lower()
        if override in ("cmd", "powershell", "bash", "zsh"):
            return ShellType(override)
        
        # PowerShell detection (works on all platforms)
        if os.environ.get("PSModulePath"):
            return ShellType.POWERSHELL
        
        # Unix shell detection
        shell_path = os.environ.get("SHELL", "")
        if "zsh" in shell_path:
            return ShellType.ZSH
        if "bash" in shell_path:
            return ShellType.BASH
        
        # Windows fallback
        if platform.system() == "Windows":
            return ShellType.CMD
        
        # Default to bash for unknown Unix
        return ShellType.BASH
    
    @staticmethod
    def normalize(path: str) -> Path:
        """Normalize path for current platform.
        
        Handles:
        - Windows paths (C:\\Users\\..., C:/Users/...)
        - Unix paths (~/Documents/...)
        - Paths with spaces
        - Relative paths
        - Environment variables
        """
        # Strip quotes if present
        path = path.strip('"').strip("'")
        
        # Expand environment variables
        path = os.path.expandvars(path)
        
        # Expand user home directory (~)
        if path.startswith("~"):
            path = os.path.expanduser(path)
        
        p = Path(path)
        return p.resolve()
    
    @classmethod
    def escape_for_shell(cls, path: Path, shell: Optional[ShellType] = None) -> str:
        """Escape path for specified shell (or auto-detect).
        
        Pure functions per shell type ensure correct quoting.
        """
        shell = shell or cls.detect_shell()
        path_str = str(path)
        
        if shell == ShellType.CMD:
            return cls._quote_cmd(path_str)
        elif shell == ShellType.POWERSHELL:
            return cls._quote_powershell(path_str)
        else:  # BASH or ZSH
            return cls._quote_posix(path_str)
    
    @staticmethod
    def _quote_cmd(s: str) -> str:
        """Quote for Windows CMD.
        
        Rules:
        - Wrap in double quotes if contains special chars
        - Escape internal " with ""
        - Escape % with %% (variable expansion)
        """
        needs_quote = any(c in PathHandler.CMD_SPECIAL for c in s) or '"' in s
        
        if not needs_quote:
            return s
        
        # Escape internal quotes and percent signs
        escaped = s.replace('"', '""').replace('%', '%%')
        return f'"{escaped}"'
    
    @staticmethod
    def _quote_powershell(s: str) -> str:
        """Quote for PowerShell.
        
        Rules:
        - Prefer single quotes (no variable expansion)
        - Escape internal ' with ''
        """
        needs_quote = any(c in PathHandler.PS_SPECIAL for c in s) or "'" in s
        
        if not needs_quote:
            return s
        
        # Single quotes: escape ' with ''
        escaped = s.replace("'", "''")
        return f"'{escaped}'"
    
    @staticmethod
    def _quote_posix(s: str) -> str:
        """Quote for bash/zsh.
        
        Rules:
        - Prefer single quotes (no expansion except ')
        - For strings with ', use $'...' syntax or escape
        """
        needs_quote = any(c in PathHandler.POSIX_SPECIAL for c in s)
        
        if not needs_quote:
            return s
        
        # If no single quotes, use single quoting (safest)
        if "'" not in s:
            return f"'{s}'"
        
        # Has single quotes: use $'...' with escaping
        escaped = s.replace("\\", "\\\\").replace("'", "\\'")
        return f"$'{escaped}'"
    
    @staticmethod
    def validate(path: str, must_exist: bool = True) -> Path:
        """Validate path exists and is accessible.
        
        Args:
            path: Path string to validate
            must_exist: If True, raise error if path doesn't exist
            
        Returns:
            Normalized absolute Path
            
        Raises:
            FileNotFoundError: If must_exist=True and path doesn't exist
            PermissionError: If path exists but is not accessible
        """
        normalized = PathHandler.normalize(path)
        
        if must_exist:
            if not normalized.exists():
                raise FileNotFoundError(f"Path not found: {normalized}")
            # Check accessibility
            try:
                normalized.stat()
            except PermissionError:
                raise PermissionError(f"Path not accessible: {normalized}")
        
        return normalized
    
    @classmethod
    def format_for_display(cls, path: Path, shell: Optional[ShellType] = None) -> str:
        """Format path for display with shell-appropriate quoting.
        
        Returns the escaped path string suitable for copy-paste into terminal.
        """
        escaped = cls.escape_for_shell(path, shell)
        return escaped


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
