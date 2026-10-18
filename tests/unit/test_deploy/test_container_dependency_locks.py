"""Contract tests for reproducible application container dependencies."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_IMAGE = "python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce"


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

    assert dockerfile.splitlines()[0] in {f"FROM {PYTHON_IMAGE}", f"FROM {PYTHON_IMAGE} AS build"}
    assert "pip install --no-cache-dir uv==0.13.0" in dockerfile
    assert "COPY pyproject.toml uv.lock setup.py README.md LICENSE MANIFEST.in ./" in dockerfile
    assert "COPY src/ src/" in dockerfile
    assert sync_command in dockerfile
    assert 'ENV PATH="/app/.venv/bin:$PATH"' in dockerfile
    assert "USER deepr" in dockerfile


def test_legacy_aws_lambda_template_is_reference_only() -> None:
    template = (REPO_ROOT / "deploy/aws/template.yaml").read_text(encoding="utf-8")

    assert "BLOCKED:" in template
    assert "ReferenceOnly: true" in template
    assert "AWS::" not in template


def test_http_native_build_tools_stay_out_of_the_runtime_stage():
    dockerfile = (REPO_ROOT / "deploy/mcp-http/Dockerfile").read_text(encoding="utf-8")
    build, runtime = dockerfile.split(f"\nFROM {PYTHON_IMAGE}\n", 1)
    assert "build-essential" in build
    assert "COPY --from=build /app /app" in runtime
    assert "build-essential" not in runtime
    assert "USER deepr" in runtime
