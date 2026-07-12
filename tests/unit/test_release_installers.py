"""Regression checks for the public GitHub Releases install channel."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("relative_path", ["scripts/install.sh", "scripts/install.ps1"])
def test_installers_resolve_a_repository_release_wheel(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "https://api.github.com/repos/blisspixel/deepr/releases/latest" in text
    assert "https://github.com/blisspixel/deepr/releases/download/" in text
    assert "deepr_research-" in text
    assert "--force" in text
    assert "-m pipx --version" in text
    assert "pypi.org" not in text.lower()
    assert "cd deepr/deepr" not in text
    assert "Configure capacity: local Ollama, a supported plan CLI, or an API provider" in text
    assert "Add at least one API key" not in text


def test_makefile_exposes_only_explicit_manual_pypi_publication() -> None:
    text = (ROOT / "scripts/Makefile").read_text(encoding="utf-8")

    assert "publish-pypi-manual:" in text
    assert "\npublish:" not in text
    assert "GitHub Releases is the current release channel" in text


def test_scripts_readme_uses_real_make_targets_from_repository_root() -> None:
    text = (ROOT / "scripts/README.md").read_text(encoding="utf-8")

    assert "make -f scripts/Makefile test" in text
    assert "make -f scripts/Makefile build" in text
    assert "make format" not in text
    assert "make typecheck" not in text
