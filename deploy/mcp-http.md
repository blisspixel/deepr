# Hosted MCP HTTP Endpoint

This recipe exposes Deepr's MCP server to remote agent hosts through
Streamable HTTP while keeping Deepr itself bound to loopback. TLS, public
DNS, and edge hardening belong at the reverse proxy. The Python process should
not be the public TLS terminator.

## Shape

```
remote agent host
  -> HTTPS reverse proxy
  -> http://127.0.0.1:8765/mcp
  -> deepr mcp serve --http
```

Use scoped MCP keys for production. Shared tokens remain available for local
testing and simple private networks, but scoped keys give each agent its own
mode, expert allowlist, budget ceiling, rate limit, revocation state, and audit
trail.

## Prepare The Host

Install Deepr on the machine that owns the experts and reports:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,full]"
deepr doctor
```

Keep provider API keys out of the proxy configuration. Put them in the Deepr
process environment only when you intentionally allow paid research tools.
Read-only and status smoke tests do not require provider keys.
Scoped-key budgets are enforced before tool dispatch from audited spend and
deterministic estimates. Metered tools without an estimate are denied before
they can run.

Create a scoped key store and mint one key per remote agent:

```bash
mkdir -p data/security
deepr mcp keys create \
  --mode read_only \
  --rate-limit 30 \
  --budget 0 \
  --keys-path data/security/mcp_keys.json
```

The secret is printed once. Store it in the remote host secret manager. Do not
commit it and do not put it in reverse-proxy access logs.

Start Deepr on loopback:

```bash
deepr mcp serve \
  --http \
  --host 127.0.0.1 \
  --port 8765 \
  --path /mcp \
  --keys-path data/security/mcp_keys.json
```

## Container Variant

For a repeatable local service, use the compose recipe in
[mcp-http/](mcp-http/). It builds a dedicated HTTP MCP image, mounts one Deepr
data directory at `/data`, publishes only `127.0.0.1:8765`, and starts with the
same scoped-key store path used above.

Bootstrap it before the first `up` so the non-loopback container bind has an
active scoped key:

```bash
cd deploy/mcp-http
cp .env.example .env
mkdir -p ../../data/security
docker compose build
docker compose run --rm deepr-mcp-http \
  mcp keys create \
  --mode read_only \
  --rate-limit 30 \
  --budget 0 \
  --keys-path /data/security/mcp_keys.json
docker compose up -d
deepr mcp smoke-http http://127.0.0.1:8765/mcp --auth-token "$DEEPR_MCP_KEY"
```

## Azure Container Apps Variant

The first cloud-provider template lives in
[mcp-http/azure-container-apps/](mcp-http/azure-container-apps/). It deploys the
same hosted MCP container to Azure Container Apps, mounts an Azure Files share
at `/data`, keeps `security/mcp_keys.json` and
`security/mcp_remote_audit.jsonl` durable, and exposes HTTPS-only ingress with
optional CIDR restrictions.

This is a template, not a deployment run. Creating Azure resources can incur
cloud cost. The repo validates the template shape locally and does not run `az`
or register with a hosted agent platform during CI.

Use scoped keys for production. The template includes an optional
`initialSharedAuthToken` only as a first-boot escape hatch; it should be removed
after the scoped-key file is uploaded to the mounted share.

## Caddy Reverse Proxy

Caddy handles certificates automatically for a public DNS name:

```caddyfile
mcp.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

Then validate from any machine that can reach the public endpoint:

```bash
deepr mcp smoke-http https://mcp.example.com/mcp --auth-token "$DEEPR_MCP_KEY"
deepr mcp registration-manifest https://mcp.example.com/mcp \
  --auth-token "$DEEPR_MCP_KEY" \
  --agent-name planner \
  --output mcp-registration.json
```

The smoke command performs only `$0` structural checks:

- `GET /health`
- JSON-RPC `initialize`
- JSON-RPC `tools/list`
- JSON-RPC `tools/call` for `deepr_tool_search`

It exits nonzero if authentication, routing, or dispatch is broken.
The registration manifest wraps the same endpoint metadata and smoke result in
the published `deepr-mcp-registration-manifest-v1` schema without writing the
bearer token into the file.

## Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name mcp.example.com;

    ssl_certificate /etc/letsencrypt/live/mcp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.example.com/privkey.pem;

    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Authorization $http_authorization;
        proxy_buffering off;
    }
}
```

Validate with the same smoke command:

```bash
deepr mcp smoke-http https://mcp.example.com/mcp --auth-token "$DEEPR_MCP_KEY"
```

## Operational Rules

- Keep Deepr bound to `127.0.0.1` unless you have a separate network boundary.
- Use HTTPS for any non-loopback caller. Bearer tokens over plaintext HTTP are
  visible on the network.
- Use `read_only` keys for discovery, status, and handoff consumers.
- Use `standard` or higher modes only for agents that are allowed to mutate
  expert state or submit paid work, and pair them with a budget ceiling.
- Set per-key rate limits for every remote agent.
- Revoke a key immediately when an agent host is retired:

```bash
deepr mcp keys revoke <key-id> --keys-path data/security/mcp_keys.json
```

Remote calls made through scoped keys write append-only audit records. Inspect
the audit log before widening the key mode or budget:

```bash
deepr mcp audit list --audit-path data/security/mcp_remote_audit.jsonl --limit 50
deepr mcp audit summary --audit-path data/security/mcp_remote_audit.jsonl
```
