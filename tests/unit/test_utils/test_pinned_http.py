"""Tests for the shared peer-bound HTTP transport."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
import requests
from requests import Request

from deepr.utils import pinned_http


def test_https_adapter_connects_to_authorized_ip_with_original_tls_name():
    adapter = pinned_http.PinnedAddressAdapter(
        address="93.184.216.34",
        hostname="example.com",
        port=443,
        scheme="https",
    )
    request = Request("GET", "https://example.com/path").prepare()

    pool = adapter.get_connection_with_tls_context(request, True)

    assert pool.host == "93.184.216.34"
    assert pool.port == 443
    assert pool.assert_hostname == "example.com"
    assert pool.conn_kw["server_hostname"] == "example.com"

    legacy_pool = adapter.get_connection("https://example.com/path")

    assert legacy_pool.host == "93.184.216.34"
    assert legacy_pool.port == 443
    assert legacy_pool.assert_hostname == "example.com"
    assert legacy_pool.conn_kw["server_hostname"] == "example.com"


def test_pinned_get_disables_environment_proxies_and_owns_session(monkeypatch):
    sessions = []

    class FakeSession:
        def __init__(self):
            self.trust_env = True
            self.mounts = []
            self.closed = False
            sessions.append(self)

        def mount(self, prefix, adapter):
            self.mounts.append((prefix, adapter))

        def get(self, url, headers, **kwargs):
            assert url == "https://example.com/check?rid=123"
            assert headers == {"Host": "example.com"}
            assert kwargs == {"timeout": 5.0, "allow_redirects": False, "stream": True}
            return SimpleNamespace(close=lambda: None)

        def close(self):
            self.closed = True

    monkeypatch.setattr(pinned_http, "resolve_safe_url_ips", lambda url, allow_private: ("93.184.216.34",))
    monkeypatch.setattr(pinned_http.requests, "Session", FakeSession)

    response = pinned_http.pinned_get(
        "https://example.com/check?rid=123",
        timeout=5.0,
        allow_redirects=False,
        stream=True,
    )

    assert len(sessions) == 1
    assert sessions[0].trust_env is False
    assert sessions[0].mounts[0][0] == "https://"
    assert sessions[0].mounts[0][1]._address == "93.184.216.34"
    pinned_http.close_pinned_response(response)
    assert sessions[0].closed is True


def test_pinned_get_retries_only_prevalidated_addresses(monkeypatch):
    attempted = []

    class FakeSession:
        trust_env = True

        def mount(self, prefix, adapter):
            self.adapter = adapter

        def get(self, url, headers, **kwargs):
            assert kwargs["allow_redirects"] is False
            attempted.append(self.adapter._address)
            if len(attempted) == 1:
                raise requests.ConnectionError("first address failed")
            return SimpleNamespace(close=lambda: None)

        def close(self):
            return None

    monkeypatch.setattr(
        pinned_http,
        "resolve_safe_url_ips",
        lambda url, allow_private: ("93.184.216.34", "93.184.216.35"),
    )
    monkeypatch.setattr(pinned_http.requests, "Session", FakeSession)

    response = pinned_http.pinned_get("https://example.com/check", allow_redirects=False)

    assert attempted == ["93.184.216.34", "93.184.216.35"]
    pinned_http.close_pinned_response(response)


def test_pinned_get_can_disable_address_failover(monkeypatch):
    attempted = []

    class FakeSession:
        trust_env = True

        def mount(self, prefix, adapter):
            self.adapter = adapter

        def get(self, url, headers, **kwargs):
            attempted.append(self.adapter._address)
            raise requests.ConnectionError("first address failed")

        def close(self):
            return None

    monkeypatch.setattr(
        pinned_http,
        "resolve_safe_url_ips",
        lambda url, allow_private: ("93.184.216.34", "93.184.216.35"),
    )
    monkeypatch.setattr(pinned_http.requests, "Session", FakeSession)

    with pytest.raises(requests.ConnectionError, match="first address failed"):
        pinned_http.pinned_get(
            "https://example.com/check",
            allow_redirects=False,
            address_failover=False,
        )

    assert attempted == ["93.184.216.34"]


def test_pinned_get_closes_session_on_unexpected_error(monkeypatch):
    sessions = []

    class FakeSession:
        trust_env = True

        def __init__(self):
            self.closed = False
            sessions.append(self)

        def mount(self, prefix, adapter):
            return None

        def get(self, url, headers, **kwargs):
            raise RuntimeError("unexpected failure")

        def close(self):
            self.closed = True

    monkeypatch.setattr(pinned_http, "resolve_safe_url_ips", lambda url, allow_private: ("93.184.216.34",))
    monkeypatch.setattr(pinned_http.requests, "Session", FakeSession)

    with pytest.raises(RuntimeError, match="unexpected failure"):
        pinned_http.pinned_get("https://example.com/check", allow_redirects=False)

    assert sessions[0].closed is True


def test_close_pinned_response_closes_owner_when_response_close_fails():
    owner = SimpleNamespace(closed=False, close=lambda: setattr(owner, "closed", True))

    def fail_close():
        raise requests.ConnectionError("close failed")

    response = SimpleNamespace(
        close=fail_close,
        _deepr_transport_owner=owner,
    )

    with pytest.raises(requests.ConnectionError, match="close failed"):
        pinned_http.close_pinned_response(response)

    assert owner.closed is True


def test_pinned_get_redacts_dependency_request_target_for_marked_request(monkeypatch, caplog):
    secret_target = "/check/secret-token?rid=private"

    class FakeSession:
        trust_env = True

        def mount(self, prefix, adapter):
            return None

        def get(self, url, headers, **kwargs):
            logging.getLogger("urllib3.connectionpool").debug(
                '%s://%s:%s "%s %s %s" %s %s',
                "https",
                "93.184.216.34",
                443,
                "GET",
                secret_target,
                "HTTP/1.1",
                200,
                0,
            )
            return SimpleNamespace(close=lambda: None)

        def close(self):
            return None

    monkeypatch.setattr(pinned_http, "resolve_safe_url_ips", lambda url, allow_private: ("93.184.216.34",))
    monkeypatch.setattr(pinned_http.requests, "Session", FakeSession)

    with caplog.at_level(logging.DEBUG, logger="urllib3.connectionpool"):
        response = pinned_http.pinned_get(
            f"https://example.com{secret_target}",
            allow_redirects=False,
            redact_request_target=True,
        )
        logging.getLogger("urllib3.connectionpool").debug("outside request is visible")

    pinned_http.close_pinned_response(response)
    assert secret_target not in caplog.text
    assert "sensitive target omitted" in caplog.text
    assert "outside request is visible" in caplog.text


def test_pinned_get_refuses_redirect_following_before_resolution(monkeypatch):
    monkeypatch.setattr(
        pinned_http,
        "resolve_safe_url_ips",
        lambda *args, **kwargs: pytest.fail("resolution must not run"),
    )

    with pytest.raises(ValueError, match="caller-managed redirects"):
        pinned_http.pinned_get("https://example.com/check", allow_redirects=True)


def test_pinned_head_uses_request_method_and_owns_session(monkeypatch):
    sessions = []

    class FakeSession:
        def __init__(self):
            self.trust_env = True
            self.methods = []
            sessions.append(self)

        def mount(self, prefix, adapter):
            self.adapter = adapter

        def request(self, method, url, headers, **kwargs):
            self.methods.append(method)
            assert method == "HEAD"
            assert url == "https://example.com/check"
            assert headers == {"Host": "example.com"}
            assert kwargs["allow_redirects"] is False
            return SimpleNamespace(close=lambda: None, is_redirect=False, url=url, headers={})

        def close(self):
            self.closed = True

    monkeypatch.setattr(pinned_http, "resolve_safe_url_ips", lambda url, allow_private: ("93.184.216.34",))
    monkeypatch.setattr(pinned_http.requests, "Session", FakeSession)

    response = pinned_http.pinned_head("https://example.com/check", allow_redirects=False)
    pinned_http.close_pinned_response(response)

    assert sessions[0].methods == ["HEAD"]
    assert sessions[0].closed is True
