"""Tests for Streamable HTTP server validation: metadata headers, the Base64
sentinel, and Origin enforcement."""

import base64

import pytest

from deepr.mcp import protocol_modern as pm
from deepr.mcp.protocol_compat import HttpMessage
from deepr.mcp.transport.http_validation import (
    decode_header_value,
    origin_is_allowed,
    validate_streamable_http_request,
)


def _modern_message(method="tools/list", params=None, message_id="1"):
    body_params = {
        "_meta": {
            pm.META_PROTOCOL_VERSION: pm.MODERN_PROTOCOL_VERSION,
            pm.META_CLIENT_CAPABILITIES: {},
        }
    }
    body_params.update(params or {})
    return HttpMessage(id=message_id, method=method, params=body_params)


def _modern_headers(method="tools/list", name=None):
    headers = {
        "MCP-Protocol-Version": pm.MODERN_PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


class TestLegacyRequests:
    def test_no_headers_no_meta_is_legacy(self):
        message = HttpMessage(id="1", method="tools/list", params={})
        validation = validate_streamable_http_request({}, message)
        assert validation.modern is False

    def test_legacy_version_header_is_tolerated(self):
        message = HttpMessage(id="1", method="tools/list", params={})
        validation = validate_streamable_http_request(
            {"MCP-Protocol-Version": "2025-06-18"}, message
        )
        assert validation.modern is False

    def test_modern_header_without_body_meta_is_header_mismatch(self):
        message = HttpMessage(id="1", method="tools/list", params={})
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            validate_streamable_http_request(
                {"MCP-Protocol-Version": pm.MODERN_PROTOCOL_VERSION}, message
            )
        assert excinfo.value.code == pm.HEADER_MISMATCH_CODE

    def test_unknown_header_version_is_unsupported(self):
        message = HttpMessage(id="1", method="tools/list", params={})
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            validate_streamable_http_request({"MCP-Protocol-Version": "2030-01-01"}, message)
        assert excinfo.value.code == pm.UNSUPPORTED_PROTOCOL_VERSION_CODE


class TestModernHeaders:
    def test_valid_request_passes(self):
        validation = validate_streamable_http_request(_modern_headers(), _modern_message())
        assert validation.modern is True
        assert validation.protocol_version == pm.MODERN_PROTOCOL_VERSION

    def test_missing_protocol_version_header(self):
        headers = _modern_headers()
        del headers["MCP-Protocol-Version"]
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            validate_streamable_http_request(headers, _modern_message())
        assert excinfo.value.code == pm.HEADER_MISMATCH_CODE

    def test_version_header_body_mismatch(self):
        headers = _modern_headers()
        headers["MCP-Protocol-Version"] = "2025-06-18"
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            validate_streamable_http_request(headers, _modern_message())
        assert excinfo.value.code == pm.HEADER_MISMATCH_CODE

    def test_missing_method_header(self):
        headers = {"MCP-Protocol-Version": pm.MODERN_PROTOCOL_VERSION}
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            validate_streamable_http_request(headers, _modern_message())
        assert excinfo.value.code == pm.HEADER_MISMATCH_CODE

    def test_method_header_mismatch(self):
        with pytest.raises(pm.JsonRpcProtocolError):
            validate_streamable_http_request(
                _modern_headers(method="prompts/list"), _modern_message(method="tools/list")
            )

    @pytest.mark.parametrize(
        ("method", "source", "value"),
        [
            ("tools/call", "name", "deepr_status"),
            ("resources/read", "uri", "deepr://campaigns/x/status"),
            ("prompts/get", "name", "research-workflow"),
        ],
    )
    def test_name_header_required_and_matched(self, method, source, value):
        message = _modern_message(method=method, params={source: value})
        validation = validate_streamable_http_request(
            _modern_headers(method=method, name=value), message
        )
        assert validation.modern is True

        with pytest.raises(pm.JsonRpcProtocolError):
            validate_streamable_http_request(_modern_headers(method=method), message)

        with pytest.raises(pm.JsonRpcProtocolError):
            validate_streamable_http_request(
                _modern_headers(method=method, name="other"), message
            )

    def test_name_header_base64_sentinel_decoded_before_compare(self):
        tool = "outil_météo"
        encoded = "=?base64?" + base64.b64encode(tool.encode("utf-8")).decode("ascii") + "?="
        message = _modern_message(method="tools/call", params={"name": tool})
        validation = validate_streamable_http_request(
            _modern_headers(method="tools/call", name=encoded), message
        )
        assert validation.modern is True

    def test_notifications_skip_header_enforcement(self):
        message = _modern_message(message_id=None)
        message.id = None
        validation = validate_streamable_http_request({}, message)
        assert validation.modern is True


class TestSentinelDecoding:
    def test_plain_value_passes_through(self):
        assert decode_header_value("deepr_status") == "deepr_status"

    def test_sentinel_decodes_utf8(self):
        encoded = "=?base64?" + base64.b64encode("Hello, 世界".encode()).decode("ascii") + "?="
        assert decode_header_value(encoded) == "Hello, 世界"

    def test_malformed_sentinel_is_header_mismatch(self):
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            decode_header_value("=?base64?!!!not-base64!!!?=")
        assert excinfo.value.code == pm.HEADER_MISMATCH_CODE


class TestOrigin:
    @pytest.mark.parametrize(
        "origin",
        [None, "http://localhost:3000", "http://127.0.0.1:8765", "https://[::1]:9000"],
    )
    def test_loopback_and_absent_origins_allowed(self, origin):
        assert origin_is_allowed(origin) is True

    @pytest.mark.parametrize(
        "origin",
        ["https://evil.example.com", "null", "file://x", "javascript:alert(1)", "http://192.168.1.5"],
    )
    def test_non_loopback_origins_rejected(self, origin):
        assert origin_is_allowed(origin) is False

    def test_allowlist_extends_policy(self):
        assert origin_is_allowed(
            "https://dashboard.example.com",
            extra_allowed=frozenset({"https://dashboard.example.com"}),
        )
