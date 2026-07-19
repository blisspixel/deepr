# Three Expert Council And Learning Workflow

Status: works-now guide, verified against the CLI on 2026-07-18. The one-shot
consult is stable. The deeper local investigation surface is experimental and
has not passed its semantic-quality promotion gate.

This guide builds three durable experts:

- Temporal Knowledge Graphs
- Digital Consciousness
- Model Context Protocol

It then runs a bounded council, turns unknowns into research, and stages two
different kinds of learning for each expert. Factual claims need replayable
source evidence and independent verification. Hypotheses, concepts, stances,
and original ideas remain non-factual perspective state with uncertainty and
disconfirming tests. The default path uses local Ollama and costs `$0` in Deepr.
An optional API synthesis is bounded by one explicit transaction ceiling.

## What Works Now

| Capability | Current behavior |
|---|---|
| Consult one expert | Reads a bounded packet of stored beliefs and runs one synthesis call |
| Consult several experts | Reads one independently selected stored-state packet per expert, then runs one synthesis call |
| Experts research and exchange a bounded round | Experimental through local-only `expert investigate`; one blinded targeted exchange, with optional private revision |
| Successful consult automatically creates gaps | Not shipped |
| Consult changes beliefs or graph state | Never |
| Investigation changes beliefs or graph state | Never automatically; `--learning stage` creates separate factual and non-factual perspective envelopes that still require explicit apply |
| Local synthesis | Works with Ollama at `$0` provider cost |
| Explicit plan synthesis | Works for eligible plan CLIs with no metered API fallback; external quota or billing cannot be proven by Deepr |
| API synthesis | Works as one priced, reserved, and settled call |
| Investigation capacity | Local Ollama only, exact `$0`, no fallback; plan-quota and metered API investigation execution are planned, not shipped |

`deepr expert consult` is a one-shot stored-context council. The expert names
identify durable knowledge states, not separate model agents. Each perspective
is selected from that expert's current beliefs. The experts do not see one
another's output. One backend synthesizes agreements, dissent, assumptions,
risks, and an execution plan.

The returned `deepr-consult-v1` artifact now makes this explicit:

- `consultation_mode` is `one_shot_stored_context_synthesis`;
- `expert_generation_calls` is `0`;
- `experts_exchange_turns` is `false`;
- `writes_beliefs` and `writes_graph` are `false`;
- the budget block separates the total transaction ceiling from the smaller
  metered synthesis ceiling.

## Choose Consult Or Investigate

Use `deepr expert consult` when the experts already contain the relevant
knowledge and you want one quick synthesis. It makes no expert-generation
calls, permits no peer turns, and performs no learning.

Use `deepr expert investigate` when the question needs fresh research and a
real, bounded exchange. The experimental local runtime:

1. freezes each named expert's current state;
2. retrieves the shared question through a distinct, hash-bound lens made from
   each expert's frozen domain, with requested URLs fetched directly instead
   of copied into discovery queries;
3. records an independent position from every expert;
4. routes one blinded, targeted challenge to each expert in `discuss` or
   `deep` mode;
5. optionally lets each expert revise privately in `deep` mode;
6. runs a separately pinned checker and synthesizer;
7. optionally stages separate factual and perspective learning envelopes after
   the answer.

Protocol modes are exact, not marketing labels:

- `independent` performs research, independent positions, checking, and
  synthesis with no peer exchange.
- `discuss` adds one blinded targeted challenge per expert, with no private
  revision turn.
- `deep` adds the same bounded challenge plus one private revision per expert.

Model-generated charter queries are saved as proposals, but they do not gain
network authority. Retrieval stays reproducible and bounded by the caller's
question and each frozen expert domain. Caller-requested URLs are fetched
directly but omitted from discovery query text. Distinct lenses
reduce identical-evidence herding without letting a model silently widen the
research scope.

This is not an open chat room or an autonomous recursive loop. It has a fixed
roster, fixed phases, exact call and retrieval ceilings, one parent time and
disk envelope, durable checkpoints, and no fallback. Agreement is never used
as evidence.

### Plan A `$0` Investigation

