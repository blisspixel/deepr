# Local MCP HTTP Container

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
HTTP POST concurrency is capped at 32 by default through
`DEEPR_MCP_HTTP_MAX_CONCURRENCY` in `.env`.

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
deepr mcp registration-manifest http://127.0.0.1:8765/mcp \
  --output mcp-registration.json
```

Registration is network-free. Deepr's outbound HTTP smoke and remote validation
commands are blocked before network access because endpoint self-reports cannot
prove `$0` execution. Authenticated external MCP clients may still call the
inbound Deepr server subject to its scoped-key, budget, and tool gates.
This bootstrap performs only `$0` structural checks inside Deepr.

## Data And Secrets

`DEEPR_HOST_DATA_DIR` from `.env` is mounted as `/data` in the container. That
directory holds experts, reports, `security/mcp_keys.json`, and
`security/mcp_remote_audit.jsonl`.

Provider API keys are optional. Leave them unset for local-only and read-only
remote consumers. If a key mode permits paid work, keep provider keys in `.env`
or the host secret manager, never in proxy configuration.

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

After DNS and TLS are ready, validate reachability with the external MCP client
that will consume the inbound service. Do not use Deepr's outbound
`smoke-http` command as a live probe; it intentionally fails closed before
network access.

See [../mcp-http.md](../mcp-http.md) for the full hosted endpoint recipe,
including nginx, revocation, and operational rules.

The AWS, Azure, GCP, and Cloudflare subdirectories are mechanically inert
reference markers. Deployable historical designs remain in version control
only. They are not supported when relying on Deepr's `$5` guarantee.
