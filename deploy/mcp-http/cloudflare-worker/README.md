# Cloudflare Worker Edge Ingress

This recipe fronts an existing hosted Deepr MCP HTTP origin with a Cloudflare
Worker. It is an edge ingress and proxy only. The origin still owns scoped-key auth,
budgets, rate limits, audit logs, tool dispatch, and all provider credentials.

Use it when the MCP container or cloud template already has a stable HTTPS
origin and you want a small edge guard in front of `/mcp`.

## Guardrails

- Only `/mcp` and `/mcp/*` are proxied.
- `DEEPR_MCP_ORIGIN` must be an HTTPS URL and should include the origin MCP path.
- Request bodies are capped at 1 MiB before proxying.
- `Authorization`, `X-Api-Key`, `Content-Type`, `Accept`, and MCP session
  headers pass through to the origin.
- `X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-For` are set for
  origin-side audit context.
- Provider API keys, scoped-key stores, and remote-audit files do not belong in
  the Worker. Keep them on the origin side.

## Configure

```bash
cd deploy/mcp-http/cloudflare-worker
cp wrangler.toml.example wrangler.toml
```

Edit `wrangler.toml`:

```toml
[vars]
DEEPR_MCP_ORIGIN = "https://mcp-origin.example.com/mcp"
```

Set a route or custom domain in the same file after DNS is ready.

## Validate Locally

The repository validates this recipe without a Cloudflare account:

```bash
node --check worker.mjs
```

After a real deployment, run the same `$0` structural smoke used by the other
hosted MCP recipes:

```bash
deepr mcp smoke-http https://mcp.example.com/mcp --auth-token "$DEEPR_MCP_KEY"
deepr mcp registration-manifest https://mcp.example.com/mcp \
  --auth-token "$DEEPR_MCP_KEY" \
  --agent-name planner \
  --output mcp-registration.json
```

The smoke command checks health, initialize, tools/list, and free tool-search
dispatch only. It does not call provider APIs.

## Operational Notes

Deploying this Worker or attaching a Cloudflare route can incur Cloudflare
cost. The checked-in recipe and CI validation are local-only.

Review the origin-side remote audit log before widening any scoped key:

```bash
deepr mcp audit summary --audit-path data/security/mcp_remote_audit.jsonl
```
