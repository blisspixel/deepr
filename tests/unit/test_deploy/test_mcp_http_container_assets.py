"""Contract tests for hosted MCP HTTP container assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_DIR = REPO_ROOT / "deploy" / "mcp-http"


def _load_compose() -> dict[str, Any]:
    return yaml.safe_load((DEPLOY_DIR / "docker-compose.yml").read_text(encoding="utf-8"))


def test_mcp_http_compose_uses_safe_network_and_data_defaults():
    service = _load_compose()["services"]["deepr-mcp-http"]

    assert service["ports"] == ["127.0.0.1:8765:8765"]
    assert service["volumes"] == ["${DEEPR_HOST_DATA_DIR:-../../data}:/data"]
    assert service["env_file"] == [{"path": ".env", "required": False}]
    assert service["environment"]["DEEPR_DATA_DIR"] == "/data"
    assert service["environment"]["DEEPR_MCP_KEYS_PATH"] == "/data/security/mcp_keys.json"
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
