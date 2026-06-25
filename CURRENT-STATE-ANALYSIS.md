# Current State Analysis

Date: 2026-06-25

## Alignment Summary

Deepr is aligned around one active product bet: persistent domain experts that keep verified knowledge current without silent spend. The README sells this as research infrastructure and a consultable knowledge role, not another chat window and not generic RAG. Current main is `v2.22.0`: local Ollama is usable for `$0` expert maintenance; explicit plan-quota execution works for `expert sync --plan <id>`, `expert absorb --plan <id>`, and `capacity probe-plan <id>` behind auth-mode and no-surprise-bills gates; Codex quota metadata refresh works through `capacity refresh-quota codex` without a model call; durable loop status is observable across CLI, MCP, and web surfaces; OKF import/export is a verified interchange path; hosted MCP has scoped keys, per-key budgets, rate limits, concurrency caps, audit records, smoke checks, registration manifests, and deployment recipes; red-team metrics measure prompt-boundary, MCP read-path, tool-spoofing, and memory trust-floor probes at `$0`; expert handoff payloads carry per-claim grounding assurance with verified and cross-vendor verified summary counts.

The latest 2026 external guidance reinforces Deepr's direction: this is agentic harness, context engineering, loop engineering, and harness-first verification work. The useful primitives are durable progress files, tight high-signal context, independent verification, trace/eval loops, typed stop conditions, scoped tools, and explicit spend/security gates. Deepr already has most of the harness substrate: `ExpertLoopRun`, loop-status rollups, context source packs, capacity previews, budget gates, scoped MCP, red-team metrics, and derived handoff contracts. The remaining work is not "more RAG"; it is closing verifier loops and making the scheduled verbs safer and more observable.

`AGENTIC_BALANCE.md` is the governing boundary: deterministic workflow code owns spend, writes, routing gates, durable state, locks, jitter, schemas, and verifier outcomes; model judgment owns meaning such as contradiction, grounding, deduplication, and synthesis.

No clarification is needed before continuing. The next slice is live trusted quota probes, starting with Codex session-log `rate_limits` and Claude Code OAuth `/usage`, because auto-routing to prepaid capacity must be based on observed remaining headroom instead of CLI presence.

## What Works Now

- API-backed research works with budget gates and the append-only cost ledger.
- Local expert creation and maintenance work through `expert make --local`, `expert sync --local`, `expert sync --local --fresh-context`, `expert sync --local --deep-context`, `expert absorb --local`, `eval local`, `eval local-context`, and scored `capacity admit`.
- Capacity visibility is in place through `deepr capacity`, quota observations, normalized backend profiles, eligibility decisions, pure backend selection, and `deepr capacity next`.
- The evidence layer is present through `eval continuity`, `eval calibrate`, `eval red-team`, source-trust floors, event logs, typed edges, lifecycle archival, and model-verdict routing for semantic absorb checks.
- Portable data is in place through `DEEPR_DATA_DIR`, `DEEPR_EXPERTS_PATH`, and `DEEPR_REPORTS_PATH`, with the cost ledger deliberately machine-local.
- Explicit plan-quota CLI execution is in place for maintenance through the lightweight `research_fn` and chat-client seams, with quota and `$0` cost-ledger writes. The quota availability substrate now has a normalized `QuotaSnapshot` contract with binding-window/headroom calculation, and `deepr capacity refresh-quota codex` records Codex local session-log `rate_limits` into `quota_ledger.jsonl` without a model call. Claude, Grok, and Antigravity metadata probes can use the same substrate next. Automatic plan routing remains gated until trustworthy live remaining-quota signals exist.
- Explicit maker-checker grounding is in place for `expert absorb` and `expert sync` through `--check-grounding`, with optional `--checker-plan <id>` for cross-plan checking. It is off by default, dry runs do not check, and metered API checker construction remains future work behind spend-policy gates. Handoff payloads now preserve per-claim `grounding_assurance` and summarize verified and cross-vendor verified claim counts.
- Fleet loop primitives are in place: `fleet status`, `expert sync-all`, `fleet install-schedule`, content-hash pre-sync change detection, per-verb locks, startup jitter, and durable loop-run records.

## Recent Progress

`deepr expert absorb` and `deepr expert sync` now have explicit maker-checker
grounding flags. `--check-grounding` injects the existing fresh-context
entailment checker into the absorb path, and `--checker-plan <id>` lets the
operator run the checker on a different plan CLI for `cross_vendor` assurance.
Without `--checker-plan`, local and plan-backed runs get
`same_vendor_fresh_context` assurance. The checker stays off by default, dry
runs do not call it, and metered API checking is not automatic.

