"""Shared HTTP authentication policy tests."""

from deepr.security.http_auth import (
    SharedSecretDecision,
    check_shared_secret,
    env_flag,
    presented_http_secret,
)


def test_configured_secret_requires_exact_match() -> None:
    assert (
        check_shared_secret(
            configured_secret="expected",
            presented_secret="expected",
            allow_unauthenticated_loopback=False,
            remote_addr="127.0.0.1",
        )
        is SharedSecretDecision.ALLOW
    )
    assert (
        check_shared_secret(
            configured_secret="expected",
            presented_secret="wrong",
            allow_unauthenticated_loopback=True,
            remote_addr="127.0.0.1",
        )
        is SharedSecretDecision.UNAUTHORIZED
    )


def test_malformed_non_ascii_secret_fails_closed() -> None:
    decision = check_shared_secret(
        configured_secret="expected",
        presented_secret="caf\u00e9",
        allow_unauthenticated_loopback=True,
        remote_addr="127.0.0.1",
    )
    assert decision is SharedSecretDecision.UNAUTHORIZED


def test_missing_configuration_needs_explicit_loopback_opt_in() -> None:
    assert (
        check_shared_secret(
            configured_secret="",
            presented_secret="",
            allow_unauthenticated_loopback=False,
            remote_addr="127.0.0.1",
        )
        is SharedSecretDecision.NOT_CONFIGURED
    )
    assert (
        check_shared_secret(
            configured_secret="",
            presented_secret="",
            allow_unauthenticated_loopback=True,
            remote_addr="127.0.0.1",
        )
        is SharedSecretDecision.ALLOW
    )
    assert (
        check_shared_secret(
            configured_secret="",
            presented_secret="",
            allow_unauthenticated_loopback=True,
            remote_addr="192.0.2.10",
        )
        is SharedSecretDecision.NOT_CONFIGURED
    )


def test_http_secret_prefers_bearer_header() -> None:
    assert presented_http_secret("Bearer bearer", "header") == "bearer"
    assert presented_http_secret("Basic ignored", "header") == "header"


def test_env_flag_requires_explicit_truthy_value(monkeypatch) -> None:
    monkeypatch.setenv("DEEPR_TEST_FLAG", "yes")
    assert env_flag("DEEPR_TEST_FLAG") is True
    monkeypatch.setenv("DEEPR_TEST_FLAG", "enabled")
    assert env_flag("DEEPR_TEST_FLAG") is False
