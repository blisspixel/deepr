# Legacy MCP ping compatibility

Status: accepted compatibility correction, September 13, 2026.

Deepr advertises the legacy MCP revisions `2025-06-18`, `2025-03-26`, and
`2024-11-05`, but its shared dispatch table has no `ping` handler. A host that
initializes successfully can subsequently receive method-not-found when
checking connection health.

The [2025-06-18 ping specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/ping)
requires a receiver to return an empty result promptly. The
[2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
removes `ping` from the modern core. The correction is therefore era-specific:
register an empty legacy handler in the shared method table and reject `ping`
alongside the existing legacy-only methods when a request carries modern
metadata. Both stdio and HTTP use that table.

The handler reads no expert or job state, creates no provider, opens no
network connection, and makes no durable write. It returns `{}` under legacy
semantics. Modern requests retain method-not-found, including HTTP 404.
Protocol dispatch remains deterministic form and control-flow handling; this
does not move the boundary defined in `AGENTIC_BALANCE.md`.

Implementing ping in each transport separately was rejected because it could
diverge across eras. Advertising an additional legacy revision or accepting
modern ping was rejected because neither is needed to correct the existing
support claim.

Regression checks initialize each advertised legacy version, accept the
initialized notification, and verify that ping returns the same request id
and an empty result. Modern ping must still be refused. The checks use stub
application state, require no model or credentials, and retain the unit
suite's network protections.

## Request-envelope correction

The same review reproduced invalid client messages reaching dispatch:
non-object HTTP bodies returned internal errors, and wrong JSON-RPC versions
and boolean ids could receive successful results. Add shared envelope
validation at both raw transport boundaries and at direct server-handler
entry points. Syntactically invalid JSON remains a parse error; valid JSON
that fails the MCP message shape is an invalid-request error before dispatch.

The [MCP message contract](https://modelcontextprotocol.io/specification/2026-07-28/basic/index)
requires JSON-RPC `2.0`, string methods, object params when present, and string
or integer request ids. An absent id means notification; an explicit null
request id is invalid. Unknown method names and additional extension fields
remain valid envelopes and follow normal method/capability negotiation.
Valid notifications remain response-free, and valid response messages do not
trigger request handlers. Legacy uncorrelated error responses can retain a
null id. HTTP preserves its existing `id: null` for uncorrelated legacy
errors; recognizable modern requests omit an unreadable id. Invalid UTF-8 is
a parse error on both transports, like malformed JSON, rather than an internal
error or a silently unanswered line. This is shape validation only and changes
no authentication or tool authority.
