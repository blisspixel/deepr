# Supported Surface

Status: v2.32.0 current main, 2026-07-08. This document defines what users and host
agents can rely on today, what is experimental, what is planned only, and what
data remains portable if development stops.

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

- Core research commands: `deepr research`, `deepr check`, `deepr learn`.
- Budget ceilings, cost estimates, and the canonical append-only cost ledger.
- Provider routing and fallback when the user supplies provider keys and a
  budget ceiling.
- Local report storage under the configured reports root.
- Expert creation, chat, import/export, and profile storage.
- Portable data root through `DEEPR_DATA_DIR`, with expert and research state
  kept under that root unless a more specific path is configured.
- CLI output modes: `--json`, `--quiet`, `--verbose`, and trace flags where
  documented. The shared `OperationResult` JSON envelope is versioned as
  `deepr-cli-operation-result-v1`.
- The published schema registry under `docs/schemas/`, with additive
  compatibility inside each v1 schema.

## Experimental But Usable

- Web dashboard and dashboard APIs.
- Agentic expert chat, slash commands, councils, task planning, and approval
  flows.
- Expert skills and first-party instruments.
- MCP stdio server and MCP HTTP serve mode.
- Scoped MCP keys, per-key budgets, per-key rate limits, HTTP concurrency caps,
  HTTP smoke checks, registration manifests, and remote-call audit review.
- `deepr_expert_handoff`, `deepr_expert_loop_status`, and adjacent versioned
  handoff contracts. The MCP loop-status tool, the CLI JSON loop-status command,
  and `/api/experts/{name}/loop-status` share the `deepr-loop-status-v1` rollup
  contract. MCP handoff and loop-status outputs fail closed if the published
  schema version, kind, or required envelope fields drift before dispatch.
- A2A task envelopes for create, status, cancel, and result-bearing completed
  tasks. These use `deepr-a2a-task-v1` and fail closed if schema version, kind,
  lifecycle state, cost, timestamps, or metadata drift before dispatch. The
  Agent Card is available at `/.well-known/agent-card.json` with
  `/.well-known/agent.json` kept as a compatibility alias. It advertises
  `deepr_consult_experts`; completed consult tasks attach the full
  `deepr-consult-v1` payload as an A2A task artifact. A2A consult defaults to
  local no-metered synthesis and requires explicit
  `allow_metered_api=true` plus a positive budget before API synthesis.
- Scheduled expert maintenance JSON contracts for sync capacity gates, gap-fill
  waits, reflection waits, health-check action plans, and health-check archive
  confirmations. These are experimental but schema-versioned and additive.
- Durable `ExpertLoopRun` records.
- Fleet self-maintenance: `deepr fleet status` (read-only `$0` roster-health
  rollup, `deepr-fleet-status-v1`, non-zero exit on a failed latest run),
  `deepr expert sync-all` (one capacity-aware roster pass, `deepr-library-sync-v1`
  roll-up, overlap-locked, per-expert budgets, skip-not-fail, explicit
  non-metered `--plan <id>` override, and admitted quota-observed plan dispatch
  when the waterfall selects one), and
  `deepr fleet install-schedule` (emits host scheduler recipes; never
  auto-installs). The off-box heartbeat (`DEEPR_HEARTBEAT_URL`) is opt-in and
  best-effort.
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
- OKF export and absorb paths. OKF export is a derived view; OKF absorb is an
  ingestion source that still passes through verified extraction.
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
  explicit plan-quota CLI with live metered fallback disabled. API consult
  synthesis accepts explicit `provider=openai|anthropic` and `model` values;
  Anthropic supports `claude-sonnet-5` through the native Messages API and
  records cache-write/read token buckets when the provider reports them. The
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
  `deepr_query_expert backend=api` supports OpenAI by default and explicit
  `provider=anthropic` for non-agentic metered API turns. The Anthropic path
  uses the native Messages API, defaults to `claude-sonnet-5`, disables tools,
  supports non-agentic text streaming, rejects `agentic=true`, and records
  Anthropic usage buckets through the chat ledger.
  Passing several experts gives a bounded council with preserved dissent. CLI
  and MCP consults append local
  `deepr-consult-trace-v1` records with selected context metadata, checks run,
  capacity posture, and synthesis failure events. CLI `deepr expert
  consult-traces` is a read-only local review surface that emits sanitized
  `deepr-consult-trace-candidates-v1` gap/eval candidates with embedded
  `deepr-consult-quality-eval-case-v1` semantic review packets. The review
  packets are `$0`, read-only, non-verdict artifacts for human or calibrated
  model judging; they cannot commit beliefs. `deepr mcp validate-consult`
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
- `deepr expert self-model` emits a read-only `deepr-expert-self-model-v1`
  record with expert capabilities, limits, goals, calibration, learning
  strategy, continuity, blockers, risks, and a bounded current-focus packet.
  It is a derived view and does not mutate expert state. Consult perspective
  context includes this bounded self-model focus metadata when the expert
  profile is available. Sync learning loop records expose it under
  `run_context.self_model`, and sync capacity wait/block payloads expose the
  same compact block as read-only scheduler context.
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
  fails. `deepr eval recall NAME` can rerun accumulated operator-labeled recall
  case libraries and emits an additive `deepr-recall-operator-validation-v1`
  block describing whether the saved report is ready for explicit sync
  preference use. The block is still routing evidence only: default sync routing
  remains lexical-first unless the operator supplies a vetted report with
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
  an explicit plan-quota CLI. `--api-provider PROVIDER --api-model MODEL
  --budget USD --confirm-metered-cost` runs a premium metered API judge behind
  preflight reservation and ledger settlement. The judge prompt uses the local
  trace answer at command time, validates the returned scores and labels
  against the review rubric, and stores only the review artifact plus calibrated
  judge metadata. Plan judges consume subscription quota, write `$0` Deepr cost
  metadata through the plan-quota path, and do not silently fall back to metered
  capacity. API judges write metered cost metadata through the canonical cost
  ledger. The command does not write beliefs, expose trace paths, or store the
  raw judge response.
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
  no-surprise-bills guards. Codex, Claude Code, and OpenCode are eligible for
  operator admission; Kiro, Grok Build, Antigravity, and GitHub Copilot remain
  explicit-only.
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

