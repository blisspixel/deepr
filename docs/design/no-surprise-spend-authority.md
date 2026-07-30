# No-surprise spend authority and bounded workflow graphs

Status: accepted; phases 1, 2, and the paid provider boundary implemented;
graph parent reservations and provider-authenticated account controls remain
gated, 2026-07-29

## Decision

Deepr will use one deterministic spend authority for every metered side effect.
The authority is evaluated before provider construction and again inside the
durable reservation transaction. A persisted operator monthly budget is a hard
ceiling, not an approval hint. Zero means no paid spend. Negative, unlimited,
malformed, unreadable, or contradictory policy fails closed.

Local owned capacity and safety-eligible plan quota remain separate capacity
classes. They may report `$0` at the margin, but they never authorize a paid API
fallback. A metered API is selected only by an explicit paid-capacity request.
Code may label a model client `$0` only through a private process-local proof
minted by Deepr after the corresponding local or plan-quota admission succeeds.
Caller labels, a numeric zero estimate, an arbitrary injected client, and a
compatible SDK type are not zero-dollar authority.

For a workflow graph, the parent must reserve the sum of the runnable branches'
worst-case envelopes before those branches become queue-eligible. Each child
inherits a non-increasing slice of that reservation. A reducer may release
unused slices, but a child, retry, repair node, verifier, or synthesizer cannot
increase the parent ceiling. Dynamic discovery may create new nodes only from
remaining reserved headroom.

## Why

The July 2026 incident recorded more than `$38` of monthly spend while the
operator believed a `$10` monthly budget was controlling execution. The
persisted budget governed confirmation on a subset of CLI paths, while other
paths used independent `$20`, `$200`, or `$500` monthly limits. Some maintenance
commands could also select a metered API when local and plan capacity were
unavailable. A manually confirmed command could exceed the nominal budget.

Those are authority failures, not estimation errors. Better estimates cannot
repair a cap that is optional or evaluated outside the transaction that admits
work.

## Capacity contract

| Capacity class | Marginal dollar posture | Admission requirement | Accounting |
|---|---:|---|---|
| `local_owned` | `$0` only when endpoint ownership is proven | Explicit local request or admitted local route | `$0` attempt receipt |
| `plan_quota` | Prepaid or subscription quota, no paid overage | Stored plan provenance, confined tools, live no-overage proof | Quota event plus `$0` cost event |
| `api_metered` | Paid | Explicit API selection, dual consent where remote, finite envelope, durable reservation | Settled canonical cost event |
| unknown | Unknown | Refused | Diagnostic only |

"Free" means free at the margin for Deepr's dispatch decision. It does not mean
the subscription or hardware has no cost. Unknown credential provenance,
remote Ollama-compatible endpoints, vendor credits, and metered-at-margin CLIs
must not be relabeled as free.

## Spend-cap resolution

The effective limit for each window is the tightest applicable non-negative
limit:

1. Explicit `DEEPR_MAX_COST_*` values.
2. Legacy `DEEPR_*_LIMIT` values during compatibility support.
3. The persisted operator monthly budget.
4. A narrower caller or workflow envelope.
5. The compiled absolute safety ceiling.

The hierarchy is normalized so `per_call <= daily <= weekly <= monthly`.
Missing explicit monthly authority disables paid dispatch by default. A
persisted zero or manual freeze disables it even when an environment value is
higher. Changing a dashboard limit can narrow the effective limit but cannot
raise any authority above the shared resolver.

The weekly window is the UTC calendar week beginning Monday. Daily and monthly
windows are UTC calendar windows, matching the canonical cost ledger.

## Reservation and settlement invariants

Before a paid side effect:

1. Parse the request into a finite provider-complete cost envelope.
2. Resolve the current authoritative caps.
3. Strictly read canonical settled spend.
4. Count every active durable hold.
5. Atomically prove `settled + active + new <= cap` for every window.
6. Persist the reservation with a random internal dispatch binding, canonical
   provider, model, job, and worst-case ceiling.
7. Freeze the request, atomically bind its canonical SHA-256 digest to that
   reservation, and persist the dispatch-intent transition immediately before
   provider work.
8. Mint one opaque, one-use, task-local grant only after that durable
   transition succeeds. The grant is bound to the exact provider object,
   provider, model, reservation, job, and frozen request digest.

After dispatch:

1. Settle provider-reported usage when complete and priceable.
2. Settle the full reserved ceiling when the outcome or usage is ambiguous.
3. Keep the hold active if canonical settlement cannot be made durable.
4. Treat `actual > reserved` as an accounting divergence and freeze subsequent
   paid dispatch until acknowledged.
