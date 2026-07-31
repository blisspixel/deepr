# Design: Hosted MCP Endpoint (remote, authenticated Deepr)

Target: v2.18. Roadmap: Phase 5 (promoted from backlog 2026-06-11 -
"cloud-hosted autopilots cannot call a stdio server on a laptop").
Status: local inbound foundation only. The versioned handoff contract, loopback
HTTP serve path, scoped-key, budget, rate-limit, audit primitives, audit review
CLI, HTTP concurrency cap, remote-audit schema, and loopback-published container
are executable. Outbound smoke and remote validation are blocked before network
access pending independent service-cost authority. Registration-manifest
generation is network-free. The Azure Container Apps, AWS ECS Fargate, GCP
Cloud Run, Cloudflare Worker, and reverse-proxy files are mechanically inert
reference shapes, not supported or live-validated deployments.

## Problem

At design inception, June-2026 agent platforms ran agents in their clouds while
Deepr's MCP server was stdio-only. Deepr now has an executable inbound loopback
HTTP listener and local container, but no supported hosted deployment or
independently authorized outbound validator. The original reach gap therefore
remains for cloud-hosted agents.

## Design

### Transport

Streamable HTTP on the existing MCP server - the tool surface, allowlist, and
error model do not change. As of v2.41.0 the endpoint implements the
`2026-07-28` revision's server rules for modern clients (metadata-header and
Origin validation, 404/-32601 unknown methods, 202 notifications,
`subscriptions/listen` as a POST-response SSE stream, no protocol sessions or
resumability) while still serving legacy `initialize`-era clients on the same
endpoint. stdio remains the local default; HTTP is an additional listener
(`deepr mcp serve --http --host 127.0.0.1 --port 8765`), one process, same
dispatch.

### Handoff contract

`deepr_expert_handoff` and `/api/experts/{name}/handoff` now provide the first
remote-friendly read contract: `deepr-expert-handoff-v1`. It is `$0`,
read-only, bounded by caller-provided limits, and generated from the shared
`build_expert_handoff` serializer so MCP and web responses cannot drift. The
payload includes profile summary, manifest counts, bounded claims/gaps,
dashboard telemetry, loop-status rollup, OKF interchange hints, and an additive
compatibility contract. Detailed expert state remains `SENSITIVE`; scoped keys
must still satisfy key mode, expert scope, and confirmation gates before it is
returned remotely.

### Auth and scoping (API-key first, OAuth later)

`ScopedMCPKeyStore` and the HTTP transport now provide the first local
primitive. When a store is configured, Bearer or `X-Api-Key` requests
authenticate against per-key metadata, and `tools/call` is checked against the
key's `ResearchMode`, optional `expert_allowlist`, and confirmation
requirement before dispatch. `RemoteMCPAuditLog` writes append-only
`deepr-mcp-remote-audit-v1` events with `{schema_version, kind, timestamp,
key_id, mode, tool, args_hash, trace_id, outcome, error_code, expert_names,
cost_usd}`. The schema is published under `docs/schemas/`.
`deepr mcp keys` creates, lists, and revokes those key records locally.
`deepr mcp audit list` and `deepr mcp audit summary` review the local audit log.
`deepr mcp smoke-http` returns a structured block before opening a connection.
A remote endpoint, including one addressed through loopback, cannot
independently prove that processing the request costs `$0`.
`deepr mcp registration-manifest` emits a
`deepr-mcp-registration-manifest-v1` packet with endpoint, auth-header,
scoped-key, audit-schema, and blocked-smoke metadata without serializing bearer
secrets or probing the endpoint. This is not a supported hosted endpoint: live
registration and cloud operational validation remain unimplemented.

- **Scoped API keys**, not one shared secret: each key carries
  `{key_id, mode, expert_allowlist, budget, rate_limit}`.
  - `mode`: maps to the existing `ResearchMode` tool allowlist
    (READ_ONLY keys cannot reach WRITE/EXECUTE/SENSITIVE tools - the
    enforcement layer already exists, keys just select it).
  - `expert_allowlist`: optional - a key scoped to specific experts.
  - `budget`: per-key spend ceiling. The HTTP transport now sums prior audited
    `cost_usd` for the key, blocks budget-aware or fixed-estimate calls that
    exceed the remaining key budget, denies metered remote tools that lack a
    deterministic estimate, injects remaining budget into tools that accept a
    budget argument when callers omit it, and records successful response costs
    back to the remote audit log. Canonical cost-ledger `key_id`
    plumbing is still a deeper cost-session integration follow-up.
  - `rate_limit`: optional calls-per-minute ceiling. The HTTP transport counts
    recent audited calls for the authenticated key, blocks over-limit calls
    before tool dispatch, returns retry metadata, and audits the denial.