The three expert profiles in this guide must already exist. Pick exact Ollama
models that fit the machine. The review model may be the same model, but a
stronger local checker, synthesizer, and staged claim verifier can be pinned
separately.

On a first setup, complete Sections 1 and 2 below before running this command.
Run `deepr expert list` and use the exact stored names. The examples use the
three names created in Section 2. If an existing profile already covers one of
these roles under a different name, substitute that exact name consistently
instead of creating a near-duplicate expert. Roster resolution fails before
network or model work when a name does not exist or is ambiguous.

```powershell
deepr expert investigate plan `
  "How should Deepr combine temporal expert memory, uncertainty about digital consciousness, and MCP authority boundaries without turning model agreement into graph truth?" `
  --expert "Temporal Knowledge Graphs" `
  --expert "Digital Consciousness" `
  --expert "Model Context Protocol" `
  --text "Treat July 16, 2026 as the research cutoff." `
  --url "https://modelcontextprotocol.io/specification/2025-11-25" `
  --file ".\ROADMAP.md" `
  --folder ".\docs\design" `
  --input-root "." `
  --local-model "qwen2.5:14b" `
  --review-model "qwen3-coder:30b" `
  --context-window-tokens 32768 `
  --review-context-window-tokens 32768 `
  --protocol deep `
  --learning stage `
  --budget-usd 0 `
  --max-elapsed-seconds 7200 `
  --out ".\investigation-plan.json"
```

Planning performs zero model calls and zero network requests. It expands and
hashes root-confined file inputs, records URL requests without fetching them,
freezes expert snapshots, and prints the exact worst-case calls, searches,
pages, tokens, time, disk, data-egress classes, and cost. It does not prove that
the selected Ollama models are installed or fast enough. Inspect the plan
before execution.

The context values are real per-request native Ollama limits, not descriptive
metadata. Larger is not automatically better. Use the smallest value that
fits the source material and leaves both selected models on the intended
hardware. The runtime refuses a prompt before dispatch when the prompt plus
maximum output cannot fit the hash-bound context.

### Run, Observe, And Control It

```powershell
deepr expert investigate run .\investigation-plan.json -y

# In another terminal, use the run id printed by plan or run.
deepr expert investigate status <run-id>
deepr expert investigate inspect <run-id>
deepr expert investigate pause <run-id>
deepr expert investigate resume <run-id>
deepr expert investigate cancel <run-id>
```

`run` requires confirmation because it starts local model calls and public web
retrieval. Pause and cancellation take effect before the next dispatch. Resume
hash-checks completed artifacts and skips finished phases. Every phase and
reservation is recorded below the configured reports root. Raw model reasoning
is not requested or retained.

The first release supports only `--capacity local --budget-usd 0`. A nonzero
budget, plan-quota investigation, or API investigation fails before execution.
The desired `$10` API form is one total ceiling across every expert, checker,
synthesizer, retry, and learning call, not `$10` per expert. That form remains
gated until every child call shares canonical reservation and settlement.

### Understand The Result And Learning Labels

`inspect` shows the answer, every expert's contribution or typed absence,
disagreement, minority positions, uncertainty, next tests, the independent
check, usage, and staged learning. A completed run still says
`Semantic quality: unreviewed`. A local review model is a model-generated check,
not a human review and not proof that the answer is excellent.

With `--learning stage`, every expert gets two independent chances to learn:

1. The factual lane compiles only that expert's retrieved source pack. Peer
   messages, consensus, synthesis prose, and private revisions cannot become
   factual evidence. The model orders candidates by usefulness. Deterministic
   form enforcement retains at most five per expert before a separate verifier
   judges source support, target-domain relevance, deduplication, and temporal
   validity. Domain relevance is judged from the exact candidate statement,
   not borrowed from a source title, excerpt, query, or rationale. Word overlap
   never decides meaning. Uncertainty produces no write.
2. The perspective lane starts from that expert's final position. It can stage
   a hypothesis or theory, concept, stance, or original idea only when the
   checker marks its form, internal coherence, and testability `well_formed`.
   Each candidate retains rationale, uncertainty, assumptions, implications,
   expected observations, and disconfirming signals. A cited source is
   inspiration or context, never proof of truth or novelty. The checker cannot
   certify truth, importance, originality, or novelty, and absence of web
   support is not refutation.

