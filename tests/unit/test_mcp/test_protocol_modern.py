"""Tests for the 2026-07-28 protocol facts: context extraction, negotiation,
and the modern result envelope."""

import pytest

from deepr.mcp import protocol_modern as pm


def _modern_meta(**overrides):
    meta = {
        pm.META_PROTOCOL_VERSION: pm.MODERN_PROTOCOL_VERSION,
        pm.META_CLIENT_CAPABILITIES: {},
    }
    meta.update(overrides)
    return meta


class TestModernRequestContext:
    def test_legacy_request_without_meta_returns_none(self):
        assert pm.modern_request_context({}) is None
        assert pm.modern_request_context(None) is None
        assert pm.modern_request_context({"_meta": {"progressToken": "t"}}) is None

    def test_modern_request_extracts_context(self):
        params = {
            "_meta": _modern_meta(
                **{
                    pm.META_CLIENT_INFO: {"name": "c", "version": "1"},
                    pm.META_LOG_LEVEL: "warning",
                }
            )
        }
        context = pm.modern_request_context(params)
        assert context is not None
        assert context.protocol_version == pm.MODERN_PROTOCOL_VERSION
        assert context.client_capabilities == {}
        assert context.client_info == {"name": "c", "version": "1"}
        assert context.log_level == "warning"

    def test_unsupported_version_raises_32022_with_spec_data(self):
        params = {"_meta": {pm.META_PROTOCOL_VERSION: "1900-01-01"}}
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            pm.modern_request_context(params)
        error = excinfo.value
        assert error.code == pm.UNSUPPORTED_PROTOCOL_VERSION_CODE
        assert error.http_status == 400
        assert error.data == {
            "supported": list(pm.SUPPORTED_PROTOCOL_VERSIONS),
            "requested": "1900-01-01",
        }

    def test_legacy_version_in_meta_is_rejected(self):
        # Pre-2026 revisions never defined per-request _meta versioning, so a
        # legacy version there is not something Deepr serves statelessly.
        params = {"_meta": {pm.META_PROTOCOL_VERSION: "2025-06-18"}}
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            pm.modern_request_context(params)
        assert excinfo.value.code == pm.UNSUPPORTED_PROTOCOL_VERSION_CODE

    def test_missing_client_capabilities_raises_invalid_params(self):
        params = {"_meta": {pm.META_PROTOCOL_VERSION: pm.MODERN_PROTOCOL_VERSION}}
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            pm.modern_request_context(params)
        assert excinfo.value.code == pm.INVALID_PARAMS_CODE
        assert excinfo.value.http_status == 400

    def test_malformed_optional_fields_are_dropped_not_fatal(self):
        params = {
            "_meta": _modern_meta(
                **{pm.META_CLIENT_INFO: "not-a-dict", pm.META_LOG_LEVEL: 3}
            )
        }
        context = pm.modern_request_context(params)
        assert context is not None
        assert context.client_info is None
        assert context.log_level is None


class TestLegacyNegotiation:
    @pytest.mark.parametrize("requested", pm.LEGACY_PROTOCOL_VERSIONS)
    def test_supported_legacy_versions_are_echoed(self, requested):
        assert pm.negotiate_legacy_initialize_version(requested) == requested

    @pytest.mark.parametrize("requested", [None, "2026-07-28", "2030-01-01", 7])
    def test_everything_else_gets_latest_legacy(self, requested):
        assert pm.negotiate_legacy_initialize_version(requested) == pm.LATEST_LEGACY_PROTOCOL_VERSION


class TestModernResultEnvelope:
    def test_result_type_and_server_info_stamped(self):
        result = pm.finalize_modern_result("tools/call", {"content": []})
        assert result["resultType"] == "complete"
        assert result["_meta"][pm.META_SERVER_INFO]["name"] == "deepr-research"
        assert "ttlMs" not in result  # tools/call is not cacheable

    def test_existing_meta_is_preserved(self):
        result = pm.finalize_modern_result("tools/call", {"_meta": {"x": 1}})
        assert result["_meta"]["x"] == 1
        assert pm.META_SERVER_INFO in result["_meta"]

    @pytest.mark.parametrize(
        ("method", "scope"),
        [
            ("server/discover", "public"),
            ("tools/list", "public"),
            ("prompts/list", "public"),
            ("resources/list", "private"),
            ("resources/read", "private"),
        ],
    )
    def test_cacheable_methods_carry_required_cache_fields(self, method, scope):
        result = pm.finalize_modern_result(method, {})
        assert isinstance(result["ttlMs"], int) and result["ttlMs"] > 0
        assert result["cacheScope"] == scope

    def test_original_result_is_not_mutated(self):
        original = {"content": []}
        pm.finalize_modern_result("tools/list", original)
        assert original == {"content": []}


class TestDiscoverResult:
    def test_shape(self):
        result = pm.discover_result()
        assert result["supportedVersions"][0] == pm.MODERN_PROTOCOL_VERSION
        assert set(pm.LEGACY_PROTOCOL_VERSIONS) <= set(result["supportedVersions"])
        assert "tools" in result["capabilities"]
        assert "logging" not in result["capabilities"]
        assert "deepr_tool_search" in result["instructions"]

    def test_capabilities_do_not_overclaim(self):
        capabilities = pm.server_capabilities()
        # No logging (unimplemented), no extensions (no Tasks claim).
        assert "logging" not in capabilities
        assert "extensions" not in capabilities
        assert capabilities["resources"]["subscribe"] is True


class TestErrors:
    def test_method_not_found_http_status_by_era(self):
        assert pm.method_not_found_error("x", modern=True).http_status == 404
        assert pm.method_not_found_error("x", modern=False).http_status == 200

    def test_to_error_omits_absent_data(self):
        error = pm.JsonRpcProtocolError(-32602, "bad")
        assert error.to_error() == {"code": -32602, "message": "bad"}
