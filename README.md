# Deepr

[![CI](https://github.com/blisspixel/deepr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/deepr/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.36.2-blue)](https://github.com/blisspixel/deepr/releases/tag/v2.36.2)

**Domain experts that remember, not another chat window.**

You bring the AI accounts, plan quotas, API keys, or local models you already
have. Deepr previews explicit local, plan-quota, and bounded API paths, dispatches
only when capacity and cost can be proven, and turns useful results into durable
experts with beliefs, gaps, contradictions, confidence, provenance, loop
records, and handoff payloads that humans or other agents can reuse later.

- Local Ollama is the true `$0` marginal-cost path for quality-tolerant expert
  setup, absorb, sync, eval, and local-context workflows.
- Explicit non-metered plan-quota CLIs run on prepaid or subscription capacity
  only after deterministic no-surprise-bills checks. Metered-at-margin adapters
  remain visible but blocked until they have complete cost accounting.
- Cloud APIs remain the strongest bounded single-job research path when you
  provide keys, a budget ceiling, and a provider/model/tool envelope Deepr can
  price completely.

A budget is a ceiling, not a target price. `--budget 3` means Deepr may spend
up to $3 for that job, stops before the ceiling when it can, and records every
settled cost in the append-only ledger.
Saved dashboard benchmark artifacts remain readable. Live provider benchmark
execution is gated in v2.36 until it uses the shared durable research
transaction; unpriced or request-unbounded benchmark adapters fail closed.

Deepr is useful when research is infrastructure: recurring expert maintenance,
repeatable bounded research, citable knowledge for coding agents, and durable domain roles
that stay current over time.

Research is the input. Verified, current, operator-accepted expert state is the reusable product.
Better repeated decisions, measured on held-out cases and later outcomes, are
the result Deepr is trying to earn.

```bash
# Prepare an explicitly unreviewed purpose draft before collecting knowledge.
deepr expert blueprint "Platform Team Expert" --template --output expert-blueprint.json
# Edit it, then produce a $0 structural preflight with no review claim or authority.
deepr expert blueprint "Platform Team Expert" --from-file expert-blueprint.json --output expert-blueprint-preflight.json
# Only after actual review, record the operator's attestation.
deepr expert blueprint "Platform Team Expert" --from-file expert-blueprint.json --apply --attested-by operator

# Create, maintain, and consult the expert on local capacity.
deepr expert make "Platform Team Expert" --local -d "Platform engineering decisions"
deepr expert subscribe "Platform Team Expert" "agent harness reliability"
deepr expert sync "Platform Team Expert" --local --fresh-context -y
deepr expert consult "What should this agentic harness improve next?" --expert "Platform Team Expert" --local

# A council reads one stored-state packet per expert and runs one synthesis.
# It is one-shot: experts do not exchange turns or write one another's knowledge.
deepr expert consult "Which cross-domain assumption should we test?" --expert "Temporal Knowledge Graphs" --expert "Digital Consciousness" --expert "Model Context Protocol" --local --budget 0 --output three-expert-council.json -y

# Record what happened later. This never changes beliefs or routing automatically.
deepr expert record-outcome "Platform Team Expert" --decision-id harness-2026-07 --summary "Choose the next harness improvement" --result mixed --observation "Recovery improved, but reviewer time did not." --attested-by operator
deepr expert outcomes "Platform Team Expert"

# Prepare a frozen four-arm value review. This command does not run the arms.
deepr eval expert-value "Platform Team Expert" --template --output expert-value-review.json
# After arm execution and blinded operator semantic and protocol attestations, aggregate locally.
deepr eval expert-value "Platform Team Expert" --from-file expert-value-review.json --output expert-value-report.json
# Add --artifact-root to recompute every declared local SHA-256 digest first.
deepr eval expert-value "Platform Team Expert" --from-file expert-value-review.json --artifact-root ./eval-artifacts --output expert-value-verified.json

# Optional paid research starts with the exact hard request maximum.
deepr research "What bottlenecks could constrain NVIDIA Blackwell deployment?" --provider openai --model o4-mini-deep-research --preview
```

Multi-provider support includes OpenAI, Gemini, Grok, Anthropic, Azure, local
Ollama, and explicit plan-quota CLIs. Reports and expert state are local
artifacts you own. Deepr also exposes 36 MCP tools for agent hosts.

For a complete, copyable workflow for the Temporal Knowledge Graphs, Digital
Consciousness, and Model Context Protocol experts, including hard per-job,
daily, and monthly `$10` caps and the safe discussion-to-research boundary, see
[Three Expert Council And Learning Workflow](docs/THREE_EXPERT_COUNCIL.md).

<p align="center">
  <img src="assets/dashboard.png" width="49%" alt="Dashboard - cost trends, job stats, activity feed" />
  <img src="assets/expert-hub.png" width="49%" alt="Expert Hub - persistent domain experts with knowledge tracking" />
</p>
<p align="center">
  <img src="assets/expert-profile.png" width="49%" alt="Expert Profile - claims, evidence, gaps, and profile state" />
  <img src="assets/models.png" width="49%" alt="Models and Benchmarks - provider comparison and quality rankings" />
</p>

## Why Deepr

If you need one report, a vendor chat product is easier. Deepr is for the cases
where research needs to be repeatable, budgeted, auditable, and reusable.

- **Budgeted research**: run one fully priced provider request under the same
  hard envelope shown by preview. Metered batch execution remains gated until
  one durable parent reservation can cover every child request.
- **Persistent experts**: maintain named roles such as "AI Strategy Expert" or
  "Security Specialist" with beliefs, gaps, provenance, and loop history.
- **Agent handoffs**: let coding agents query a stable knowledge layer over MCP
  instead of relying on stale training data or session memory.
- **Current knowledge**: schedule quality-tolerant refreshes through local or
  prepaid capacity, and reserve metered APIs for work that needs them.
- **Auditability**: cost, routing, source trust, budget denials, and loop stops
  are recorded as structured artifacts.

The long-term direction is self-auditing understanding, not unbounded autonomy.
Experts should be able to explain what they know, what they do not know, what
changed, and what they should learn next. They do not get to authorize their own
spend, writes, or authority changes.

## Who Deepr Is For

Deepr fits builders, operators, researchers, and agent-host users who need
research to become durable local state instead of one-off chat transcripts.

- **Buyers and operators** who need budget ceilings, audit trails, and repeatable
  research workflows across multiple providers.
- **Builders** who want local-first expert maintenance, explicit plan-quota
  execution, and structured artifacts they can inspect or version.
- **Agent-host users** who want coding agents or MCP clients to query a current
  knowledge layer instead of relying on stale training data.

Deepr is not the shortest path for a casual one-off question. It is also not a
way to bypass provider terms, spend without explicit budgets, or let an agent
authorize its own writes, tools, or paid calls.

## Quick Start

**Windows PowerShell**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"
```

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash
```

These installers resolve the latest versioned wheel from GitHub Releases and
install it with pipx. If GitHub is unavailable or the release has no supported
wheel, they stop before changing an existing Deepr installation. Public PyPI
installation is not currently available.

Open a new terminal after install:

```bash
deepr init
deepr doctor
deepr expert blueprint "My Domain Expert" --template --output expert-blueprint.json
# Edit the mission, decision use cases, source policy, and acceptance cases.
deepr expert blueprint "My Domain Expert" --from-file expert-blueprint.json --output expert-blueprint-preflight.json
# Apply only after actual review; Deepr records but cannot verify the attestation.
deepr expert blueprint "My Domain Expert" --from-file expert-blueprint.json --apply --attested-by operator
deepr expert make "My Domain Expert" --local -d "The decisions this expert supports"
deepr expert subscribe "My Domain Expert" "The first topic to keep current"
deepr expert sync "My Domain Expert" --local --fresh-context -y
deepr expert consult "What should we decide next?" --expert "My Domain Expert" --local
```

This path needs no API key and never falls through to a paid provider. For one
bounded cloud research job, preview the exact provider/model request first and
then rerun it with an explicit `--budget` ceiling.

Install from source when developing:

```bash
git clone https://github.com/blisspixel/deepr
cd deepr
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
pip install -e ".[dev,full]"
```

For a global editable command instead of an activated venv:

```bash
pipx install -e .
```

Results are saved under the configured reports root, defaulting to
`data/reports/`. See [docs/QUICK_START.md](docs/QUICK_START.md) and
[docs/INSTALL.md](docs/INSTALL.md) for setup details.

## What Works Now

| Area | Status | Where to go |
|---|---|---|
| API-backed research | Single bounded jobs work for provider/model/tool combinations with complete finite pricing. Preview and dispatch use the same hard envelope. Automatic metered fallback, hosted file/vector context, and multi-call campaigns are gated in v2.36. | [docs/FEATURES.md](docs/FEATURES.md), [docs/MODELS.md](docs/MODELS.md) |
| Local expert maintenance | Works through Ollama for local expert setup, absorb, sync, fresh/deep local context, eval, and scored admission | [docs/CAPACITY.md](docs/CAPACITY.md) |
| Explicit plan-quota execution | Works for selected non-metered expert sync, sync-all, gap-fill, absorb, learn, consult, and probe commands behind auth-mode and no-surprise-bills checks | [docs/CAPACITY.md](docs/CAPACITY.md), [docs/design/plan-quota-cli-backends.md](docs/design/plan-quota-cli-backends.md) |
| Domain experts | Works for unreviewed blueprint drafts, zero-call structural preflight, operator-attested purpose contracts and outcome observations, local creation and maintenance, consult, beliefs, gaps, loop status, `$0` next-action guidance, OKF export/import, self-model reads, monitor proposals, reviewed monitor promotion, and self-model update review and acceptance records | [docs/EXPERTS.md](docs/EXPERTS.md) |
| MCP | Works for local stdio and experimental HTTP/SSE with scoped keys, budgets, rate limits, audit logs, smoke checks, no-metered one-shot consult validation, and registration manifests | [mcp/README.md](mcp/README.md) |
| A2A | Library and validation prototype only: Agent Card, in-memory tasks, consult mapping, and host validation exist, but no long-running serve command or A2A 1.0 conformance claim is shipped | [docs/SUPPORTED_SURFACE.md](docs/SUPPORTED_SURFACE.md) |
| Web dashboard | Experimental but usable for reports, experts, costs, model views, loop status, and OpenAI-backed research submission; use CLI workflows for other providers | [docs/FEATURES.md](docs/FEATURES.md) |

Job cancellation reports success only after the provider or queue transition,
cost reservation closure, and recorded provider-resource cleanup are confirmed. If any state cannot be confirmed,
the API, web dashboard, and CLI report a retryable failure instead of claiming
that the job was cancelled.

Automatic routing to plan-quota CLIs is still conservative. Explicit `--plan`
is the works-now path for selected non-metered expert workflows. Auto-routing
to plan capacity waits for operator admission and trusted remaining-quota
observations. Metered-at-margin Copilot is fleet-visible but fails closed before
execution until deterministic estimation, reservation, usage settlement, and
canonical cost-ledger support exist.

`deepr init --data-dir PATH` configures expert, report, and operational
runtime roots below one folder. That folder can be synced for sequential use
across devices. Setting `DEEPR_DATA_DIR` manually relocates experts and runtime
state, including the local queue at `queue/research_queue.db` below that root,
but does not override the separate report root. `DEEPR_QUEUE_DB_PATH` is the
explicit queue override. Stop Deepr services, use one writer at a time, and wait
for the sync provider to finish before switching devices. Concurrent
multi-device mutation is not shipped; the staged
event-journal design is documented in
[multi-device-expert-continuity.md](docs/design/multi-device-expert-continuity.md).

## Core Workflows

### Research

```bash
# Inspect the exact maximum before any provider call.
deepr research "What changed in AI infrastructure economics this quarter?" --provider openai --model o4-mini-deep-research --preview

# Run one bounded job. The budget is a hard ceiling.
deepr research "What changed in AI infrastructure economics this quarter?" --provider openai --model o4-mini-deep-research --budget 2

# Batch routing preview is $0; metered batch execution is gated in v2.36.
deepr research --auto --batch queries.txt --dry-run
```

Hosted file upload, file search, vector-store creation, metered multi-job
campaigns, dream-team research, and automatic cross-provider metered fallback
fail closed in v2.36 until their full storage or parent-run costs share the
durable reservation. Use local source packs, `expert make --local --files`, or
one bounded research job at a time.

Model names and prices move quickly. The registry under
`src/deepr/providers/registry.py` is the canonical source for pricing used by
estimates and settlement. Current Anthropic support includes `claude-sonnet-5`
for balanced chat/synthesis and `claude-opus-4-8` for higher-reasoning research;
Sonnet 5 is handled through the native Messages API with adaptive thinking and
no non-default sampling parameters. Deepr estimates Sonnet 5 with Anthropic's
standard post-intro token rates so budget checks do not understate future spend;
Anthropic's current docs list lower introductory pricing through 2026-08-31.

### Experts

```bash
# Start with an unreviewed draft and structural preflight.
deepr expert blueprint "AI Policy Expert" --template --output expert-blueprint.json
deepr expert blueprint "AI Policy Expert" --from-file expert-blueprint.json --output expert-blueprint-preflight.json
# Apply only after someone actually reviews the draft.
deepr expert blueprint "AI Policy Expert" --from-file expert-blueprint.json --apply --attested-by operator
deepr expert make "AI Policy Expert" --local -d "EU AI Act enforcement timeline"
deepr expert subscribe "AI Policy Expert" "EU AI Act enforcement timeline"
deepr expert sync "AI Policy Expert" --local --fresh-context -y
deepr expert consult "What should our agentic harness improve next?" --expert "AI Policy Expert" --local
deepr expert record-outcome "AI Policy Expert" --decision-id policy-review-2026 --summary "Choose the policy response" --result succeeded --observation "The reviewed response met the compliance deadline." --attested-by operator
deepr expert outcomes "AI Policy Expert" --json
deepr eval consult --json
deepr eval conversation --json
deepr eval deliberation --json
deepr eval hallucination-risks --json
deepr expert self-model "AI Policy Expert" --json
deepr expert next "AI Policy Expert"
deepr expert monitor "AI Policy Expert" --json
deepr expert review-consult-quality "AI Policy Expert" consult_abc123 --score uses_expert_state=5 --score surfaces_uncertainty=5 --score preserves_dissent=5 --score actionability=5 --score grounded_when_factual=5 --score original_thought=5 --reviewer operator --decision accept --target eval --apply
deepr expert judge-consult-quality "AI Policy Expert" consult_abc123 --local-judge-model qwen2.5 --target eval --json
deepr expert judge-consult-quality "AI Policy Expert" consult_abc123 --plan codex --plan-model gpt-5-mini --target eval --json
deepr expert promote-monitor "AI Policy Expert" meta_abc123 --target gap --apply
deepr expert propose-self-model "AI Policy Expert" meta_def456 --json
deepr expert accept-self-model "AI Policy Expert" ./data/self_model_updates/ai-policy/self_model_update_meta_def456_20260626_120000000000.json --outcome-evidence loop_run:loop_123 --reviewer operator --json
deepr expert memory-card "AI Policy Expert" --write
deepr expert semantic-recall "AI Policy Expert" "agentic guardrail evidence" --json
deepr expert semantic-recall "AI Policy Expert" "agentic guardrail evidence" --local-embedding-model nomic-embed-text --json
deepr expert refresh-semantic-recall "AI Policy Expert" --embedding-model local-test --embeddings-json ./belief-vectors.json --json
deepr expert refresh-semantic-recall "AI Policy Expert" --local-embedding-model nomic-embed-text --json
deepr expert loop-status "AI Policy Expert" --json
deepr expert export-okf "AI Policy Expert" ./okf/ai-policy
```

The draft and preflight are non-authoritative preparation artifacts, not
knowledge and not proof of review. Each applied revision is a complete
operator-attested scope snapshot with reviewer identity explicitly unverified
and no claim of human authorship. Outcome records use the same attestation
boundary for later decision observations. They are append-only and do not
automatically change beliefs, prompts, routing, spend, or authority. These lanes
close the product loop from intended use to observed value without pretending
that more stored material is proof of improvement.

`deepr eval expert-value NAME --template --output FILE` turns the latest
operator-attested blueprint into an intentionally incomplete longitudinal
review workbook. An operator supplies at least two frozen, hashed source worlds,
the complete fresh-research, static-history, compiled-expert, and
maintained-expert trial matrix, artifact hashes, costs, effort, rubric scores,
risk labels, semantic attestations, and a protocol attestation. Each
attestation explicitly denies verified identity and human authorship.
`--from-file` validates and aggregates that workbook into separate quality,
false-support, stale-memory, transfer, cost, effort, outcome, reproducible
paired-bootstrap uncertainty, and cost-only break-even measures. By default the
evaluator records the protocol's operator hash attestation and does not open
referenced files. `--artifact-root PATH` instead rejects absolute,
traversing, escaping, missing, conflicting, or mismatched references and
recomputes every SHA-256 digest inside that root. Neither mode makes model,
provider, or network calls. Reports write only to an explicit output path, emit
no superiority flag, select no winner, and change no default. Running the arms
is a separate capacity decision and can incur the costs recorded in the
workbook.

Learning is a processing loop, not passive RAG. Source material becomes atomic
beliefs, concepts, hypotheses, stance, provenance refs, temporal edges,
contradiction signals, gap backlogs, freshness watchlists, and regenerated
digest, memory-card, or handoff views. Generated reports, digests, `EXPERT.md`
memory cards, OKF bundles, and handoff payloads are derived views over
structured state.

`deepr expert next NAME` turns operator-attested-blueprint presence, current claims,
freshness, gaps,
contradictions, and durable loop outcomes into at most three argument-safe next
actions. Its JSON contract carries argv arrays instead of shell text, so names
and domains are never reinterpreted as commands. It is a `$0`, read-only
structural navigator, not a semantic maturity score and never a default-policy
change.

Compiled sync through `--local` or explicit `--plan <id>` capacity runs
budget-gated semantic extraction and verification over source-note windows,
builds a verified graph-commit
envelope, and applies that envelope instead of calling the legacy absorber. It
writes claim-extraction, claim-verification, graph-commit envelope, and
`graph_commit_apply_results` sidecars with prompt, schema, provider, model,
capacity, cost, source-window refs, read-only recall context, and
verifier-supplied temporal edge qualifiers when present. Sync cadence advances
only after an applied or already-applied graph commit result is durably
recorded. Use `--stage-compiled-claims` with `--compile-claims` when you need
the old no-write staging behavior; `--apply-compiled-claims` remains a
compatibility alias for the default apply behavior.

Read-side perspective deltas and belief explanations now surface those
temporal edge qualifiers as structured `temporal_edges` /
`temporal_contexts`, and `deepr eval continuity` checks that stored temporal
edge qualifiers are inspectable through the `$0` read and generated-digest
surfaces. Regenerated expert digests also render temporal edge qualifiers in a
dedicated derived section so humans can inspect valid time, observed time,
scope, and provenance without treating the Markdown view as canonical memory.

`deepr eval consult` runs a `$0` consult harness suite. It checks structural
contracts for expert routing, context packets, collaboration metadata,
no-metered capacity posture, dissent preservation, replayable traces, and
sanitized semantic quality review cases. It does not score answer meaning with
brittle lexical rules.

`deepr eval conversation` is the `$0`, no-write contract gate for the internal
durable conversation core. Its twelve frozen checks cover application handles,
owner isolation, serialized versions, idempotent replay, typed stops, bounded
frozen context, finite retention, content-free audit events, local-only
capacity, and proposal-only advice. It publishes a repeated-one-shot structural
comparison manifest but does not claim that multi-turn answers are semantically
better. The protocol-neutral SQLite core now passes restart, concurrency,
deletion, recovery, property, schema, and injected-executor tests without a
model. MCP start, continue, inspect, and close now ship for the explicit local
Ollama path with per-request authorization and loopback or authenticated HTTP
validation. A held-out comparison remains required before claiming that this
multi-turn path is semantically better than repeated one-shot queries.

`deepr eval deliberation` is the `$0`, frozen-fixture gate for future
expert-to-expert discussion. Its eleven checks cover bounded round lineage,
independent first positions, targeted challenges, dissent preservation, typed
stops, inert untrusted text, no fallback, and proposal-only authority. The
report is explicitly `unreviewed` for semantic quality, and no live multi-round
surface is enabled by this command.

`deepr expert review-consult-quality` turns one review-ready consult trace case
into a `deepr-consult-quality-review-v1` artifact. Human or calibrated-model
scores own semantic judgment; Deepr only validates score shape, records the
review, enforces the acceptance policy, and can promote accepted cases into gap
or eval artifacts. This path costs `$0` and never commits beliefs.
`deepr expert judge-consult-quality NAME TRACE_ID --local-judge-model MODEL`
runs that same review path with an explicit local Ollama judge. The command can
also use an explicit plan-quota judge with `--plan BACKEND` and optional
`--plan-model MODEL`. The judge sees the local trace answer at command time,
but Deepr stores only validated scores, labels, notes, and bounded judge
metadata in the review artifact. Plan judges consume subscription quota and
record `$0` Deepr cost metadata through the plan-quota ledger path. The premium
`--api-provider` implementation is gated in v2.36 pending the shared durable
transaction.
`deepr expert consult-quality-trends NAME` summarizes those reviewed artifacts
as `deepr-consult-quality-trend-v1`, including score trends and deterministic
prompt-regression candidates selected only from reviewer scores and review
status.
`deepr eval hallucination-risks` emits
`deepr-hallucination-risk-report-v1`, a `$0` no-write advisory report over
consult traces, consult-quality reviews, optional expert handoff artifacts, and
optional source-pack manifest artifacts. It routes hallucination-pattern risk
signals into review and regression selection without blocking answers or
writing beliefs. False-premise, template-order, and long-context middle-loss
labels come only from human or calibrated-model consult-quality review cases.
Traces with selected middle context now create review-only cases for
middle-context evidence preservation. Consult trace and consult-quality review
signals also produce read-only prompt-regression candidates for prompt-variant
selection. Consult traces preserve selected-order context-position metadata
without treating position alone as a semantic verdict.

### Capacity

```bash
deepr capacity
deepr capacity --probe
deepr capacity next --task-class sync --context-mode fresh --scheduled
deepr eval local --model qwen2.5:14b --judge-model qwen2.5:14b --save
deepr eval local-context --model qwen2.5:14b --judge-model qwen2.5:14b --save
deepr capacity admit --from-eval latest --task-class sync --yes
```

Local and non-metered plan-backed services must not create dollar cost inside
Deepr. They may consume hardware time, subscription quota, or external credits
that Deepr cannot prove, so explicit plan and CLI-judge paths stay opt-in and
documented. Metered-at-margin plan CLIs remain execution-blocked until their
estimation, reservation, settlement, and canonical ledger contracts are
complete. Copilot is visible/read-only capacity metadata in v2.36.

### MCP and Agents

Deepr experts are consultable roles for host agents. An agent can list experts,
read a handoff, inspect loop state, run a one-expert or multi-expert one-shot consult,
use `deepr_query_expert` with explicit local or plan capacity for a no-metered
read-only compiled-context turn. In v2.36, every standalone metered
`ExpertChatSession` dispatch fails closed, including CLI, browser, and
`deepr_query_expert backend=api` paths. Restoring metered chat requires a
durable reserve, dispatch-mark, and settlement lifecycle for every provider
call, hard output ceilings, auxiliary calls charged to the parent budget, and
serialized turns per session. API council synthesis is a separate bounded
surface and remains available with explicit approval. A current council member
contributes selected stored state, not a live model-generated turn. The host remains the
orchestrator; Deepr provides the verified knowledge layer.

MCP query and council consult are one-shot today. Four owner-bound MCP tools now
support a durable `$0` local conversation with one frozen expert snapshot:
start, continue, inspect, and close. That is not a multi-expert deliberation.
Live expert-to-expert rounds and a long-running A2A service remain gated on
held-out quality, aggregate token and context enforcement, replay, resume, and
A2A conformance. See
[remote-expert-conversations.md](docs/design/remote-expert-conversations.md).

A deeper evidence-first investigation that accepts a topic plus inline text,
URLs, files, and folders is planned but not shipped. The accepted plan freezes
each expert, performs independent research first, allows at most one targeted
cross-examination round, checks and synthesizes with preserved dissent, and
stages only source-verified learning. One parent envelope covers the entire
roster, so a `$10` limit means `$10` total. See
[evidence-first-expert-investigations.md](docs/design/evidence-first-expert-investigations.md).

```bash
deepr mcp serve
deepr mcp serve --http --host 127.0.0.1 --port 8765
deepr mcp smoke-http http://127.0.0.1:8765/mcp
deepr mcp validate-consult --json
deepr capacity validate-fleet --backend codex --backend claude --backend grok --backend antigravity --expert "AI Agent Harnesses" --json
deepr mcp validate-consult http://127.0.0.1:8765/mcp --auth-token "$DEEPR_MCP_KEY" --json
```

API consult synthesis can be pinned to `provider=openai|anthropic` and a model
when the caller supplies a positive budget. Local and plan modes remain the
no-metered path for validation and routine agent handoff tests.

`deepr mcp validate-consult` proves the external-agent consult contract without
metered fallback. With no URL it runs a deterministic offline fixture. With
`--live` it exercises local or explicit plan capacity in-process. With a URL it
calls the HTTP MCP endpoint and validates `deepr_consult_experts`,
`deepr-consult-v1`, `deepr-expert-collaboration-v1`, trace linkage, cost fields,
capacity no-fallback posture, dissent preservation, host action boundaries, and
secret redaction.

`deepr capacity validate-fleet` is the plan-fleet health check for operator
machines. It fans out selected plan CLI transport probes, records quota
observations, then validates the no-metered consult contract only for
transports that succeeded. It is not an auto-routing shortcut and does not
score answer meaning.

See [mcp/README.md](mcp/README.md) and
[docs/MCP_AGENT_TEST_GUIDE.md](docs/MCP_AGENT_TEST_GUIDE.md).

## Agentic Balance

Deepr deliberately separates workflow control from model judgment.

- Deterministic code owns spend, budget reservations, cost settlement, quota
  gates, auth-mode checks, schema validation, durable writes, locks, typed stop
  reasons, and human-review gates.
- Model judgment owns meaning: extraction, synthesis, contradiction, grounding,
  gap selection, and narrative quality.
- Cheap lexical or structural checks may route work, but they must not conclude
  semantic truth.
- Original ideas, hypotheses, and stances are first-class expert state. They
  need origin, rationale, uncertainty, and disconfirming signals, not an online
  source requirement. They must not masquerade as verified external facts.
- Self-model updates must be proposals with evidence, verifier results,
  accepted-record gates, and explicit outcome evidence before they affect a
  learning transaction. They do not grant new authority.
- The research-processing compiler starts with deterministic source snapshots,
  source notes, content hashes, prompt/schema versions, explicit
  `--compile-claims` extraction, verification, graph-commit envelopes, durable
  graph-commit apply results, and `--stage-compiled-claims` no-write staging
  when requested. Deterministic code validates temporal edge qualifier shape
  and ISO date fields, while leaving support, contradiction, deduplication,
  temporal scope, and semantic edges to calibrated model judgment.

This boundary is tracked in
[docs/plans/AGENTIC_BALANCE.md](docs/plans/AGENTIC_BALANCE.md) and the active
order of operations in [ROADMAP.md](ROADMAP.md).

## Cost Controls

Bounded single-job provider research and paid synchronous planning reserve cost
before dispatch and settle after usage. Research admission coordinates REST,
web, direct CLI, MCP, and internal single-job orchestrator processes through
durable maximum holds. Ambiguous provider outcomes settle conservatively and
are not automatically replayed. Deepr also has per-operation limits, daily and monthly
caps, anomaly checks, and an append-only cost ledger at
`data/costs/cost_ledger.jsonl`. See
[research-cost-reservations.md](docs/design/research-cost-reservations.md).

Defaults favor owned capacity: local `$0` backends first, then explicit
plan-quota capacity where supported. Metered APIs are explicit premium paths;
Deepr does not automatically fall through to another paid provider in v2.36.
Image generation follows the same rule:
`DEEPR_LOCAL_IMAGE_URL` is the only portrait provider auto-selected by default.
OpenAI, Gemini, and xAI remain recognized explicit provider choices, but paid
portrait dispatch fails closed in v2.36 pending the shared durable transaction.
Set `DEEPR_LOCAL_IMAGE_URL` and pass `--provider local` for the shipped path.
Existing portraits are not regenerated by default. Generated portraits live
under the configured runtime data root, and forced regeneration archives the
previous image before replacement.

In v2.36, unsafe metered expert lifecycle entry points fail closed while their
shared durable transaction is completed. This includes nonlocal `expert make`
and `--learn`, API curriculum `expert plan`, `expert resume`, normal metered
`expert reflect` and MCP `deepr_reflect`, provider-backed `expert refresh` and
`--synthesize`, API `fill-gaps`, explicit API sync and sync-all, paid portraits,
API consult-quality judging, live provider benchmarks, and paid
`deepr eval calibrate --corpus`. Use local, scheduled, dry-run, history-only,
or explicit plan-quota paths where available; `$0`
`deepr eval calibrate --from` remains available.
`deepr expert make --local` is the provider-free profile setup path.
Hosted file/vector context and metered multi-call research also fail closed.
Their `$0` previews remain available, but batch, campaign, team, and prepared
campaign execution require one durable parent reservation before re-enablement.
Legacy metered `deepr check`, `deepr make docs`, `deepr make strategy`, and
`deepr agentic research` also fail before provider construction until they use
the shared durable call transaction.

```bash
deepr budget set 5
deepr costs show
deepr costs doctor
deepr research --auto --batch queries.txt --dry-run
```

Set `DEEPR_COST_TRACKING_STRICT=1` to fail fast when cost events cannot be
persisted. Provider prompt-cache controls remain planned until TTL, cache-key,
and pre-warm estimators are explicit and budget-gated. See
[docs/CAPACITY.md](docs/CAPACITY.md#costing-deep-dive) for provider-specific
cost buckets such as cached tokens, server-side tools, batch modifiers, and
provider-returned exact cost settlement.

## Stable vs Experimental

Stable today: bounded single-job research for supported provider/model/tool
envelopes, guided setup, cost controls, provider selection with user keys,
local report storage, expert profiles, CLI output modes, and published schemas.

Experimental but usable: web dashboard, councils, skills,
MCP HTTP, scoped keys, remote-call audits, loop status, OKF interchange,
self-model reads, metacognitive monitor proposals, reviewed monitor promotion,
local execution, plan-quota execution, local evals, red-team metrics, and fleet
maintenance surfaces.

Standalone metered expert chat is gated in v2.36. Local and explicit plan
`deepr_query_expert` read-only turns remain available, and no metered chat live
validation is claimed for this release.

See [docs/SUPPORTED_SURFACE.md](docs/SUPPORTED_SURFACE.md) for the contract.

## Documentation

| Guide | Description |
|---|---|
| [Quick Start](docs/QUICK_START.md) | Installation and first research job |
| [Install](docs/INSTALL.md) | Platform setup and extras |
| [Features](docs/FEATURES.md) | Full command reference |
| [Capacity](docs/CAPACITY.md) | Local, plan-quota, metered API, scheduler, and no-surprise-bills behavior |
| [Experts](docs/EXPERTS.md) | Domain expert system |
| [Three Expert Council](docs/THREE_EXPERT_COUNCIL.md) | Three reviewed experts, one-shot council, verified graph learning, and a strict `$10` cap |
| [Models](docs/MODELS.md) | Provider comparison and model selection |
| [Architecture](docs/ARCHITECTURE.md) | Technical architecture, security, budget protection |
| [Security Threat Model](docs/security/THREAT_MODEL.md) | Trust boundaries, attacker stories, mitigations, and severity calibration |
| [MCP Integration](mcp/README.md) | MCP server setup and agent integration |
| [Agentic Balance](docs/plans/AGENTIC_BALANCE.md) | Workflow vs agent boundary |
| [Supported Surface](docs/SUPPORTED_SURFACE.md) | Stable, experimental, planned, and export guarantees |
| [Changelog](docs/CHANGELOG.md) | Release history |
| [Roadmap](ROADMAP.md) | Active development order |

## Requirements

- Python 3.12+ (tested on 3.12-3.14)
- At least one usable capacity source:
  - local Ollama for `$0` expert maintenance after evaluation and admission
  - provider API key for full API-backed research
  - explicit plan-quota CLI for selected expert workflows
- Optional Node.js 18+ for web dashboard development

## Project Notes

The test suite has 8000+ tests (Python 3.12-3.14), with an 80% coverage gate.
Pre-commit and CI run ruff, mypy on strict islands, docs consistency checks,
file-size ratchets, and security/complexity ratchets.

Security issues should use GitHub private vulnerability reporting when
available. Do not post exploit details publicly.

## License

[Apache 2.0](LICENSE). Free to use, build on, fork, and share.

Maintainer: Nick Seal ([blisspixel](https://github.com/blisspixel)).

[GitHub](https://github.com/blisspixel/deepr) | [Issues](https://github.com/blisspixel/deepr/issues) | [Discussions](https://github.com/blisspixel/deepr/discussions)
