"""Contracts for the supported local MCP container and inert cloud references."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_DIR = REPO_ROOT / "deploy" / "mcp-http"


def _load_compose() -> dict[str, Any]:
    return yaml.safe_load((DEPLOY_DIR / "docker-compose.yml").read_text(encoding="utf-8"))


def test_mcp_http_compose_uses_safe_network_and_data_defaults() -> None:
    service = _load_compose()["services"]["deepr-mcp-http"]

    assert service["ports"] == ["127.0.0.1:8765:8765"]
    assert service["volumes"] == ["${DEEPR_HOST_DATA_DIR:-../../data}:/data"]
    assert service["env_file"] == [{"path": ".env", "required": False}]
    assert service["environment"]["DEEPR_DATA_DIR"] == "/data"
    assert service["environment"]["DEEPR_MCP_KEYS_PATH"] == "/data/security/mcp_keys.json"
    assert service["environment"]["DEEPR_MCP_HTTP_MAX_CONCURRENCY"] == "${DEEPR_MCP_HTTP_MAX_CONCURRENCY:-32}"
    assert service["restart"] == "unless-stopped"


def test_mcp_http_compose_serves_with_scoped_key_store() -> None:
    service = _load_compose()["services"]["deepr-mcp-http"]
    assert service["command"] == [
        "mcp",
        "serve",
        "--http",
        "--host",
        "0.0.0.0",
        "--port",
        "8765",
        "--path",
        "/mcp",
        "--keys-path",
        "/data/security/mcp_keys.json",
    ]
    assert service["healthcheck"]["test"][-1].count("/mcp/health") == 1


def test_mcp_http_dockerfile_runs_as_cli_with_frozen_full_install() -> None:
    dockerfile = (DEPLOY_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY pyproject.toml uv.lock setup.py README.md LICENSE MANIFEST.in ./" in dockerfile
    assert "uv sync --frozen --no-dev --no-editable --extra full" in dockerfile
    assert "USER deepr" in dockerfile
    assert "DEEPR_MCP_KEYS_PATH=/data/security/mcp_keys.json" in dockerfile
    assert "DEEPR_MCP_HTTP_MAX_CONCURRENCY=32" in dockerfile
    assert 'ENTRYPOINT ["deepr"]' in dockerfile
    assert '"--host", "0.0.0.0"' in dockerfile
    assert '"--keys-path", "/data/security/mcp_keys.json"' in dockerfile


def test_mcp_http_readme_documents_zero_spend_local_bootstrap() -> None:
    readme = (DEPLOY_DIR / "README.md").read_text(encoding="utf-8")

    assert "mcp keys create" in readme
    assert "--budget 0" in readme
    assert "docker compose up -d" in readme
    assert "Do not use Deepr's outbound" in readme
    assert "smoke-http` command as a live probe" in readme
    assert "only `$0` structural checks" in readme


def test_hosted_mcp_assets_are_mechanically_inert() -> None:
    cases = {
        "aws-ecs-fargate/template.yaml": ("BLOCKED:", "ReferenceOnly: true"),
        "azure-container-apps/main.bicep": ("BLOCKED:", "targetScope = 'reference-only'"),
        "gcp-cloud-run/main.tf": ("BLOCKED:", 'required_version = "< 0.0.0"'),
        "cloudflare-worker/worker.mjs": ("BLOCKED:", "No fetch handler"),
        "cloudflare-worker/wrangler.toml.example": ("BLOCKED:", "no deployable"),
    }
    forbidden = (
        "AWS::",
        "Microsoft.App/",
        'resource "google_',
        "export default",
        'main = "worker.mjs"',
    )
    for relative, required in cases.items():
        source = (DEPLOY_DIR / relative).read_text(encoding="utf-8")
        assert all(fragment in source for fragment in required)
        assert all(fragment not in source for fragment in forbidden)


def test_hosted_mcp_docs_state_reference_only_cost_boundary() -> None:
    for directory in (
        "aws-ecs-fargate",
        "azure-container-apps",
        "gcp-cloud-run",
        "cloudflare-worker",
    ):
        readme = (DEPLOY_DIR / directory / "README.md").read_text(encoding="utf-8")
        assert "not supported in v2.40" in readme or "not a supported deployment surface in v2.40" in readme
        assert "outside Deepr's cost ledger" in readme
        assert "Do not" in readme
        assert "`$5` guarantee" in readme