5. Preserve raw provider output or a recoverable staging record before marking
   the application workflow complete.

The exported provider base owns the public submission boundary and adapters
cannot override it. Calling a public adapter, its internal implementation, a
different provider object, or a changed request without the exact one-use grant
fails before an SDK request. Queue metadata never exposes the dispatch binding.
Hosted upload and vector-store creation stay blocked until their complete
lifecycle cost can use the same authority.

Completed research is priced from the canonical queued model, not a provider
fallback label. Provable web-search calls and code-interpreter sessions are
added to token cost. Missing or inconsistent model, usage, or tool evidence
settles the full reserved ceiling. A missing, refunded, or non-settled durable
outcome freezes paid dispatch and fails before terminal publication. Immediate
OpenAI-compatible completions conservatively consume the full reservation
because that seam does not preserve the admitted tool envelope.

No human confirmation, `--yes`, unrestricted MCP mode, dashboard mutation,
retry, or model-generated instruction can bypass these invariants.

## Spend truth and receipt identity

Every operator-facing cost view must distinguish:

1. Canonical settled spend for the exact UTC window.
2. Durable active holds that may still become spend.
3. Exposure, defined as settled spend plus active holds.
4. Per-window remaining capacity.
5. The maximum new paid call allowed by the per-job, day, week, and month
   ceilings together.

An unreadable ledger or reservation store is unknown money state, not zero.
Unknown money state reports zero authorizable headroom and blocks paid work.
Derived dashboard preferences are not spend authority and must not be labeled
as limits unless they are clamped through the shared resolver.

The canonical write root is `~/.deepr/costs` unless an absolute
`DEEPR_COST_DATA_DIR` explicitly isolates a deployment. During legacy
migration, a validated checkout can contribute read-only ledger and reservation
state. Each discovered artifact is durably appended to
`accounting_sources.jsonl` under the canonical root before it is trusted. A
wheel later launched outside the checkout reads that registry instead of
depending on package location or current directory. A registered artifact that
is missing, malformed, or unreadable makes accounting incomplete and blocks
paid work. Health output distinguishes the primary write path from every
accounting read path and its contribution.

The canonical root also owns a durable random cost-state identity and a
monotonic registry-prefix anchor. Each registered ledger records its byte
high-water mark and prefix digest. Each reservation database records its row
high-water mark, count, and row digest. Truncation, replacement, missing
required provenance, duplicate JSON keys, a removed `.env` cap, or a widened
historical `.env` cap invalidates authority. Editable installs and installed
wheels therefore retain the same strict money history when they can reach the
registered artifacts.

This is not an independent rollback oracle. Restoring the entire canonical
cost root, including its identity and anchors, from one older snapshot can make
that snapshot internally consistent. After any whole-root restore, paid
authority must remain frozen and be explicitly reauthorized against current
provider billing evidence. A future independent monotonic anchor is required
to detect that class of rollback automatically.

For later invoice reconciliation, supported central metered calls preserve a
local client correlation ID, a provider HTTP request ID when exposed, and a
separate provider object ID. The extractor is bounded and reads only declared
fields, known mappings, known request-ID headers, and bounded exception chains.
It does not record prompts, responses, credentials, authentication headers, or
provider endpoints. An absent provider request ID remains honest missing data.

These identifiers improve joining but do not make the local ledger a provider
invoice. Provider billing remains authoritative. Deepr now imports a bounded
normalized statement offline, separates capacity classes, performs exact
receipt reconciliation, and freezes on non-clean applied evidence. It still
cannot detect calls made outside Deepr. Provider-specific authenticated hard-
limit verification and current account, scope, and credential resolution are
not installed, so production paid dispatch remains blocked. Those controls
remain required defense in depth.

## Graph execution contract

Deepr does not need a new graph framework merely to parallelize work. Existing
queues and run records are sufficient when they represent real dependencies.
The useful graph rules are:

- Persist node inputs, outputs, status, attempt identity, and artifact
  references outside prompt context.
- Make node payloads schema-valid and idempotent.
- Enqueue only nodes whose dependencies and inherited budget are satisfied.
- Give every fan-out an expected child count and an explicit all, quorum, or
  optional completion policy.
- Report missing, failed, timed-out, and dead-lettered branches as partial, not
  complete.
- Retry or repair only failed branches when successful outputs are durable.
- Use deterministic reducers for schema checks, counts, normalization, and
  exact deduplication. Model judgment owns semantic support, contradiction,
  relevance, and synthesis.
