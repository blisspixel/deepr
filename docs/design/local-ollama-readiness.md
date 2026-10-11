# Local Ollama readiness and refusal reporting

Status: implementation repair for issue 202, 2026-10-11.

## Problem and decision

The local quick start detects installed models but cannot generate until the
Ollama daemon proves persistent cloud disablement. Formation currently starts
discovery before that proof, catches the refusal as a query fallback, and labels
later refused study calls as parse failures. Operators need the same actionable
capacity evidence before research and in diagnostics.

Reuse the capacity validators and native backend attestation. Expose a bounded,
read-only preflight through the resolved study backend. Shared CLI/dashboard
formation performs it before retaining seeds, proposing queries, searching,
accounting model attempts, or dispatching generation. A refused initial attempt
retains a small incomplete operation record, with stage `capacity`, and sends no
generation or unload request. Profile-only creation remains available.

Preflight is an observation, never cached execution authority. Every dispatch
continues to validate the owned loopback endpoint, persistent cloud-disabled
status, and exact materialized local model. No remote address, metered fallback,
provider credential, new dependency, or model-default authority is introduced.

## Error and observation contracts

A specific local-capacity refusal carries a bounded, secret-safe reason. Query
proposal propagates that refusal instead of silently selecting fallback search.
Study records a `capacity_refused` lens outcome, retains findings from earlier
lenses and successful chunks of the current lens, checkpoints, and stops. It
returns nonzero and does not promote incomplete material to a brief. Refused
outcomes cannot be reused as completed lenses on retry. Ordinary malformed model
answers retain the existing per-chunk recovery behavior.

Formation retains its existing `incomplete` top-level status and exposes the
capacity reason before generic stage validation. The frontend status union does
not change. Retry is explicit, holds the existing overlap lock, and revalidates
current capacity; earlier evidence stays inspectable. A later capacity refusal
also suppresses cleanup unload requests: cleanup uses a generation endpoint and
must not send another POST after known proof loss. Successful work still unloads.

Inventory keeps runtime presence distinct from generation readiness. Additive
local generation evidence reports ready, refused, or unverified, including the
cloud-disabled source and a safe reason. A ready preliminary observation does
not claim arbitrary workflow eligibility. Init, capacity human/JSON output, and
connected doctor consume the same observation. `doctor --skip-connectivity`
makes no provider HTTP request and explicitly reports local proof as unchecked;
its summary must not imply local execution is verified.

## Operator guidance and validation

Ollama reads `.ollama/server.json` from its daemon user's home. Preserve existing
JSON settings and set `"disable_ollama_cloud": true`, then restart that daemon.
The standard Linux service runs as `ollama`, with home `/usr/share/ollama`;
interactive `ollama serve` uses the interactive user's home. Environment-only
`OLLAMA_NO_CLOUD` is supported upstream but does not meet Deepr's existing
persistent-proof contract. A configured SSH local forward to owned hardware
can use an accepted loopback port; direct LAN endpoints remain refused.

Bounded offline regressions prove refusal before any research or generation,
honest diagnostics without hidden requests, exact-model and dispatch-time
revalidation, partial-evidence retention, nonzero JSON exits, and successful
controls. Existing lint, types, ratchets, paid-boundary and documentation gates
remain unchanged. This repairs deterministic workflow admission and reporting;
model judgment, semantic qualification, and autonomy do not change.

Primary sources checked against Ollama v0.33.3 and current v0.40.3:

- [Cloud configuration](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features)
- [Linux daemon user](https://docs.ollama.com/linux#adding-ollama-as-a-startup-service-recommended)
- [Config and source taxonomy](https://github.com/ollama/ollama/blob/eab97e9f92b9a25c2d52d2cc6c1b1c99bd9fae21/envconfig/config.go#L393)
- [Status response](https://github.com/ollama/ollama/blob/eab97e9f92b9a25c2d52d2cc6c1b1c99bd9fae21/server/routes.go#L2573)
