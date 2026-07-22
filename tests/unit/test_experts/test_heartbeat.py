"""Tests for the off-box scheduled-maintenance heartbeat."""

from __future__ import annotations

import logging

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
        monkeypatch.setattr(
            hb.requests,
            "get",
            lambda url, timeout, allow_redirects: (
                seen.update(
                    url=url,
                    timeout=timeout,
                    allow_redirects=allow_redirects,
                )
                or _Resp(200)
            ),
        )
        assert hb.send_heartbeat(url="https://hc.example/abc") is True
        assert seen["url"] == "https://hc.example/abc"
        assert seen["allow_redirects"] is False

    def test_failure_pings_fail_endpoint(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            hb.requests,
            "get",
            lambda url, timeout, allow_redirects: seen.update(url=url, allow_redirects=allow_redirects) or _Resp(200),
        )
        hb.send_heartbeat(success=False, url="https://hc.example/abc/")
        assert seen["url"] == "https://hc.example/abc/fail"
        assert seen["allow_redirects"] is False

    def test_non_2xx_returns_false(self, monkeypatch):
        monkeypatch.setattr(hb.requests, "get", lambda url, timeout, allow_redirects: _Resp(500))
        assert hb.send_heartbeat(url="https://hc.example/abc") is False

    def test_network_error_is_swallowed(self, monkeypatch):
        def boom(url, timeout, allow_redirects):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(hb.requests, "get", boom)
        # Best-effort: never raises, returns False.
        assert hb.send_heartbeat(url="https://hc.example/abc") is False

    def test_redirect_response_is_not_followed(self, monkeypatch):
        seen = {}

        def redirect(url, timeout, allow_redirects):
            seen.update(url=url, allow_redirects=allow_redirects)
            return _Resp(302)

        monkeypatch.setattr(hb.requests, "get", redirect)

        assert hb.send_heartbeat(url="https://hc.example/redirect") is False
        assert seen == {"url": "https://hc.example/redirect", "allow_redirects": False}

    def test_failure_logs_do_not_disclose_url_or_exception(self, monkeypatch, caplog):
        secret_url = "https://hc.example/check/secret-token"

        def boom(url, timeout, allow_redirects):
            raise requests.ConnectionError("private resolver detail")

        monkeypatch.setattr(hb.requests, "get", boom)
        with caplog.at_level(logging.DEBUG, logger="deepr.experts.heartbeat"):
            assert hb.send_heartbeat(url=secret_url) is False

        logs = caplog.text
        assert "secret-token" not in logs
        assert secret_url not in logs
        assert "private resolver detail" not in logs
        assert "heartbeat request failed" in logs

    def test_non_2xx_logs_only_status(self, monkeypatch, caplog):
        secret_url = "https://hc.example/check/secret-token"
        monkeypatch.setattr(hb.requests, "get", lambda url, timeout, allow_redirects: _Resp(503))

        with caplog.at_level(logging.DEBUG, logger="deepr.experts.heartbeat"):
            assert hb.send_heartbeat(url=secret_url) is False

        logs = caplog.text
        assert "secret-token" not in logs
        assert secret_url not in logs
        assert "HTTP 503" in logs
