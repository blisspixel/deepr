# Local structured consult graph

Status: eval-only prototype shipped on 2026-07-29. It is not production consult
or MCP runtime behavior.

## Decision

Deepr will test one fixed, read-only dependency graph for deeper expert
consultation using proven owned local inference only. The prototype belongs in
the consult evaluation harness. It does not change `deepr expert consult`, add
a generic swarm runtime, enable unattended work, or authorize plan-quota or
metered capacity.

The first graph is deliberately small:

```text
validated brief and frozen expert snapshots
                    |
       +------------+------------+
       |            |            |
       v            v            v
 local position  local position  local position
       |            |            |
       +------------+------------+
                    |
           deterministic completion gate
                    |
                    v
             local synthesis
```

Each position node independently answers the same precise question from one
expert's frozen state. It returns a versioned, concise artifact rather than
free-form workflow history. Synthesis runs only after the declared completion
policy passes. The public one-shot stored-packet council remains the baseline.

The experiment is called `$0` only in the narrow provider-invoice sense. Local
tokens, elapsed time, electricity, memory, hardware occupancy, and thermal load
remain real resources and are bounded and reported.

## Why this shape fits Deepr

Deepr already has bounded parallel packet loading, expert selection, frozen
state, local Ollama synthesis, traces, no-live-fallback controls, and a consult
evaluation spine. The missing capability is question-specific independent
expert judgment before synthesis. A dependency graph can make that distinction
explicit without inventing a general orchestration platform.

The supplied graph-engineering article contributes useful tests:

- Keep an edge only when a node consumes an earlier artifact or shares a
  conflicting mutable resource.
- Fan out independent work, then apply an explicit completion gate.
- Store artifacts outside prompt history and pass bounded references or fields.
- Count expected, completed, failed, cancelled, timed-out, and skipped nodes.
- Repair only a failed branch, within the original envelope.
- Treat external evidence and executable checks as anchors. Agent agreement is
  not verification.

Its example code is not a production contract. An unbounded `gather`, a
synchronous client inside an async function, arbitrary model-planned nodes,
missing schemas, and no completion or resource policy are specifically rejected.
Running 1,000 local generations is not a goal.

## Capacity and `$0` authority

The whole graph is rejected before the first model token unless every model
node proves all of the following:

1. Capacity kind is `owned_hardware`.
2. Provider is exactly `local`.
3. The Ollama endpoint passes the literal-loopback, DNS-free owned endpoint
   validator before transport construction.
4. Native `GET /api/status` reports `cloud.disabled=true` with source exactly
   `config`. Operators must start Ollama with cloud disabled, such as
   `OLLAMA_NO_CLOUD=1`, and restart the server before this mode is eligible.
5. The selected model is an exact `/api/tags` inventory entry with a positive
   local byte size, a lowercase SHA-256 digest, and format exactly `gguf`.
   Unknown, cloud, alias-only, digestless, zero-size, and remote-tagged models
   fail before `/api/chat`.
6. The graph uses a narrow Ollama-native HTTP transport. It sends no provider
   credentials, ignores proxy and OpenAI environment state, follows no
   redirects, and performs no automatic retries.
7. Live metered fallback is false.
8. Plan-quota fallback is false.
9. Tools, browsing, embeddings, remote retrieval, and provider APIs are absent.
10. Every node writes one fsynced, content-free `$0` cost-ledger dispatch
    marker before inference. Ledger failure blocks the model call.
11. The result reports `$0` Deepr metered cost and freezes the local model
    digest, size, format, cloud-disable proof, and transport posture.

Unknown, LAN, DNS-named, proxy-routed, credential-bearing, or remote
OpenAI-compatible endpoints do not qualify as local. Installed API keys do not
grant fallback authority. No node can change its provider, endpoint, model
class, tool surface, or capacity class after preflight.

## Resource envelope

Dollar cost and token cost are separate controls. One immutable run envelope
must declare and enforce:

- maximum expert position nodes;
- maximum total graph nodes and depth;
- maximum concurrent local generations;
- maximum aggregate input tokens and context bytes;
- maximum aggregate output tokens;
- maximum calls by node kind;
- per-node and whole-run elapsed ceilings;
- maximum artifact bytes;
- retry and targeted-repair allowances; and
- completion policy.

The prototype defaults to three expert positions, permits at most the existing
ten-expert council ceiling, and defaults local generation concurrency to one.
Width and execution concurrency are different settings. A single GPU may gain
quality breadth from several independent nodes while becoming slower or running
out of memory if those nodes generate simultaneously. Concurrency above one
must therefore be explicit and benchmarked on the operator's local capacity.

The initial protocol allows exactly one attempt per position and one synthesis
call. It has no planner call, verifier call, repair call, discovery loop, peer
turn, or layered reducer. Later node kinds may be admitted only by adding their
worst-case calls and tokens to the same preflight envelope.