- `max_concurrency`: process-level HTTP POST ceiling. The transport rejects
  excess concurrent requests with 429 and retry metadata before reading or
  dispatching tool work. Operators can set `DEEPR_MCP_HTTP_MAX_CONCURRENCY` or
  `deepr mcp serve --http --max-concurrency`; default is 32.
- Keys are hashed at rest with a salted one-way KDF. The key CLI shows each
  secret once at mint (`deepr mcp keys create --mode read_only --budget 5`),
  supports revocation (`keys revoke`), and lists last-used timestamps.
- OAuth/OIDC deferred to team features (Phase 5 proper) - the key model
  must not preclude it (auth is a middleware, not woven into dispatch).

### Hardening (minimum to expose at all)

- TLS required (terminate at a reverse proxy; document the nginx/Caddy
  shape rather than embedding TLS).
- Per-key rate limits are shipped as a transport-level calls-per-minute guard
  over audited remote tool calls. Global HTTP POST concurrency caps are shipped
  as a transport-level 429 guard.
- Request size limits; tool-call audit log `{key_id, tool, args_hash,
  cost, trace_id, timestamp}` - this doubles as the expert mutation audit
  log the architect review asked for, scoped to remote calls first.
- No credential, no public socket: the HTTP listener refuses public bind with
  neither an active scoped key nor the legacy shared-token fallback. Any
  experimental non-loopback use should use scoped keys, but this guard does not
  make hosted deployment a supported surface.

### Deployment shapes

1. Supported locally: `deepr mcp serve --http` on literal loopback, or the
   loopback-published `deploy/mcp-http/` container with scoped keys and durable
   local data.
2. Reference-only: Caddy/nginx public exposure plus Azure, AWS, GCP, and
   Cloudflare shapes. These files are mechanically inert, are not exercised
   against cloud accounts, and provide no ledger-bound guarantee for compute,
   storage, network, logging, gateway, or egress charges.
3. Hosted-by-Deepr SaaS is explicitly out of scope (non-goal: no SLA).

## Order of operations

1. Versioned handoff payloads for downstream consumers, callable locally through
   MCP and the dashboard API. Shipped as `deepr-expert-handoff-v1`.
2. HTTP transport on the existing server. Loopback use is supported and ships
   as `deepr mcp serve --http`; a credential-gated reachable bind exists as
   substrate but is not a hosted-support claim.
3. Key store + middleware (mode scoping reuses the allowlist; budget uses
   audited remote cost attribution plus deterministic estimates). Key store,
   mode/expert middleware, fail-closed metered-tool estimate coverage, and the
   transport budget guard are shipped.
4. Audit log + rate limits + concurrency caps + size caps. Audit log, per-key
   rate limits, global HTTP POST concurrency caps, and size caps are shipped.
5. Local deployment guide and loopback container. Shipped. Public reverse-proxy
   and cloud files remain unsupported reference material.
6. Independent outbound cost authority, then platform smoke tests with one real
   host. Neither is shipped. `smoke-http`, URL-based `validate-consult`, and
   both managed and URL-based `validate-conversation` must remain blocked until
   that authority exists. Local registration manifests are descriptive only.

## Open questions

- Streaming long research jobs over SSE vs returning job IDs for poll
  (lean: job IDs + `deepr_check_status`, matching the async-first MCP
  design already shipped).
- Whether per-key budgets refresh monthly (lean: yes, calendar-month,
  mirroring plan-quota windows).

## Exit criteria

Future hosted support exits design only when a cloud-hosted agent with no
filesystem access completes consult and sync round-trips against a TLS endpoint
using a scoped key, a READ_ONLY key provably cannot mutate, every remote call
appears in both required audit and cost authority records, revocation takes
effect without restart, and the deployment's external service costs are bounded
independently of provider self-report. None of these hosted exit criteria is
currently claimed.
