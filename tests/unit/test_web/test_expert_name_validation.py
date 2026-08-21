"""Regression: expert-name validation must reject control whitespace.

The name flows into health-check recommended-action command strings. The old
validator used ``\\s``, which matches newlines and tabs, so a name like
``"Research\\necho injected"`` passed validation and could split a copied/agent
shell command. The validator now allows only a literal space.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("flask")

# Keep provider-backed submission out of this validation-only test module.
# (never called here). CI has none, so set a dummy before import.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")

import deepr.web.app as web_app
from deepr.experts.paths import expert_slug
from deepr.utils.security import InvalidInputError
from deepr.web.app import _decode_expert_name, _validate_expert_name


@pytest.mark.parametrize(
    "name",
    [
        "Research\necho injected",
        "Tech\tExpert",
        "AI\rExpert",
        "Name\x0bwith vtab",
        "Name\x0cwith ff",
    ],
)
def test_control_whitespace_rejected(name):
    assert _validate_expert_name(name) is not None


@pytest.mark.parametrize(
    "name",
    [
        "AI Strategy Expert",
        "Security Specialist",
        "Fabric Architect",
        "O'Brien's Data Team",
        "Team (Platform), 2026",
    ],
)
def test_legitimate_names_accepted(name):
    assert _validate_expert_name(name) is None


def test_path_traversal_still_rejected():
    assert _validate_expert_name("../etc/passwd") is not None
    assert _validate_expert_name("a/b") is not None
    assert _validate_expert_name("a\\b") is not None


def test_reserved_windows_device_names_rejected():
    with pytest.raises(InvalidInputError, match="reserved Windows device"):
        expert_slug("CON")
    decoded, error = _decode_expert_name("NUL")
    assert decoded is None
    assert error is not None


def test_decode_returns_the_canonical_storage_slug():
    display_name = "O'Brien's Data Team"

    decoded, error = _decode_expert_name(display_name)

    assert error is None
    assert decoded == expert_slug(display_name)


def test_expert_route_rejects_directory_symlink_escape(tmp_path, monkeypatch):
    display_name = "Outside Expert"
    outside = tmp_path.parent / "outside-expert"
    outside.mkdir(exist_ok=True)
    link = tmp_path / expert_slug(display_name)
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    monkeypatch.setattr(web_app, "_experts_dir", tmp_path)

    client = web_app.app.test_client()
    response = client.get("/api/experts/Outside%20Expert")

    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}