- Use fresh, task-specific verifier context and external anchors such as a
  primary source, passing tests, or a durable provider receipt.
- Give discovery loops stable node identities, deduplication, iteration and
  node caps, wall-clock limits, and inherited cost ceilings.
- Isolate mutable state per parallel worker and merge through a controlled
  write boundary.

The structured expert-consult graph is a narrower prototype. It is eval-only,
read-only, and owned-local. Every model node must prove provider `local` and a
literal-loopback Ollama endpoint, with no plan-quota or metered fallback. Its
token, call, context, artifact, concurrency, and time ceilings are binding even
though its provider-invoice cost is `$0`. See
[local-structured-consult-graph.md](local-structured-consult-graph.md).

## Rollout

1. Unify cap resolution, make the operator budget binding, add manual freeze,
   add the weekly window, clamp web mutation, and remove implicit metered
   maintenance fallback.
2. Require every paid SDK, tool, upload, embedding, image, judge, and script to
   use the durable paid-call transaction. Add a blocking static boundary check.
3. Add parent reservations and child budget slices to composed and fan-out
   workflows before re-enabling them.
4. Add provider-complete envelopes, divergence freeze, strict ledger-root
   reconciliation, and durable attempt receipts for all capacity classes.
5. Add threshold notifications and graph-level partial-completion telemetry.
6. Import provider-authoritative billing evidence and freeze paid work on
   unexplained positive drift. The bounded offline importer and freeze are
   shipped. Keep paid authority blocked until provider-specific authenticated
source and credential-identity adapters can prove hard-limit or overage-off
   posture. The external hard no-overage ceiling must be no higher than the
   operator ceiling, and cached evidence is not sufficient for dispatch.
7. Consolidate registered legacy roots into one lock-protected canonical state
   and bind any future paid authorization to a stable cost-state manifest.
   Root, policy, digest, or migration-status drift must invalidate authority.

Implementation note, 2026-07-25: the shared wallet, job/day/week/month
hierarchy, manual freeze, durable aggregate reservations, pre-dispatch
revalidation, exact bounded chat and embedding envelopes, dual MCP consent,
terminal success/failure settlement, canonical REST spend view, and static paid
boundary are shipped in the working tree. Paid composed fan-out remains gated;
parent reservation slices and branch-completion telemetry are not yet shipped.

Implementation note, 2026-07-27: strict budget history, active-hold visibility,
effective CLI cap displays, live pull-based CLI threshold state, provider
receipt identifiers, offline billing import, capacity-class reconciliation,
immutable apply evidence, and divergence freeze are shipped. Outbound threshold
delivery, provider-specific authenticated account-control adapters, and
external-spend detection are not shipped. A provider account can still accrue
charges through another application, a shared or compromised credential, a
vendor-side pricing change, or taxes outside Deepr's usage ledger.

Implementation note, 2026-07-28: validated legacy accounting roots persist in
an append-only home registry shared by editable and installed processes.
Missing registered state is unknown and fail-closed. Canonical consolidation
and an independent rollback anchor remain required before paid authority can be
enabled after a whole-root restore.

Implementation note, 2026-07-29: the canonical root now has a durable identity,
registry-prefix anchor, ledger and reservation high-water identities, strict
duplicate-key rejection, and monotonic checkout `.env` caps. Paid research
reservations persist an internal provider, model, request, job, ceiling, and
random binding before a one-use provider grant can exist. The provider base
owns a non-overridable public boundary, direct legacy consensus fan-out is
disabled, and unproven `$0` injected clients fail before dispatch. Research
completion uses canonical model pricing, adds provable paid-tool charges, and
uses the reservation ceiling whenever evidence is ambiguous. Paid APIs remain
frozen because provider-authenticated account and credential controls are not
installed. A future unfreeze also requires a live control observation for each
one-use dispatch, bound to the owned client and exact account scope. Generic
clients, provider callbacks, retained server context, and unbounded billed tool
sessions remain disabled.

Each phase is independently fail-closed. A later phase may improve
availability, reporting, or efficiency, but it must not weaken an earlier
money invariant.

## Rejected alternatives

- Treating `budget.json` as a confirmation threshold. Confirmation cannot make
  a hard cap exceedable.
- Allowing `-1` or another unlimited mode. Unlimited paid autonomy is
  incompatible with the no-surprise-bills objective.
- Automatically falling through local, plan, then API. Capacity unavailability
  is a typed stop, not spend authorization.
