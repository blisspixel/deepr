"""Tests for the off-box scheduled-maintenance heartbeat."""

from __future__ import annotations

import requests

from deepr.experts import heartbeat as hb


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code


class TestHeartbeatUrl:
    def test_none_when_unset(self, monkeypatch):
        monkeypatch.delenv(hb.HEARTBEAT_ENV, raising=False)
        assert hb.heartbeat_url() is None

    def test_blank_is_none(self, monkeypatch):
        monkeypatch.setenv(hb.HEARTBEAT_ENV, "   ")
        assert hb.heartbeat_url() is None

    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv(hb.HEARTBEAT_ENV, "https://hc.example/abc")
        assert hb.heartbeat_url() == "https://hc.example/abc"


class TestSendHeartbeat:
    def test_no_url_is_a_noop(self, monkeypatch):
        monkeypatch.delenv(hb.HEARTBEAT_ENV, raising=False)
        called = []
        monkeypatch.setattr(hb.requests, "get", lambda *a, **k: called.append(a) or _Resp(200))
        assert hb.send_heartbeat() is False
        assert called == []  # never touches the network without a URL

    def test_success_pings_base_url(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(hb.requests, "get", lambda url, timeout: seen.update(url=url, timeout=timeout) or _Resp(200))
        assert hb.send_heartbeat(url="https://hc.example/abc") is True
        assert seen["url"] == "https://hc.example/abc"

    def test_failure_pings_fail_endpoint(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(hb.requests, "get", lambda url, timeout: seen.update(url=url) or _Resp(200))
        hb.send_heartbeat(success=False, url="https://hc.example/abc/")
        assert seen["url"] == "https://hc.example/abc/fail"

    def test_non_2xx_returns_false(self, monkeypatch):
        monkeypatch.setattr(hb.requests, "get", lambda url, timeout: _Resp(500))
        assert hb.send_heartbeat(url="https://hc.example/abc") is False

    def test_network_error_is_swallowed(self, monkeypatch):
        def boom(url, timeout):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(hb.requests, "get", boom)
        # Best-effort: never raises, returns False.
        assert hb.send_heartbeat(url="https://hc.example/abc") is False
