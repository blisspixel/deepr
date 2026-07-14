# Changelog

All notable changes to Deepr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Plan-quota subprocesses now drain stdout and stderr concurrently under an
  independent 8 MiB raw-byte ceiling for each stream. Overflow kills and reaps
  the process tree, returns `output_limit_exceeded`, records unknown quota usage
  plus one paired `$0` cost event, and never promotes the bounded partial output
  or falls through to another backend. Timeout and cancellation cleanup remain
  bounded on Windows and Linux. Windows children enter a kill-on-close Job
  Object before they resume, Linux children run under a child-subreaper
  supervisor, and other POSIX platforms fail before launch when equivalent
  detached-descendant ownership is unavailable. Cleanup never
  re-buffers output through `communicate()`, closes transports on every terminal
  cleanup path, applies the elapsed deadline to launch, and surfaces uncertain
  Job Object cleanup as a typed failure. Windows handle closure has bounded
  retries; an unresolved handle remains in a durable in-process retry registry
  that blocks later launches. Cleanup uses stable process and Job Object handles,
  never a reusable PID. Linux reports launch,
  runtime, and cleanup status over a parent-only pipe; failed child enumeration
  and forced supervisor termination fail closed. Antigravity transcript dispatch
  and recovery are cross-process serialized and correlated with a unique
  per-attempt prompt nonce appended after the pre-dispatch byte offset. Snapshot
  work runs off the event loop under the operation deadline; root enumeration,
  changed candidates, actual bytes read, decoded answers, and line iteration are
  bounded under one 8 MiB operation ceiling. Lock release, late-launch cleanup,
  and launch-plus-cleanup uncertainty remain typed without masking cancellation.
  Research and probe failures preserve dispatch truth, attempt outcome, attempt
  id, paired-ledger status, and the no-metered-fallback contract, including
  canonical accounting failure after a successful vendor response.
- Metered expert-chat OpenAI and Anthropic completions and streams now run
  through shared durable reserve, dispatch-mark, and settlement wrappers when
  execution is enabled (`execute_reserved_async_call` /
  `execute_reserved_async_stream`). Streams settle final provider usage or
  consume the held ceiling conservatively when usage is missing. Quick lookup,
  follow-up, and compact paths pass explicit per-call ceilings. Grok
  standard-research samples use the same durable admission with the registry
  estimate as the hold when the SDK omits usage. Accounting-only request fields
  such as `max_cost_per_job` are stripped before provider params. Production
  remains fail-closed via `METERED_EXPERT_CHAT_EXECUTION_ENABLED = False` until
  deep-research job accounting, embeddings, skill tools, and session-hold
  contracts clear. Startup banner unit tests isolate dumb-terminal and
  `NO_COLOR` host environments so CI and agent shells do not false-fail the
  suite.

## [2.36.0] - 2026-07-12

### Added

- Consults now allocate their final trace id before cancellable setup and open
  an append-only `deepr-consult-lifecycle-event-v1` journal before backend
  construction or dispatch. The journal records bounded phase, ownership,
  logical-work, elapsed-time, capacity, spend, cancellation, and failure state
  without storing answers or private reasoning. Final consult traces remain the
  derived transaction artifact under the same id.
- Added `deepr eval deliberation`, an offline `$0`
  `deepr-deliberation-eval-v1` evaluator over eleven frozen structural cases.
  It checks lineage, independent first positions, targeted questions, dissent
  preservation, typed stops, call ceilings, proposal-only authority, inert
  adversarial text, and no-write/no-fallback boundaries. Semantic review stays
  `unreviewed`; no live multi-round CLI, MCP, or A2A surface is enabled.
- Published the lifecycle and deliberation evaluator schemas and registered
  exact `openai/gpt-4o-mini` pricing and context metadata. The documented
  registry snapshot now contains 56 models, including 39 active benchmarkable
  public text or research models.
- Published `deepr-recon-evidence-handoff-v1` with a frozen fixture for
  evidence-only Recon observations. The contract forbids belief-write authority
  and keeps inferred infrastructure relationships labeled as observations for
  later verification.

### Changed

- One-shot consults now use a 600-second cumulative elapsed ceiling by default,
  accept an explicit ceiling up to 21,600 seconds, and cap one canonical roster
  at 10 experts. Case and slug aliases resolve to one canonical identity;
  duplicate identities fail before dispatch.
- Consult lifecycle and final-trace storage run off the event loop, use bounded
  process-local and OS lock waits, and remain owned through cancellation.
  Cancellation never selects another backend. Retryability is limited to
  failures proven to occur before provider work or any possibly partial write.
- API council synthesis uses exact supported pricing, conservative token and
  context bounds, full reservation before dispatch, provider usage settlement,
  and canonical append-only cost events. OpenAI cached input is separated when
  reported; Anthropic uses native Messages usage without unsupported cache
  controls. Live metered perspective fallback remains gated when stored expert
  context is unavailable, even when metered synthesis itself was explicitly
  approved.
- Every standalone metered `ExpertChatSession` dispatch now fails closed before
  provider work. Local and explicit plan `deepr_query_expert` read-only turns
  remain available, and API council synthesis remains a separate bounded
  surface. The release gate is
  `METERED_EXPERT_CHAT_EXECUTION_ENABLED = False` and returns
  `metered_expert_chat_accounting_unavailable`. No metered expert-chat live
  validation was performed or claimed.
- Unsafe metered expert lifecycle entry points also fail closed in v2.36:
  nonlocal profile creation and `--learn`, API curriculum planning,
  provider-backed refresh and synthesis, resume, normal metered CLI and MCP
  reflection, API gap filling, explicit API sync and sync-all, paid portraits,
  API consult-quality judging, live provider benchmarks, and paid corpus
  calibration. Local, scheduled, dry-run, history-only, and explicit plan-quota
  paths where available, plus `$0` calibration from existing graded pairs, remain
  available.
- Direct research preview, reservation, queued metadata, provider payload, and
  settlement now share one finite request envelope covering input, output,
  provider-request, tool-call, and serialized-byte ceilings. Exact pricing and
  bounded OpenAI or Azure built-in tools remain usable; unknown pricing,
  unsupported bounds, Gemini managed Deep Research, Azure Foundry agents, xAI
  multi-agent fan-out, and unpriced tool loops fail before provider work.
- Hosted file upload, file search, vector-store creation or attachment,
  automatic cross-provider metered fallback, and metered batch, campaign, team,
  prepared campaign, continuation, and autonomous multi-round execution now
  fail closed. Their restoration requires complete storage lifecycle pricing or
  one durable parent reservation with separately settled nested calls.
- Legacy metered `deepr check`, `deepr make docs`, `deepr make strategy`, and
  `deepr agentic research` fail before provider construction until they use the
  shared durable call transaction. MCP sampling no longer silently falls
  through from host capacity to an unaccounted provider fallback.
- Plan-quota attempt accounting now writes paired idempotent quota and `$0` cost
  events with required durability and bounded locks. Dispatch-boundary errors,
  cancellation, timeout, launch failure, and post-launch runner failure retain
  honest usage uncertainty and partial-accounting status.
- The v2.36 validation pass used local or frozen fixtures and made no paid
  provider calls.
- Bundled host-agent skill guidance now distinguishes executable local, plan,
  bounded single-job API, visible/read-only, and gated capacity. It no longer
  recommends agentic research, API expert chat, hosted context, metered fan-out,
  or automatic provider fallback. Its lexical research-decision helper is now
  a non-authoritative preview router with no static price or paid-model verdict;
  exact provider preview and explicit approval own admission.

### Fixed

- Read-only council selection no longer creates or rewrites expert belief state.
  Canonical roster selection and consult traces now preserve exact runtime
  capacity, dissent, truncation, and typed synthesis failure without treating a
  structural result as semantic acceptance.
- Consult trace and lifecycle writers now serialize across threads and
  processes, fail closed on corrupt or partial journals, keep storage paths out
  of public errors, and preserve settled cancellation cost before terminal
  lifecycle state.
- Metered synthesis settlement now completes before fallible completion hooks,
  runs off the event loop, survives cancellation without a hidden late writer,
  and attaches recovery metadata when canonical settlement fails.
- Cost and quota ledgers now reject non-finite money or quota values, fail
  closed on malformed history before an accounting append, detect conflicting
  idempotency keys, and re-run a required fsync before accepting a replay after
  ambiguous durability failure.
- Plan CLI launch cancellation now retains ownership of a process that appears
  late, then kills and reaps it. Windows taskkill and post-kill cleanup are
  bounded; prelaunch scratch, stdin encoding, and timeout validation cannot be
  misclassified as vendor dispatch; public runner errors omit private paths.
- Shared metered-call helpers now mark durable dispatch before invoking a
  provider, conservatively settle the full reserved ceiling for cancellation,
  provider failure, or malformed usage, and keep reserve, mark, settle, and
  refund work off the event loop and owned through cancellation.
- Research reservation store operations now close every SQLite connection
  explicitly after commit or rollback, including cancellation cleanup, so
  Windows does not retain database handles after an operation returns.
- `scripts/check_costs.py` now reads the canonical append-only cost ledger
  instead of the obsolete `research_queue` SQLite table. A subprocess
  regression covers the standalone QA command.
- The legacy `scripts/submit_doc_research_jobs.py` no longer constructs an
  OpenAI provider or submits an unreserved six-job batch. It is now a
  compatibility stub that returns `research_parent_budget_unavailable` before
  filesystem writes or provider construction, with a subprocess regression.
- Direct `scripts/benchmark_models.py` execution now applies the same v2.36
  fail-closed live-provider gate as the supported CLI. Provider validation,
  evaluation, and judge calls cannot bypass admission, while `--dry-run` no
  longer performs optional network model discovery.
- `scripts/analyze_doc_gaps.py` and the `scripts/discover_models.py --llm`
  path now fail closed before credential loading or model work. Offline registry
  display and read-only provider model-list discovery remain available.
- Interactive `deepr expert chat` now fails before session construction. Its
  task-planning and council slash commands, hosted-vector upload helper, and
  legacy knowledge-synthesis calls carry independent inner gates so direct
  command or Python invocation cannot reach an unreserved charge.
- Capacity guidance no longer suggests a plan fallback during an explicit local
  wait, and revocation guidance names only commands that can actually recover
  the blocked state.
- The API-consult zero-budget regression now normalizes Click's wrapped output,
  so the same error contract passes on Windows and Linux terminal widths.

### Security

- A2A consult validation now requires exact booleans and finite numeric budget
  and elapsed values instead of accepting truthy or coercible substitutes.
- Metered council synthesis refuses unknown pricing, unaffordable context or
  output bounds, invalid usage, actual cost above the reserved bound, and
  non-finite settlement. Deepr-created OpenAI and Anthropic synthesis clients
  disable hidden SDK retries so one admitted dispatch cannot multiply behind
  one reservation.
- Plan and consult accounting surfaces preserve path-safe typed errors, exact
  attempt or trace ids, and paired-ledger status without rendering raw OS
  exceptions or credential-bearing CLI output.
- Research dispatch refuses a reservation smaller than its exact request
  envelope, persists and revalidates every bound before provider dispatch, and
  conservatively settles a marked attempt on provider failure. A definite
  pre-dispatch validation failure refunds its hold.
- AWS hosted research now returns
  `aws_metered_research_accounting_unavailable` before API request parsing or
  DynamoDB and SQS writes. The Fargate worker independently blocks legacy or
  manually queued work before provider import or construction and records only
  the fixed path-safe failure contract.

### Migration

- Callers with more than 10 experts must split the roster into separate bounded
  consults. Callers that need more than the new 600-second default must pass an
  explicit `max_elapsed_seconds` no greater than 21,600.
- The lifecycle journal and evaluator schemas are additive derived artifacts;
  existing belief stores and `deepr-consult-trace-v1` records require no data
  migration.
- Existing callers of standalone metered expert chat must use local or explicit
  plan read-only query capacity, or the separate bounded council synthesis
  surface, until the P1 restoration contract is complete.
- Callers of gated metered expert lifecycle commands must use local, scheduled,
  dry-run, history-only, or explicit plan-quota equivalents where available.
  Paid `eval calibrate --corpus` must
  be replaced with `$0` `eval calibrate --from` until each surface migrates to
  the shared durable per-call and parent-run budget transaction with storage
  and tool pricing.
- Hosted-context callers must use local source packs or local expert files.
  Multi-call research callers must submit bounded jobs one at a time. Legacy
  fact-check and artifact-generation callers must use direct bounded research or
  local or explicit plan expert consultation until their transaction gates are
  complete.

## [2.35.0] - 2026-07-11

### Added

- Scheduled local sync, sync-all, local route-gaps, and plan-backed compiled
  sync with a local recall embedder now take a read-only, best-effort GPU
  utilization observation before local model dispatch. Confirmed contention records
  durable per-expert `capacity_unavailable` WAITING outcomes with a bounded
  30-minute, 2-hour, then 6-hour retry cadence and never sleeps in-process or
  falls through to plan/API capacity. `deepr capacity` and `capacity next`
  expose local capacity as `free`, `busy`, or `unknown`; missing or malformed
  platform support remains unknown, and resident Ollama VRAM is not treated as
  contention. Busy artifacts preserve the requested verb and material options
  as argument-safe argv plus selected capacity/model metadata, and embedded
  guidance never advertises a fallback that contradicts an explicit-local
  wait. Explicit local work without `--scheduled` remains an operator override.
- `deepr expert migrate-legacy-state NAME` now previews a one-expert migration
  of known runtime artifacts from legacy display-name directories into the
  canonical expert directory. Apply refuses differing collisions, verifies
  copied bytes before removing a source, and leaves unknown content untouched.
- Python source and wheel distributions now include the built dashboard plus
  required configuration, skill, and template data. The frontend archive is
  deterministic, wheel contents are validated in CI, and package builds fail
  when the committed dashboard archive is missing or stale.
- Added an evidence-gated polyglot architecture decision and a measured local
  baseline. Deepr remains Python-first while explicit benchmark, correctness,
  packaging, fallback, and end-to-end value gates define when a bounded Rust
  engine, Go hosted runner, Mojo kernel, or free-threaded Python experiment may
  be justified.

### Fixed

- Frontend archive generation now normalizes generated text assets to LF and
  pins ZIP creator metadata instead of inheriting platform defaults. Archive
  members sort by their case-sensitive POSIX names instead of platform path
  semantics, and intermediate entries are stored without zlib-dependent
  compression. A Windows-produced release payload now rebuilds byte-for-byte
  on Linux CI while the final wheel and sdist remain compressed.
- Public installers and `deepr upgrade` now resolve an exact version-matched
  wheel from the latest GitHub release, validate that the asset belongs to the
  Deepr repository, and stop before subprocess changes when release metadata is
  offline, invalid, or missing the wheel. Documentation now states that GitHub
  Releases is the working binary channel, PyPI is future/manual, editable
  installs receive source-update guidance, and installer next steps accept
  local Ollama, supported plan CLIs, or API providers.
- Root CLI help and version handling now use a static lazy command registry,
  while provider and expert package exports load their implementations only on
  first use. A 20-process Windows benchmark reduced `deepr --version` p95 from
  roughly 4 to 5.4 seconds to about 223 ms and root help to about 217 ms. Import
  regressions prove these no-provider paths do not load OpenAI, Anthropic,
  Google, Azure, NumPy, or expert-chat implementations.
- Quota-ledger reads and durable appends now share one resolved-path lock across
  instances and an OS-backed lock across processes. Spawned-writer regressions
  prove concurrent fleet observations preserve every JSONL event on Windows.
- Brave, Tavily, and built-in scraper requests no longer execute synchronous
  network work on the async event loop. Concurrency regressions prove other
  tasks can continue while these compatibility adapters use bounded worker
  threads.
- Fresh/deep context and topic-learning page retrieval now preserve exact caps
  and output order while using four slots across distinct hosts and serializing
  requests to the same normalized host. Built-in DuckDuckGo and automatic
  multi-query search stay serial, explicit backends use bounded search fanout,
  and worker polling checks at most eight unique jobs concurrently with
  per-job in-flight protection and cancellation cleanup.
- Direct HTTP and Wayback page bodies now stream under an 8 MiB default
  decompressed-byte ceiling configurable with `SCRAPE_MAX_RESPONSE_BYTES`.
  Trustworthy oversized lengths fail before a body read; chunked and compressed
  bodies stop at the limit plus one byte; the failure is typed and cannot fall
  through to heavier strategies. Wayback metadata has a separate 256 KiB limit,
  and untrusted snapshot URLs and every redirect pass the public-host SSRF gate
  before dispatch with all intermediate responses closed.
- Browser expert-chat thought markers now use the packaged Lucide icon set
  instead of emoji glyphs. A frontend source-policy regression rejects emoji
  and en or em dash characters in authored frontend source.
- Council synthesis now reports output-limit and reasoning-only responses as
  incomplete instead of successful. Local Ollama synthesis disables hidden
  reasoning through its supported compatibility option. Durable consult traces
  now allocate the trace id before one append-only write and record the same
  roster, capacity, trace, and no-fallback contract returned by CLI and MCP,
  including explicit rosters and truncated results.
- Concurrent absorb through CLI or MCP now takes one non-blocking per-expert
  guard before store, backend, or model construction. A colliding run exits at
  `$0`, preventing stale snapshots from admitting duplicate beliefs. The wider
  cross-verb knowledge-mutation transaction remains tracked separately.
- Thought logs, hierarchical memory, document reconstruction, graph and RAG
  state, feedback, prompt optimization, and knowledge consolidation now resolve
  through the canonical expert directory unless an explicit storage override
  is supplied. Generated memory-card commands use the same canonical identity.
- Reconciliation-aware cost attribution now applies a unique append-only
  correction to the derived provider/model breakdown without changing raw
  events or dollar totals. Zero-dollar correction events no longer inflate call
  counts, and ambiguous or malformed corrections remain unapplied.
- Consult trace defaults now honor `DEEPR_DATA_DIR` before the legacy per-user
  path, preventing unit evaluations from mixing live operator traces into test
  results while retaining backward compatibility when no runtime root is set.
- Expert knowledge freshness now advances both the cutoff and last-refresh
  fields from the successful completion observation across accepted absorption,
  topic learning, source-backed sync, graph commits, corpus and vector writes,
  MCP, chat, learner, reflection follow-ups, and gap filling. Dry runs,
  all-rejected absorption, under-ready evidence, failed or empty ingestion, and
  ungrounded no-change markers remain non-advancing. Partial file learning
  counts only successful uploads. `expert reconcile-freshness` provides a
  cost-$0 preview-first metadata repair based only on accepted append-only
  events for currently live beliefs, with no provider call or belief mutation.
- Queue-backed research dispatch now restores the persisted cost reservation
  immediately before its atomic submission claim and verifies the exact
  reservation ID, job ID, provider, model, and held maximum against an active
  job-owned row. Missing, closed, or mismatched holds fail durably before any
  provider POST. A transient reservation-store read failure keeps the job
  queued and its possible hold intact for retry. The modern CLI now uses the
  same gate instead of trusting only its in-memory reservation.
- The local research queue now has one compatibility-safe path contract across
  both legacy config loaders and no-argument `SQLiteQueue` callers. An explicit
  `DEEPR_QUEUE_DB_PATH` wins, `DEEPR_DATA_DIR` places the queue under
  `<runtime-root>/queue/research_queue.db`, and an unset environment preserves
  `queue/research_queue.db`. Unit tests pin both variables to a per-test temp
  root so CLI commands cannot populate the workspace queue. `deepr doctor` now
  inspects the real `research_queue` table in SQLite read-only mode and reports
  queued zero-attempt rows older than 24 hours as advisory lifecycle candidates,
  including reservation-reference counts, without changing jobs or holds.
- Compiled graph commits now apply the verifier-ready subset when one claim
  verification artifact contains both accepted and rejected candidates. Each
  rejected candidate and reason remains in the envelope, sync reports ready and
  blocked counts, and apply still validates all selected operations before any
  write. Top-level extraction or verification schema, kind, model-response, or
  response-failure defects continue to block the entire envelope. Regression
  coverage preserves the live 7-candidate shape with 4 atomic writes and 3
  reviewable rejections.
- Metered-at-margin plan adapters now fail before probe or client construction
  until they implement adapter-specific deterministic estimates, durable cost
  reservations, provider-usage settlement, and canonical cost-ledger writes.
  This closes Copilot `$0` accounting paths in `capacity probe-plan`,
  `capacity probe-fleet`, expert sync, and expert absorb, including JSON and
  `-y`; retained backend choices and acknowledgement flags cannot override the
  gate, while non-metered plan adapters are unchanged.
- Plan CLI failures now preserve a bounded credential-redacted terminal stderr
  cause instead of truncating the start of a banner or progress stream, with
  prompt-overlap suppression before display. Every eligible dispatched attempt
  writes exactly one canonical `$0` cost event. Successful usage, exhaustion,
  ambiguous nonzero/timeout/empty-output attempts, and launch failures retain
  distinct honest quota metadata, and fleet status no longer calls an ambiguous
  failed attempt active.
