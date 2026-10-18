# First-run inspection and output parity

Status: implementation, 2026-10-17. Issues #237, #232 and #233.

The installed CLI reproduces three gaps: capacity inspection creates a local
quota lock, setup inspection has no JSON form, and research previews disable
web search without explaining the existing admission boundary. Repair these
at their owning seams without widening execution or moving runtime data.

## Contracts

Research preview carries the effective web-search setting and its reason in
both human and JSON output. Reasons distinguish an explicit disable, unbounded
provider tool spend, unknown model context and a context exceeding the reserved
input ceiling. The existing admission predicate remains authoritative. A quoted
request is not execution authority or proof of live research.

Quota inspection creates neither directories nor lock files. Writers retain
interprocess locking, idempotency and durability. Readers take a byte snapshot;
an unfinished final record refuses inspection rather than presenting an older
quota observation as current. Missing ledgers remain empty. Existing complete
malformed-record compatibility is unchanged. The default runtime root stays
unchanged; the banner's intentional seen marker moves to the existing per-user
state directory, with explicit state-directory overrides preserved.

Doctor collects one result and presents equivalent JSON and human views, with
progress on stderr. Its summary separates configuration counts from observed
local capacity proof; absent or skipped proof cannot imply executable capacity.
Optional detail can be requested with --all. No model generation or external
provider request is added. Expert inventory similarly uses one stored snapshot
for both views. Consultation refusals retain their exit codes and expose code,
category, retryability and an actionable hint in JSON, using the existing error
classification fields rather than parsing exception prose.

## Verification and alternatives

Reproduce the installed failures in isolated directories. Add tests for empty
and populated read paths, partial concurrent append refusal, unchanged writer
locking, per-user banner placement, human/JSON count parity and keyless local
refusals. Preview tests assert the reason follows the effective tool posture
without changing dispatch eligibility. Run the existing strict islands and full
release gates. There is no codegraph in this checkout; trace source callers and
tests directly. Do not migrate runtime roots, add dependencies, rewrite the
ledger, infer readiness from credentials, or enable a tool to improve the copy.
