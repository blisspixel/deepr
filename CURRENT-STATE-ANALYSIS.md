# Current State Analysis

Date: 2026-06-20

## Alignment Summary

Deepr is aligned around one active product bet: persistent domain experts that can keep verified knowledge current without silent spend. The README sells this as research infrastructure, not another chat window. Current main is now the `v2.17.2` prompt-boundary hardening patch release: local Ollama is usable for `$0` expert maintenance, durable loop status is observable across CLI, MCP, and web surfaces, OKF import/export is a verified interchange path, the hosted MCP foundation is in place, host-facing output contracts fail closed on schema drift, the lockfile includes the `msgpack` security fix, and ingested/tool content prompt boundaries now cover fresh context, report absorption, first-party findings, document review, campaign context, and team synthesis paths. Plan-quota adapters remain explicitly not execution backends until adapters, probes, no-surprise-bills guards, and tests ship. `AGENTIC_BALANCE.md` is the governing boundary: deterministic workflow code owns spend, writes, routing gates, durable state, and verifier outcomes; model judgment owns meaning such as contradiction, grounding, deduplication, and synthesis.

No clarification is needed before continuing. The docs are internally consistent about what works now, what is visible/read-only, and what remains planned.

## What Works Now

- API-backed research works with budget gates and the append-only cost ledger.
- Local expert creation and maintenance work through `expert make --local`, `expert sync --local`, `expert sync --local --fresh-context`, `expert sync --local --deep-context`, `expert absorb --local`, `eval local`, `eval local-context`, and scored `capacity admit`.
- Capacity visibility is in place through `deepr capacity`, quota observations, normalized backend profiles, eligibility decisions, pure backend selection, and `deepr capacity next`.
- The evidence layer is present through `eval continuity`, `eval calibrate`, source-trust floors, event logs, typed edges, lifecycle archival, and model-verdict routing for semantic absorb checks.
- Portable data is in place through `DEEPR_DATA_DIR`, `DEEPR_EXPERTS_PATH`, and `DEEPR_REPORTS_PATH`, with the cost ledger deliberately machine-local.

## Recent Progress

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
claims/gaps, dashboard telemetry, loop-status rollup, OKF interchange hints, and
an additive compatibility contract.

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

The next security gap is adversarial measurement, not another lexical rule.
The prompt boundary now blocks embedded directives from blending into
instruction text, but the agentic red-team suite still needs attack-success
metrics for prompt injection, tool abuse, MCP read extraction, and trust-floor
bypass attempts.

That gap matters because it proves the boundary under hostile inputs instead of
relying on happy-path unit tests. It is also aligned with agentic balance:
deterministic code records the envelope and metrics, while semantic acceptance
continues to depend on calibrated extraction, grounding, contradiction, dedup,
and trust-floor gates.

## Next Work

Next slice: start the agentic red-team metrics item for prompt-injection,
tool-abuse, MCP read extraction, and trust-floor bypass attempts. Keep all local
validation at `$0`.

## Spend Ledger For This Run

External paid spend: `$0.00`.

Only local filesystem reads, local tests, lint, and git operations are planned. No provider APIs, embeddings, paid evals, or paid research runs will be used.
