"""Contract tests for hosted MCP HTTP container assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_DIR = REPO_ROOT / "deploy" / "mcp-http"
AZURE_TEMPLATE = DEPLOY_DIR / "azure-container-apps" / "main.bicep"
AWS_TEMPLATE = DEPLOY_DIR / "aws-ecs-fargate" / "template.yaml"
GCP_TEMPLATE = DEPLOY_DIR / "gcp-cloud-run" / "main.tf"
CLOUDFLARE_DIR = DEPLOY_DIR / "cloudflare-worker"
CLOUDFLARE_WORKER = CLOUDFLARE_DIR / "worker.mjs"
CLOUDFLARE_WRANGLER = CLOUDFLARE_DIR / "wrangler.toml.example"


def _load_compose() -> dict[str, Any]:
    return yaml.safe_load((DEPLOY_DIR / "docker-compose.yml").read_text(encoding="utf-8"))


class _CloudFormationLoader(yaml.SafeLoader):
    pass


def _load_cloudformation_template() -> dict[str, Any]:
    return yaml.load(AWS_TEMPLATE.read_text(encoding="utf-8"), Loader=_CloudFormationLoader)


def _cloudformation_tag_constructor(
    loader: _CloudFormationLoader, _tag_prefix: str, node: yaml.Node
) -> str | list[Any] | dict[str, Any] | None:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_CloudFormationLoader.add_multi_constructor("!", _cloudformation_tag_constructor)


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


def test_mcp_http_aws_template_mounts_persistent_deepr_data():
    parsed = _load_cloudformation_template()
    template = AWS_TEMPLATE.read_text(encoding="utf-8")

    assert parsed["Resources"]["TaskDefinition"]["Properties"]["ContainerDefinitions"][0]["Name"] == "deepr-mcp-http"
    assert "AWS::EFS::FileSystem" in template
    assert "AWS::EFS::AccessPoint" in template
    assert "AWS::EFS::MountTarget" in template
    assert "BackupPolicy:" in template
    assert "Status: ENABLED" in template
    assert "Uid: '1000'" in template
    assert "Gid: '1000'" in template
    assert "Path: /deepr-data" in template
    assert "ContainerPath: /data" in template
    assert "TransitEncryption: ENABLED" in template
    assert "AccessPointId: !Ref DataAccessPoint" in template
    assert "Value: /data/reports" in template
    assert "Value: /data/security/mcp_keys.json" in template


def test_mcp_http_aws_template_serves_with_https_guardrails():
    template = AWS_TEMPLATE.read_text(encoding="utf-8")

    assert "AWS::ElasticLoadBalancingV2::LoadBalancer" in template
    assert "AWS::ElasticLoadBalancingV2::Listener" in template
    assert "Port: 443" in template
    assert "Protocol: HTTPS" in template
    assert "CertificateArn: !Ref CertificateArn" in template
    assert "HealthCheckPath: /mcp/health" in template
    assert "HealthCheckProtocol: HTTP" in template
    assert "TargetType: ip" in template
    assert "AWS::EC2::SecurityGroupIngress" in template
    assert "AWS::EC2::SecurityGroupEgress" in template
    assert "SecurityGroupEgress: []" in template
    assert "- mcp" in template
    assert "- serve" in template
    assert "- --http" in template
    assert "- --host" in template
    assert "- 0.0.0.0" in template
    assert "- --keys-path" in template
    assert "- /data/security/mcp_keys.json" in template
    assert "- --max-concurrency" in template
    assert "Name: DEEPR_MCP_HTTP_MAX_CONCURRENCY" in template
    assert "Value: !Sub '${MaxConcurrentRequests}'" in template


def test_mcp_http_aws_template_keeps_provider_keys_out_of_infra():
    template = AWS_TEMPLATE.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" not in template
    assert "GOOGLE_API_KEY" not in template
    assert "XAI_API_KEY" not in template
    assert "ANTHROPIC_API_KEY" not in template
    assert "DEEPR_MCP_AUTH_TOKEN" in template
    assert "InitialSharedAuthToken" in template


def test_mcp_http_aws_readme_documents_scoped_key_bootstrap():
    readme = (DEPLOY_DIR / "aws-ecs-fargate" / "README.md").read_text(encoding="utf-8")

    assert "mcp keys create" in readme
    assert "--budget 0" in readme
    assert "InitialSharedAuthToken" in readme
    assert "aws cloudformation deploy" in readme
    assert "deepr mcp smoke-http" in readme
    assert "only `$0` structural checks" in readme
    assert "Add provider API keys only when paid tools are intentional" in readme


def test_mcp_http_gcp_template_mounts_persistent_deepr_data():
    template = GCP_TEMPLATE.read_text(encoding="utf-8")

    assert 'resource "google_storage_bucket" "data"' in template
    assert 'public_access_prevention    = "enforced"' in template
    assert "uniform_bucket_level_access = true" in template
    assert "versioning {" in template
    assert "enabled = true" in template
    assert 'role   = "roles/storage.objectAdmin"' in template
    assert "volume_mounts {" in template
    assert 'mount_path = "/data"' in template
    assert "gcs {" in template
    assert "bucket    = google_storage_bucket.data.name" in template
    assert "read_only = false" in template
    assert 'name  = "DEEPR_REPORTS_PATH"' in template
    assert 'value = "/data/reports"' in template
    assert 'name  = "DEEPR_MCP_KEYS_PATH"' in template
    assert 'value = "/data/security/mcp_keys.json"' in template


def test_mcp_http_gcp_template_serves_with_single_writer_guardrails():
    template = GCP_TEMPLATE.read_text(encoding="utf-8")

    assert 'resource "google_cloud_run_v2_service" "mcp"' in template
    assert 'ingress  = "INGRESS_TRAFFIC_ALL"' in template
    assert 'resource "google_cloud_run_v2_service_iam_member" "public_invoker"' in template
    assert 'role     = "roles/run.invoker"' in template
    assert 'member   = "allUsers"' in template
    assert "max_instance_request_concurrency = var.max_concurrent_requests" in template
    assert "condition     = var.max_instances == 1" in template
    assert "condition     = var.max_concurrent_requests == 1" in template
    assert '"mcp",' in template
    assert '"serve",' in template
    assert '"--http",' in template
    assert '"--host",' in template
    assert '"0.0.0.0",' in template
    assert '"--keys-path",' in template
    assert '"/data/security/mcp_keys.json",' in template
    assert '"--max-concurrency",' in template
    assert 'name  = "DEEPR_MCP_HTTP_MAX_CONCURRENCY"' in template
    assert "value = tostring(var.max_concurrent_requests)" in template
    assert 'path = "/mcp/health"' in template


def test_mcp_http_gcp_template_keeps_provider_keys_out_of_infra():
    template = GCP_TEMPLATE.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" not in template
    assert "GOOGLE_API_KEY" not in template
    assert "XAI_API_KEY" not in template
    assert "ANTHROPIC_API_KEY" not in template
    assert "DEEPR_MCP_AUTH_TOKEN" not in template


def test_mcp_http_gcp_readme_documents_scoped_key_bootstrap():
    readme = (DEPLOY_DIR / "gcp-cloud-run" / "README.md").read_text(encoding="utf-8")

    assert "mcp keys create" in readme
    assert "--budget 0" in readme
    assert "gcloud storage cp" in readme
    assert "allow_public_invoker=false" in readme
    assert "allow_public_invoker=true" in readme
    assert "deepr mcp smoke-http" in readme
    assert "only `$0` structural checks" in readme
    assert "Add provider API keys only when paid tools are intentional" in readme


def test_mcp_http_cloudflare_worker_is_edge_guard_only():
    worker = CLOUDFLARE_WORKER.read_text(encoding="utf-8")

    assert "DEEPR_MCP_ORIGIN" in worker
    assert 'url.protocol !== "https:"' in worker
    assert "ORIGIN_REQUIRES_HTTPS" in worker
    assert "pathname === MCP_PATH_PREFIX || pathname.startsWith(`${MCP_PATH_PREFIX}/`)" in worker
    assert 'jsonError(404, "NOT_FOUND"' in worker
    assert "MAX_BODY_BYTES = 1048576" in worker
    assert 'jsonError(413, "REQUEST_TOO_LARGE"' in worker
    assert 'headers.set("X-Forwarded-Proto", "https")' in worker
    assert 'headers.set("X-Forwarded-Host", requestUrl.host)' in worker
    assert "CF-Connecting-IP" in worker


def test_mcp_http_cloudflare_worker_preserves_origin_enforcement():
    worker = CLOUDFLARE_WORKER.read_text(encoding="utf-8")

    assert "fetch(new Request(targetUrl, init))" in worker
    assert 'normalized === "host"' in worker
    assert "HOP_BY_HOP_HEADERS" in worker
    assert "request.arrayBuffer()" in worker
    assert "ScopedMCPKeyStore" not in worker
    assert "RemoteMCPAuditLog" not in worker
    assert "OPENAI_API_KEY" not in worker
    assert "GOOGLE_API_KEY" not in worker
    assert "XAI_API_KEY" not in worker
    assert "ANTHROPIC_API_KEY" not in worker


def test_mcp_http_cloudflare_wrangler_example_requires_https_origin():
    wrangler = CLOUDFLARE_WRANGLER.read_text(encoding="utf-8")

    assert 'main = "worker.mjs"' in wrangler
    assert 'compatibility_date = "2026-06-19"' in wrangler
    assert "DEEPR_MCP_ORIGIN" in wrangler
    assert "https://mcp-origin.example.com/mcp" in wrangler
    assert "refuses plaintext origins" in wrangler


def test_mcp_http_cloudflare_readme_documents_zero_spend_validation():
    readme = (CLOUDFLARE_DIR / "README.md").read_text(encoding="utf-8")

    assert "edge ingress and proxy only" in readme
    assert "origin still owns scoped-key auth" in readme
    assert "Request bodies are capped at 1 MiB" in readme
    assert "Provider API keys, scoped-key stores, and remote-audit files do not belong" in readme
    assert "node --check worker.mjs" in readme
    assert "deepr mcp smoke-http https://mcp.example.com/mcp" in readme
    assert "The checked-in recipe and CI validation are local-only" in readme
