"""Contract tests for reproducible application container dependencies."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_IMAGE = (
    "python:3.12.13-slim@"
    "sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de"
)


@pytest.mark.parametrize(
    ("path", "sync_command"),
    [
        ("Dockerfile", "uv sync --frozen --no-dev --no-editable"),
        (
            "deploy/aws/src/worker/Dockerfile",
            "uv sync --frozen --no-dev --no-editable --extra aws",
        ),
        (
            "deploy/mcp-http/Dockerfile",
            "uv sync --frozen --no-dev --no-editable --extra full",
        ),
    ],
)
def test_application_containers_use_one_frozen_dependency_authority(
    path: str,
    sync_command: str,
) -> None:
    dockerfile = (REPO_ROOT / path).read_text(encoding="utf-8")

    assert dockerfile.startswith(f"FROM {PYTHON_IMAGE}\n")
    assert "pip install --no-cache-dir uv==0.11.32" in dockerfile
    assert "COPY pyproject.toml uv.lock setup.py README.md LICENSE MANIFEST.in ./" in dockerfile
    assert "COPY src/ src/" in dockerfile
    assert sync_command in dockerfile
    assert 'ENV PATH="/app/.venv/bin:$PATH"' in dockerfile
    assert "USER deepr" in dockerfile


def test_aws_lambda_runtime_matches_the_packaged_python_floor() -> None:
    template = (REPO_ROOT / "deploy/aws/template.yaml").read_text(encoding="utf-8")

    assert "Runtime: python3.12" in template
    assert "Runtime: python3.11" not in template