One expert may receive ready writes while another produces a no-op or blocked
result. This is the truthful meaning of "they all learn": each expert gets its
own bounded research and proposal path, but Deepr never forces a mutation.
Staging writes no expert state.

Preview every selected expert and both channels as one preflight transaction:

```powershell
deepr expert investigate apply-learning <run-id> --dry-run --json
```

You may narrow the preview or apply:

```powershell
deepr expert investigate apply-learning <run-id> --expert "Temporal Knowledge Graphs" --facts --no-perspectives --dry-run --json
deepr expert investigate apply-learning <run-id> --no-facts --perspectives --dry-run --json
```

Only after the preflight succeeds, explicitly admit all selected writes:

```powershell
deepr expert investigate apply-learning <run-id> -y --json
```

The command hash-verifies the completed run and producer-owned artifact index,
preflights every selected envelope before any write, locks all selected experts,
and applies idempotently. Its record says `operator_confirmed_apply: true` and
`human_reviewed: false`. Applying a perspective does not make it factual, does
not verify truth or novelty, and does not advance factual knowledge freshness.
Blocked and no-op entries remain visible. A provenance-verified producer
`blocked` or `empty` envelope with no operations is a no-op and does not hide
ready lanes. An unexpectedly empty ready envelope or any other validation
failure blocks the complete selected transaction.

Run the `$0` structural contract evaluator separately:

```powershell
deepr eval investigation --json
```

It checks boundaries and artifact form, not answer meaning. Promotion still
requires held-out comparisons against a strongest single expert, the one-shot
consult, independent research, and the bounded discussion arm.

## Set A Hard Dollar Ceiling

For a strict current-shell ceiling on Windows PowerShell:

```powershell
$env:DEEPR_MAX_COST_PER_JOB = "10.00"
$env:DEEPR_MAX_COST_PER_DAY = "10.00"
$env:DEEPR_MAX_COST_PER_MONTH = "10.00"
$env:DEEPR_COST_TRACKING_STRICT = "1"
deepr costs show
deepr costs doctor
```

These environment limits are the authoritative cost-admission caps for the
currently enabled metered paths. The daily and monthly limits include earlier
ledger spend in the same periods, so the available amount can be less than
`$10`. Unsafe legacy metered expert paths remain disabled rather than escaping
the cap.

A budget is never spend permission. Remote and API request bodies must also
carry the exact booleans `allow_metered_api=true` and
`confirm_metered_cost=true`. CLI paid execution requires an interactive
confirmation, or the command's explicit noninteractive cost-confirmation flag.
Missing consent, finite pricing, reservation, or ledger settlement fails closed
before provider construction.

This is a current-period ceiling, not a lifetime wallet. The daily and monthly
windows reset. Deepr does not yet ship a reusable parent budget spanning an
arbitrary list of shell commands. Keep a paid council to one transaction with
`--budget 10`, or keep the period caps in place for the whole experiment and
stop before their reset boundary. Local `--budget 0` work remains the safest
way to prepare experts without consuming that allowance.

`deepr budget set 10` is a monthly approval policy. It is not a substitute for
the hard environment caps above. A command-level `--budget` is also a ceiling
for that one command, not a shared budget across an arbitrary shell script.

For the strongest no-bill posture, use explicit `--local --budget 0`. A
safety-eligible `--plan` path records `$0` in Deepr but consumes subscription
quota or credits, and Deepr cannot prove the vendor's final billing treatment.
An explicit plan selection never bypasses the auth, native-tool, or marginal-
cost gate.

The current API council meters only final synthesis. It reserves the complete
requested transaction ceiling, while the synthesis request is limited to 10
percent of that ceiling. With `--budget 10`, the transaction cannot exceed
`$10` and the one synthesis call cannot exceed `$1`. Stored expert perspectives
make no provider calls.

## 1. Prepare The Purpose Contracts Without Claiming Review

