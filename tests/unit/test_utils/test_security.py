"""Unit tests for the security utility module.

Tests input sanitization, path validation, URL safety, and other security utilities.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from deepr.utils.security import (
    SecurityError,
    PathTraversalError,
    SSRFError,
    InvalidInputError,
    sanitize_name,
    validate_path,
    is_safe_url,
    validate_url,
    validate_file_size,
    validate_file_extension,
    validate_prompt_length,
    validate_api_key,
    sanitize_log_message
)


class TestSanitizeName:
    """Test sanitize_name function."""

    def test_sanitize_simple_name(self):
        """Test sanitizing simple name."""
        result = sanitize_name("my_expert")
        assert result == "my_expert"

    def test_sanitize_name_with_spaces(self):
        """Test sanitizing name with spaces."""
        result = sanitize_name("my expert")
        assert result == "my_expert"

    def test_sanitize_name_with_special_chars(self):
        """Test sanitizing name with special characters."""
        result = sanitize_name("my@expert#name!")
        assert "@" not in result
        assert "#" not in result
        assert "!" not in result

    def test_sanitize_path_traversal(self):
        """Test sanitizing path traversal attempt."""
        result = sanitize_name("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_sanitize_empty_name(self):
        """Test sanitizing empty name raises error."""
        with pytest.raises(InvalidInputError):
            sanitize_name("")

    def test_sanitize_only_special_chars(self):
        """Test sanitizing name with only special chars raises error."""
        with pytest.raises(InvalidInputError):
            sanitize_name("@#$%^&*()")

    def test_sanitize_collapses_underscores(self):
        """Test that multiple underscores are collapsed."""
        result = sanitize_name("my___expert___name")
        assert "___" not in result
        assert "__" not in result

    def test_sanitize_strips_leading_trailing(self):
        """Test that leading/trailing underscores are stripped."""
        result = sanitize_name("___expert___")
        assert not result.startswith("_")
        assert not result.endswith("_")


class TestValidatePath:
    """Test validate_path function."""

    def test_validate_relative_path(self):
        """Test validating relative path within base."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            subdir = base / "subdir"
            subdir.mkdir()
            
            result = validate_path("subdir", base)
            assert result == subdir

    def test_validate_path_traversal_blocked(self):
        """Test that path traversal is blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            
            with pytest.raises(PathTraversalError):
                validate_path("../../etc/passwd", base)

    def test_validate_absolute_path_within_base(self):
        """Test validating absolute path within base."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            subdir = base / "subdir"
            subdir.mkdir()
            
            result = validate_path(str(subdir), base)
            assert result == subdir

    def test_validate_absolute_path_outside_base(self):
        """Test that absolute path outside base is blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            
            with pytest.raises(PathTraversalError):
                validate_path("/etc/passwd", base)

    def test_validate_must_exist_true(self):
        """Test validate_path with must_exist=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            
            with pytest.raises(FileNotFoundError):
                validate_path("nonexistent", base, must_exist=True)

    def test_validate_must_exist_false(self):
        """Test validate_path with must_exist=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            
            result = validate_path("nonexistent", base, must_exist=False)
            assert result == base / "nonexistent"

    def test_validate_empty_path(self):
        """Test validating empty path raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(InvalidInputError):
                validate_path("", tmpdir)


class TestIsSafeUrl:
    """Test is_safe_url function."""

    def test_safe_https_url(self):
        """Test that HTTPS URL is safe."""
        # Mock DNS resolution to return a public IP
        with patch('socket.gethostbyname', return_value='93.184.216.34'):
            assert is_safe_url("https://example.com") is True

    def test_safe_http_url(self):
        """Test that HTTP URL is safe."""
        with patch('socket.gethostbyname', return_value='93.184.216.34'):
            assert is_safe_url("http://example.com") is True

    def test_unsafe_file_url(self):
        """Test that file:// URL is unsafe."""
        assert is_safe_url("file:///etc/passwd") is False

    def test_unsafe_ftp_url(self):
        """Test that FTP URL is unsafe."""
        assert is_safe_url("ftp://example.com") is False

    def test_unsafe_localhost(self):
        """Test that localhost is unsafe."""
        with patch('socket.gethostbyname', return_value='127.0.0.1'):
            assert is_safe_url("http://localhost") is False

    def test_unsafe_private_ip(self):
        """Test that private IP is unsafe."""
        with patch('socket.gethostbyname', return_value='192.168.1.1'):
            assert is_safe_url("http://192.168.1.1") is False

    def test_private_ip_allowed(self):
        """Test that private IP is allowed when allow_private=True."""
        with patch('socket.gethostbyname', return_value='192.168.1.1'):
            assert is_safe_url("http://192.168.1.1", allow_private=True) is True

    def test_unsafe_no_hostname(self):
        """Test that URL without hostname is unsafe."""
        assert is_safe_url("http://") is False

    def test_unsafe_invalid_url(self):
        """Test that invalid URL is unsafe."""
        assert is_safe_url("not a url") is False


class TestValidateUrl:
    """Test validate_url function."""

    def test_validate_safe_url(self):
        """Test validating safe URL returns it."""
        with patch('socket.gethostbyname', return_value='93.184.216.34'):
            result = validate_url("https://example.com")
            assert result == "https://example.com"

    def test_validate_unsafe_url_raises(self):
        """Test validating unsafe URL raises SSRFError."""
        with pytest.raises(SSRFError):
            validate_url("file:///etc/passwd")


