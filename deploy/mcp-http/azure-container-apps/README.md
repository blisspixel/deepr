# Azure Container Apps Hosted MCP Template

This template runs the hosted MCP HTTP container on Azure Container Apps with a
persistent Azure Files mount for Deepr data, scoped keys, reports, cost ledgers,
and remote-call audit logs.

It is a local deployment artifact only. Creating Azure resources can incur cloud
costs, so this repo validates the template shape locally and does not run `az`
commands during tests.

## What It Creates

- Log Analytics workspace for Container Apps logs.
- Storage account plus Azure Files share mounted at `/data`.
- Container Apps managed environment.
- Container App running `deepr mcp serve --http --host 0.0.0.0 --path /mcp`.
- HTTPS-only ingress with optional public exposure and optional CIDR allowlist.

Provider API keys are intentionally absent. Add provider credentials only when a
scoped key mode, budget ceiling, and rate limit intentionally allow paid tools.

## Build And Push The Image

Build the existing hosted MCP image from the repo root and push it to a registry
your Container App can pull from:

```bash
docker build -f deploy/mcp-http/Dockerfile -t ghcr.io/OWNER/deepr-mcp-http:TAG .
docker push ghcr.io/OWNER/deepr-mcp-http:TAG
```

For a private registry, pass `registryServer`, `registryUsername`, and
`registryPassword` as Bicep parameters or configure registry access after
deployment with Azure CLI.

## Bootstrap Scoped Keys

Scoped keys are the production path because they carry mode, expert allowlist,
budget ceiling, rate limit, revocation state, and audit metadata. Create the key
store locally with the same image:

```bash
mkdir -p ./deepr-mcp-data/security
docker run --rm \
  -v "$PWD/deepr-mcp-data:/data" \
  ghcr.io/OWNER/deepr-mcp-http:TAG \
  mcp keys create \
  --mode read_only \
  --rate-limit 30 \
  --budget 0 \
  --keys-path /data/security/mcp_keys.json
```

The key secret is printed once. Store it in the remote agent host secret store.
After the Bicep deployment creates the file share, upload
`deepr-mcp-data/security/mcp_keys.json` to `security/mcp_keys.json` in that
share, then restart the Container App revision.

`initialSharedAuthToken` exists only as a first-boot escape hatch. It can prove
the HTTPS route is wired before the scoped-key file is uploaded, but it does not
carry per-agent scope, budget, rate-limit, or audit metadata. Remove it once
scoped keys are in place.

## Deploy

```bash
az group create --name deepr-mcp-rg --location eastus
az deployment group create \
  --resource-group deepr-mcp-rg \
  --template-file deploy/mcp-http/azure-container-apps/main.bicep \
  --parameters \
    containerImage=ghcr.io/OWNER/deepr-mcp-http:TAG \
    externalIngress=true \
    allowedIpRanges='["203.0.113.0/24"]'
```

Use `externalIngress=false` for a private environment. If you enable public
ingress, keep HTTPS on, use scoped keys, and prefer `allowedIpRanges` whenever
the remote agent host has stable egress ranges.

## Validate

After the key store exists on the mounted share and the revision is healthy:

```bash
MCP_ENDPOINT="$(az deployment group show \
  --resource-group deepr-mcp-rg \
  --name main \
  --query properties.outputs.mcpEndpoint.value \
  --output tsv)"

deepr mcp smoke-http "$MCP_ENDPOINT" --auth-token "$DEEPR_MCP_KEY"
```

The smoke command performs only `$0` structural checks: health, initialize,
tools/list, and free `deepr_tool_search` dispatch.

## Operate

Remote calls through scoped keys append audit records to
`/data/security/mcp_remote_audit.jsonl`. Review the file before widening key
mode or budget:

```bash
deepr mcp audit list --audit-path ./mcp_remote_audit.jsonl --limit 50
deepr mcp audit summary --audit-path ./mcp_remote_audit.jsonl
```

Keep the same guardrails as the local container recipe:

- Use one scoped key per remote agent.
- Start read-only with `--budget 0`.
- Set a per-key rate limit.
- Upload and back up `security/mcp_keys.json` and audit logs as durable data.
- Add provider API keys only when paid tools are intentional.
