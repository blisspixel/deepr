# No-surprise spend authority and bounded workflow graphs

Status: accepted; phases 1 and 2 implemented, phase 4 partially implemented,
2026-07-25

## Decision

Deepr will use one deterministic spend authority for every metered side effect.
The authority is evaluated before provider construction and again inside the
durable reservation transaction. A persisted operator monthly budget is a hard
ceiling, not an approval hint. Zero means no paid spend. Negative, unlimited,
malformed, unreadable, or contradictory policy fails closed.

Local owned capacity and safety-eligible plan quota remain separate capacity
classes. They may report `$0` at the margin, but they never authorize a paid API
fallback. A metered API is selected only by an explicit paid-capacity request.

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
6. Persist the reservation.
7. Persist a dispatch-intent marker immediately before provider work.

After dispatch:

1. Settle provider-reported usage when complete and priceable.
2. Settle the full reserved ceiling when the outcome or usage is ambiguous.
3. Keep the hold active if canonical settlement cannot be made durable.
4. Treat `actual > reserved` as an accounting divergence and freeze subsequent
   paid dispatch until acknowledged.
5. Preserve raw provider output or a recoverable staging record before marking
   the application workflow complete.

No human confirmation, `--yes`, unrestricted MCP mode, dashboard mutation,
retry, or model-generated instruction can bypass these invariants.

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

Implementation note, 2026-07-25: the shared wallet, job/day/week/month
hierarchy, manual freeze, durable aggregate reservations, pre-dispatch
revalidation, exact bounded chat and embedding envelopes, dual MCP consent,
terminal success/failure settlement, canonical REST spend view, and static paid
boundary are shipped in the working tree. Paid composed fan-out remains gated;
parent reservation slices and branch-completion telemetry are not yet shipped.

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
- xAI pricing and tool-usage documentation, updated July 3 and May 27, 2026 and
  accessed 2026-07-25, state that server-side search is billed per successful
  invocation and that one `max_turns` turn may invoke multiple tools in
  parallel. A turn cap is therefore not a hard dollar cap:
  <https://docs.x.ai/developers/pricing>
  <https://docs.x.ai/developers/tools/tool-usage-details>

## Acceptance criteria

- With an operator monthly budget of `$10`, canonical settled spend plus every
  active hold can never exceed `$10` through any supported paid entry point.
- At or beyond a cap, every new paid reservation fails before client
  construction. The failure remains true under concurrent processes.
- `budget set 0` and `budget freeze` block all paid dispatch. `budget unfreeze`
  cannot bypass an exhausted cap.
- Malformed or unreadable cap policy fails closed.
- Web endpoints cannot raise limits above current authority.
- No maintenance command selects an API merely because local or plan capacity
  is unavailable, including noninteractive execution.
- Paid fan-out remains disabled until one atomic parent reservation covers all
  runnable branches and completion status accounts for every expected child.
- Local and plan execution never fall through to paid API after a failure.
- Focused concurrency and bypass regression tests pass, followed by the full
  unit, branch coverage, lint, format, type, ratchet, and build gates.