The repository includes strict, machine-prepared draft blueprints with real
acceptance cases. They are not human reviewed, operator attested, canonical, or
authoritative. Generate a zero-call preflight for each one:

```powershell
deepr expert blueprint "Temporal Knowledge Graphs" --from-file .\examples\expert_blueprints\temporal-knowledge-graphs.json --output .\tkg-blueprint-preflight.json
deepr expert blueprint "Digital Consciousness" --from-file .\examples\expert_blueprints\digital-consciousness.json --output .\digital-consciousness-blueprint-preflight.json
deepr expert blueprint "Model Context Protocol" --from-file .\examples\expert_blueprints\model-context-protocol.json --output .\mcp-blueprint-preflight.json
```

Preflight strictly parses and normalizes the draft, computes its semantic hash,
summarizes structural coverage, supplies review questions, and records zero
model calls, zero provider calls, zero network access, zero cost, no canonical
write, no semantic-quality verdict, no human-review claim, and no scope
authority. This is everything deterministic code can honestly conclude.

Edit the drafts if their mission or acceptance cases do not match your intended
decisions. Only after someone actually reviews them should that operator attest
that the review occurred:

```powershell
deepr expert blueprint "Temporal Knowledge Graphs" --from-file .\examples\expert_blueprints\temporal-knowledge-graphs.json --apply --attested-by operator
deepr expert blueprint "Digital Consciousness" --from-file .\examples\expert_blueprints\digital-consciousness.json --apply --attested-by operator
deepr expert blueprint "Model Context Protocol" --from-file .\examples\expert_blueprints\model-context-protocol.json --apply --attested-by operator
```

The resulting record says `operator_attested`, `identity_verified: false`, and
`human_authorship_claimed: false`. Deepr records the attestation but cannot
prove who reviewed the content or whether the review was good. Until that step,
keep using the draft and preflight labels.

## 2. Create The Local Expert Profiles

```powershell
deepr expert make "Temporal Knowledge Graphs" --local -d "Temporal graph representation, reasoning, evaluation, and agent memory"
deepr expert make "Digital Consciousness" --local -d "Machine consciousness evidence, theory, ethics, and governance"
deepr expert make "Model Context Protocol" --local -d "Versioned MCP interoperability, extensions, authorization, and security"
```

An operator-attested blueprint defines scope and evaluation intent. It does not
populate knowledge. A local profile creates the durable store without a
provider call.

## 3. Give Each Expert A Narrow Research Agenda

Start with a few high-value subscriptions instead of an unbounded curriculum:

```powershell
deepr expert subscribe "Temporal Knowledge Graphs" "Temporal knowledge graph agent memory, correction, and forgetting evaluation" --every 14 --budget 0.50
deepr expert subscribe "Temporal Knowledge Graphs" "Bitemporal semantics, event validity, and provenance-preserving replay" --every 30 --budget 0.50

deepr expert subscribe "Digital Consciousness" "Machine consciousness evaluation across competing theories" --every 30 --budget 0.50
deepr expert subscribe "Digital Consciousness" "Digital moral patienthood under empirical uncertainty" --every 30 --budget 0.50

deepr expert subscribe "Model Context Protocol" "Official MCP specification, release candidates, and final SEPs" --every 7 --budget 0.50
deepr expert subscribe "Model Context Protocol" "MCP authorization, transport security, Tasks, and extensions" --every 7 --budget 0.50
```

Subscription budgets are per-topic ceilings for a metered sync. They do not
spend on their own.

## 4. Build Verified Graph Candidates

Use current web context with a local model, compile source notes into claims,
and stage graph commits for review:

```powershell
deepr expert sync "Temporal Knowledge Graphs" --local --all --fresh-context --compile-claims --stage-compiled-claims --budget 0.50 -y --json
deepr expert sync "Digital Consciousness" --local --all --fresh-context --compile-claims --stage-compiled-claims --budget 0.50 -y --json
deepr expert sync "Model Context Protocol" --local --all --fresh-context --compile-claims --stage-compiled-claims --budget 0.50 -y --json
```

`--stage-compiled-claims` writes replayable compiler sidecars but does not apply
the graph commit. Review each reported envelope, then preview and apply it:

