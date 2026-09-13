# MCP compatibility evidence

Checked September 13, 2026 against official MCP specification, schema, release,
and SDK sources. Scope: Deepr's declared server protocol and structural client
surface. No model, provider, credential, or paid inference operation was used.

## Current revision and scope

The latest official revision verified in this review is `2026-07-28`, released
July 28, 2026. The official release announcement identifies the stateless core,
per-request metadata, routing headers, cacheable lists, and separate extension
framework. A stale GitHub release-page excerpt still showed the earlier release
candidate; it was not used to override the final specification and dated GA
announcement.
[Official GA announcement](https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/blog/content/posts/2026-07-28-spec-ga/index.md),
[final changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog).

Deepr declares modern `2026-07-28` and legacy `2025-06-18`, `2025-03-26`, and
`2024-11-05`. It does not declare `2025-11-25`. An unsupported legacy request
can negotiate an earlier mutually supported version; omitting a revision from
the support list is not itself a protocol violation. The final versioning
contract permits dual-era servers and per-request modern operation.
[Versioning and compatibility](https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/docs/specification/2026-07-28/basic/versioning.mdx).

Modern Tasks and Apps are optional extensions, not obligations to grant task
execution, remote control, or user-interface authority. Deepr's lack of MRTR
input requests likewise does not prevent its ordinary complete-result methods
from working. Its outbound client remains a documented legacy structural
client, not a fully general modern client. SDK migration documentation should
not be read as evidence that every host has migrated.
[Final changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog),
[official TypeScript SDK migration](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28).

## Implementation checked

| Area | Current evidence |
| --- | --- |
| Modern negotiation | `protocol_modern.py` requires the current version and an object-valued client-capabilities envelope; unsupported versions use `-32022` and the supported/requested data shape |
| Discovery and results | `server/discover` exists; completed modern results include `resultType`, server identity under `_meta`, and cache fields on the supported cacheable methods |
| HTTP routing metadata | `http_validation.py` matches protocol version, method, and named-method header values to the body; includes Base64 sentinel decoding |
| Origin and isolation | HTTP checks Origin before authentication/dispatch; scoped resource reads remain identity-aware; resource responses have private cache scope |
| Subscriptions | `subscriptions/listen` replaces modern legacy subscription methods, acknowledges the honored filter first, tags notifications by original request id, and has bounded registration/queue behavior |
| Capability honesty | No logging, Tasks, or MRTR capability is newly advertised by this change; paid/provider and remote authority remain gated |

These observations match the relevant final requirements for request routing,
complete results, caching, and subscription correlation. They are bounded code
and test evidence, not certification of every host and transport combination.
[Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http),
[result envelopes](https://modelcontextprotocol.io/specification/2026-07-28/basic/index),
[caching](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching),
[subscriptions](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions).

## Confirmed defect corrected: legacy ping

Before this correction, `protocol_dispatch.method_handlers()` omitted `ping`.
An otherwise successful legacy initialization could be followed by a
method-not-found reply to a host's health probe. The legacy specification says
the receiver must respond with an empty result; the modern revision removes
the method. A shared legacy-only handler now returns `{}` without consulting
application state. Modern requests still receive method-not-found, with HTTP
404. Both transports register the shared table.
[Legacy ping requirements](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/ping),
[modern removal](https://modelcontextprotocol.io/specification/2026-07-28/changelog).

The [design note](../design/mcp-legacy-ping-compatibility.md) explains the
boundary and rejected alternatives. Regression tests initialize every declared
legacy revision, accept `notifications/initialized`, and check an exact ping
response with the original integer request id over both transport handlers.
They also assert that no application mock was used. Modern rejection is part
of the existing removed-method test matrix.

## Confirmed request-boundary defects corrected

Read-only probes used mock requests and application state without starting a
transport, event loop, provider, or model. Shared envelope validation now
protects both raw transport boundaries and direct server handlers before
application work.

| Input | Behavior before correction | Corrected behavior |
| --- | --- | --- |
| HTTP JSON body `[]` or `1` | HTTP 500, JSON-RPC `-32603`, from calling `.get()` on a non-object in `HttpMessage.from_dict` | HTTP 400 with invalid-request `-32600`, before handler invocation |
| Request with `jsonrpc: "1.0"` and otherwise valid modern discovery fields | Handler returns a successful discovery result | Invalid-request `-32600` |
| Request with `id: true` and valid modern discovery fields | Handler returns success with boolean response id | Invalid-request `-32600`; boolean id is never echoed as a valid id |
| Invalid UTF-8 body or stdio line | HTTP internal error or unanswered stdio line | Parse error `-32700`, with HTTP 400 |

The validator distinguishes an absent notification id from an invalid explicit
null request id, validates method and params types, preserves unknown extension
fields, and rejects mixed request/result/error envelopes. Valid notifications
and response messages do not invoke request work. HTTP preserves legacy
uncorrelated `id: null` errors and omits an unreadable id for recognizable
modern requests. Legacy incoming uncorrelated errors remain accepted. These
are shape checks, not semantic decisions or broader execution authority.
[Official message contract](https://modelcontextprotocol.io/specification/2026-07-28/basic/index),
[immutable schema](https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/cbd57657ec769b942263a5251afc05959fc4ce58/schema/2026-07-28/schema.json).

## Standards evidence and verification limits

The MCP pin in `docs/standards/pins.json` identifies immutable upstream commit
`cbd57657ec769b942263a5251afc05959fc4ce58`. During this review, its public
schema was fetched directly and independently checked: 181,474 bytes, SHA-256
`ef70b61f99b6d2e5e3b46863822eab08dff6a45bedc7a08914e0e5b133f40203`.
Both match the stored pin.
[Pinned official schema](https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/cbd57657ec769b942263a5251afc05959fc4ce58/schema/2026-07-28/schema.json).

The repository's offline MCP pin test currently verifies the declared version,
status, immutable URL relationship, and digest-string length. It does not
recompute the upstream schema digest or validate every wire artifact against
that schema. The schema is not vendored locally. The offline conformance report
is therefore a useful bounded check of Deepr contracts, not comprehensive
external-schema or live-host conformance. This review did not add a large
vendored schema or a network dependency to unit tests.

Focused checks used `.venv/Scripts/python.exe` and the existing socket guards:

- Protocol metadata, HTTP header validation, offline conformance, and standards
  pins: 60 tests passed in 13.58 seconds.
- Protocol dispatch, including new legacy ping and modern refusal regressions:
  20 tests passed in 12.80 seconds.
- Final envelope, dispatch, and modern HTTP regression set after all fixes:
  112 tests passed in 14.74 seconds.
- Independent review reproduced HTTP notifications reaching scoped admission.
  The transport now acknowledges non-requests before tool admission or
  accounting, after authentication and wire validation. Twelve new cases
  include the real read-only denial path; the 104-test HTTP regression set
  passed with the normal socket guard.
- Strict mypy passed all 81 MCP modules. Ruff lint passed; all seven changed
  source/test files passed format verification and `git diff --check`.

An entire MCP-directory run during development collected 1,527 tests and
reached 55 percent without an assertion failure, then hit its 30-second
fixture timeout while constructing a Windows Proactor event loop. The stack
ended in `socket.socketpair()` and `lsock.accept()` before the next test body
in `test_server_tool_methods.py`. This reproduces the environment hang seen
elsewhere in the session. The final focused run above completed successfully.
No socket protection was removed.

These runs used `--no-cov` for focused verification. They do not establish the
full-suite coverage threshold or hosted CI status. Installed subprocess
exchanges and the complete release gates are recorded separately in the
[verification record](../validation/research-review-2026-09-13.md).