- Reserving each child independently after fan-out. Concurrent children can
  jointly overcommit and a partially launched graph cannot honor one approved
  run ceiling.
- Relying on agreement between agents. Agreement is not an external anchor and
  does not authorize money.

## Current guidance checked

- LangGraph persistence documentation, accessed 2026-07-25, documents
  checkpointing at graph supersteps and pending per-task writes so completed
  branches can be preserved during recovery:
  <https://docs.langchain.com/oss/python/langgraph/persistence>
- LangGraph Functional API documentation, accessed 2026-07-25, requires
  serializable task inputs and outputs, deterministic replay, and idempotent
  handling of side effects:
  <https://docs.langchain.com/oss/python/langgraph/functional-api>
- AWS Step Functions Distributed Map documentation, accessed 2026-07-25,
  exposes explicit maximum concurrency and tolerated failure count or
  percentage. An omitted concurrency limit can permit very wide execution:
  <https://docs.aws.amazon.com/step-functions/latest/dg/state-map-distributed.html>
- OpenTelemetry GenAI semantic conventions 1.43, accessed 2026-07-25, define
  standard provider, model, operation, request-token-limit, and token-usage
  attributes. Prompt and response content remain sensitive and are not required
  for cost accounting:
  <https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/>
- OpenTelemetry moved the GenAI conventions to their own repository by
  2026-07-29. Deepr should pin the vocabulary it emits and migrate deliberately,
  not silently follow renamed attributes. The canonical ledger remains the
  spend authority; telemetry is a derived diagnostic view:
  <https://github.com/open-telemetry/semantic-conventions-genai>
- AWS Budgets documentation, checked 2026-07-29, says billing data used for
  budgets updates at least daily and alerts follow that refresh cadence. Cloud
  alerts are therefore backstops, not dispatch authorization. Any hosted Deepr
  deployment must enforce its local reservation ceiling before work and use a
  provider-side budget action or permission removal only as a second barrier:
  <https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html>
  <https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-action-configure.html>
- GitHub Actions documentation, checked 2026-07-29, says public repositories
  can use standard GitHub-hosted runners without charge, private repositories
  consume included minutes and then bill, and a workflow job otherwise has a
  360-minute default timeout. Deepr therefore pins a timeout on every CI job.
  A literal `$0` CI posture also requires keeping the repository public or
  disabling paid Actions and payment authority at the account boundary. GitHub
  budget alerts alone are not treated as a hard real-time stop:
  <https://docs.github.com/en/billing/concepts/product-billing/github-actions>
  <https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes>
  <https://docs.github.com/en/billing/concepts/budgets-and-alerts>
- xAI pricing and tool-usage documentation, updated July 3 and May 27, 2026 and
  accessed 2026-07-25, state that server-side search is billed per successful
  invocation and that one `max_turns` turn may invoke multiple tools in
  parallel. A turn cap is therefore not a hard dollar cap:
  <https://docs.x.ai/developers/pricing>
  <https://docs.x.ai/developers/tools/tool-usage-details>

## Acceptance criteria

- With an operator monthly budget of `$5`, canonical settled spend plus every
  active hold can never exceed `$5` through any supported paid entry point.
- At or beyond a cap, every new paid reservation fails before client
  construction. The failure remains true under concurrent processes.
- `budget set 0` and `budget freeze` block all paid dispatch. `budget unfreeze`
  cannot bypass an exhausted cap or use self-asserted account-control evidence.
- Malformed or unreadable cap policy fails closed.
- Web endpoints cannot raise limits above current authority.
- No maintenance command selects an API merely because local or plan capacity
  is unavailable, including noninteractive execution.
- Paid fan-out remains disabled until one atomic parent reservation covers all
  runnable branches and completion status accounts for every expected child.
- Local and plan execution never fall through to paid API after a failure.
- An injected client that merely claims local, plan, or zero-dollar execution
  cannot cross a model boundary without an exact Deepr-minted capacity proof.
- Direct provider methods, adapter implementation methods, mismatched provider
  objects, altered requests, reused grants, and client-visible binding metadata
  cannot cross the paid provider boundary.
- A provider hard no-overage ceiling above the operator ceiling, a cached-only
  control observation, an injected client, a custom endpoint, a provider
  webhook, retained server context, or an unbounded billed tool session cannot
  authorize dispatch.
- Ambiguous response model, token, tool, or durable settlement evidence consumes
  the reservation ceiling or freezes paid work. It never settles optimistic
  zero.
- Focused concurrency and bypass regression tests pass, followed by the full
  unit, branch coverage, lint, format, type, ratchet, and build gates.