```powershell
deepr expert apply-graph-commit "Temporal Knowledge Graphs" .\path\reported-by-sync.json --dry-run --json
deepr expert apply-graph-commit "Temporal Knowledge Graphs" .\path\reported-by-sync.json -y --json
```

Repeat the apply command for operator-accepted envelopes belonging to the other two
experts. Omitting `--stage-compiled-claims` makes verified compiled sync apply
its graph commits directly, but staging is the better first-run posture.

The graph commit boundary can persist factual beliefs, typed edges, temporal
qualifiers, gaps, exploration agendas, hypotheses, concepts, stances, and
original ideas. The verifier supplies meaning. Deterministic code owns schema,
provenance, idempotency, and writes.

## 5. Run The Three Expert Council

Use a question that actually needs all three domains:

```powershell
deepr expert consult "How should an MCP-based network of persistent experts represent time-varying claims, preserve uncertainty about digital consciousness, and turn disagreements into source-backed research without treating discussion as graph evidence?" --expert "Temporal Knowledge Graphs" --expert "Digital Consciousness" --expert "Model Context Protocol" --local --budget 0 --output .\three-expert-council.json -y
```

This costs `$0` in Deepr and writes the full returned artifact only because
`--output` is explicit. The append-only consult trace is recorded separately.

An explicit plan alternative is:

```powershell
# Use a dedicated plan-only shell. Deepr refuses while this API credential is set.
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
deepr expert consult "Which cross-domain assumption should we test next?" --expert "Temporal Knowledge Graphs" --expert "Digital Consciousness" --expert "Model Context Protocol" --plan claude --budget 0 --output .\three-expert-council-plan.json -y
```

Claude Code is the current safety-eligible plan adapter. Before every call,
Deepr reads provider usage metadata and requires an explicit `extra usage off`
signal. It then uses safe mode, empty tool and MCP surfaces, no persistence, the
included `sonnet` alias, and no API credential. If any control is unavailable,
the consult stops before dispatch. Codex, OpenCode, Kiro, Grok, Antigravity,
and Copilot remain visible in `deepr capacity` but fail before dispatch because
Deepr cannot prove their tool confinement, provider/auth provenance, overage
posture, transcript side effects, or complete metered accounting.

Removing the environment variable in this dedicated shell does not delete the
stored Claude subscription login. If `ANTHROPIC_API_KEY` is present, Deepr
refuses before vendor dispatch rather than silently stripping it and guessing
which credential the CLI will use. `deepr capacity refresh-quota claude --json`
is a metadata-only `$0` check; `deepr capacity probe-plan claude --json` consumes
one subscription request only after the same live overage proof.

An optional metered synthesis, still under the global and transaction caps, is:

```powershell
deepr expert consult "Which cross-domain assumption should we test next?" --expert "Temporal Knowledge Graphs" --expert "Digital Consciousness" --expert "Model Context Protocol" --provider openai --model MODEL_FROM_THE_CURRENT_REGISTRY --budget 10 --output .\three-expert-council-api.json
```

Review the confirmation and exact model pricing before approving. Do not add
`-y` to a first paid run.

## 6. Turn Discussion Into Research, Not Facts

Read `DISAGREEMENTS`, `ASSUMPTIONS AND RISKS`, and `EXECUTION PLAN` in the saved
artifact. Select only questions that would materially improve an acceptance
case. Assign each question to one expert as a subscription, then sync again.

```powershell
deepr expert subscribe "Temporal Knowledge Graphs" "How should uncertain or open-ended validity intervals be represented and evaluated?" --every 30 --budget 0.50
deepr expert subscribe "Digital Consciousness" "Which observations discriminate functional continuity from theory-specific consciousness claims?" --every 30 --budget 0.50
deepr expert subscribe "Model Context Protocol" "How should a stateless MCP transport expose durable owner-bound expert work?" --every 7 --budget 0.50
```

Do not pass the council JSON to `expert absorb` as factual evidence. It is
synthetic proposal text. Research its questions against primary sources, then
let source notes, claim verification, and graph commits carry the result.

