# Local MCP HTTP Endpoint

Deepr can expose its inbound MCP server over Streamable HTTP from a local
machine or local Docker container. This is the supported background-service
shape in the current release. Hosted cloud infrastructure is not supported.

## Request path

```text
external MCP client
  -> operator-managed HTTPS boundary, when needed
  -> http://127.0.0.1:8765/mcp
  -> deepr mcp serve --http
  -> scoped-key policy
  -> expert and local-capacity tools
```

Deepr does not call a remote MCP server. Outbound MCP clients, live smoke
commands, and remote validation are blocked before network access. An external
client may call Deepr's inbound server.

## Start locally

Install the full local package, then create a scoped read-only key:

```bash
uv pip install -e ".[dev,full]"
mkdir -p data/security
deepr mcp keys create \
  --mode read_only \
  --rate-limit 30 \
  --budget 0 \
  --keys-path data/security/mcp_keys.json
```

Start the server on literal loopback:

```bash
deepr mcp serve \
  --http \
  --host 127.0.0.1 \
  --port 8765 \
  --path /mcp \
  --max-concurrency 32 \
  --keys-path data/security/mcp_keys.json
```

Generate registration metadata without opening a network connection:

```bash
deepr mcp registration-manifest http://127.0.0.1:8765/mcp \
  --agent-name planner \
  --output mcp-registration.json
```

Store the key secret in the consuming agent's secret store. Validate the real
connection from that external MCP client.

## Run in local Docker

The recipe in [mcp-http/](mcp-http/) mounts one Deepr data root at `/data`,
publishes only `127.0.0.1:8765`, and uses the same scoped-key store.

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
```

The image does not bundle Ollama. Local-model consultation works only when
Deepr can prove a cloud-disabled Ollama endpoint on its own literal loopback
interface. A remote model endpoint is never relabeled as local.

## Cost and security rules

- Start every remote consumer with a read-only key and `--budget 0`.
- Provider keys are optional and should remain unset for local-only operation.
- Paid tools require a finite scoped-key ceiling, canonical operator authority,
  durable reservation, one-use dispatch grant, and append-only settlement.
- Paid dispatch refuses process proxy variables because proxy charges are not
  tracked by Deepr.
- Keep the service on loopback. Use an operator-managed HTTPS boundary for any
  non-loopback client.
- Set a rate limit and expert allowlist per key.
- Review and revoke keys rather than sharing one permanent bearer token.
- Inspect `data/security/mcp_remote_audit.jsonl` before widening permissions.

```bash
deepr mcp keys revoke <key-id> --keys-path data/security/mcp_keys.json
deepr mcp audit list --audit-path data/security/mcp_remote_audit.jsonl --limit 50
deepr mcp audit summary --audit-path data/security/mcp_remote_audit.jsonl
```

## Cloud status

The AWS, Azure, GCP, and Cloudflare files under `deploy/mcp-http/` are
mechanically inert markers. Their deployable historical designs remain in
version control only. Cloud compute, storage, logging, networking, and egress
can create charges outside Deepr's ledger, and provider budget alerts are not
hard stops.

Do not create hosted resources when relying on the `$5` guarantee. A future
hosted release requires an enforceable account-level total cost ceiling,
zero-idle-cost defaults, bounded scaling and retention, and independently
verified teardown.