- Automatic routing to plan-quota CLIs remains gated until Deepr has trusted
  live remaining-quota signals for the candidate backend. `expert sync-all` and
  scheduled `route-gaps --execute` consume admitted, quota-observed plan
  selections from that gate, but Codex and Claude remain the clean
  auto-routable candidates; Grok, Antigravity, and other sources remain planned
  or explicit-only. Explicit `--plan` is still the works-now path and automatic
  plan dispatch must stay conservative.
- Multi-account capacity pools are planned after a single-account mechanism is
  complete.
- Live hosted-agent registration smoke against a real third-party platform is
  still open.
- OAuth/OIDC, team RBAC, and workspace isolation are planned team features.
- Hosted-by-Deepr SaaS, SLAs, and enterprise SSO are non-goals for this project
  shape.

## Export Guarantees

If development stops, users keep these portable artifacts:

- Markdown research reports and their adjacent metadata under the configured
  reports root.
- Expert profiles, belief stores, event logs, edge stores, gap manifests, and
  loop-run records under the configured data root.
- Generated expert memory cards (`EXPERT.md`) when written. These are derived
  orientation views over canonical state, including labeled original-idea
  perspective state, and can be regenerated.
- OKF bundles from `deepr expert export-okf`, including `index.md`,
  `log.md`, concept pages, citations, gaps, and contested claims.
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

- Published v1 schemas are additive within the same schema version.
- Removing a required field, changing required semantics, or changing the kind
  of a record requires a new schema file and schema version.
- Stable commands should keep existing flags working or document a migration in
  `docs/CHANGELOG.md`.
- Experimental commands may change, but changes should preserve data safety:
  no silent spend, no silent mutation, and no secret disclosure.
- Planned capacity must stay labeled as planned or visible/read-only until the
  adapter, quota probe, budget guard, and tests are present.

## Operator Responsibilities

- Provider API keys are user-owned credentials. Deepr enforces budget ceilings,
  but users choose when to provide keys and when to allow paid tools.
- Local Ollama capacity is only as available as the local machine and admitted
  model evidence.
- Remote MCP endpoints must use HTTPS outside loopback, scoped keys per agent,
  budget ceilings, deterministic estimates for metered tools, rate limits, and
  concurrency caps, plus audit review before widening key mode.
- Edge ingress recipes must stay stateless pass-through guards. Scoped-key
  enforcement, budgets, rate limits, audit logs, and provider credentials stay
  on the Deepr origin.
- Cloud templates are deployment artifacts. Creating cloud resources can incur
  infrastructure cost even when Deepr itself makes no provider API calls.