For failed or low-context consults, the existing trace path can produce review
candidates:

```powershell
deepr expert consult-traces --json
deepr expert monitor "Temporal Knowledge Graphs" --json
```

A successful consult is not automatically converted into a gap. That semantic
decision requires explicit review today.

## 7. Measure Whether The Experts Became Better

Regenerate memory cards, inspect provenance, and run the held-out blueprint
cases instead of judging improvement by graph size:

```powershell
deepr expert memory-card "Temporal Knowledge Graphs" --write
deepr expert memory-card "Digital Consciousness" --write
deepr expert memory-card "Model Context Protocol" --write

deepr eval expert-value "Temporal Knowledge Graphs" --template --output .\eval\tkg-review.json
```

After completing the frozen four-arm trials and adding operator semantic and
protocol attestations, independently verify every bound local artifact before
aggregation. Those attestations do not prove reviewer identity or human
authorship:

```powershell
deepr eval expert-value "Temporal Knowledge Graphs" --from-file .\eval\tkg-review.json --artifact-root .\eval\artifacts --output .\eval\tkg-report.json
```

The report output must remain outside the artifact root and cannot overwrite
the review workbook. This keeps the evidence tree read-only during independent
verification.

The evaluator reports separate correctness, factual support, stale reuse,
false support, uncertainty, transfer, cost, and reviewer effort. It does not
select a winner or change a default.

## Why The Pasted Recursive Improvement Script Is Unsafe To Copy

| Pasted instruction | Current reality |
|---|---|
| `capacity admit --local` | Invalid. Admit a tested local model with `capacity admit MODEL --task-class sync`, preferably from a saved eval. |
| `capacity admit --plan codex` | Invalid. `capacity admit-plan` records intent only, never overrides the adapter safety gate, and Codex execution is currently blocked. |
| `DEEPR_PREFERRED_CAPACITY=local,plan` | Not a Deepr setting. Use explicit `--local`, explicit `--plan`, or the admitted waterfall where supported. |
| `health-check --local` | Invalid. Health check is already a `$0` read-only command. |
| `reflect NAME --local` | Invalid. Reflection requires a report id and uses the scheduled capacity path where supported. |
| `propose-self-model NAME --local --evidence-from-recent-loops` | Invalid. It requires a concrete monitor proposal id. |
| `eval consult-quality` | Invalid. Use `expert review-consult-quality` or `expert judge-consult-quality`. |
| Repeated `--budget` flags keep the script under `$10` | False. Each flag scopes one command unless a command explicitly owns a parent run ceiling. |
| Absorb prior discussion to close the loop | Unsafe. Discussion is not external evidence. |
| `export-okf` provides rollback | False. OKF is a regenerated portability view, not canonical history or rollback. |
| Run the meta-expert on itself for recursion | Not a verified improvement loop. It can amplify synthetic errors without held-out evidence. |

The useful idea is controlled compounding: better evidence can produce better
factual state, while disciplined conjecture can produce better hypotheses and
research questions. Keeping those lanes distinct, then measuring later decision
value, is what separates improvement from recursive self-confirmation.

## What Remains Gated

The experimental local investigation now provides independent research, one
targeted blinded exchange, optional private revision, checking, synthesis, and
staged learning under a hash-bound `$0` envelope. That is still not a generic
multi-agent chat runtime, a quality claim, or permission to run indefinitely.
The structural evaluator and live pilots do not establish superiority.
One pilot exposed cross-domain negative transfer before any write was applied;
the follow-up relevance-gated pilot safely produced zero writes when
deduplication remained uncertain. A corrected deep pilot completed all 20 local
calls at `$0.00` and staged six candidate writes, but content audit rejected all
six because they were redundant, generic, or semantically overclaimed. None
were applied. The same run found low-relevance general-web sources in one
expert pack. Safe staging worked; answer and learning quality remain unproven.

Plan-quota investigation remains explicit-only future work. A paid runtime must
reserve one parent ceiling, meter every dispatch, enforce aggregate token and
context limits, support replay and resume, and keep all output proposal-only.
Its requested `$10` must be the maximum for the whole run, not a per-expert or
per-phase allowance. Explicit bulk apply works now. Automatic learning apply
remains a separate later gate.

