"""Contract tests for reproducible application container dependencies."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_IMAGE = "python:3.15.1-slim@sha256:08275f764e022331c6d3e3ca55d8cce01fa4684b02111adf0445d71806fe7941"


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
    assert "python -m pip install --no-cache-dir uv==0.13.5" in dockerfile
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


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", ".github/workflows/mutation.yml"])
def test_maintained_acquisition_uses_patched_uv(path: str) -> None:
    workflow = yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))
    steps = [step for job in workflow["jobs"].values() for step in job["steps"]]
    uv_steps = [step for step in steps if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")]
    assert uv_steps
    assert all(Version(step["with"]["version"]) >= Version("0.13.5") for step in uv_steps)


def test_lock_and_dev_tooling_require_repaired_pip_without_runtime_dependency() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert "pip>=26.2.2" in project["project"]["optional-dependencies"]["dev"]
    assert not any(Requirement(dep).name == "pip" for dep in project["project"]["dependencies"])
    assert project["tool"]["uv"]["required-version"] == ">=0.13.5"
    pip = next(package for package in lock["package"] if package["name"] == "pip")
    assert Version(pip["version"]) >= Version("26.2.2")


def test_current_dev_pip_uses_repaired_vendored_bundle() -> None:
    from importlib.metadata import version

    from pip._vendor import certifi

    assert Version(version("pip")) >= Version("26.2.2")
    assert Version(certifi.__version__) >= Version("2026.10.19")


@pytest.mark.parametrize("name,minimum", [("brotli", "1.2.1"), ("brotlicffi", "1.2.1.0")])
def test_search_lock_excludes_vulnerable_brotli_decoders(name: str, minimum: str) -> None:
    """GHSA-9v8h-qqgm-4m35 affects both HTTPX implementation branches."""
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = [package for package in lock["package"] if package["name"] == name]
    assert packages
    assert all(Version(package["version"]) >= Version(minimum) for package in packages)


def test_filelock_metadata_and_lock_exclude_known_vulnerable_releases() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = next(
        Requirement(dep) for dep in project["project"]["dependencies"] if Requirement(dep).name == "filelock"
    )
    assert Version("3.32.2") not in requirement.specifier
    assert Version("4.2.0") not in requirement.specifier
    assert Version("4.2.4") in requirement.specifier
    assert Version("5.0.0") not in requirement.specifier
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = [package for package in lock["package"] if package["name"] == "filelock"]
    assert packages
    assert all(Version(package["version"]) >= Version("4.2.4") for package in packages)



def test_dev_lock_excludes_virtualenv_bash_prompt_regression() -> None:
    """GHSA-cx6f-vjhg-g3cc affects generated Bash activators in 21.14.9-12."""
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    pre_commit = next(package for package in lock["package"] if package["name"] == "pre-commit")
    assert any(dependency["name"] == "virtualenv" for dependency in pre_commit["dependencies"])
    packages = [package for package in lock["package"] if package["name"] == "virtualenv"]
    assert packages
    assert all(Version(package["version"]) >= Version("21.14.13") for package in packages)


def test_container_rebuild_and_base_trust_are_verified_without_network() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["containers"]["steps"]
    build = next(step["run"] for step in steps if "docker build" in step.get("run", ""))
    assert "--pull --no-cache" in build
    trust = next(
        step["run"]
        for step in steps
        if "Verify repaired base installer trust" == step.get("name", "").removesuffix(" without network access")
    )
    assert "--network none" in trust and "/usr/local/bin/python" in trust
    assert "ensurepip.version()" in trust and "certifi.__version__" in trust
    assert "emSign ECC Root CA - G3" in trust
