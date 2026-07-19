"""Coverage tests for ``deepr/utils/security.py`` helpers.

These functions sit on user-input boundaries - path validation, SSRF check,
file-size + extension limits, API-key shape, log redaction. They previously
had no dedicated unit tests; the existing ``test_security.py`` covers the
PromptSanitizer in ``prompt_security.py``.
"""

import ipaddress
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.utils.security import (
    InvalidInputError,
    PathTraversalError,
    SSRFError,
    is_blocked_ip,
    is_loopback_bind_host,
    is_safe_url,
    resolve_all_ips,
    resolve_safe_url_ips,
    sanitize_log_message,
    sanitize_name,
    validate_api_key,
    validate_file_extension,
    validate_file_size,
    validate_path,
    validate_prompt_length,
    validate_url,
)


class TestSanitizeName:
    def test_replaces_disallowed_chars(self):
        out = sanitize_name("hello world!", allowed_chars=r"\w")
        # spaces and ! collapsed into single underscores
        assert "_" in out or out.isalnum()

    def test_raises_on_empty_after_sanitize(self):
        with pytest.raises(InvalidInputError, match="empty"):
            sanitize_name("!!!", allowed_chars=r"\w")

    def test_raise_on_change_flag(self):
        with pytest.raises(InvalidInputError, match="not permitted"):
            sanitize_name("a b", allowed_chars=r"\w", raise_on_change=True)


class TestValidatePath:
    def test_empty_path_raises(self, tmp_path):
        with pytest.raises(InvalidInputError, match="empty"):
            validate_path("", tmp_path)

    def test_traversal_blocked(self, tmp_path):
        with pytest.raises(PathTraversalError):
            validate_path("../../etc/passwd", tmp_path)

    def test_safe_relative_path(self, tmp_path):
        out = validate_path("subdir/file.txt", tmp_path)
        assert tmp_path in out.parents or tmp_path == out.parent.parent

    def test_must_exist_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            validate_path("missing.txt", tmp_path, must_exist=True)

    def test_no_create_missing_raises(self, tmp_path):
        with pytest.raises(InvalidInputError, match="creation not allowed"):
            validate_path("missing.txt", tmp_path, allow_create=False)

    def test_absolute_within_base_allowed(self, tmp_path):
        f = tmp_path / "sub" / "f"
        out = validate_path(str(f), tmp_path)
        assert str(out).startswith(str(tmp_path))


class TestIsBlockedIp:
    def test_private_ip_blocked_by_default(self):
        assert is_blocked_ip(ipaddress.ip_address("192.168.1.1"))

    def test_loopback_blocked_by_default(self):
        assert is_blocked_ip(ipaddress.ip_address("127.0.0.1"))

    def test_link_local_blocked(self):
        assert is_blocked_ip(ipaddress.ip_address("169.254.1.1"))

    def test_multicast_blocked(self):
        assert is_blocked_ip(ipaddress.ip_address("224.0.0.1"))

    def test_public_ip_not_blocked(self):
        assert not is_blocked_ip(ipaddress.ip_address("8.8.8.8"))

    def test_allow_private_lets_private_through(self):
        assert not is_blocked_ip(ipaddress.ip_address("192.168.1.1"), allow_private=True)


class TestIsLoopbackBindHost:
    def test_loopback_bind_hosts_are_local(self):
        assert is_loopback_bind_host("localhost")
        assert is_loopback_bind_host("127.0.0.1")
        assert is_loopback_bind_host("127.0.0.5")
        assert is_loopback_bind_host("::1")

    def test_empty_host_is_not_local(self):
        assert not is_loopback_bind_host("")
        assert not is_loopback_bind_host(None)

    def test_non_loopback_bind_hosts_are_not_local(self):
        assert not is_loopback_bind_host("0.0.0.0")
        assert not is_loopback_bind_host("::")
        assert not is_loopback_bind_host("203.0.113.5")


class TestResolveAllIps:
    def test_unknown_host_returns_empty(self):
        with patch(
            "deepr.utils.security.socket.getaddrinfo",
            side_effect=__import__("socket").gaierror("no DNS"),
        ):
            assert resolve_all_ips("nonexistent.invalid") == []

    def test_known_host_returns_ips(self):
        with patch("deepr.utils.security.socket.getaddrinfo") as ga:
            ga.return_value = [
                (0, 0, 0, "", ("93.184.216.34", 0)),
                (0, 0, 0, "", ("2606:2800:220:1:248:1893:25c8:1946", 0)),
            ]
            ips = resolve_all_ips("example.com")
            assert "93.184.216.34" in ips


