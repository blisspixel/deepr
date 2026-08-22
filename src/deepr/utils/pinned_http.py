"""Peer-bound HTTP requests for security-sensitive outbound fetches."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool

from deepr.utils.security import SSRFError, resolve_safe_url_ips

_REDACT_REQUEST_TARGET = ContextVar("deepr_redact_pinned_request_target", default=False)


class _PinnedRequestLogFilter(logging.Filter):
    """Remove secret request targets from dependency logs for marked requests."""

    def filter(self, record: logging.LogRecord) -> bool:
        if _REDACT_REQUEST_TARGET.get():
            record.msg = "Pinned HTTP request event; sensitive target omitted"
            record.args = ()
        return True


logging.getLogger("urllib3.connectionpool").addFilter(_PinnedRequestLogFilter())


class PinnedAddressAdapter(HTTPAdapter):
    """Connect to one prevalidated IP while retaining the original TLS name."""

    def __init__(self, *, address: str, hostname: str, port: int, scheme: str) -> None:
        super().__init__(max_retries=0)
        self._address = address
        self._hostname = hostname
        self._port = port
        self._scheme = scheme

    def _connection_pool(self) -> HTTPConnectionPool:
        if self._scheme == "https":
            return HTTPSConnectionPool(
                self._address,
                self._port,
                assert_hostname=self._hostname,
                server_hostname=self._hostname,
                maxsize=1,
                block=True,
            )
        return HTTPConnectionPool(self._address, self._port, maxsize=1, block=True)

    def get_connection(self, url: str | bytes, proxies: Any = None) -> HTTPConnectionPool:
        """Pin connections for Requests versions before the TLS-context hook."""
        del url, proxies
        return self._connection_pool()

    def get_connection_with_tls_context(
        self,
        request: Any,
        verify: Any,
        proxies: Any = None,
        cert: Any = None,
    ) -> HTTPConnectionPool:
        del request, verify, proxies, cert
        return self._connection_pool()


def pinned_get(
    url: str,
    *,
    address_failover: bool = True,
    redact_request_target: bool = False,
    **kwargs: Any,
) -> requests.Response:
    """GET without redirects through prevalidated addresses and optional failover."""
    return _pinned_send(
        "GET",
        url,
        address_failover=address_failover,
        redact_request_target=redact_request_target,
        **kwargs,
    )


def pinned_head(
    url: str,
    *,
    address_failover: bool = True,
    redact_request_target: bool = False,
    **kwargs: Any,
) -> requests.Response:
    """HEAD without redirects through prevalidated addresses and optional failover."""
    return _pinned_send(
        "HEAD",
        url,
        address_failover=address_failover,
        redact_request_target=redact_request_target,
        **kwargs,
    )


def _pinned_send(
    method: str,
    url: str,
    *,
    address_failover: bool = True,
    redact_request_target: bool = False,
    **kwargs: Any,
) -> requests.Response:
    """Issue one method without redirects through prevalidated addresses."""
    if kwargs.get("allow_redirects", False):
        raise ValueError("pinned fetches require caller-managed redirects")
    kwargs["allow_redirects"] = False
    parsed = urlparse(url)
    addresses = resolve_safe_url_ips(url, allow_private=False)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    headers = dict(kwargs.pop("headers", {}) or {})
    headers["Host"] = parsed.netloc
    last_error: requests.RequestException | None = None
    attempted_addresses = addresses if address_failover else addresses[:1]
    verb = method.upper()
    for address in attempted_addresses:
        session = requests.Session()
        session.trust_env = False
        session.mount(
            f"{parsed.scheme}://",
            PinnedAddressAdapter(
                address=address,
                hostname=str(parsed.hostname),
                port=port,
                scheme=parsed.scheme,
            ),
        )
        redaction_token = _REDACT_REQUEST_TARGET.set(redact_request_target)
        try:
            if verb == "GET":
                response = session.get(url, headers=headers, **kwargs)
            else:
                response = session.request(verb, url, headers=headers, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
            session.close()
            continue
        except Exception:
            session.close()
            raise
        finally:
            _REDACT_REQUEST_TARGET.reset(redaction_token)
        response.__dict__["_deepr_transport_owner"] = session
        return response
    if last_error is not None:
        raise last_error
    raise SSRFError("URL did not resolve to a safe public address")


def close_pinned_response(response: requests.Response) -> None:
    """Close a pinned response and the session that owns its transport."""
    owner = getattr(response, "_deepr_transport_owner", None)
    try:
        response.close()
    finally:
        if owner is not None:
            owner.close()