The sync command file was split cleanly before adding flags:
`expert_sync_support.py` now owns capacity waits, loop records, context
builders, and overlap locking, keeping the command module under the file-size
ratchet while preserving behavior.

The first capacity QOL slice is now in place. `deepr capacity next` accepts
concrete job context (`--expert`, `--report-id`, `--context-mode`, and
`--scheduled`) and returns deterministic wait/fallback guidance without running
research or spending.

`deepr expert sync --scheduled` now consumes the same guidance before launching a
due subscription sync. If a scheduled run would otherwise fall through to
metered API, or if fresh/deep context needs local capacity, the command returns a
wait payload with next actions instead of spending. Explicit `--api` remains the
operator override.

`deepr expert route-gaps --execute --scheduled` now returns pending routes and a
wait state instead of starting metered gap-fill research from recurring
schedulers. This does not pretend gap-fill has a cheap backend yet; it exposes
the pending work and waits.

`deepr expert reflect --scheduled` now validates the report lookup and returns a
structured wait before the reflection evaluator or follow-up research can run.
This keeps recurring reflection follow-up jobs honest while cheap evaluator
capacity is still planned.

`deepr expert health-check --scheduled` now emits a scheduler action plan for
the audit's recommended actions. Metered recommendations wait for capacity,
confirm-gated local writes wait for confirmation, and `--archive-stale
--scheduled` will not mutate unless `--yes` is explicit.

Scheduled expert wait and action-plan surfaces now append durable
`ExpertLoopRun` snapshots and include `loop_run` JSON. This covers sync,
gap-fill route execution, reflection follow-ups, and health-check action plans,
so blocked recurring maintenance is visible through `deepr expert loop-status`
without repeating the job.

The loop-status state is now available to host agents through the
`deepr_expert_loop_status` MCP tool, with optional status and loop-type filters.

Successful `deepr expert sync` runs now append completed or failed
`ExpertLoopRun` snapshots with trigger, budget spent, capacity source, accepted
change count, and next action for failed topics.

Non-dry `deepr expert route-gaps --execute` runs now append gap-fill
`ExpertLoopRun` snapshots too. The record carries trigger, budget spent,
capacity source, accepted-change count, typed failure stops, and concrete next
actions for failed outcomes, deferred specialist routes, or budget exhaustion.

`deepr expert reflect` now appends reflection `ExpertLoopRun` snapshots with
verifier outcome, score, model version, typed verifier-failed stops, and
follow-up absorption metrics when `--execute-followups` runs.

`deepr expert health-check` and confirmed `--archive-stale` runs now append
health-check `ExpertLoopRun` snapshots with verifier outcome, recommended
action state, accepted archival counts, and typed stops for critical reports,
capacity waits, confirmation gates, or no corrective work.

The dashboard API now exposes `/api/experts/{name}/loop-status`, a read-only
rollup over the same durable run records. It returns the latest run, last sync
result, waiting scheduled action, latest failure, status and loop-type counts,
capacity-source counts, spend totals, acceptance metrics, cost per accepted
change, verifier-failure count, and recent run records. The same response now
includes `expert_state` telemetry for freshness, 7-day and 30-day gap velocity,
top open gaps, and contested/open claim counts from structured manifest links
and belief contradiction edges.

The loop completion contract is now enforced at the record layer.
`ExpertLoopRun` rejects completed, failed, or cancelled records without a typed
stop reason, and rejects waiting, completed, failed, or cancelled records when
the stop reason does not match the status.

The loop admission contract is now codified in `LoopAdmissionContract` and
exposed through the dashboard rollup as `admission_contracts`. Sync,
reflection, and health-check are admitted under the four workflow gates;
gap-fill remains supervised until gap-closure verifier evidence is recorded.

`deepr expert export-okf NAME PATH` now starts the OKF interchange track. It
regenerates a Markdown/YAML bundle from structured expert state at `$0`,
including `index.md`, `log.md`, concept pages, citations, typed relations,
gaps, contested claims, and optional `llms.txt`, with marker-based overwrite
protection. The belief/event/edge store remains canonical.

`deepr expert absorb-okf NAME PATH` now closes the OKF interchange loop. It
parses OKF concept Markdown and frontmatter into source text, then sends that
text through `ReportAbsorber` so extraction, grounding, dedup, and contradiction
gates decide what becomes persistent belief state.

