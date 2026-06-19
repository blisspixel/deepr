"""Contract tests for hosted MCP HTTP container assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_DIR = REPO_ROOT / "deploy" / "mcp-http"
AZURE_TEMPLATE = DEPLOY_DIR / "azure-container-apps" / "main.bicep"


def _load_compose() -> dict[str, Any]:
    return yaml.safe_load((DEPLOY_DIR / "docker-compose.yml").read_text(encoding="utf-8"))


def test_mcp_http_compose_uses_safe_network_and_data_defaults():
    service = _load_compose()["services"]["deepr-mcp-http"]

    assert service["ports"] == ["127.0.0.1:8765:8765"]
    assert service["volumes"] == ["${DEEPR_HOST_DATA_DIR:-../../data}:/data"]
    assert service["env_file"] == [{"path": ".env", "required": False}]
    assert service["environment"]["DEEPR_DATA_DIR"] == "/data"
    assert service["environment"]["DEEPR_MCP_KEYS_PATH"] == "/data/security/mcp_keys.json"
    assert service["environment"]["DEEPR_MCP_HTTP_MAX_CONCURRENCY"] == "${DEEPR_MCP_HTTP_MAX_CONCURRENCY:-32}"
    assert service["restart"] == "unless-stopped"


def test_mcp_http_compose_serves_with_scoped_key_store():
    service = _load_compose()["services"]["deepr-mcp-http"]
    command = service["command"]

    assert command == [
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


def test_mcp_http_dockerfile_runs_as_cli_with_full_install():
    dockerfile = (DEPLOY_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert 'pip install --no-cache-dir ".[full]"' in dockerfile
    assert "USER deepr" in dockerfile
    assert "DEEPR_MCP_KEYS_PATH=/data/security/mcp_keys.json" in dockerfile
    assert "DEEPR_MCP_HTTP_MAX_CONCURRENCY=32" in dockerfile
    assert 'ENTRYPOINT ["deepr"]' in dockerfile
    assert '"--host", "0.0.0.0"' in dockerfile
    assert '"--keys-path", "/data/security/mcp_keys.json"' in dockerfile


def test_mcp_http_readme_documents_zero_spend_bootstrap_and_smoke():
    readme = (DEPLOY_DIR / "README.md").read_text(encoding="utf-8")

    assert "mcp keys create" in readme
    assert "--budget 0" in readme
    assert "docker compose up -d" in readme
    assert "deepr mcp smoke-http http://127.0.0.1:8765/mcp" in readme
    assert "only `$0` structural checks" in readme


def test_mcp_http_azure_template_mounts_persistent_deepr_data():
    template = AZURE_TEMPLATE.read_text(encoding="utf-8")

    assert "Microsoft.App/managedEnvironments/storages@2024-03-01" in template
    assert "Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01" in template
    assert "storageType: 'AzureFile'" in template
    assert "storageName: environmentStorage.name" in template
    assert "mountPath: '/data'" in template
    assert "value: '/data/reports'" in template
    assert "value: '/data/security/mcp_keys.json'" in template
    assert "name: 'DEEPR_MCP_HTTP_MAX_CONCURRENCY'" in template
    assert "value: string(maxConcurrentRequests)" in template


def test_mcp_http_azure_template_serves_with_http_guardrails():
    template = AZURE_TEMPLATE.read_text(encoding="utf-8")

    assert "Microsoft.App/containerApps@2024-03-01" in template
    assert "external: externalIngress" in template
    assert "allowInsecure: false" in template
    assert "ipSecurityRestrictions: [for (range, i) in allowedIpRanges:" in template
    assert "'mcp'" in template
    assert "'serve'" in template
    assert "'--http'" in template
    assert "'--host'" in template
    assert "'0.0.0.0'" in template
    assert "'--keys-path'" in template
    assert "'/data/security/mcp_keys.json'" in template
    assert "param maxConcurrentRequests int = 32" in template
    assert "concurrentRequests: string(maxConcurrentRequests)" in template
    assert "path: '/mcp/health'" in template


def test_mcp_http_azure_template_keeps_provider_keys_out_of_infra():
    template = AZURE_TEMPLATE.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" not in template
    assert "GOOGLE_API_KEY" not in template
    assert "XAI_API_KEY" not in template
    assert "ANTHROPIC_API_KEY" not in template
    assert "DEEPR_MCP_AUTH_TOKEN" in template


def test_mcp_http_azure_readme_documents_scoped_key_bootstrap():
    readme = (DEPLOY_DIR / "azure-container-apps" / "README.md").read_text(encoding="utf-8")

    assert "mcp keys create" in readme
    assert "--budget 0" in readme
    assert "initialSharedAuthToken" in readme
    assert "deepr mcp smoke-http" in readme
    assert "only `$0` structural checks" in readme
    assert "Add provider API keys only when paid tools are intentional" in readme
