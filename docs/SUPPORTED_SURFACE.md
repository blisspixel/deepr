# Supported Surface

Status: v2.50.12 current main, 2026-09-04. This document defines what users and host
agents can rely on today, what is experimental, what is planned only, and what
data remains portable if development stops. Unattended metered dispatch remains
frozen until provider account-control adapters land. The narrow attended absorb
path is structurally complete but remains execution-blocked without verified
provider prepaid-no-overage or hard-stop evidence.

**v2.50.12 preserves cited evidence and measurement periods.** Consult source
excerpts use exact study anchors to retain passages beyond the opening text,
with existing source and character limits. First-world hard-negative cases
remain in false-support measures and stay out of negative-transfer measures.
OpenRouter key checks use current-month counters for monthly headroom while
preserving lifetime usage separately. No semantic or dispatch authority widens.

**v2.50.9 added bounded OpenRouter comparison without paid dispatch.** Seven
exact cross-family model slugs support write-free research previews. A no-key
public route check and a hidden-prompt current-key control check produce
sanitized, non-authorizing evidence without inference. Automatic routing,
expert routing, evaluation, reservation, and provider construction remain
blocked. Exact response identity, parent settlement, complete usage evidence,
and final billing reconciliation remain required before execution can ship.

**v2.50.8 makes the first local expert path complete and testable.** README,
Quick Start, root help, research help, and local profile creation now direct an
operator through profile creation, trusted source retention, local study,
grounded brief creation, and local consultation. The path constructs no paid
provider and retains the cited source passage in the consult context. Gated
metered research, team, agentic, and chat help no longer present blocked
invocations as runnable examples. No execution authority widened in this
release.

**v2.50.7 keeps MCP job state and task execution monotonic.** SQLite persistence
migrates legacy databases in place and preserves plans, active tasks, temporal
findings, and hypothesis history when a caller saves only one part of a job.
Finished jobs cannot be revived by a stale provider observation, accumulated
cost cannot decrease, and progress, cost, confidence, and estimates reject
non-finite JSON values before mutation. Task dispatch validates identities,
coroutines, dependency references, and dependency cycles before work starts;
global cancellation stops running work across concurrent batches. Wildcard
subscriptions are limited to canonical campaign and expert base resources.

**v2.50.6 keeps local report identity and retention deterministic.** Readable
directory lookup verifies the complete stored job ID, trusted metadata fields
cannot be replaced by caller metadata, and report files are replaced atomically.
Listing includes campaign reports without exposing internal metadata sidecars.
Retention operates per report, preserves fresh campaigns, and rejects negative
thresholds. Optional quota observations treat malformed or non-finite values as
unavailable and cannot restore a stale snapshot after a failed forced refresh.

**v2.50.5 bounds acquisition proposals before execution.** Model-proposed
search plans accept only strings, remove case-insensitive duplicates, and run
at most four queries per arm. An empty topic makes no completion call. REST
rate-limit responses use a positive numeric retry delay, and release builds
verify that local frontend dependencies do not enter either distribution.

**v2.48.0 makes expert consultation local or plan-only.** CLI consultation
uses confined local Ollama by default. An explicit plan may execute only after
the existing no-surprise-bills gate proves it safe. CLI, MCP, and A2A requests
for metered consult synthesis are blocked before transaction and paid-client
construction; budget and legacy consent flags cannot enable them.

**v2.49.0 separates cumulative credits from each paid job ceiling.** A person
at the CLI may explicitly add any exact-cent amount to one persistent local
metered-spend wallet. Every later settled API dollar and active hold draws down
that pool across providers, while every paid job still requires a separate
finite confirmed ceiling and durable reservation. There is no overdraft,
automatic refill, or metered fallback. Wallet funding does not transfer or
verify provider funds. Provider-side prepaid credits or a provider-enforced
hard stop with overage disabled are also mandatory for dispatch. An open
postpaid account remains blocked even with wallet credits. MCP,
schedules, loops, and automatic fallback ignore the local wallet.

The Expert Hub has a user-curated flagship tier and a complete standard tier.
The pictured maintainer reference fleet currently selects 25 flagship experts;
a clean install does not seed that roster or guarantee that count. Its readiness
field reports only whether durable presentation structure exists: a portrait,
standpoint, position, studied finding, and retained source. It does not certify
correctness, importance, or expert quality.

**Historical v2.47.0 attended authority is superseded by the v2.49.0 wallet.** A person at the CLI could issue a typed,
expiring grant with a non-configurable $2 total maximum, then run the supported
API-backed absorb path under its own narrower call reservation and consent.
Settled API cost and active holds share one drawdown from grant issuance. Local
and admitted prepaid-plan work records $0 and does not consume it. MCP,
schedules, loops, automatic fallback, and other metered surfaces cannot use the
grant. Existing grant files do not migrate into wallet authority.

**v2.46.0 renames the files inside an expert directory.** They were named
after the commands that wrote them; they are now named for what they are:
`self.json`, `noticed/`, `hold/current.json` and `hold/history.json`,
`became/`, `attend/`, `met/`. `corpus/` is unchanged.

This matters to the portability contract below, so it is stated here rather
than only in the changelog. Nothing is lost and nothing needs converting by
hand: `deepr expert migrate` moves an expert in place, dry run by default, and
every reader resolves the old path when only the old path exists, so an
un-migrated expert stays fully readable. The maintainer's 57-expert reference
fleet was migrated and verified field by field against a pre-migration backup
with zero differences; that count is evidence from one local fleet, not an
installed product invariant. `beliefs/` and `knowledge/` are v1 storage and are
untouched.

**Development later shipped in v2.45.0 added the expert study surface as
experimental**: retained corpus
(`corpus/index.jsonl` plus content-addressed sources), the multi-lens study pass,
coverage reporting, and the notebook render. These are additive; existing belief
stores are untouched and keep working. The study pass proposes findings and never
writes to the belief store, so nothing here can alter an expert's beliefs without
a separate, explicit absorb. Perspective lenses are provisional pending a
matched-spend evaluation (see [expert-evidence-base.md](design/expert-evidence-base.md)).

## Support Levels

**Stable** means the surface is part of the supported contract. Changes should
be additive, backward compatible, or documented with a migration note.

**Experimental** means the surface works and is tested, but command names,
payload details, or operational guidance may still change before 3.0.

**Visible/read-only** means Deepr can inspect or model the capacity source, but
does not yet execute work through it.

**Planned** means the roadmap describes intent only. It is not shipped UX and
must not be described as usable capacity.

## Stable Today