The hosted reach track now has its first read-only contract. `deepr_expert_handoff`
and `/api/experts/{name}/handoff` expose `deepr-expert-handoff-v1`: a `$0`
versioned handoff payload with profile summary, manifest counts, bounded
claims/gaps, per-claim grounding assurance, verified-claim counts, dashboard
telemetry, loop-status rollup, OKF interchange hints, and an additive
compatibility contract.

The hosted reach track also has its first scoped-key and remote-audit primitive.
`ScopedMCPKeyStore` persists one-way hashed key records with mode, expert
allowlist, and budget metadata; the HTTP transport enforces mode, confirmation,
and expert scope for `tools/call` before dispatch; `RemoteMCPAuditLog` appends
`deepr-mcp-remote-audit-v1` events with hashed arguments. `deepr mcp keys`
creates, lists, and revokes scoped keys. The scoped HTTP transport now enforces
per-key budget ceilings by summing prior audited `cost_usd`, blocking calls
whose requested budget or fixed estimate exceeds the remaining key budget,
failing closed when a metered remote tool has no deterministic estimate,
injecting remaining budget into budget-aware tools when omitted, and recording
successful response costs back to the audit log. `deepr_expert_validate` is now
advertised as a low-cost MCP tool to match its paid validation call. It also
enforces optional per-key calls-per-minute limits from recent audited calls,
blocks over-limit calls before dispatch, returns retry metadata, and audits the
denial. The HTTP transport now also enforces a global POST concurrency cap,
returning 429 with retry metadata before reading or dispatching excess requests.
`deepr mcp serve --http` now runs the same MCP server over HTTP/SSE on loopback
by default, with reachable binds protected by shared-token or scoped-key
authentication.
`deepr mcp audit list` reviews the local append-only remote-call audit log with
key, tool, outcome, limit, and JSON filters, while `deepr mcp audit summary`
aggregates counts and audited cost by key, tool, and outcome. `deepr mcp
smoke-http` validates local and TLS-proxied endpoints at `$0`, and
`deploy/mcp-http.md` documents the scoped-key plus reverse-proxy deployment
shape. `deploy/mcp-http/` now provides the containerized local service variant
with scoped-key bootstrap, loopback-only host publishing, a mounted Deepr data
directory, and `$0` smoke validation guidance. The first three cloud-provider
templates now live at `deploy/mcp-http/azure-container-apps/`,
`deploy/mcp-http/aws-ecs-fargate/`, and `deploy/mcp-http/gcp-cloud-run/`,
preserving persistent `/data`, HTTPS ingress, scoped-key state, remote-audit
durability, and the same max-concurrency contract across Azure Container Apps,
AWS ECS Fargate, and GCP Cloud Run. The GCP variant stays single-writer by
default while key and audit files live on an object-backed mount.
`deploy/mcp-http/cloudflare-worker/` now adds the edge ingress recipe in front
of an existing HTTPS origin. It proxies only `/mcp` paths, caps request bodies,
forwards scoped-key auth headers, and keeps scoped-key enforcement, budgets,
rate limits, audit logs, and provider keys on the origin side.
`deepr mcp registration-manifest` now emits a token-redacted
`deepr-mcp-registration-manifest-v1` packet with endpoint metadata and optional
smoke results for remote host setup. Live third-party host registration remains
open.

The contract surface is now broader than the handoff payload. `docs/schemas/`
publishes `deepr-expert-handoff-v1`, `deepr-loop-status-v1`, and
`deepr-okf-profile-v1`, `deepr-mcp-remote-audit-v1`, and
`deepr-mcp-registration-manifest-v1`, with `registry.json` and a README
documenting additive compatibility and deprecation rules for downstream agents.
`docs/SUPPORTED_SURFACE.md` now states stable, experimental, visible/read-only,
planned, export, and compatibility guarantees directly.

The MCP allowlist enforcement gap from the panel review is now closed locally.
Contract tests cover every visible registry tool and dispatcher-only tool
across every `ResearchMode`, asserting the declared policy, scoped-key
authorization behavior, and JSON-RPC pre-dispatch block or confirmation gate
stay aligned.

The circuit-breaker/session-budget audit finding is also closed locally.
Expert chat session circuit trips propagate through `CostSafetyManager` as
blocked session reasons; standard research stops before fallback provider calls
when the session circuit is open; and deep research now preserves
session-specific budget or circuit metadata in blocked responses.

