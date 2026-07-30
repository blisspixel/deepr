"""Tests for quarantined off-box scheduled-maintenance heartbeat delivery."""

from __future__ import annotations

import pytest

from deepr.experts import heartbeat as hb


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
        assert hb.validate_heartbeat_url("  https://hc.example/abc?rid=123  ") == "https://hc.example/abc?rid=123"

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
        assert hb.deliver_heartbeat() == hb.HeartbeatDelivery(
            attempted=False,
            delivered=False,
            failure_kind="not_configured",
        )
        assert hb.send_heartbeat() is False

    def test_remote_service_is_blocked_before_dispatch(self):
        assert hb.REMOTE_HEARTBEAT_EXECUTION_ENABLED is False
        assert hb.deliver_heartbeat(url="https://hc.example/secret") == hb.HeartbeatDelivery(
            attempted=False,
            delivered=False,
            failure_kind="unmetered_external_service",
        )

    def test_failure_status_does_not_change_the_pre_dispatch_block(self):
        assert hb.deliver_heartbeat(success=False, url="https://hc.example/secret") == hb.HeartbeatDelivery(
            attempted=False,
            delivered=False,
            failure_kind="unmetered_external_service",
        )

    def test_invalid_endpoint_is_rejected_before_cost_classification(self):
        assert hb.deliver_heartbeat(url="http://hc.example/secret") == hb.HeartbeatDelivery(
            attempted=False,
            delivered=False,
            failure_kind="invalid_configuration",
        )

    @pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf")])
    def test_non_positive_or_non_finite_timeout_is_rejected(self, timeout):
        assert hb.deliver_heartbeat(url="https://hc.example/secret", timeout=timeout) == hb.HeartbeatDelivery(
            attempted=False,
            delivered=False,
            failure_kind="invalid_configuration",
        )
