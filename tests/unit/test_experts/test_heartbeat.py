"""Tests for the off-box scheduled-maintenance heartbeat."""

from __future__ import annotations

import logging

import pytest
import requests

from deepr.experts import heartbeat as hb


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.closed = False

    def close(self) -> None:
        self.closed = True


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

    def test_valid_endpoint_is_normalized_without_changing_query(self):
        assert hb.validate_heartbeat_url("  https://hc.example/abc?rid=123  ") == ("https://hc.example/abc?rid=123")

    @pytest.mark.parametrize(
        "url",
        [
            "http://hc.example/abc",
            "file:///tmp/ping",
            "https://user:password@hc.example/abc",
            "https://hc.example/abc#fragment",
            "https://hc.example/line\nbreak",
            "https://hc.example:invalid/abc",
            "https://",
            "https://hc.example/" + "x" * 2048,
        ],
    )
    def test_unsafe_or_ambiguous_endpoint_is_rejected(self, url):
        with pytest.raises(hb.HeartbeatConfigurationError):
            hb.validate_heartbeat_url(url)


class TestSendHeartbeat:
    def test_no_url_is_a_noop(self, monkeypatch):
        monkeypatch.delenv(hb.HEARTBEAT_ENV, raising=False)
        called = []
        monkeypatch.setattr(hb, "pinned_get", lambda *a, **k: called.append(a) or _Resp(200))
        assert hb.send_heartbeat() is False
        assert called == []  # never touches the network without a URL

    def test_success_pings_base_url(self, monkeypatch):
        seen = {}
        response = _Resp(200)
        monkeypatch.setattr(
            hb,
            "pinned_get",
            lambda url, timeout, allow_redirects, stream, address_failover, redact_request_target: (
                seen.update(
                    url=url,
                    timeout=timeout,
                    allow_redirects=allow_redirects,
                    stream=stream,
                    address_failover=address_failover,
                    redact_request_target=redact_request_target,
                )
                or response
            ),
        )
        assert hb.send_heartbeat(url="https://hc.example/abc") is True
        assert seen["url"] == "https://hc.example/abc"
        assert seen["allow_redirects"] is False
        assert seen["stream"] is True
        assert seen["address_failover"] is False
        assert seen["redact_request_target"] is True
        assert response.closed is True

    def test_failure_pings_fail_endpoint(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            hb,
            "pinned_get",
            lambda url, timeout, allow_redirects, stream, address_failover, redact_request_target: (
                seen.update(
                    url=url,
                    allow_redirects=allow_redirects,
                    stream=stream,
                    address_failover=address_failover,
                    redact_request_target=redact_request_target,
                )
                or _Resp(200)
            ),
        )
        hb.send_heartbeat(success=False, url="https://hc.example/abc/")
        assert seen["url"] == "https://hc.example/abc/fail"
        assert seen["allow_redirects"] is False

    def test_failure_path_preserves_query_parameters(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            hb,
            "pinned_get",
            lambda url, **kwargs: seen.update(url=url, **kwargs) or _Resp(200),
        )

        result = hb.deliver_heartbeat(
            success=False,
            url="https://hc.example/abc?create=1&rid=123",
        )

        assert result.delivered is True
        assert seen["url"] == "https://hc.example/abc/fail?create=1&rid=123"

    def test_non_2xx_returns_false(self, monkeypatch):
        monkeypatch.setattr(
            hb,
            "pinned_get",
            lambda url, timeout, allow_redirects, stream, address_failover, redact_request_target: _Resp(500),
        )
        assert hb.send_heartbeat(url="https://hc.example/abc") is False

    def test_non_2xx_returns_typed_failure_and_closes_response(self, monkeypatch):
        response = _Resp(503)
        monkeypatch.setattr(hb, "pinned_get", lambda *args, **kwargs: response)

        result = hb.deliver_heartbeat(url="https://hc.example/abc")

        assert result == hb.HeartbeatDelivery(
            attempted=True,
            delivered=False,
            failure_kind="http_error",
            http_status=503,
        )
        assert response.closed is True

    def test_network_error_is_swallowed(self, monkeypatch):
        def boom(url, timeout, allow_redirects, stream, address_failover, redact_request_target):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(hb, "pinned_get", boom)
        # Best-effort: never raises, returns False.
        assert hb.send_heartbeat(url="https://hc.example/abc") is False

    def test_network_error_returns_typed_failure(self, monkeypatch):
        monkeypatch.setattr(
            hb,
            "pinned_get",
            lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError("down")),
        )

        assert hb.deliver_heartbeat(url="https://hc.example/abc") == hb.HeartbeatDelivery(
            attempted=True,
            delivered=False,
            failure_kind="network_error",
        )

    def test_cleartext_endpoint_is_rejected_without_request(self, monkeypatch):
        called = []
        monkeypatch.setattr(hb, "pinned_get", lambda *args, **kwargs: called.append(args) or _Resp(200))

        result = hb.deliver_heartbeat(url="http://hc.example/secret")

        assert result == hb.HeartbeatDelivery(
            attempted=False,
            delivered=False,
            failure_kind="invalid_configuration",
        )
        assert called == []

    @pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf")])
    def test_non_positive_or_non_finite_timeout_is_rejected_without_request(self, monkeypatch, timeout):
        called = []
        monkeypatch.setattr(hb, "pinned_get", lambda *args, **kwargs: called.append(args) or _Resp(200))

        result = hb.deliver_heartbeat(url="https://hc.example/secret", timeout=timeout)

        assert result == hb.HeartbeatDelivery(
            attempted=False,
            delivered=False,
            failure_kind="invalid_configuration",
        )
        assert called == []

    def test_private_or_unresolved_target_is_blocked_without_request(self, monkeypatch, caplog):
        called = []
        secret_url = "https://internal.example/secret-token"

        def block_target(url, **kwargs):
            called.append((url, kwargs))
            raise hb.SSRFError("must not disclose URL")

        monkeypatch.setattr(hb, "pinned_get", block_target)

        with caplog.at_level(logging.DEBUG, logger="deepr.experts.heartbeat"):
            result = hb.deliver_heartbeat(url=secret_url)

        assert result == hb.HeartbeatDelivery(
            attempted=False,
            delivered=False,
            failure_kind="unsafe_target",
        )
        assert len(called) == 1
        assert secret_url not in caplog.text
        assert "secret-token" not in caplog.text
        assert "public-address safety checks" in caplog.text

    def test_redirect_response_is_not_followed(self, monkeypatch):
        seen = {}

        def redirect(url, timeout, allow_redirects, stream, address_failover, redact_request_target):
            seen.update(
                url=url,
                allow_redirects=allow_redirects,
                stream=stream,
                address_failover=address_failover,
                redact_request_target=redact_request_target,
            )
            return _Resp(302)

        monkeypatch.setattr(hb, "pinned_get", redirect)

        assert hb.send_heartbeat(url="https://hc.example/redirect") is False
        assert seen == {
            "url": "https://hc.example/redirect",
            "allow_redirects": False,
            "stream": True,
            "address_failover": False,
            "redact_request_target": True,
        }

    def test_failure_logs_do_not_disclose_url_or_exception(self, monkeypatch, caplog):
        secret_url = "https://hc.example/check/secret-token"

        def boom(url, timeout, allow_redirects, stream, address_failover, redact_request_target):
            raise requests.ConnectionError("private resolver detail")

        monkeypatch.setattr(hb, "pinned_get", boom)
        with caplog.at_level(logging.DEBUG, logger="deepr.experts.heartbeat"):
            assert hb.send_heartbeat(url=secret_url) is False

        logs = caplog.text
        assert "secret-token" not in logs
        assert secret_url not in logs
        assert "private resolver detail" not in logs
        assert "heartbeat request failed" in logs

    def test_non_2xx_logs_only_status(self, monkeypatch, caplog):
        secret_url = "https://hc.example/check/secret-token"
        monkeypatch.setattr(
            hb,
            "pinned_get",
            lambda url, timeout, allow_redirects, stream, address_failover, redact_request_target: _Resp(503),
        )

        with caplog.at_level(logging.DEBUG, logger="deepr.experts.heartbeat"):
            assert hb.send_heartbeat(url=secret_url) is False

        logs = caplog.text
        assert "secret-token" not in logs
        assert secret_url not in logs
        assert "HTTP 503" in logs
