"""Tests for explicit grounding-checker CLI support."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.cli.commands.semantic.grounding_support import (
    absorber_kwargs,
    build_grounding_checker,
    validate_grounding_flags,
)


class _FakeClient:
    def __init__(self) -> None:
        self.calls = []

        async def _create(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="SUPPORTED\nDirect."))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


def test_validate_grounding_flags_rejects_checker_plan_without_enable():
    with pytest.raises(ValueError, match="--check-grounding"):
        validate_grounding_flags(check_grounding=False, checker_plan="codex", checker_plan_model=None)


def test_absorber_kwargs_omits_optional_values():
    assert absorber_kwargs(model="m") == {"model": "m"}


async def test_default_grounding_checker_uses_same_vendor_fresh_context():
    client = _FakeClient()
    checker = build_grounding_checker(
        enabled=True,
        checker_plan=None,
        checker_plan_model=None,
        maker_vendor="local",
        default_client=client,
        default_vendor="local",
        default_model="qwen-local",
    )

    assert checker is not None
    verdict = await checker("claim", "evidence")

    assert verdict.supported is True
    assert verdict.assurance.value == "same_vendor_fresh_context"
    assert client.calls[0]["model"] == "qwen-local"


def test_grounding_checker_requires_default_or_plan():
    with pytest.raises(ValueError, match="--local, --plan, or --checker-plan"):
        build_grounding_checker(
            enabled=True,
            checker_plan=None,
            checker_plan_model=None,
            maker_vendor="api_metered",
        )
