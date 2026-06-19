# Design: Hosted MCP Endpoint (remote, authenticated Deepr)

Target: v2.18. Roadmap: Phase 5 (promoted from backlog 2026-06-11 -
"cloud-hosted autopilots cannot call a stdio server on a laptop").
Status: design, with the first versioned handoff contract shipped.

## Problem

Every June-2026 agent platform (Anthropic Managed Agents, Bedrock
AgentCore, Antigravity Managed Agents, OpenAI Workspace Agents, Microsoft
Autopilots) runs agents in *their* cloud. Deepr's MCP server is
stdio-only: reachable from a local Claude Code/Cursor, unreachable from
the platforms Deepr positions itself for. The architect panel seat called
this the single highest-leverage item: "the door to the party Deepr says
it's dressed for."

## Design

### Transport

Streamable HTTP (the current MCP spec transport, SSE for streaming) on the
existing 28-tool server - the tool surface, allowlist, and error model do
not change. stdio remains the local default; HTTP is an additional
listener (`deepr mcp --http :8400`), one process, same dispatch.

### Handoff contract

`deepr_expert_handoff` and `/api/experts/{name}/handoff` now provide the first
remote-friendly read contract: `deepr-expert-handoff-v1`. It is `$0`,
read-only, bounded by caller-provided limits, and generated from the shared
`build_expert_handoff` serializer so MCP and web responses cannot drift. The
payload includes profile summary, manifest counts, bounded claims/gaps,
dashboard telemetry, loop-status rollup, OKF interchange hints, and an additive
compatibility contract. Detailed expert state remains `SENSITIVE` in MCP
allowlists until scoped keys exist.

### Auth and scoping (API-key first, OAuth later)

- **Scoped API keys**, not one shared secret: each key carries
  `{key_id, mode, expert_allowlist, budget}`.
  - `mode`: maps to the existing `ResearchMode` tool allowlist
    (READ_ONLY keys cannot reach WRITE/EXECUTE/SENSITIVE tools - the
    enforcement layer already exists, keys just select it).
  - `expert_allowlist`: optional - a key scoped to specific experts.
  - `budget`: per-key spend ceiling, enforced through the existing
    CostSafetyManager session machinery (a key is a session); the
    canonical cost ledger records `key_id` on every event.
- Keys are hashed at rest (argon2), shown once at mint
  (`deepr mcp keys create --mode read-only --budget 5`), revocable
  (`keys revoke`), listed with last-used timestamps.
- OAuth/OIDC deferred to team features (Phase 5 proper) - the key model
  must not preclude it (auth is a middleware, not woven into dispatch).

### Hardening (minimum to expose at all)

- TLS required (terminate at a reverse proxy; document the nginx/Caddy
  shape rather than embedding TLS).
- Per-key rate limits (flask-limiter pattern already used by the portrait
  endpoint) + global concurrency cap.
- Request size limits; tool-call audit log `{key_id, tool, args_hash,
  cost, trace_id, timestamp}` - this doubles as the expert mutation audit
  log the architect review asked for, scoped to remote calls first.
- No key, no socket: the HTTP listener refuses to start with zero keys
  minted.

### Deployment shapes (documented, not productized)

1. Home-lab / VPS: `deepr mcp --http` behind Caddy with a key per agent
   platform.
2. The existing cloud templates gain an MCP service variant.
3. Hosted-by-Deepr SaaS is explicitly out of scope (non-goal: no SLA).

## Order of operations

1. Versioned handoff payloads for downstream consumers, callable locally through
   MCP and the dashboard API. Shipped as `deepr-expert-handoff-v1`.
2. HTTP transport on the existing server (no auth, loopback-only bind,
   integration-tested against a real MCP client).
3. Key store + middleware (mode scoping reuses the allowlist; budget
   reuses cost sessions) - the bulk of the new code, all unit-testable.
4. Audit log + rate limits + size caps.
5. `keys` CLI + docs + deployment guide; loopback restriction lifts only
   when a key exists.
6. Platform smoke tests: register the endpoint with one real host
   (Anthropic Managed Agents connector first) and run the
   subscribe -> sync -> what_changed loop remotely.

## Open questions

- Streaming long research jobs over SSE vs returning job IDs for poll
  (lean: job IDs + `deepr_check_status`, matching the async-first MCP
  design already shipped).
- Whether per-key budgets refresh monthly (lean: yes, calendar-month,
  mirroring plan-quota windows).

## Exit criteria

A cloud-hosted agent (no filesystem access to the machine) completes
expert consult + sync round-trips against a TLS endpoint using a scoped
key; a READ_ONLY key provably cannot mutate; every remote call appears in
the audit log with cost attribution; revocation takes effect without
restart.
