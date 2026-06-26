"""Regression test: MCP HTTP transport must catch the ``TypeError`` that
``hmac.compare_digest`` raises on non-ASCII string inputs and return 401
instead of letting it escape into a generic 500.

Same fix as web/app.py + api/app.py - applied to the MCP surface in
the bug-hunt pass.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def transport():
    from deepr.mcp.transport.http import HttpTransport

    t = HttpTransport(auth_token="valid-token")
    return t


def _make_request_with_authorization(value: str):
    """Build a minimal request-like object whose .headers behaves like
    aiohttp's CIMultiDict."""
    request = MagicMock()
    headers = {"Authorization": f"Bearer {value}"}
    request.headers.get = lambda k, default=None: headers.get(k, default)
    return request


class TestBearerTypeErrorCatch:
    @pytest.mark.asyncio
    async def test_non_ascii_token_returns_unauthorized_not_500(self, transport):
        """A token containing non-ASCII chars triggers TypeError in
        ``hmac.compare_digest``. The transport should catch it and
        return a 401 response, not a 500."""
        request = _make_request_with_authorization("token-with-非ascii")
        result = transport._check_auth(request)
        assert result is not None  # An unauthorized response was returned
        assert result.status == 401

    @pytest.mark.asyncio
    async def test_valid_token_passes(self, transport):
        request = _make_request_with_authorization("valid-token")
        result = transport._check_auth(request)
        assert result is None  # None means auth passed

    @pytest.mark.asyncio
    async def test_invalid_ascii_token_returns_unauthorized(self, transport):
        request = _make_request_with_authorization("wrong-but-ascii-token")
        result = transport._check_auth(request)
        assert result is not None
        assert result.status == 401

    @pytest.mark.asyncio
    async def test_no_auth_token_configured_allows_all(self):
        from deepr.mcp.transport.http import HttpTransport

        t = HttpTransport(auth_token=None)
        request = _make_request_with_authorization("anything")
        # No token configured = no auth check
        assert t._check_auth(request) is None