class TestValidateFileSize:
    """Test validate_file_size function."""

    def test_validate_small_file(self):
        """Test validating small file passes."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"small content")
            f.flush()
            
            result = validate_file_size(f.name, max_size_mb=1)
            assert result.exists()

    def test_validate_large_file_fails(self):
        """Test validating large file fails."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            # Write 2MB of data
            f.write(b"x" * (2 * 1024 * 1024))
            f.flush()
            
            with pytest.raises(InvalidInputError):
                validate_file_size(f.name, max_size_mb=1)

    def test_validate_nonexistent_file(self):
        """Test validating nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            validate_file_size("/nonexistent/file.txt")


class TestValidateFileExtension:
    """Test validate_file_extension function."""

    def test_validate_allowed_extension(self):
        """Test validating allowed extension passes."""
        result = validate_file_extension("document.pdf", [".pdf", ".txt"])
        assert result.suffix == ".pdf"

    def test_validate_disallowed_extension(self):
        """Test validating disallowed extension fails."""
        with pytest.raises(InvalidInputError):
            validate_file_extension("script.exe", [".pdf", ".txt"])

    def test_validate_case_insensitive(self):
        """Test extension validation is case insensitive."""
        result = validate_file_extension("document.PDF", [".pdf", ".txt"])
        assert result.suffix == ".PDF"


class TestValidatePromptLength:
    """Test validate_prompt_length function."""

    def test_validate_short_prompt(self):
        """Test validating short prompt passes."""
        result = validate_prompt_length("short prompt")
        assert result == "short prompt"

    def test_validate_long_prompt_fails(self):
        """Test validating long prompt fails."""
        long_prompt = "x" * 100000
        with pytest.raises(InvalidInputError):
            validate_prompt_length(long_prompt, max_length=50000)

    def test_validate_at_limit(self):
        """Test validating prompt at exact limit passes."""
        prompt = "x" * 1000
        result = validate_prompt_length(prompt, max_length=1000)
        assert result == prompt


class TestValidateApiKey:
    """Test validate_api_key function."""

    def test_validate_empty_key(self):
        """Test validating empty key fails."""
        with pytest.raises(InvalidInputError):
            validate_api_key("", "openai")

    def test_validate_whitespace_key(self):
        """Test validating whitespace key fails."""
        with pytest.raises(InvalidInputError):
            validate_api_key("   ", "openai")

    def test_validate_openai_key_format(self):
        """Test validating OpenAI key format."""
        # Valid format
        result = validate_api_key("sk-proj-abcdefghijklmnopqrstuvwxyz", "openai")
        assert result.startswith("sk-")

    def test_validate_invalid_openai_key(self):
        """Test validating invalid OpenAI key fails."""
        with pytest.raises(InvalidInputError):
            validate_api_key("invalid-key", "openai")


class TestSanitizeLogMessage:
    """Test sanitize_log_message function."""

    def test_sanitize_api_key(self):
        """Test sanitizing API key in log message."""
        message = "Using API key: sk-proj-abc123xyz"
        result = sanitize_log_message(message)
        assert "sk-proj-abc123xyz" not in result
        assert "[REDACTED]" in result

    def test_sanitize_password(self):
        """Test sanitizing password in log message."""
        message = "password: mysecretpassword"
        result = sanitize_log_message(message)
        assert "mysecretpassword" not in result
        assert "[REDACTED]" in result

    def test_sanitize_token(self):
        """Test sanitizing token in log message."""
        message = "token: abc123token456"
        result = sanitize_log_message(message)
        assert "abc123token456" not in result
        assert "[REDACTED]" in result

    def test_sanitize_xai_key(self):
        """Test sanitizing xAI key in log message."""
        message = "Using xai-abcdefghijklmnop"
        result = sanitize_log_message(message)
        assert "xai-abcdefghijklmnop" not in result
        assert "[REDACTED]" in result

    def test_sanitize_preserves_normal_text(self):
        """Test that normal text is preserved."""
        message = "Processing request for user"
        result = sanitize_log_message(message)
        assert result == message


class TestSecurityEdgeCases:
    """Test edge cases in security utilities."""

    def test_sanitize_name_with_dashes(self):
        """Test sanitizing name with dashes."""
        result = sanitize_name("my-expert-name")
        assert result == "my-expert-name"

    def test_sanitize_name_with_numbers(self):
        """Test sanitizing name with numbers."""
        result = sanitize_name("expert123")
        assert result == "expert123"

    def test_validate_path_symlink(self):
        """Test validating symlink path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            target = base / "target"
            target.mkdir()
            
            # Create symlink within base
            link = base / "link"
            try:
                link.symlink_to(target)
                result = validate_path("link", base)
                assert result.exists()
            except OSError:
                # Symlinks may not be supported on all systems
                pytest.skip("Symlinks not supported")

    def test_is_safe_url_dns_failure(self):
        """Test URL safety when DNS fails."""
        with patch('socket.gethostbyname', side_effect=Exception("DNS failed")):
            assert is_safe_url("http://nonexistent.invalid") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