The live-validation CLI polish finding is closed locally. Bare `deepr search
"query"` now routes to the query subcommand instead of returning a generic Click
error, and `deepr expert list` labels the name and description fields so roster
entries are easier to scan.

The CLI output-as-contract work has started. The shared `OperationResult`
`--json` envelope now includes `schema_version` and `kind`, is published as
`deepr-cli-operation-result-v1` in the schema registry, and has runtime schema
validation coverage. The recurring scheduler JSON surfaces beyond sync now also
have published schemas: scheduled gap-fill waits, scheduled reflection waits,
health-check action plans, and health-check archive confirmations.
The loop-status contract gap is narrower now: the CLI, MCP, and web loop-status
reads all return the shared `deepr-loop-status-v1` rollup payload instead of
split ad hoc shapes.
Capacity guidance now has its first command-specific JSON contract:
`deepr-capacity-next-v1` covers `deepr capacity next --json` and the
`capacity_next` object embedded by scheduled sync waits.
The outer sync wait/block response is also versioned as
`deepr-sync-capacity-gate-v1`, so a scheduler can validate both the envelope and
the nested guidance object.
The adjacent scheduled maintenance envelopes are now versioned as
`deepr-scheduled-gap-fill-wait-v1`, `deepr-scheduled-reflection-wait-v1`,
`deepr-health-check-action-plan-v1`, and
`deepr-health-check-archive-confirmation-v1`.
The MCP host-facing expert reads now also validate their published envelopes at
runtime: `deepr_expert_handoff` and `deepr_expert_loop_status` fail closed with
`SCHEMA_VALIDATION_FAILED` if required schema/kind/envelope fields drift before
the response leaves Deepr.
The A2A task lifecycle now has the same structural guard. `Task.to_dict()`
emits `deepr-a2a-task-v1`, the schema is published in `docs/schemas/`, and
create/status/cancel task responses fail closed with `SCHEMA_VALIDATION_FAILED`
if schema version, kind, lifecycle state, cost, timestamps, metadata, or
required envelope fields drift.

The indirect prompt-injection prompt-boundary slice is in place. `PromptSanitizer`
now exposes an untrusted-content wrapper that delimits source text as data, not
instructions. Fresh retrieval context, report absorption prompts, first-party
tool findings, local document review previews, campaign context summarization,
completed-research review, company-intelligence reuse, and team-result synthesis
use that boundary before text reaches a model or expert prompt context. This
does not judge truth; belief absorption still relies on extraction, confidence,
contradiction, dedup, and trust-floor gates.

## Active Gap

The next-version edge is harness hardening, not plain retrieval. The dependency
order is:

- Release and repo hygiene: keep `main`, the package version, README badge,
  changelog, tag, and GitHub release in agreement before widening scope.
- Dogfood expert refresh and consultation: validate `deepr capacity`, refresh
  project-relevant experts through `$0` local/fresh-context or explicit
  plan-quota capacity, then consult them on README and ROADMAP.
- Replayable evidence: make source packs content-addressed and memoize
  claim+source+window verification before broader checker escalation.
- Maker-checker completion: metered provider-adapter checker construction with
  spend-policy gates, then bounded second-check escalation before holding
  unsupported claims.
- Local-vs-frontier A/B: evidence that `$0` local experts preserve grounding
  and identify the calibration/coverage cases that deserve targeted metered
  escalation.
- Final Phase 4d primitives: conditional GET before retrieval cost, plus the
  remaining scheduled-verb lock and jitter wiring.
- Brittle-rule cleanup and semantic recall: remaining lexical verdict surfaces
  must route to model judgment when they make semantic claims; local-first
  embedding candidates can improve recall while the epistemic graph still
  decides trust.

Security breadth remains open too: expert-chat harness coverage, ingestion-path
corpora beyond built-in canaries, and broader adaptive MCP extraction probing.
Those stay workflow metrics over observable boundaries, while semantic
acceptance continues to depend on calibrated extraction, grounding,
contradiction, dedup, and trust-floor gates.

## Next Work

Next slice: wire Claude Code OAuth `/usage` into the same `QuotaSnapshot`
contract, then validate the project-expert refresh and consultation path using
free/local capacity or explicit plan-quota capacity only.

## Spend Ledger For This Run

External paid spend: `$0.00`.

Only local filesystem reads, local tests, lint, and git operations are planned. No provider APIs, embeddings, paid evals, or paid research runs will be used.