This direction matches current evidence:

- [Diverse Evidence, Better Forecasts](https://arxiv.org/abs/2607.01661) is a
  July 2, 2026 preprint reporting that shared plus disjoint evidence reduces
  correlated errors and improves multi-agent forecasts over identical evidence.
  It supports expert-specific evidence lenses, but its reported gains are not
  yet a general result for every research task.
- [Demystifying Multi-Agent Debate](https://aclanthology.org/2026.findings-acl.1694/)
  reports that vanilla homogeneous debate can underperform simpler voting, while
  diverse initial positions and calibrated confidence are the useful levers.
- [Hear Both Sides](https://arxiv.org/abs/2603.20640) studies diversity-aware
  message retention and reports that broadcasting every message can add noise
  and redundancy. That supports targeted peer packets instead of transcript
  flooding.
- [Free-MAD](https://aclanthology.org/2026.findings-acl.1600/) reports a
  consensus-free single-round design with lower communication overhead and
  less conformity pressure. That supports ceilings and early stops, not a
  requirement to consume every allowed turn.
- [When Identity Skews Debate](https://aclanthology.org/2026.acl-long.650/)
  documents peer sycophancy and self-bias and evaluates response anonymization.
  A future Deepr runtime should preserve canonical lineage privately while
  testing blinded peer-content evaluation.
- [CascadeDebate](https://aclanthology.org/2026.acl-industry.93/) selectively
  invokes deliberation at uncertainty boundaries. That supports measured
  escalation instead of running a full panel for every question.
- [DYNA](https://arxiv.org/abs/2606.15778) is a June 2026 preprint that studies
  an external temporal graph as updatable episodic memory across three temporal
  recall tasks. It supports evaluating temporal structure, not treating model
  conversation as graph truth or assuming broad generalization from one study.
- [Graph-based Agent Memory](https://arxiv.org/abs/2602.05665) separates
  knowledge from experience, structured from unstructured memory, and the
  extraction, storage, retrieval, and evolution lifecycle. Deepr should measure
  retrieval and later-use quality across that lifecycle, not reward graph size.
- The 2026
  [Digital Consciousness Model](https://arxiv.org/abs/2601.17060) is an early
  probabilistic, multi-theory evidence framework. Its authors describe it as a
  first attempt and say the evidence about 2024 LLMs is not decisive. That
  supports pluralistic evidence tracking and calibrated uncertainty, not a
  binary consciousness label.
- [CTM-AI](https://arxiv.org/abs/2605.04097) is an April 2026 preprint showing
  that an architecture inspired by a formal consciousness model can be
  evaluated on ordinary capability benchmarks. Better task performance does
  not by itself establish phenomenal consciousness, so the blueprint tests
  that distinction explicitly.
- [Contemporary AI lacks the imagination to diverge or negate in science](https://arxiv.org/abs/2606.08251)
  reports convergence in scientific ideation and no spontaneous null
  hypotheses in its tested model classes. Deepr therefore asks for an explicit
  null hypothesis and preserves testable minority proposals instead of making
  consensus the objective.
- [On the Limits of LLM-as-Judge for Scientific Novelty Assessment](https://arxiv.org/abs/2606.12071)
  reports a systematic novelty mirage and weakens any case for automatic
  novelty certification. Deepr's checker is limited to form, internal
  coherence, and testability; `novelty_verified` remains false.
- The official [MCP 2026-07-28 release candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
  moves toward a stateless core and extension-based durable Tasks. As of
  2026-07-16 it is a release candidate, not the final specification.
- Final [SEP-2577](https://modelcontextprotocol.io/seps/2577-deprecate-roots-sampling-and-logging)
  deprecates core sampling, roots, and logging. Deepr should keep the host as
  orchestrator instead of building new expert recursion around server-initiated
  sampling.

See [bounded-expert-deliberation.md](design/bounded-expert-deliberation.md) for
the runtime acceptance contract and [expert-purpose-and-value-loop.md](design/expert-purpose-and-value-loop.md)
for the measurement boundary.
