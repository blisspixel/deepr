# Prepared consultation (S1) contract

Status: proposed design, 2026-09-24; boundary review 2026-10-22;
first-slice contract refined 2026-10-25.
The packet below is not implemented.
`deepr expert currency` is the earlier read-only inspection. It does not
fetch, judge, or replace stored-only consult. This note defines
the additive contract the [delivery plan](../plans/living-expertise.md#s1-prepare-before-consultation-with-bounded-temporary-evidence)
requires before S1 code. Prototypes wait for the frozen S0 protocol; the
default-on switch waits for S1's own exit evidence.
The operator selected independent model review for the next protocol and
answer review. Record that review and its calibration honestly, including
disagreement and shared-model limitations; do not record human attestations
that did not occur. This changes neither the code gate nor the evidence
needed to claim useful advice or improved expertise.

## Problem

Consultation today is stored-only. `consult_prompt.brief_synthesis_blocks`
opens with "Stored research only; no live check was performed" and
`synthesis_delivery` reports `freshness: stored_context_only`. Fresh context
exists only inside `expert sync --fresh-context`, which mutates the expert
through absorption. A caller asking a version-sensitive question therefore
gets the expert's last study, with honest disclosure but no current check.

## Where it plugs in

CLI `expert consult` and MCP `deepr_consult_experts` already share
`execute_consult_transaction`. Preparation runs there, before `run_consult`,
so both surfaces get identical behavior. Its output is one frozen packet that
`build_briefed_perspective` and `build_consult_context` receive as an extra
evidence layer, and that replaces the stored-only block with a dated
disclosure. Temporary sources live in an operation-scoped
`CorpusStore(storage_dir=...)`, never the canonical corpus.

The concrete transaction hook is inside
`consult_transaction._run_inside_deadline`, after `_construct_backend` proves
owned local capacity and before `_run_generation` invokes `run_consult`.
Preparation shares that transaction's deadline, cancellation, lifecycle and
trace identity. CLI and MCP supply the same validated preparation request;
neither interface acquires sources or calls `sync --fresh-context` itself.

## Flow and authority

1. **Scope** (code): question, caller identity, declared environment (for
   Python: interpreter version, platform, lockfile digest), information date,
   limits.
2. **Assumptions** (model): list the claims the answer would rest on and judge
   which need current evidence and why. The model owns this meaning; code
   validates the list's shape and caps its length. No keyword list decides it.
3. **Acquire** (code): for each checked assumption, fetch from the allowlisted
   source class for its kind, within source, byte, call, elapsed-time and
   capacity limits. Every attempt, including failures, consumes allowance.
4. **Study** (model): relate observations to stored positions; record
   conflicts as dated pairs (stored view, current observation), never as a
   silent override.
5. **Freeze** (code): write the packet, then answer from expert revision plus
   packet. Nothing canonical changes; proposals for learning are staged only.

### Acquisition and privacy admission

Reuse the peer-pinned HTTP transport, not a second networking stack. Generic
scrape defaults are not a preparation budget: they include retries and archive
fallback, while pinned HTTP can attempt multiple resolved addresses. One
operation owns the deadline and cumulative request, source and decoded-byte
allowances across every redirect, retry, address attempt and response stream.
Do not reset limits on cache revalidation or cancellation. Disable archive and
browser fallback for authoritative version/advisory checks. Revalidate allowed
origins and public destination addresses before each hop, keep environment
proxies and ambient authentication disabled, and retain structured failure
receipts without secret-bearing URLs or response content in logs.

Public requests disclose only explicitly admitted package/version coordinates.
Do not transmit private questions, source text, full lockfiles, paths or caller
credentials to a metadata/advisory endpoint. Operation storage must have an
owner, path-safe identity, restrictive permissions, a declared retention and
cleanup policy, and a receipt for expired or cancelled work. A matching question
hash never grants another caller access. Define these contracts before private
packet caching, then test cross-caller reads as well as reuse refusal.

Canonical profile, beliefs, corpus, graph and revision history are invariant.
Existing consultation lifecycle, trace and cost receipts plus operation-local
packets are intentional writes, stored separately. Acceptance hashes that
explicit canonical inventory; it must not disable durable observability to
make a whole-directory equality assertion pass. Retrieved prose is evidence,
never permission to add tools, destinations, spend or canonical writes.

## Packet (`deepr-prepared-context-v1`, proposed)

| Field | Meaning |
| --- | --- |
| `operation_id`, `caller_scope` | Identity; packets with private task context bind to one caller |
| `expert_revision` | Digest of the stored state the answer also uses |
| `question_sha256`, `environment` | What was prepared for |
| `assumptions[]` | Text, `checked` / `unchecked` / `not_needed` with the model's reason |
| `observations[]` | URL, request time, response `Date`, `Last-Modified`, ETag, SHA-256 of bytes, applicable version scope, status `ok` / `revalidated` / `failed` / `offline` |
| `conflicts[]` | Stored position id, current observation id, dated note |
| `implications[]` | Guidance affected, each linked to observations |
| `stop_reason`, `limits`, `attempts` | Complete / partial / failed / cancelled and why |
| `review_markdown_sha256`, `graph_sha256` | The dated Markdown review and graph projection, both rebuildable from this packet |

"No change found", "check failed" and "not examined" are distinct values.
A timestamp, empty search result or unchanged hash alone never yields
"current".

## Reuse

Reuse a packet only when caller scope, question assumption set, environment
digest and source set all match and every observation is within its class's
staleness allowance; otherwise revalidate with `If-None-Match` or
`If-Modified-Since`. A 304 records a new observation time without new bytes. A
changed hash triggers re-study of the affected assumption, not automatic
invalidation of the answer. Identical concurrent requests share one operation;
retries do not create fresh allowances.

The first slice below admits no completed-packet cache reuse. Replay returns
an owner-checked duplicate/conflict result without dispatch or a reset.
The broader reuse contract above is deferred. A later implementation must
count 304s, redirects and address attempts against the same operation policy;
it cannot silently gain a fresh request or time allowance.

## Source-class sequence (Python exemplar)

Structured, keyless sources documented 2026-09-24 and rechecked against official
documentation 2026-10-22, before any general web search: release-specific PyPI
JSON and the Index API for versions and yanks; OSV.dev
query and querybatch for advisories affecting pinned versions;
`peps.python.org/api/release-cycle.json` for interpreter support status.
GitHub's unauthenticated advisory API (60 requests per hour) and
endoflife.date are corroboration only. Official changelogs and "What's New"
pages are an allowlisted second tier through the existing pinned HTTP
transport. Do not depend on PyPI's deprecated project `releases` key, or treat
project-latest vulnerability metadata as a check of the caller's pinned release.
OSV documents no current API rate limit; this never removes Deepr's own request,
response-size or elapsed-time bounds. These documentation checks are not an
implemented live-source smoke. Details and limits:
[practice review](../research/s0-s1-practice-2026-09-24.md#reassessment-2026-10-22).
SearXNG stays blocked under the current capacity policy.

The first implementation is limited to the PyPI release JSON and JSON Index
API. OSV, interpreter support data, advisory corroboration, changelogs and
general search remain separate work. A version lookup does not establish
advisory coverage, interpreter support, or version-dependent API behavior.

## First opt-in slice: one Python environment

Everything in this section is an implementation contract, not shipped
behavior. Do not begin code until the replacement S0 protocol is frozen.
An unfavorable S0 result does not block this S1 prototype, and the prototype
does not change S0's interpretation.

### Admission and interface shape

Require one explicitly named, formed expert, local synthesis, and one declared
Python environment. Do not auto-select an expert, switch models, install a
model, infer the caller's installed environment, or route preparation to a
plan or metered backend. Existing stored-only consultation remains the
default and retains its current request/output behavior.

Proposed additive input is a `preparation` object containing:

- `enabled: true`, `schema_version: deepr-python-preparation-request-v1`;
- `request_id`: a caller-chosen opaque idempotency key, 16-64 ASCII letters,
  digits, underscores or hyphens; it is not an owner, path or credential;
- `environment`: explicit interpreter version, platform label and optional
  caller-supplied lockfile SHA-256, with the declaration distinguished from
  an environment that Deepr inspected;
- `packages`: one to three explicit `{name, version}` coordinates. Names are
  normalized using the existing packaging conventions; versions must be
  concrete versions, not ranges, URLs, paths or editable requirements.

The object contains no caller identity, packet path, endpoint override, full
lockfile, source text or credentials. The model may choose a subset of these
coordinates for checking. It may not invent a package or version to transmit
private task text through a public URL. Duplicate normalized coordinates are
coalesced before allowance reservation; contradictory declarations are refused.
Parsing names and versions guards request form, not relevance or correctness.
The complete input JSON is at most 16 KiB, the question at most 4,000
characters, platform label 128, package name 200 and version 128 characters.
Reject extra fields and invalid types before backend or acquisition work.
Bound assumptions to six records with 512-character reasons and exact admitted
coordinate IDs. Retained header projections are at most 8 KiB; bounded IPC
frames include their encoding overhead. Existing HTTP parser header limits
must be checked against the locked runtime, not described as body allowance.

CLI adds one `--prepare-environment PATH` option that reads this bounded JSON
object locally and explicitly discloses the outgoing package/version
coordinates. MCP accepts the equivalent object on `deepr_consult_experts`.
Both reach `execute_consult_transaction`; a supplied object with disabled,
missing or malformed admission is refused rather than ignored. Packet reads
are service-owned operations, not arbitrary filesystem reads or new public
MCP resources. Update input schemas, help, protocol fixtures and clean-wheel
stdio checks together. Do not add a new tool or expose a network fallback.

### One cumulative allowance

These proposed conservative ceilings apply to an entire preparation operation:

| Resource | Initial ceiling and accounting |
| --- | --- |
| Admitted packages | Three normalized name/version coordinates |
| Public source requests | Six attempts total, at most one release JSON and one JSON index request per selected package |
| Retained source responses | Six, including failed or partial observations |
| Response body | 1 MiB per source; 2 MiB cumulative decoded bytes, counting partial bytes before a failure |
| Acquisition elapsed | 30 seconds total, including DNS, address attempts, headers and streaming |
| Preparation model calls | Two total: assumptions and interpretation; failures and cancellation consume their attempted slot |
| Preparation model output | 1,024 tokens per call; truncated or malformed output is retained as a typed failure, never silently repaired by another call |
| Preparation model input | 32,768 rendered characters per call, including instructions, retained context and source projections; omit whole non-fitting fields/blocks with named omissions rather than silently dropping qualifications |
| Model-call elapsed | 90 seconds per call, additionally bounded by remaining preparation and transaction time |
| Cancellable preparation elapsed | 210 seconds total, additionally bounded by the outer consult deadline |

The outer transaction may impose a tighter bound. Durable accounting and
terminal writes follow its existing awaited-finalization contract; a
cancelled filesystem write is not assumed absent. Public acquisition counters
are separate from local runtime preflight and generation receipts. Report
those local checks and all native attempts as overhead too.
The character ceiling is not an exact tokenizer proof. Use the native context
window and retain truncation or refusal; do not claim that a source retained
outside the delivered projection was read by the model.

An operation never resets these counters on retry, waiting, cancellation or
duplicate acquisition. Exhaustion records a terminal or partial packet and a
specific stop reason. It does not increase a limit, replace an input, attempt
another source class or claim that the checks completed. Inspect representative
PyPI fixtures and local model capacity before freezing these proposed defaults;
an inadequate bound is a measured limitation requiring a new prospective
policy, not an in-run adjustment.

### Fixed acquisition process

Use a fixed, Windows-safe trusted acquisition subprocess whose implementation
invokes no model, tool or child process. This is deadline/cancellation
containment, not an OS sandbox or a claim that arbitrary hostile Python code
lacks filesystem or process authority. It reuses `utils.pinned_http.pinned_get` and
`close_pinned_response`; it does not instantiate another networking stack or
reuse the generic scraper. Its input contains only admitted coordinates,
source policy, numerical allowances and opaque operation identity. No private
question, local path, lockfile, credential or model-generated source URL is
sent to PyPI. Do not pass credentials or dotenv loading to this process.

The initial endpoint templates are HTTPS on `pypi.org` only: a normalized
project's release-specific JSON path and its JSON Simple Index path. Request
the JSON media type appropriate to each endpoint. Artifact download URLs in
the response are data, never authorization to fetch an artifact. Recheck the
official endpoint/media-type contract before implementation or a live smoke;
the 2026-10-25 refinement itself made no live-source request.

Set `allow_redirects=False`, `address_failover=False`, zero application retries
and `Accept-Encoding: identity`. Reject redirects, unexpected content encoding
and non-JSON content with a structured observation. No browser, archive,
mirror, compression or general-search fallback is admitted. Preserve TLS-name
verification, safe public address resolution, and disabled environment proxies
and ambient authentication. A failure of the selected first address consumes
one attempt and does not advance through the remaining DNS answers.

The child emits a request intent and waits. Only after the parent durably
reserves the attempt and acknowledges it may the child send that request.
Each acknowledged intent is charged even when dispatch becomes ambiguous.
The parent owns one monotonic acquisition deadline, bounds streamed IPC and
body sizes, and terminates and awaits the child on expiry or cancellation.
It records returned bytes and outstanding intents before finalization. No
orphan downloader may continue after a cancelled consult. Reject an operation
if its durable intent cannot be recorded.

Blocking DNS and slow streaming must be tested through this process boundary.
`asyncio.to_thread` plus a Requests idle timeout alone cannot enforce this
contract. A source that sends small chunks forever still exhausts the one
elapsed allowance. Unexpected compression is refused before decoding, so a
decompressor cannot allocate beyond the byte counter before the caller sees
the output. Cancellation, worker exit and malformed IPC retain distinct
receipts without response bodies or private details in diagnostic logs.

### Source identity and temporary storage

Retain exact response bytes under their raw SHA-256 and preserve their
observation time, request identity, HTTP status and relevant date/validator
headers. Parse a separate bounded representation. Verify that returned package
and version identities match the requested coordinates; malformed or partial
metadata is not an empty successful source. File-level yanks and incomplete
index coverage remain explicit. Conflicting metadata is delivered for model
interpretation, not resolved by a newest-date or keyword rule.
Release JSON binds the requested package and version. The project-wide index
binds its requested project, API/media type and selected file/version records;
it does not independently assert one release identity. A missing index record
does not prove absence or lack of a yank. Accept documented JSON index 1.x
schema forms and refuse an unknown major; retain the observed minor version
and unavailable fields. An empty-string yank reason still marks a yank.

An operation-local `CorpusStore` receives explicit `storage_dir` and bounded
source text for existing context machinery. Its text hash normalizes newlines;
record it separately from the raw response hash. Never claim the normalized
corpus text is the exact wire bytes. No call in this path omits `storage_dir`,
absorbs findings, marks a canonical source superseded, or promotes a brief.
Raw bytes, corpus text and packet projections must cross-link by exact IDs.

Use the configured runtime data root, with opaque owner and operation directory
names generated by the service. Reject symlinks, reparse points, path traversal
and caller-supplied storage locations before private reads or writes. Use the
existing atomic-file and durable-append seams. Do not add a database or copy
the expert persistence implementation.

### Caller ownership, reuse and expiry

Derive identity at the interface boundary and validate it in the shared service:

- CLI uses the actual operating-system principal in a local operator namespace;
  do not derive authority from a username environment variable.
- HTTP MCP requires an authenticated scoped key and uses the server-derived
  `MCPRequestIdentity` owner. Reject shared-token and unauthenticated requests
  for this private preparation surface, including shared tokens on loopback.
- Stdio MCP uses the OS principal plus a server-owned process nonce. The
  existing constant `mcp:stdio:local-v1` is not a per-client identity and cannot
  authorize private cache reuse across server processes. Do not accept a
  caller-supplied nonce or owner ID.

One credential represents one principal. Hosts sharing that credential are
not isolated from each other by this contract. The local operator retains
operator authority; packet ownership separates authenticated remote callers,
not hostile code executing as the same OS account.

Before the first private write, establish a restrictive owner-only directory
and verify its protection. On Windows, use an actual ACL for the current token
principal and fail closed if that protection cannot be established; POSIX mode
bits alone are not a Windows ACL. On POSIX, require owner-only directory/file
permissions. Do not write a question, model output, private packet or extended
trace payload into an unprotected staging directory while attempting to repair
permissions afterward.
Create a fresh opaque staging root with no private contents, then protect and
verify it before any private child or tempfile is created. Windows uses the
current token SID, protected inheritance and explicit full-control ACEs only
for that principal and SYSTEM. POSIX requires the current UID and mode 0700
for directories/0600 for files. Nested directories, locks and atomic tempfiles
inherit the protected parent. Reject preexisting unexpected entries and
reparse/link ancestors under the operation lock; do not claim this defeats an
arbitrary privileged same-account filesystem attacker.

An operation claim binds exact owner scope and request_id to the question,
environment, captured expert revision, admitted coordinates, policy and model.
Use the existing cross-process lock to admit that claim once. A concurrent or
completed duplicate returns an owner-checked typed duplicate result and opaque
receipt reference without dispatch. A changed input under the same key is a
conflict. Retain consumed allowance and terminal status for failed, cancelled
and ambiguous work. Do not silently allocate a new key for a retry. A caller
may explicitly choose a new request_id for a new operation; report it as new
work. No private-packet cache lookup, result sharing, conditional revalidation
or cross-process stdio reuse ships in this slice. Identical question text alone
provides no access or fresh allowance.

Private bodies, source bytes and projections have a seven-day access TTL.
Expiry denies service reads and reuse before cleanup. Cleanup records a
tombstone with owner binding, operation/packet hashes, prior terminal status,
expiry and confirmed deletion outcome, without private prose. Reclamation is
bounded and opportunistic at service access; the TTL is an access cutoff, not
a promise of wall-clock deletion while the process is stopped. A cleanup
failure leaves access denied and records `cleanup_failed` or `cleanup_pending`;
it must not claim bytes were removed. Minimal append-only lifecycle and cost
receipts remain. Do not reconstruct expired content from a trace or derived
Markdown view, and test every such read path against the same owner and TTL.
Long-lived shared journals receive preparation hashes and owner-bound references,
not a second private packet or preparation prompt body. Keep the exact prompts
and extended delivery context in the protected operation store under its TTL.
Copying a full prepared prompt into an append-only global trace would defeat
that retention policy; the opt-in trace adapter must preserve exact hashes and
references without creating that second body.
Use a strict opt-in global-trace allowlist, including every nested payload,
result, perspective, context and failure path. Global records retain only
schema/status codes, content hashes, numeric resources, owner-bound opaque
references and typed failure codes. Questions, final answers, perspective
prose, implications, raw errors and exact messages remain solely in the
protected operation store and the authorized caller's returned artifact.
Trace readers must report protected or expired content as unavailable, never
as an empty successful answer. Existing opt-out trace behavior is unchanged.

### Model, packet and delivery bindings

The assumptions call receives the question, declared environment, admitted
coordinates and relevant retained perspective. It names assumptions, marks
which admitted checks could matter, and explains unavailable or unnecessary
checks. The interpretation call receives those assumptions plus retained
observations and distinguishes observations, hypotheses, recommendations,
conflicts, implications and omissions. Model outputs cannot widen the
admitted coordinates, destinations, limits, spend or writes. Source text is
untrusted evidence, not an instruction to change those permissions.

Both calls use the selected native local backend, with pre-dispatch owned-local
proof and canonical attempt accounting. Do not use an unrecorded model client,
silent repair call, output clipping or paid fallback. A changed model identity
refuses the operation. Extend lifecycle work bounds and phase/progress representation
to include these two calls before the first preparation dispatch; the current
roster-plus-one council count cannot silently stand for extra work. Preserve
the existing one-synthesis-call limit and record preparation overhead separately.
Set the transaction's work-started state before the first preparation dispatch
or durable acquisition intent. Subsequent deadline, cancellation or storage
failures must retain consumed authority and must not advertise a safe automatic
retry. Regress this transition before council generation, where the current
transaction first marks provider work started.

Freeze one packet containing the request/owner/operation identities, expert
revision, model/policy identities, assumptions, raw and corpus source hashes,
applicable versions, observation times, checks and omissions, conflicts,
implications, limits, attempt outcomes and stop reason. Its freshness scope is
`pypi_release_and_index_only`; advisory coverage, interpreter support and API
behavior remain `unchecked` unless a later admitted source class checks them.
Retain and expose any applicable adverse metadata returned by an admitted
release response, including reported vulnerabilities. Partial advisory metadata
does not establish complete coverage, and an empty field does not establish
absence of vulnerabilities. Source-scope notices must not suppress positive
evidence already acquired.
An unchanged response hash is not a semantic no-change verdict.

Use non-circular hash ordering: canonical preparation content excludes its own
hash and derived hashes; hash that content, render Markdown and a small graph
from it, then hash those bytes and freeze a separate projection manifest.
Final message and answer receipts are later append-only operation records
binding this frozen content/manifest, never fields fed back into its hash.
Keep raw-body, normalized corpus, parsed projection, rendered context and final
message hashes distinct. Observation links must resolve to retained bytes;
implication links record model interpretations rather than deterministic
entailment. Deliver the packet as an extra layer through
`run_consult`, `ExpertCouncil`, `build_briefed_perspective` and
`build_consult_context`, including every admitted fallback path.
The first formed-expert admission avoids manufacturing useful expert state
for an expert that has never been built.
Preparation is a mandatory independent source layer even if no stored
perspective has positive packing confidence. Report that absence; do not
increase confidence to force an expert's inclusion. Refuse before synthesis
if the mandatory notice and its binding cannot fit.

`brief_synthesis_blocks` and `build_synthesis_packet` must reserve and account
for the preparation notice and bounded evidence, with exact delivered and
omitted observation IDs. `synthesis_delivery` binds packet hash, operation ID,
rendered context hash, source hashes and omissions to the actual final messages.
It retains `stored_context_only` for opt-out calls and describes complete,
partial, failed and offline preparation accurately for opt-in calls.
The final payload, trace and caller-visible Markdown use those same bindings.
Do not replace the notice with a generic claim that the expert is current.

No cache read, packet rendering, graph projection or final answer grants
canonical mutation authority. A proposed learning item remains a proposal.

### Canonical invariance and acceptance

Before preparation, freeze the explicit canonical inventory for the selected
expert: profile authority, beliefs and their durable event/snapshot/mutation
history, retained corpus bytes/index, study, current brief and position history,
canonical evidence/perspective graph and existing expert revision records.
Resolve current and legacy study/brief paths through `expert_layout.part_in`
and expert identity through `experts.paths`, rather than guessing directories.
Hash relative paths and bytes, including recorded absences. Do not include the
separate operation corpus, packet, preparation projections, consultation
lifecycle, trace or cost receipts in the unchanged-canonical assertion.

Recheck the inventory before answer dispatch and after finalization. A changed
canonical revision is a typed identity failure, not a cache hit or permission
to answer under the old revision label. Retain the failed candidate and actual
delivered context; do not overwrite the expert or retry invisibly. Fixtures
must compare all inventory hashes, not just `beliefs.json` or one graph file.
Capture the exact formed study/brief/corpus bytes once before model work and
validate their existing study/source bindings. Use that immutable captured
context in assumptions, interpretation and final synthesis; do not reread a
different canonical perspective after acquisition. Require captured hashes to
match the checked inventory and refuse mismatched or unavailable formed-state
bindings. The revision identifies this input bundle, not a new universal
transaction revision across all expert stores. Before/after checks detect
observed drift; they do not prove absence of transient external writes or that
Deepr caused a concurrent writer's change. Stronger cross-store snapshot claims
require the owning writers' shared admission/locking contract first.

Start with the existing transaction, CLI/MCP, consult context/prompt, corpus
and pinned HTTP tests. Add fixture-backed coverage for changed releases,
file-level yanks, conflicting and incomplete metadata, misleading and sound
premises, source unavailability, slow streams and DNS, cancellation, worker
failure, duplicate callers, denied cross-owner reads, TTL expiry, traversal,
malicious source instructions and cleanup failure. Exhaust redirect, address,
request, byte and elapsed allowances without a fallback. Assert that network
requests contain only admitted coordinates and that intended receipts survive.

Verify packet/Markdown/graph/context agreement and exact CLI/MCP behavior under
matched fixture scope; random operation IDs and authenticated owners remain
distinct identities, not fields to forge for byte equality. Run strict types,
full unit/coverage, lint/format, ratchets, paid-boundary and docs checks. The
MCP shape change also requires existing protocol conformance and clean-wheel
stdio smoke evidence. Update `AGENTIC_BALANCE.md` when implementing the new
surface; this proposed contract does not move the shipped boundary itself.

Then conduct a matched preparation-on/off answer review from one fixed expert
revision and a bounded authorized live-source smoke. Use independent model
review under the operator-selected lane, freeze calibration and disagreement
handling first, preserve whole answers and failures, and disclose correlated
reviewer/model errors. Neither structural tests nor these bounded results
establish a longitudinal memory benefit. Default-on requires its own reviewed
usefulness evidence; S2-S4 remain separate gates.

### Choices still requiring implementation evidence

The numeric bounds and seven-day access TTL above are
prospective defaults to test, not measured sufficiency claims. Retain a failed
capacity or source-size probe rather than increasing them mid-operation. Before
the first private write, demonstrate the Windows ACL and process-termination
mechanisms with real isolated filesystem/process tests as well as injected
failures. Verify official PyPI schemas and content-type behavior before any
live request. None of these checks was executed by this design refinement.

## Acceptance evidence (from the delivery plan, made concrete)

The list below covers the broader staged S1 target. In the first PyPI-only
slice, advisory and interpreter-support fixtures must show explicit unchecked
coverage; they cannot pass by pretending the later source classes were used.

- CLI and MCP produce the same packet for the same inputs and fixtures.
- Offline fixtures cover: a new release that changes advice, a new advisory
  for a pinned version, a yanked version, similar APIs with version-dependent
  behavior, contradictory references, unreachable sources, timeout,
  cancellation, duplicate requests, and denied cross-caller reuse.
- Deliberately stale sources, mismatched dates, missing links and an
  unsupported "up to date" claim fail the consistency check between packet,
  Markdown, graph and delivered context.
- Canonical profile, beliefs, corpus, graph and revision history are
  byte-identical before and after; separate operation and lifecycle receipts
  remain durable. Adversarial fixtures cover cross-caller reads, path traversal,
  private query disclosure, malicious source instructions and cleanup failures.
- A separate paired preparation-on/off experiment from one expert revision,
  and a small dated live-source smoke. Neither is a longitudinal claim.

## Rejected alternatives

- **Running `sync --fresh-context` before consult:** mutates canonical state
  and is not scoped to the question.
- **General web search first:** unreproducible results and unprovable
  marginal cost; structured sources cover versions, advisories and support
  status authoritatively.
- **Confidence or recency as the trigger:** local text models expose no
  reliable internal signal, and file dates do not measure currency.
