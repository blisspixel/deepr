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

from deepr.web.app import _validate_expert_name


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
