"""Unit tests for the paths utility module.

Tests cross-platform path resolution, glob patterns, filename sanitization,
and the PathHandler class for shell-specific quoting.
"""

import pytest
import os
import tempfile
from pathlib import Path

from deepr.utils.paths import (
    resolve_path,
    resolve_file_path,
    resolve_glob_pattern,
    normalize_path_for_display,
    get_safe_filename,
    ensure_directory,
    PathHandler,
    ShellType
)


class TestResolvePath:
    """Test resolve_path function."""

    def test_resolve_relative_path(self):
        """Test resolving relative path."""
        path = resolve_path(".")
        assert path.is_absolute()
        assert path == Path.cwd()

    def test_resolve_absolute_path(self):
        """Test resolving absolute path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = resolve_path(tmpdir)
            assert path.is_absolute()
            assert str(path) == str(Path(tmpdir).resolve())

    def test_resolve_path_with_quotes(self):
        """Test resolving path with quotes."""
        path = resolve_path('"."')
        assert path == Path.cwd()
        
        path = resolve_path("'.'")
        assert path == Path.cwd()

    def test_resolve_path_with_tilde(self):
        """Test resolving path with home directory tilde."""
        path = resolve_path("~")
        assert path.is_absolute()
        assert path == Path.home()

    def test_resolve_path_with_env_var(self):
        """Test resolving path with environment variable."""
        # Set a test environment variable
        os.environ["TEST_PATH_VAR"] = str(Path.cwd())
        
        if os.name == 'nt':  # Windows
            path = resolve_path("%TEST_PATH_VAR%")
        else:  # Unix
            path = resolve_path("$TEST_PATH_VAR")
        
        assert path.is_absolute()
        
        # Clean up
        del os.environ["TEST_PATH_VAR"]


class TestResolveFilePath:
    """Test resolve_file_path function."""

    def test_resolve_existing_file(self):
        """Test resolving existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")
            
            path = resolve_file_path(str(test_file), must_exist=True)
            assert path.exists()
            assert path.is_file()

    def test_resolve_nonexistent_file_must_exist(self):
        """Test resolving nonexistent file with must_exist=True."""
        with pytest.raises(FileNotFoundError):
            resolve_file_path("/nonexistent/path/file.txt", must_exist=True)

    def test_resolve_nonexistent_file_no_must_exist(self):
        """Test resolving nonexistent file with must_exist=False."""
        path = resolve_file_path("/some/path/file.txt", must_exist=False)
        assert path.is_absolute()


class TestResolveGlobPattern:
    """Test resolve_glob_pattern function."""

    def test_glob_simple_pattern(self):
        """Test simple glob pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "file1.txt").write_text("test1")
            (Path(tmpdir) / "file2.txt").write_text("test2")
            (Path(tmpdir) / "file3.md").write_text("test3")
            
            pattern = str(Path(tmpdir) / "*.txt")
            matches = resolve_glob_pattern(pattern)
            
            assert len(matches) == 2
            assert all(m.suffix == ".txt" for m in matches)

    def test_glob_recursive_pattern(self):
        """Test recursive glob pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            
            (Path(tmpdir) / "file1.txt").write_text("test1")
            (subdir / "file2.txt").write_text("test2")
            
            pattern = str(Path(tmpdir) / "**/*.txt")
            matches = resolve_glob_pattern(pattern)
            
            assert len(matches) == 2

    def test_glob_no_matches(self):
        """Test glob with no matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pattern = str(Path(tmpdir) / "*.nonexistent")
            matches = resolve_glob_pattern(pattern)
            assert matches == []

    def test_glob_no_matches_must_match(self):
        """Test glob with no matches and must_match=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pattern = str(Path(tmpdir) / "*.nonexistent")
            with pytest.raises(FileNotFoundError):
                resolve_glob_pattern(pattern, must_match=True)

    def test_glob_with_quotes(self):
        """Test glob pattern with quotes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "file.txt").write_text("test")
            
            pattern = f'"{tmpdir}/*.txt"'
            matches = resolve_glob_pattern(pattern)
            
            assert len(matches) == 1


class TestNormalizePathForDisplay:
    """Test normalize_path_for_display function."""

    def test_normalize_relative_path(self):
        """Test normalizing relative path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")
            
            normalized = normalize_path_for_display(test_file)
            
            # Should use forward slashes
            assert "\\" not in normalized

    def test_normalize_absolute_path(self):
        """Test normalizing absolute path."""
        path = Path("/some/absolute/path/file.txt")
        normalized = normalize_path_for_display(path)
        
        # Should use forward slashes
        assert "\\" not in normalized

    def test_normalize_string_path(self):
        """Test normalizing string path."""
        normalized = normalize_path_for_display("some/path/file.txt")
        assert "\\" not in normalized


