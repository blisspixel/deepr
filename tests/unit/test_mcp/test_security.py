"""
Tests for MCP Security module.

Validates:
- SSRF protection (internal IP blocking)
- Domain allowlisting
- Sampling request/response primitives
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.security.network import (
    SSRFProtector,
    is_internal_ip,
    resolve_hostname,
    BLOCKED_NETWORKS,
)
from deepr.mcp.security.sampling import (
    SamplingRequest,
    SamplingResponse,
    SamplingReason,
    create_captcha_request,
    create_paywall_request,
    create_confirmation_request,
)


# ------------------------------------------------------------------ #
# is_internal_ip
# ------------------------------------------------------------------ #

class TestIsInternalIP:

    @pytest.mark.parametrize("ip", [
        "127.0.0.1",
        "127.0.0.2",
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.1.100",
        "169.254.1.1",
    ])
    def test_blocks_internal_ipv4(self, ip):
        assert is_internal_ip(ip) is True

    @pytest.mark.parametrize("ip", [
        "8.8.8.8",
        "1.1.1.1",
        "104.18.32.7",
        "13.107.42.14",
    ])
    def test_allows_public_ipv4(self, ip):
        assert is_internal_ip(ip) is False

    @pytest.mark.parametrize("ip", [
        "::1",
        "fc00::1",
        "fe80::1",
    ])
    def test_blocks_internal_ipv6(self, ip):
        assert is_internal_ip(ip) is True

    def test_blocks_unparseable(self):
        """Unparseable IPs should be blocked for safety."""
        assert is_internal_ip("not_an_ip") is True

    def test_blocked_networks_list_not_empty(self):
        assert len(BLOCKED_NETWORKS) >= 5


# ------------------------------------------------------------------ #
# SSRFProtector
# ------------------------------------------------------------------ #

class TestSSRFProtector:

    def test_allows_public_url(self):
        protector = SSRFProtector()
        with patch("deepr.mcp.security.network.resolve_hostname", return_value="8.8.8.8"):
            url = protector.validate_url("https://api.openai.com/v1/chat")
            assert url == "https://api.openai.com/v1/chat"

    def test_blocks_localhost(self):
        protector = SSRFProtector()
        with patch("deepr.mcp.security.network.resolve_hostname", return_value="127.0.0.1"):
            with pytest.raises(ValueError, match="SSRF blocked"):
                protector.validate_url("http://localhost/admin")

    def test_blocks_internal_ip_url(self):
        protector = SSRFProtector()
        with patch("deepr.mcp.security.network.resolve_hostname", return_value="10.0.0.5"):
            with pytest.raises(ValueError, match="SSRF blocked"):
                protector.validate_url("http://internal-service.local/api")

    def test_blocks_private_class_c(self):
        protector = SSRFProtector()
        with patch("deepr.mcp.security.network.resolve_hostname", return_value="192.168.1.1"):
            with pytest.raises(ValueError, match="SSRF blocked"):
                protector.validate_url("http://router.home/config")

    def test_blocks_link_local(self):
        protector = SSRFProtector()
        with patch("deepr.mcp.security.network.resolve_hostname", return_value="169.254.169.254"):
            with pytest.raises(ValueError, match="SSRF blocked"):
                protector.validate_url("http://metadata.google.internal/")

    def test_blocks_no_hostname(self):
        protector = SSRFProtector()
        with pytest.raises(ValueError, match="no hostname"):
            protector.validate_url("file:///etc/passwd")

    def test_allows_unresolved_hostname(self):
        """If DNS resolution fails, URL should still be allowed (no IP to check)."""
        protector = SSRFProtector()
        with patch("deepr.mcp.security.network.resolve_hostname", return_value=None):
            url = protector.validate_url("https://some-api.example.com/data")
            assert url == "https://some-api.example.com/data"


# ------------------------------------------------------------------ #
# SSRFProtector: domain allowlist
# ------------------------------------------------------------------ #

class TestDomainAllowlist:

    def test_allows_listed_domain(self):
        protector = SSRFProtector(allowed_domains=["api.openai.com"])
        with patch("deepr.mcp.security.network.resolve_hostname", return_value="8.8.8.8"):
            url = protector.validate_url("https://api.openai.com/v1/models")
            assert "openai" in url

    def test_blocks_unlisted_domain(self):
        protector = SSRFProtector(allowed_domains=["api.openai.com"])
        with pytest.raises(ValueError, match="not in allowlist"):
            protector.validate_url("https://evil.com/steal")

    def test_multiple_allowed_domains(self):
        protector = SSRFProtector(
            allowed_domains=["api.openai.com", "api.x.ai", "api.google.com"]
        )
        with patch("deepr.mcp.security.network.resolve_hostname", return_value="8.8.8.8"):
            protector.validate_url("https://api.openai.com/v1")
            protector.validate_url("https://api.x.ai/v1")
            protector.validate_url("https://api.google.com/v1")

    def test_no_allowlist_allows_all_public(self):
        protector = SSRFProtector(allowed_domains=None)
        with patch("deepr.mcp.security.network.resolve_hostname", return_value="8.8.8.8"):
            protector.validate_url("https://any-domain.com/api")


# ------------------------------------------------------------------ #
# SSRFProtector: validate_ip
# ------------------------------------------------------------------ #

class TestValidateIP:

    def test_allows_public_ip(self):
        protector = SSRFProtector()
        assert protector.validate_ip("8.8.8.8") == "8.8.8.8"

    def test_blocks_internal_ip(self):
        protector = SSRFProtector()
        with pytest.raises(ValueError, match="SSRF blocked"):
            protector.validate_ip("127.0.0.1")

    def test_blocks_private_ip(self):
        protector = SSRFProtector()
        with pytest.raises(ValueError, match="SSRF blocked"):
            protector.validate_ip("10.0.0.1")


# ------------------------------------------------------------------ #
# Sampling primitives
# ------------------------------------------------------------------ #

class TestSamplingRequest:

    def test_to_mcp_params(self):
        req = SamplingRequest(
            reason=SamplingReason.CAPTCHA,
            prompt="Solve this CAPTCHA",
            url="https://example.com",
        )
        params = req.to_mcp_params()

        assert "messages" in params
        assert params["messages"][0]["role"] == "user"
        assert "CAPTCHA" in params["messages"][0]["content"]["text"]
        assert params["maxTokens"] == 1024
        assert params["metadata"]["reason"] == "captcha"
        assert params["metadata"]["url"] == "https://example.com"

    def test_default_max_tokens(self):
        req = SamplingRequest(reason=SamplingReason.CONFIRMATION, prompt="Confirm?")
        assert req.max_tokens == 1024


class TestSamplingResponse:

    def test_from_mcp_result(self):
        result = {
            "content": {"type": "text", "text": "yes"},
            "stopReason": "endTurn",
            "metadata": {"source": "user"},
        }
        resp = SamplingResponse.from_mcp_result(result)
        assert resp.content == "yes"
        assert resp.approved is True
        assert resp.metadata["source"] == "user"

    def test_from_mcp_result_cancelled(self):
        result = {
            "content": {"type": "text", "text": ""},
            "stopReason": "cancelled",
        }
        resp = SamplingResponse.from_mcp_result(result)
        assert resp.approved is False

    def test_from_mcp_result_string_content(self):
        result = {"content": "raw string response"}
        resp = SamplingResponse.from_mcp_result(result)
        assert resp.content == "raw string response"


class TestSamplingFactories:

    def test_create_captcha_request(self):
        req = create_captcha_request("https://example.com", "Image CAPTCHA")
        assert req.reason == SamplingReason.CAPTCHA
        assert "example.com" in req.prompt
        assert req.url == "https://example.com"

    def test_create_paywall_request(self):
        req = create_paywall_request("https://wsj.com/article", "Market Analysis")
        assert req.reason == SamplingReason.PAYWALL
        assert "wsj.com" in req.prompt
        assert req.context["title"] == "Market Analysis"

    def test_create_confirmation_request(self):
        req = create_confirmation_request("Delete all data", "This is irreversible")
        assert req.reason == SamplingReason.CONFIRMATION
        assert "Delete all data" in req.prompt
        assert req.url is None