## Node and graph contracts

Every node needs a stable ID and a versioned contract containing:

- graph ID, node kind, dependencies, and input artifact IDs;
- expert ID and immutable expert snapshot hash when applicable;
- prompt and protocol version;
- local endpoint class, model, and model identity evidence;
- input, output, time, and artifact ceilings;
- attempt identity and maximum attempts;
- status, start and completion timestamps, and stop reason; and
- output artifact ID, hash, schema result, and token usage.

Preflight deterministically rejects duplicate IDs, missing dependencies,
self-dependencies, cycles, excessive width or depth, unsupported node kinds,
undeclared mutable resources, and an envelope that cannot cover every node.
Downstream execution receives validated dependency artifacts, not a coroutine
that closes over shared mutable state.

The position artifact separates:

- answer or explicit abstention;
- evidence-backed claims and exact source refs;
- assumptions;
- important unknowns;
- question-specific uncertainty;
- a plausible alternative;
- a disconfirming observation or discriminating test; and
- decision implications.

Stored-belief confidence remains distinct from confidence in the
question-specific judgment. Concise rationale is allowed. Private
chain-of-thought is neither requested nor stored.

## Completion, reduction, and synthesis

`require_all` is the prototype's only completion policy. Synthesis does not run
when any required position is failed, cancelled, timed out, missing, empty, or
schema-invalid. The run artifact remains useful and explicitly incomplete.

Any later partial policy must be caller-selected before execution and must
preserve missing node identities in the synthesized artifact and non-success
CLI status. A plausible report can never conceal a vanished branch.

Deterministic code owns exact counts, schema validation, hashes, bounds,
normalization, and exact duplicate IDs. Models own relevance, evidence meaning,
alternatives, dissent, and synthesis. Lexical overlap may route candidate
experts but cannot conclude semantic suitability or truth.

Layered fan-in is not part of the first prototype. With at most ten concise
positions, extra local summary calls may cost more tokens and lose evidence.
It becomes eligible only if a deterministic serialized-context ceiling shows
that direct synthesis cannot fit, and every reducer call fits the original
envelope.

## Verification and evaluation

The prototype must extend `deepr eval consult` before any runtime command is
considered. Frozen, human-anchored held-out cases compare four arms:

1. one predeclared relevant expert;
2. the current stored-packet council;
3. the structured independent-position graph; and
4. one union-context synthesizer.

The primary comparison holds the local model, eligible frozen expert state,
aggregate context, aggregate output-token ceiling, and task set constant.
Reports record calls, input and output tokens, context and artifact bytes,
latency, peak concurrency, node completion counts, model identity, and `$0`
metered cost. Participant ordering and arm labels are blinded where practical.

Human or calibrated, bias-checked review scores framing, expert relevance,
unique evidence retained, evidence and assumption separation, uncertainty,
alternative and crux coverage, dissent preservation, useful next tests, and
unsupported claims. Structural completion is never semantic acceptance.

The quality threshold and tolerated resource regression must be declared in
the eval fixture before live trials. If the graph arm does not beat the baseline
under matched resources, work stops. Adding nodes, roles, rounds, or a stronger
synthesizer after seeing the result is a new experiment, not a rescue of the
failed one.

## Rollout

1. Publish versioned brief, position, graph-run, and synthesis schemas plus
   zero-call structural fixtures. Complete on 2026-07-29.
2. Add an explicit local-only live eval mode with no expert or project-state
   writes and no fallback. Content-free `$0` cost-ledger dispatch markers are
   mandatory observability writes.
   Complete on 2026-07-29 as `deepr eval consult --structured-local QUESTION`.
3. Collect matched-resource held-out evidence and local capacity measurements.
4. If the predeclared gate passes, consider an opt-in shadow mode beside the
   current consult command.
5. Consider a public additive contract only after recovery, cancellation,
   trace, and negative-transfer evidence passes.

Plan-quota, paid API, unattended, state-writing, recursive discovery, general
debate, and generic swarm modes are outside this rollout.

## Shipped eval surface

The opt-in command runs the fixed graph against frozen stored expert packets:

```bash
deepr eval consult --structured-local "Which control should we test first?" \
  --expert "Reliability Expert" \
  --expert "Security Expert" \
  --model qwen2.5:14b \
  --concurrency 1 \
  --max-elapsed-seconds 3600 \
  --save
```