- Write-free bounded research preview through `deepr research --preview` for
  provider/model/tool combinations with a complete finite cost envelope.
  Unattended metered dispatch remains blocked until authenticated provider
  account-control and current credential-identity adapters are installed.
- Budget ceilings, cost estimates, and the canonical append-only cost ledger.
  The metered transaction substrate uses cross-process maximum-cost
  reservations, conservative ambiguous-outcome settlement, terminal-state
  reconciliation, disabled hidden SDK retries, and provider receipt IDs.
  Strict CLI and web views expose settled spend, active and unresolved holds,
  effective authority, and maximum new-call headroom. Offline provider-billing
  preview and explicit fail-closed apply are stable. Attended status reports a
  single cumulative wallet drawdown rather than misleading day, week, or month
  balances. Provider hard-stop status is reported separately.
- Explicit local and safety-eligible plan selection. Automatic cross-provider
  metered fallback is disabled.
- Local report storage under the configured reports root.
- Local expert creation, expert import/export, profile storage, and bounded
  local or explicit plan consult/query surfaces.
- Unreviewed blueprint drafts, zero-call structural preflight, and
  operator-attested expert blueprints and decision outcomes. Drafts and
  preflight artifacts are non-authoritative. Applied revisions and outcome
  observations are local append-only records with published v1 schemas. Deepr
  does not verify reviewer identity or claim human authorship. These artifacts
  make purpose and later results inspectable but never authorize spend,
  knowledge writes, routing changes, or external actions.
- Brief positions may register prospective predictions with an observable
  falsifier criterion and ISO check date. The position ledger preserves each
  prediction with the exact position version that made it. `deepr expert
  experience NAME` builds a bounded `$0`, read-only derived view over position
  history, consult trace metadata, and corrected outcome observations. It does
  not accept a ledger or outcome from another expert and does not expose trace
  content unless the stored expert roster matches. It does not decide whether
  a prediction fired, infer whether advice was good, link an outcome to a
  prediction by meaning, or apply a learning change.
- `deepr eval expert-value` template generation and review aggregation. The
  evaluator binds a complete four-arm matrix to the exact operator-attested
  blueprint and frozen source-world hashes, reports separate quality, risk,
  transfer, effort, cost, and outcome-link measures, makes no external calls,
  and selects no winner. Trial semantic and protocol assertions are operator
  attestations with unverified identity and no human-authorship claim.
  Operator-attested mode does not open referenced files. Explicit
  `--artifact-root` mode recomputes every declared local SHA-256 digest under a
  root-confined path policy with no network access. It does not execute the four
  arms; those runs use separately governed capacity and may incur the costs
  recorded by the review.
- Relocatable data through coordinated roots written by `deepr init --data-dir`.
  `DEEPR_DATA_DIR` covers expert, queue, trace, benchmark, observability, and
  selected MCP state; reports use `DEEPR_REPORTS_PATH`. Synced-folder portability supports
  sequential device use only: one Deepr writer or service at a time, then wait
  for sync before switching devices. Concurrent multi-device mutation is
  planned, not shipped.
- CLI output modes: `--json`, `--quiet`, `--verbose`, and trace flags where
  documented. The shared `OperationResult` JSON envelope is versioned as
  `deepr-cli-operation-result-v1`.
- The published schema registry under `docs/schemas/`. Descriptive fields are
  additive inside v1 by default. Entries labeled as closed authority accept
  additions only under their ignored `extensions` object; changing tools,
  credentials, spend, transport, identity, validation, or other authority
  requires a new schema version.

## Experimental But Usable

- Web dashboard and dashboard APIs.
- Expert councils, task planning contracts, and approval flows. Standalone
  metered expert chat is gated as described under Visible Or Planned Only.
- `deepr eval consult --structured-local` is an eval-only owned-local graph. It
  freezes selected expert packets, generates independent question-specific
  positions, requires every branch, and performs one local synthesis under
  fixed call, token, context, artifact, elapsed-time, concurrency, transport,
  and `$0` accounting contracts. It is not an MCP tool or a replacement for
  `deepr expert consult`.
- Expert skill inventory, metadata, installation, and scaffolding. Python and
  MCP tool execution is quarantined before module import, process creation, or
  network dispatch; legacy `run-skill` validates and exits blocked.
- MCP stdio server and MCP HTTP serve mode. Dual-era protocol support for the
  MCP `2026-07-28` revision (modern per-request `_meta` negotiation,
  `server/discover`, `subscriptions/listen`, Streamable HTTP header/Origin
  rules) while continuing to serve legacy `initialize`-era clients
  (`2025-06-18`, `2025-03-26`, `2024-11-05`) on both transports.
  Local job persistence migrates legacy schemas without replacing parent rows,
  retains nested plans and belief history across partial saves, and marks
  interrupted jobs failed with no active tasks after restart. Terminal job
  state is monotonic against stale provider polling. Dependency dispatch
  rejects unknown references and cycles before execution, and cancellation
  stops tracked running coroutines rather than changing status alone.
