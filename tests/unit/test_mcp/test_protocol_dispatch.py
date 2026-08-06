"""Tests for era-aware dispatch: server/discover, modern envelopes, and the
removal of legacy-only methods from the modern surface."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.mcp import protocol_modern as pm
from deepr.mcp.protocol_dispatch import dispatch_protocol_method, registered_method_names


def _modern_params(**extra):
    return {
        "_meta": {
            pm.META_PROTOCOL_VERSION: pm.MODERN_PROTOCOL_VERSION,
            pm.META_CLIENT_CAPABILITIES: {},
        },
        **extra,
    }


class TestRegisteredMethods:
    def test_covers_core_and_legacy_aliases(self):
        names = registered_method_names()
        assert "initialize" in names
        assert "server/discover" in names
        assert "tools/call" in names
        assert "query_expert" in names  # legacy alias


class TestServerDiscover:
    @pytest.mark.asyncio
    async def test_discover_is_served_and_stamped(self):
        result = await dispatch_protocol_method(MagicMock(), "server/discover", _modern_params())
        assert result["resultType"] == "complete"
        assert result["supportedVersions"][0] == pm.MODERN_PROTOCOL_VERSION
        assert result["cacheScope"] == "public"
        assert result["_meta"][pm.META_SERVER_INFO]["name"] == "deepr-research"

    @pytest.mark.asyncio
    async def test_discover_works_for_legacy_probe_without_meta(self):
        # A dual-era stdio client may probe server/discover before deciding
        # its era; the probe must not require modern _meta to succeed.
        result = await dispatch_protocol_method(MagicMock(), "server/discover", {})
        assert result["supportedVersions"][0] == pm.MODERN_PROTOCOL_VERSION
        assert "resultType" not in result  # legacy-shaped response, no stamp


class TestModernSurface:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["initialize", "resources/subscribe", "resources/unsubscribe"])
    async def test_legacy_only_methods_are_gone_in_modern_era(self, method):
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            await dispatch_protocol_method(MagicMock(), method, _modern_params())
        assert excinfo.value.code == pm.METHOD_NOT_FOUND_CODE
        assert excinfo.value.http_status == 404

    @pytest.mark.asyncio
    async def test_unknown_method_status_depends_on_era(self):
        with pytest.raises(pm.JsonRpcProtocolError) as modern_exc:
            await dispatch_protocol_method(MagicMock(), "nope", _modern_params())
        assert modern_exc.value.http_status == 404

        with pytest.raises(pm.JsonRpcProtocolError) as legacy_exc:
            await dispatch_protocol_method(MagicMock(), "nope", {})
        assert legacy_exc.value.http_status == 200

    @pytest.mark.asyncio
    async def test_unsupported_version_rejected_before_method_lookup(self):
        params = {"_meta": {pm.META_PROTOCOL_VERSION: "2030-01-01"}}
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            await dispatch_protocol_method(MagicMock(), "tools/list", params)
        assert excinfo.value.code == pm.UNSUPPORTED_PROTOCOL_VERSION_CODE

    @pytest.mark.asyncio
    async def test_modern_tools_list_is_stamped(self):
        with patch(
            "deepr.mcp.server._handle_tools_list",
            new=AsyncMock(return_value={"tools": []}),
        ):
            result = await dispatch_protocol_method(MagicMock(), "tools/list", _modern_params())
        assert result["resultType"] == "complete"
        assert result["ttlMs"] > 0
        assert result["cacheScope"] == "public"

    @pytest.mark.asyncio
    async def test_legacy_tools_list_is_not_stamped(self):
        with patch(
            "deepr.mcp.server._handle_tools_list",
            new=AsyncMock(return_value={"tools": []}),
        ):
            result = await dispatch_protocol_method(MagicMock(), "tools/list", {})
        assert result == {"tools": []}


class TestModernResourcesRead:
    @pytest.mark.asyncio
    async def test_read_failure_is_invalid_params_error(self):
        server = MagicMock()
        server.resource_handler.read_resource.return_value = MagicMock(success=False)
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            await dispatch_protocol_method(server, "resources/read", _modern_params(uri="deepr://campaigns/x/status"))
        # -32602 replaces the retired -32002 resource-not-found code.
        assert excinfo.value.code == pm.INVALID_PARAMS_CODE
        assert excinfo.value.data == {"uri": "deepr://campaigns/x/status"}

    @pytest.mark.asyncio
    async def test_read_success_returns_contents_with_envelope(self):
        server = MagicMock()
        server.resource_handler.read_resource.return_value = MagicMock(success=True, data={"ok": 1})
        result = await dispatch_protocol_method(
            server, "resources/read", _modern_params(uri="deepr://campaigns/x/status")
        )
        assert result["contents"][0]["uri"] == "deepr://campaigns/x/status"
        assert result["resultType"] == "complete"
        assert result["cacheScope"] == "private"


class TestLegacyAliases:
    @pytest.mark.asyncio
    async def test_alias_strips_meta_from_arguments(self):
        server = MagicMock()
        with patch(
            "deepr.mcp.server._handle_tools_call",
            new=AsyncMock(return_value={"content": []}),
        ) as tools_call:
            await dispatch_protocol_method(server, "query_expert", _modern_params(expert_name="a"))
        tools_call.assert_awaited_once_with(
            server,
            {"name": "deepr_query_expert", "arguments": {"expert_name": "a"}},
        )