Omit `--expert` to use the existing disclosed read-only router. Configure the
Ollama server with `OLLAMA_NO_CLOUD=1` and restart it first. The command requires
the native status endpoint to prove cloud is disabled by stable config, then
binds an exact materialized local GGUF inventory entry by name, digest, and
positive byte size. It uses a credential-free native transport with environment
proxies, redirects, and retries disabled. Provider-invoice cost is fixed at
`$0`; plan and metered fallback, tools, and retrieval are absent. It writes no
expert or project state. Every execution receives a unique run ID. Every node
must first append a content-free, fsynced `$0` cost-ledger dispatch marker bound
to that run ID, so repeating an identical question remains separately visible.
A content-free terminal marker reconciles node and transport-attempt counts,
including cancellation. At most ten positions and four simultaneous
local generations are allowed, and default concurrency remains one. Model
residency is fixed and disclosed at five minutes rather than inherited from an
environment override.

The result is `deepr-structured-consult-run-v1`. It embeds the immutable brief,
successful position artifacts, optional synthesis, exact terminal node counts,
its unique run ID, reserved token and context ceilings, model provenance, elapsed time including
preflight, transport attempts, ambiguous usage, peak concurrency, and typed
stops. A failed, timed-out, cancelled, empty, malformed,
or missing position causes synthesis to be skipped. Raw malformed model output
and private reasoning are not copied into the run artifact.

This surface is deliberately absent from MCP and `deepr expert consult`. A
hosted MCP container does not become local capacity merely because its caller
is local. Promotion requires the four-arm held-out comparison, semantic review,
recovery evidence, and a separate additive runtime decision.

## Rejected alternatives

- A general graph framework before the consult eval proves a need.
- A model planner that can invent runtime nodes or dependencies.
- Automatic local to plan to API fallback.
- Identical prompt replicas followed by majority vote.
- Parallel writes to expert state.
- Unbounded `gather` or a default concurrency based on node count.
- Treating consensus, confidence, or fluent synthesis as an external anchor.
- Always-on layered fan-in.
- Calling owned hardware resource-free.

## Implementation map

The smallest additional source set required after this design gate is:

- `src/deepr/evals/consult.py` for the matched-resource arm report;
- one dedicated consult-graph contract module for validation and typed
  dependency artifacts;
- the existing eval CLI command module for an explicit local-only option;
- `tests/unit/test_eval/test_consult_eval.py` for report invariants; and
- focused graph-contract tests for cycles, missing nodes, envelope overflow,
  completion counts, fallback refusal, and zero-cost authority.

The generic async dispatcher must not be assumed to provide this contract. It
currently orders preconstructed coroutines but does not pass typed dependency
results into downstream factories or provide the complete graph preflight and
completion artifact required here.

## Current guidance

- Anthropic, *Building Effective Agents*, December 2024: start with the
  simplest workflow that meets the need and use parallelization only for
  independent subtasks.
- Google Research, *Towards a science of scaling agent systems*, 2026: topology
  must match task structure, and added agents can amplify errors.
- Anthropic, *How we built our multi-agent research system*, 2025: parallel
  breadth can help research, but orchestration, token use, and failure handling
  dominate production reliability.
- AWS Step Functions Distributed Map documentation, checked 2026-07-26:
  production fan-out needs explicit concurrency and tolerated-failure policy.
- OpenTelemetry GenAI semantic conventions 1.43, checked 2026-07-25: model,
  provider, operation, token-limit, and token-usage fields support bounded node
  observability without storing sensitive prompt content.
- Ollama structured-output documentation, checked 2026-07-29: native
  `/api/chat` accepts a JSON Schema in `format` and recommends validating the
  returned object. The graph sends the exact contract schema and still validates
  every response locally because schema-shaped output is not semantic proof:
  <https://docs.ollama.com/capabilities/structured-outputs>
- MCP 2026-07-28, checked 2026-07-29: long-running tool work may use the
  optional Tasks extension, but an ordinary synchronous `tools/call` remains
  compliant. The eval-only graph is not promoted into MCP Tasks until its
  quality gate and durable task authorization contract both pass:
  <https://modelcontextprotocol.io/specification/2026-07-28>

## Acceptance criteria

- No graph node can construct or call a plan-quota or metered provider.
- A non-loopback endpoint, cloud-enabled server, unstable cloud-disable source,
  or unmaterialized model rejects the full run before inference.
- Every attempted local node has one durable, content-free `$0` ledger marker
  and bounded token fields. A separate terminal marker reconciles attempts even
  after cancellation. Repeated identical runs never share marker identity.
  Ledger failure prevents dispatch or successful terminal completion.
- The run never exceeds declared node, call, token, byte, concurrency, time,
  retry, or repair ceilings.
- Cycles, duplicate IDs, missing dependencies, and unknown node kinds fail
  before dispatch.
- Expected and terminal node counts reconcile exactly.
- Required node failure prevents synthesis and produces an incomplete artifact.
- The graph writes no belief, graph, profile, expert, or source state. Its only
  mandatory write is the append-only cost-ledger marker.
- The four-arm held-out report holds aggregate resources constant and separates
  structural completion from reviewed semantic quality.
- No public runtime surface is promoted unless the predeclared quality and
  resource gate passes.