- Published Agent Plugins 1.0.0 package foundation under
  `packages/deepr-agent-plugin`. The package uses an installed `deepr-mcp`
  stdio executable, a spec-conformant Agent Skill, explicit state roots beneath
  `PLUGIN_DATA`, and zero primary and legacy spend ceilings. Its `read_only`
  profile is capability-read-only, not filesystem-immutable: runtime and audit
  databases are expected beneath plugin data, while the installed package must
  remain unchanged. Clean-install and byte-reproducibility checks are blocking,
  including manifest-driven executable search, both MCP protocol eras, paths
  with spaces, and preserved data after package replacement. The ten-tool
  profile inspects existing expert metadata and results; generative consult is
  absent. A new plugin workspace starts with no experts. Follow the
  [Agent Plugins install guide](INSTALL.md#agent-plugins-hosts) for prerequisites
  and explicit workspace provisioning. External host versions need separate
  validation.
- Offline machine-checkable MCP host-interop rollup via
  `deepr mcp conformance` (`deepr-mcp-conformance-v1`): dual-era constants,
  offline consult form checks, remote smoke fail-closed posture, managed
  conversation fail-closed posture, registration-manifest offline shape, and
  the capabilities map. No network, no model, `$0`. Does not score semantic
  answer quality. `deepr doctor` surfaces the same offline rollup under the MCP
  category so host preflight is one command.
- Offline and live no-metered consult validation (`deepr mcp validate-consult`,
  `validate-consult-fleet`) and fail-closed remote smoke / conversation
  validation commands. Remote HTTP tool calls remain blocked until an
  independently enforced cost authority exists.
- MCP durable local expert conversations through
  `deepr_start_expert_conversation`, `deepr_continue_expert_conversation`,
  `deepr_get_expert_conversation`, and `deepr_close_expert_conversation`.
  Opaque application handles, scoped ownership, optimistic concurrency,
  idempotency, frozen expert snapshots, retention, and no metered fallback are
  enforced by the shared conversation core. Managed and remote conversation
  validation currently fail closed before dispatch without cost authority.
- Scoped MCP keys, per-key budgets, per-key rate limits, HTTP concurrency caps,
  HTTP smoke checks, registration manifests, and remote-call audit review.
- Durable spend dispositions for settled cost events without report artifacts
  (`deepr costs dispose`, `dispose-unexplained`, `dispositions`) and
  `deepr costs doctor` matched / disposed / unexplained buckets. The
  append-only cost ledger is never rewritten. Parent-budget transaction
  substrate and offline maximum-charge contract evaluators are present for
  future metered lifecycle re-enable; paid dispatch outside the attended absorb
  path stays blocked.
- `deepr_expert_handoff`, `deepr_expert_loop_status`, and adjacent versioned
  handoff contracts. The MCP loop-status tool, the CLI JSON loop-status command,
  and `/api/experts/{name}/loop-status` share the `deepr-loop-status-v1` rollup
  contract. MCP handoff and loop-status outputs fail closed if the published
  schema version, kind, or required envelope fields drift before dispatch.
- A2A library and validation contracts, not a shipped network service. The
  `A2AServer` class, generated Agent Card, in-memory task manager, consult-task
  adapter, and `deepr a2a validate-host` are tested. Within that prototype,
  `deepr-a2a-task-v1` fails closed if schema version, kind, lifecycle state,
  cost, timestamps, or metadata drift before dispatch. The generated Agent Card
  uses `/.well-known/agent-card.json` with `/.well-known/agent.json` as a
  compatibility alias and advertises `deepr_consult_experts`; completed consult
  tasks attach the full `deepr-consult-v1` payload. The adapter defaults to
  local no-metered synthesis. API synthesis is production-frozen.
  Legacy consent flags and a positive budget remain necessary contract inputs
  but cannot authorize provider dispatch. No `deepr a2a serve` command is
  shipped, task state is not restart-durable, and the custom model is not an
  A2A 1.0 conformance claim.
- Scheduled expert maintenance JSON contracts for sync capacity gates, gap-fill
  waits, reflection waits, health-check action plans, and health-check archive
  confirmations. These are experimental but schema-versioned and additive.
- Durable `ExpertLoopRun` records.
- Fleet self-maintenance: `deepr fleet status` (read-only `$0` roster-health
  rollup, `deepr-fleet-status-v2`, non-creating profile discovery, explicit
  completeness and typed profile, loop-run, and subscription read errors,
  nullable unknown row and aggregate metrics, explicitly labeled observed lower
  bounds, bounded relative-source repair posture, literal single-line stored
  terminal text, and non-zero exit on a failed latest run or unreadable durable
  state),
  `deepr expert sync-all` (one capacity-aware roster pass, `deepr-library-sync-v1`
  roll-up, overlap-locked, finite per-expert budgets, continue-on-error roster
  execution with non-zero final status for full or partial expert failure, fixed
  public failure copy, safe loop-status inspection argv, explicit non-metered
  `--plan <id>` override, and admitted quota-observed plan dispatch when the
  waterfall selects one). Automatic and explicit metered sync-all execution is
  gated; dry-run remains available. The command also preserves
  `would_sync` as a distinct preview state and returns a versioned empty-roster
  completion with a structured local create-expert action. Read-only preflight
  blocks unreadable profile or subscription state before capacity selection,
  and a no-due roster completes without backend lookup. Completed and expected
  early machine outcomes share the additive versioned envelope with explicit
  process status, safe next actions, bounded heartbeat disposition, invariant
  aggregate counts, and a separate `roster_experts` snapshot count. Stored
  expert-name control characters are rendered visibly on one human-output row.
  Dry-run uses the preflight subscription snapshot directly, constructs no
  write-capable maintenance dependency, and reports `dry_run: true` plus
  `state_changes: 0`; its human heading and footer identify it as a preview.
  Experts without subscriptions are not dispatched under `--all`. Fleet
  maintenance also includes
  `deepr fleet install-schedule` (previews or writes root-confined Windows, cron,
  or systemd recipes with atomic per-file replacement; existing files require `--force`; never
  auto-installs). Auto-selection uses cron on macOS with explicit no-catch-up and
  no-jitter limits because native launchd emission is not shipped. The off-box
  heartbeat (`DEEPR_HEARTBEAT_URL`) is configuration-visible and locally
  validated during scheduled dry-run without sending. Real delivery is blocked
  before DNS or HTTP because Deepr cannot prove the external service's marginal
  cost or billing posture. Typed output reports
  `blocked_unmetered_external_service` with failure kind
  `unmetered_external_service`; `attempted` and `delivered` stay false. The URL
  is never logged.
- Pre-sync content-hash change-detection gate, the per-(expert, verb) overlap
  guard + startup jitter, budget degradation tiers + value-of-spend gate, and the
  reservation TTL sweep - deterministic spend/side-effect guards.
- Cross-vendor maker-checker grounding assurance on absorbed beliefs
  (`Belief.grounding_assurance`). `deepr expert absorb` and `deepr expert sync`
  can opt into the checker with `--check-grounding`; `--checker-plan <id>` uses
  a different plan CLI as the checker. On both `deepr expert absorb` and
  `deepr expert sync`, `--second-checker-plan <id>` additionally escalates a weak
  first verdict to a genuinely independent third-vendor checker (built lazily, so
  a clean run never pays for it); two independent refutations leave the claim
  unverified (never assurance-stamped) and flag it, rather than promoting it to
  trusted knowledge. Grounding stays advisory throughout - it never blocks
  storage. The checker is off by default, dry runs
  do not check, and metered API checking is not automatic. Expert handoff
  payloads preserve per-claim `grounding_assurance` and include verified-claim
  counts by assurance level. The verdict is model judgment; vendor diversity and
  spend gates are deterministic routing requirements.
- Deepr OKF 0.2 profile export and absorb paths. Export targets the published
  hard bundle rules through `deepr-okf-profile-v2`: concept frontmatter starts
  on the first line with a non-empty `type`, the root index declares
  `okf_version: "0.2"`, and the reserved log is frontmatter-free and grouped
  newest first. The `$0` validator uses pinned offline fixtures and accepts
  unknown concept types, unknown extension keys, omitted optional fields, and
  broken links as the specification requires. Generated bundles remain
  derived views over canonical expert state. `sources` comes from stored
  evidence references, and `verified` appears only for recorded grounding
  assurance that reflects an actual checker. Absorb treats every non-reserved
  Markdown file as an untrusted concept ingestion source and still passes each
  candidate through verified extraction. OKF computation execution and runtime
  attestation are not shipped.
- Indirect prompt-injection boundaries for fresh retrieval context, report
  absorption, first-party tool findings, local document review previews,
  campaign context summarization, completed-research review, company-intelligence
  reuse, and team-result synthesis. These delimit and sanitize untrusted source
  text before model prompts, while semantic acceptance still depends on the
  existing verification and trust-floor gates.
- Host-facing MCP expert handoff and loop-status payloads sanitize derived
  string fields before downstream host consumption. The structured expert store
  remains canonical.
- MCP `deepr_consult_experts` can synthesize through local Ollama or an
  explicit plan-quota CLI with live metered fallback disabled. Local is the
  default for both CLI and MCP. API consult synthesis retains explicit
  `provider=openai|anthropic` and `model` inputs for compatibility, but returns
  `METERED_API_DISABLED` before a consult transaction, provider client, or
  request exists. A positive budget and legacy consent flags cannot lift this
  quarantine. The
  returned `deepr-consult-v1` artifact includes a `capacity` block describing
  the selected synthesis backend. Each council perspective's `context` also
  discloses its selected beliefs' grounding assurance: an inline
  `cross-vendor verified` or `same-vendor verified` label on the belief line and
  a `beliefs_verified` count. This is additive disclosure within
  `deepr-consult-v1`; it does not reorder selection or drop unverified beliefs.
  Passing one explicit expert gives a focused
  no-metered single-expert consult; `deepr_query_expert` also supports explicit
  `backend=local|plan` as a read-only compiled-context chat turn with
  `readonly_chat_artifact`, `research_triggered=0`, and no live metered fallback.
  `deepr_query_expert backend=api` and every other standalone
  metered `ExpertChatSession` path fail closed before provider dispatch. Local
  and explicit plan read-only query turns are unchanged. API council synthesis
  is a separate compatibility surface whose final synthesis is also blocked.
  Live metered perspective fallback remains gated when a selected expert has no
  stored context.
  Passing several experts gives a bounded one-shot council with preserved
  dissent. Each expert contributes a deterministic stored-state selection, not
  a model-generated turn, and experts do not exchange messages. One synthesis
  call produces the proposal on local or eligible plan capacity. The generated
  contract exposes zero expert generation calls, zero peer turns, and no belief
  or graph write authority. The dormant API contract retains a complete
  transaction ceiling and a 10 percent synthesis sub-ceiling, but production API
  council synthesis is blocked by the authenticated provider-account authority
  gate. This contract does not authorize dispatch. CLI
  `--output` explicitly saves the full artifact; no separate full artifact path
  is written by default.
  Experimental CLI `deepr expert investigate` is a distinct local-only
  surface. It performs independent free-web research, records one position per
  explicit expert, permits one blinded targeted challenge in `discuss` or
  `deep` mode, optionally revises privately, then checks and synthesizes. Its
  hash-bound plan owns aggregate call, search, page, prompt, output, context,
  elapsed, disk, and `$0` cost ceilings. It supports durable status, inspect,
  pause, resume, and cancel operations with no provider fallback.
  Optional `--learning stage` builds separate source-only verified graph commit
  envelopes after synthesis. Each compiler retains at most five ordered
  candidates before separate verification. Extraction receives the target
  expert domain, and deterministic code requires a positive material relevance
  verdict from the verifier model before commit compilation. It never writes
  expert state automatically and never treats peer or synthesis text as
  evidence. Completed results remain semantically unreviewed. Plan-quota, API,
  MCP, A2A, and automatic-apply investigation surfaces are not shipped.
  CLI and MCP consults append local
  `deepr-consult-trace-v1` records with selected context metadata, checks run,
  capacity posture, and synthesis failure events. Before cancellable local
  discovery or backend dispatch they open a separate append-only
  `deepr-consult-lifecycle-event-v1` journal under the same trace id. It records
  phase heartbeats, process ownership, finite logical-work, elapsed-time, and
  spend ceilings, observed and remaining spend, one-way capacity resolution,
  and typed cancellation or failure state. The current one-shot wrapper does
  not measure aggregate provider token or context totals and omits those
  optional lifecycle counters. It never stores answers or private reasoning.
  CLI and MCP accept a cumulative ceiling for
  cancellable setup and generation plus lifecycle checkpoints. Durable
  lifecycle and final-trace operations run off the event loop and are awaited
  through cancellation; cancellation never selects another backend. Every
  journal or trace lock wait is capped at five seconds. Active-attempt writes
  also use the smaller remaining allowance. Pre-dispatch elapsed or storage
  contention is retryable; post-dispatch failure and any possibly partial write
  are not. Lock and I/O errors are typed separately and neither discloses the
  local path. Canonically settled cancellation cost is checkpointed into the
  lifecycle before its terminal event. CLI `deepr expert consult-traces` is a
  read-only local review surface that emits sanitized
  `deepr-consult-trace-candidates-v1` gap/eval candidates with embedded
  `deepr-consult-quality-eval-case-v1` semantic review packets. The review
  packets are `$0`, read-only, non-verdict artifacts for human or calibrated
  model judging; they cannot commit beliefs. Successful council output is not
  automatically converted into a gap or graph candidate and must not be
  absorbed as factual evidence. `deepr mcp validate-consult`
  emits `deepr-mcp-consult-validation-v1` reports for offline fixtures,
  in-process local or plan validation, and HTTP endpoint validation.
  `deepr capacity validate-fleet` emits `deepr-plan-fleet-validation-v1` as the
  preferred plan-fleet operator health check: it runs selected plan CLI
  transport probes, records quota observations, then validates the no-metered
  consult contract only for transports that succeeded. It fails selected
  backends that are skipped, missing, exhausted, timed out, or return failed
  synthesis status.
  `deepr mcp validate-consult-fleet` emits
  `deepr-mcp-consult-fleet-validation-v1` for bounded concurrent no-metered
  validation across selected plan backends. MCP JSON-object tool results
  include `structuredContent` while retaining text JSON compatibility. A2A
  consult tasks reuse the same consult artifact contract
  instead of creating a parallel answer shape. `deepr a2a validate-host` emits
  `deepr-a2a-host-validation-v1` reports for offline fixtures and remote A2A
  endpoint checks.
- `deepr eval deliberation` emits `deepr-deliberation-eval-v1` from eleven
  built-in frozen-fixture checks at `$0`. It checks round-one independence,
  lineage, targeted-question cardinality, dissent and original-position
  preservation, typed stops, provider-call ceilings, proposal-only authority,
  the default evidence-seeking skeptic, inert adversarial text, and the no-write
  and no-fallback boundaries. It makes no semantic verdict and reports semantic
  review as `unreviewed`. This evaluator does not enable a generic deliberation
  runtime. The separate experimental local CLI investigation has its own
  bounded contract; remote multi-expert CLI, MCP, and A2A chat remains gated.
- `deepr eval conversation` emits `deepr-conversation-eval-v1` from twelve
  built-in frozen-fixture checks at `$0`. The five conversation contracts and
  evaluator report cover protocol-neutral identity, optimistic concurrency,
  idempotent replay, typed lifecycle state, bounded frozen context, finite
  retention, content-free audit events, owner isolation, local-only capacity,
  and proposal-only advice. The protocol-neutral SQLite store and injected
  executor service are implemented as an internal core with durable leases,
  conservative ambiguous-attempt accounting, restart recovery, bounded exact
  replay, finite content retention, and append-only content-free events. Its
  repeated-one-shot comparison is structural; no MCP multi-turn service or
  semantic superiority claim is enabled.
- `deepr expert self-model` emits a read-only `deepr-expert-self-model-v1`
  record with expert capabilities, limits, goals, calibration, learning
  strategy, continuity, blockers, risks, and a bounded current-focus packet.
  It is a derived view and does not mutate expert state. Consult perspective
  context includes this bounded self-model focus metadata when the expert
  profile is available. Sync learning loop records expose it under
  `run_context.self_model`, and sync capacity wait/block payloads expose the
  same compact block as read-only scheduler context.
- `deepr expert next` emits `deepr-expert-next-v1`, a `$0`, read-only plan of
  at most three actions derived from claims, freshness, gaps, contradictions,
  and durable loop outcomes. Its stage is operational navigation, not a
  semantic maturity score, and it cannot change policy or run the commands it
  recommends.
- `deepr expert memory-card` emits or writes a generated
  `deepr-expert-memory-card-v1` / `EXPERT.md` orientation view over profile,
  manifest, belief events, and self-model state. It includes identity policy,
  current stance, explicitly tagged theories and insights, self-research agenda,
  what would change the expert's mind, agency scope, calibration, goals,
  beliefs, gaps, contradictions, collaboration guidance, and update policy. It
  is `$0`, derived, preview-first, and never canonical memory.
- Local semantic recall over beliefs, concepts, and original ideas emits
  `candidate_only` routing metadata only. Original-idea candidates are labeled
  as `perspective_state`, include the non-factual promotion policy, and do not
  imply external verification, support, contradiction, deduplication, or graph
  writes. Belief recall can use a persisted local vector index when a caller
  supplies an already-gated query embedding; stale claim vectors are ignored,
  and embedding generation is not automatic. Claim-verification decisions can
  carry these hits in a `recall_context` packet for verifier routing only; the
  packet is read-only and does not affect commit readiness. `deepr expert
  semantic-recall NAME QUERY` exposes the same `candidate_only` boundary to
  operators at `$0`, and MCP `deepr_semantic_recall` exposes the same read-only
  surface to host agents with host-facing payload sanitization. Indexed vector
  recall requires a caller-supplied `--query-embedding` and `--embedding-model`
  on CLI, an explicit `--local-embedding-model` for a local Ollama `$0` query
  embedding on CLI, or `query_embedding` and `embedding_model` over MCP.
  `deepr expert refresh-semantic-recall NAME --embedding-model MODEL
  --embeddings-json PATH` refreshes missing or stale belief vectors from
  precomputed embeddings; it never calls an embedding provider and keeps the
  declared upstream estimate separate from Deepr spend. `deepr expert
  refresh-semantic-recall NAME --local-embedding-model MODEL` computes those
  vectors through a local Ollama embedding model at `$0` with no metered
  fallback. `deepr expert sync --compile-claims --recall-embedding-model MODEL`
  embeds ready claim statements through the same local `$0` embedder so
  verifier recall context can use the indexed belief vectors, degrading to
  lexical routing instead of blocking verification when the local embedder
  fails. `deepr eval recall-libraries` emits a read-only
  `deepr-recall-library-inventory-v1` inventory so operators can see which
  accumulated case libraries have enough labels for route-evidence evals, and
  `deepr eval recall-libraries --validation-plan --local-embedding-model MODEL`
  emits `deepr-recall-library-validation-plan-v1` command argv for ready
  libraries without executing retrieval or changing routing.
  `deepr eval recall NAME` can rerun accumulated operator-labeled recall case
  libraries and emits `deepr-recall-eval-report-v2` with hit@k, MRR,
  precision@k, recall@k, MAP@k, NDCG@k, and deterministic paired bootstrap
  intervals. Explicit vector preference needs at least 30 paired cases,
  complete current vectors, required point-estimate wins, and 95 percent
  interval lower bounds above zero. Sync recomputes case metrics, route
  summaries, paired intervals, preference, and the live belief/vector state
  digest before accepting eligible evidence. The source-pack recall path checks
  the digest again at use time and requires an exact evaluated top-k, expert
  domain, and minimum-score match, falling back lexically after any drift. The report
  remains routing evidence only: default sync routing is
  lexical-first unless the operator supplies a vetted report with
  `--recall-preference-report`. All of these remain explicit operator choices,
  and recall stays `candidate_only` routing in every mode.
- `deepr expert monitor` emits a read-only `deepr-metacognitive-monitor-v1`
  artifact with review-required proposals derived from self-model risks, failed
  loop runs, capacity waits, and sanitized consult trace candidates. It does
  not mutate goals, strategy, prompts, tools, skills, gaps, or eval suites.
- `deepr expert promote-monitor` emits `deepr-metacognitive-promotion-v1`
  preview or apply results. It previews by default and requires `--apply` before
  promoting a reviewed gap/eval proposal into the metacognition gap backlog or
  a local eval-case artifact.
- `deepr expert review-consult-quality` emits and can write
  `deepr-consult-quality-review-v1` artifacts. The semantic scores come from a
  human or calibrated-model judge; Deepr validates score shape, known labels,
  acceptance gates, and write boundaries. Accepted reviews can promote only gap
  or eval artifacts, never beliefs.
- `deepr expert judge-consult-quality NAME TRACE_ID --local-judge-model MODEL`
  runs consult-quality review with an explicit local Ollama judge at `$0`.
  `--plan BACKEND` with optional `--plan-model MODEL` runs the same path through
  an explicit plan-quota CLI. The judge prompt uses the local trace answer at
  command time, validates returned scores and labels against the review rubric,
  and stores only the review artifact plus calibrated judge metadata. Plan
  judges consume subscription quota, write `$0` Deepr cost metadata through the
  plan-quota path, and do not silently fall back to metered capacity. The
  premium `--api-provider` implementation is gated under Visible Or Planned
  Only. The command does not write beliefs, expose trace paths, or store the raw
  judge response.
- `deepr expert consult-quality-trends NAME` emits
  `deepr-consult-quality-trend-v1`, a `$0` read-only trend report over reviewed
  consult-quality artifacts. It summarizes score dimensions, review statuses,
  and deterministic consult prompt regression candidates selected from
  reviewer scores and review status only; it does not judge answer meaning,
  write beliefs, or expose local artifact paths.
- `deepr eval hallucination-risks` emits
  `deepr-hallucination-risk-report-v1`, a `$0` read-only advisory report over
  consult traces, reviewed consult-quality artifacts, optional expert handoff
  artifacts, and optional source-pack manifest artifacts. It routes observed
  unsupported-claim, citation/provenance, temporal, overconfidence,
  context-loss, grounding-assurance, handoff-contestation, and high-stakes
  review signals into regression selection or review queues, and records
  remaining coverage gaps. The labels inform only; they do not block answers,
  write beliefs, or claim semantic truth from deterministic rules.
  False-premise compliance, template-order sensitivity, and long-context
  middle-loss are available as consult-quality semantic review labels only
  after a human or calibrated-model judge marks them. Consult traces with
  selected middle context create review-only middle-context candidates, and
  consult-quality review signals can produce read-only prompt-regression
  candidates for prompt-variant selection. Consult traces preserve
  selected-order context-position metadata, but the report does not claim
  middle-context-loss detection from position alone.
- Local Ollama expert maintenance, local evals, local context evals, local
  red-team attack-success-rate metrics including MCP read-path canaries and
  saved trend artifacts, and scored local admission. `deepr eval
  grounding-correctness` is a `$0` local eval that scores whether a SUPPORTED
  grounding verdict is actually correct over a curated golden set of labeled
  entailment triples (`--set baseline|hard|all`), emitting
  `deepr-grounding-correctness-v1`; the report discloses that agreement on a
  bounded set is not proof of world-truth.
- `deepr route explain "<query>"` is a `$0`, no-model routing view: which experts
  a consult would fan out to (a deterministic keyword-overlap selection router,
  never a quality verdict) plus the non-probing next-run capacity outlook, as
  `deepr-route-explanation-v1`.
- Explicit plan-quota CLI execution for expert maintenance and bootstrap:
  `deepr expert sync --plan <id>`, `deepr expert sync-all --plan <id>`,
  `deepr expert route-gaps --execute --plan <id>`,
  `deepr expert absorb --plan <id>`, topic learning via
  `deepr expert learn --plan <id>`, the explicit
  `deepr expert learn-web --plan <id>` alias, and
  `deepr capacity probe-plan <id>` run through deterministic auth-mode and
  no-surprise-bills guards. Claude Code is currently executable and can become
  auto-routable only after a trusted quota observation. Every dispatch also
  requires a fresh provider response proving paid extra usage is disabled, uses
  safe mode with empty tool and MCP surfaces and no persistence, pins the
  included `sonnet` alias, and uses no API credential. Codex, OpenCode, Kiro,
  Grok Build, and Antigravity
  are visible/read-only because
  Deepr cannot yet prove their native-tool confinement, stored provider
  provenance, prepaid overage posture, or transcript side-effect confinement.
  GitHub Copilot is visible/read-only
  because it is metered at the margin and lacks deterministic estimation,
  reservation, usage settlement, and canonical cost-ledger support.
- Quota metadata refresh:
  `deepr capacity refresh-quota codex` reads local Codex session `rate_limits`
  metadata, and `deepr capacity refresh-quota claude` reads Claude Code OAuth
  usage metadata when the current user has Claude Code configured.
  `deepr capacity refresh-quota grok` reads the Grok CLI auth file, calls the
  Grok billing metadata endpoint, and records a monthly quota window when
  available. These refreshes record conservative quota-ledger events without
  running a model call or storing credential material.
- Hosted MCP deployment recipes, including the local container, Azure Container
  Apps template, AWS ECS Fargate template, GCP Cloud Run template, and
  Cloudflare Worker edge ingress recipe.
- Research-processing compiler artifacts through source-pack manifests, source
  notes, semantic claim extraction, claim verification, graph commit envelopes,
  and graph commit apply results are experimental but schema-versioned.
  `--compile-claims` writes claim extraction, claim-verification,
  graph-commit envelope, and graph-commit apply sidecars while bypassing the
  legacy absorber for that topic. `--stage-compiled-claims` preserves the
  no-write compiler sidecar path. `--apply-compiled-claims` is accepted as a
  compatibility alias for the default compiled apply behavior.
  Claim-verification envelopes record verifier
  decisions, optional candidate-to-candidate typed edge decisions with
  structured temporal qualifiers, and
  `candidate_only` recall
  context packets; graph commit envelopes plan
  idempotent writes without mutating state. `deepr-graph-commit-envelope-v1`
  is belief-only; `deepr-graph-commit-envelope-v2` adds verifier-gated
  `promote_gap` operations for the metacognition gap backlog;
  `deepr-graph-commit-envelope-v3` adds verifier-gated
  `promote_exploration_agenda` operations for the metacognition exploration
  agenda backlog; `deepr-graph-commit-envelope-v4` adds verifier-gated
  `promote_hypothesis` operations for the metacognition hypothesis backlog;
  `deepr-graph-commit-envelope-v5` adds verifier-gated `promote_concept`
  operations for the metacognition concept backlog;
  `deepr-graph-commit-envelope-v6` adds verifier-gated `promote_stance`
  operations for the metacognition stance backlog; and
  `deepr-graph-commit-envelope-v7` adds verifier-gated
  `promote_original_idea` operations for the metacognition original-idea
  backlog. `deepr-graph-commit-envelope-v8` adds structured temporal
  qualifiers to typed edge operations.
  `deepr expert apply-graph-commit NAME ENVELOPE --yes` is the explicit write
  boundary for verified factual add-belief operations, typed-edge operations,
  typed-edge temporal qualifiers,
  verified gap promotions, verified exploration agenda promotions, and verified
  hypothesis, concept, stance, and original-idea promotions.

## Visible Or Planned Only

- OpenRouter has seven preview-only exact model slugs across OpenAI,
  Anthropic, Google, xAI, Qwen, MoonshotAI, and DeepSeek. Use
  `deepr research --provider openrouter --model qwen/qwen3.8-flash --preview`
  for a write-free bounded request envelope. These entries are excluded from
  automatic routing, expert routing, and eval targets. Omitting `--preview`
  fails with `research_provider_preview_only` before reservation or provider
  construction. `deepr providers openrouter-check` uses bounded public metadata
  and no key to verify one selected endpoint metadata tag, reject additional
  non-tier variants matched by a base tag, and bound reachable text-inference
  price classes, required parameters, and context limits for each route. It
  proposes response caching off, router metadata on, and forbids explicit
  prompt-cache controls, fallbacks, service tiers, media, plugins, presets,
  server tools, and background execution. Preview
  estimates reserve a full-input cache write as an additional maximum charge.
  `deepr providers openrouter-key-check` accepts a credential through a hidden
  prompt by default. Explicit `--from-env` uses the quarantined process copy
  when available or parses only `OPENROUTER_API_KEY` from the bounded
  checkout-local `.env` without exporting it. It returns a sanitized limit
  observation with zero inference requests. Official nullable limit and reset
  fields remain visible as `null` and produce specific ineligibility reasons
  instead of a malformed-response error or a false `$0.00` limit. It never
  reads the local source without that flag, unquarantines or exports the key,
  or passes it to a child. Both checks state that dispatch remains
  unauthorized because account-level BYOK and plugin controls, endpoint-tag
  response proof, complete usage settlement, parent settlement, and final
  billing reconciliation are not complete. No OpenRouter inference client is
  built.
  See [openrouter-metered-gateway.md](design/openrouter-metered-gateway.md).
- Attended OpenAI report absorption through `deepr expert absorb --api` has a
  complete wallet, job reservation, exact-client, dispatch, and settlement
  transaction, but no production provider account-control verifier ships in
  v2.49. It therefore fails before provider construction even after
  `deepr budget credits add`, typed amount confirmation, and explicit per-call
  consent. Reclassify it as experimental only after authenticated evidence can
  prove prepaid-no-overage or a provider hard stop for the active credential.
  The local wallet is ignored by MCP and refused by scheduled or loop execution.
- `deepr eval local` retains `--judge-cli`, `--judge-command`, and
  `--allow-cli-judge` for compatibility, but every CLI judge request exits
  before process creation. Deepr cannot prove the external CLI's billing source,
  overage posture, or total cost. Use a local Ollama judge.
- `DEEPR_SEARXNG_URL` is configuration-readable and visible in diagnostics, but
  SearXNG search dispatch is blocked because Deepr cannot prove that every
  configured upstream engine has zero marginal cost. Explicit URL retrieval and
  the bounded direct DuckDuckGo path remain available.
- Hosted file upload, file search, and vector-store creation or attachment fail
  before provider work with `research_file_storage_unbounded`. Existing provider
  vector stores can still be listed, inspected, and explicitly deleted. Re-enable
  creation and research attachment only when upload, indexing, retention,
  retrieval, and cleanup costs share the same reservation.
- Metered auto-batch, multi-phase campaign, dream-team, prepared campaign,
  continuation, and autonomous multi-round execution fail before paid work with
  `research_parent_budget_unavailable`. Routing and plan previews remain
  available. Re-enable only after every nested call belongs to one durable
  parent reservation with exact per-call settlement and cancellation handling.
- Automatic cross-provider metered fallback is disabled. A definite or
  ambiguous provider failure closes the current reservation according to its
  durable state and does not spend through another provider. Re-enable only
  when each attempt owns a separate reservation and the user approves the full
  retry envelope.
- Legacy metered `deepr check`, `deepr make docs`, `deepr make strategy`, and
  `deepr agentic research` fail before provider construction. MCP sampling also
  never falls through from host capacity to Deepr-owned provider capacity.
  Re-enable these only after their calls use durable reservation, bounded
  output, canonical settlement, and one parent ceiling where multiple calls are
  possible.
- Standalone metered expert chat is hard-disabled with no runtime or
  environment override. Browser, CLI, MCP API, and
  direct API chat fail before provider work with
  `metered_expert_chat_accounting_unavailable`. Re-enable only after one
  provider-enforceable maximum charge covers serialized input, output,
  reasoning, every tool loop, streaming, research, compaction, follow-up,
  synthesis, cache, embedding, vector, storage, retry, redirect, fallback, and
  metered-skill call under one parent reservation. The acceptance gate also
  requires a Deepr-owned attested client, official endpoint, exact model,
  authenticated account and billing scope, provider hard limit or overage-off
  proof, conservative identity mismatch handling, cancellation settlement,
  canonical-ledger idempotency, concurrency, and ledger-failure regressions.
  Local and explicit plan read-only query is shipped and unaffected.
- Unsafe metered expert lifecycle surfaces also fail closed:
  nonlocal `expert make` and `--learn`, API curriculum `expert plan`,
  provider-backed `expert refresh` and `--synthesize`, `expert resume`, normal
  metered `expert reflect` and MCP `deepr_reflect`, API `fill-gaps` including
  consensus and deep modes, explicit API sync and sync-all, paid portraits,
  API consult-quality judging, live provider benchmarks, and paid
  `deepr eval calibrate --corpus`. Re-enable each only after it uses the
  shared durable per-call and parent-run budget transaction, including storage
  and tool pricing. Local, scheduled, dry-run, history-only, and explicit
  plan-quota expert paths where available, plus `$0`
  `deepr eval calibrate --from`, remain
  shipped.
- Automatic routing to plan-quota CLIs remains gated until Deepr has trusted
  live remaining-quota signals for the candidate backend. `expert sync-all` and
  scheduled `route-gaps --execute` consume admitted, quota-observed plan
  selections from that gate. Claude is the only current safety-eligible
  auto-routable candidate and every Claude dispatch also requires a fresh
  provider observation proving paid extra usage is disabled. Codex, OpenCode,
  Kiro, Grok, Antigravity, and Copilot are execution-blocked. Explicit `--plan`
  selects an adapter but never bypasses auth, tool, side-effect, live-overage,
  marginal-cost, or process-safety gates.
- Multi-account capacity pools are planned after a single-account mechanism is
  complete.
- One experimental host-specific reference now ships:
  `deepr mcp host-profile openclaw` deterministically emits a closed,
  config-only `deepr-mcp-host-profile-v1` artifact for OpenClaw stable
  `v2026.7.1-2`. The profile pins the signed tag object, target commit, package
  version, exact configuration source blobs, local stdio transport, the ten
  policy-filtered read-only tools, explicit contained roots, and zero primary
  and legacy spend ceilings. It remains `reference`, not fixture-validated or
  live-validated. It does not install a host, edit host configuration, inspect
  credentials, open a network route, or prove OpenClaw parser, handshake,
  discovery, tool-call, sandbox, or Agent Plugins behavior.
- Experimental investigation projection contracts now exist as local `$0`
  builders over one run: status, event cursor pages, and artifact metadata
  pages, plus preview-only follow-up and fork lineage. They cannot mutate a
  run, return artifact bodies, include local paths, or imply semantic
  acceptance. MCP observer tools, remote start, and control remain planned.
- Additional host profiles, remote MCP routes, steering, and external computer
  control remain planned. The next local fixtures target DeepSeek Harness
  `dsh-v0.1.1-rc.2`, and Grok Build 1.0.6. OpenClaw Agent Plugins are stable in
  upstream `v2026.8.2`, but Deepr has not fixture-validated that host. The
  packaged server now exposes its exact ten policy-filtered read-only tools to
  ordinary MCP discovery; this is package correctness, not an OpenClaw support
  claim. Manual Grok Bot installation is a valid future host path, but no
  public Bot lifecycle API
  is claimed. NemoClaw `v0.0.113` with its pinned OpenShell 0.0.106 remains a
  reference-only remote profile. Every path requires independently validated
  host capability evidence and cannot widen the shipped local read-only package
  boundary. See
  [external-harness-investigation-bridge.md](design/external-harness-investigation-bridge.md).
- OKF 0.2 export and offline form validation ship under
  `deepr-okf-profile-v2`. Import remains permissive, untrusted, and
  verification-gated. Runtime computation execution and attestation do not
  ship.
- Live hosted-agent registration smoke against a real third-party platform is
  still open.
- A long-running A2A conversation mapping is not shipped. MCP query and consult
  remain intentionally one-shot; callers that need continuation use the
  separate durable local MCP conversation tools. See
  [remote-expert-conversations.md](design/remote-expert-conversations.md).
- A long-running A2A service is planned only after the current in-memory custom
  substrate is migrated or versioned against A2A 1.0, tasks and contexts survive
  restart, authorization is caller-scoped on every request, and a separate A2A
  client passes live conformance-oriented validation.
- OAuth/OIDC, team RBAC, and workspace isolation are planned team features.
- Hosted-by-Deepr SaaS, SLAs, and enterprise SSO are non-goals for this project
  shape.

## Export Guarantees

If development stops, users keep these portable artifacts:

- Markdown research reports and their adjacent metadata under the configured
  reports root.
- Expert profiles, belief stores, event logs, edge stores, gap manifests, and
  loop-run records under the configured data root.
- An expert's own account of itself (`self.json`), what it noticed in what it
  read (`noticed/`), the view it currently holds and every view it has held
  (`hold/`), what changed it (`became/`), what it is chasing (`attend/`), and
  what has been put to it (`met/`). All plain JSON and Markdown under the
  expert's directory, readable without Deepr.
- Generated expert memory cards (`EXPERT.md`) when written. These are derived
  orientation views over canonical state, including labeled original-idea
  perspective state, and can be regenerated.
- Deepr OKF-profile bundles from `deepr expert export-okf`, including
  `index.md`, `log.md`, concept pages, citations, gaps, and contested claims.
  They are portable Markdown/YAML derived views. v2.50 ships a mechanical OKF
  0.2 form check; it does not claim full specification conformance.
- Published JSON Schemas under `docs/schemas/` for handoff, expert self-models,
  metacognitive monitor proposals, reviewed monitor promotion, loop status, OKF
  profile mapping, expert memory cards, compiler envelopes, A2A task envelopes,
  A2A host validation, remote audit events, MCP registration manifests,
  capacity guidance, sync capacity gates, scheduled maintenance payloads, and
  the shared CLI operation-result envelope.
- Cost ledger JSONL and remote MCP audit JSONL records.
- Scoped MCP key metadata, excluding plaintext secrets. Created key secrets are
  shown once and cannot be recovered from stored hashes.

Generated digests, memory cards, OKF bundles, reports, and registration
manifests are derived views or handoff artifacts. The structured store remains
authoritative unless a specific command explicitly says it is importing external
source text through the verified absorb path.

## Compatibility Rules

- Published v1 schemas are additive within the same schema version by default.
  A registry entry labeled as closed authority may add ignored descriptive
  extensions only; any authority change requires a new schema version.
- Removing a required field, changing required semantics, or changing the kind
  of a record requires a new schema file and schema version.
- Stable commands should keep existing flags working or document a migration in
  `docs/CHANGELOG.md`.
- Experimental commands may change, but changes should preserve data safety:
  no silent spend, no silent mutation, and no secret disclosure.
- Planned capacity must stay labeled as planned or visible/read-only until the
  adapter, quota probe, budget guard, and tests are present.

## Operator Responsibilities

- Provider API keys are user-owned credentials. Deepr's metered transaction
  substrate enforces budget ceilings, but production dispatch is currently
  blocked because local assertions cannot prove account-side controls. Use a
  dedicated provider project, the smallest available account hard limit or
  disabled paid overage, monitored provider alerts, and regular billing-export
  reconciliation. Deepr imports bounded normalized statements offline
  and freezes on non-clean applied evidence. It does not yet ship an
  authenticated provider verifier or current credential-identity resolver and
  cannot govern another application using the same credential.
- Local Ollama capacity is only as available as the local machine and admitted
  model evidence.
- Remote MCP endpoints must use HTTPS outside loopback, scoped keys per agent,
  budget ceilings, deterministic estimates for metered tools, rate limits, and
  concurrency caps, plus audit review before widening key mode.
- An expert allowlist is a hard data and execution boundary. It denies global
  expert and skill discovery and generic research that has no expert target;
  expert-targeted calls must name only allowlisted experts. Key creation,
  authentication timestamps, and revocation are serialized across processes.
- Edge ingress recipes must stay stateless pass-through guards. Scoped-key
  enforcement, budgets, rate limits, audit logs, and provider credentials stay
  on the Deepr origin.
- Cloud templates are deployment artifacts. Creating cloud resources can incur
  infrastructure cost even when Deepr itself makes no provider API calls.
