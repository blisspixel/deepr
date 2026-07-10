"""Tests for provider-controlled status normalization."""

import pytest

from deepr.services.provider_status import (
    classify_provider_status,
    provider_exception_name,
    terminal_provider_error,
)


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        ("cancelled", "Provider reported research cancellation"),
        ("expired", "Provider research request expired"),
        ("failed", "Provider reported research failure"),
        ("incomplete", "Provider returned an incomplete research result"),
    ],
)
def test_terminal_statuses_have_fixed_content_free_errors(status: str, expected_error: str) -> None:
    normalized = classify_provider_status(status)

    assert terminal_provider_error(normalized) == expected_error
    assert "\n" not in expected_error


@pytest.mark.parametrize("status", ["completed", "in_progress", "queued", "unknown\nforged"])
def test_non_failure_statuses_have_no_error(status: str) -> None:
    assert terminal_provider_error(classify_provider_status(status)) is None


def test_unknown_status_is_bounded_but_remains_nonterminal() -> None:
    normalized = classify_provider_status("new_provider_state\nforged")

    assert normalized == "unsupported"
    assert terminal_provider_error(normalized) is None


def test_provider_exception_name_omits_exception_content() -> None:
    error = RuntimeError("secret\nforged")

    assert provider_exception_name(error) == "RuntimeError"
    assert "secret" not in provider_exception_name(error)
