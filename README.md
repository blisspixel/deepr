# Deepr

[![CI](https://github.com/blisspixel/deepr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/deepr/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.24.0-blue)](https://github.com/blisspixel/deepr/releases/tag/v2.24.0)

**Domain experts that remember, not another chat window.**

You bring the AI accounts, plan quotas, API keys, or local models you already
have. Deepr previews the route, runs each research task through the cheapest
capable path, and turns useful results into durable experts with beliefs, gaps,
contradictions, confidence, provenance, loop records, and handoff payloads that
humans or other agents can reuse later.

- Local Ollama is the true `$0` marginal-cost path for quality-tolerant expert
  setup, absorb, sync, eval, and local-context workflows.
- Explicit plan-quota CLIs run on prepaid or subscription capacity only after
  deterministic no-surprise-bills checks.
- Cloud APIs remain the strongest full research path when you provide keys and
  a budget ceiling.

A budget is a ceiling, not a target price. `--budget 3` means Deepr may spend
up to $3 for that job, stops before the ceiling when it can, and records every
settled cost in the append-only ledger.

Deepr is useful when research is infrastructure: recurring expert maintenance,
batch research, citable knowledge for coding agents, and durable domain roles
that stay current over time.

```bash
# Preview route and cost before spending.
deepr research "What bottlenecks could constrain NVIDIA Blackwell deployment?" --auto --dry-run

# Run a research job with a $3 budget ceiling.
deepr research "Will open-weight frontier models erode AI enterprise margins by 2027?" --auto --budget 3

# Consult a persistent expert at $0 through local synthesis.
deepr expert consult "What should this agentic harness improve next?" --local

# Keep an expert current with local model plus free retrieval context.
deepr expert sync "Platform Team Expert" --local --fresh-context -y

# Compile, verify, and apply graph commits instead of legacy absorb.
deepr expert sync "Platform Team Expert" --local --fresh-context --compile-claims -y

# Stage compiler sidecars without applying graph commits.
deepr expert sync "Platform Team Expert" --local --fresh-context --compile-claims --stage-compiled-claims -y
```

Multi-provider support includes OpenAI, Gemini, Grok, Anthropic, Azure, local
Ollama, and explicit plan-quota CLIs. Reports and expert state are local
artifacts you own. Deepr also exposes 32 MCP tools for agent hosts.

<p align="center">
  <img src="assets/dashboard.png" width="49%" alt="Dashboard - cost trends, job stats, activity feed" />
  <img src="assets/expert-hub.png" width="49%" alt="Expert Hub - persistent domain experts with knowledge tracking" />
</p>
<p align="center">
  <img src="assets/expert-profile.png" width="49%" alt="Expert Chat - agentic chat with slash commands and visible reasoning" />
  <img src="assets/models.png" width="49%" alt="Models and Benchmarks - provider comparison and quality rankings" />
</p>

## Why Deepr

If you need one report, a vendor chat product is easier. Deepr is for the cases
where research needs to be repeatable, budgeted, auditable, and reusable.

- **Batch research**: run many questions through previewed, budgeted routing
  instead of manually clicking deep research one question at a time.
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

Open a new terminal after install:

```bash
deepr init
deepr doctor
# Budget ceiling: spend at most $3 for this job.
deepr research "Your question here" --auto --budget 3
```

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
| API-backed research | Works with provider keys, preflight estimates, budget ceilings, and append-only cost settlement | [docs/FEATURES.md](docs/FEATURES.md), [docs/MODELS.md](docs/MODELS.md) |
| Local expert maintenance | Works through Ollama for local expert setup, absorb, sync, fresh/deep local context, eval, and scored admission | [docs/CAPACITY.md](docs/CAPACITY.md) |
| Explicit plan-quota execution | Works for selected expert sync, absorb, learn, consult, and probe commands behind auth-mode and no-surprise-bills checks | [docs/CAPACITY.md](docs/CAPACITY.md), [docs/design/plan-quota-cli-backends.md](docs/design/plan-quota-cli-backends.md) |
| Domain experts | Works for expert creation, chat, consult, beliefs, gaps, loop status, OKF export/import, self-model reads, monitor proposals, reviewed monitor promotion, and self-model update review and acceptance records | [docs/EXPERTS.md](docs/EXPERTS.md) |
| MCP | Works for local stdio and experimental HTTP/SSE with scoped keys, budgets, rate limits, audit logs, smoke checks, no-metered consult validation, and registration manifests | [mcp/README.md](mcp/README.md) |
| Web dashboard | Experimental but usable for reports, experts, costs, model views, and loop status | [docs/FEATURES.md](docs/FEATURES.md) |

Automatic routing to plan-quota CLIs is still conservative. Explicit `--plan`
is the works-now path. Auto-routing to plan capacity waits for trusted
remaining-quota observations and measured quality evidence.

## Core Workflows

### Research

```bash
deepr research "What changed in AI infrastructure economics this quarter?" --auto --explain
deepr research --auto --batch queries.txt --dry-run
deepr research "Analyze this corpus" --files docs/*.md --budget 5
```

Model names and prices move quickly. The registry under
`src/deepr/providers/registry.py` is the canonical source for pricing used by
estimates and settlement.

### Experts

```bash
deepr expert make "AI Policy Expert" -d "EU AI Act enforcement timeline" --learn --budget 5
deepr expert chat "AI Policy Expert" --budget 3
deepr expert consult "What should our agentic harness improve next?" --local
deepr eval consult --json
deepr expert self-model "AI Policy Expert" --json
deepr expert monitor "AI Policy Expert" --json
deepr expert review-consult-quality "AI Policy Expert" consult_abc123 --score uses_expert_state=5 --score surfaces_uncertainty=5 --score preserves_dissent=5 --score actionability=5 --score grounded_when_factual=5 --score original_thought=5 --reviewer operator --decision accept --target eval --apply
deepr expert promote-monitor "AI Policy Expert" meta_abc123 --target gap --apply
deepr expert propose-self-model "AI Policy Expert" meta_def456 --json
deepr expert accept-self-model "AI Policy Expert" ./data/self_model_updates/ai-policy/self_model_update_meta_def456_20260626_120000000000.json --outcome-evidence loop_run:loop_123 --reviewer operator --json
deepr expert memory-card "AI Policy Expert" --write
deepr expert semantic-recall "AI Policy Expert" "agentic guardrail evidence" --json
deepr expert loop-status "AI Policy Expert" --json
deepr expert export-okf "AI Policy Expert" ./okf/ai-policy
```

Learning is a processing loop, not passive RAG. Source material becomes atomic
beliefs, concepts, hypotheses, stance, provenance refs, temporal edges,
contradiction signals, gap backlogs, freshness watchlists, and regenerated
digest, memory-card, or handoff views. Generated reports, digests, `EXPERT.md`
memory cards, OKF bundles, and handoff payloads are derived views over
structured state.

`deepr expert sync --compile-claims` now runs budget-gated semantic extraction
and verification over source-note windows, builds a verified graph-commit
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

`deepr expert review-consult-quality` turns one review-ready consult trace case
into a `deepr-consult-quality-review-v1` artifact. Human or calibrated-model
scores own semantic judgment; Deepr only validates score shape, records the
review, enforces the acceptance policy, and can promote accepted cases into gap
or eval artifacts. This path costs `$0` and never commits beliefs.

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
documented. Metered-at-margin plan CLIs are billed per use and remain
explicit-only behind budget and cost-ledger gates.

### MCP and Agents

Deepr experts are consultable roles for host agents. An agent can list experts,
read a handoff, inspect loop state, run a one-expert or multi-expert consult,
use `deepr_query_expert` with explicit local or plan capacity for a no-metered
read-only compiled-context turn, or use API chat with an operator-approved
budget. API query chat supports OpenAI by default and explicit Anthropic
non-agentic turns through `provider=anthropic`. The host remains the
orchestrator; Deepr provides the verified knowledge layer.

```bash
deepr mcp serve
deepr mcp serve --http --host 127.0.0.1 --port 8765
deepr mcp smoke-http http://127.0.0.1:8765/mcp
deepr mcp validate-consult --json
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

Every metered path is supposed to estimate before dispatch and settle after
usage. Deepr has per-operation limits, daily and monthly caps, budget
reservations, anomaly checks, and an append-only cost ledger at
`data/costs/cost_ledger.jsonl`.

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

Stable today: core research commands, guided setup, cost controls, provider
routing with user keys, local report storage, expert profiles, CLI output modes,
and published schemas.

Experimental but usable: web dashboard, agentic expert chat, councils, skills,
MCP HTTP, scoped keys, remote-call audits, loop status, OKF interchange,
self-model reads, metacognitive monitor proposals, reviewed monitor promotion,
local execution, plan-quota execution, local evals, red-team metrics, and fleet
maintenance surfaces.

See [docs/SUPPORTED_SURFACE.md](docs/SUPPORTED_SURFACE.md) for the contract.

## Documentation

| Guide | Description |
|---|---|
| [Quick Start](docs/QUICK_START.md) | Installation and first research job |
| [Install](docs/INSTALL.md) | Platform setup and extras |
| [Features](docs/FEATURES.md) | Full command reference |
| [Capacity](docs/CAPACITY.md) | Local, plan-quota, metered API, scheduler, and no-surprise-bills behavior |
| [Experts](docs/EXPERTS.md) | Domain expert system |
| [Models](docs/MODELS.md) | Provider comparison and model selection |
| [Architecture](docs/ARCHITECTURE.md) | Technical architecture, security, budget protection |
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

The test suite has 6800+ tests (Python 3.12-3.14), with an 80% coverage gate.
Pre-commit and CI run ruff, mypy on strict islands, docs consistency checks,
file-size ratchets, and security/complexity ratchets.

Security issues should use GitHub private vulnerability reporting when
available. Do not post exploit details publicly.

## License

[Apache 2.0](LICENSE). Free to use, build on, fork, and share.

Maintainer: Nick Seal ([blisspixel](https://github.com/blisspixel)).

[GitHub](https://github.com/blisspixel/deepr) | [Issues](https://github.com/blisspixel/deepr/issues) | [Discussions](https://github.com/blisspixel/deepr/discussions)