- Codex's current `You've hit your usage limit` stderr wording now records an
  exhausted plan instead of an unknown failed attempt. Its absolute
  `try again at H:MM AM/PM` hint resolves through the host timezone and DST
  rules to one future UTC reset, including next-day rollover. Ambiguous,
  nonexistent, or unavailable local clocks remain unknown rather than using a
  guessed offset, and the phrase is never classified from answer stdout.
- Non-dry single-expert sync and each overlap-locked sync-all attempt now append
  a durable RUNNING loop snapshot after the
  overlap lock and before maintenance-engine construction, then appends its
  completion or caught execution failure with the same run id. A hard process
  termination therefore leaves visible interrupted-work state instead of
  source-pack partials with no loop record. Dry runs remain write-free, and an
  unavailable loop store blocks dispatch rather than allowing untracked work.
  Caught failures preserve any settled non-negative spend exposed by the error
  chain in both the failed run and sync-all rollup instead of resetting it to
  `$0`.
- Local expert maintenance now honors the model recorded by
  `expert make --local --local-model` instead of silently replacing it with
  the first process-wide Ollama default. Explicit command and admitted-capacity
  models still take precedence, non-local profiles retain the existing default,
  and the shared resolution contract covers sync, forced-local roster sync,
  absorb, topic learn, OKF absorb, and gap-fill construction.
- API-backed expert absorption now enforces one caller-supplied run ceiling
  across extraction plus every dynamically routed contradiction, dedup, and
  optional adjudication call. Each dispatch reserves before provider work,
  derives a provider `max_completion_tokens` cap from exact model pricing and a
  conservative input bound, settles reported token usage into the canonical
  append-only cost ledger, and
  contributes to the returned aggregate `actual_cost`; a missing usage record
  consumes its hold and an unavailable budget or settlement fails closed.
  Direct CLI, MCP, OKF, sync, and gap-fill totals now use settled cost, including
  paid previews and partial failed runs. MCP no longer records a duplicate
  process-local estimate, adjudication cannot write contested state after a
  budget denial, and explicit local or prepaid-plan absorbers retain `$0` cost.
- Contradiction routing can no longer become semantic graph truth by itself.
  Normal `ConflictResolver.detect_contradictions` returns only model-selected
  pairs, and generic `BeliefStore.add_belief` never persists lexical router
  hits as typed contradiction edges. After an initial absorb-time YES, a second
  fresh-context structured disconfirmation pass reverses statement order and
  searches for a compatible reading; only two agreeing judgments create a
  model-confirmed edge. Ambiguous or disabled verification preserves both
  claims without an edge or lexical dedup collapse. Contested read surfaces now
  expose model-confirmed versus unverified provenance, and continuity
  methodology v1.3 separates structural surfacing from verification coverage
  without claiming either proves semantic accuracy.
- Ordinary expert health checks are read-only again. Manual and scheduled
  audit-only paths no longer append loop records or expose a pending execution
  state for proposed actions. Scheduled action-plan JSON now uses
  `deepr-health-check-action-plan-v2`; the v1 schema remains published for
  historical consumers. Explicit `--archive-stale` mutation and wait paths
  continue to record durable loop state.
- Legacy CLI and web conflict-resolution mutations now fail before expert-store
  or provider construction. Their numeric budget previously limited only pair
  count while detection, adjudication, and consensus calls could bypass durable
  reservation and canonical settlement. The `$0` contested view remains
  available while a fully accounted local/plan-first replacement is tracked.
- Fresh and deep local or plan-context sync now sends search a concise
  subscription topic plus bounded focus instead of the full synthesis prompt,
  while retaining explicit URLs and the full answer instructions for the
  generation backend. A provenance-only preflight requires enough replayable,
  content-addressed evidence before local or plan generation, without requiring
  every search result to fetch or making a lexical relevance verdict. Sparse
  packs persist for diagnosis and return a retryable no-metered failure without
  advancing sync cadence or consuming local model or plan quota.
- Topic `expert learn` and `learn-web` no longer count search snippets or failed
  page fetches as synthesized live sources. Search-discovered runs require two
  fetched, content-addressed pages before local or plan generation, while an
  explicit URL retains a one-source path. Every attempt persists a source pack,
  manifest, source notes, and snapshots under the configured expert root, and a
  successful run also persists its report. Candidate extraction selects exact
  supporting labels; only the selected replay pointers enter each belief, and
  candidates without a valid pointer are rejected. Under-ready runs remain
  retryable, never fall through to metered capacity, and do not update knowledge
  freshness.
- Topic-learning extraction now accepts an exact replay-catalog value or treats
  one citation-style bracket pair as key form, so both
  `source_note:sn_...:w0` membership and `[S1]` resolve without fuzzy matching.
  Unknown pointers, semantic aliases, nested wrappers, and citation prose remain
  invalid. An all-rejected run no longer advances expert freshness. Human output
  groups rejection reasons and identifies failed retrieval candidates with
  bounded labels and URLs that omit userinfo, query parameters, and fragments.
  Structured learn-web failures suppress redundant low-level strategy warnings;
  generic scrape callers retain their existing warnings.
- Browser expert chat now requires an explicit API backend, positive bounded
  session budget, selected chat mode, and two metered-cost acknowledgements
  before provider construction. Socket.IO follow-ups and slash commands reuse
  one serialized session, cannot raise its approved ceiling, and clean up on
  explicit end, disconnect, or terminal failure. The REST fallback enforces
  the same contract, while unsupported browser local and plan capacity is
  rejected explicitly.
- Browser Stop now cancels the in-flight chat coroutine on its owning event
  loop, requests cancellation for accepted background provider jobs where the
  provider exposes it, suppresses conversation save and completion after
  cancellation, and closes provider plus cost-session resources before the
  `chat_cancelled` acknowledgement. Each browser turn holds its approved
  remaining ceiling durably, refunds it before dispatch, or settles the
  unaccounted remainder conservatively after an ambiguous dispatch. The UI
  waits for that acknowledgement before preserving partial text and no longer
  terminates healthy 5-20 minute modes with an artificial 60-second timeout.
  Provider exceptions returned through the legacy session string interface are
  typed as terminal failures before browser save or completion. Optional
  follow-up suggestions now reserve a conservative, 200-output-token bound,
  settle reported usage or ambiguous failure cost, and skip provider dispatch
  when that bound does not fit the approved session ceiling.
- Browser chat now initializes its displayed session ceiling from the loaded
  server maximum and clamps stale or oversized values. Terminal turn failures
  remain visible as failed assistant entries, retain partial text, and require
  the user to re-confirm the metered ceiling before Retry. Durable browser holds
  use the validated routed API provider/model passed to the turn, fail closed
  when that identity is unknown or mismatched, and label an ambiguous
  unaccounted-ceiling settlement as conservative rather than provider-reported
  actual usage. OpenAI and Anthropic expert-chat clients disable hidden SDK
  retries so one admitted dispatch cannot silently multiply behind one Deepr
  reservation. `costs show --daily-limit` and `--monthly-limit` now apply their
  explicit display overrides after persisted dashboard state loads.
- Cost Intelligence now distinguishes a loading model breakdown, a retryable
  ledger-query failure, a populated model breakdown, and a genuinely empty
  time range. The web breakdown endpoint has regression coverage proving it
  reads model-attributed and unknown-model events from the canonical ledger.
- Web polling now resolves the provider recorded on each persisted job for
  status reads, terminal cost settlement, cancellation, and provider-resource
  cleanup. Unknown or unavailable adapters remain active and visible without
  falling through to OpenAI. The OpenAI-only single and batch dashboard
  submission paths reject other provider model families before reservation or
  provider construction and persist their OpenAI ownership explicitly.
- `deepr web` now refuses to run the Werkzeug development server on a
  non-loopback interface, even when API authentication or the legacy public
  bind acknowledgement is present. Loopback development remains supported;
  network exposure requires a production WSGI server.
- Direct `python -m deepr.web.app` startup now passes Flask-SocketIO's Werkzeug
  safety override only through a helper that first validates the bind as
  loopback. This keeps intended local development startup working while
  preserving the non-loopback refusal before server construction.
- Installation guidance no longer claims an unavailable public PyPI package.
  Until a separate PyPI publication workflow exists, releases provide verified
  wheel and source archives on GitHub and source installation remains supported.

## [2.34.4] - 2026-07-10

### Security

- Read-only expert guidance resolves belief storage only from an existing,
  containment-validated directory enumerated below the configured expert root;
  stored or command-line expert names do not become unchecked filesystem paths.

### Added

- Added `deepr expert next NAME`, a `$0`, read-only navigator that returns a
  bounded action plan from current claims, freshness, gaps, contradictions,
  and durable learning-loop evidence. Its published `deepr-expert-next-v1`
  contract uses argument-safe argv plans, checks capacity before scheduled
  compiled sync, and explicitly disclaims semantic maturity scoring and policy
  changes.
- Added current research and staged designs for forgetting-aware expert
  improvement, bitemporal event authority, device-partitioned continuity,
  historically grounded perspective lenses, and modern agent-harness run
  control.

### Changed

- `deepr doctor`, README, ROADMAP, expert docs, supported-surface docs, and the
  portability ADR now state that generic synced folders support sequential
  device use only: one writer at a time, then a completed sync before switching
  devices. Concurrent multi-device mutation remains planned rather than
  marketed as shipped.
- Portability documentation now states that `DEEPR_DATA_DIR` also relocates
  queues, traces, benchmarks, observability artifacts, and several MCP
  databases instead of incorrectly describing them all as machine-local.

### Fixed

- Local experts no longer appear blocked merely because they have no provider
  vector store, and incomplete or stale expert guidance now routes through
  `deepr expert next` instead of emitting a topic-less learning command that
  cannot run.

## [2.34.3] - 2026-07-10

### Security

- Reserved provider cleanup identifiers are now server-owned job metadata.
  Public API, single-job web, and batch web submissions reject those fields,
  and public job responses
  redact them so callers cannot select another same-credential provider file or
  vector store for deletion.
- Provider failures now persist and log fixed diagnostics plus bounded exception
  class names instead of provider-controlled response or exception content.
- Metadata validation failures now return fixed public errors instead of
  exception-derived text across REST and web submission paths.
- Tightened the no-growth security-lint ratchet from 86 findings to 84 after
  the lifecycle hardening removed two findings.

### Changed

- API, web, and CLI cancellation now reports success only after the job
  transition, cost-reservation closure, and provider-resource cleanup are confirmed. Unconfirmed outcomes
  remain visible as retryable failures.
- Cancellation resolves the provider recorded on the job, atomically preserves
  concurrent terminal history, and remains available for provider-free queued
  jobs after credentials are removed.
- Repeated cancellation verifies or repairs durable cost closure before
  returning success, including after an interrupted queue or settlement step.
- The Research Live page stops polling on cancellation and keeps failed
  cancellation attempts visible with an actionable retry message.
- Provider `incomplete`, `failed`, and `cancelled` terminal states now converge
  deterministically across worker and web polling paths. Unknown future status
  values remain active, bounded, and observable until the provider contract is
  understood.
- CLI result retrieval and stale-list refresh now settle canonical cost, verify
  the ledger, clean provider resources, persist results, and only then mark a
  provider-completed job `COMPLETED`.

### Documentation

- Replaced removed `research wait`, `research trace`, and `jobs export` examples
  with the current durable-status, direct trace-flag, and stored-result commands.
- Updated the supported-version policy and documented truthful cancellation
  semantics.

## [2.34.2] - 2026-07-10

### Security

- Stopped provider validation from echoing unexpected model response content
  into console and dashboard-captured output. Unexpected responses now fail
  validation and produce a nonzero command exit while preserving a fixed
  diagnostic state and latency.
- Replaced benchmark-start exception serialization with a fixed validation
  response so internal exception details cannot cross the HTTP boundary.

## [2.34.1] - 2026-07-10

### Changed

- Bound web benchmark approval to the exact tier, quick-run, and judge options
  used for its cost estimate. Changing an option now invalidates the approval,
  and provider readiness filters fail closed when configuration is unavailable.
- Added scoped recovery actions to web expert, trace, model, and settings
  surfaces so a secondary request failure no longer erases valid primary data
  or masquerades as a legitimate empty state.

### Fixed

- Preserved benchmark failure output after a run exits and added a direct path
  back to run setup.
- Made benchmark estimates report only providers participating in the selected
  run instead of every configured provider.
- Restored dashboard benchmark subprocess execution from any working directory
  and carry the approved estimate into matching preflight and runtime caps.
- Added durable per-call reservations and append-only ledger settlement for
  benchmark evaluation, judge, and provider-validation calls. Parallel work is
  submitted only after reservation, and unbounded paid runs are refused.
- Made benchmark reservations cover the actual adapter output maxima and bounded
  search allowances, with unknown pricing and context metadata failing closed.
  Native managed research agents, uncapped Gemini 3 grounding, and xAI search
  tools are excluded from paid benchmark execution; research evaluation uses
  bounded orchestration. Grok 4.3 chat evaluation remains available without tools.
- Made destructive demo-data mutations mutually exclusive, surfaced fixed
  server denial messages, and linked unconfigured environments to capacity
  setup guidance.

## [2.34.0] - 2026-07-10

### Changed

- Made the experimental web Research Studio readiness-aware. It now identifies
  its OpenAI-backed submission boundary, pauses when OpenAI configuration or
  cost estimation is unavailable, removes misleading static price claims, and
  preserves fixed server denial messages for actionable recovery.
- Reconciled dashboard queue and ledger language. Overview and the persistent
  status bar now use the full queued-plus-processing total, queued work no
  longer claims to be processing, job cards show submission age, and Cost
  Intelligence separates all-operation ledger spend from queue completion.
- Made stale-job cleanup state its 30-minute queued/processing scope before
  confirmation and report the number of records safely transitioned.
- Added session-scoped Research Studio draft recovery for prompts and scalar
  configuration. The dashboard validates restored state, excludes uploaded
  file contents, reports unavailable storage, preserves drafts until a
  different URL-prefilled prompt is explicitly accepted, and clears drafts
  explicitly or after successful submission.
- Tightened narrow-screen hierarchy with compact Overview KPIs, responsive
  research and status actions, and 44-pixel Results view controls.

### Fixed

- Restored semantic keyboard navigation for active jobs, recent activity,
  result cards, and result pagination, including named controls and current-page
  state for assistive technology. Collapsed navigation and command search also
  retain explicit accessible names.
- Changed Socket.IO startup to polling-first fallback before WebSocket upgrade,
  restored same-origin connections on custom CLI hosts and ports without
  broadening cross-origin access, and replaced the unlabeled footer dot with a
  named connection state.
- Removed the hardcoded Help version and now render the running package version
  from the existing health response without full-page internal navigation.
- Closed unit-test isolation gaps in CLI run and fallback coverage. Tests now
  mock the durable enqueue seam instead of writing synthetic queued jobs into
  the developer's machine-local research database.
- Exposed Research Studio mode, Configuration, file-removal, and Results view
  state to assistive technology, and clarified where context-file upload lives.
- Added blocking frontend unit coverage for draft validation, privacy,
  persistence failure, URL-prefill arbitration, and clearing behavior.
- Replaced deprecated package-license table metadata with its SPDX expression
  and explicit license file before the setuptools 2027 removal deadline.

## [2.33.1] - 2026-07-09

### Security

- Replaced exception-derived API and web research errors with fixed public
  messages and safe server-side failure classification. Cost-limit and
  provider-construction failures can no longer expose dependency, ledger, or
  configuration exception text to clients.
- Separated webhook payload parsing from HTTP response construction. Signed
  invalid payloads and job identifiers now return fixed JSON errors, while
  request-controlled payload objects can reach only the authenticated callback
  and are never reused as route responses.
- Tightened local report job identifiers to an exact alphanumeric, hyphen, and
  underscore allowlist instead of silently rewriting punctuation. Direct job
  paths now pass resolved-base containment before the first filesystem probe,
  including rejection of symlink escapes.

## [2.33.0] - 2026-07-09

### Added
- Added a runtime-local recall case library for `deepr eval recall`. Operators
  can now run `deepr eval recall NAME --cases cases.json --record-cases` to
  merge labeled recall cases into `data/benchmarks/recall_cases/<expert>.json`,
  or run `deepr eval recall NAME --query TEXT --relevant-belief-id ID
  --record-cases` to capture one reviewed case without a scratch JSON file.
  The accumulated set can be rerun with `deepr eval recall NAME`. The library
  is versioned as `deepr-recall-eval-case-library-v1`, costs `$0`, writes no
  beliefs, writes no graph state, and keeps labels as operator-supplied routing
  evidence only.
- Added review-required recall case candidates to consult trace mining.
  Stored-belief consult context now includes selected belief ids, and
  `deepr-consult-trace-candidates-v1` may include
  `deepr-recall-eval-case-candidate-v1` drafts for failed-check, low-context,
  or middle-context traces that had selected belief context. These candidates
  are not auto-recorded as labels and require operator relevance review before
  they become `deepr eval recall` cases.
- Added the same review-required recall case candidate contract to claim
  verification decisions blocked by duplicate, contradiction, or temporal-scope
  memory context. The published `deepr-claim-verification-v1` schema now records
  the additive draft field and summary count without auto-recording labels or
  treating recall context as a relevance verdict.
- Added a conservative scheduler-preference eligibility block to
  `deepr eval recall` reports. Vector recall is marked eligible only after the
  vector route was evaluated on enough labeled cases, won required retrieval
  metrics, and the requested belief-vector index has no missing or stale records;
  the block remains routing evidence only and does not change scheduling yet.
- Added an explicit source-pack recall route preference seam. Claim verification
  can now consume a vetted recall eval scheduler-preference block and try
  vector-only recall first while preserving lexical fallback when the preference
  is absent, ineligible, or produces no vector hits.
- Added `deepr expert sync --recall-preference-report PATH` for compiled-claim
  sync. The flag validates a local `deepr eval recall` report for the same
  expert and embedding model, then passes only its scheduler-preference block
  into claim verification; the default path remains lexical-first unless an
  operator supplies the report explicitly.
- Added validation coverage proving an accumulated `deepr eval recall` case
  library can generate an eligible report that `deepr expert sync
  --recall-preference-report` accepts without ingesting the full report body.
- Hardened `deepr expert sync --recall-preference-report` so eligible reports
  are rechecked for enough cases, required vector metric wins, evaluated vector
  routing, no ineligible reasons, and complete current vector coverage before
  sync consumes the scheduler-preference block.
- Added an operator-validation block to `deepr eval recall` reports. Accumulated
  recall-library runs now declare whether their scheduler-preference evidence is
  ready for explicit sync use, while also recording that default routing remains
  lexical-first and still requires an operator-supplied saved report.
- Added `deepr eval recall-libraries`, a read-only `$0` inventory of accumulated
  recall case libraries. It emits `deepr-recall-library-inventory-v1`, flags
  invalid libraries, and shows which experts have enough operator-labeled cases
  to run route-evidence evals before any explicit sync preference report is
  considered.
- Added `deepr eval recall-libraries --validation-plan`, a read-only command
  plan for ready accumulated recall libraries. It emits
  `deepr-recall-library-validation-plan-v1`, includes local-embedding eval argv
  when the operator supplies `--local-embedding-model`, and records that the
  plan does not execute retrieval, write state, or authorize default routing.

### Changed
- Raised the web extra's Mistune floor to 3.3.0 and refreshed the lock to
  3.3.3, clearing CVE-2026-49851 inherited through Flasgger.
- Refreshed the lock to pip 26.1.2, clearing CVE-2026-8643 from the complete
  development and optional-extra dependency audit.
- Deferred web and REST research-provider construction until a request crosses
  the cost gate. Importing either application without provider credentials is
  now safe, and a paid submit fails closed with HTTP 503 when its provider is
  not configured.
- Closed the web submit fail-open path when cost-control initialization,
  estimation, or ledger checks fail. Paid submission now returns HTTP 503
  before provider construction whenever the money gate is unavailable.
- Provider-backed REST, web, direct CLI, campaign-batch, MCP, and internal
  orchestrator research now reserves maximum estimated cost atomically across
  processes against cumulative daily and monthly limits before provider work.
  Completion settles provider-reported cost, missing usage settles the held
  estimate, pre-provider failures or queued cancellations refund the
  reservation, and accepted cancellations settle the estimate conservatively;
  every settlement writes the canonical append-only ledger idempotently.
- Provider POST retries now reuse a stable idempotency key when the provider
  supports server-side idempotency. Gemini and Azure Foundry creation calls do
  not apply an application retry because those adapters expose no supported
  idempotency contract. Ambiguous timeout or connection outcomes settle the
  maximum hold instead of refunding potentially accepted work, while terminal
  queue and ledger evidence repair orphaned holds.
- Extended durable maximum-cost admission to direct CLI research and campaign
  batch tasks. Dispatch and queued cancellation now use competing atomic queue
  transitions, preventing a stale queued snapshot from refunding an in-flight
  provider submission.
- Added durable admission to document review, research planning, and team
  architecture model calls. These synchronous planning operations reserve the
  full configured per-call ceiling, settle provider token usage, and refuse to
  replay ambiguous failures. Interactive docs and team commands now confirm
  before those planning calls. Context-augmented CLI research now estimates
  and reserves the exact expanded prompt sent to the provider.
- Disabled OpenAI SDK retries for synchronous document review, research
  planning, team architecture, and team synthesis calls because those request
  shapes do not carry a supported application idempotency key. Team synthesis
  now uses the same durable ceiling and usage settlement as the other planning
  calls.
- Repaired `deepr docs analyze` to use the implemented document-review contract
  and configured queue path, and repaired `deepr team analyze` to construct the
  batch executor dependencies and call its supported campaign API.
- Closed reservation lifecycle gaps for pre-submit document failures,
  exact enhanced-prompt estimation, missing deep-research tools, immediate CLI
  completions, and the final dream-team task.
- Moved direct CLI cost admission ahead of provider file uploads and vector-store
  creation, so a rejected ceiling cannot create billable or persistent provider
  resources. Team and campaign research now honor the configured queue path and
  selected model through admission, persistence, and provider dispatch.
- Added compensating cleanup for files and vector stores when direct CLI
  preparation cannot reach provider submission. Because preparation may itself
  incur provider cost, any rollback after a created provider resource settles
  the held ceiling conservatively even when deletion is confirmed.
- Persisted provider file identifiers for completion cleanup, wired the worker
  and immediate-result paths to delete successful-job uploads, and gave
  OpenAI-compatible vector stores a one-day last-active expiry as a final leak
  bound when cleanup cannot be confirmed.
- Extended upload cleanup to terminal provider failure, confirmed cancellation,
  and the enqueue-to-claim cancellation race. Unconfirmed provider cancellation
  now retains processing state and resources for later polling instead of
  deleting context beneath live work.
- Replaced dream-team research's destructive 10-minute timeout behavior with a
  cancellation-aware boundary. Confirmed provider cancellation settles the
  maximum hold conservatively; an unconfirmed cancellation leaves the job in
  durable processing state with its reservation active for later polling and
  reconciliation.
- Campaign execution now polls accepted provider jobs through the same result
  finalization path as the worker. Its bounded wait attempts cost-safe provider
  cancellation and reports an unconfirmed job as pending without releasing its
  durable hold. Pending phases now pause the campaign and suppress downstream
  synthesis instead of finalizing an incomplete report.
- Added durable admission and no-replay behavior to campaign context summaries,
  autonomous research reviews, context-index construction, and explicit
  semantic context queries. Automatic pre-confirmation context discovery is
  keyword-only, so cancelling a research submission cannot spend on an
  embedding request.
- Added expert claim validation to the same durable metered-call contract and
  disabled SDK retries for its non-idempotent model request. CLI and MCP
  validation now share one cross-process ceiling and one canonical ledger
  settlement instead of separate process-local accounting.
- Changed registry background evaluation from default-on to explicit opt-in
  through `DEEPR_AUTO_EVAL=true`, preventing router construction and dry-run
  previews from silently starting provider-backed benchmark work.
- Replaced the recall preference point-estimate artifact with published
  `deepr-recall-eval-report-v2`. Reports now include hit@k, MRR, precision@k,
  recall@k, MAP@k, NDCG@k, and deterministic 95 percent paired percentile
  bootstrap intervals over 9,999 resamples.
- Tightened explicit vector preference eligibility to require at least 30
  paired operator-labeled cases, complete current vector coverage, required
  metric wins, and confidence lower bounds above zero for every required
  metric. The 30-case threshold is an operating floor, not a claim that the
  library represents future traffic.
- Hardened `--recall-preference-report` by recomputing case metrics, route
  summaries, paired uncertainty, and the scheduler-preference block before
  expert state is loaded, then matching its model-specific belief/vector state
  digest against live local state. The recall path repeats the digest check at
  use time, requires runtime top-k, expert domain, and minimum score to match
  the evaluated retrieval contract, and falls back lexically after any drift.
  Legacy v1 point-estimate reports, stale indexes, non-operator labels, and
  nonzero-cost evidence now fail closed with guidance to rerun the local `$0`
  evaluation. Default routing remains lexical-first.

## [2.32.0] - 2026-07-08

### Changed
- Refreshed README screenshot assets with isolated demo data so the cost
  intelligence image no longer displays spend above its configured budget, and
  added a screenshot QA guard that refuses future over-limit cost captures unless
  explicitly overridden.
- Expanded the blocking strict mypy gate to include `src/deepr/security`,
  `src/deepr/queue`, `src/deepr/storage`, `src/deepr/tools`, and
  `src/deepr/routing`, `src/deepr/worker`, `src/deepr/webhooks`,
  `src/deepr/a2a`, and the importable `deepr.skills` package as the fourth through
  twelfth strict islands, with CI, `pyproject.toml`, and contributor guidance kept in
  sync. Local probes
  confirmed the package targets are clean under
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/security`
  and
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/queue`
  and
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/storage`
  and
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/tools`
  and
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/routing`
  and
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/worker`
  and
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/webhooks`
  and
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/a2a`
  and
  `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/skills`.
- Cleaned queue typing without changing runtime behavior: JSON fallback parsing
  now casts the parsed value to the caller-supplied fallback type, SQLite helper
  methods declare their `None` returns, SQL parameter lists are explicitly
  heterogeneous, and the queue factory has typed keyword arguments.
- Cleaned storage typing without changing runtime behavior: the SQLite findings
  store now annotates lifecycle helper returns, database-row tuples, candidate
  ID sets, and close semantics, and the storage factory has typed keyword
  arguments.
- Cleaned tools typing while preserving runtime behavior: tool result timestamps
  now use a typed default factory, execution kwargs are typed consistently,
  web-search provider inputs are validated before dispatch, and score parsing
  no longer relies on object truthiness.
- Cleaned routing typing while preserving runtime behavior: auto-mode decisions,
  benchmark rankings, cheapest fallback candidates, summary stats, and route
  fallback tuples now have explicit shapes, and `ModelRouter.__init__` declares
  its `None` return.
- Cleaned worker typing while preserving runtime behavior: the local job poller
  now declares queue, provider, storage, job, response, socket, and async helper
  types against the existing backend abstractions.
- Cleaned webhooks typing while preserving runtime behavior: the Flask callback
  boundary, webhook views, ngrok process lifecycle, and tunnel context manager
  now have explicit strict-mode shapes.
- Added the already strict-clean A2A protocol package to the blocking strict
  mypy gate so the Agent Card, task, validation, and consult-handoff boundary
  cannot regress silently.
- Added the already strict-clean importable skill portability package to the blocking
  strict mypy gate so SKILL.md generation and per-expert export contracts
  cannot regress silently. Bundled hyphenated skill tool resource scripts remain
  outside this scoped island until their duplicate-module/import shape is
  normalized.
- Updated the A2A Agent Card property tests to assert the current contract:
  registered expert skills are followed by the built-in
  `deepr_consult_experts` collaboration skill.
- Added a roadmap watch item for the official MCP `2026-07-28` release
  candidate so Deepr can evaluate stateless transport, discovery, Tasks
  extension, schema, and deprecation changes in a focused protocol cycle after
  the final spec lands.

## [2.31.0] - 2026-07-04

### Added
- Council consults now disclose each stored belief's grounding assurance to the
  synthesis model. The deterministic perspective packet annotates a belief that a
  checker corroborated (`cross-vendor verified` or the weaker `same-vendor
  verified`) inline, next to the confidence and contested signals it already
  carried, and the perspective `context` payload gains a `beliefs_verified` count
  for programmatic hosts. The council synthesis prompt now also defines those
  labels, so the model can actually read them and weigh corroboration as one
  signal (never a rule that a verified belief must win). This is where the
  grounding stamp finally reaches the step that writes the answer: previously
  `grounding_assurance` was recorded on a belief and surfaced in handoff/recall
  summaries but never travelled into the council's synthesis context. Per
  AGENTIC_BALANCE it is disclosure, not a gate:
  the model still owns how much to weight a verified belief, lexical-overlap
  selection order is unchanged, and an unverified belief is neither dropped nor
  penalized for lacking the stamp (its absence is the honest signal). The "which
  assurance levels count as verified" semantics now live once on `CheckAssurance`
  (`maker_checker`) as `VERIFIED_ASSURANCES`/`ASSURANCE_LEVELS`, shared by the
  council packet and the handoff summary instead of each re-listing the strings.

## [2.30.0] - 2026-07-03

### Added
- Added `deepr eval grounding-correctness`, a `$0` (local Ollama by default),
  read-only eval that makes the verification spine's promise falsifiable. It runs
  the grounding checker over a curated golden set of human-labeled
  `(claim, evidence, label)` entailment triples (supported / contradicted /
  unrelated) and reports whether a SUPPORTED verdict is actually correct: the
  headline `support_precision` (when it says SUPPORTED, how often the evidence
  truly entails - the "trust a verified belief" number), `false_support_rate`
  (stamped SUPPORTED for contradicted/unrelated evidence; the dangerous failure),
  `support_recall`, `abstention_rate`, per-label accuracy, and the confusion
  matrix. Emits `deepr-grounding-correctness-v1` (`--json`, `--save`), accepts
  `--cases` for domain-specific triples, and can run against a `--checker-plan`
  vendor. `--set baseline|hard|all` selects the built-in golden set: `hard` is an
  adversarial set (lexical traps that share words but flip a key fact, unit/number
  contradictions, shared-entity distractors like Mercury-the-planet vs the element,
  no-overlap entailment, and `partial` cases where the evidence supports only one
  conjunct of a claim so the whole is not entailed). AGENTIC_BALANCE: the model
  (checker) owns the entailment verdict; this scoring is deterministic against
  human-curated ground truth, and the report discloses that agreement on a
  bounded set is not proof of world-truth.
- Added `deepr route explain "<query>"`, a `$0`, read-only, no-model command that
  shows how a query would route before anything is dispatched: which experts a
  consult would fan out to (by the deterministic keyword-overlap selection
  router) and the non-probing next-run capacity outlook (`$0` local / prepaid
  plan vs metered). It emits `deepr-route-explanation-v1` (`--json`) with a
  `no_model_call` / `routing_only` contract. Per AGENTIC_BALANCE the keyword
  overlap is labeled a high-recall selection router, never a judgment of which
  expert is authoritative or whether an answer will be correct; zero-overlap
  fallbacks are still shown so a consult is never starved. The council's
  auto-selection and this command now share one router (`deepr.experts.expert_routing`),
  and the capacity-outlook rendering is shared with `deepr expert loop-status`.

## [2.29.0] - 2026-07-03

### Added
- Added `due_subscriptions` (count + due topic names) to the `deepr-loop-status-v1`
  rollup, so `deepr expert loop-status` and the `deepr_expert_loop_status` MCP
  tool now show how much pending sync work an expert has. It is a cheap,
  read-only, fail-open read of the subscription sidecar; the field is additive
  within `deepr-loop-status-v1`, and the CLI escapes operator-set topic names
  before rendering. (Open-gap and contested-belief counts remain a follow-up.)
- Added a forward-looking `next_run_outlook` to the `deepr-loop-status-v1`
  rollup (surfaced by `deepr expert loop-status` and the `deepr_expert_loop_status`
  MCP tool). It reports, per maintenance task class (sync, absorb, gap_fill,
  reflect), whether cheap `$0` local or prepaid-plan capacity is *admitted* or a
  run would fall to metered budget, so an operator can see before a scheduled
  loop fires whether it will cost money. It is a pure, non-probing read of the
  admission ledger (`build_capacity_outlook`): "admitted" is a durable
  eligibility fact, not a liveness guarantee, and the payload says so (a local
  model must still be loaded, plan auto-routing also needs an observed quota
  window). The field is additive within `deepr-loop-status-v1`; the CLI prints a
  compact per-task-class capacity line.
- Added `--gate-untrusted-judges` to `deepr expert consult-quality-trends`. When
  set, it builds the judge-calibration report for the same expert and excludes
  calibrated-model reviews from judges that are not measured-trusted from
  prompt-regression candidate selection only; human reviews always stay
  eligible and descriptive trend stats still cover every review. The trend
  report records a `regression_gate` block (applied, trusted reviewers,
  excluded count). Gate off (the default) preserves the prior behavior. This
  closes the calibration loop: an unproven model judge can no longer silently
  steer which consult prompts are selected for regression.
- Added `deepr eval judge-calibration`, a `$0` read-only eval that measures how
  well a calibrated-model consult-quality judge agrees with a human anchor. It
  pairs the latest human review and latest calibrated-model review of the same
  consult trace and reports per-dimension agreement (mean absolute error,
  signed directional bias, exact- and within-tolerance-agreement rates) plus
  decision agreement, emitting `deepr-judge-calibration-report-v1`. Every
  number is a deterministic statistic over already-recorded scores; agreement
  is not correctness, and the report flags insufficient data below five
  independently paired traces so a judge is not trusted as a product metric
  before it is measured. The report also breaks agreement down per model-judge
  reviewer and marks each `trusted` only when it clears both the paired-trace
  floor and a within-tolerance agreement rate against the human anchor, so a
  specific judge can be gated rather than the aggregate; `trusted_model_reviewers`
  exposes that set for the planned regression-selection gate.
- Added bounded second-checker grounding escalation
  (`deepr.experts.grounding_escalation`). A weak first grounding verdict (a
  positive refutation, a could-not-verify from a checker that actually ran, or
  a caller-flagged high-risk claim) escalates to a genuinely independent
  second checker - a third vendor different from both the maker and the first
  checker - while a clean SUPPORTED verdict is never escalated, so healthy
  claims pay for one check, not two. Two independent refutations leave the
  claim unverified (never assurance-stamped) and flag it with a two-vendor
  reason; a disagreement or unresolved second check is surfaced as a contested
  flag and also left unverified; two independent supports stamp the assurance.
  Grounding stays advisory - it never blocks storage - so "hold" means the
  claim is not promoted to trusted knowledge, not that it is quarantined.
  Deterministic code owns which claims
  escalate, the independent-vendor choice, the verdict combination, and
  whether a metered second checker is constructed at all; the model still owns
  entailment. `ReportAbsorber` consumes it through an optional injected
  escalator, defaulting to the previous record-the-first-signal behavior.
- Wired bounded second-checker grounding escalation into `deepr expert absorb`
  and `deepr expert sync` via `--second-checker-plan` (and optional
  `--second-checker-plan-model`). It requires `--check-grounding --checker-plan`
  and must name a distinct plan-quota vendor, so a weak first grounding verdict
  escalates to a genuinely independent third opinion across all three maker
  backends (local, plan, and metered). On `expert sync` (including scheduled
  single-expert runs) the escalator threads through the shared
  `build_sync_engine` so background maintenance can hold double-refuted claims,
  not just one-shot absorb. (`expert sync-all` runs no grounding check and is
  unaffected.) The second checker is built
  lazily behind the escalator's factory, so a clean run never constructs it and
  healthy claims still pay for one check, not two. Validation runs before any
  store or provider work, and an ill-formed combination exits non-zero without
  cost.
- Added `deepr expert validate-export PATH`, a `$0` form-only validator for
  exported derived views: handoff payloads (`.json`), OKF bundle directories,
  and `SKILL.md` exports. It checks required provenance, schema version,
  trust metadata (grounding assurance, canonical-state/derived-view class
  markers), required skill frontmatter, and that a skill export at least
  references MCP consultation (a form-only presence check, not proof the
  skill is a pointer). It emits `deepr-export-validation-v1`, judges no
  content truth, and exits non-zero on failure so export pipelines can gate
  on it.
- Context-bearing sync now writes content-addressed raw snapshots: each
  fetched source's full text is persisted once under
  `sync_artifacts/snapshots/<content_hash>.txt` and the source-pack entry
  gains a `snapshot_ref`, so excerpt-based evidence is re-verifiable by
  re-hashing the snapshot file against the recorded `content_hash`. A
  snapshot is written only when the carried text actually hashes to the
  recorded `content_hash`, so conditional 304 excerpt reuse can never
  corrupt the content-addressed store, and oversized pages are skipped
  rather than truncated. The transient full text never lands in the pack
  artifact itself, identical content dedupes to one snapshot file, and a
  snapshot write failure records a per-source error without failing the
  sync (pack and hash provenance still persist fail-closed).
- Compiled-sync claim verification now memoizes claim+source+window decisions
  per expert (`deepr-verification-memo-v1`, an append-only JSONL cache under
  the expert's sync artifacts). A decision is replayed verbatim only when the
  full rendered judgment packet (statement, policy, evidence excerpts, recall
  context), prompt version, provider, and model are byte-identical; anything
  else re-dispatches the model. Fully replayed verifications skip the model
  call at `$0`, partial hits dispatch only fresh candidates, replayed items
  never carry `edge_decisions`, and both the verifier output and the persisted
  claim-verification sidecar record which candidates were replayed vs freshly
  judged, including the recall context each replayed decision was originally
  judged against. Punted decisions (any core verdict `unverified`) are never
  memoized, so a flaky output cannot freeze into a permanent replay. Known
  tradeoff: on partial hits, cross-candidate `edge_decisions` between fresh
  and replayed claims are not judged because replayed claims are absent from
  the reduced prompt. Set `DEEPR_DISABLE_VERIFICATION_MEMO=1` to always
  verify fresh.
- Added `--local-embedding-model` to `deepr expert refresh-semantic-recall` so
  missing or stale belief claim vectors can be computed through a local Ollama
  embedding model at `$0`, with explicit source validation and no metered
  fallback.
- Added `--local-embedding-model` to `deepr expert semantic-recall` so the
  query embedding for indexed vector recall can be computed locally at `$0`;
  the payload records `embedding_generation: local_ollama_query` and recall
  remains `candidate_only` routing.
- Added `deepr.backends.local.make_local_embedder`, an OpenAI-compatible
  Ollama `/v1/embeddings` batcher on the existing local client seam, with
  order restoration and strict vector-count validation.
- Added `--recall-embedding-model` to `deepr expert sync` so `--compile-claims`
  verification can embed ready claim statements through a local Ollama model at
  `$0` and route verifier recall context through the indexed belief vectors;
  embedding failure degrades to lexical recall routing without blocking the
  already-gated verification call.
- Persisted `deepr-claim-verification-v1` sidecars now record the exact recall
  packets the verifier prompt was built from, so the per-candidate recall
  `method` field in the durable artifact shows whether vector or lexical
  routing was actually used instead of re-resolving recall at artifact-build
  time.
- Scheduled `deepr expert reflect --scheduled` now consumes admitted
  owned/prepaid capacity for the new `reflect` task class instead of always
  waiting: the evaluator runs on an admitted local Ollama model or a
  trusted-quota plan backend, follow-ups execute only when the `gap_fill`
  waterfall rung also resolves to owned/prepaid capacity, and the run emits
  `deepr-scheduled-reflection-run-v1` with the capacity source recorded on the
  loop run. Scheduled mode still never dispatches metered evaluation or
  research; without admitted capacity the existing wait payload is unchanged.
- Added `reflect` to the plan-quota admission task classes
  (`deepr capacity admit-plan <backend> --task-class reflect`).
- Added `deepr eval recall NAME --cases PATH`, a `$0` read-only eval that
  compares lexical and indexed-vector recall routing on operator-labeled
  cases and emits `deepr-recall-eval-report-v1` with hit rate, mean
  reciprocal rank, and per-metric route winners. Relevance labels are
  operator-supplied; the report is routing evidence, never a semantic
  verdict, and `--save` writes the artifact under the configured benchmarks
  directory.

### Fixed
- Fixed a latent evidence-window bug in claim extraction and verification: the
  source-window excerpt helper floored `char_end` at the text length, which
  discarded any real sub-span window end and always ran the excerpt to the end
  of the source text (capped only by the per-window character limit). It now
  floors `char_end` at 0 and lets the existing end-before-start guard supply
  the full-text default, so a cited sub-span window is honored. Masked today
  by the single full-span-window producer; a regression pins the sub-span,
  missing-end, and out-of-range cases.
- Removed accidentally tracked external Distillr runtime telemetry from
  `library/.distill/`, ignored that generated directory, and added a hygiene
  regression so provider-usage telemetry cannot re-enter tracked source.

## [2.28.0] - 2026-07-01

Model currency, screenshot refresh, no-surprise-cost hardening, and release
hygiene release.

### Added
- Added a repository threat model covering Deepr trust boundaries, attacker
  stories, existing mitigations, and severity calibration.
- Added an append-only spend-decision log for value-of-spend gate decisions.
- Added `deepr costs spend-decisions` to inspect value-gate allow/defer
  decisions from the append-only spend-decision log without making provider
  calls.
- Added overlap-lock reporting for scheduled health-check archival so locked
  archive runs emit a structured `waiting_for_overlap` payload and loop-run
  record.

### Changed
- Refreshed the model-selection guide around the current registry snapshot,
  official provider verification links, the active web benchmarkable count,
  and no-surprise-bills capacity policy.
- Marked shut-down Gemini preview model IDs as deprecated migration entries,
  moved the `gemini-flash-lite` alias to the GA Flash-Lite model, and excluded
  deprecated registry entries from benchmark-derived routing and new web
  benchmark target counts.
- Updated web/API model allow-lists and benchmark validation targets to current
  xAI and Gemini registry IDs instead of retired Grok 4.1 or shut-down Gemini
  preview IDs.
- Added a current model watchlist to the model-selection guide for provider
  preview or limited-availability models that Deepr should not auto-route until
  registry pricing, adapter behavior, and settlement are verified.
- Refreshed architecture, install, examples, expert, and in-app Help model
  guidance so user-facing docs no longer imply API keys are required or promote
  stale provider defaults.
- Fixed registry discovery and demo expert seeding helpers so the documented
  model-registry command and web demo screenshots work with the current
  `src/` layout and configured data roots. Demo-looking existing experts now
  refresh to non-empty document, finding, and gap counts instead of preserving
  stale zero-count screenshot data.
- Regenerated web screenshots from current demo data with non-empty expert
  profiles, including profile-level claims instead of an empty chat tab.
- Kept image-generation registry entries out of the benchmarkable model list so
  premium media APIs do not appear as ordinary chat capacity.
- Added automatic metered gap-fill value decisions so default
  `deepr expert route-gaps --execute` can defer low-value paid research before
  provider dispatch while explicit `--api`, local, plan, scheduled wait, and
  dry-run paths stay unchanged.
- Local and plan fresh-context sync now persists `ETag` / `Last-Modified`
  validators and sends conditional requests for known sources, reusing
  `304 Not Modified` cached hashes for the existing no-change proof before paid
  absorb work.
- `deepr expert health-check --archive-stale --scheduled --yes` now supports
  startup `--jitter` and skips before opening the belief store when another
  health-check archive already holds the overlap lock.
- `deepr expert reflect --execute-followups` now holds the per-expert
  `reflect` overlap guard before constructing gap-fill execution, so duplicate
  follow-up runs record `overlap_locked` and skip before starting research.
- Legacy `deepr expert fill-gaps` now requires explicit `--api`, and
  unattended `--yes` also requires `--confirm-metered-cost`. The web
  fill-gaps endpoint now requires `allow_metered_api` plus
  `confirm_metered_cost` before it can construct a provider client. Health
  checks and docs point users to `route-gaps --execute --scheduled` as the
  local/plan-first path.
- Health-check belief-store reads and stale-belief archival now use the
  canonical expert directory, avoiding display-name and slug-name drift.
- Automatic metered `deepr expert sync` now evaluates schedule-derived
  value-of-spend factors before research dispatch and skips resumably when the
  current budget tier hurdle is not met. Local, dry-run, prepaid plan, and
  explicit `--api` paths are unchanged.

## [2.27.0] - 2026-06-30

Expert quality, hallucination-risk, cost-safety, and model-support release.

### Added
- Added Claude Sonnet 5 API support. `claude-sonnet-5` is now registered for
  Anthropic pricing, prompt-cache pricing, routing priors, API/web allowlists,
  and balanced Anthropic chat/synthesis defaults. Deepr treats it as a native
  Messages API adaptive-thinking model and omits unsupported sampling
  parameters.
- Added `deepr expert consult-quality-trends NAME`, a `$0` read-only trend
  report over reviewed consult-quality artifacts. It emits
  `deepr-consult-quality-trend-v1`, summarizes score dimensions and review
  statuses, and selects consult prompt regression candidates deterministically
  from reviewer scores and review status without judging answer meaning or
  writing beliefs.
- Added `deepr expert judge-consult-quality NAME TRACE_ID` with
  `--local-judge-model MODEL`, an explicit `$0` local Ollama judge path for
  consult-quality review.
  It validates model-returned rubric scores and failure labels, records them as
  calibrated-model review artifacts, and avoids storing raw trace answers or
  raw judge responses.
- Added explicit plan-quota consult-quality judging via
  `deepr expert judge-consult-quality NAME TRACE_ID --plan BACKEND`. It reuses
  the same calibrated review path, consumes only operator-selected plan quota,
  records `$0` Deepr cost metadata, and keeps metered fallback disabled.
- Added explicit budgeted API consult-quality judging via
  `deepr expert judge-consult-quality NAME TRACE_ID --api-provider PROVIDER`.
  It requires a model, positive budget, and `--confirm-metered-cost`, reserves
  the preflight estimate before dispatch, settles usage through the append-only
  cost ledger, and stores no raw trace answer or raw judge response.
- Added `deepr eval hallucination-risks`, a `$0` no-write advisory report over
  consult traces and reviewed consult-quality artifacts. It emits
  `deepr-hallucination-risk-report-v1`, routes observed hallucination-pattern
  risk signals into review and regression selection, and records coverage gaps
  without blocking answers or writing beliefs.
- Extended `deepr eval hallucination-risks` to optional expert handoff and
  source-pack manifest artifacts. The added signals cover grounding-assurance
  gaps, handoff contestation, handoff truncation, source-pack hash/readiness
  gaps, and high-stakes artifact routing without exposing local paths.
- Added false-premise compliance and template-order sensitivity checks to
  consult-quality semantic review cases. These are reviewer or calibrated-judge
  labels, not deterministic truth verdicts, and now feed
  `deepr eval hallucination-risks` as advisory signals.
- Added read-only consult prompt-regression candidates to
  `deepr eval hallucination-risks`, selected only from advisory consult trace
  and consult-quality review labels.
- Added selected-order context-position metadata to consult traces and surfaced
  aggregate context-position metadata in `deepr eval hallucination-risks`
  without treating middle-context placement as a semantic verdict.
- Added review-only long-context middle-loss eval cases for consult traces with
  selected middle context. Human or calibrated-model consult-quality reviews
  can now label `long_context_middle_loss`, and
  `deepr eval hallucination-risks` maps those reviewed labels into advisory
  prompt-regression candidates without blocking answers or writing beliefs.
- Added `deepr expert refresh-semantic-recall NAME`, an explicit `$0` operator
  path that refreshes the local belief-vector index from precomputed embeddings
  only, reports declared upstream embedding estimates separately from Deepr
  spend, and keeps recall `candidate_only` with no graph writes.

### Fixed
- Fixed three GitHub CodeQL findings: portrait generation now refunds reserved
  cost and returns a generic error on provider failure, citation validation skips
  markdown paths that resolve outside the expert documents directory, and
  `deepr mcp agent-guide --json` redacts bearer tokens while refusing JSON-only
  key creation that would lose the one-time secret.
- Hardened portrait generation against surprise image spend: local image
  endpoints remain the only auto-selected portrait provider, while OpenAI,
  Gemini, and xAI image generation require explicit provider selection or
  the single premium auto opt-in `DEEPR_ALLOW_METERED_IMAGE_AUTO=1`; legacy
  provider-specific image auto env vars are ignored; existing portraits are
  skipped unless regeneration is forced; and metered web or unattended CLI
  requests must acknowledge the estimate before budget reservation and
  dispatch.
- Made generated portraits portable and overwrite-safe by defaulting library
  and CLI portrait writes to the configured runtime data root and archiving any
  existing portrait before forced replacement.
- Added an API-backed `deepr expert make` cost-posture preview before provider
  construction. It shows the metered provider, selected upload size, and
  provider-specific vector-store storage estimate where available, and requires
  `--confirm-metered-profile` for unattended `--yes` runs.
- Tightened the GitHub security readback fixes: MCP agent guides now write
  redacted files instead of persisted bearer-token guides, portrait cost blocks
  return a generic external error, and citation-validation document lookup uses
  the loaded expert profile name for follow-on document paths.

## [2.26.0] - 2026-06-30

Scheduled gap-fill overlap guard release.

### Added
- Added `--jitter` to `deepr expert route-gaps --execute`, applying the same
  deterministic startup delay used by scheduled sync runs before non-dry
  gap-fill execution.

### Fixed
- Wrapped non-dry `deepr expert route-gaps --execute` runs in the per-expert
  `route-gaps` overlap lock. A colliding run now exits successfully with a
  skipped outcome and records an `overlap_locked` loop run without constructing
  a gap-fill engine or client.

## [2.25.0] - 2026-06-30

Plan capacity and expert-chat backend release.

### Fixed
- Excluded generated frontend build, screenshot, and `node_modules` directories
  from Python namespace package discovery so local frontend artifacts cannot
  leak into source distributions or wheels.
- Isolated capacity admission data in the unit-test fixture stack so selector
  tests and scheduled-maintenance tests never read a developer workstation's
  real `data/capacity` ledger.
- Hardened expert-chat backend turn construction so requested tools are
  rejected before dispatch when a backend declares no tool support, and
  `tool_choice` is omitted on no-tool turns.
- Made Anthropic-style expert-chat cost settlement use conservative fallback
  pricing when registry lookup fails, so metered input, output, cache-write,
  and cache-read usage cannot silently record as zero.

### Added
- Added admitted plan-quota dispatch to scheduled gap-fill execution.
  `deepr capacity admit-plan <backend> --task-class gap_fill` now records
  operator intent for gap-fill maintenance, and
  `deepr expert route-gaps NAME --execute --scheduled` consumes a plan backend
  only when the shared waterfall returns an operator-admitted,
  trusted-quota-observed choice. Without that cheap-capacity signal, scheduled
  gap-fill still waits instead of falling through to metered research.
- Added plan-quota dispatch to `deepr expert sync-all`. Roster maintenance can
  now use an explicitly selected non-metered plan backend with `--plan <id>` or
  an auto-selected plan backend only when the existing waterfall returns an
  operator-admitted, trusted-quota-observed plan choice. Metered-at-margin CLI
  backends are rejected for roster plan dispatch; use `--api` for explicit
  metered roster runs.
- Added `deepr capacity validate-fleet`, a bounded plan-fleet health check that
  runs selected plan CLI transport probes, records quota observations, then
  validates the no-metered consult contract only for transports that succeeded.
  It emits `deepr-plan-fleet-validation-v1`, uses a wrapper timeout above the
  plan subprocess guard, and fails selected backends that are skipped, missing,
  exhausted, timed out, or return failed synthesis status.
- Added `synthesis_status` and `synthesis_error_type` to `deepr-consult-v1`
  artifacts and the MCP consult validator summary, with validation now failing
  structurally when consult synthesis reports `failed`.
- Added non-agentic Anthropic expert-chat streaming through the native
  Messages stream helper, yielding text deltas and final usage for cost
  settlement while tools remain disabled.
- Added a streaming method to the expert-chat backend contract and routed final
  OpenAI token streaming through `OpenAIExpertChatBackend`, including streamed
  usage settlement. Local and plan expert-chat backends continue to
  declare streaming unsupported until provider-specific policy and tests exist.
- Added explicit Anthropic API support for non-agentic MCP
  `deepr_query_expert backend=api` calls. `provider=anthropic` now selects a
  native Anthropic Messages `ExpertChatBackend`, disables tools, supports
  non-agentic text streaming, omits OpenAI-only sampling parameters, rejects
  `agentic=true`, and records Anthropic input, output, cache-write, and
  cache-read token buckets through the chat cost ledger.
- Wired MCP `deepr_query_expert backend=local|plan` to the owned-capacity
  `ExpertChatBackend` adapters for one read-only compiled-context turn. These
  modes now attach `readonly_chat_artifact`, keep `research_triggered=0`,
  disable live metered fallback, and keep scoped-key spend at `$0`.
- Added a council-level regression test proving expert consult fan-out runs
  concurrently while respecting the bounded council concurrency cap.
- Added local Ollama and plan-quota `ExpertChatBackend` adapters for read-only
  compiled-context turns. Both declare tools, streaming, and prompt cache
  unsupported, expose no Deepr dollar spend, and are groundwork for public
  local/plan interactive chat routing.
- Moved expert-chat quick lookup and standard-research fallback calls onto the
  `ExpertChatBackend` seam while preserving their existing GPT-5.5 request
  shape, budget checks, and operation-specific cost ledger records.
- Moved expert-chat follow-up suggestions and conversation compaction onto the
  `ExpertChatBackend` seam, preserving the existing OpenAI model, sampling, and
  token-limit behavior while reducing remaining direct chat client calls.
- Added the first `ExpertChatBackend` slice for expert chat. Primary
  non-streaming API answer-generation turns now use `OpenAIExpertChatBackend`
  through a normalized request/result seam while preserving existing OpenAI
  behavior and chat cost accounting.
- Added provider-pluggable API synthesis for `deepr expert consult` and MCP
  `deepr_consult_experts`. API consults can now select `openai` or `anthropic`
  plus an explicit model; the Anthropic path uses the native Messages API,
  omits unsupported sampling parameters, handles refusal stops fail-closed, and
  records Anthropic cache-write/read usage buckets in synthesis ledger metadata.
- Added `deepr mcp validate-consult-fleet`, a bounded concurrent no-metered
  consult validation command for selected plan backends. It reuses the existing
  consult validator, skips metered-at-margin adapters, preserves the
  no-fallback capacity contract, and emits
  `deepr-mcp-consult-fleet-validation-v1`.
- Added `deepr capacity probe-fleet`, a bounded concurrent validation command
  for plan-quota CLIs. It probes selected backends in one pass, records the same
  quota observations as `probe-plan`, skips metered-at-margin adapters by
  default, and emits a versioned `deepr-plan-fleet-probe-v1` JSON envelope for
  automation.
- Added `deepr capacity next --probe`, which runs a `$0` live local-model probe
  before reporting automatic local routing as ready. A visible but unloadable
  admitted model now downgrades the next-action view to blocked instead of
  presenting stale readiness.
- Added a loopback-only socket guard to the dev/unit pytest environment so the
  unit gate fails on accidental outbound network calls while preserving local
  fixtures.
- Added a root `deepr --no-color` flag that disables ANSI color output for
  existing Rich consoles and sets `NO_COLOR` for consoles created later.
- Added first-class `ExpertProfile.schema_version` round-tripping. Profile
  serialization now preserves schema version metadata, and store saves align
  in-memory and persisted profiles with `PROFILE_SCHEMA_VERSION`.
- Added `deepr-expert-mutation-audit-v1`, an append-only
  `mutation_audit.jsonl` record beside each expert belief store. Belief
  creates, updates, revisions, archives, restores, contested writes, and
  conflict-merge updates now record actor, operation, belief id, event hash,
  and before/after state hashes without duplicating full claim text.
- Added MCP `deepr_semantic_recall`, a confirmation-gated, read-only,
  cost-$0 host-agent surface over the same `candidate_only` belief recall
  contract. Host-facing payloads are sanitized, and indexed vector recall still
  requires caller-supplied `query_embedding` plus `embedding_model`; Deepr does
  not generate embeddings in the tool.
- Added `deepr expert semantic-recall NAME QUERY`, a read-only, cost-$0
  operator surface over belief recall. It emits `candidate_only` JSON with no
  graph writes and no embedding generation; indexed vector recall runs only
  when the caller supplies both an explicit query embedding and embedding model.
- Added a persisted local belief-vector index for semantic recall. BeliefStore
  can now store already-computed belief embeddings, ignore stale vectors when a
  claim changes, prune vectors when beliefs are archived, and route
  claim-verification candidates through indexed vector recall without provider
  calls or graph writes. The construction-side refresh helper can index missing
  or stale belief embeddings through an injected embedder only after the caller
  supplies an explicit budget estimate; embedding generation remains an
  explicit, budget-gated caller responsibility.
- Added temporal edge qualifier rendering to regenerated expert digests.
  `deepr expert digest` now surfaces stored valid time, observed time,
  temporal scope, provenance, and missing-endpoint labels as derived view
  content while keeping the belief store canonical.
- Added `deepr eval continuity` methodology v1.2 with
  `temporal_edge_digest_visibility`, a `$0` check that regenerated expert
  digests expose stored temporal edge qualifiers as derived view content.
- Added MCP `deepr_temporal_edges`, a read-only, cost-$0 query over persisted
  typed-edge temporal qualifiers with `valid_at`, `observed_since`,
  `observed_until`, `edge_type`, `belief_ref`, and bounded `limit` filters.
- Added `deepr-graph-commit-envelope-v8` with first-class temporal edge
  qualifiers. Claim verification can now carry verifier-supplied `valid_from`,
  `valid_until`, `observed_at`, and `temporal_scope` fields on candidate edge
  decisions; graph-commit apply persists those qualifiers on typed belief
  edges and idempotent replay repairs missing temporal context without
  duplicating the edge.
- Added read-side temporal edge visibility. `what_changed` snapshots and
  `explain_belief` edge entries now surface temporal edge qualifiers, and
  `deepr eval continuity` measures temporal edge qualifier visibility through
  the `$0` read surface.
- Added explicit sync-side graph-commit apply for compiled claims.
  `deepr expert sync --compile-claims` now bypasses the legacy absorber for
  that topic, applies only the verified graph-commit envelope through the
  existing idempotent apply service, records a `graph_commit_apply_results`
  sidecar, and updates cadence only after an applied or already-applied
  result. `--apply-compiled-claims` remains accepted as a compatibility alias
  for the default apply path.
- Hardened sync-side graph-commit apply with an injectable metacognition
  tracker and regression coverage for verified knowledge-gap promotions, so the
  compiled apply path covers both factual belief writes and gap-backlog writes.
- Broadened sync-side graph-commit apply coverage for verified
  exploration-agenda, hypothesis, concept, stance, and original-idea promotions
  through the same injected metacognition tracker path.
- Added sync-side replay coverage for already-applied tracker state. The opt-in
  compiled apply path now has regression proof that repeated perspective-state
  promotion reports `already_applied`, keeps sync status `synced`, writes an
  apply sidecar, and does not duplicate metacognition records.
- Added concrete budget-gated claim verification for `expert sync
  --compile-claims`. Local, explicit plan-quota, and metered API sync paths now
  inject a `SemanticClaimVerifier` alongside extraction, include read-only
  memory recall in the verifier prompt, and surface claim-verification plus
  graph-commit sidecar refs in sync loop-run context.
- Added optional sync-side claim-verification and graph-commit sidecar
  artifacts. `ExpertSyncEngine` can now run an injected verifier after semantic
  claim extraction, compile store-backed recall into the claim-verification
  artifact, and write a staged graph-commit envelope for replayable review.
- Added store-backed, read-only recall routing for claim verification.
  `build_claim_verification` can now derive `candidate_only` memory-quality
  recall packets from a `BeliefStore` for ready claim candidates while leaving
  deduplication, contradiction, and temporal-scope judgment with the verifier.

### Changed
- Moved expert-chat streaming setup and streaming tool-loop rounds onto the
  `ExpertChatBackend` seam. Final token streaming still uses the direct
  provider stream until the backend contract grows a streaming interface, but
  streamed usage is now requested and settled when the provider returns it.
- Made OpenCode plan-quota capacity explicit-only until Deepr can verify that
  the routed provider is OAuth/subscription or local. Auto-routable plan
  capacity is now limited to Codex and Claude.
- Clarified the README first-screen value proposition, `--budget` examples, and
  audience fit. The README now calls `--budget 3` a budget ceiling, explains
  that users bring accounts, quotas, API keys, or local models, and
  distinguishes buyers, builders, agent-host users, and casual one-off chat use.
- Migrated compiled sync to graph-commit apply by default.
  `deepr expert sync --compile-claims` now applies the verified graph-commit
  envelope instead of calling the legacy absorber. Use
  `--stage-compiled-claims` with `--compile-claims` for the previous no-write
  sidecar staging behavior. `--apply-compiled-claims` remains accepted as a
  compatibility alias for the default apply path.

### Fixed
- Hardened plan-quota cost accounting. Plan-quota chat calls now fail closed if
  the canonical cost ledger cannot be written, and `capacity probe-plan` /
  `capacity probe-fleet` write `$0` cost-ledger events for quota-consuming
  validation probes.
- Required an explicit paid-capacity acknowledgement before metered-at-margin
  plan adapters such as Copilot can be selected, while preserving the existing
  sync and absorb confirmation prompts as that acknowledgement.
- Made plan-quota CLI timeout and cancellation cleanup terminate the subprocess
  tree instead of only the parent process.
- Hardened MCP sandbox creation against path-segment job ids by sanitizing the
  sandbox id, resolving the sandbox root, and asserting containment before
  creating or cleaning files.
- Recorded the actual estimated xAI Grok 4.3 cost for expert-chat standard
  research and blocked the GPT fallback when the fallback estimate exceeds cost
  safety.
- Hardened scraper redirects against SSRF by validating every redirect target
  before following it and stopping fallback strategies after a security block.
- Moved the Google Imagen API key out of the query string and sanitized Google
  image-generation HTTP errors so provider secrets are not echoed in logs.
- Added budget reservation before web portrait generation and allowed explicit
  local portrait generation without a metered reservation.
- Tightened the security ratchet baseline from 88 findings to 87 after marking
  the legacy expert-query session key hash as non-security use.
- Made plan-quota fleet status show the effective sanitized child auth mode and
  the raw parent-shell auth mode separately, so an API key in the parent
  environment no longer makes a safe plan-auth child run look metered.
- Recorded quota observations from explicit `capacity probe-plan` calls, so the
  fleet view updates after successful probes and observed exhaustion.
- Included the live local-probe result in `deepr capacity --probe --json`.
- Hardened report absorption against provider JSON that contains raw control
  characters inside strings or lightweight wrapper text, while still requiring
  parseable JSON before any claim extraction proceeds.
- Persisted and audited lower-confidence conflict evidence retained during
  belief resolution while preserving the existing no-new-absorbed-change return
  contract.
- Hardened public-bind detection across A2A, MCP HTTP, Flask API, and the web
  dashboard. Empty or unset bind hosts are now treated as all-interface binds,
  not loopback, so unauthenticated public-bind guardrails cannot be bypassed by
  passing an empty host value.
- Kept sync graph-commit apply auditability fail-closed. If a compiled apply
  mutates state but the apply-result sidecar cannot be written, the sync outcome
  now fails and leaves cadence due so a later idempotent replay can write the
  missing audit artifact.
- Unified runtime artifact roots behind configured data directories. Benchmark
  readers and writers, local eval artifacts, red-team artifacts, MCP state
  stores, web traces, portraits, routing logs, job logs, audit logs, and report
  access now consistently honor `DEEPR_DATA_DIR` or the configured reports root
  instead of drifting across hardcoded repository-local paths.
- Hardened no-key and redacted-key provider initialization so configuration
  redaction does not accidentally become a literal API key.
- Tightened durable local writes and cleanup paths across ledgers, belief
  events, profile writes, MCP state, and job logs without introducing silent
  no-op branches.
- Sanitized worker poller error logging so exception tracebacks do not re-emit
  unredacted provider details after redaction.

- Tightened the security ratchet baseline from 95 findings to 88 after the
  maintenance sweep reduced the current count.

## [2.24.0] - 2026-06-28

Compiler recall context release.

<details>
<summary>Archived autonomous progress milestones before the latest five cycles</summary>

- Built the Level 5 and Level 6 expert maturity design, including explicit
  self-model, metacognitive monitor, and reflective-continuity gates.
- Added the MCP no-metered consult path and host-agent test guide.
- Added topic learning through local and explicit plan capacity.
- Added Grok, Codex, and Claude quota metadata refresh paths.
- Added plan-quota execution for sync, absorb, learn, route-gaps, and probes.
- Added hosted MCP HTTP, scoped keys, per-key budgets, rate limits, concurrency
  caps, audit review, registration manifests, and deployment recipes.
- Added loop-run records, loop-status rollups, OKF export/import, handoff
  schemas, scheduled maintenance schemas, prompt-boundary red-team metrics, and
  supported-surface documentation.

</details>

### Added
- Added compiler-side recall context for claim verification decisions.
  `build_claim_verification` can now attach caller-supplied belief, concept, or
  original-idea recall hits under a `candidate_only` `recall_context` packet so
  the verifier can inspect memory-quality candidates without changing readiness
  or writing the graph.
- Added read-only original-idea recall candidates over metacognitive state.
  `recall_original_idea_candidates` and `MetaCognitionTracker` now route active
  original ideas through the existing `candidate_only` recall contract with
  perspective-state authority, non-factual promotion policy metadata, and no
  writes or semantic verdicts.
- Added `deepr-expert-perspective-state-v1`, a read-only metacognitive
  perspective-state packet that exposes active original ideas with authority,
  promotion policy, uncertainty, expected observations, and disconfirming
  signals. Expert memory cards, handoff payloads, and consult contexts now use
  that packet so original ideas can guide agent planning without being
  presented as verified external facts.
- Added `deepr-graph-commit-envelope-v7` with verifier-gated
  `promote_original_idea` operations. Verified original-idea candidates now
  carry title, statement, origin, rationale, uncertainty, assumptions,
  implications, expected observations, disconfirming signals, priority,
  confidence, provenance, and an idempotency key through the explicit commit
  boundary without being treated as factual beliefs.
- Extended `deepr expert apply-graph-commit` to apply v7 original-idea
  promotions into the metacognition original-idea backlog while preserving v1
  through v6 envelope compatibility, dry-run previews, noninteractive `--yes`
  gating, locks, and `$0` no-model apply semantics.
- Added `deepr-graph-commit-envelope-v6` with verifier-gated
  `promote_stance` operations. Verified stance candidates now carry title,
  position, origin, rationale, uncertainty, tradeoffs, decision criteria,
  expected observations, disconfirming signals, priority, confidence,
  provenance, and an idempotency key through the explicit commit boundary
  without being treated as factual beliefs.
- Extended `deepr expert apply-graph-commit` to apply v6 stance promotions
  into the metacognition stance backlog while preserving v1 through v5
  envelope compatibility, dry-run previews, noninteractive `--yes` gating,
  locks, and `$0` no-model apply semantics.
- Added `deepr-graph-commit-envelope-v5` with verifier-gated
  `promote_concept` operations. Verified concept candidates now carry name,
  description, origin, rationale, uncertainty, key properties, related terms,
  expected observations, disconfirming signals, priority, confidence,
  provenance, and an idempotency key through the explicit commit boundary
  without being treated as factual beliefs.
- Extended `deepr expert apply-graph-commit` to apply v5 concept promotions
  into the metacognition concept backlog while preserving v1 through v4
  envelope compatibility, dry-run previews, noninteractive `--yes` gating,
  locks, and `$0` no-model apply semantics.
- Added `deepr-graph-commit-envelope-v4` with verifier-gated
  `promote_hypothesis` operations. Verified hypothesis candidates now carry
  title, statement, origin, rationale, uncertainty, assumptions, expected
  observations, disconfirming signals, priority, confidence, provenance, and an
  idempotency key through the explicit commit boundary without being treated as
  factual beliefs.
- Extended `deepr expert apply-graph-commit` to apply v4 hypothesis promotions
  into the metacognition hypothesis backlog while preserving v1, v2, and v3
  envelope compatibility, dry-run previews, noninteractive `--yes` gating,
  locks, and `$0` no-model apply semantics.
- Added `deepr-graph-commit-envelope-v3` with verifier-gated
  `promote_exploration_agenda` operations. Verified agenda candidates now carry
  title, questions, origin, rationale, uncertainty, expected observations,
  disconfirming signals, success criteria, priority, expected value, cost
  estimate, provenance, and an idempotency key through the explicit commit
  boundary without being treated as factual beliefs.
- Extended `deepr expert apply-graph-commit` to apply v3 exploration-agenda
  promotions into the metacognition agenda backlog while preserving v1
  add-belief and v2 gap-promotion envelope compatibility, dry-run previews,
  noninteractive `--yes` gating, locks, and `$0` no-model apply semantics.
- Added `deepr-graph-commit-envelope-v2` with verifier-gated `promote_gap`
  operations. Verified knowledge-gap candidates can now carry topic,
  questions, priority, expected value, cost estimate, provenance, and an
  idempotency key through the same explicit commit boundary as belief writes.
- Extended `deepr expert apply-graph-commit` to apply v2 gap promotions into
  the existing metacognition gap backlog while preserving v1 add-belief envelope
  compatibility, dry-run previews, noninteractive `--yes` gating, locks, and
  `$0` no-model apply semantics.
- Added `deepr a2a validate-host`, a no-metered A2A host-validation harness.
  It validates current Agent Card discovery at `/.well-known/agent-card.json`,
  consult skill advertisement, no-metered consult task completion, artifact
  linkage, cost and capacity posture, dissent preservation, host action
  boundaries, and secret redaction. The legacy `/.well-known/agent.json` path
  remains supported as a compatibility alias.
- Added A2A `deepr_consult_experts` support. The Agent Card now advertises the
  consult skill, and completed consult tasks return a task-level artifact with
  the full `deepr-consult-v1` payload, collaboration metadata, capacity posture,
  cost, trace id, agreements, and disagreements. A2A consult defaults to local
  no-metered synthesis; API synthesis requires explicit `allow_metered_api=true`
  and a positive budget.
- Added `deepr expert apply-graph-commit`, the explicit write boundary for
  verified graph commit envelopes. It supports dry-run JSON previews,
  noninteractive `--yes` gating, per-expert locking, idempotent replay, typed
  edge writes, contradiction mirror updates, and the published
  `deepr-graph-commit-apply-v1` result schema without model calls or spend.
- Added verifier-supplied candidate edge decisions to the claim-verification
  and graph-commit envelope contracts. Valid ready-candidate relationships now
  become idempotent typed edge operations, while malformed edge decisions are
  reported without blocking the underlying factual belief decision.
- Added `deepr-graph-commit-envelope-v1`, the deterministic no-write boundary
  after claim verification. It turns verified factual decisions into
  idempotent add-belief operations, blocks hypotheses and other perspective
  states until dedicated stores exist, and requires the explicit graph commit
  apply command before graph mutation.
- Added `deepr mcp validate-consult`, a no-metered external-agent consult
  validation harness. It can run as a `$0` offline fixture, an in-process live
  local or explicit plan-capacity check, or an HTTP MCP endpoint check. Reports
  use `deepr-mcp-consult-validation-v1` and validate consult schema, trace
  linkage, capacity no-fallback posture, cost ceiling, dissent preservation,
  host action boundaries, and secret redaction without judging answer meaning.
- Published `deepr-consult-v1` and added MCP `outputSchema` plus
  `structuredContent` for JSON-object tool results while preserving text JSON
  compatibility for older MCP clients.
- Added `deepr expert review-consult-quality` and the published
  `deepr-consult-quality-review-v1` schema. Operators can now score a sanitized
  consult quality case with human or calibrated-model judgment, persist the
  reviewed score artifact, and promote accepted cases into gap or eval artifacts
  without committing beliefs or using lexical verdicts.
- Added `deepr-consult-quality-eval-case-v1`, a published semantic review-case
  packet generated from failed or low-context consult traces. `deepr eval
  consult` now checks collaboration metadata, no-metered capacity posture,
  dissent preservation, trace candidate shape, and semantic quality review-case
  boundaries at `$0` without turning lexical checks into meaning verdicts.
- Added `deepr expert memory-card`, a `$0` generated `EXPERT.md` surface backed
  by the published `deepr-expert-memory-card-v1` schema. The card is derived
  from profile, manifest, belief events, and self-model state, then renders a
  compact wiki-style orientation packet with identity policy, current stance,
  explicitly tagged theories and insights, self-research agenda, what would
  change the expert's mind, agency scope, calibration, goals, beliefs, gaps,
  contradictions, collaboration guidance, and update policy. It previews by
  default and writes only when `--write` is set.
- Added `deepr-claim-verification-v1`, the verifier-decision compiler envelope
  after semantic claim extraction. It records support, contradiction,
  deduplication, temporal-scope, and type-specific policy decisions while
  keeping graph writes disabled until a graph commit envelope is explicitly
  applied. Factual claims require support; hypotheses, stances, concepts,
  proposals, and original ideas require origin, rationale, uncertainty, and
  disconfirming signals instead of an online-source veto.
- Added the `deepr-expert-collaboration-v1` council contract to CLI and MCP
  consult artifacts. Host agents now receive a machine-readable collaboration
  packet with the expert roster, per-expert role, shared consult trace id,
  budget and capacity contract, evidence-packet summary, dissent handling, and
  result artifact refs without an extra model call or downstream action
  authority.
- Added local candidate recall for belief and concept memory. The new recall
  contract accepts supplied vectors for local cosine routing, falls back to an
  explicitly labeled lexical router when allowed, returns only `candidate_only`
  metadata, and exposes `BeliefStore.recall_contradiction_candidates` so
  paraphrased same-domain conflicts can reach later verifier checks without
  graph writes, model calls, or confidence changes.
- Added explicit `deepr expert sync --compile-claims` semantic compiler
  invocation. Sync can now run a budget-gated local, plan-quota, or metered
  OpenAI-shaped chat client over ready source-note windows, quarantine
  untrusted source excerpts in the prompt, persist
  `deepr-semantic-claim-extraction-v1` sidecar artifacts, and keep graph writes
  disabled until verification and a commit envelope exist.
- Clarified the expert-state boundary: factual claims need support checks, while
  original ideas, hypotheses, and stances are first-class state with origin,
  rationale, uncertainty, review status, and disconfirming signals instead of an
  online-source veto.
- Added `deepr-semantic-claim-extraction-v1`, the first model-judgment
  compiler envelope after source notes. It records prompt/schema version
  metadata, provider/model/capacity refs, raw response hashes, source-note and
  source-window refs, normalized candidate IDs, model-reported confidence and
  claim metadata, and verifier-pending gates while explicitly keeping graph
  writes disabled until verification, a commit envelope, and explicit apply.
- Added `deepr-source-note-v1`, the second deterministic compiler stage after
  source-pack manifests. Sync now writes source-note cards with stable IDs,
  note hashes, provenance refs, source-window pointers, and fail-closed
  readiness flags beside each source pack, then attaches those artifact refs to
  sync loop-run context. The stage is `$0`, read-only, and performs no semantic
  judgment or model calls.
- Added `docs/design/expert-chat-capacity-backends.md`, clarifying the path to
  local, plan-quota, OpenAI, and Anthropic expert chat backends without silent
  fallback or provider-shaped cost leaks. The MCP guide now correctly limits
  local and plan backend claims to `deepr_consult_experts` until
  `deepr_query_expert` has a backend-neutral chat runner.
- Added `deepr expert accept-self-model`, a `$0` outcome-evidence acceptance
  gate for recorded self-model update review artifacts. It publishes
  `deepr-expert-self-model-update-acceptance-v1`, requires explicit reviewer
  and outcome evidence refs, writes only a separate append-only acceptance
  record, and attaches accepted records to later sync loop-run context as
  read-only guidance without mutating the derived self-model or granting
  authority.
- Added `deepr-source-pack-manifest-v1`, the first research-processing compiler
  stage. Context-bearing sync runs now write a companion deterministic manifest
  beside each source pack with provenance, source counts, excerpt hashes,
  content-hash validity, and readiness metadata. It costs `$0`, makes no model
  calls, and never emits semantic verdicts.
- Added `deepr expert propose-self-model`, a `$0` verifier-gated self-model
  update review-record surface backed by the published
  `deepr-expert-self-model-update-v1` schema. It previews by default and
  requires `--apply` before writing an append-only local artifact; the gate
  validates proposal type, target path, evidence refs, human review, zero cost,
  no derived self-model mutation, and no authority expansion.
- Added `deepr mcp agent-guide`, a scoped-key and copy-ready handoff generator
  for letting another agent test Deepr experts over HTTP MCP with a zero-dollar
  budget ceiling, rate limit, endpoint, server command, and no-metered consult
  instructions.
- Hardened scoped HTTP MCP keys so expert-scoped consult calls are constrained
  to the key's expert allowlist before dispatch, and `agent-guide --output`
  refuses git-trackable bearer-token files by default.
- Added a blocking Gitleaks history scan in CI, removed scanner-triggering fake
  key literals from current test fixtures, and documented the historical
  redaction-test false positives in `.gitleaksignore`.
- Added repo-root `.gitleaks.toml` so CI keeps the default Gitleaks rules while
  allowing only exact historical fake redaction-test fixtures. This makes the
  full-history secret scan pass without skipping files, commits, or
  `generic-api-key`.
- Added `deepr expert promote-monitor`, a `$0` reviewed promotion surface backed
  by the published `deepr-metacognitive-promotion-v1` schema. It previews by
  default and requires `--apply` before a `gap_or_eval_candidate` monitor
  proposal writes a metacognition gap, a local eval-case artifact under
  `data/benchmarks`, or both.
- Added `deepr expert monitor`, a `$0` read-only metacognitive monitor surface
  backed by the published `deepr-metacognitive-monitor-v1` schema. It turns
  self-model blockers or calibration risks, failed loop runs, capacity waits,
  and sanitized consult trace candidates into `review_required` proposals
  without applying goal, strategy, gap, eval, prompt, tool, or skill changes.
- Added `deepr expert self-model`, a `$0` read-only expert self-model surface
  backed by the published `deepr-expert-self-model-v1` schema. The payload is
  derived from the profile and manifest and includes capabilities, limits,
  current goals, calibration, learning strategy, continuity, blockers, risks,
  and a bounded current-focus packet without mutating expert state.
- Added persisted consult traces. CLI and MCP consults now append local
  `deepr-consult-trace-v1` records with the question, requested experts,
  selected context metadata, capacity posture, output artifact, checks run, and
  first-class synthesis failure events. The schema is published under
  `docs/schemas/` and registered for downstream compatibility checks.
- Added sanitized consult trace review. `deepr expert consult-traces` mines local
  failed or low-context consult traces into `deepr-consult-trace-candidates-v1`
  gap/eval candidates without exposing local trace file paths or raw trace
  payloads.
- Added `deepr_capabilities`, a free MCP discovery tool returning the versioned
  `deepr-capabilities-v1` map: expert roster, key tools with live registry-sourced
  cost tiers and outcome-oriented when-to-use, the `$0` owned/prepaid synthesis
  paths, the cost-tier legend, and the structured-error contract. Cost tiers are
  read from the live registry so the map cannot drift from the tools served.
- Raised consult auto-fan-out breadth from 5 to 10 (`MAX_CONSULT_EXPERTS`,
  `ExpertCouncil.MAX_EXPERTS`) with a relevance floor so a wide fan-out drops
  zero-overlap experts instead of padding the council, and never returns empty
  when experts exist. `deepr_consult_experts.max_experts` accepts up to 10.
- Made all four plan-quota CLIs run headless: Codex and Claude over stdin, Grok
  over `--prompt-file` (long research prompts exceeded the Windows command-line
  limit as an argument), and Antigravity by recovering its answer from its
  transcript (`antigravity_transcript.recover_answer`) since `agy -p` drops stdout
  under a non-TTY pipe. A shared `client._build_invocation` resolves file/stdin/argv
  delivery for the chat seam and the probe.
- Documented agent quality-of-life in `mcp/README.md`: a "For the consuming agent"
  guide grounded in current MCP best practices, plus a LAN-access recipe validated
  end to end (LAN-IP endpoint with a token passes; without it every real call is
  Unauthorized). Added `QUALITY-RUBRIC.md`, the 6-category merge bar.
- Added `deepr capacity refresh-quota grok`, a metadata-only `$0` probe that
  reads the current user's Grok CLI auth file, calls the Grok billing metadata
  endpoint, parses the returned gRPC-web quota frame, and records a normalized
  monthly quota window without running a model call or storing credential
  material.
- Added `deepr expert learn-web --plan <id>`, an explicit plan-quota expert
  bootstrap path. It uses free DuckDuckGo retrieval, then runs both cited-report
  synthesis and verified belief extraction through one plan-quota CLI client
  with `$0` cost-ledger entries.
- Added `deepr eval consult`, a `$0` consult harness regression suite covering
  explicit expert slug resolution, stored-belief context packet shape,
  synthesis agreement/disagreement parsing, `deepr-consult-v1` context
  preservation, `deepr-consult-trace-v1` trace contracts, and
  `deepr-consult-trace-candidates-v1` candidate contracts. It can emit JSON and
  save artifacts under `data/benchmarks`.
- Added owned-capacity consult synthesis flags:
  `deepr expert consult --local` uses local Ollama synthesis at `$0`, and
  `deepr expert consult --plan <id>` uses an explicit plan-quota CLI for
  synthesis. Both modes disable live metered expert fallback when an expert has
  no stored belief context, so owned/prepaid consults cannot silently become API
  calls.
- Added `docs/MCP_AGENT_TEST_GUIDE.md`, a host-agent test guide for connecting
  to Deepr over MCP, listing experts, reading handoff and loop state, and
  running no-metered expert consults through local or explicit plan capacity.
- Added `docs/design/level-5-6-expert-maturity.md`, defining Deepr's concrete
  gates for Level 5 bounded learning experts, explicit expert self-models,
  metacognitive monitoring, reflective continuity, and the Level 6 expert-fleet
  improvement control plane.
- Added an explicit product framing for Deepr as a deep research and
  understanding loop: evidence compiles into beliefs, gaps, contradictions,
  confidence, provenance, temporal context, and a next learning plan.

### Changed
- Refreshed release-facing docs for v2.24.0, including current test-count
  floors, roadmap status wording, and no-attribution plain-ASCII documentation
  hygiene.
- Moved the legacy root-level MCP checklist into
  `docs/MCP_A2A_INTEROP_CHECKLIST.md`, refreshed it against current official
  MCP, A2A, and agentic AI security guidance, and linked it from the docs index.
- Clarified MCP expert-chat guidance for external agents: no-metered
  single-expert advice now uses `deepr_consult_experts` with one explicit expert
  and `synthesis_backend=local|plan`, while `deepr_query_expert` is labeled as
  the legacy metered-capable chat path until the backend-neutral runner exists.
- Refreshed the expert-chat backend design with 2026 multi-agent findings:
  bounded orchestrator-worker collaboration, specialists-as-tools, visible MCP
  cost and no-fallback contracts, A2A task artifacts, and preserved dissent as
  the default council behavior.
- Refreshed user-facing docs for the compiled expert memory loop: README usage,
  the expert guide, supported-surface contract, schema registry docs, and
  ROADMAP order now distinguish shipped compiler, memory-card, collaboration,
  and recall surfaces from the future graph commit envelope.
- `ExpertProfile.get_manifest()` now reads synthesis worldview and decision-log
  files through the canonical expert directory, so generated self-model and
  memory-card surfaces do not miss state for display names that slug differently
  on disk.
- Reworked the README as a concise front door, moved capacity operations into
  `docs/CAPACITY.md`, added a provider-costing deep dive for cached-token
  buckets, server-side tool costs, exact provider settlement, tier modifiers,
  and cache-control preconditions, and refreshed tracked text files to remove
  literal em/en dash characters.
- API provider cost accounting now records cached OpenAI/Azure/xAI input,
  Anthropic cache creation and cache read buckets, Gemini large-context input
  and output tiers, and current Grok 4.20 token rates from provider usage
  details before ledger settlement.
- Sync learning loop records now carry bounded read-only self-model metadata in
  `run_context.self_model`, and sync capacity wait/block payloads expose the
  same compact block when an expert profile is available. This uses the shared
  self-model context builder, keeps `next_action` action-only, and does not
  mutate expert goals, prompts, or state.
- `deepr expert consult` perspective context now includes bounded read-only
  self-model metadata when the expert profile exists. The embedded block carries
  current goals, calibration, blocker/risk counts, and the current-focus packet
  for traces and host handoffs without changing synthesis prompts or mutating
  expert state.
- Tightened the flake8-bandit ratchet baseline from 97 findings to 96 after
  replacing a silent council progress-callback no-op with debug logging.
- `deepr expert consult` now prefers stored belief context for expert
  perspectives before falling back to a live expert chat session. Explicit
  expert names are resolved through profile display names and slugs, and
  auto-selection uses normalized profile terms so "agentic" queries route to
  agent experts more reliably without using lexical checks as truth verdicts.
- `deepr-consult-v1` perspective artifacts now include optional context
  metadata when available: context source, stored-belief selection reason,
  included and available belief counts, and matched query terms. This makes
  consult runs easier to replay and turn into eval cases without changing the
  human-rendered CLI output.
- Expert council synthesis now accepts an injected local or plan-quota
  chat-completions client. Local and plan-quota synthesis report `$0` cost,
  while the default metered synthesis path still records actual cost through
  the canonical ledger.
- MCP `deepr_consult_experts` now exposes `synthesis_backend=api|local|plan`,
  `local_model`, `plan`, and `plan_model`, and returns a `capacity` block so host
  agents can verify whether live metered fallback was disabled.
- Owned-capacity consult modes skip paid-budget reservation when live metered
  fallback is disabled, so `$0` local or explicit plan consults remain usable
  even after the metered API budget is exhausted.
- Web-grounded expert bootstrap now defaults to DuckDuckGo instead of the
  `auto` search backend, so hidden Brave or Tavily keys in a developer shell are
  not consumed by surprise.
- Topic-based `deepr expert learn "Expert" "topic"` now routes through the
  verified live-web absorption pipeline by default. Use `--plan <id>` for an
  explicit plan-quota backend or `--model` for a local Ollama model; `learn-web`
  remains as an explicit compatibility verb.
- Local and plan-backed absorbers now inject `estimated_cost=0.0`, so expert
  profile spend accounting stays aligned with the canonical `$0` ledger events
  for owned or prepaid capacity.
- The roadmap now frames expert improvement as a research-processing compiler:
  source packs become atomic beliefs, typed temporal graph edges,
  contradiction and gap agendas, and regenerated wiki/digest views instead of
  passive document accumulation.
- Report-absorbed belief creation events and auto-related graph edges now carry
  report provenance, making `expert why`, digest, and handoff views more
  replayable from the original source pack.
- README security and project-footer copy now uses GitHub-native contact
  surfaces, and package/public docs keep authorship as Nick Seal with GitHub
  identity `blisspixel`.
- Distillr's first-party MCP profile now classifies all 27 live tools from the
  installed `distill-mcp` server. Free existing-corpus reads remain
  auto-approved, while corpus synthesis, derived-export writes, ingestion,
  refresh, and watch-list mutation stay approval-gated.
- Roadmap and agentic-balance docs now treat Level 5/6 expert maturity as
  self-improvement under verification gates: trace first, update a bounded
  self-model and learning plan, evaluate, then promote only measured
  improvements.

### Fixed
- Blocked legacy expert chat before its first direct model path when the session
  budget cannot cover the selected-model estimate, including the streaming chat
  path. This keeps zero-budget remote single-expert calls from reaching a
  metered chat completion before denial.
- Fixed GitHub secret-scan drift where historical redaction-test fingerprints
  could pass locally but fail in CI. The scan now relies on an explicit
  default-extending config and the current `main` security job is green.
- Allowed `deepr expert consult --local --budget 0` and
  `deepr expert consult --plan <id> --budget 0` to run through the documented
  no-metered synthesis path while keeping API-backed consults positive-budget
  only.
- Changed `deepr mcp test` to use only read-only `$0` MCP calls. It no longer
  probes `deepr_query_expert`, which can reach expert chat and spend despite a
  caller intending a no-cost diagnostic.
- Fixed HTTP scoped-key authorization so MCP protocol handshakes
  (`initialize`, `tools/list`) are not treated as sensitive tool calls requiring
  `_approved=true`; scoped keys still enforce approval and budget gates on
  actual `tools/call` requests.
- Hardened self-model update evidence refs so accepted prefixes must also carry
  a non-empty value, and malformed local review records fail closed before an
  acceptance artifact can be emitted.
- Changed monitor-generated gap/eval promotion recommendations to preview-first
  commands so copied recommendations do not apply local state changes without
  an explicit operator decision.
- Research submissions now reserve estimated cost before provider dispatch,
  refund the reservation on submit failure, and settle the append-only cost
  ledger from provider-reported completion usage instead of treating the
  preflight estimate as final spend.
- Fixed Windows malformed UNC-like path normalization so drive-less forms such
  as `\\0` normalize to the current drive root instead of returning a
  non-absolute `WindowsPath('//0')`.
- The free DuckDuckGo retrieval path now retries with exponential backoff (3
  attempts) instead of a single attempt. DuckDuckGo rate-limits aggressively, so
  one transient failure was degrading to "no sources -> no report" and starving
  `$0` expert maintenance; a bounded retry recovers most transient rate limits
  before falling back.
- Belief extraction now de-references source pointers: a claim states the bare
  domain fact ("Llama 3.1:8B is a tier-1 model for 8-12GB VRAM") instead of
  copying the report's citation numbering ("Source [5] lists ..."), and never
  emits meta-commentary about the author/assistant's own knowledge or limits.
  Provenance still lives in `evidence`/`evidence_refs`.
- Fixed Claude plan synthesis on Windows: a multi-line synthesis prompt passed as
  a `claude.cmd` argument was mangled by cmd.exe, so Claude saw an empty task and
  answered conversationally at `$0`. The prompt now goes over stdin.
- Fixed a false-exhaustion bug: the plan-quota client scanned the whole CLI
  output for keywords like "rate limit"/"quota"/"credits", so a good report about
  provider rate limits was misread as a depleted plan and a bogus EXHAUSTED event
  was written. Exhaustion is now scoped to the error channel (stderr on success,
  everything on failure); the answer body is never scanned.
- Council synthesis now records its model cost in the canonical append-only cost
  ledger instead of returning a cost only in the consult payload.
- Council synthesis parsing now keeps `DISAGREEMENTS` separate from
  `AGREEMENTS`; the previous substring order could classify disagreement
  bullets as agreements.
- Council synthesis parsing now normalizes Markdown-bold bullet labels so local
  model outputs like `- **Topic**: detail` do not leave stray emphasis markers
  in agreement or disagreement artifacts.
- Plan-quota CLI execution now normalizes NUL bytes in argv text and drops
  invalid subprocess environment entries before launch. Fresh web context or
  cleared environment variables can no longer make an otherwise valid
  plan-quota run fail before the vendor CLI starts.
- Plan-quota CLI execution now resolves Windows `PATHEXT` launch targets such as
  `codex.cmd`, removes metered API-key variables from child environments, and
  sends Codex prompts through stdin so long fresh-context prompts do not exceed
  the Windows command-line limit.
- Expert sync now treats Markdown-wrapped `no significant changes` responses as
  no-change markers instead of absorbing them as domain beliefs. Report
  absorption also rejects exact no-change meta statements as non-domain claims.
- Report absorption now preserves scalar model `evidence` output as one excerpt
  instead of splitting it into character refs. This keeps provenance,
  source-trust ceilings, and grounding-check prompts aligned when a model
  returns a string despite the requested evidence array.
- Expert health checks now treat heuristic-only contradiction candidates as
  advisory `info` instead of creating a capacity action. Recorded contested
  pairs still produce a warning and an adjudication action, and small gap
  backlogs no longer block scheduled health loops.

## [2.23.0] - 2026-06-25

Claude quota metadata release.

### Added
- Added `deepr capacity refresh-quota claude`, a metadata-only `$0` probe that
  reads Claude Code OAuth usage windows when the current user has Claude Code
  configured. The command normalizes five-hour, weekly, and Opus weekly windows
  into the shared `QuotaSnapshot` contract and records a conservative
  quota-ledger observation without running a model call or storing credential
  material.

### Changed
- Added a roadmap gate for API provider prompt-cache economics across Anthropic,
  OpenAI/Azure, Gemini, and xAI. Cache controls stay planned until estimator
  support, actual usage accounting, and explicit budget gates prove they reduce
  spend instead of adding cache-write or pre-warm costs.

## [2.22.0] - 2026-06-25

Codex quota metadata release.

### Added
- Added a normalized plan-quota snapshot contract for live quota probes. Provider
  windows now have a pure binding-window/headroom calculation and can be
  converted into conservative quota-ledger events before any automatic routing
  trusts them.
- Added `deepr capacity refresh-quota codex`, a metadata-only `$0` probe that
  reads Codex local session-log `rate_limits` and records a trusted
  quota-ledger observation without running a model call.

## [2.21.0] - 2026-06-25

Handoff assurance and CI refresh release.

### Added
- Added maker-checker assurance to host-facing expert handoff payloads.
  `Claim` now preserves `grounding_assurance` from belief state, and
  `deepr-expert-handoff-v1` includes per-claim assurance plus summary counts for
  verified and cross-vendor verified claims.

### Changed
- Updated pinned GitHub Actions workflow dependencies to
  `actions/checkout@v7.0.0` and `astral-sh/setup-uv@v8.2.0`.
- Corrected package runtime author metadata to `Nick Seal`; GitHub repository
  identity remains `blisspixel/deepr`.

## [2.20.0] - 2026-06-22

Licensing, safe-defaults, and model-freshness release.

### Changed
- **License** finalized to plain **Apache 2.0** (the interim Commons Clause
  rider was removed); `LICENSE`, `pyproject.toml`, and the README now agree.
- **Lower, coherent default budget caps** so a fresh install can't quietly run
  up a large bill: the web dashboard and local REST API now default to
  per-job **$5**, daily **$10**, monthly **$20** (previously $20 / $100 /
  $1000). The cost-intelligence sliders were rescaled to matching personal-use
  ranges. Existing saved limits and the `DEEPR_PER_JOB_LIMIT` /
  `DEEPR_DAILY_LIMIT` / `DEEPR_MONTHLY_LIMIT` env overrides are unchanged.
- **OpenAI task-model defaults bumped to `gpt-5.5`** (the current flagship) for
  the metered chat / synthesis / planning / documentation / strategy tasks,
  replacing the stale `gpt-5.2` defaults. Pricing is unaffected (`gpt-5.5` is
  registered).
- **README** reformatted to the conventional layout - title, badges, and
  tagline lead; license and authorship details move to the License section at
  the foot of the document.

### Fixed
- Reconciled the parallel `core/settings.py` configuration with `config.py`:
  its `TASK_MODEL_MAP`, `synthesis_model`, and OpenAI env default were left on
  `gpt-5.2` when `config.py` moved to `gpt-5.5`, so the two config systems
  disagreed on the default model. Both now resolve to `gpt-5.5`.
- Committed the `uv.lock` update for the maintained `ddgs` web-search
  dependency so locked and declared dependencies match.

## [2.19.0] - 2026-06-20

Red-team trend artifact release.

### Added
- Added `deepr eval red-team --save`, which writes local `$0` attack-success
  reports under `data/benchmarks/red_team_*.json` and includes `saved_to` in
  JSON output for release-to-release trend tracking.

## [2.18.1] - 2026-06-20

MCP read-boundary hardening patch release.

### Added
- Extended `deepr eval red-team` with `$0` MCP handoff and loop-status
  read-path canaries, bringing the built-in suite to 13 blocked cases.

### Security
- Added host-facing payload sanitization for derived MCP expert handoff and
  loop-status reads so directive and tool-spoof canaries are neutralized before
  downstream host agents consume the JSON payload.

## [2.18.0] - 2026-06-20

Agentic red-team metric release.

### Added
- Added `deepr eval red-team`, a local `$0` agentic red-team verifier that
  reports attack-success-rate across built-in prompt-injection, jailbreak,
  data-exfiltration, tool-spoofing, and memory trust-floor probes.

### Security
- Prompt sanitization now neutralizes structured untrusted `tool_call`,
  `function_call`, and `tool_result` markers before source text is embedded in
  prompts.

## [2.17.2] - 2026-06-20

Prompt-boundary security hardening patch release.

### Security
- Added an untrusted-content prompt wrapper to `PromptSanitizer` and applied it
  to fresh retrieval context, report absorption prompts, first-party tool
  findings, local document review previews, campaign context summarization,
  completed-research review, company-intelligence reuse, and team-result
  synthesis so embedded source directives are delimited and neutralized before
  model use.

## [2.17.1] - 2026-06-20

Contract-validation and dependency-security patch release.

### Added
- Added published scheduler JSON contracts for recurring expert maintenance:
  `deepr-scheduled-gap-fill-wait-v1`,
  `deepr-scheduled-reflection-wait-v1`,
  `deepr-health-check-action-plan-v1`, and
  `deepr-health-check-archive-confirmation-v1`, with runtime payload stamps,
  registry entries, and schema-validation coverage.
- Added runtime MCP output-contract validation for `deepr_expert_handoff` and
  `deepr_expert_loop_status`; malformed published payloads now fail closed with
  `SCHEMA_VALIDATION_FAILED` before host agents consume them.
- Added `deepr-a2a-task-v1` to the published schema registry and runtime
  validation to A2A task create/status/cancel responses; malformed task/result
  envelopes now fail closed with `SCHEMA_VALIDATION_FAILED`.

### Security
- Updated locked `msgpack` to `1.2.1` to resolve GHSA-6v7p-g79w-8964 from
  the transitive `cachecontrol[filecache]` dependency.

## [2.17.0] - 2026-06-20

Loop/interchange, hosted MCP foundation, and schema-contract release.

### Added
- Added the first v2.17 durable loop substrate: schema-versioned
  `ExpertLoopRun` records, an append-only per-expert loop-run store, and
  read-only `deepr expert loop-status`.
- Added `deepr_expert_loop_status`, a read-only MCP tool for host agents to
  inspect durable expert loop runs, stop reasons, budget/capacity source,
  verifier fields, acceptance metrics, and next actions.
- Added `deepr_expert_handoff` and `/api/experts/{name}/handoff`, a `$0`
  read-only `deepr-expert-handoff-v1` payload for downstream agents. It includes
  profile summary, manifest counts, bounded claims/gaps, dashboard telemetry,
  loop-status rollup, OKF interchange hints, and an additive compatibility
  contract, with JSON Schema published under `docs/schemas/`.
- Added `deepr-loop-status-v1`, `deepr-okf-profile-v1`, and
  `docs/schemas/registry.json` so downstream agents can validate durable loop
  status and the OKF mapping contract with an additive compatibility policy.
- Added `deepr-mcp-remote-audit-v1` and registered it in
  `docs/schemas/registry.json` so hosted MCP remote-call audit records have a
  published additive compatibility contract.
- Added `docs/SUPPORTED_SURFACE.md`, a supported-surface statement covering
  stable, experimental, visible/read-only, planned, export, and compatibility
  guarantees for users and host agents.
- Added the first hosted-MCP scoped-key primitive: `ScopedMCPKeyStore`, HTTP
  transport enforcement for key mode, expert allowlists, confirmation
  requirements, and append-only `deepr-mcp-remote-audit-v1` events for
  authenticated remote tool calls.
- Added `deepr mcp keys create/list/revoke` for local scoped-key management.
  Created secrets are shown once, list output omits secrets and hashes, and
  revoked keys are rejected by the HTTP scoped-key authenticator.
- Added per-key budget enforcement for scoped HTTP MCP calls. The transport now
  sums prior audited key spend, blocks calls whose requested budget or fixed
  estimate exceeds the remaining key budget, injects remaining budget into
  budget-aware tools when omitted, and records successful response costs in the
  remote audit log.
- Added fail-closed scoped-key spend coverage for metered remote MCP tools. If
  a budgeted scoped call targets a metered tool without a deterministic estimate,
  the transport denies it before handler dispatch with
  `KEY_BUDGET_ESTIMATE_UNAVAILABLE`.
- Added per-key rate limits for scoped HTTP MCP calls. Key records can now carry
  a calls-per-minute ceiling, `deepr mcp keys create --rate-limit` exposes it,
  and the HTTP transport blocks over-limit calls before tool dispatch with
  retry metadata and an audited denial.
- Added a global HTTP MCP concurrency cap. `deepr mcp serve --http` now limits
  simultaneous POST requests to `DEEPR_MCP_HTTP_MAX_CONCURRENCY` or 32 by
  default, returns 429 with retry metadata when full, and exposes
  `--max-concurrency` for operators.
- Added `deepr mcp audit list`, a read-only local CLI for reviewing
  `deepr-mcp-remote-audit-v1` remote-call audit records with key, tool, outcome,
  limit, and JSON filters.
- Added `deepr mcp audit summary`, a read-only aggregate view over the same
  remote-call audit log with counts and audited cost grouped by key, tool, and
  outcome.
- Added `deepr mcp serve --http`, a Streamable HTTP/SSE serve mode for the
  existing MCP server. It defaults to loopback and relies on the HTTP
  transport's shared-token or scoped-key gates for reachable binds.
- Added `deepr mcp smoke-http`, a `$0` HTTP MCP endpoint smoke check covering
  health, initialize, tools/list, and free `deepr_tool_search` dispatch for
  local or TLS-proxied endpoints.
- Added `deepr mcp registration-manifest`, a token-redacted
  `deepr-mcp-registration-manifest-v1` endpoint packet for remote host setup
  that can embed the `$0` HTTP smoke result without serializing bearer secrets.
- Added `deploy/mcp-http.md`, a hosted MCP reverse-proxy recipe covering
  scoped keys, loopback service binding, Caddy/nginx TLS termination, smoke
  validation, revocation, and operational guardrails.
- Added `deploy/mcp-http/`, a hosted MCP HTTP container recipe with a dedicated
  Dockerfile, compose service, `.env.example`, scoped-key bootstrap steps,
  loopback-only host publishing, and `$0` smoke validation guidance.
- Added `deploy/mcp-http/azure-container-apps/`, an Azure Container Apps
  template for the hosted MCP HTTP container with persistent `/data` on Azure
  Files, HTTPS-only ingress, scoped-key state, and remote-audit durability.
- Added `deploy/mcp-http/aws-ecs-fargate/`, an AWS ECS Fargate template for the
  hosted MCP HTTP container with HTTPS ALB ingress, EFS-backed `/data`,
  scoped-key state, remote-audit durability, and the same concurrency cap
  contract as the local and Azure recipes.
- Added `deploy/mcp-http/gcp-cloud-run/`, a GCP Cloud Run template for the
  hosted MCP HTTP container with a Cloud Storage FUSE-backed `/data`, scoped-key
  state, remote-audit durability, optional public invoker binding, and
  single-writer defaults for object-backed key and audit files.
- Added `deploy/mcp-http/cloudflare-worker/`, a Cloudflare Worker edge ingress
  recipe for hosted MCP that requires an HTTPS origin, proxies only `/mcp`
  paths, caps request bodies at 1 MiB, forwards scoped-key auth headers, and
  keeps provider keys, scoped-key state, and audit logs on the origin side.
- Added cross-surface MCP allowlist enforcement contract tests. They cover the
  union of visible registry tools and JSON-RPC dispatch tools across every
  `ResearchMode`, including scoped-key authorization and the JSON-RPC
  pre-dispatch block/confirmation gates.
- Added `deepr-cli-operation-result-v1` to the published schema registry and
  versioned the shared CLI `OperationResult` JSON envelope with `schema_version`
  and `kind`.
- Added `deepr-capacity-next-v1` to the published schema registry. The
  `deepr capacity next --json` command and scheduled sync wait payloads now
  share the same versioned, read-only `$0` capacity guidance object.
- Added `deepr-sync-capacity-gate-v1` for the outer `deepr expert sync` capacity
  wait/block payload, including the embedded `deepr-capacity-next-v1` guidance
  object and optional loop-run record.
- `deepr expert loop-status --json` and `deepr_expert_loop_status` now return
  the shared `deepr-loop-status-v1` rollup payload, matching the web loop-status
  API contract instead of emitting smaller ad hoc run lists.
- Tightened expert chat session-budget coordination for deep research. Session
  budget exhaustion and open session circuit breakers now return blocked
  responses with session-specific metadata before any provider call, and
  regression tests cover manager propagation plus standard/deep research
  preflight behavior.
- Scheduled expert wait and action-plan surfaces now append `ExpertLoopRun`
  snapshots and include a `loop_run` object in JSON output for `sync`,
  `route-gaps`, `reflect`, and `health-check`.
- Successful `deepr expert sync` runs now append completed or failed
  `ExpertLoopRun` snapshots with trigger, budget spent, capacity source, accepted
  change count, and next action for failed topics.
- Non-dry `deepr expert route-gaps --execute` runs now append gap-fill
  `ExpertLoopRun` snapshots with trigger, budget spent, capacity source,
  accepted changes, typed failure stops, and human-gate or budget stop actions
  when routed gaps are deferred or skipped.
- `deepr expert reflect` now appends reflection `ExpertLoopRun` snapshots with
  verifier outcome, score, model version, typed verifier-failed stops, and
  follow-up absorption metrics when `--execute-followups` runs.
- `deepr expert health-check` and confirmed `--archive-stale` runs now append
  health-check `ExpertLoopRun` snapshots with verifier outcome, recommended
  action state, accepted archival counts, and typed stops for critical reports,
  capacity waits, confirmation gates, or no corrective work.
- Added `/api/experts/{name}/loop-status`, a read-only dashboard API rollup over
  durable expert loop runs with latest run, last sync result, waiting scheduled
  action, failure, capacity source, spend, acceptance, and verifier failure
  metrics.
- The loop-status dashboard API now includes `expert_state` telemetry for
  profile freshness, 7-day and 30-day gap velocity, top open gaps, and
  contested/open claim counts from manifest links and belief contradiction
  edges.
- `ExpertLoopRun` now enforces the loop completion contract: completed, failed,
  and cancelled runs require typed stop reasons, and waiting, completed, failed,
  and cancelled states reject stop reasons that do not match their status.
- Added `LoopAdmissionContract` and dashboard `admission_contracts` so loop
  surfaces expose the four admission gates: repeat demand, automated
  verification, explicit budget/capacity, and failure-diagnosis state. Gap-fill
  remains supervised until gap-closure verifier evidence is recorded.
- Added `deepr expert export-okf NAME PATH`, a `$0` regenerated OKF Markdown
  bundle over structured expert state. It writes `index.md`, `log.md`, concept
  pages, citations, typed relations, gaps, contested claims, and optional
  `llms.txt`, with marker-based overwrite protection so the bundle remains an
  interchange view rather than authoritative state.
- Added `deepr expert absorb-okf NAME PATH`, which parses OKF concept Markdown
  and frontmatter into source text for `ReportAbsorber`. The existing
  extraction, grounding, dedup, and contradiction gates decide what enters the
  belief store, so OKF Markdown is never trusted as canonical state.
- Added `deepr expert health-check --scheduled`, which emits a scheduler action
  plan for recommended actions, and made `--archive-stale --scheduled` wait for
  explicit confirmation instead of prompting or mutating unless `--yes` is set.
- Added `deepr expert reflect --scheduled`, which validates the local report
  lookup and then returns a structured wait payload before any reflection
  evaluator or follow-up research can run from a recurring scheduler job.
- Added `deepr expert route-gaps --execute --scheduled`, which returns pending
  routes plus a wait state instead of starting metered gap-fill research from a
  recurring scheduler run.
- Added `deepr expert sync --scheduled`, a scheduler-facing capacity gate that
  waits with structured `capacity next` actions instead of falling through to
  metered API when a due recurring sync lacks owned/prepaid capacity. Explicit
  `--api` remains the operator override.
- Added concrete job previews to `deepr capacity next`: `--expert`,
  `--report-id`, `--context-mode none|fresh|deep`, and `--scheduled` fill the
  suggested command shape and show wait guidance when a fresh/deep scheduled
  sync should wait for cheap local capacity instead of falling through to
  metered API.
- Added `deepr expert make --local`, a provider-free expert creation path that
  records `provider=local`, copies optional seed documents into the expert's
  local documents folder, and prints the next `subscribe` plus
  `sync --local --fresh-context` commands for $0 maintenance.
- Added `deepr capacity next`, a read-only `$0` guidance surface that ranks
  the current capacity block reason, local setup steps, latest usable eval
  artifact admission, eval refresh, and explicit metered fallback for a task
  class.
- Added saved local eval artifact admission:
  `deepr capacity admit --from-eval <path|latest> --task-class <task>` loads
  `deepr eval local --save` output, validates zero Deepr metered cost, score
  ranges, minimum score, model match, and failed prompt results, then records
  the selected model's score and artifact summary in the machine-local
  admission ledger.
- Added free-only fresh retrieval context for local expert sync:
  `deepr expert sync NAME --local --fresh-context` fetches explicit URLs and
  DuckDuckGo results when the optional package is installed, prepends bounded
  source context to the local Ollama prompt, and keeps Deepr metered cost at
  `$0` without invoking API-key search providers.
- Added bounded local deep context for expert sync:
  `deepr expert sync NAME --local --deep-context` runs multi-query free
  retrieval before the local Ollama call, de-duplicates URLs, records source
  pack metadata, supports `DEEPR_SEARXNG_URL` for a self-hosted SearXNG search
  endpoint, and keeps the no-source path as `no_changes` instead of absorbing
  unsupported local claims.
- Added `$0` local context evaluation via `deepr eval local-context`. It
  compares no context, fresh context, and deep context for one local model,
  uses a local model as the judge, records source and citation metadata, and can
  save a JSON artifact under `data/benchmarks` without invoking provider APIs.
- Added source-pack artifacts for context-bearing expert sync runs. Local
  fresh/deep sync now writes a bounded JSON source pack under the expert
  knowledge directory, includes the artifact path and source summary in sync
  outcomes, and blocks absorption if the source trail cannot be persisted.
- Added `$0` local Ollama comparison via `deepr eval local`. It compares local
  models on an agentic-loop prompt set, uses a local model as the judge, reports
  score, latency, winner, and cost, and can save a JSON artifact under
  `data/benchmarks` without invoking provider APIs.
- Added explicit CLI judge support to `deepr eval local`: `--judge-cli grok`
  for the installed Grok CLI shape and `--judge-command` for other headless
  subscription CLIs. CLI judges require `--allow-cli-judge`, receive prompts
  through a temp file, run with shell execution disabled, and are never selected
  implicitly because the external CLI may consume its own quota.
- Added pure backend selection for the capacity waterfall. The selector orders
  normalized backends `local -> plan_quota -> api_metered`, reuses eligibility
  decisions, enforces optional measured quality floors, and returns structured
  candidate reasons without invoking adapters, vendor CLIs, or provider APIs.
- Added pure backend eligibility decisions over `ResearchBackend` plus observed
  `QuotaState`, covering unavailable backends, unsupported task classes,
  metered budget gates, missing or unknown quota, exhausted windows,
  quarantines, overage-enabled plan backends, reserve floors, and
  multi-account eligible-account selection without invoking vendor CLIs or
  provider APIs.

### Changed
- Corrected `deepr_expert_validate` tool discovery metadata from `free` to
  `low` so the advertised MCP cost tier matches the implementation's paid
  validation call.
- `expert sync --local` now keeps the full maintenance loop local by passing a
  local Ollama-backed absorber into the sync engine. Fresh-context syncs with
  zero retrieved sources now record no changes instead of absorbing the local
  model's uncertainty as beliefs.
- Fresh/deep context flags now require a local sync backend. If no admitted
  local model is available and `--local` was not provided, Deepr stops instead
  of silently falling through to a metered API backend.
- Clarified README, feature docs, roadmap, capacity design, and agent
  instructions so local Ollama, APIs, plan CLIs, and explicit CLI judges are
  described by their current shipped status instead of blended together.
- Automatic local routing now feeds admitted scores into the runtime quality
  floor. Scoreless manual admissions remain visible but no longer take over
  `expert sync` or `expert absorb` automatically; `--local` remains the
  explicit override.
- Aligned the capacity README, roadmap, changelog, and design notes so the
  README stays as the front-door summary, the roadmap stays forward-facing, and
  release history remains in the changelog.

### Fixed
- Corrected the built-in search backend wrapper to pass structured query
  arguments to `WebSearchTool` instead of a positional dict.
- Restored the blocking C901 code-health ratchet by extracting the new loop-run
  validation, OKF absorption setup, MCP HTTP dispatch, scoped-key checks, and
  remote-call cost extraction branches into smaller helpers without changing
  behavior.
- `deepr search "query"` now dispatches to `deepr search query "query"` instead
  of surfacing Click's generic "No such command" message, and `deepr expert
  list` labels names and descriptions so roster output is easier to scan.
- `deepr_query_expert` now passes the caller's budget into `ExpertChatSession`
  for normal expert answers, not only for `agentic=true`, so remote scoped
  budgets and explicit low ceilings cap model-token spend on plain expert
  queries too.
- Corrected the built-in browser backend to use the existing scraper fetcher and
  content extractor instead of a missing `scrape_url` helper.

## [2.16.2] - 2026-06-17

Capacity-ledger and CI reproducibility patch release.

### Added
- Added the append-only capacity quota ledger
  (`data/capacity/quota_ledger.jsonl`, overrideable with
  `DEEPR_CAPACITY_DATA_DIR`) and surfaced the latest observed quota state in
  `deepr capacity` / `deepr capacity --json` without invoking vendor CLIs or
  provider APIs.

### Fixed
- Prevented the web background poller from starting under Flask `TESTING`
  mode, so the unit suite does not leave a daemon poller running during
  interpreter shutdown.
- Added the PyYAML type stub package to dev dependencies so the documented
  strict mypy gate is reproducible from a fresh dev install.

## [2.16.1] - 2026-06-17

Bug and security hardening patch release.

### Fixed
- Prevented rapid back-to-back belief events from being skipped on
  filesystems or clocks with equal timestamp granularity by making event
  timestamps monotonic per store.
- Normalized offset-aware cost ledger timestamps to UTC before daily, monthly,
  and custom range bucketing.
- Closed unstarted dispatcher coroutines on dependency failure, cancellation,
  timeout, and fanout shutdown so cancelled task graphs do not leak runtime
  warnings.
- Corrected stale docs and CLI references from deprecated `deepr cost` to
  `deepr costs`.

### Security
- Hardened Azure blob storage report paths by validating job IDs and filenames
  before blob name construction and skipping malformed legacy blob names during
  listing.
- Tightened local report storage filename validation and removed
  substring-based report directory lookup so unrelated readable report names
  cannot be selected by crafted IDs or prompt slugs.

## [2.16.0] - 2026-06-16

Packaging, repo-hygiene, and security release.

### Changed
- Adopted the canonical PyPA **src layout**: the package now lives at
  `src/deepr/` (import name `deepr` unchanged). This prevents accidentally
  importing the package from the working directory instead of the installed
  one. Packaging, CI, code-health scripts, and docs updated accordingly.

### Fixed
- Corrected `.mailmap`, which was reversed and relabelled the maintainer's own
  commits as a third-party GitHub user on the contributor graph. Automation/AI
  emails now coalesce onto the maintainer; no bot appears as a contributor.
- Security: `BeliefStore` now containment-checks the expert name before using
  it as a path component (it is constructed directly from MCP tool args), so a
  traversal name cannot escape the experts root.
- Security: web/API error responses no longer echo exception text to clients
  (generic message client-side, detail logged server-side).

### Security
- Triaged all open CodeQL alerts (multi-agent triage + adversarial
  verification): real findings fixed with tests, false positives dismissed with
  documented reasons. Added `validate_identifier` + `safe_path_within` helpers
  in `utils/security.py`.
- Hardened GitHub Actions with least-privilege `permissions: contents: read`
  on the CI and mutation workflows; all actions pinned to commit SHAs.

## [2.15.1] - 2026-06-16

Security and maintenance release. No functional changes.

### Security
- Cleared all 9 npm advisories in the web frontend (0 vulnerabilities
  remaining): Vite 5 -> 8 with esbuild (GHSA-67mh-4wv8-2f99,
  GHSA-gv7w-rqvm-qjhr), react-syntax-highlighter 15 -> 16 with prismjs
  (GHSA-x7hr-w5r2-h6wg), ws 8.21 (GHSA-96hv-2xvq-fx4p), @babel/core 7.29.7
  (GHSA-4x5r-pxfx-6jf8), and form-data 4.0.6 (GHSA-hmw2-7cc7-3qxx).
- Python security bumps: aiohttp 3.13.5 -> 3.14.1, cryptography 48.0.0 ->
  48.0.1.

### Changed
- Frontend dependency refresh, verified green (lint/tsc/build):
  @vitejs/plugin-react 6, TypeScript 6, framer-motion 12, sonner 2,
  tailwind-merge 3, zustand 5. Dropped the deprecated tsconfig `baseUrl`
  (TS 6 resolves `paths` without it). Routine pip bumps: openai,
  azure-cosmos, flask-limiter, rich, google-genai, react-markdown.

### Build
- Pinned all GitHub Actions to commit SHAs and normalized setup-uv to v7
  (supply-chain hardening). Documented the branch, merge, and hygiene
  policy in CONTRIBUTING.

## [2.15.0] - 2026-06-14

### Changed
- Absorb contradiction and dedup are now agentic, not brittle. The free
  word-overlap heuristics only *route*; a cheap model verdict concludes
  (`AGENTIC_BALANCE.md`). A phrasing-level false contradiction is absorbed
  normally instead of recorded as a false contested belief, and two different
  facts that merely share words (e.g. "$10/M" vs "$30/M") are no longer silently
  merged into one (data loss). The verdict is authoritative for the graph too (no
  lexical contradiction edge is re-created behind it), and the absorb result
  reports how many false positives the verdicts caught (`contradictions_refuted`,
  `merges_blocked`). Cost-bounded (uncertain band only), reuses the extraction
  client, every existing caller unchanged.
- Removed a regex "atomicity monitor" that classified claim atomicity with
  word-markers: atomicity is meaning, the extraction model's job, not a lexical
  rule (the brittle-rule-for-meaning anti-pattern).

### Fixed
- No-surprise-bills: `ExpertChatSession` did `budget or 10.0`, so an explicit
  `budget=0.0` ("do not spend") silently became a $10 ceiling (0.0 is falsy). A
  `deepr expert chat --budget 0` caller, or an agent passing 0, got a real
  budget. Now `None` means default ($10) and `0.0` is honored; the MCP
  `query_expert` default flips `0.0 -> None` so unspecified still defaults sanely.
- Tests polluted the user's real `data/experts/` (leaking `MagicMock`,
  `test_expert`, and stray expert dirs): the experts root was the one isolation
  the suite lacked. Added an autouse fixture pinning `DEEPR_DATA_DIR` to a
  per-test tmp dir.
- `eval continuity` on an expert that exists but has no beliefs yet wrongly said
  "Create or learn an expert first", and a typo'd name created an empty belief
  dir. Now checks the profile exists first (read-only) with accurate per-case
  messages.
- `costs doctor` reported "Issues found (1/3)" on a healthy ledger-only setup
  because the *derived* `cost_log.json` view did not exist. The view is
  regenerable from the canonical ledger, so its absence is informational, not a
  failure.
- Unified the reports root across every component. Config-driven writers
  (CLI `run`, web app) saved under `data/reports`, but `ContextIndex`
  scanned `./reports`, a no-arg `LocalStorage()` (used by `prep`, `team`,
  `retrieve_expert_reports`) wrote to `./reports`, and `company_research`
  fell back to a third root (`results`) - so a completed job could render
  "No report content available" in the web UI, and search/absorb could
  not see reports written elsewhere. Every no-arg default now resolves
  through `load_config()["results_dir"]` (one root, env
  `DEEPR_REPORTS_PATH` honored everywhere; default `data/reports`).
  Regression tests cover root agreement, env flow, save-then-scan
  visibility, and end-to-end web-API retrievability of a saved report.
- `mypy --strict` providers gate (blocking CI) broke against current
  Azure SDK releases: `azure-ai-projects` / `azure-ai-agents` now ship
  typed clients, so the lazily-assigned `self._project_client = None`
  inferred as `None`-typed and `project_endpoint: str | None` flowed into
  a `str` parameter. Narrowed the endpoint guard and annotated the lazy
  clients as `Any`; the gate is green against both old (untyped) and new
  (typed) SDKs.
- `tests/unit/test_core/test_company_research.py` only passed when
  `OPENAI_API_KEY` happened to be set (a dev `.env`, or another module's
  import-time `os.environ.setdefault` during full-suite collection - an
  inter-test ordering dependency). An autouse fake-key fixture makes the
  file self-sufficient on any machine and in any test ordering.

### Added
- Guided setup and a portable data directory (UX-first onboarding):
  - `deepr init` detects existing provider keys, writes `.env`, sets a
    budget ceiling, and can point storage at a synced folder. Scriptable
    and CI-safe: `--yes`, `--budget`, `--data-dir` (writes `DEEPR_DATA_DIR`
    / `DEEPR_EXPERTS_PATH` / `DEEPR_REPORTS_PATH`), no prompts required.
  - `deepr doctor` gains a severity model (ok / info / warning / error), a
    one-line `_summarize()` verdict, a storage-locations check, and a
    ranked "next step" so the most actionable fix is always surfaced.
  - One experts root: `config.experts_root()` is the single source of
    truth (`DEEPR_EXPERTS_PATH`, else `DEEPR_DATA_DIR/experts`, else
    `data/experts`), so setting one data dir relocates experts + research
    to a synced folder and they follow you across machines. ~12 experts
    modules were centralized onto it; a guard test prevents split-store
    regressions. Cost ledger, queue, and traces stay machine-local
    ([ADR 0004](decisions/0004-one-experts-root-and-portable-data-dir.md)).
  - `numpy` moved to core dependencies (it is imported at startup) with a
    CI `core-install` smoke job, so a base `pip install` no longer crashes
    on first run.
- Capacity visibility and $0 local-model execution (toward routing on
  owned/prepaid capacity before metered API):
  - `deepr capacity` (`--json`, `--probe`) reports detected capacity -
    local Ollama, plan-based CLIs, metered APIs - with a cost model, so you
    can see what runs for free before paying per token.
  - A local Ollama backend (`deepr/backends/local.py`) targets the
    OpenAI-compatible `/v1` endpoint and plugs into the injectable research
    seams; `deepr expert absorb --local` and `deepr expert sync --local`
    run extraction and sync at $0. Expert maintenance (absorb + sync) was
    extracted into its own module to keep file-size ratchets honest.
  - Routing **quality priors** (`deepr/routing/quality_priors.py`) seed
    provisional model rankings from published benchmark indices, so auto
    mode routes sensibly without every user paying for evals first.
  - Eval-gated local **admission** + automatic owned-capacity-first routing
    for expert maintenance: `deepr capacity admit <model> --task-class
    sync|absorb` records the operator's dated acceptance (default 90-day
    expiry; `admissions` / `revoke` to inspect and withdraw). Once a model
    is admitted, `deepr expert sync`/`absorb` run on it automatically at $0
    before any metered API call - the first wired rung of the waterfall.
    `--local` forces local with no admission; the new `--api` forces
    metered. The chosen backend and the reason are printed ("why did this
    run on X"). Admissions are machine-local (`DEEPR_CAPACITY_DATA_DIR`),
    not in the portable experts dir, since local capacity is per-machine.
    Selection is admission-driven and verified against live availability: the
    waterfall uses an admitted model only if Ollama currently has it loaded
    (checked via a new `available_local_models()`), so it is robust to model
    list order and does not depend on `DEEPR_LOCAL_MODEL` (which now only
    breaks ties among several admitted+available models). Validated end to end
    on a local 80B MoE (`qwen3-coder-next`): $0 context-grounded claim
    extraction, admit -> auto-route -> local, admitted-but-unloaded ->
    metered fallback.
  - `deepr capacity` now also detects **GitHub Copilot CLI** (`copilot`) and
    **Cursor CLI** (`cursor-agent`) as plan-quota sources, alongside Claude
    Code / Codex / Antigravity / Kiro.
  Design: [capacity-waterfall.md](design/capacity-waterfall.md).
- Evidence layer - making expert trust measurable rather than asserted:
  - `deepr eval continuity` scores staleness honesty, abstention,
    contradiction-surfacing, and what-changed exactness from stored belief
    state at $0.
  - `deepr eval calibrate` answers "does extraction confidence track
    grounding?" - reliability curve, expected calibration error, and a
    numpy Platt-scaling threshold (Newton-Raphson, no sklearn). `--from`
    grades existing pairs at $0; `--corpus` runs the paid extraction +
    strong-model pre-grade (FActScore/SAFE-style atomic decomposition,
    `--grader-model`, `--sample`, `--max-cost`, `--yes`). First measured
    curve committed in [docs/CALIBRATION.md](CALIBRATION.md).
  - The deterministic-vs-agentic check boundary is documented in
    [checks-deterministic-vs-agentic.md](design/checks-deterministic-vs-agentic.md)
    (deterministic for structure/types/ranges; model judgment for semantic
    grounding, contradiction, and atomicity).
- Install / update QOL, matching modern CLI tooling (claude / codex / grok):
  - `deepr upgrade` self-updates to the latest released version, detecting
    how deepr was installed (pipx / pip / editable source checkout) and
    running the right command. `deepr upgrade --check` reports whether a
    newer version exists (via the PyPI JSON API) without installing;
    degrades gracefully offline and for editable installs (prints git
    steps). No new dependencies (urllib + subprocess).
  - The install one-liners (`scripts/install.ps1`, `scripts/install.sh`)
    are now idempotent: re-running updates an existing install instead of
    failing, report the installed version, and support uninstall
    (`-Uninstall` / `-- --uninstall`). `scripts/install.bat` is modernized
    to delegate to install.ps1 (was stale: referenced Python 3.9).
- Agent-classifiable error envelope across every error surface (RFC 9457 /
  agent-error pattern), so a consumer can classify a failure and drive
  backoff without scraping the message:
  - `DeeprError` carries `category` (provider / auth / budget / config /
    storage / validation / internal) and a boolean `retryable`; `to_dict()`
    surfaces them plus `retry_after` (seconds, when known). Transient
    provider failures (timeout, unavailable, rate-limit) are retryable;
    auth/budget/config/validation are actionable and not.
  - The provider-layer `ProviderError` gains the same fields + `to_dict()`,
    plus a `classify_provider_exception()` helper that maps a raw provider-
    SDK exception to (category, retryable, retry_after) by class name
    (works across openai/anthropic/gemini/xai/azure without importing each).
    `ProviderError` auto-classifies from its `original_error` when the
    envelope is not set explicitly, so every adapter's existing
    `raise ProviderError(..., original_error=e)` gets correct classification
    with no per-site changes - the envelope is populated on every provider
    path, not just one adapter.
  - The MCP `ToolError` always emits `category` + `retryable` (and
    `retry_after` when known) and gains `ToolError.from_exception(...)`;
    `_make_error()` accepts the classification.
  - The CLI `OperationResult` JSON error output always carries `category` +
    `retryable` (+ `retry_after`), with `OperationResult.from_exception(...)`.
  Fully additive everywhere: existing keys (error/error_code/message/
  details, retry_hint/fallback_suggestion) are unchanged.
- CLI best-practices refinements (audited against clig.dev / kubectl / uv /
  Heroku conventions, mid-2026):
  - `deepr` with no arguments now prints help and exits 0 when stdin is not
    a TTY (a script, CI, or an AI agent driving the CLI), and only launches
    interactive mode on a real terminal. Previously it always tried
    interactive mode, which is meaningless to a non-interactive caller.
  - `deepr completion <bash|zsh|fish>` emits a shell tab-completion script
    to stdout (install hint to stderr, so `eval "$(deepr completion bash)"`
    and redirection stay clean). Surfaces Click's native completion behind
    a documented, discoverable verb.
- `deepr migrate consolidate` moves reports left under a legacy `./reports`
  root into the configured root (merges directory collisions one level
  deep, never overwrites a file; `--dry-run` previews). `ContextIndex`
  now logs a warning when it finds orphaned reports under the legacy root
  so they are not silently invisible to search and the dashboard.
- `AGENTS.md` at the repo root: the canonical, vendor-neutral agent guide
  (dev setup, test/lint/type commands, hard rules), replacing tool-specific
  instruction shims with one source of truth.
- Belief lifecycle and salience substrate (design:
  `docs/design/belief-lifecycle.md`), grounded in a nine-corpus review of
  the 2026 agent-memory and claim-verification literature (the documented
  root failure mode of agent memory is monotonic accumulation - deepr
  shared it with 17 of 20 surveyed systems):
  - Bi-temporal valid time: belief events carry an optional world-valid
    `invalidated_at` (when the fact stopped being true) distinct from the
    event timestamp (when the store learned it) - the Graphiti pattern,
    added while the event schema is young. Old event lines parse
    unchanged.
  - Lossless archival: archival events embed a full belief snapshot and
    `restore_belief` rebuilds from the log alone - reversibility is
    executable, not aspirational. Pre-snapshot archival events honestly
    return None.
  - Usage salience: per-belief `retrieval_count`/`last_retrieved_at` +
    `BeliefStore.record_retrieval`, recordable only from already-mutating
    surfaces - the read-side query surface (validate, why, digest,
    contested, what-changed) stays pure/$0, regression-tested. Usage only
    ever protects a belief from archival; absence never condemns one.
  - Consolidation pass: health-check gains an `archive_candidates`
    finding and an `--archive-stale` action ($0, no LLM). Candidates must
    pass every gate - decayed below 0.2, unevidenced 90+ days, no
    recorded usage, and not contested (contested beliefs are signal,
    never garbage - the Rashomon rule). Dry-listed with confirmation;
    every archival event-logged with snapshot and thresholds.
  Live-validated end to end at $0: inject stale belief, audit flags it,
  CLI archives it, snapshot restores it.
- Roadmap absorbs the rest of the corpus review: entailment-shaped
  contradiction screen and atomic claim decomposition (v2.15, from the
  claim-verification corpus), continuity-property metrics for eval
  methodology v2 (the ATANT audit shows popular memory benchmarks test
  at most 2 of 7 continuity properties), and ADAM-style memory
  extraction/poisoning cases for the Phase 5 red-team suite.
- Abstention as a first-class absorb outcome (`insufficient` bucket).
  Candidates the report supports weakly (extraction confidence in
  [0.4, min_confidence)) are no longer lumped into "rejected": they
  render as "insufficient grounding - abstained, not refuted", natural
  re-research targets that may well be true. The DAVinCI/TRUST
  "Not Enough Info" pattern from the calibration literature corpus;
  noise below 0.4 stays rejected. CLI summary and MCP payload carry
  insufficient_count.
- Source-trust confidence ceilings (v2.15 evidence release, panel finding
  shipped). `Belief.trust_class` (primary/secondary/tertiary; retroactive
  tertiary default for all pre-floor beliefs) with deterministic caps
  applied at read time like decay: tertiary single-source reads at most
  0.60, two independent tertiary sources at most 0.80, secondary+
  uncapped. Because enforcement is read-time, the cap holds through every
  write path (absorb, sync, merge, adjudication) and no model judgment
  can lift it - only new better-sourced evidence raises the ceiling.
  Absorb marks research-derived beliefs tertiary, making this the
  deterministic ingestion-time prompt-injection backstop: a poisoned
  report claiming 0.98 extraction confidence stores a belief that reads
  <= 0.60 (regression-tested). Honest framing: extraction confidence
  means report support, never truth probability - measured calibration
  is the harness, next.
- Frontend checks are a blocking CI job (lint with zero warnings, tsc,
  production build on Node 22 with npm cache). Previously the React
  frontend was verified only by hand - which is how a type-breaking
  dangling identifier and a missing ESLint config survived for months.
  First item of the v2.15 evidence release.

## [2.14.0] - 2026-06-11

### Added
- Auto re-research from reflection (`deepr expert reflect ...
  --execute-followups [--budget X]`). The last advisory half-loop closed:
  the follow-up queries reflection emits for weak reports now actually
  run, through the same gap-fill engine (run-ceiling budget,
  skip-not-fail, verification-gated absorb with contradiction flagging).
  Opt-in with confirmation - plain reflect stays read-only. With this,
  every v2.14 loop-closer is shipped: sync, gap-fill execution,
  reflection follow-ups, and health-check actioning of absorb-time flags.
- Autonomous gap-fill execution (`deepr expert route-gaps --execute`).
  The gap-to-tool router graduates from advisory to action: the
  highest-value research-route fills run (ordered by the router's
  value-per-dollar signal), findings absorb through the
  verification-gated pipeline (dedup + contradiction flagging), and the
  sweep is budget-bounded (per-gap inside a run ceiling, skip-not-fail,
  --dry-run at $0, confirmation with an upper-bound estimate). Bounded
  autonomy deliberately: specialist-instrument routes (recon/distillr/
  primr) are deferred with their exact command printed - approval-gated
  multi-minute paid jobs must not start as a side effect of a sweep.
- Health-check now surfaces absorb/sync-time contradiction flags. The
  contradictions check merges recorded contested pairs (the contradiction
  edges that absorb and sync write when a conflicting claim arrives) with
  freshly heuristic-detected ones, deduplicated by id pair - previously
  the audit re-ran the heuristic only and the recorded flags never
  reached the action menu. Summary and the adjudicate action distinguish
  "N recorded, M new". The read path is genuinely read-only: the audit
  no longer creates belief-store directories as a side effect
  (regression-tested - same CWD-pollution class as the cost-ledger bug).
- Regenerated expert digest (`deepr expert digest NAME [--print] [--force]`).
  The Phase E regeneration invariant made executable: a compile pass over
  the canonical belief store (beliefs + typed edges + open contradictions)
  emits a browsable Markdown digest - $0, no LLM call, deterministic and
  byte-stable for an unchanged store (the "as of" stamp derives from the
  latest belief event, not the wall clock). Open contradictions are
  surfaced with both sides and the resolve-conflicts pointer, never
  smoothed; contested beliefs are flagged inline. The CLI refuses to
  overwrite a digest that lost its derived-view marker (possible
  hand-edit) unless --force - a stale or edited artifact can never
  silently become canonical knowledge.
- explain_belief - the introspection query (TKG step 4, third temporal
  tool). `deepr expert why NAME BELIEF` and MCP `deepr_explain_belief`
  (tool 26): resolves a belief by id or claim text (query-coverage match
  with prefix tolerance), then returns evidence roots (provenance), the
  confidence trajectory from the append-only event log, supporting/
  derived-from chains walked depth-bounded and cycle-safe over the typed
  belief graph, and open contradictions with status. Read-side, cost-$0,
  SENSITIVE-tier in the MCP allowlist like the other perspective queries.
  Live-validated day one: the original symmetric text matcher rejected
  "dynamic tool discovery" against the exact belief describing it
  (short query vs long claim); rescoring by query coverage fixed it.

## [2.13.3] - 2026-06-11

### Added
- **Belief event log (TKG step 1).** Every belief change (created/updated/
  revised/archived/contested/merged) appends to `events.jsonl` - the
  cost-ledger pattern applied to knowledge. Written at change time (not
  deferred to save), so events survive mid-operation failures.
  `what_changed` reads the log when present and is exact with no
  truncation caveat (proven: a 120-belief delta returns complete past the
  old 100-record window); legacy stores keep the honest truncation
  report. Design: docs/design/temporal-knowledge-graph.md.
- **Typed belief-graph edges (TKG step 2).** `Edge(src, dst, type,
  provenance[], created_at)` with supports/contradicts/enables/
  derived_from; `contradicts` is symmetric (A-B == B-A); re-asserting a
  relationship accumulates provenance instead of duplicating. Legacy
  `contradictions_with` lists migrate idempotently on first load with the
  legacy field mirrored for one release, so every existing reader keeps
  working. Conflict detection and contested-absorb route through
  `add_edge`; same-polarity related beliefs (0.35-0.7 similarity band)
  now get `supports` edges - the structure `explain_belief` will walk.
- **First-party integrations re-verified + live drift check.** All three
  sibling integrations had silently drifted since v2.12: primr v1.29.3
  removed `batch_analyze`/`quick_lookup` (still referenced in profile,
  skill pack, and prompt), distillr v0.11.1 renamed its entire verb
  surface (the one auto-approved tool, `query_library`, no longer
  existed - the free corpus path was dead), recon v2.1.18 added five
  tools. Profiles, skill packs, prompts, and tests rebuilt on the real
  surfaces (recon 22/22, distillr 21/21, primr 17/17 declared-vs-live).
  New `scripts/validate_integrations.py`: $0 `tools/list` handshake
  through Deepr's own MCP client diffing reality against the profiles -
  its first run corrected two errors in the static fix itself.
- **Budget gate hardening (no-surprise-bills audit).** Three holes found
  and closed: (1) `-y` short-circuited the monthly budget gate entirely -
  every headless run could spend past the budget unchecked; `-y` now
  skips confirmation, never the gate, and refuses when the gate wants a
  human. (2) Cautious mode's under-$1 auto-approve had no cumulative cap
  (a loop of $0.99 jobs was unbounded); now capped at $25/month of
  ledger-verified spend. (3) The web submit gate failed open when the
  limit check itself errored; now fail-closed. Budget decisions read
  max(side counter, canonical ledger) so no entry point can make the
  month look cheaper than it was.
- **Saturation-aware eval rankings + $0 regeneration.** The benchmark's
  routing-preference generation used plain max() over per-task scores; on
  tasks where the question set has no headroom (gpt-4.1-nano scored a
  mean 1.00 over 896 reasoning evals), the "best" pick degenerated to
  iteration order - which is how auto mode came to route reasoning
  queries to a nano model. Tasks are now flagged saturated (top-2 tie
  within 0.02, or top score >= 0.99) and their best_quality pick is
  chosen by discriminative quality (mean score across tasks that DO
  discriminate) among models above a competence floor. New
  `--regenerate-rankings` rebuilds routing_preferences.json from stored
  benchmark data with zero API calls - the entire fix was validated and
  deployed without spending anything (10 of 14 task types were
  saturated; reasoning now elects gpt-5.2). A paid eval run is only
  needed when a new model must be benchmarked (`--new-models` with the
  $1 preflight cap) or when the harder question set ships (eval
  methodology v2, planned v2.15).

### Fixed
- **Six live findings from an external agent driving deepr headless**
  (2026-06-11) - the most valuable bug report class, all front-door issues:
  - `deepr research` now accepts `--budget/-b` (alias of `--limit/-l`) -
    the README documented a flag the CLI did not have.
  - Windows cp1252 consoles no longer crash on CLI output containing
    arrows/box characters (`deepr research -h` raised UnicodeEncodeError):
    stdout/stderr are reconfigured to UTF-8 with replacement at entry.
    Also closes the earlier `costs timeline` encoding finding.
  - `--auto` no longer pairs the web-search tool with models that reject
    it (gpt-4.1-nano took the tool, errored, and burned every fallback):
    nano-tier models drop the tool up front, and the submit loop retries
    the same model once without the tool on a tool-rejection error.
  - A run that fails on every provider now marks its queue job FAILED -
    previously it exited with the job still QUEUED, leaving a zombie the
    user had to cancel manually.
  - An explicit `-m` is never overridden by routing: previously
    `-m o4-mini-deep-research` without `--provider` was silently replaced
    by the pinned default (which also made the cheaper deep-research
    model unselectable). The provider is now inferred from the registry
    for explicitly requested models.
  - The o3-deep-research deprecation warning cited a retirement date
    (2026-03-26) that passed without the model retiring (alias
    live-verified still served). The entry is informational now, and
    date-less entries no longer warn on every run.
- **Deep-research pricing drift** (live pricing page, 2026-06-11):
  o3-deep-research corrected $11/$44 -> $10/$40 per MTok;
  o4-mini-deep-research corrected $1.10/$4.40 (the plain o4-mini rate,
  copied by mistake) -> $2/$8. Registry remains the single pricing
  source, so estimates and settlement both pick up the corrections.
  Full four-provider sweep verified everything else current (gpt-5.5/
  5.5-pro, grok-4.3/4.20, gemini-3.5-flash, claude-opus-4-8/fable-5
  all present and correctly priced; gemini-2.0-flash retired upstream
  June 1 and was already absent).

## [2.13.2] - 2026-06-11

### Added
- **Expert sync - scheduled freshness with delta-only integration.** The
  flagship loop-closer: `deepr expert subscribe NAME TOPIC [--every Nd]
  [--budget X]` registers what an expert stays current on;
  `deepr expert sync NAME` researches only due subscriptions with a
  delta-only freshness prompt ("what changed since <last sync>; if nothing
  meaningful, say exactly so"), absorbs through the verification-gated
  pipeline (dedup + contradiction-as-signal), and reports the perspective
  delta via `what_changed`. Per-topic budgets inside a run ceiling,
  skip-not-fail exhaustion, `--dry-run` at $0; "no significant changes"
  answers skip the paid extraction. Idempotent per cadence window, so cron
  or host-platform schedulers can run it daily and only due topics spend.
- **Simple default surface** (top finding of a six-persona cold review,
  hit by 5 of 6 reviewers): `deepr --help` opens with a worked
  three-command quickstart and lists five core commands (research, expert,
  costs, doctor, web) before an Advanced section; deprecated commands and
  single-letter aliases hidden but functional. `.env.example` reduced
  179 -> 19 lines (one key + budget ceilings; full template in
  `.env.example.full`). README gained a plain-language one-liner,
  budget-is-a-ceiling note, and a who-this-is-for block.
- **Durable learner jobs.** Every `expert learn` research submission is
  recorded in the local queue (`learn-<id>`, PROCESSING with the provider
  job id) so interrupted runs are recoverable via `deepr status`/`list`;
  terminal states and actual cost sync back. The completion summary now
  credits completed/failed topics (was always "Completed: 0 topics").
- **Frontend lint actually runs.** No ESLint config existed, so
  `npm run lint` had failed on every invocation since the frontend was
  built. Added `.eslintrc.cjs` (vite react-ts baseline) and fixed every
  violation it surfaced.

### Fixed
- **Web cost endpoints read the canonical ledger.** `/api/cost/summary`,
  `/api/cost/trends`, and `/api/cost/breakdown` computed spend from queue
  job costs - a third parallel money source that missed every CLI / MCP /
  expert spend path (dashboard showed "TODAY $0.00" against real ledger
  spend). All three now read the append-only cost ledger fresh per
  request; the daily-limit preflight counts cross-process spend.
- **Expert stats tell the truth in the web UI.** List/detail endpoints
  read legacy profile fields, showing "2 docs, 0 findings" for an expert
  with 7 documents and 24 beliefs; the Claims tab omitted the belief
  store entirely, so absorbed beliefs (the expert's actual perspective)
  never appeared. Counts now come from the profile document counter, the
  canonical belief store, and the manifest gap backlog; Claims merges
  belief-store beliefs with confidence decay and contradiction edges.
- **Unaffordable learn budgets refused at $0.** `generate_curriculum`
  raises before its first paid call when the budget cannot fund even the
  cheapest plan (previously spent ~$0.10-0.30 on generation/discovery and
  then skipped every topic).
- **research-studio file upload crash.** A refactor left dangling
  `finalFiles` references; the frontend had not type-checked since.

### Changed
- **README screenshots regenerated from live data** (all 11 assets,
  1440x900) via the improved `screenshot-qa.mjs` (dynamic job/expert
  selection from the API, `--viewport` mode); the capture run doubles as
  a web-layer regression check - it is what surfaced the cost and expert
  API bugs above.
- **Frontend dependencies updated with real verification** (CI does not
  build the frontend, so PR checks alone proved nothing):
  typescript-eslint 7.18 -> 8.61 (plugin + parser together), date-fns 4,
  immer 11, lucide-react 1.17, react-query/axios/socket.io-client/radix
  minors - lint, tsc, and production build verified locally.
- **CI actions updated**: actions/checkout v6, actions/upload-artifact v7,
  astral-sh/setup-uv v7 with `activate-environment: true` (v7 stopped
  auto-creating the venv - the bumped action fails without it).
- **Roadmap** records the six-persona panel review findings (calibration
  evidence, source-trust scoring with confidence floors, mutation audit
  log, allowlist enforcement tests) and marks the shipped items.

## [2.13.1] - 2026-06-11

### Added
- **Claude Fable 5 support.** Anthropic's new frontier tier (`claude-fable-5`,
  $10/$50 per MTok, 1M context) registered in the model registry, provider
  `SUPPORTED_MODELS`, pricing tables, and docs/MODELS.md. The registry entry is
  itself a budget guard: an unregistered model silently bills at the o4-mini
  default rate (~10x under for Fable). Opt-in only - premium price, new
  tokenizer (~30% more tokens), safety classifiers, 30-day retention.
- **Temporal perspective queries (`what-changed`, `contested`).** The first two
  tools of the TKG query surface (the autopilot wedge), shipped ahead of the
  full graph as read-side, cost-$0 layers over structures the belief store
  already persists. `deepr expert what-changed NAME --since 7d|ISO` buckets
  belief changes into added / revised / contested / archived with reasons and
  current snapshots (re-sync with an expert instead of re-reading everything);
  `deepr expert contested NAME` lists open contradiction pairs with both sides'
  claims, confidence, and provenance. CLI + MCP (`deepr_what_changed`,
  `deepr_contested`); MCP surface now 25 tools.
- **Contradiction-as-signal in `expert absorb`.** A candidate claim that
  contradicts an existing belief is no longer silently dropped: by default it
  is recorded as a *contested* belief via the new
  `BeliefStore.add_contested_belief` - contradiction edges both ways, queryable
  by health-check / `resolve-conflicts` / `contested`, never lost. The safety
  property is preserved and regression-tested: `add_contested_belief` bypasses
  similarity merging and conflict-resolution strategies entirely, so the
  existing belief is guaranteed untouched. Optional `adjudicate=True` runs
  `ConflictResolver.resolve` per conflict (advisory; verdict recorded on the
  flag, never applied). `flag_contradictions=False` restores the legacy drop.
- **`deepr costs doctor --rebuild`.** Regenerates the cost dashboard view from
  the canonical append-only ledger (the regeneration invariant applied to
  money) - repairs the ledger-vs-dashboard drift the doctor already detects.
- **`DEEPR_COST_DATA_DIR`.** Env override for the cost-state directory, honored
  by both the canonical ledger and the dashboard.

### Fixed
- **Anthropic provider sent `budget_tokens` thinking unconditionally**, which
  returns a 400 on Opus 4.7/4.8 (and Fable 5) - models the registry already
  recommended. The provider now selects thinking per model: adaptive for
  4.6+/Fable, omitted for Haiku, legacy enabled+budget for older models.
  Fable 5 safety-classifier refusals surface as a `ProviderError` instead of an
  empty billed report. Default model: `claude-opus-4-5` -> `claude-opus-4-8`.
- **Pricing single-sourcing.** `CostEstimator` delegates to the registry
  instead of its stale 4-model table, which priced every unlisted model at
  o3-deep-research rates (o3-deep-research itself was ~5x underpriced at $2/$8
  vs the registry's $11/$44). Tiered pricing (Gemini 3.x Pro >200K input: 2x
  input / 1.5x output) now applies at settlement, not just estimates, so the
  ledger records what the provider bills. Unknown-model pricing fallback logs
  a warning. `CostSession.can_proceed` enforces the $10 absolute per-operation
  ceiling previously checked only in `check_and_reserve`.
- **`load_config()`'s redacted `"***"` api_key passed through to providers.**
  ~30 CLI call sites handed the masked placeholder to `create_provider`,
  overriding every provider's env-var fallback and 401-ing at the first real
  call (caught by live validation - `expert make` was broken). The factory and
  the two direct constructors (curriculum learn loop, ContextBuilder) now treat
  `"***"`/empty as not-provided.
- **Unit tests polluted the real cost ledger.** The ledger and dashboard
  default to CWD-relative paths, so tests run from the repo root appended
  ~1,200 fabricated cost events (~$860 phantom spend) to the developer's real
  canonical ledger over the project's life. An autouse conftest fixture now
  isolates every test via `DEEPR_COST_DATA_DIR`.
- **The CI coverage gate was silently non-blocking.** pytest-cov printed
  "FAIL Required test coverage not reached" on the 3.12/3.13 jobs without
  failing the step (HEAD was green at 79.75% against an 80% gate; only the
  3.14 job propagated the failure). CI now runs an explicit
  `coverage report` gate step (reads `fail_under` from pyproject, fails
  version-independently). The CI-vs-local coverage gap was also structural:
  benchmark-rankings loaders read CWD-relative `data/benchmarks/*.json` that
  exist only on dev machines - now covered by synthetic-fixture tests.

### Changed
- **Python 3.14 promoted to a blocking CI matrix entry.** The full
  `[dev,full]` extras install and the entire suite pass on 3.14; supported
  window 3.12/3.13/3.14, all blocking.
- ruff 0.15 modernization autofixes (datetime.UTC, PEP 604 optionals) across
  51 files; generic Claude model-name mappings updated (opus -> 4-8,
  sonnet -> 4-6, new fable); retired `claude-sonnet-3-7` removed.

## [2.13.0] - 2026-06-01

### Added
- **Expert-as-guardrail (`deepr expert validate NAME CLAIM`,
  `deepr_expert_validate`).** The expert applies its existing knowledge as a
  read-only validator: PASS/WARN/FAIL verdict with confidence, reasoning,
  supporting/contradicting claims (resolved to canonical `Claim` objects with
  full citation provenance), and caveats. `--from-file -` reads the claim from
  stdin; structured JSON output makes the verdict machine-actionable for
  downstream agents that need domain validation before acting. Never mutates
  the expert. (Shipped 2026-05-27; entry added retroactively during the
  roadmap/changelog reconciliation.)
- **Per-expert SKILL.md export (`deepr expert export-skill NAME`).** Packages a
  single expert as an installable agentskills.io skill for any compatible host
  (Claude Code, Codex CLI, Gemini CLI, VS Code Copilot, Cursor, OpenClaw): the
  generated SKILL.md triggers on the expert's domain and instructs the host to
  consult exactly this expert through Deepr's MCP tools. Packages a pointer
  (calls routed over MCP at run time), not a copy of the knowledge. Builds on
  the generic `SkillPackager`; CLI-only (`--print` to preview, `-o` for output
  dir). This is the distribution play - one export reaches every major host.
- **Gap-to-tool router (`deepr expert route-gaps NAME`, `deepr_route_gaps`).**
  Read-only, cost-$0 dynamic tool selection: maps each open gap to the best
  instrument - recon (infrastructure), distillr (academic), primr (strategic),
  or general research (default) - by keyword signal, flags which instruments are
  installed (`shutil.which`), estimates cost, and gives a rationale. Advisory:
  it recommends, it does not fill. Falls back to general research when the
  specialist is not installed.
- **Reflection loop (`deepr expert reflect NAME REPORT_ID`, `deepr_reflect`).**
  Self-evaluates a research report against its question on four dimensions -
  grounding, completeness, calibration, directness - and returns a verdict
  (accept / revise / re_research) with concrete issues and follow-up queries.
  The model scores; the verdict is computed deterministically from thresholds.
  `--depth 0` skips, `1` single pass, `2+` rigorous. A natural pre-step to
  `expert absorb`. MCP surface now 23 tools.

### Fixed
- **`/why` and `/decisions` crashed** (`AttributeError`): the handlers read
  `.decision`/`.reasoning` on `DecisionRecord`, which exposes `.title`/
  `.rationale`. Reachable from both CLI (`\why`) and web (`/why`) once any
  decision was recorded.
- **Path traversal in expert-conversation GET/DELETE** (`/api/experts/<name>/
  conversations/<session_id>`): `session_id` flowed into a file path unvalidated
  (the sibling restore path was already guarded). Now rejected with 400 unless
  it matches `^[\w-]+$` - closes an arbitrary `.json` read/delete vector when
  the API runs without an API key.
- **Temporal fact-ID collision**: two facts on the same topic within the same
  wall-clock second got the same ID, overwriting one in `facts_by_id` and
  undercounting temporal stats. IDs now include microseconds.
- **`update_cost_limits` accepted booleans** (`bool` is an `int` subclass), so
  `{"per_job": true}` silently set the limit to 1.0; now rejected with 400.

### Roadmap
- Added **Phase 4c: Expert Crews** (composable, exportable expert teams) -
  composition of existing parts (council, dspy_pipeline, per-expert SKILL.md,
  absorb/reflection), scoped as `crew` (not the existing `team`), with the
  static core first and gated self-improvement last; a crew is one composable
  role (a bounded council internally), preserving the non-orchestrator stance.

## [2.12.0] - 2026-06-01

### Added
- **Expert health-check (Phase 4, knowledge maintenance loop).**
  ``deepr expert health-check NAME`` runs a read-side, cost-$0 audit of an
  expert's knowledge state - freshness, belief contradictions (free heuristic,
  no LLM), claims missing source provenance, beliefs decayed below the
  confidence threshold, the open-gap backlog, and documents ingested but never
  synthesized. Output is two-phase: findings (each with a severity) plus a
  recommended-action menu where every corrective step carries its CLI command,
  estimated cost, and the approval tier that would gate it. The audit only
  proposes; it never mutates or spends. Exposed as the ``deepr_expert_health_check``
  MCP tool (SENSITIVE: blocked in read-only, confirm in standard/extended).
- **Expert absorb (Phase 4, output-to-knowledge feedback loop).**
  ``deepr expert absorb NAME REPORT_ID`` promotes a completed research report
  into an expert's permanent beliefs, verification-gated: one extraction call
  turns the report into atomic, report-grounded candidate claims; weak claims
  and any that contradict existing beliefs are rejected (the contradiction gate
  reuses the same free heuristic as health-check); survivors are integrated via
  ``BeliefStore.add_belief`` (deduped) with the report id as provenance.
  ``--dry-run`` previews without writing. Exposed as the ``deepr_expert_absorb``
  MCP tool (WRITE: mutating + paid, gated accordingly). MCP surface now 21 tools.
- **Native Distillr integration (first-party instrument, Phase 2b #2).** When
  the ``distill-mcp`` binary is on ``PATH`` (``pip install distillr``), Deepr
  auto-discovers and mounts the distillr MCP server with no user
  configuration, alongside recon. Built-in skill (``deepr/skills/distillr/``)
  exposes ``query_library`` (free corpus search), ``discover``,
  ``ingest_papers`` / ``ingest_youtube`` / ``ingest_sites``, and ``refresh``
  (delta re-ingest, the freshness engine behind "stay current").
- **Corpus absorption.** ``KnowledgeAbsorber.categorize_distillr_response``
  parses distillr's ingestion/query output into academic findings that cite
  the corpus synthesis artifact for provenance, integrating only the first
  non-empty result set to avoid double counting.
- **Budget-capped, approval-gated ingestion.** Unlike free recon, the distillr
  profile carries a per-call ``budget_limit`` (default $2) enforced by
  ``BudgetPropagator``; only the free ``query_library`` auto-approves, and
  ``progress: true`` reuses the existing MCP ``ProgressNotifier`` for long runs.
- **Native Primr integration (first-party instrument, Phase 2b #3).** When the
  ``primr-mcp`` binary is on ``PATH`` (``pip install primr``), Deepr
  auto-discovers and mounts the primr MCP server. Built-in skill
  (``deepr/skills/primr/``) exposes ``estimate_run`` (free pre-flight),
  ``quick_lookup`` (fast recon+scrape context), ``research_company``,
  ``generate_strategy``, ``batch_analyze``, and ``check_jobs``. Primr is the
  heaviest instrument (35-50 min, paid), so every cost-incurring tool is
  approval-gated, the per-call ``budget_limit`` is $5, the timeout is 60m, and
  long runs stream progress and resume via the existing task-durability layer.
- **Multi-category company absorption.**
  ``KnowledgeAbsorber.categorize_primr_response`` is the first parser to emit
  across categories: the recon pre-flight becomes infrastructure facts (higher
  confidence) while the brief, hiring signals, and strategic initiatives become
  strategic knowledge, each citing the report artifact for provenance.
  This completes Phase 2b (recon + distillr + primr all integrated).

- **Engineering standards foundation (Phase E).** New continuous
  code-quality track in the roadmap with firm, blocking gate targets. This
  release lands the foundation:
  - **Python baseline raised to 3.12** (``requires-python >=3.12``); CI matrix
    now 3.12 / 3.13 (blocking) + 3.14 (non-blocking until optional-dep wheels
    are confirmed). 3.9/3.10 (EOL / test-collection failures) and 3.11
    (supported only to Oct 2027) dropped; a 3.12 floor holds security coverage
    to Oct 2028. ``ruff target-version`` is ``py312``.
  - **``uv`` adopted as the canonical toolchain**: ``uv.lock`` and
    ``.python-version`` committed for reproducible dev/CI/container
    environments; CI installs via ``uv pip install``. setuptools remains the
    build backend so ``pip install`` keeps working downstream.
  - **Syntax modernized to the 3.12 baseline** via Ruff autofix: PEP 604
    unions (``X | None``), ``datetime.UTC``, exception/import aliases
    (~1.6k mechanical, test-verified changes). ``ruff target-version`` is now
    ``py312``.
  - **mypy** wired into CI as a non-blocking baseline (``[tool.mypy]`` config
    added; baseline 314 errors / 76 files), ratcheting toward a blocking
    ``--strict`` gate. **Strict islands shipped:** ``deepr/core`` (44 kernel
    errors) and ``deepr/providers`` (82 errors across all adapters - including
    realigning grok's vector-store stubs to the base provider contract) are now
    ``mypy --strict``-clean and enforced by a **blocking**
    ``mypy --strict deepr/core deepr/providers deepr/mcp`` CI step. ``deepr/mcp``
    was driven strict-clean and **flipped into the blocking gate this release**
    (the third strict island); the migration also fixed a latent bug where the
    expert-info MCP tools used dict-subscript access on ``ExpertProfile`` objects.
  - **pip-audit** wired into CI and already **blocking**: the baseline it
    surfaced was cleared immediately (see Security), so a new known
    vulnerability now fails the build.
  - **Dependency update automation** enabled (pip + github-actions + npm, weekly).
  - **Branch coverage** enabled (stricter than line coverage): the gate is now
    ``fail_under = 78`` over branch coverage (was 80 line), ratcheting toward 95.
  - **C901 complexity cap** (max-complexity 10) surfaced as an advisory CI
    signal alongside the S-rules; 134 over-cap functions tracked for refactor.
  - **Mutation testing** (mutmut) wired as a scheduled / on-demand non-blocking
    workflow over the kernel (budget, cost ledger, cost safety), with config in
    ``[tool.mutmut]``.
  - **SBOM** (hash-pinned dependency bill of materials via ``uv export``)
    published as a CI build artifact.
  - **Python floor raised again to 3.12** (from the 3.11 set earlier this
    cycle): 3.11 is supported only to Oct 2027; a 3.12 floor holds security
    coverage to Oct 2028. ``ruff target-version = "py312"``, CI matrix 3.12/3.13
    + 3.14 (non-blocking), Dockerfile base ``python:3.12-slim``.

### Security
- **flask-cors bumped 4.x -> 6.x**, clearing CVE-2024-6839, CVE-2024-6844, and
  CVE-2024-6866 (all fixed in 6.0.0). The old ``<5.0.0`` pin held the project
  on the vulnerable 4.0.2; the new pip-audit CI gate caught it on its first
  run. Deepr's usage (``CORS(app, origins=...)``) is unchanged across the bump.

### Changed
- ``ConfigLoader.load()`` first-party auto-discovery generalized from
  recon-only to a table (recon, distillr, primr); user-defined profiles still
  take precedence over any auto-discovered one of the same name.
- ``scripts/check_docs_consistency.py`` (CI) now also guards the built-in
  skill count against ``deepr/skills/``.

### Fixed
- **Runaway knowledge-graph edge growth (multi-GB `edges.json`).**
  `EdgeBuilder.build_edges` created a co-occurrence edge for every pair of
  concepts in a section (O(C^2)), and the concept extractor emits a concept for
  every 2-5 word n-gram, so a single large section generated millions of edges;
  with `min_pmi=0.0` nothing was pruned. One expert's `edges.json` reached
  26 GB (51k concepts). The builder now pairs only the top
  `max_concepts_per_section` (default 40) concepts - headings/key-phrases first
  - and `KnowledgeGraph` enforces a hard `max_edges` safety cap (default 1M)
  that drops further new edges with a one-time warning while still merging
  existing ones. Re-index affected experts to rebuild a healthy graph.
- Stale recon **integration** tests (not run by CI, which executes only
  ``tests/unit/``) updated to the shipped ``RECON_PROFILE_TEMPLATE`` tool
  names and modern ``asyncio.run`` (the deprecated ``get_event_loop`` form
  raised on Python 3.11+). Count-based config-loader unit tests are now
  isolated from host-installed first-party binaries.
- **``expert learn --resume`` crashed** - ``do_resume()`` built
  ``LearningTopic`` without the required ``description``/``priority`` fields and
  ``LearningCurriculum`` without ``generated_at``, a guaranteed ``TypeError``
  whenever resume ran. All required fields are now passed.
- **``expert refresh`` crashed on a never-refreshed expert** - the stats display
  called ``.strftime()`` on ``last_knowledge_refresh`` (``datetime | None``)
  unconditionally. Guarded; shows "never" when unset.
- **``expert absorb`` crashed on malformed model output** - an extraction
  response of ``{"claims": null}`` (or a non-list value) hit ``None[:n]``.
  Non-list ``claims`` now degrades to zero candidates.
- **Date-dependent test flake** - ``test_reset_if_needed_daily`` set
  ``last_reset`` to "yesterday", so on the 1st of any month the monthly bucket
  also reset (correct production behaviour), failing CI on those dates. Pinned
  to a mocked mid-month ``now``.
- Replaced the remaining deprecated ``datetime.utcnow()`` calls across the test
  suite with ``datetime.now(UTC)`` (production code was already clean).

---

## [2.11.0] - 2026-05-27

First-party native integration of Recon, the passive domain intelligence
tool, plus a follow-on hardening / version-centralization sweep.

### Added
- **Native Recon integration (first-party instrument).** When the
  ``recon`` binary is on ``PATH`` (``pip install recon-tool``), Deepr now
  auto-discovers and mounts the recon MCP server with no user
  configuration. Built-in skill (``deepr/skills/recon/``) covers the real
  shipped tool surface: ``lookup_tenant``, ``analyze_posture``,
  ``assess_exposure``, ``find_hardening_gaps``, ``chain_lookup``,
  ``get_posteriors``, ``explain_dag``.
- **Autonomous recon probe in expert chat.** When an expert is in
  ``agentic`` mode and the user message contains a domain, Deepr fires
  ``lookup_tenant`` at cost $0 and surfaces high-confidence
  infrastructure findings (services, related domains, tenant/provider,
  email-security posture) directly into the system prompt for that turn.
  ``KnowledgeAbsorber.categorize_recon_response`` is a specialized parser
  that emits >= 0.8 confidence findings from the real recon response
  shape.
- **`deepr doctor` Native Instruments check** reports whether recon is
  available and suggests ``pip install -U recon-tool`` when missing.
- **CI advisory security lint** via ``ruff check --select S`` (Bandit-
  equivalent) runs on every push with ``continue-on-error: true`` so
  findings show up in the log without retroactively gating on legacy
  ``try/except/pass`` and partial-executable-path findings.

### Changed
- **Single source of truth for version.** ``AgentCardGenerator``,
  ``MCPClient`` clientInfo, ``SkillPackager`` default, and the web
  ``/health`` endpoint now import ``deepr.__version__`` instead of
  hardcoded ``"2.10.0"`` / ``"2.9.0"`` strings (and matching tests
  updated to assert against ``DEEPR_VERSION``). This closes a recurring
  silent-drift bug class.
- **ExpertSkillWrapper gap-tool map** updated for the real recon tool
  names (``lookup_tenant``, ``analyze_posture``, ``chain_lookup``) with
  legacy ``domain_lookup`` retained as a fallback for user-defined
  skills.

### Security
- **`doc_reviewer.scan_docs` symlink/traversal hardening.** Rejects
  symlinks, uses ``validate_path`` + realpath containment, and skips
  files larger than 2 MB before any content is read.
- **`config.load_config` no longer leaks provider API keys** in its
  return dict; callers needing real keys must go through the provider
  factory or environment variables. Removes an accidental cross-context
  key disclosure path.
- **`bin/deepr-api`** documents that ``DEEPR_ALLOW_PUBLIC_BIND=1`` is
  acknowledgement of a real risk (data disclosure + provider-spend
  abuse), not a routine convenience flag.
- **Documentation hardening** in ``deepr/api/app.py`` and
  ``deepr/web/app.py`` makes the local-dev-only nature of the
  unauthenticated default explicit.

### Fixed
- **MCP / async exception handling.** ``MCPClientProxy.call_tool`` and
  ``SkillExecutor`` now re-raise ``CancelledError``, ``SystemExit``, and
  ``KeyboardInterrupt`` instead of swallowing them into a generic
  ``{"error": ...}``. Remaining broad ``except`` blocks now carry an
  intent-explaining comment.
- **`assert` replaced with explicit logging + safe return** in
  ``StdioTransport._read_loop``, ``LiveShimmerStatus._run``, and
  ``ExpertSkillWrapper.execute`` (asserts are stripped under ``python
  -O``; the previous code could fall off the end with ``None`` in
  pathological cases).
- **`AzureFoundryProvider.__del__`** clean-up swallow is now explicitly
  documented as intentional (must not raise during interpreter
  shutdown).
- **`ConfigLoader.load`** no longer raises ``FileNotFoundError`` when
  the integrations config is absent; it returns auto-discovered profiles
  (recon if installed) and an empty list otherwise.

### Tests
- Patch ``discover_recon_profile`` in two config-loader tests so they
  do not depend on whether the ``recon`` binary happens to be installed
  on the dev / CI machine.
- ``test_a2a_integration`` and ``test_packager`` now assert against
  ``DEEPR_VERSION`` so future version bumps don't break tests.
- Replace ``assert False`` with ``raise AssertionError`` (ruff B011).
- Remove unused locals across A2A / MCP / services coverage tests.
- ``tests/integration/test_grok_search.py`` moved to
  ``grok_search_demo.py`` - it was a manual demo, not a pytest test, so
  it no longer triggers collection errors when ``xai_sdk`` is missing.

### Roadmap
- Phase 2b first-party instrument sequencing made explicit:
  Recon (1) -> Distillr (2) -> Primr (3). Recon is now the pilot
  delivered.

---

## [2.10.3] - 2026-05-17

Five-round bug-hunt sweep covering cost/budget, async/concurrency, storage
durability, provider correctness, auth, skill subsystem, CLI flag validation,
deploy templates, MCP client + transports, frontend accessibility, and
documentation accuracy. ~360 fixes across ~190 files. All 4,341+ unit tests
pass. Coverage threshold raised from 60% to 75%.

### Security
- **Skill executor RCE closed.** Skill ``module``/``function`` fields are
  now resolved with ``importlib.util.spec_from_file_location`` against a
  path inside the skill directory; ``module: os, function: system`` is
  refused. Function names are validated as public identifiers; dunders
  blocked. ``sys.path`` is never modified.
- **Skill MCP subprocess allowlist.** ``server_command`` must be on a
  per-skill allowlist (built-ins only by default; opt in via
  ``DEEPR_SKILL_ALLOW_MCP_COMMANDS=*``). MCP subprocesses no longer
  inherit the full host environment - only ``server.env`` keys, plus a
  minimal ``PATH``/``HOME`` set.
- **Skill path traversal closed.** ``prompt_file`` rejects absolute paths
  and any path that resolves outside the skill directory.
  ``SkillManager(expert_name=...)`` sanitises the expert name through
  ``deepr.utils.security.sanitize_name``.
- **Webhook server fail-closed.** Refuses anonymous POSTs when
  ``DEEPR_WEBHOOK_SECRET`` is unset; refuses to start on a non-loopback
  bind without a secret. Adds a 1 MiB body cap.
- **A2A server bearer-auth gate.** ``POST /tasks`` and
  ``POST /tasks/{id}/cancel`` now require ``DEEPR_A2A_TOKEN`` when set.
  Refuses non-loopback bind without a token unless
  ``DEEPR_A2A_ALLOW_PUBLIC=1``. 1 MiB body cap, header / body read
  timeouts.
- **MCP HTTP transport bearer over plain HTTP** now emits a warning at
  subscribe time when the URL is non-loopback. Body cap set explicitly.
- **`deepr templates show/delete/use`** sanitise the template name  -
  ``../`` no longer reads or deletes arbitrary files.
- **MCP confirmation gate** strips the ``_approved`` kwarg before
  dispatch so handlers without that parameter no longer crash with
  ``TypeError``.
- **Shared cloud `security.py`** uses ``hmac.compare_digest`` with
  ``TypeError`` catch (was raw ``==``).
- **`InstructionSigner` convenience helpers** now share a singleton so
  ``sign_instruction`` / ``verify_instruction`` actually round-trip when
  ``DEEPR_SIGNING_KEY`` is unset.
- **Azure**: legacy unauthenticated ``deploy/azure/function_app/``
  directory removed; cancel_job uses Cosmos ETag (``If-Match``) with
  retry loop; documents now write a top-level ``job_id`` field matching
  the container's ``/job_id`` partition key.
- **GCP**: cancel_job wrapped in a Firestore transactional decorator.

### Cost correctness
- **`CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION`** + ``ABSOLUTE_MAX_DAILY``
  + ``ABSOLUTE_MAX_MONTHLY`` class attributes added (round-2 patch fixed
  a swallowed AttributeError; this exposes the constants the MCP server
  + CLI reference).
- **Reservation pattern.** ``cost_safety.check_and_reserve()`` returns
  a reservation_id; ``record_cost(reservation_id=...)`` settles the
  reservation. N-way parallel fan-out (council, task planner, batch
  executor) can no longer over-commit against the daily cap.
- **`services/research_api.py`** ``cost_limit`` semantics fixed: when
  the model's estimate exceeds the caller's cap we now reject upfront
  instead of treating the cap as the spend.
- **`services/batch_executor.py`** + **`services/research_api.py`** now
  call ``record_cost`` after successful submission so daily / monthly
  spend doesn't drift below reality.
- **`services/batch_auto.py`** ``execute_batch`` enforces a
  ``cost_safety.check_operation`` gate against the total routing-cost
  estimate (previously a 100-query batch could spend $100+ unchecked).
- **`experts/chat.py`** ``_deep_research`` uses ``get_cost_estimate``
  from the registry (was hardcoded ``$0.20`` for a ``$2.00`` model).
  Multi-round tool loops re-check ``cost_session.can_proceed`` between
  rounds. ``_quick_lookup`` gets a pre-flight check and registry-driven
  pricing; cached-token discount honoured.
- **`mcp/client/pool.py`** clamps server-reported cost so a malicious
  server returning ``cost=0`` cannot bypass spend tracking and ``-1``
  cannot credit budget back.
- **`web/app.py`** ``POST /api/jobs`` enforces ``CostController.check_cost_limit``;
  ``/api/experts/council`` clamps caller budget against
  ``ABSOLUTE_MAX_PER_OPERATION``; ``/api/experts/chat`` clamps against
  daily remaining.
- **`core/costs.py`** ``record_cost`` now calls ``reset_if_needed()``
  first so a job recorded just after UTC midnight lands in the new
  day's bucket.

### Correctness
- **`agents/orchestrator.py`** no longer drops subtasks beyond
  ``len(workers)``; workers are picked round-robin via
  ``idx % len(workers)``. Output keys sort numerically so ``worker-10``
  lands after ``worker-2``.
- **`observability/routing_log.py`** ``get_events`` returns the LAST N
  rows, not the FIRST N - every analytics query in this module was
  silently analysing the oldest history slice.
- **`observability/circuit_breaker.py`** OPEN -> HALF_OPEN transition
  now holds ``self._lock`` so concurrent callers can't both fire a
  probe.
- **`observability/traces.py`** ``TraceContext.get_current`` uses a
  ``contextvars.ContextVar`` instead of ``threading.local`` so async
  coroutines on the same thread see their own context.
- **`research_agent/poller.py`** treats ``cancelled``, ``canceled``,
  ``expired`` as terminal; adds exponential backoff (capped 5 min) on
  persistent errors. ``queued`` is a recognised no-op.
- **`core/research.py`** ``_temporal_trackers`` is popped on
  ``cancel_job`` and ``process_completion`` so long-running orchestrators
  don't leak one entry per job.
- **`core/company_research.py`** constructor + ``submit_research`` call
  now use the real ``ResearchOrchestrator`` API. Previously every call
  crashed at init.
- **`providers/anthropic_provider.py`** for-else on the multi-turn
  tool loop now surfaces a truncation note when ``max_turns`` is hit
  without convergence; usage is accumulated across turns and ``get_status``
  returns the stored response (previously every call recorded $0).
- **`providers/registry.py`** ``get_token_pricing`` normalises Grok's
  dot/hyphen aliases (was an 80% undercharge on multi-agent); cached
  token discount applied; partial-match candidates sorted by length so
  ``flash-lite`` doesn't match ``flash``.
- **`providers/openai_provider.py`** rate-limit fallback uses
  ``dataclasses.replace`` instead of mutating the caller's request.
- **`providers/gemini_provider.py`** reads ``chunk.usage_metadata``
  for real token counts (including thinking tokens) instead of
  ``len(text)//4`` estimates.
- **`providers/azure_provider.py`** adds retries on transient errors;
  defends against ``response.model = None``.

### Durability
- **`deepr/utils/atomic_io.py`** introduced (``atomic_write_bytes``,
  ``atomic_write_text``, ``atomic_write_json``, ``append_jsonl_durable``).
  ~17 storage call sites migrated.
- **Cost ledger** appends now ``flush() + os.fsync()`` so the last
  event survives a crash.
- **`queue/local_queue.py`** runs in WAL mode; ledger event is written
  BEFORE the SQLite commit so a crash between the two can't leave a
  job marked completed without a billing row. Partial UNIQUE index on
  ``provider_job_id`` blocks double-billing on submit-retry races.
- **`mcp/state/persistence.py`** ``save_job`` is atomic via
  ``with self._conn:`` - all three INSERTs commit together.

### Async / lifecycle
- **`mcp/transport/stdio.py`** ``stop()`` drains in-flight handler
  tasks with a 5-second grace; ``_in_flight`` initialised in
  ``__init__`` rather than lazily in the read loop.
- **`mcp/transport/http.py`** ``HttpClient.subscribe()`` cancels any
  prior subscription task before creating a new one (was leaking
  zombie SSE streams). ``_handle_post`` returns a generic 500 instead
  of echoing exception text. SSE subscriber dict overwrite now signals
  the old handler to exit cleanly.
- **`mcp/client/base.py`** spawns a background ``_drain_stderr`` so
  a chatty MCP server doesn't fill the ~64 KB pipe buffer and hang.
  Reconnect backoff has full jitter. Timeout in ``_send_request``
  forces a reconnect to prevent JSON-RPC framing corruption.
- **`mcp/state/async_dispatcher.py`** waits for dependencies BEFORE
  acquiring the concurrency semaphore - fixes a deadlock on chains
  longer than ``max_concurrent``.
- **`experts/task_planner.py`** parallel ``_run_step`` coroutines
  serialise through an ``asyncio.Lock`` on the shared session;
  ``ExpertChatSession`` is no longer concurrently mutated.
- **`a2a/server.py`** writer cleanup uses ``await writer.wait_closed()``.
- **`a2a/task_manager.py`** bounded eviction of terminal tasks.
- **`mcp/security/output_verification.py`** chain head primed from DB
  on init (was breaking chains on every restart).

### CLI
- **`deepr templates`** sanitises template name via ``sanitize_name``.
- **`deepr jobs cancel`** routes by ``job.provider``, not the global
  config default.
- **`deepr interactive`** maps model names to providers correctly
  (was routing Grok / Claude to ``gemini``).
- **`--cost-limit`** accepts ``FloatRange(min=0.0)``; **``--phases``**
  accepts ``IntRange(1, 10)``; **``--perspectives``** accepts
  ``IntRange(1, 12)`` - runaway-spend bypasses closed.
- **`deepr team`** uses ``web_search_preview`` for OpenAI providers
  (was using the unknown name ``web_search``).
- **`deepr search --keyword-only`** is now respected (precedence bug
  ``not keyword_only or True`` evaluated to ``True``).
- **`deepr costs limits`** now persists daily / monthly limits to
  ``cost_data.json`` and validates ``>= 0``.

### Round 4 - auto-mode, emitter, agent budgets, frontend safety
- **`research/auto_mode.py`** fallback model selection no longer crashes
  when the configured model is missing from the registry; falls back to
  a sane default.
- **`observability/metadata_emitter.py`** per-job temporal tracker
  replaces the shared field - fixes the race where parallel jobs
  clobbered each other's elapsed-time accounting.
- **`agents/budget.py`** ``AgentBudget.check`` propagates parent
  remaining downward correctly when a worker spawns a sub-worker so
  bounded fan-out no longer over-spends its slice.
- **Frontend safety**: result-detail citation rendering no longer
  crashes on malformed URLs (``new URL`` wrapped in try/catch);
  budget sliders debounced (was firing mutations on every pixel drag);
  cost-intelligence utilisation handles zero-denominator division.

### Round 5 - cost gates, MCP stability, frontend a11y
- **LLM cost-safety gates** added to seven previously uncovered call
  sites that could otherwise drive unbounded spend on long inputs:
  ``experts/citation_validator``, ``gap_discovery``, ``conflict_resolver``,
  ``curriculum``, ``map_reduce`` (map + reduce), ``multi_pass``
  (extract/cross-ref/synthesise), ``synthesis`` (synthesize + extract),
  ``task_planner`` (decompose + synth), ``embedding_cache`` (per-doc +
  query).
- **`experts/skills/executor.py`** MCPClientProxy now drains stderr in a
  background task so a chatty MCP subprocess can't fill the pipe buffer
  and deadlock.
- **`experts/skills/definition.py`** trigger-regex compilation protected
  from ReDoS - pattern length capped at 256 chars, nested-quantifier
  backtracking patterns rejected.
- **`mcp/client/pool.py`** terminal ``ProgressEvent`` now emitted on
  tool completion (the ``_progress_notifier`` was stored but never
  triggered - subscribers saw zero events).
- **`storage/findings_store.py`** in-memory index mutations now guarded
  by ``threading.RLock``.
- **`cli/commands/research.py`** ``cancel`` merges nested
  ``asyncio.run()`` calls into a single event loop so lookup + cancel
  share the same loop.
- **Frontend a11y**: htmlFor/id pairing on settings + research-studio
  inputs; aria-label on search and slider widgets; aria-valuemin/max/now
  on cost-intelligence slider; responsive sidebar hiding
  (trace-explorer ``<lg``, expert-profile ``<md``).
- **Dead frontend code removed**: ``use-local-storage`` /
  ``use-media-query`` hooks, ``activity-feed`` /
  ``memory-indicator`` components.

### Documentation
- This file. CHANGELOG was empty for v2.10.3 (3 commits' worth of work
  had no release notes).
- ``--agentic`` flag references removed - flag doesn't exist; agentic
  is the default, ``--no-research`` disables.
- ``deploy/azure/README.md`` + ``deploy.sh`` corrected to ``functions/``
  (the ``function_app/`` directory was removed).
- MCP tool count: 16 -> 18 in ``README.md`` and ``mcp/README.md``.
- Test count: 4300+ -> 4341+ in ``README.md``, ``ROADMAP.md``,
  ``SECURITY.md``, ``docs/VISION.md``.
- Coverage threshold: 60% -> 75% in ``CONTRIBUTING.md`` and ``ROADMAP.md``.

---

## [2.10.2] - 2026-05-13

Security and hardening patch. No breaking changes for default operation;
adds explicit opt-out flags for previously implicit unsafe behavior.

### Security
- **Web dashboard refuses unsafe Werkzeug binds.** `python -m deepr.web.app`
  now refuses to start the Werkzeug development server on any non-loopback
  host, drops `allow_unsafe_werkzeug=True`, and requires either
  `DEEPR_API_KEY` or `DEEPR_ALLOW_PUBLIC_BIND=1` to bind beyond `127.0.0.1`.
- **MCP confirmation gate enforced.** Tools that require confirmation in
  the current research mode now return `CONFIRMATION_REQUIRED` instead of
  being dispatched silently. Callers must pass `arguments._approved=true`
  or set `DEEPR_MCP_AUTO_APPROVE=1` to opt back into the legacy
  log-and-continue behavior.
- **MCP tool allowlist covers the real surface.** Registered
  `deepr_research`, `deepr_agentic_research`, `deepr_cancel_job`,
  `deepr_expert_manifest`, `deepr_rank_gaps`, `deepr_query_expert`, and
  six read-only Deepr tools with explicit categories so allowlist
  decisions reflect the actual exposed tools instead of treating each as
  "unknown".
- **Bearer-token compare handles non-ASCII headers.** Both
  `deepr/api/app.py` and `deepr/web/app.py` now catch the `TypeError`
  that `hmac.compare_digest` raises for non-ASCII `str` inputs and
  return `401 Unauthorized` instead of letting it escape into the
  generic 500 handler.
- **`POST /api/experts` validates string fields.** `description` and
  `domain` must be strings and are truncated to 1000/200 characters,
  preventing persisted objects/arrays from tripping the React Expert
  Hub error boundary across all clients.
- **`POST /api/jobs` (modular API) enforces guards before provider call.**
  Added 1 MB body cap, 50K prompt-length cap, model allowlist, and
  pre-submit `CostController.check_cost_limit()` check.
- **`/api/demo/clear` gated behind `DEEPR_DEMO=1`** plus an explicit
  `{"confirm": "DELETE_ALL_DATA"}` body. Returns 403/400 otherwise.
- **`/api/benchmarks/estimate` cannot fan out subprocesses.** Per-route
  6/min rate limit, module-level execution lock, and a 2-minute
  per-(tier, quick, no_judge) result cache so concurrent estimates
  serialize on a single Python child.
- **Portrait endpoint records cost and is rate-limited.** Cooldown +
  provider allowlist already shipped; v2.10.2 adds a 5/hour route
  limiter and writes generated portraits to the canonical cost ledger
  via `CostSafetyManager.record_cost`.
- **Citation-validation GET caches results.** Per-expert mtime-keyed
  10-minute TTL cache prevents dashboard polling from re-fanning out
  paid LLM validation batches.
- **AWS worker reads cancellation from DynamoDB.** Worker now consults
  the API's `JobsTable` instead of an S3 `metadata.json` the API never
  creates; status/cost/completion updates flow back via `UpdateItem`,
  and reports are written under `results/{job_id}/report.md` so the API
  `get_result` endpoint can serve them.
- **Grok multi-agent budget pre-flight.** `AgentBudget.check()` runs
  before each worker chat-completion call and synthesis is skipped when
  the operation budget has been exhausted.
- **Removed dead `deepr/api/routes/` submodule.** The never-imported
  modular routes (job/result/cost/config blueprints) shipped with stale
  `check_job_limit`/`to_dict()` calls and would have been an
  unauthenticated provider-spend surface if wired in.

### Changed
- **GPT-5.2 chat sessions cost at registry rates.** `ExpertChatSession`
  now computes token cost via a `_chat_token_cost(usage, model)` helper
  that pulls input/output prices from the model registry instead of
  hard-coding the legacy GPT-5 $1.25/$10 per-1M rates. GPT-5.2 sessions
  accumulate at the correct $1.75/$14 per-1M.
- **Gemini Deep Research priced from the registry.** `gemini-deep-research`
  and `deep-research` aliases now resolve to
  `deep-research-pro-preview-12-2025` ($2.50/job) in both
  `get_cost_estimate()` and `MODEL_COST_ESTIMATES`, so orchestrator and
  MCP budget guards no longer approve $1+ jobs against the $0.20
  unknown-model default.
- **Gemini 3.x Pro tiered pricing.** `_calculate_cost` applies the 2x
  multiplier for prompts above 200K input tokens; `get_cost_estimate()`
  accepts an optional `input_tokens` hint so pre-flight budget checks
  reflect the tier.
- **Consensus engine Gemini cost.** Bumped provider budget estimate to
  $0.20 (Gemini 3.1 Pro Preview base) and replaced the flat $0.05
  placeholder with token-accurate cost from `usage_metadata` including
  the tiered multiplier.
- `CostDashboard.record` and buffered cost recording now emit canonical
  ledger events.
- `DEEPR_COST_TRACKING_STRICT=1` enables fail-fast behavior when ledger
  writes fail in cost dashboard/safety paths.

### Added
- Canonical append-only cost ledger at `data/costs/cost_ledger.jsonl`
  with idempotency-key support (`deepr/observability/cost_ledger.py`).
- `deepr costs doctor` command for zero-cost tracker integrity checks
  (ledger writable + drift vs dashboard totals).
- Queue cost persistence records positive cost deltas with idempotency
  metadata to avoid duplicate attribution.
- `CostSafetyManager.record_cost` writes canonical ledger events for
  non-queue spend paths (used by the portrait endpoint).
- Rich animated ASCII startup banner with cross-platform fallbacks
  (compact/narrow terminals, legacy Windows, non-UTF output).
- Startup banner env controls: `DEEPR_BANNER_MODE=off|static|light|full`
  and `DEEPR_BANNER_DURATION=<seconds>`.

---
## [2.9.1] - 2026-02-16

### Added
- `deepr web` CLI command to start the web dashboard (replaces `python deepr/web/app.py`)
  - `--host`, `--port` / `-p`, `--debug` options
  - Graceful error if web dependencies are not installed

### Changed
- Documentation updated to use `deepr web` instead of `python deepr/web/app.py`

---

## [2.9.0] - 2026-02-16

### Added

**Agentic Expert Chat**
- Streaming expert chat over WebSocket (Socket.IO) with real-time token delivery, tool call visibility, and follow-up suggestions
- 27 slash commands organized by category (Mode, Session, Reasoning, Control, Management, Utility) with `/` prefix in web and `\` prefix in CLI
- Command registry (`deepr/experts/commands.py`) with shared parsing for CLI and web, alias resolution, and category grouping
- 4 chat modes: ASK (quick answers, KB-only tools), RESEARCH (default, all tools), ADVISE (consulting-style structured recommendations), FOCUS (always-on chain-of-thought reasoning)
- Mode switching via `/ask`, `/research`, `/advise`, `/focus` commands; mode badge displayed in chat header
- Visible reasoning: ThoughtStream callbacks pipe real-time thinking steps to frontend via `chat_thought` WebSocket events; collapsible ThinkingPanel shows planning, search, evidence, and decision steps with confidence indicators
- Context compaction: `/compact` summarizes earlier messages while preserving recent context, enabling longer sessions without token budget exhaustion; auto-suggest banner after 30+ messages or 80K+ estimated tokens
- Human-in-the-loop approval flows: `ApprovalManager` with three tiers (auto-approve, notify, confirm) based on operation cost and budget; inline confirmation dialog in chat for expensive operations
- Expert council: `/council` command queries multiple experts in parallel on cross-domain questions, synthesizes agreements and disagreements; also available as `POST /api/experts/council` REST endpoint
- Hierarchical task decomposition: `/plan` command breaks complex queries into subtasks with dependency graph, executes independent subtasks in parallel with live progress per step
- Memory commands: `/remember` pins facts to session, `/forget` removes them, `/memories` lists all; pinned memories included in system prompt
- Session management: `/clear` resets chat, `/new` starts fresh session, `/save` and `/load` for named sessions, `/export` to markdown or JSON
- Reasoning commands: `/trace` shows full reasoning chain, `/why` explains last decision, `/decisions` lists all decisions, `/thinking on/off` toggles verbose reasoning display
- Control commands: `/model` switches model, `/tools` lists available tools, `/effort` adjusts reasoning depth, `/budget` shows remaining budget, `/status` shows session stats
- Conversations API: `GET/POST /api/experts/<name>/conversations` for listing and loading past chat sessions
- Expert portrait generation: AI-generated SVG portraits based on expert domain and description, cached per expert, displayed in profile header
- Web slash command autocomplete: floating menu triggered by `/` in chat input, grouped by category, keyboard navigable
- Frontend chat components: `ThinkingPanel`, `ConfirmDialog`, `CompactBanner`, `PlanDisplay`, `MemoryIndicator`, `SlashCommandMenu`, `MessageActions`, `ToolCallBlock`

**Expert Skills System**
- Domain-specific capability packages that give experts unique tools and reasoning
- `SkillDefinition` format: `skill.yaml` manifest + `prompt.md` overlay + Python/MCP tools
- Three-tier storage: built-in (`deepr/skills/`), user global (`~/.deepr/skills/`), expert-local (`data/experts/{name}/skills/`)
- `SkillManager`: discovery across all tiers, keyword/regex trigger matching, domain-based suggestion
- `SkillExecutor`: Python tool execution via importlib, MCP bridging via JSON-RPC stdio proxy
- Progressive disclosure in expert chat: skill summaries always in system prompt, full prompt loaded only on activation
- Tool namespacing (`skill_name__tool_name`) prevents conflicts across skills
- Budget tracking per skill with cost tier estimates (free/low/medium/high)
- Profile schema migration v2->v3 adding `installed_skills` field (backward compatible)
- 4 built-in skills shipping in `deepr/skills/`:
  - `web-search-enhanced`: structured data extraction from research text
  - `code-analysis`: dependency audit + cyclomatic complexity analysis
  - `financial-data`: financial ratio calculations (P/E, P/B, debt-to-equity, ROE, margins)
  - `data-visualization`: markdown table generation + ASCII bar charts
- CLI: `deepr skill list/install/remove/create/info` command group
- CLI: `deepr expert run-skill` for direct tool execution
- Web API: `GET/POST/DELETE /api/experts/<name>/skills/<skill>`, `GET /api/skills`
- MCP: `deepr_list_skills` and `deepr_install_skill` tools
- Frontend: Skills tab (6th tab) in Expert Profile with install/remove buttons
- 124 new unit tests for skills definition, manager, and executor

**Expert Intelligence**
- Multi-provider consensus gap-filling (`--consensus` flag)
- Semantic citation validation (`SupportClass` enum, `--validate-citations` flag)
- Multi-pass gap-filling pipeline (`--deep` flag)
- Automated gap discovery via claim clustering (`deepr expert discover-gaps`)
- Conflict resolution agent with multi-provider adjudication (`deepr expert resolve-conflicts`)

### Changed
- Shared constants module (`deepr/experts/constants.py`) centralizes model names, tool identifiers, and budget fractions across council, task planner, command handlers, and WebSocket events
- `_run_in_thread()` helper in WebSocket events replaces duplicated asyncio event loop boilerplate
- Frontend: extracted reusable `SkillCard` and `EmptyState` components, reducing expert-profile.tsx bundle by 1.5KB
- Frontend: replaced 4 inline empty state patterns and 2 inline skill card renderings with shared components

### Fixed
- Removed unused imports `AppConfig` and `create_provider` in `experts.py` discover-gaps command
- Removed unused import `KnowledgeSynthesizer` and unused variable `do_validate` in `app.py` fill-gaps endpoint
- ThinkingPanel showed "Thought for " with empty duration when timestamps were identical (now shows "<1s")
- Compact toast showed "undefined messages" when backend omitted count (added fallback)
- Chat auto-scroll: `userScrolledRef` was never set to true (added `onScroll` handler)
- Duplicate React keys in active tool call list (key now includes `startedAt` timestamp)
- Chat mode was not sent to backend `startChat()` (added mode parameter to WebSocket emit)
- Unsafe `(data as any).mode` cast in chat complete handler replaced with proper typed field
- Dead `setChatInput(fu)` in follow-up handler removed (was immediately overwritten)
- Clipboard copy in message actions now has try/catch for environments where `navigator.clipboard` is unavailable
- Confirm dialog cost display uses `formatCurrency()` for consistent formatting
- Council synthesis missing newline separators between expert perspectives
- Task planner result truncation was slicing a list instead of truncating the joined string
- Removed unused `_PROVIDERS` constant in portraits module
- Removed redundant alias entries in command handlers (registry already resolves aliases)
- Moved lazy imports (`uuid`, `os`, `AsyncOpenAI`) to top level in approval and council modules

---

## [2.8.1] - 2026-02-14

### Added

**Models & Benchmarks Page**
- New web page (`/models`) with model registry browser showing all registered models grouped by provider
- Benchmark results viewer with quality rankings by tier (chat/news/research), quality bar charts, and per-task-type radar charts
- Run benchmarks from the UI with tier, quick/full, judge toggle, and budget controls
- Cost estimation (dry-run) before starting a benchmark run
- Benchmark history file selector to load and compare different runs
- Routing configuration display showing current auto-mode preferences
- Provider key status indicators (configured vs not set)
- Backend APIs: `GET /api/benchmarks`, `GET /api/benchmarks/latest`, `GET /api/benchmarks/<filename>`, `POST /api/benchmarks/start`, `POST /api/benchmarks/estimate`, `GET /api/benchmarks/status`, `GET /api/benchmarks/routing-preferences`
- Model registry API: `GET /api/registry`

**Help Page**
- New web page (`/help`) with API key setup guide linking to all provider consoles
- CLI quick reference with common commands
- Model tier explanations (research, news, chat) with strengths and cost guidance
- "When to use Deepr" section comparing against single-vendor tools
- Free tier callouts for providers that offer free API access

**Demo Data Endpoint**
- `POST /api/demo/load` backend endpoint that creates sample experts and research jobs
- "Load Demo Data" button in Settings page Environment section
- Populates the UI with sample data for exploring the dashboard without a running research pipeline

**UX Improvements**
- Cost Intelligence accuracy disclaimer banner (costs are Deepr-internal estimates, check provider billing consoles)
- Standardized error states across all 10+ pages: muted icon, "Unable to load [thing]", consistent backend-down messaging, retry buttons
- Loading skeleton on Cost Intelligence page (was showing $0 values during load)
- Expert Profile tabs overflow scroll on mobile (5 tabs: Chat, Claims, Gaps, Decisions, History)
- Overview empty state no longer references CLI commands - links to web-native budget controls instead
- Expert Hub error state copy improvement
- `deepr config set` now supports CLI UX aliases:
  - `cli.animations` -> `DEEPR_ANIMATIONS` (`off|light|full`)
  - `cli.branding` -> `DEEPR_BRANDING` (`off|on|auto`)
  - Unknown `cli.*` keys now fail with explicit validation errors

### Fixed
- Removed dead code: `api/activity.ts`, `api/traces.ts`, `components/shared/stat-card.tsx` (never imported)
- Added `p-6` padding to Help page wrapper (missing from all other pages' pattern)
- Export dropdown in Result Detail now closes on Escape key press
- "Submit Research" -> "New Research" button text consistency in Results Library
- Unsafe type assertion in Expert Profile history query replaced with proper `ExpertHistoryEvent` interface
- Gemini provider import hardening:
  - provider initialization now degrades safely when `google-genai` is present but incompatible
  - clear runtime errors are retained for unavailable Gemini client operations
  - prevents unrelated command/test breakage from optional SDK import failures

**Background Job Polling + WebSocket Push**
- Flask-SocketIO initialization with `cors_allowed_origins="*"` and threading async mode
- Background poller thread that checks PROCESSING jobs every 15 seconds via provider API
- WebSocket events: `job_created` on submit, `job_completed`/`job_failed` on poller detection
- `to_dict()` method on `ResearchJob` dataclass (enum, datetime, Path serialization)
- `POST /api/jobs/cleanup-stale` endpoint to mark stuck/orphaned jobs as failed
- `socketio.run()` replaces `app.run()` for WebSocket support
- Frontend already handled all events via `use-websocket.ts` - now actually connected

**Web Dashboard UX Overhaul**
- Skeleton loading states: `CardGridSkeleton`, `DetailSkeleton`, `FormSkeleton`, `DashboardSkeleton` replacing all spinner patterns
- Honest progress phases: replaced fake time-based 6-phase progress with 3 status-based phases (Queued/Processing/Complete)
- Standardized all form controls to shadcn/ui components (Input, Select, Button) across research-studio, expert-hub, results-library, expert-profile
- Copy-to-clipboard button on result-detail page with toast feedback
- Cmd+Enter / Ctrl+Enter keyboard shortcut to submit research from textarea
- Drag-and-drop file upload on research studio with visual feedback and file type filtering
- Pagination on results library (12 per page, page controls, total count)
- Mobile hamburger navigation via Sheet component (sidebar hidden on small screens)
- FOUC prevention: critical CSS inlined in index.html
- Skip-to-content link for keyboard/screen-reader accessibility
- Settings page: Environment info card showing provider, queue, storage, API key status
- Research Live completed state: enriched with prompt text, 4-stat grid (cost, tokens, completed date, model), content preview with markdown stripping

### Fixed
- Timezone naive/aware datetime comparison errors across 10+ locations in app.py (`_ensure_utc()` helper)
- JSX unicode escape `\u21B5` rendering as literal text in keyboard hint (moved to JS expression)
- Flask serving stale asset hashes when restarted before rebuild
- Results API sort crashing on naive datetime comparison
- Activity feed sort crashing on naive datetime comparison

---

## [2.8.0] - 2026-02-04

### Added

**Provider Intelligence (5.1, 5.3)**
- Latency percentiles (p50, p95, p99) in `ProviderMetrics` for performance analysis
- Success rate tracking by task type (research, chat, synthesis, planning)
- `deepr providers benchmark --history` command to view historical benchmark data
- `deepr providers benchmark --json` for machine-readable output
- Exploration vs exploitation in provider routing (10% exploration rate, configurable)
- Auto-disable failing providers (>50% failure rate, 1hr cooldown)
- `deepr providers status` shows auto-disabled providers with cooldown info

**Advanced Context (6.4, 6.5)**
- Temporal knowledge tracking wired into `ResearchOrchestrator`
- `--temporal` flag in `deepr research trace` shows findings/hypothesis timeline
- `--lineage` flag in `deepr research trace` shows context flow visualization (tree view)
- Context chaining via `ContextChainer` for phase-to-phase handoff
- Temporal data export in trace files

**Web Dashboard Overhaul**
- Rebuilt frontend with React 18, Vite, Tailwind CSS 3.4, and Radix UI (shadcn/ui pattern) component library
- 10 pages with code-split lazy loading via React.lazy and Suspense
- New pages: Overview (activity feed, system health), Research Studio (mode selector, model picker), Research Live (WebSocket progress), Result Detail (markdown viewer, citation sidebar, export), Expert Hub (list, stats, knowledge gaps), Expert Profile (chat, gaps, history), Cost Intelligence (charts, budget sliders, anomaly detection), Trace Explorer (execution spans, timing, cost)
- WebSocket integration for real-time job status updates (Socket.io client connected in AppShell)
- Command palette (Ctrl+K) for quick navigation across all pages
- Light/dark/system theme support via Zustand store
- Toast notifications via Sonner for all user-facing actions
- Recharts for cost trends, model breakdown, and utilization charts
- Fixed: division by zero in cost utilization calculations
- Fixed: unsafe URL parsing in citation display
- Fixed: budget sliders firing mutations on every pixel drag (debounced)
- Fixed: expert profile "Research this" button was not wired
- Fixed: research studio mode selector was ignored in submit payload
- Fixed: citation sidebar invisible on mobile viewports
- Removed dead code: unused type files, legacy pages, stale constants, unused components

**Expert System**
- `deepr expert plan` command to preview a learning curriculum without creating an expert or spending money
- Outputs as Rich table (default), JSON (`--json`), CSV (`--csv`), or prompts only (`-q`)
- Supports `--budget`, `--topics`, and `--no-discovery` options

**Expert & Decision Formalization (Phase 5)**
- Canonical types in `core/contracts.py`: `Source`, `Claim`, `Gap`, `DecisionRecord`, `ExpertManifest` with full serialization (`to_dict()`/`from_dict()`)
- `TrustClass` enum (primary, secondary, tertiary, self_generated) and `DecisionType` enum (routing, stop, pivot, budget, belief_revision, gap_fill, conflict_resolution, source_selection)
- `gap_scorer.py` with EV/cost ranking: `score_gap()` and `rank_gaps()` for rational gap prioritization
- Adapter methods: `Belief.to_claim()`, `KnowledgeGap.to_gap()` on existing classes for backward compatibility
- `ExpertProfile.get_manifest()` composes claims, scored gaps, and decision records into a typed snapshot
- `ThoughtStream.record_decision()` creates structured `DecisionRecord` objects alongside existing thought logging
- `--explain` flag now shows decision table (type, decision, confidence, cost impact) in CLI
- Web: Expert Profile page gains Claims tab, Decisions tab, and scored Gaps tab with EV/cost badges
- Web: Trace Explorer gains collapsible decision sidebar for the current job
- Web API: `GET /api/experts/<name>/manifest`, `/claims`, `/decisions` endpoints
- MCP: `deepr_expert_manifest` and `deepr_rank_gaps` tools for agent consumption
- 69 new unit tests (contracts, gap scorer, adapters)

**Real-Time Progress (7.3)**
- `ResearchProgressTracker` for live progress updates during research
- `--progress` flag in `deepr research wait` shows phase tracking with progress bar
- Phase detection (queued -> initializing -> searching -> analyzing -> synthesizing -> finalizing)
- Partial results streaming when provider supports it
- Customizable poll intervals via `--poll-interval`

**Output Improvements (7.6)**
- `print_truncated()` utility for long output with "use --full to see all"
- `make_hyperlink()` and `print_report_link()` for clickable links in supported terminals

### Changed

- `ProviderMetrics.record_success()` and `record_failure()` now accept optional `task_type` parameter
- `AutonomousProviderRouter.record_result()` now accepts optional `task_type` parameter
- `AutonomousProviderRouter.select_provider()` now filters auto-disabled providers and adds exploration
- `get_status()` includes latency percentiles and task type stats per provider
- Enhanced providers CLI with historical data display and JSON export
- `MetadataEmitter.save_trace()` now includes temporal knowledge data when tracker is set
- Removed deprecated `run single` and `run campaign` commands (use `research` instead)

---

## [2.7.0] - 2026-02-04

### Added

**Context Discovery (6.1-6.3)**
- `deepr search query "topic"` command with semantic + keyword search across prior research
- `deepr search index` to index reports with embeddings (text-embedding-3-small)
- `deepr search stats` to view index statistics
- Automatic related research detection on `deepr research submit`
- `--context <job-id>` flag to include prior research as context
- `--no-context-discovery` flag to skip automatic detection
- Stale context warnings (>30 days old)
- Context truncation for token budget management
- Job ID prefix matching (can use `--context abc123` instead of full UUID)

**Observability Improvements (4.2, 4.4, 4.5)**
- Instrumented `core/research.py` with spans for submit, completion, cancel operations
- Instrumented `experts/chat.py` with spans for tool calls and message handling
- Cost attribution per span with token counts
- ThoughtStream decision summary generation (`generate_decision_summary()`, `get_why_summary()`)
- Research quality metrics: `EntropyStoppingCriteria`, `InformationGainTracker`, `QualityMetrics`
- Temporal knowledge tracking with `TemporalKnowledgeTracker`

**Code Quality**
- Configuration consolidation: single `Settings` class in `core/settings.py`
- ExpertProfile refactoring with composed managers (`budget_manager.py`, `activity_tracker.py`)
- 300+ new tests (3100+ total)

### Changed

- Interactive mode (`deepr` with no args) now shows model picker with cost estimates
- Improved test stability with faster hypothesis strategies

### Fixed

- Flaky hypothesis test `test_episode_tags_preserved` (42+ second generation time)
- Windows console Unicode encoding for ThoughtStream summaries

---

## [2.6.0] - 2026-02-03

### Added

**Documentation Overhaul**
- Rewrote README to better communicate value proposition for enterprise users (cloud architects, CIOs)
- Added "MCP + Skills" section highlighting research infrastructure for AI agents
- New workflow example: Claude Code -> query expert -> fill knowledge gaps -> continue with accurate info
- Emphasized expert system differentiation: self-aware, self-improving, persistent, portable
- Enterprise-focused examples: competitive intelligence, due diligence at scale, institutional knowledge retention
- Updated decision table and "What You Can Do" section with AI agent capabilities first

**CLI Trace Flags (4.1)**
- `--explain` flag on `deepr research` and `deepr run focus` shows task hierarchy with model/cost reasoning
- `--timeline` flag renders Rich table with offset, task, status, duration, cost per phase
- `--full-trace` flag dumps complete trace JSON to `data/traces/{job_id}_trace.json`
- `TraceFlags` dataclass wired through CLI command decorators, backward compatible

**Output Modes (7.1)**
- `OutputMode` enum: MINIMAL (default), VERBOSE, JSON, QUIET
- `OutputContext` and `OutputFormatter` for consistent output across commands
- `@output_options` decorator adds `--verbose`, `--json`, `--quiet` to commands
- Conflicting flags rejected with clear error messages

**Gemini Deep Research Agent (5.4)**
- Native Gemini Deep Research support via Google Interactions API (`client.interactions.create()`)
- Dual-mode `GeminiProvider`: deep research agent for async research, `generate_content` for regular queries
- Model detection routes `deep-research` models to Interactions API automatically
- File Search Store integration for document grounding (`client.file_search_stores.create()`)
- Citation URL resolution for Google grounding redirect URLs
- Adaptive polling intervals: 5s (first 60s), 10s (60-300s), 20s (300s+)
- Experimental API warning suppression for stable operation
- Added `gemini/deep-research` to model capabilities registry
- 19 new tests covering deep research submission, status polling, file stores, citations, and adaptive polling

**Auto-Fallback on Provider Failures (5.2)**
- `AutonomousProviderRouter` wired into `_run_single()` in `cli/commands/run.py`
- Retry with fallback: timeout retries once then falls back, rate limit falls back immediately, auth error skips provider
- Max 3 fallback attempts before failure
- `_classify_provider_error()` bridges provider errors to core error hierarchy
- Vector store graceful degradation when falling back to non-OpenAI providers
- Fallback events emitted to trace and shown in `--explain` output
- `--no-fallback` flag on `focus`, `single`, `docs`, `run_alias`, `research` commands

**Cost Attribution Dashboard (4.3)**
- `deepr costs breakdown --period` flag (today, week, month, all) replaces `--days`
- `deepr costs timeline` command with ASCII bar chart, anomaly detection (>2x average), `--weekly` aggregation
- `deepr costs expert "Name"` subcommand shows per-expert cost breakdown, budget utilization, per-operation costs
- `CostAggregator.get_entries_by_expert()` and `get_expert_breakdown()` helpers
- Cost metadata (`total_cost`, `cost_by_model`) stored in `reports/{job_id}/metadata.json`

**Docker and Deployment**
- Dockerfile with Python 3.11-slim, non-root user (UID 1000), healthcheck
- `.dockerignore` reducing build context from 168MB to ~2MB
- `docker-compose.yml` with bridge network, resource limits (512MB, 1 CPU)

**Cloud Deployment Templates (10.1)**
- AWS SAM/CloudFormation template (`deploy/aws/`) with Lambda API, SQS queue, Fargate worker, DynamoDB, S3
- Azure Bicep template (`deploy/azure/`) with Functions, Queue Storage, Container Apps, Cosmos DB, Blob Storage
- GCP Terraform template (`deploy/gcp/`) with Cloud Functions, Pub/Sub, Cloud Run, Firestore, Cloud Storage
- Shared API library (`deploy/shared/deepr_api_common/`) with validation, security headers, response utilities
- API key authentication via Authorization Bearer token and X-Api-Key header
- CORS preflight OPTIONS handling on all endpoints
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options, Cache-Control)
- 90-day TTL on job documents for automatic cleanup (DynamoDB, Firestore, Cosmos DB)
- Input validation with sanitization (prompt length, model validation, UUID format)
- Detailed deployment documentation in `deploy/README.md`

**CI and Code Quality Tooling**
- GitHub Actions CI workflow: lint (ruff) + unit tests on push to `main` and PRs, Python 3.11/3.12 matrix
- `.pre-commit-config.yaml` with ruff (lint+format), trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files, debug-statements
- `[tool.coverage]` in `pyproject.toml`: source/omit config, 60% minimum threshold, show_missing
- `[tool.ruff]` configuration in `pyproject.toml`
- `CONTRIBUTING.md` with setup, dev workflow, code style, testing, and guidelines
- CI enforces coverage minimum (`--cov-fail-under=60`) via `pytest-cov`
- `pytest-cov` added to `[project.optional-dependencies] dev`

### Fixed
- Fixed `pyproject.toml` URLs pointing to wrong GitHub organization
- Moved `test_conversation_memory.py` from unit to integration tests (was loading 4.3GB knowledge graph)
- Fixed model registry tests referencing `gpt-5` instead of `gpt-5.2`
- Fixed staleness urgency test expecting wrong value for missing cutoff date
- Fixed skill frontmatter token count test (limit bumped from 200 to 300 after metadata growth)
- Fixed flaky Hypothesis test `test_negation_detected_as_contradiction` (negation words in generated inputs + deadline exceeded on cold init)
- Fixed flaky Hypothesis test `test_normalize_produces_absolute_path` (drive-relative paths like `H:0` misidentified as absolute on Windows)

### Changed
- Test suite grew from 1300 to 2820+ tests
- Unified all version strings to 2.6.0 across package, CLI, API, and user-agent
- Replaced 47 `print()` calls in 13 library modules with structured `logging` (lazy `%s` formatting)
- Consolidated model pricing into single registry source of truth (`deepr/providers/registry.py`); removed hardcoded pricing from `base.py`, `research.py`, and provider modules
- Tightened exception handling in core, providers, and MCP server (bare `except Exception` replaced with `openai.OpenAIError`, `GenaiAPIError`, `DeeprError`, `OSError`, etc.)
- Tightened exception handling in storage and services: `storage/local.py` (5 catches -> `OSError`), `storage/blob.py` (7 catches -> `AzureError`), `core/jobs.py` (4 catches -> `json.JSONDecodeError`/`KeyError`/`TypeError`/`ValueError`), `utils/scrape/fetcher.py` (1 catch -> `requests.RequestException`/`json.JSONDecodeError`/`KeyError`/`ValueError`)
- Split monolithic `cli/commands/semantic.py` (3,318 lines) into `cli/commands/semantic/` package: `research.py` (research/learn/team/check commands), `artifacts.py` (make/agentic commands), `experts.py` (expert subcommands). Backward-compatible re-exports in `__init__.py`
- Removed `sys.path.insert()` hack in MCP server; uses standard package imports
- Removed 4 DEBUG `print()` statements left in production code (`semantic.py`)
- Fixed 3 bare `except:` catches with specific exception types (`prep.py`, `web/app.py`)
- Single-sourced version string: 5 modules now import `__version__` from `deepr/__init__.py` instead of hardcoding
- Replaced last `sys.path.insert()` in MCP server (skills loading) with `importlib.util.spec_from_file_location()`
- Converted remaining `print()` in `formatting/normalize.py` and `formatting/converters.py` to structured logging
- Dockerfile uses `pip install --no-cache-dir .` instead of editable install

- Removed redundant `black` from pre-commit hooks (ruff-format covers formatting) and `[tool.black]` from `pyproject.toml`
- Replaced 10 stub comments in API routes with explanatory comments noting CLI-managed features
- Cleaned up API route stubs in `config.py`, `jobs.py`, `cost.py`, `results.py`

### Removed
- Deleted dead legacy CLI module (`deepr/cli.py`, 350 lines) shadowed by `deepr/cli/` package
- Deleted `setup.py` (fully redundant with `pyproject.toml`)

## [2.5.0] - 2026-01-15

### Added

**MCP Advanced Patterns Implementation**
- Added Dynamic Tool Discovery with BM25/vector search in `deepr/mcp/search/registry.py`
- Added Resource Subscriptions for event-driven async monitoring in `deepr/mcp/state/subscriptions.py`
- Added Human-in-the-Loop Elicitation for cost governance in `deepr/mcp/state/elicitation.py`
- Added Sandboxed Execution for isolated research contexts in `deepr/mcp/state/sandbox.py`
- Added JobManager for background task coordination in `deepr/mcp/state/job_manager.py`
- Added ResourceHandler for MCP resource protocol in `deepr/mcp/state/resource_handler.py`
- Added ExpertResources for expert profile/beliefs/gaps resources in `deepr/mcp/state/expert_resources.py`

**Transport Layer**
- Added Stdio transport for local process communication in `deepr/mcp/transport/stdio.py`
- Added Streamable HTTP transport for cloud deployment in `deepr/mcp/transport/http.py`
- StdioTransport ensures research data never leaves local process tree
- StreamingHttpTransport supports SSE for server-to-client notifications
- HttpClient for connecting to remote MCP servers

**Agent Trajectory Evaluation**
- Added TrajectoryMetrics for tracking agent performance in `deepr/mcp/evaluation/metrics.py`
- Tracks trajectory efficiency (steps vs optimal golden path)
- Tracks citation accuracy (beliefs with cited sources)
- Tracks hallucination rate (invented parameters not in schema)
- Tracks context economy (tokens per task)
- MetricsTracker for aggregating metrics across sessions

**MCP Server Architecture**
- Job pattern for async research: `deepr_research()` returns immediately, poll with `deepr_check_status()`
- SQLite persistence for job state across server restarts
- Reports exposed as MCP Resources (`deepr://reports/{job_id}/final.md`, `summary.json`, etc.)
- Progress notifications via subscription manager
- Structured error responses with `ToolError` dataclass (error_code, retry_hint, fallback_suggestion)
- Trace ID propagation for end-to-end debugging

**Claude Skill Infrastructure**
- Created `skills/deepr-research/` directory following Claude Skill conventions
- Added SKILL.md with activation keywords and progressive disclosure
- Added reference documents for research modes, expert system, cost guidance, prompt patterns, troubleshooting, and MCP patterns
- Added scripts for research decision classification and result formatting
- Added templates for research report output
- LLM-optimized tool descriptions with usage hints, negative guidance, example invocations
- Prompt primitives: `deep_research_task`, `expert_consultation`, `comparative_analysis`
- Install scripts (`install.sh`, `install.ps1`) with env var checking
- `deepr_status` health check tool

**Security Hardening**
- SSRF protection: blocks requests to private/internal IPs, optional domain allowlist
- Path traversal protection via `PathValidator` in sandbox module
- MCP Sampling primitives for human-in-the-loop (`SamplingRequest`, `SamplingResponse`)

**Multi-Runtime Configuration**
- Config templates for OpenClaw, Claude Desktop, Cursor, VS Code
- Docker variant config with volume mounts
- Per-runtime setup guides in `mcp/README.md`

**Claude-Specific Optimizations**
- Chain of Thought guidance prepended to research tool descriptions
- Lazy loading for large reports (summary + resource URI, configurable threshold)

**Elicitation System**
- ElicitationHandler for structured user input requests via JSON-RPC
- BudgetDecision enum with APPROVE_OVERRIDE, OPTIMIZE_FOR_COST, ABORT options
- CostOptimizer for dynamic model switching when optimizing for cost
- Budget limit triggers that pause jobs and request user decisions
- JSON Schema support for structured elicitation responses

**Sandbox System**
- SandboxManager for isolated execution contexts
- PathValidator with path traversal attack prevention
- SandboxConfig for configurable isolation settings
- Filesystem isolation with strict working directory enforcement
- Report synthesis and merge for extracting results from sandboxed contexts

**Test Coverage**
- 302 tests passing across MCP and skill modules
- 34 tests for transport layer (stdio and HTTP)
- 34 tests for trajectory metrics
- 37 tests for elicitation module
- 36 tests for sandbox module
- Property-based tests using Hypothesis for core skill logic

## [2.3.0] - 2025-11-15

### Added

**Always-On Prompt Refinement**
- Added `DEEPR_AUTO_REFINE` configuration option in .env
- When enabled, automatically applies prompt refinement to all research submissions
- No need to specify `--refine-prompt` flag each time
- Provides seamless best practices for all queries

**Campaign Pause/Resume Controls**
- Added `deepr prep pause` command to pause active research campaigns
- Added `deepr prep resume` command to resume paused campaigns
- Execute command now checks pause status before running
- Enables mid-campaign intervention for human oversight
- Supports both specific plan IDs and most recent campaign

**Persistent Vector Store Management**
- Added `deepr vector create` command to create reusable vector stores
- Added `deepr vector list` command to list all vector stores
- Added `deepr vector info` command to show vector store details
- Added `deepr vector delete` command to remove vector stores
- Added `--vector-store` flag to `deepr research submit` for reusing existing stores
- Vector stores can be looked up by ID or name
- Enables document indexing once, reuse across multiple research jobs

**Batch Job Download and Queue Sync**
- Added `--all` flag to `deepr research get` for downloading all completed jobs
- Added `deepr queue sync` command to update all job statuses without downloading
- Automatically checks provider for all pending jobs and downloads completed ones
- Useful for batch processing after submitting multiple research jobs
- Queue sync updates local status to match provider without downloading results

**Enhanced Cost Management**
- Added `--period` flag to `deepr cost summary` (today, week, month, all)
- Cost breakdown by model showing per-model spending and job counts
- Budget tracking with percentage of daily/monthly limits
- Improved statistics with total jobs, completed count, and averages

**Research Export**
- Added `deepr research export` command for exporting in multiple formats
- Supports markdown, txt, json, and html export formats
- Automatic output path generation or custom output location
- Includes job metadata, content, and usage statistics in exports

**Build and Installation**
- Added pyproject.toml for modern Python packaging
- Created INSTALL.md with platform-specific instructions
- Added install scripts for Linux/macOS (install.sh) and Windows (install.bat)
- Added Makefile for common development tasks
- Added build scripts (build.bat for Windows)
- Updated setup.py to version 2.3.0
- Console script entry point enables `deepr` command globally

**Configuration Management**
- Added `deepr config validate` command to check configuration and API connectivity
- Added `deepr config show` command to display current settings (sanitized)
- Added `deepr config set` command to update configuration values
- Validates API keys, directories, and budget limits
- Tests provider connectivity during validation

**Analytics and Insights**
- Added `deepr analytics report` command for usage analytics
- Success rates, model performance, cost analysis by time period
- Added `deepr analytics trends` showing daily job counts and costs
- Added `deepr analytics failures` for failure pattern analysis
- Identifies most cost-effective models and provides recommendations

**Prompt Templates**
- Added `deepr templates save` to save reusable prompts with placeholders
- Added `deepr templates list` to view all saved templates
- Added `deepr templates show` to display template details
- Added `deepr templates delete` to remove templates
- Added `deepr templates use` to submit research using templates
- Tracks usage count for each template
- Supports placeholder substitution (e.g., {industry}, {region})

### Changed
- Execute command now prevents execution of paused campaigns
- Improved human-in-the-loop controls with pause/resume workflow
- Research submit command now supports both new file uploads and existing vector stores
- Simplified README Quick Start to focus on pip install workflow

## [2.2.0] - 2025-10-29

### Added

**File Upload & Vector Stores**
- Added `--files` / `-f` flag to `deepr research submit` for document upload
- Automatic vector store creation and indexing for semantic search
- Support for PDF, DOCX, TXT, MD, and code files
- Successfully tested with multi-document research workflows

**Automatic Prompt Refinement**
- Added `--refine-prompt` flag to optimize research queries automatically
- Uses GPT-5.2-mini to enhance prompts with temporal context and structure (~$0.001 per refinement)
- Automatically adds current date context ("As of October 2025...")
- Suggests structured deliverables and flags missing business context
- Provides before/after comparison of prompt improvements

**Ad-Hoc Result Retrieval**
- Added `deepr research get <job-id>` command for on-demand result downloads
- Check provider status and download results without continuous worker
- Perfect for daily check-ins, CI/CD integration, and casual usage
- Eliminates need for 24/7 worker process

**Detailed Cost Breakdowns**
- Added `--cost` flag to `deepr research result` command
- Shows comprehensive token usage breakdown (input/output/reasoning)
- Displays separate cost calculations for input and output tokens
- Includes model pricing information (per 1M tokens)
- Shows job metadata and prompt context

**Human-in-the-Loop Controls**
- Added `--review-before-execute` flag to `deepr prep plan` command
- Tasks start unapproved when flag is used, requiring explicit human approval
- Prevents autonomous execution without oversight
- Use `deepr prep review` to approve/reject tasks before execution

**Provider Resilience**
- Implemented retry logic with exponential backoff (3 attempts: 1s, 2s, 4s delays)
- Graceful degradation: automatically falls back from o3-deep-research to o4-mini-deep-research
- Handles rate limits, connection errors, and timeouts automatically
- Ensures research completes even if preferred model is unavailable

### Changed

**CLI Commands**
- Renamed `poll` to `get` for clearer intent (retrieve results)
- Improved command descriptions and help text across all commands
- Enhanced error messages with actionable guidance

**Documentation**
- Restructured README Quick Start with clear numbered steps
- Added prerequisites section (Python 3.9+, Node.js 16+)
- Added "Why Deepr?" value proposition with key differentiators
- Clarified target audience (researchers, analysts, product teams, developers, AI agents)
- Added cost warning and budget management guidance
- Updated all time/cost estimates to "Estimated: ~$X" format
- Added descriptive context before code example sections
- Fixed grammar issues ("becoming an expert", improved wording)
- Updated Multi-Provider Support section with current October 2025 models
- Removed all emojis from documentation

**ROADMAP**
- Updated from v2.1 to v2.2 release status
- Marked priorities 1-6 as complete or partially complete
- Added implementation details for each completed feature
- Clarified model references (GPT-5, o3-deep-research, o4-mini-deep-research)
- Updated version timeline (v2.3, v2.4, v2.5)
- Updated Agentic Levels table to reflect current progress

### Fixed
- Fixed version inconsistencies throughout documentation (v2.1 -> v2.2)
- Fixed port references (backend: 5000, frontend: 3000)
- Corrected model naming for clarity
- Improved Unicode handling in CLI output for Windows compatibility

### Meta-Research
- Used Deepr itself to analyze README and ROADMAP for refinement opportunities
- Applied 12+ specific recommendations from research report
- Research cost: $2.00 for comprehensive documentation review
- Demonstrated platform capabilities through self-improvement

## [2.1.0] - 2025-10-XX

### Added
- Multi-phase research campaigns with adaptive planning
- GPT-5.2 as research lead for reviewing and planning phases
- Context chaining with automatic summarization
- Dynamic research teams (experimental)
- Web UI with real-time updates and cost analytics

### Changed
- Improved background worker with stuck job detection
- Enhanced cost tracking from OpenAI token usage

## [2.0.0] - 2025-10-XX

### Added
- Initial release of Deepr
- Single deep research jobs via CLI
- OpenAI Deep Research integration (o3, o4-mini models)
- SQLite queue and filesystem storage
- Background worker with automatic polling
- Basic web UI

---

For more details on upcoming features, see [ROADMAP.md](../ROADMAP.md).
