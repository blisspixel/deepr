"""Shared explicit compatibility setup for dashboard unit tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def allow_unauthenticated_loopback_for_unit_tests(monkeypatch: pytest.MonkeyPatch):
    """Keep endpoint-focused tests explicit about bypassing production auth."""
    from deepr.web import app as web_app

    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", True)