class TestGetSafeFilename:
    """Test get_safe_filename function."""

    def test_safe_filename_simple(self):
        """Test safe filename with simple input."""
        result = get_safe_filename("document.pdf")
        assert result == "document.pdf"

    def test_safe_filename_with_spaces(self):
        """Test safe filename with spaces."""
        result = get_safe_filename("my document.pdf")
        assert result == "my document.pdf"

    def test_safe_filename_with_invalid_chars(self):
        """Test safe filename with invalid characters."""
        result = get_safe_filename('file<>:"/\\|?*.txt')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_safe_filename_leading_trailing_spaces(self):
        """Test safe filename strips leading/trailing spaces."""
        result = get_safe_filename("  document.pdf  ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_safe_filename_leading_trailing_dots(self):
        """Test safe filename strips leading/trailing dots."""
        result = get_safe_filename("..document.pdf..")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_safe_filename_long_name(self):
        """Test safe filename truncates long names."""
        long_name = "a" * 300 + ".txt"
        result = get_safe_filename(long_name)
        assert len(result) <= 255

    def test_safe_filename_path_traversal(self):
        """Test safe filename handles path traversal attempts."""
        result = get_safe_filename("../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result


class TestEnsureDirectory:
    """Test ensure_directory function."""

    def test_ensure_existing_directory(self):
        """Test ensuring existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ensure_directory(tmpdir)
            assert result.exists()
            assert result.is_dir()

    def test_ensure_new_directory(self):
        """Test ensuring new directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_subdir"
            assert not new_dir.exists()
            
            result = ensure_directory(new_dir)
            
            assert result.exists()
            assert result.is_dir()

    def test_ensure_nested_directory(self):
        """Test ensuring nested directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "level1" / "level2" / "level3"
            assert not nested.exists()
            
            result = ensure_directory(nested)
            
            assert result.exists()
            assert result.is_dir()

    def test_ensure_directory_string_path(self):
        """Test ensuring directory with string path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = str(Path(tmpdir) / "string_dir")
            
            result = ensure_directory(new_dir)
            
            assert result.exists()
            assert result.is_dir()

    def test_ensure_directory_returns_absolute(self):
        """Test that ensure_directory returns absolute path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ensure_directory(tmpdir)
            assert result.is_absolute()


class TestPathsEdgeCases:
    """Test edge cases in path utilities."""

    def test_resolve_empty_path(self):
        """Test resolving empty path."""
        # Empty string should resolve to current directory
        path = resolve_path("")
        assert path.is_absolute()

    def test_safe_filename_unicode(self):
        """Test safe filename with unicode characters."""
        result = get_safe_filename("文档.pdf")
        assert result  # Should not be empty

    def test_safe_filename_emoji(self):
        """Test safe filename with emoji."""
        result = get_safe_filename("document 📄.pdf")
        assert result  # Should not be empty

    def test_normalize_windows_path(self):
        """Test normalizing Windows-style path."""
        normalized = normalize_path_for_display("C:\\Users\\test\\file.txt")
        assert "\\" not in normalized


class TestPathHandler:
    """Test PathHandler class for cross-platform path handling."""

    def test_detect_shell_with_override(self, monkeypatch):
        """Test shell detection with DEEPR_SHELL override."""
        monkeypatch.setenv("DEEPR_SHELL", "powershell")
        assert PathHandler.detect_shell() == ShellType.POWERSHELL
        
        monkeypatch.setenv("DEEPR_SHELL", "cmd")
        assert PathHandler.detect_shell() == ShellType.CMD
        
        monkeypatch.setenv("DEEPR_SHELL", "bash")
        assert PathHandler.detect_shell() == ShellType.BASH
        
        monkeypatch.setenv("DEEPR_SHELL", "zsh")
        assert PathHandler.detect_shell() == ShellType.ZSH

    def test_normalize_simple_path(self):
        """Test normalizing simple path."""
        path = PathHandler.normalize(".")
        assert path.is_absolute()
        assert path == Path.cwd()

    def test_normalize_path_with_quotes(self):
        """Test normalizing path with quotes."""
        path = PathHandler.normalize('"."')
        assert path == Path.cwd()
        
        path = PathHandler.normalize("'.'")
        assert path == Path.cwd()

    def test_normalize_path_with_tilde(self):
        """Test normalizing path with home directory tilde."""
        path = PathHandler.normalize("~")
        assert path.is_absolute()
        assert path == Path.home()

    def test_normalize_path_with_env_var(self, monkeypatch):
        """Test normalizing path with environment variable."""
        monkeypatch.setenv("TEST_PATH_VAR", str(Path.cwd()))
        
        if os.name == 'nt':  # Windows
            path = PathHandler.normalize("%TEST_PATH_VAR%")
        else:  # Unix
            path = PathHandler.normalize("$TEST_PATH_VAR")
        
        assert path.is_absolute()

    def test_escape_for_shell_cmd(self, monkeypatch):
        """Test escaping path for Windows CMD."""
        monkeypatch.setenv("DEEPR_SHELL", "cmd")
        
        # Path without special chars - no quoting needed
        simple_path = Path("/simple/path")
        escaped = PathHandler.escape_for_shell(simple_path)
        # Simple paths may or may not be quoted depending on content
        
        # Path with spaces - needs quoting
        space_path = Path("/path with spaces/file.txt")
        escaped = PathHandler.escape_for_shell(space_path)
        assert '"' in escaped or "'" in escaped or " " not in escaped

    def test_escape_for_shell_powershell(self, monkeypatch):
        """Test escaping path for PowerShell."""
        monkeypatch.setenv("DEEPR_SHELL", "powershell")
        
        # Path with special chars
        special_path = Path("/path with $var/file.txt")
        escaped = PathHandler.escape_for_shell(special_path)
        # PowerShell uses single quotes
        assert "'" in escaped or "$" not in escaped

    def test_escape_for_shell_bash(self, monkeypatch):
        """Test escaping path for bash."""
        monkeypatch.setenv("DEEPR_SHELL", "bash")
        
        # Path with spaces
        space_path = Path("/path with spaces/file.txt")
        escaped = PathHandler.escape_for_shell(space_path)
        assert "'" in escaped or "\\" in escaped or " " not in escaped

    def test_validate_existing_path(self):
        """Test validating existing path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")
            
            validated = PathHandler.validate(str(test_file), must_exist=True)
            assert validated.exists()
            assert validated.is_absolute()

    def test_validate_nonexistent_path_must_exist(self):
        """Test validating nonexistent path with must_exist=True."""
        with pytest.raises(FileNotFoundError):
            PathHandler.validate("/nonexistent/path/file.txt", must_exist=True)

    def test_validate_nonexistent_path_no_must_exist(self):
        """Test validating nonexistent path with must_exist=False."""
        path = PathHandler.validate("/some/path/file.txt", must_exist=False)
        assert path.is_absolute()

    def test_format_for_display(self, monkeypatch):
        """Test formatting path for display."""
        monkeypatch.setenv("DEEPR_SHELL", "bash")
        
        path = Path("/path with spaces/file.txt")
        formatted = PathHandler.format_for_display(path)
        # Should be properly escaped for the shell
        assert formatted  # Not empty

    def test_quote_cmd_special_chars(self):
        """Test CMD quoting with special characters."""
        # Test internal method
        result = PathHandler._quote_cmd("path with spaces")
        assert '"' in result
        
        # Test percent escaping
        result = PathHandler._quote_cmd("path%var%")
        assert "%%" in result

    def test_quote_powershell_special_chars(self):
        """Test PowerShell quoting with special characters."""
        # Test internal method
        result = PathHandler._quote_powershell("path with spaces")
        assert "'" in result
        
        # Test single quote escaping
        result = PathHandler._quote_powershell("path'with'quotes")
        assert "''" in result

    def test_quote_posix_special_chars(self):
        """Test POSIX quoting with special characters."""
        # Test internal method
        result = PathHandler._quote_posix("path with spaces")
        assert "'" in result
        
        # Test path without special chars
        result = PathHandler._quote_posix("simple_path")
        assert result == "simple_path"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
