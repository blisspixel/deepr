# Hosted MCP HTTP Container

This compose recipe runs the Deepr MCP server over Streamable HTTP for remote
agent hosts while keeping the host-facing port bound to loopback. Put Caddy,
nginx, or a cloud load balancer in front of it when callers are not on the same
machine.

The service refuses to bind inside the container until a shared token or active
scoped key exists. This recipe uses scoped keys because they give each remote
agent its own mode, expert allowlist, budget ceiling, rate limit, revocation
state, and audit trail.
Budgeted scoped calls are checked before handler dispatch from audited spend and
deterministic estimates. Metered tools without an estimate fail closed.

## Bootstrap

From this directory:

```bash
cp .env.example .env
mkdir -p ../../data/security
docker compose build
docker compose run --rm deepr-mcp-http \
  mcp keys create \
  --mode read_only \
  --rate-limit 30 \
  --budget 0 \
  --keys-path /data/security/mcp_keys.json
```

The key secret is printed once. Store it in the remote agent host secret store
or export it locally for smoke validation:

```bash
export DEEPR_MCP_KEY="deepr_mcp_..."
```

Then start the service:

```bash
docker compose up -d
deepr mcp smoke-http http://127.0.0.1:8765/mcp --auth-token "$DEEPR_MCP_KEY"
deepr mcp registration-manifest http://127.0.0.1:8765/mcp \
  --auth-token "$DEEPR_MCP_KEY" \
  --output mcp-registration.json
```

The smoke command performs only `$0` structural checks: health, initialize,
tools/list, and free `deepr_tool_search` dispatch.

## Data And Secrets

`DEEPR_HOST_DATA_DIR` from `.env` is mounted as `/data` in the container. That
directory holds experts, reports, `security/mcp_keys.json`, and
`security/mcp_remote_audit.jsonl`.

Provider API keys are optional. Leave them unset for read-only remote
consumers. If a key mode or tool budget allows paid work, keep provider keys in
`.env` or the host secret manager, not in proxy configuration.

Review remote calls before widening key mode or budget:

```bash
docker compose run --rm deepr-mcp-http \
  mcp audit list --audit-path /data/security/mcp_remote_audit.jsonl --limit 50
docker compose run --rm deepr-mcp-http \
  mcp audit summary --audit-path /data/security/mcp_remote_audit.jsonl
```

## Reverse Proxy

Keep the compose service published on `127.0.0.1:8765`. Terminate HTTPS at a
reverse proxy and forward to the loopback service:

```caddyfile
mcp.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

Validate the public endpoint after DNS and TLS are ready:

```bash
deepr mcp smoke-http https://mcp.example.com/mcp --auth-token "$DEEPR_MCP_KEY"
```

See [../mcp-http.md](../mcp-http.md) for the full hosted endpoint recipe,
including nginx, revocation, and operational rules.

For Azure Container Apps, see
[azure-container-apps/](azure-container-apps/). That template uses the same
image and command, mounts Azure Files at `/data`, and keeps scoped-key plus audit
state durable across revisions.
