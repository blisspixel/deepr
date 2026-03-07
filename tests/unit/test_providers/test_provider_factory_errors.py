"""Tests for provider factory optional import error reporting."""

import pytest

import deepr.providers as providers


def test_create_provider_includes_optional_import_root_cause(monkeypatch):
    monkeypatch.setattr(providers, "GeminiProvider", None)
    monkeypatch.setitem(providers._OPTIONAL_PROVIDER_IMPORT_ERRORS, "gemini", RuntimeError("sdk mismatch"))

    with pytest.raises(ImportError) as excinfo:
        providers.create_provider("gemini")

    message = str(excinfo.value)
    assert "Gemini provider requires" in message
    assert "Root cause: sdk mismatch" in message