class TestIsSafeUrl:
    def test_rejects_non_http_scheme(self):
        assert not is_safe_url("file:///etc/passwd")
        assert not is_safe_url("ftp://example.com")
        assert not is_safe_url("javascript:alert(1)")

    def test_rejects_missing_host(self):
        assert not is_safe_url("http://")

    def test_rejects_private_resolution(self):
        with patch("deepr.utils.security.resolve_all_ips", return_value=["10.0.0.5"]):
            assert not is_safe_url("http://corp.internal")

    def test_rejects_when_dns_fails(self):
        with patch("deepr.utils.security.resolve_all_ips", return_value=[]):
            assert not is_safe_url("http://nonexistent.invalid")

    def test_allows_public(self):
        with patch("deepr.utils.security.resolve_all_ips", return_value=["93.184.216.34"]):
            assert is_safe_url("http://example.com")

    def test_invalid_ip_string_blocked(self):
        # Implementation guards against malformed IPs (ipaddress.ip_address raises).
        with patch("deepr.utils.security.resolve_all_ips", return_value=["not-an-ip"]):
            assert not is_safe_url("http://example.com")

    def test_allow_private_lets_private_through(self):
        with patch("deepr.utils.security.resolve_all_ips", return_value=["192.168.1.5"]):
            assert is_safe_url("http://example.com", allow_private=True)

    def test_rejects_rfc6598_shared_address_space(self):
        with patch("deepr.utils.security.resolve_all_ips", return_value=["100.64.0.1"]):
            assert not is_safe_url("http://shared.example")
            with pytest.raises(SSRFError):
                resolve_safe_url_ips("http://shared.example")

    def test_resolved_fetch_addresses_are_frozen_and_sorted(self):
        with patch(
            "deepr.utils.security.resolve_all_ips",
            return_value=["2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34"],
        ):
            assert resolve_safe_url_ips("https://example.com/path") == (
                "93.184.216.34",
                "2606:2800:220:1:248:1893:25c8:1946",
            )


class TestValidateUrl:
    def test_safe_url_returned(self):
        with patch("deepr.utils.security.is_safe_url", return_value=True):
            assert validate_url("http://example.com") == "http://example.com"

    def test_unsafe_url_raises(self):
        with patch("deepr.utils.security.is_safe_url", return_value=False):
            with pytest.raises(SSRFError):
                validate_url("http://internal")


class TestValidateFileSize:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            validate_file_size(tmp_path / "nope.txt", max_size_mb=1)

    def test_small_file_returns_path(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_text("hi")
        assert validate_file_size(f, max_size_mb=1) == f

    def test_oversize_raises(self, tmp_path):
        f = tmp_path / "big.bin"
        f.write_bytes(b"\x00" * (2 * 1024 * 1024))  # 2 MB
        with pytest.raises(InvalidInputError, match="exceeds limit"):
            validate_file_size(f, max_size_mb=1)


class TestValidateFileExtension:
    def test_allowed(self):
        out = validate_file_extension("doc.pdf", [".pdf", ".txt"])
        assert out.name == "doc.pdf"

    def test_disallowed_raises(self):
        with pytest.raises(InvalidInputError, match="not allowed"):
            validate_file_extension("malware.exe", [".pdf", ".txt"])

    def test_case_insensitive(self):
        out = validate_file_extension("Doc.PDF", [".pdf"])
        assert out.name == "Doc.PDF"


class TestValidatePromptLength:
    def test_short_ok(self):
        assert validate_prompt_length("short") == "short"

    def test_too_long_raises(self):
        with pytest.raises(InvalidInputError, match="exceeds limit"):
            validate_prompt_length("x" * 100, max_length=50)


class TestValidateApiKey:
    @pytest.mark.parametrize(
        "key,provider",
        [
            ("sk-proj-abcdefghijklmnopqrstuvwx", "openai"),
            ("sk-ant-abcdefghijklmnopqrstuvwx", "anthropic"),
            ("xai-abcdefghijklmnopqrstuvwx", "xai"),
            ("a" * 32, "azure"),
            ("abcdefghijklmnopqrstuvwx", "gemini"),
        ],
    )
    def test_valid_formats(self, key, provider):
        assert validate_api_key(key, provider) == key

    def test_empty_raises(self):
        with pytest.raises(InvalidInputError, match="empty"):
            validate_api_key("", "openai")

    def test_whitespace_only_raises(self):
        with pytest.raises(InvalidInputError, match="empty"):
            validate_api_key("   ", "openai")

    def test_wrong_format_raises(self):
        with pytest.raises(InvalidInputError, match="format"):
            validate_api_key("wrong-prefix-key", "openai")

    def test_unknown_provider_accepts_any_nonempty(self):
        # No pattern configured for unknown providers - just non-empty check.
        out = validate_api_key("whatever", "groq")
        assert out == "whatever"


class TestSanitizeLogMessage:
    def test_redacts_openai_keys(self):
        s = sanitize_log_message("Failed with key sk-proj-abc123def456ghi789jkl0")
        assert "sk-proj-abc123def456ghi789jkl0" not in s

    def test_passthrough_for_safe_text(self):
        s = sanitize_log_message("Just a normal log line.")
        assert s == "Just a normal log line." or "REDACTED" not in s
