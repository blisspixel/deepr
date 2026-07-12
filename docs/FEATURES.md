# Deepr Features Guide

Complete guide to Deepr features (continuously updated).

## Table of Contents

- [Setup and Capacity](#setup-and-capacity)
- [Web Dashboard](#web-dashboard)
- [Semantic Commands](#semantic-commands)
- [Context Discovery](#context-discovery)
- [Research Operations](#research-operations)
- [Real-Time Progress](#real-time-progress)
- [Research Observability](#research-observability)
- [Expert System](#expert-system)
- [Provider Intelligence](#provider-intelligence)
- [Vector Store Management](#vector-store-management)
- [Cost Management](#cost-management)
- [Queue Operations](#queue-operations)
- [Configuration](#configuration)
- [Analytics](#analytics)
- [Export and Integration](#export-and-integration)

## Web Dashboard

A local web interface for managing research operations visually. Built with React, TypeScript, Vite, and Tailwind CSS. 12 pages with code-split routing.

### Starting the Dashboard

```bash
pip install -e ".[web]"
deepr web
# Open http://localhost:5000
```

### Pages

**Overview** - Landing page with active jobs, recent activity feed, spending summary, and system health status.

**Research Studio** - Submit one bounded OpenAI background research request with an o3/o4-mini model picker, priority, and web search toggle. Compatibility choices for check, learn, team, and docs remain visible but fail closed before provider work in v2.36 because their legacy or multi-call transactions are incomplete. The form checks OpenAI readiness and pauses submission when provider configuration or cost estimation is unavailable. Prompt and scalar configuration drafts are validated and restored from session-scoped browser storage, with visible saved, restored, invalid, and unavailable states plus explicit clearing. A saved draft is preserved until the user explicitly accepts a different URL-prefilled prompt. Uploaded file names and contents are never persisted. The Context Files selector retains local validation, but provider file submission is gated in v2.36 before provider work until storage lifecycle costs share the research reservation. Ctrl+Enter / Cmd+Enter submits only after the same readiness and budget checks as the button. Request-specific cost estimation appears as you type. Use CLI workflows for Gemini, xAI, local, and plan-quota capacity. Supports pre-filled prompts via URL query parameter.

**Research Live** - Real-time progress tracking for running jobs via Socket.IO. The browser starts with reliable HTTP polling and upgrades to WebSocket when supported. A background server poller checks the provider API every 15 seconds. Completed jobs show enriched summary with cost, tokens, model, completion date, and content preview.

**Results Library** - Browse and search completed research with sorting (date, cost, model). Result cards and pagination are semantic keyboard-accessible links and controls. Paginated grid view (12 per page). Total result count in header.

**Result Detail** - Full markdown report viewer with citation sidebar showing source URLs and snippets. Copy-to-clipboard button for the full report content. Export dropdown for downloading results.

**Expert Hub** - List all domain experts with document counts, finding counts, knowledge gaps, and cost stats. Search and sort controls. Navigate to individual expert profiles.

**Expert Profile** - Seven tabs: Chat (the interface remains visible, but metered streaming and slash-command execution fail closed in v2.36; use explicit local or plan query and consult surfaces), Claims (tracked assertions with confidence scores and source provenance), Knowledge Gaps (view gaps with EV/cost priority), Decisions (reasoning audit trail with rationale and alternatives), History (learning timeline with costs), Skills (install/remove domain-specific capability packages), and Conversations (browse stored sessions read-only; metered resume is gated). Each secondary view distinguishes a retrieval failure from a legitimate empty state and offers a scoped retry without hiding the loaded profile.

**Cost Intelligence** - Append-only ledger spending trends over configurable time ranges (7/30/90 days), per-model cost breakdown with charts, budget limit controls with debounced sliders, all-operation ledger total, and queue completion progress. The scope note explains that imported or demo result costs do not create ledger spend and provider billing remains authoritative.

**Models & Benchmarks** - Model registry browser with provider grouping, saved benchmark results with quality rankings by tier (chat/news/research), quality charts, dry-run estimates, retained historical output, benchmark file selection, and routing configuration display. Available-only filtering requires verified provider configuration and fails closed when readiness is unavailable. All live provider validation, evaluation, and judge dispatch is gated in v2.36, including direct script execution; a larger estimate cap or approval does not unlock it.

**Trace Explorer** - Inspect research execution traces. View span hierarchy with timing, cost attribution, token counts, and model info for each operation. The collapsible decision sidebar shows the reasoning audit trail, while scoped warnings and retries preserve trace data when temporal findings or decision evidence fail independently.

**Help** - API key setup guide with provider links, CLI quick reference with common commands, model tier explanations (research/news/chat), getting-started walkthrough, and the running package version.

**Settings** - Theme selection (light/dark/system), default model, web search toggle, budget limit configuration, environment info (provider, queue, storage, API key status), and demo data loader for populating the UI with sample data.

### Keyboard Shortcuts

- **Ctrl+K** - Open command palette for quick navigation to any page
- **Ctrl+Enter** / **Cmd+Enter** - Submit research from the Research Studio textarea
- Theme cycles through light, dark, and system modes via the header button

### Technical Details

- Code-split routing: each page loads independently via React.lazy and Suspense
- Real-time updates: Socket.IO with Flask-SocketIO backend push for job events, using polling first and WebSocket upgrade when supported; same-origin connections follow the actual CLI host and port, while cross-origin clients require `DEEPR_CORS_ORIGINS`
- Background poller: daemon thread checks provider API every 15s for PROCESSING jobs
- State management: Zustand for UI state, React Query for server data with automatic cache invalidation on WebSocket events
- Component library: Radix UI primitives (shadcn/ui pattern) with Tailwind CSS
- Loading states: skeleton components (CardGridSkeleton, DetailSkeleton, FormSkeleton) instead of spinners
- Charts: Recharts for cost trends, model breakdown, and utilization
- Accessibility: skip-to-content link, mobile hamburger navigation via Sheet component
- FOUC prevention: critical CSS inlined in index.html

## Semantic Commands

Deepr uses intent-based commands that express what you want to accomplish:

### Research

```bash
# Preview one exact bounded request
deepr research "Your research question" --provider openai --model o4-mini-deep-research --preview

# Specify provider and model
deepr research "Question" --provider openai --model o3-deep-research

# Company site capture without provider handoff
deepr research company "Company Name" "https://company.com" --scrape-only

# Preview the exact maximum without spending
deepr research "Question" --provider openai --model o4-mini-deep-research --preview
```

Hosted file upload, scrape-to-provider handoff, file search, and vector-store
attachment are gated in v2.36 until upload, indexing, retention, retrieval, and
cleanup costs share the same durable reservation. Local expert source files and
local source packs remain available.

### Fact Verification

The legacy metered `deepr check` completion path is gated in v2.36 because its
retry loop does not yet use the shared reserve, dispatch-mark, output-ceiling,
and settlement transaction. Use one bounded `deepr research` job or a local or
plan expert consult.

### Documentation Generation

The legacy metered `deepr make docs` path is gated in v2.36 until its provider
call uses durable admission and canonical settlement. Existing reports remain
available as local source material.

### Strategic Analysis

The legacy metered `deepr make strategy` path is gated by the same transaction
requirement.

### Multi-Phase Learning

Metered `deepr learn` is gated because it is a multi-call campaign. For durable
expert learning, use `expert sync` or `expert absorb` with local or explicit
plan capacity.

### Team Analysis

Metered `deepr team` is gated until every perspective and synthesis call belongs
to one durable parent reservation. Use bounded expert councils with local or
explicit plan synthesis.

## Context Discovery

Find and reuse prior research to avoid redundant work and build on existing knowledge.

### Search Prior Research

```bash
# Search using a durably budgeted semantic embedding plus keyword matching
deepr search query "kubernetes deployment patterns"

# Use only the local keyword index with no model call or metered spend
deepr search query "kubernetes deployment patterns" --keyword-only

# More results with lower threshold
deepr search query "AWS security" --top 10 --threshold 0.6

# JSON output for scripting
deepr search query "machine learning" --json
```

### Index Reports

```bash
# Index new reports with durably admitted, ledgered embeddings
deepr search index

# Force re-index all reports
deepr search index --force

# View index statistics
deepr search stats

# Clear the index
deepr search clear
```

### Use Prior Research as Context

When submitting new research, Deepr automatically detects related prior research
through the local keyword index. Pre-confirmation discovery never creates a
metered embedding request:

```bash
# Automatic detection (shown before confirmation)
deepr research submit "kubernetes best practices"
# Output: "Related prior research found (2): ..."

# Skip automatic detection
deepr research submit "k8s" --no-context-discovery

# Explicitly include prior research as context
deepr research submit "update k8s findings" --context abc123

# Use with -y to skip confirmation
deepr research submit "follow-up research" --context abc123 -y
```

**Stale Context Warnings:** When using `--context`, Deepr warns if the prior research is older than 30 days. Use `-y` to skip the confirmation.

## Research Operations

### Single Research Jobs

Submit individual deep research queries using the `run` command group:

```bash
# Focus mode (quick research)
deepr run focus "Your research question" --yes

# Documentation mode
deepr run docs "Document the authentication flow" --yes

# Choose model
deepr run focus "Question" --model o3-deep-research --yes
```

`--preview` on the primary `deepr research` command reports the same hard
request envelope used for admission. Automatic cross-provider metered fallback
is disabled, so a failed attempt never silently spends through another provider.

**Available models:**
- `openai/o3-deep-research` (high-quality deep research)
- `openai/o4-mini-deep-research` (alternative deep research profile)

### Checking Results

```bash
# Get results from jobs command
deepr jobs get <job-id>

# List all jobs
deepr jobs list

# Filter by status
deepr jobs list --status completed

# Check job status
deepr jobs status <job-id>

# Cancel a job
deepr jobs cancel <job-id>
```

### Automatic Prompt Refinement

Always-on optimization for all queries:

```bash
# Enable in .env
DEEPR_AUTO_REFINE=true
```

**What it adds:**
- Temporal context (adds current date for recency)
- Structured deliverables
- Scope clarification
- Missing context detection

### Multi-Phase Research

Plan and review adaptive campaigns without dispatching them:

```bash
# Plan and review
deepr prep plan "Research goal" --topics 3
deepr prep review
```

Metered `prep execute`, `prep continue`, `prep auto`, auto-batch, legacy
`run project`, and legacy `run team` execution are gated in v2.36. They require
one durable parent reservation that covers every nested call before they can be
re-enabled. Submit bounded research jobs one at a time meanwhile.

## Real-Time Progress

Track long-running research operations through their durable job status.

### Progress Tracking

```bash
# Read the current durable status
deepr jobs status abc123

# Open the dashboard and follow an active job
deepr web
```

The Research Live dashboard polls while a job is `queued` or `processing` and
stops when it reaches `completed`, `failed`, or `cancelled`. Deepr does not
invent percentage completion for providers that expose only lifecycle status.

## Research Observability

Request research-path evidence on a direct research run.

### Trace Commands

```bash
# Explain task routing and execution after the run
deepr research "Question" --explain

# Show the execution timeline after the run
deepr research "Question" --timeline

# Include the full trace in the completed run output
deepr research "Question" --full-trace
```

### Understanding Traces

**--explain:** Shows the task hierarchy, selected model, cost, and available
decision evidence.

**--timeline:** Shows the completed task sequence, status, duration, and cost.

**--full-trace:** Includes the complete available execution trace. These flags
apply to the direct `research` command; there is no separate `research trace`
subcommand for a queued job.

## Provider Intelligence

Monitor and optimize provider performance.

### Provider Status

```bash
# View all providers with health, circuit breaker state, auto-disabled status
deepr providers status

# List available providers and models
deepr providers list
```

### Benchmarking

```bash
# View historical benchmark data
deepr providers benchmark --history

# Preview model-eval work without provider dispatch
deepr eval new --dry-run --tier all
```

Live provider benchmark execution is gated in v2.36 until each request uses the
shared durable reserve, dispatch-mark, settlement, and canonical-ledger
transaction. Historical and dry-run views remain available.

### Auto-Disable & Exploration

Deepr records provider health, latency percentiles, and success metrics for
read-only inspection. Automatic cross-provider metered fallback and exploratory
dispatch are gated in v2.36 because each attempt needs its own approved
reservation.

View disabled providers with `deepr providers status`.

## Expert System

Create and interact with domain experts that can answer questions from uploaded documents.

### Create Expert

```bash
# Create a local expert from documents
deepr expert make "Azure Architect" --local --files docs/*.md

# Create a local-only expert profile with no provider API calls
deepr expert make "UI Experience Expert" --local --description "UI/UX for agentic research tools"

# With description and local seed files
deepr expert make "Supply Chain Expert" --local --files *.md --description "Logistics and supply chain domain"
```

Nonlocal profile setup and `--learn` fail closed in v2.36 pending one shared
durable parent-run budget transaction that prices hosted storage and every
nested call. Use `--local` for provider-free profile setup, then local or
explicit plan-quota maintenance.

### Preview Curriculum

API curriculum `expert plan` is gated in v2.36. Use
`deepr expert next NAME --json` for a `$0` structural next-action plan until
curriculum generation uses
the shared durable run-budget transaction.

### Manage Experts

```bash
# List all experts
deepr expert list

# Get expert details
deepr expert info "Azure Architect"

# Delete expert
deepr expert delete "Azure Architect" --yes
```

### Consult an Expert

```bash
deepr expert consult "What should we verify next?" --experts "Azure Architect" --local
deepr expert consult "Which assumption is weakest?" --experts "Azure Architect" --plan codex
```

Standalone metered expert chat is gated in v2.36. Local and explicit plan MCP
query and bounded consult surfaces remain available.

### Gated Agentic Chat Design

The disabled interactive design includes slash commands, chat modes, and
research triggers. CLI, web, and MCP API chat fail before provider dispatch in
v2.36; the capabilities below do not authorize metered execution.

**Chat Modes** control how the expert responds:

```bash
# In chat, switch modes with slash commands:
/ask        # Quick answers, KB-only tools
/research   # Default - all tools available
/advise     # Structured consulting-style recommendations
/focus      # Always-on chain-of-thought reasoning
```

**Slash Commands** (27 total, organized by category):

| Category | Commands |
|----------|----------|
| Mode | `/ask`, `/research`, `/advise`, `/focus`, `/mode [name]` |
| Session | `/clear`, `/compact`, `/remember <text>`, `/forget <idx>`, `/memories`, `/new` |
| Reasoning | `/trace`, `/why`, `/decisions`, `/thinking [on/off]` |
| Control | `/model [name]`, `/tools`, `/effort [low/med/high]`, `/budget [amount]` |
| Management | `/save [name]`, `/load <id>`, `/export [md/json]`, `/council <query>`, `/plan <query>` |
| Utility | `/help [cmd]`, `/status`, `/quit` |

Use `/` prefix in web, `\` prefix in CLI.

**Context Compaction** keeps sessions usable over long conversations:

```bash
/compact           # Summarize earlier messages, keep recent context
```

The system also auto-suggests compaction after 30+ messages.

**Expert Council** consults multiple experts on cross-domain questions:

```bash
/council "How will AI regulation affect our cloud architecture?"
deepr expert consult "How should this agentic harness improve next?" --local
deepr expert consult "What changed in plan-quota capacity?" --plan grok --json
```

Selects relevant experts, queries each in parallel, synthesizes agreements and disagreements.
The CLI form emits a versioned `deepr-consult-v1` artifact with `--json`.
Explicitly approved API council synthesis uses its separate bounded cost
contract. `--local` and `--plan <id>` use owned or explicit plan-quota synthesis
and disable live metered expert fallback when stored belief context is missing.
The MCP result also exposes `structuredContent` for JSON-object clients while
retaining text JSON for older clients.
Each run appends a local `deepr-consult-trace-v1` record with input, selected
context metadata, capacity posture, checks run, and synthesis failure events.
`deepr expert consult-traces` reviews those local records and emits sanitized
`deepr-consult-trace-candidates-v1` gap/eval candidates for failed or
low-context consults. Candidate payloads include
`deepr-consult-quality-eval-case-v1` semantic review packets with rubric
dimensions for a human or calibrated model judge. They are `$0`, read-only,
non-verdict artifacts and cannot commit beliefs.
`deepr expert review-consult-quality NAME TRACE_ID` records reviewed rubric
scores as a `deepr-consult-quality-review-v1` artifact. Preview is the default;
`--apply` writes the review artifact, and `--target gap`, `--target eval`, or
`--target both` can promote only accepted reviews into gap or eval artifacts.
The reviewer or calibrated judge owns semantic judgment. Deepr validates score
shape, failure-label membership, acceptance policy, and write boundaries.
```bash
deepr expert review-consult-quality "Azure Architect" consult_abc123 \
  --score uses_expert_state=5 \
  --score surfaces_uncertainty=5 \
  --score preserves_dissent=5 \
  --score actionability=5 \
  --score grounded_when_factual=5 \
  --score original_thought=5 \
  --reviewer operator \
  --decision accept \
  --target eval \
  --apply
deepr expert judge-consult-quality "Azure Architect" consult_abc123 --local-judge-model qwen2.5 --json
deepr expert judge-consult-quality "Azure Architect" consult_abc123 --plan codex --plan-model gpt-5-mini --json
```
The judge command stores only validated review fields plus judge metadata. Local
judges cost `$0`; plan judges consume subscription quota and record `$0` Deepr
cost metadata without metered fallback. The premium `--api-provider` judge
implementation is gated in v2.36 pending the shared durable transaction.
`deepr mcp validate-consult` validates the no-metered external-agent consult
path before another machine asks real questions. With no URL it runs a `$0`
offline fixture. With `--live` it exercises local or explicit plan capacity on
the host. With a URL it calls the HTTP MCP endpoint and validates
`deepr_consult_experts`, `deepr-consult-v1`, collaboration metadata, trace
linkage, cost ceiling, no-metered fallback posture, dissent preservation, host
action boundaries, and secret redaction.
```bash
deepr mcp validate-consult --json
deepr mcp validate-consult --live --synthesis-backend local --expert "AI Agent Harnesses" --json
deepr mcp validate-consult http://127.0.0.1:8765/mcp --auth-token "$DEEPR_MCP_KEY" --json
```
When an expert profile exists, consult perspective context includes a bounded
read-only `self_model` block with current goals, calibration, blockers, risks,
and current-focus packet metadata.
Sync learning loop records and sync capacity wait/block payloads include the
same compact `self_model` block as read-only run context when an expert profile
is available.
`deepr expert self-model NAME --json` emits a read-only
`deepr-expert-self-model-v1` record with capabilities, limits, goals,
calibration, risks, and the bounded current-focus packet.
`deepr expert next NAME --json` emits a read-only `deepr-expert-next-v1`
action plan over claims, freshness, gaps, contradictions, and durable loop
outcomes. It routes structural evidence to argument-safe argv plans but cannot judge
semantic maturity, execute work, or change learning policy.
`deepr expert monitor NAME --json` emits a read-only
`deepr-metacognitive-monitor-v1` artifact that converts self-model risks,
failed loop runs, capacity waits, and consult trace candidates into
review-required proposals. It never applies the proposed goal, strategy, gap, or
eval changes.
`deepr expert promote-monitor NAME PROPOSAL_ID` previews one selected
gap/eval proposal, and `--apply` is required before it writes a metacognition
gap or local eval-case artifact. This keeps monitor output advisory while
making reviewed failures durable.

`deepr eval consult` runs the built-in `$0` consult harness regression suite.
It checks deterministic contracts for explicit expert routing, stored context,
synthesis section parsing, collaboration metadata, no-metered capacity posture,
dissent preservation, replayable traces, trace candidates, and semantic quality
review-case shape. It does not judge answer meaning through keyword matching.

**Task Planning** decomposes complex queries into subtasks:

```bash
/plan "Design a zero-trust architecture for healthcare"
```

Generates a step-by-step plan, runs independent steps in parallel, shows live progress per step.

**Approval Flows** protect against expensive operations:
- Free operations (KB search, standard research) auto-approve
- Moderate operations show a notification with cost
- Expensive operations (deep research above threshold, council above $3) block until the user approves or denies

### Update Expert Knowledge

```bash
# Add knowledge via topic research
deepr expert learn "Azure Architect" "Azure AI Agent Service 2026" --local
deepr expert learn "Azure Architect" "Azure AI Agent Service 2026" --plan codex

# Fill knowledge gaps proactively (ranked by EV/cost ratio)
deepr expert route-gaps "Azure Architect" --execute --scheduled --top 3

# Direct API resume is gated in v2.36; saved progress remains intact.

# Absorb a completed report into permanent beliefs (verification-gated, deduped)
# The free word-overlap heuristics only ROUTE; a cheap model verdict concludes -
# it drops phrasing-level false contradictions and refuses to merge two different
# facts that merely share words (e.g. "$10/M" vs "$30/M"). The result reports how
# many false positives the verdicts caught. Pass --no-... equivalents in code via
# verify_contradictions / verify_dedup to disable.
deepr expert absorb "Azure Architect" <job_id> --dry-run   # preview
deepr expert absorb "Azure Architect" <job_id>             # apply

# Optional cross-vendor grounding check on absorbed claims (advisory, never blocks
# storage): a fresh-context verifier stamps a grounding_assurance level. Add
# --second-checker-plan to escalate a weak first verdict to a distinct third-vendor
# checker (built lazily, only when the first verdict is weak). Same flags on sync.
deepr expert absorb "Azure Architect" <job_id> --check-grounding --checker-plan codex --second-checker-plan claude

# Reflect through admitted local or trusted plan capacity, or wait without spend.
deepr expert reflect "Azure Architect" <job_id> --depth 2 --scheduled
```

API `fill-gaps`, provider-backed refresh or synthesis, and API compiled-claim
sync fail closed in v2.36. Use local or explicit plan-quota expert paths.

### Knowledge Maintenance

```bash
# Read-only, cost-$0 audit: freshness, contradictions (recorded absorb-time
# flags + fresh heuristic detections, deduplicated), missing provenance,
# decayed beliefs, open-gap backlog, un-synthesized docs - with a recommended
# action menu (command + estimated cost + approval tier per action).
deepr expert health-check "Azure Architect"
deepr expert health-check "Azure Architect" --json

# Route open gaps to the best instrument (recon/distillr/primr/research), $0
deepr expert route-gaps "Azure Architect" --top 10

# ...and EXECUTE the highest-value research-route fills, budget-bounded
# (specialist instruments are deferred with their command, never auto-run)
deepr expert route-gaps "Azure Architect" --execute --dry-run     # preview, $0
deepr expert route-gaps "Azure Architect" --execute --budget 1 -y

# Stay current: subscribe to topics, sync pulls only what changed (delta
# prompts, verified absorb; idempotent per cadence window - cron-able)
deepr expert subscribe "Azure Architect" "Azure Landing Zone updates" --every 7 --budget 0.50
deepr expert subscriptions "Azure Architect"
deepr expert sync "Azure Architect" --dry-run
deepr expert sync "Azure Architect" --local -y
deepr expert sync "Azure Architect" --local --fresh-context --compile-claims -y
deepr expert sync "Azure Architect" --local --fresh-context --compile-claims --stage-compiled-claims -y
deepr expert loop-status "Azure Architect"
deepr expert loop-status "Azure Architect" --json

# Run follow-ups only when scheduled owned or prepaid capacity is ready.
deepr expert reflect "Azure Architect" <job_id> --execute-followups --scheduled --budget 1 -y
```

### Fleet Maintenance (whole roster)

Keep an entire roster of experts current as a fleet, mostly at `$0`, and run it unattended.

```bash
# Read-only $0 roster health: per expert the last run, what changed, cost +
# capacity source, last failure, and whether a refresh is due. Anomalies sort
# first; exits non-zero when any latest run failed, so a scheduler can run it as
# a watchdog.
deepr fleet status
deepr fleet status --json

# Sync every due expert in one capacity-aware pass: owned/prepaid capacity first
# (local model at $0 with --local), per-expert budgets within a total ceiling,
# skip-not-fail, overlap-locked so a pass never collides with a manual sync. A
# --scheduled pass waits instead of spending metered when the monthly pool is
# drained, and pings the heartbeat (below) on completion.
deepr expert sync-all --dry-run
deepr expert sync-all --local -y
deepr expert sync-all --scheduled -y

# Emit the correct host scheduler recipe (Windows Task Scheduler XML / cron /
# systemd timer), tuned for catch-up not punctuality. It prints the recipe plus
# the exact install command; it does not auto-install (a privileged host step).
deepr fleet install-schedule --command "deepr expert sync-all --scheduled -y"
deepr fleet install-schedule --platform systemd --output ./schedule
```

Set `DEEPR_HEARTBEAT_URL` to a free dead-man's-switch (healthchecks.io / Dead Man's Snitch) so you are alerted if a scheduled pass ever silently does not run - the only signal that catches "the laptop never woke up" (a same-host monitor dies with the jobs).

### Temporal Perspective Queries

```bash
# All read-side, cost-$0, also available as MCP tools for host agents.

# Re-sync: what did the expert's beliefs do since a point in time?
deepr expert what-changed "Azure Architect" --since 7d

# Open conflicts: contradiction pairs with both sides + provenance
deepr expert contested "Azure Architect"

# Introspection: why does the expert believe X? Evidence roots, confidence
# trajectory (event log), support chains (typed graph), contradictions.
deepr expert why "Azure Architect" "landing zone subscription vending"

# Recall candidate beliefs for verifier routing. It costs $0 and does not
# generate embeddings unless a future budgeted embedding path supplies them.
deepr expert semantic-recall "Azure Architect" "subscription vending guardrails" --json
# Tool: deepr_semantic_recall

# Evaluate accumulated operator-labeled recall cases as routing evidence only.
deepr eval recall-libraries --json
deepr eval recall-libraries --validation-plan --local-embedding-model nomic-embed-text --json
deepr eval recall "Azure Architect" --query-embeddings-json query-vectors.json --embedding-model nomic-embed-text --save
# recall-libraries emits deepr-recall-library-inventory-v1 or
# deepr-recall-library-validation-plan-v1. Saved evaluations emit
# deepr-recall-eval-report-v2 with hit@k, MRR, precision@k, recall@k, MAP@k,
# NDCG@k, and deterministic paired uncertainty. Preference eligibility needs
# 30 cases, complete current vectors, required metric wins, and 95 percent
# confidence lower bounds above zero. Sync also rejects the report after any
# belief or vector state-digest drift, or when runtime top-k, expert domain, or
# minimum score differs from the evaluated retrieval contract. Default sync
# routing stays lexical-first.

# MCP-only temporal edge query: filter typed edge qualifiers by valid time,
# observed time, edge type, or one belief reference.
# Tool: deepr_temporal_edges

# Derived self-model: capabilities, limits, goals, calibration, current focus.
deepr expert self-model "Azure Architect" --json

# Structural next actions: what to repair, learn, or review now at $0.
deepr expert next "Azure Architect"

# Generated EXPERT.md orientation for humans and host agents. This is a
# derived view, not canonical memory.
deepr expert memory-card "Azure Architect"
deepr expert memory-card "Azure Architect" --write

# Monitor proposals: measured failures and risks become reviewed next steps.
deepr expert monitor "Azure Architect" --json
deepr expert promote-monitor "Azure Architect" meta_abc123 --target gap
deepr expert promote-monitor "Azure Architect" meta_abc123 --target gap --apply

# Browsable derived view: beliefs by domain, conflicts surfaced, temporal edge
# qualifiers rendered, byte-stable
deepr expert digest "Azure Architect" --print
```

### Distribution

```bash
# Package an expert as an installable agentskills.io SKILL.md (Claude Code,
# Codex, Cursor, VS Code Copilot, OpenClaw, ...). Consults the expert via MCP.
deepr expert export-skill "Azure Architect"
deepr expert export-skill "Azure Architect" --print   # preview

# Export a portable OKF Markdown bundle generated from structured expert state.
# Includes index.md, log.md, concept pages, citations, relations, gaps,
# contested claims, and llms.txt discovery. Cost $0, no model call.
deepr expert export-okf "Azure Architect" ./okf/azure-architect
deepr expert export-okf "Azure Architect" ./okf/azure-architect --json

# Absorb OKF concepts through the same verified report absorber. The bundle is
# parsed as source text, then extraction, dedup, and contradiction gates decide
# what enters the belief store (grounding checks stay advisory, never blocking).
deepr expert absorb-okf "Azure Architect" ./okf/azure-architect --dry-run
deepr expert absorb-okf "Azure Architect" ./okf/azure-architect --local -y
```

### Expert Skills

Domain-specific capability packages that give experts unique tools:

```bash
# List all available skills
deepr skill list

# List skills installed on an expert
deepr skill list "Financial Analyst"

# Install a skill on an expert
deepr skill install "Financial Analyst" financial-data

# Remove a skill
deepr skill remove "Financial Analyst" financial-data

# Show skill details (tools, triggers, domains)
deepr skill info code-analysis

# Scaffold a new custom skill
deepr skill create my-custom-skill

# Run a skill tool directly
deepr expert run-skill "Dev Lead" code-analysis complexity_report --args '{"code": "def foo(): pass"}'
```

**Built-in skills:** `web-search-enhanced` (data extraction), `code-analysis` (dependencies + complexity), `financial-data` (ratio calculations), `data-visualization` (tables + charts), `recon` (infrastructure/email security), `distillr` (source ingestion), and `primr` (company strategy).

Skills auto-activate when user queries match keyword or regex triggers. Full skill documentation loads only when activated (progressive disclosure).

### Export/Import Experts

```bash
# Export expert for sharing
deepr expert export "Azure Architect" --output ./exports/

# Import expert from corpus
deepr expert import "New Expert" --corpus ./exports/azure_architect/

# OKF import is verification-gated:
deepr expert absorb-okf "Existing Expert" ./okf/azure-architect --dry-run
```

## Vector Store Management

New provider vector-store creation and research attachment are gated in v2.36
until their full storage lifecycle is priced. Existing stores from earlier
releases can still be inspected and explicitly cleaned up.

### Manage Vector Stores

```bash
# List all stores
deepr vector list

# Show details
deepr vector info <vector-store-id>

# Delete store
deepr vector delete <vector-store-id> --yes
```

`deepr vector create` returns a fixed fail-closed explanation before provider
construction. Use `expert make --local --files` for a provider-free local corpus.

## Campaign Management

### Pause/Resume Controls

Mid-campaign intervention:

```bash
# Pause active campaign
deepr prep pause

# Pause specific campaign
deepr prep pause <plan-id>

# Resume most recent
deepr prep resume

# Resume specific
deepr prep resume <plan-id>
```

**Use cases:**
- Review interim results
- Adjust strategy mid-campaign
- Budget control
- Quality oversight

### Campaign Status

```bash
# View campaign status
deepr prep status <plan-id>
```

These status and pause records remain readable. New metered execution is gated
before provider work in v2.36.

## Safe Eval Workflow

```bash
# Estimate only
deepr eval new --dry-run --tier all

# Local-only comparison at $0: candidates and judge all run through Ollama
deepr eval local --model qwen2.5:14b --model qwen3-coder:30b --judge-model qwen2.5:14b
deepr eval local --max-models 2 --max-prompts 2 --save

# Local-only context comparison at $0: no context vs fresh vs deep
deepr eval local-context --model qwen2.5:14b --judge-model qwen2.5:14b --save

# Optional CLI judge: candidates stay local, judge runs through the approved CLI
deepr eval local --model qwen2.5:14b --judge-cli grok --allow-cli-judge
deepr eval local --model qwen2.5:14b \
  --judge-command "grok --prompt-file {prompt_file} --output-format plain --disable-web-search --max-turns 1" \
  --judge-name cli:grok --allow-cli-judge
```

Use `--tier all` full-catalog runs sparingly; they are for periodic baseline refreshes, not daily iteration.

`deepr eval local` is the no-provider path for comparing local Ollama models before admitting one for automatic maintenance. It runs the built-in `agentic-loops` prompt set, asks a local judge model to score each answer against the rubric, reports the winner, latency, and Deepr metered cost `$0`, and can save JSON under `data/benchmarks`. The score is routing evidence, not ground truth: the judge handles semantic quality while Deepr validates response shape, score range, cost, and prompt failures.

`deepr eval local-context` uses the same no-provider contract for a different decision: whether a model should answer a freshness task with no context, a small fresh context pack, or bounded deep context. It runs the built-in `local-freshness` prompt set, retrieves free-only context for the fresh/deep modes, asks a local judge to score answer relevance and grounding, and records source counts, citation-label validity, latency, and Deepr metered cost `$0`. This is context-routing evidence, not automatic scheduler behavior yet.

`deepr eval red-team` is the no-provider security verifier for Deepr's own
agentic boundaries. It runs built-in prompt-injection, jailbreak,
data-exfiltration, tool-spoofing, MCP handoff and loop-status read-path, and
memory trust-floor probes at `$0`, reports attack-success-rate, and exits
non-zero if a built-in attack succeeds. The metric checks boundary form,
derived read-payload leakage, and confidence ceilings only; semantic acceptance
still belongs to extraction, grounding, contradiction, dedup, and trust-floor
gates. Use `--save` to write a local `data/benchmarks/red_team_*.json` artifact
for release-to-release trend review.

`deepr eval judge-calibration NAME` is a `$0`, read-only eval that measures how
well a calibrated-model consult-quality judge agrees with a human anchor: it
pairs the latest human and latest model review of each consult trace and reports
per-dimension agreement (mean absolute error, signed bias, exact- and
within-tolerance rates) plus decision agreement, emitting
`deepr-judge-calibration-report-v1`. Agreement is not correctness, and a judge is
marked `trusted` only above a paired-trace and agreement floor. That trusted set
feeds `deepr expert consult-quality-trends --gate-untrusted-judges`, which
excludes not-yet-trusted model judges from prompt-regression selection (human
reviews always stay eligible; descriptive trend stats still cover every review).

`deepr eval grounding-correctness` makes the verification spine's promise
falsifiable: it runs the grounding checker over a curated golden set of
human-labeled `(claim, evidence, label)` entailment triples and reports whether a
SUPPORTED verdict is actually correct - `support_precision` (when it says
SUPPORTED, how often the evidence truly entails), `false_support_rate` (stamped
SUPPORTED for contradicted/unrelated evidence - the dangerous failure), recall,
abstention, per-label accuracy, and a confusion matrix, as
`deepr-grounding-correctness-v1`. `$0` on local Ollama by default; pass `--cases`
for domain-specific triples or `--checker-plan <id>` to test a plan vendor. The
model owns the entailment verdict; the scoring is deterministic against
human-curated ground truth, and the report is explicit that agreement on a
bounded set is not proof of world-truth.

Saved artifacts can feed admission directly:

```bash
deepr eval local --max-models 2 --max-prompts 2 --save
deepr capacity admit --from-eval latest --task-class sync --yes
deepr capacity admit qwen2.5:14b --from-eval data/benchmarks/local_compare_20260618_120000.json --task-class absorb
```

`--from-eval latest` resolves the newest `data/benchmarks/local_compare_*.json` artifact. Deepr only accepts zero-cost local eval artifacts, enforces score ranges, rejects failed prompt results, applies a default minimum score of `0.70`, and records the artifact summary in the machine-local admission ledger. Use `--min-score` to raise or lower the floor for a specific admission.

Automatic local routing now uses the admitted score as runtime quality evidence. A scoreless manual admission is still visible in `deepr capacity admissions`, but it does not take over `expert sync` or `expert absorb` automatically because it cannot clear the measured quality floor. Use `--local` when you want an explicit one-off override.

CLI judges are supported for plan or subscription tools when the operator explicitly approves them with `--allow-cli-judge`. The Grok preset expands to a headless prompt-file command; custom commands must include `{prompt_file}` and run with `shell=False`. Deepr still records metered cost `$0`, but the external CLI may consume its own quota or credits, so this path is never auto-selected.

### Evidence Evals

Three evals make expert trust measurable instead of asserted.

```bash
# Continuity: staleness honesty, abstention, contradiction-surfacing,
# what-changed exactness, and temporal edge qualifier visibility in read and
# generated digest surfaces at $0.
deepr eval continuity "AI Policy Expert"

# Red team: prompt-boundary, MCP read-path, tool-spoofing, and trust-floor probes at $0.
deepr eval red-team --json
deepr eval red-team --save

# Calibration: does extraction confidence track grounding?
# Reliability curve + expected calibration error + Platt-derived threshold.
deepr eval calibrate --from data/calibration/graded.jsonl   # $0, grades existing pairs

```

Non-dry `deepr eval new` and live provider benchmarks are gated in v2.36.
Local, local-context, saved-artifact, and explicit CLI-judge evaluation paths
above remain available under their documented capacity rules.

Paid `deepr eval calibrate --corpus` is gated in v2.36 pending the shared
durable transaction. Continue to use `--from` with existing graded pairs at
`$0`.

Calibration uses FActScore/SAFE-style atomic claim decomposition and a strong-model grader; the threshold fit is numpy Platt scaling (no sklearn). Red-team metrics are local workflow checks over shipped boundaries, not a replacement for calibrated model judgment. The first measured curve is in [CALIBRATION.md](CALIBRATION.md); the deterministic-vs-model check boundary is in [design/checks-deterministic-vs-agentic.md](design/checks-deterministic-vs-agentic.md).

## Setup and Capacity

```bash
# Guided setup: detect keys, write .env, set a budget, choose a data dir.
deepr init                                              # interactive
deepr init --yes --budget 5 --data-dir ~/OneDrive/deepr # scripted / CI-safe

# Verify connectivity and storage; ranked next step on any problem.
deepr doctor

# See what you can actually run with: owned/prepaid capacity first.
deepr capacity            # local Ollama, plan CLIs, metered APIs + cost model
deepr capacity --probe    # actively probe local endpoint and list models
deepr capacity refresh-quota codex  # record Codex quota windows from local logs
deepr capacity refresh-quota claude # record Claude Code usage windows when configured
deepr capacity refresh-quota grok   # record Grok billing metadata when configured
deepr capacity next       # ranked next actions for making cheap capacity usable
deepr capacity next --task-class sync --context-mode fresh --scheduled
deepr expert sync "Platform Team Expert" --scheduled --fresh-context -y
deepr expert route-gaps "Platform Team Expert" --execute --scheduled --json
deepr expert reflect "Platform Team Expert" <job_id> --execute-followups --scheduled --json
deepr expert health-check "Platform Team Expert" --scheduled --json
deepr capacity --json
```

`deepr init` writes `DEEPR_DATA_DIR` plus explicit `DEEPR_EXPERTS_PATH` and `DEEPR_REPORTS_PATH` children. Pointing the data dir at OneDrive, Dropbox, iCloud, or another synced folder therefore relocates experts, reports, and runtime artifacts that use `DEEPR_DATA_DIR`, including queues, traces, benchmarks, observability, and several MCP databases. Use one Deepr writer or service at a time and wait for sync to finish before switching devices; generic file sync does not safely merge concurrent expert or operational state. The cost and capacity ledgers can remain machine-specific through their dedicated root overrides. See [ADR 0004](decisions/0004-one-experts-root-and-portable-data-dir.md) and the [multi-device design](design/multi-device-expert-continuity.md).

Capacity source status:

| Source | Status | Notes |
|---|---|---|
| Local Ollama | Execution works for local expert setup, local sync, deep/fresh local context, local absorb, local eval, local context eval, and scored admission | `$0` marginal cost, quality-gated before automatic routing |
| OpenAI, Gemini, Grok, Anthropic, Azure APIs | Core research execution works when configured with API keys and budget ceilings; unsafe metered expert lifecycle surfaces are gated in v2.36 | Cost ledger writes every supported spend source |
| Codex, Claude Code, OpenCode, Antigravity, Grok Build, Kiro, and other non-metered plan CLIs | Explicit execution works through `expert sync --plan <id>`, `expert absorb --plan <id>`, topic `expert learn --plan <id>`, and the explicit `expert learn-web --plan <id>` alias behind auth-mode and no-surprise-bills gates; Codex, Claude Code, and Grok have live quota metadata probes | Automatic plan routing still requires trusted remaining-quota observations per backend; metered-at-margin Copilot is visible but execution-blocked until full cost accounting exists |
| CLI judge for local eval | Explicit opt-in only | `--allow-cli-judge` is required because Deepr cannot prove the vendor CLI's billing source |

Local-model execution runs quality-tolerant steps at $0 against a local Ollama
endpoint. Force it with `--local`, choose explicit plan-quota capacity with
`--plan <id>`, or admit a local model so maintenance uses owned capacity.
Metered API overrides for the gated expert lifecycle surfaces do not dispatch
in v2.36:

```bash
deepr expert make "Platform Team Expert" --local -d "Platform engineering knowledge"
deepr expert absorb "Platform Team Expert" report.md --local   # force local, $0
deepr expert sync "Platform Team Expert" --local --fresh-context # local model + free retrieval context
deepr expert sync "Platform Team Expert" --local --deep-context  # multi-query free retrieval context
deepr expert sync "Platform Team Expert" --local --fresh-context --compile-claims # extract, verify, apply commit
deepr expert sync "Platform Team Expert" --local --fresh-context --compile-claims --stage-compiled-claims # no-write staging

# Review local quality first, then admit it for automatic use.
deepr expert absorb "Platform Team Expert" report.md --local --dry-run
deepr eval local --model qwen2.5:14b --judge-model qwen2.5:14b
deepr eval local-context --model qwen2.5:14b --judge-model qwen2.5:14b --save
deepr eval local --model qwen2.5:14b --judge-cli grok --allow-cli-judge
deepr capacity admit --from-eval latest --task-class sync --yes
deepr capacity admit llama3.1 --task-class absorb --days 60 --score 0.74
deepr capacity admissions          # what's admitted (and when it expires)
deepr capacity next --task-class sync
deepr capacity next --task-class sync --context-mode deep --expert "Platform Team Expert" --scheduled
deepr expert sync "Platform Team Expert" --scheduled --fresh-context -y
deepr expert route-gaps "Platform Team Expert" --execute --scheduled --json
deepr expert reflect "Platform Team Expert" <job_id> --execute-followups --scheduled --json
deepr expert health-check "Platform Team Expert" --archive-stale --scheduled --json
deepr capacity revoke llama3.1 --task-class absorb
```

After scored admission, `deepr expert sync`/`absorb` (with no backend flag) run on the admitted local model at $0 and print why. Admissions use a 90-day default expiry so they are re-earned as models change, and are machine-local (`DEEPR_CAPACITY_DATA_DIR`) since local capacity differs per machine. Use `deepr eval local --save` as the cheap review step before admitting a model, then `deepr capacity admit --from-eval latest` to turn that reviewed artifact into the admission record.

`deepr capacity next` is the guided path when the safe cheap route is not ready. It ranks the current block reason, local setup commands, latest usable eval-artifact admission, eval refresh, scheduled-job wait guidance, and honest gated status. It can preview a concrete job shape with `--expert`, `--report-id`, `--context-mode none|fresh|deep`, and `--scheduled`, but it never authorizes an API expert-lifecycle fallback. It is read-only, runs no research, and makes no provider API calls. JSON output uses the published `deepr-capacity-next-v1` payload, which scheduled sync waits embed under `capacity_next`. The outer sync wait/block response is published as `deepr-sync-capacity-gate-v1`. `deepr expert sync --scheduled` consumes the same preview automatically for due subscription syncs: when owned/prepaid capacity is unavailable, or when fresh/deep context needs local capacity, it exits successfully with a wait payload and next actions instead of spending. `deepr expert route-gaps --execute --scheduled` uses the same scheduler default for gap-fill sweeps by returning pending routes and a wait state instead of starting metered research. `deepr expert reflect --scheduled` waits before constructing the reflection evaluator, so recurring reflection follow-up jobs expose pending evaluation and follow-up work without making a metered call. `deepr expert health-check --scheduled` returns a read-only scheduler action plan that separates gated metered recommendations, confirmation-gated local writes, and ready local actions. Sync, gap-fill, reflection, and explicit health archive wait or mutation payloads include durable `loop_run` records where work or a gated mutation exists. Audit-only health action plans use published `deepr-health-check-action-plan-v2` JSON and intentionally carry no `loop_run` or pending execution state.

Local and explicit plan sync backends do not automatically have current web
context. For sync runs that need freshness, add `--fresh-context`; for broader
source coverage, add `--deep-context`. Both require an owned or prepaid sync
backend, either explicit `--local`, explicit `--plan <id>`, or an admitted local
model, so a freshness request cannot silently fall through to metered APIs.
Add `--compile-claims` when you want the source-note compiler to run semantic
claim extraction, claim verification, and verified graph-commit apply for the
sync. It persists `sync_artifacts/claim_extractions/<timestamp>_<topic>.json`,
`sync_artifacts/claim_verifications/<timestamp>_<topic>.json`, and
`sync_artifacts/graph_commit_envelopes/<timestamp>_<topic>.json`, records
prompt, schema, provider, model, capacity, cost, source-window refs, and
read-only recall context, bypasses the legacy absorber for that topic, applies
only the verified graph-commit envelope, carries verifier-supplied temporal
edge qualifiers when present, and writes
`sync_artifacts/graph_commit_apply_results/<timestamp>_<topic>.json`.
Use `--stage-compiled-claims` with `--compile-claims` to persist compiler
sidecars without applying graph commits. `--apply-compiled-claims` remains a
compatibility alias for the default compiled apply behavior and cannot run with
`--dry-run`.
Perspective deltas and belief explanations include temporal edge qualifiers
from applied graph commits as structured read-only metadata.
`deepr expert apply-graph-commit NAME ENVELOPE --dry-run --json` validates the
commit plan without writing. `deepr expert
apply-graph-commit NAME ENVELOPE --yes --json` applies verified factual
add-belief, typed-edge, gap-promotion, exploration-agenda, hypothesis, concept,
stance, and original-idea operations idempotently, emits
`deepr-graph-commit-apply-v1`, and refuses noninteractive writes without
`--yes`. `deepr-graph-commit-envelope-v1` remains the belief-only envelope;
`deepr-graph-commit-envelope-v2` adds verified gap promotions into the
metacognition gap backlog; `deepr-graph-commit-envelope-v3` adds verified
exploration agendas into the metacognition agenda backlog;
`deepr-graph-commit-envelope-v4` adds verified hypotheses into the
metacognition hypothesis backlog; `deepr-graph-commit-envelope-v5` adds
verified concepts into the metacognition concept backlog;
`deepr-graph-commit-envelope-v6` adds verified stances into the metacognition
stance backlog; `deepr-graph-commit-envelope-v7` adds verified original ideas
into the metacognition original-idea backlog; and
`deepr-graph-commit-envelope-v8` adds structured temporal qualifiers to typed
edge operations. Active original ideas then surface through memory cards,
consult context, and handoff payloads as `deepr-expert-perspective-state-v1`
perspective state rather than verified external facts. Local and non-metered
plan claim compilation is `$0`
inside Deepr; metered API and metered-at-margin plan paths require budget and
cost-ledger gates.
Deepr builds a bounded source pack first, then prepends it to the prompt and
asks the model to cite source labels. The fresh/deep retrieval path is free-only
inside Deepr: it can fetch explicit URLs, can use a configured self-hosted
SearXNG endpoint (`DEEPR_SEARXNG_URL`), and otherwise can use DuckDuckGo when
`ddgs` is installed. It does not use Brave, Tavily, or other API-key search
providers. If no fresh sources are available, the model is told to say that
current context is unavailable, and sync records no changes instead of absorbing
that uncertainty as permanent beliefs.

When a sync run uses fresh/deep context, Deepr writes a bounded JSON source pack
under the expert knowledge directory at
`sync_artifacts/source_packs/<timestamp>_<topic>.json`. The sync outcome reports
the artifact path, source count, and context mode. If the artifact cannot be
written, Deepr treats the run as failed instead of absorbing a context-grounded
answer without provenance.

Use `deepr eval local-context` before depending on fresh/deep context for
automation. The eval compares no context, fresh context, and deep context with a
local judge, then records the retrieval and citation envelope as JSON under
`data/benchmarks` when `--save` is passed. Schedulers do not consume those
context artifacts yet; scheduler rules are the next slice in
[design/local-fresh-context.md](design/local-fresh-context.md).

Plan-quota adapters execute expert maintenance and bootstrap by explicit opt-in.
`deepr expert sync NAME --plan codex`, `deepr expert absorb NAME REPORT --plan
codex`, and topic learning through `deepr expert learn NAME TOPIC --plan codex`
run through the plan-quota chat-client seam so synthesis and extraction stay on
the chosen CLI instead of silently falling back to metered APIs. `deepr expert
learn-web NAME TOPIC --plan codex` remains an explicit live-web alias. The same
non-metered path supports Claude Code, OpenCode, Kiro, Grok Build, and
Antigravity according to their adapter safety settings. GitHub Copilot remains
fleet-visible but execution-blocked until its metered adapter has deterministic
estimation, durable reservation, usage settlement, and canonical cost-ledger
support. `deepr capacity probe-plan <id>` validates auth and one tiny round trip
for eligible adapters; `deepr capacity refresh-quota codex` reads Codex local
session-log `rate_limits` metadata, `deepr capacity refresh-quota claude` reads
Claude Code OAuth usage metadata, and `deepr capacity refresh-quota grok` reads
Grok billing metadata. These refreshes record conservative quota-ledger events
without running a model call. Automatic plan routing stays conservative:
selection orders local, plan-quota, and metered backends, then blocks execution
on missing or unknown quota, exhaustion, quarantine, overage, reserve-floor
breaches, unsupported task classes, missing measured quality, and metered
fallback without a budget gate.

Topic `learn` and `learn-web` share the fresh-context provenance preflight: two
fetched, content-addressed sources for search discovery or one for an explicit
URL, before any local or plan model generation. Each attempt persists portable
source-pack, manifest, source-note, and snapshot artifacts under the configured
expert root, with a durable report on successful synthesis. Failed fetches
remain diagnostic candidates instead of being counted as live sources. The
extraction model selects supporting labels per candidate, while code stores
only the selected replay pointers and rejects candidates with no valid pointer.

The intended QOL is simple: ask for a job, see the cheapest safe route, and get a
clear reason if Deepr should wait rather than pay. `deepr capacity next` is
read-only today and now accepts enough job context to preview sync context mode
and recurring scheduler intent. `deepr expert sync --scheduled` now consumes
that preview before launching due subscription syncs. `route-gaps --execute
--scheduled` now gives gap-fill sweeps the same no-surprise-spend wait behavior.
`expert reflect --scheduled` waits before reflection evaluation and follow-up
research until owned/prepaid evaluator capacity exists. A one-off metered
reflection remains gated in v2.36. `expert health-check --scheduled` adds an action plan, and
`--archive-stale --scheduled` waits for confirmation instead of prompting or
mutating unless `--yes` is explicit. These scheduled wait/action-plan payloads
append `ExpertLoopRun` snapshots, include `loop_run` JSON, and are published as
versioned scheduler schemas for sync, gap-fill, reflection, health-check action
plans, and archive confirmations. Successful-run
instrumentation now covers `deepr expert sync`, non-dry `deepr expert
route-gaps --execute`, `deepr expert reflect`, `deepr expert health-check`, and
confirmed `--archive-stale`; these append loop snapshots with spend, capacity
source, verifier outcome, accepted-change metrics where applicable, and typed
stop actions when work fails, waits on a human gate, has no corrective work,
fails the verifier, or exhausts the run budget. The dashboard API now exposes
`/api/experts/{name}/loop-status`, a read-only rollup over those records with
latest run, last sync result, next scheduled action, a non-probing per-task-class
next-run capacity outlook (admitted `$0`/prepaid vs metered), a due-subscription
summary, failure, capacity source,
spend, acceptance, verifier failure metrics, and `expert_state` telemetry for
freshness, gap velocity, and contested/open claims. Host agents can already
read the durable loop state through `deepr_expert_loop_status`. Terminal loop
records now require status-compatible typed stop reasons before they can be
stored. The dashboard API also exposes `admission_contracts` for repeat demand,
automated verification, explicit budget/capacity, and failure-diagnosis state.
The CLI, MCP tool, and dashboard API share the same
`deepr-loop-status-v1` rollup payload, so host agents can validate one shape
instead of handling separate ad hoc run lists.
For downstream agents that need one stable read contract before choosing a more
specific tool, `/api/experts/{name}/handoff` and MCP `deepr_expert_handoff`
return the versioned `deepr-expert-handoff-v1` payload: profile summary,
manifest counts, bounded claims/gaps, dashboard telemetry, loop-status rollup,
OKF interchange hints, original-idea perspective-state counts, and an additive
compatibility contract. The schema is published at
[schemas/expert-handoff-v1.json](schemas/expert-handoff-v1.json).
MCP handoff and loop-status responses validate their published envelope before
dispatch and fail closed with `SCHEMA_VALIDATION_FAILED` if schema version,
kind, or required envelope fields drift.
The A2A task lifecycle uses the same contract posture: create, status, cancel,
and result-bearing task responses are stamped as `deepr-a2a-task-v1`, published
at [schemas/a2a-task-v1.json](schemas/a2a-task-v1.json), and fail closed if
their schema version, kind, lifecycle state, cost field, timestamps, or metadata
drift.
The adjacent loop-status and OKF mapping contracts are published as
[schemas/loop-status-v1.json](schemas/loop-status-v1.json) and
[schemas/okf-profile-v1.json](schemas/okf-profile-v1.json). Hosted MCP
remote-audit, scheduled maintenance, capacity, and registry contracts are also
published under [schemas/](schemas/).
The MCP HTTP transport also has an experimental scoped-key primitive:
configured key stores authenticate Bearer or `X-Api-Key` requests, enforce
key mode, expert allowlists, confirmation gates, per-key budget ceilings, and
per-key rate limits before `tools/call` dispatch, and append
`deepr-mcp-remote-audit-v1` records for remote calls with response cost
attribution when available. Metered remote tools must have deterministic
pre-dispatch estimates; scoped budget checks fail closed when that estimate is
missing. HTTP POST concurrency is capped at 32 by default and can be adjusted
with `--max-concurrency` or `DEEPR_MCP_HTTP_MAX_CONCURRENCY`.
Use `deepr mcp keys create/list/revoke` to manage those local key records, and
`deepr mcp audit list` / `deepr mcp audit summary` to review and aggregate the
local append-only remote-call audit log with key, tool, outcome, limit, and JSON
filters. Use `deepr mcp serve --http` to run the same MCP server over HTTP/SSE
on loopback by default. Use `deepr mcp smoke-http URL` to run `$0` health,
initialize, tools/list, and free tool-search checks against a local or
TLS-proxied HTTP MCP endpoint. Use `deepr mcp registration-manifest URL` to
write a token-redacted `deepr-mcp-registration-manifest-v1` packet with endpoint
metadata and optional smoke results for remote host setup. A
repeatable hosted container recipe lives in
[../deploy/mcp-http/](../deploy/mcp-http/); it publishes only loopback by
default, mounts one Deepr data directory at `/data`, and bootstraps scoped keys
before the service starts. An Azure Container Apps template under
[../deploy/mcp-http/azure-container-apps/](../deploy/mcp-http/azure-container-apps/)
uses the same image with persistent `/data`, HTTPS-only ingress, scoped-key
state, and remote-audit durability while leaving provider keys out until paid
tools are intentionally enabled. Its `maxConcurrentRequests` parameter feeds
both the app's in-process cap and the platform HTTP scale rule.
An AWS ECS Fargate template under
[../deploy/mcp-http/aws-ecs-fargate/](../deploy/mcp-http/aws-ecs-fargate/)
uses the same image with EFS-backed `/data`, HTTPS ALB ingress, scoped-key
state, and remote-audit durability while leaving provider keys out until paid
tools are intentionally enabled. Its `MaxConcurrentRequests` parameter feeds
both the app's in-process cap and `deepr mcp serve --max-concurrency`.
A GCP Cloud Run template under
[../deploy/mcp-http/gcp-cloud-run/](../deploy/mcp-http/gcp-cloud-run/) uses the
same image with Cloud Storage FUSE-backed `/data`, optional public invoker
binding, scoped-key state, and remote-audit durability while leaving provider
keys out until paid tools are intentionally enabled. It defaults to one Cloud
Run instance and one MCP POST at a time while key and audit files live on the
object-backed mount.
A Cloudflare Worker edge ingress recipe under
[../deploy/mcp-http/cloudflare-worker/](../deploy/mcp-http/cloudflare-worker/)
fronts an existing HTTPS MCP origin, proxies only `/mcp` paths, caps request
bodies at 1 MiB, forwards scoped-key auth headers, and leaves scoped-key state,
budgets, rate limits, audit logs, and provider keys on the origin side.

See [design/capacity-waterfall.md](design/capacity-waterfall.md) for the capacity model and [design/local-fresh-context.md](design/local-fresh-context.md) for the fresh-context loop.

## Cost Management

One provider-backed REST, web, CLI, or MCP research request uses a cross-process
maximum-cost reservation and the same finite bounds at preview and dispatch.
Queued cancellation and dispatch use atomic competing transitions. Timeout and
connection outcomes settle conservatively and do not trigger an application
replay when acceptance is uncertain. Metered campaign-batch, internal fan-out,
and synchronous multi-call planning are gated until one durable parent
reservation covers every nested request.
See [design/research-cost-reservations.md](design/research-cost-reservations.md).

### Cost Estimation

```bash
# Estimate before submitting
deepr costs estimate "Your prompt"
deepr costs estimate "Prompt" --model o3-deep-research
```

### Cost Dashboard

```bash
# Daily/monthly summary with budget utilization
deepr costs show

# Cost history over time
deepr costs history --days 14

# Breakdown by provider, operation, or model
deepr costs breakdown --by provider --period today
deepr costs breakdown --by model --period week
deepr costs breakdown --by operation --period all

# Cost trends with ASCII chart and anomaly detection
deepr costs timeline --days 30
deepr costs timeline --days 60 --weekly

# Per-expert cost tracking
deepr costs expert "Expert Name"

# Run tracker integrity checks (no API calls)
deepr costs doctor
deepr costs doctor --drift-threshold 0.05

# View active cost alerts
deepr costs alerts

# View or set cost limits
deepr costs limits
deepr costs limits --daily 15 --monthly 150
```

**Shows:**
- Daily and monthly spending with budget utilization
- Cost breakdown by provider, operation, model, or expert
- Timeline chart with anomaly detection (days > 2x average highlighted)
- Per-expert costs: total research cost, monthly spending, budget usage, per-operation breakdown
- Active alerts at configurable thresholds (50%, 80%, 95%)
- Tracker integrity checks (ledger writable + drift vs dashboard totals) via `deepr costs doctor`

Set `DEEPR_COST_TRACKING_STRICT=1` to fail fast when cost events cannot be written to the canonical ledger.

### Budget Limits

Configure in `.env`:

```bash
DEEPR_MAX_COST_PER_JOB=10.0
DEEPR_MAX_COST_PER_DAY=100.0
DEEPR_MAX_COST_PER_MONTH=1000.0
```

## Queue Operations

### Queue Management

```bash
# List all jobs
deepr queue list

# Filter by status
deepr queue list --status completed
deepr queue list --status failed

# Limit results
deepr queue list --limit 20

# Queue statistics
deepr queue stats

# Watch in real-time
deepr queue watch
```

### Queue Sync

Sync all job statuses with provider:

```bash
# Update all active jobs
deepr queue sync
```

**What it does:**
- Checks all pending jobs with provider
- Updates local status
- Tracks cost/token usage
- Doesn't download results (use `get --all` for that)

## Configuration

### Validation

```bash
# Validate configuration
deepr config validate
```

**Checks:**
- API keys present
- Directory structure
- Budget limits
- API connectivity
- Provider initialization

### Display Configuration

```bash
# Show current settings (sanitized)
deepr config show
```

**Shows:**
- Provider type
- API key (masked)
- Storage paths
- Budget limits
- Default model

### Update Configuration

```bash
# Set configuration value
deepr config set DEEPR_AUTO_REFINE true
deepr config set DEEPR_MAX_COST_PER_JOB 5.0

# CLI UX settings (preferred aliases)
deepr config set cli.animations light
deepr config set cli.branding auto
```

Supported CLI UX values:
- `cli.animations`: `off`, `light`, `full`
- `cli.branding`: `off`, `on`, `auto`

Notes:
- `cli.animations` maps to `DEEPR_ANIMATIONS`
- `cli.branding` maps to `DEEPR_BRANDING`
- Legacy direct env keys still work (for example `DEEPR_ANIMATIONS=light`)
- Startup banner controls:
- `DEEPR_BANNER_MODE=off|static|light|full`
- `DEEPR_BANNER_DURATION=<seconds>` (animated modes only)

## Analytics

### Usage Analytics

```bash
# Weekly report (default)
deepr analytics report

# By period
deepr analytics report --period today
deepr analytics report --period week
deepr analytics report --period month
deepr analytics report --period all
```

**Includes:**
- Success/failure rates
- Cost analysis
- Model performance comparison
- Timing metrics
- Recommendations

### Trends

```bash
# Daily trends over past week
deepr analytics trends
```

**Shows:**
- Jobs per day
- Completions per day
- Cost per day

### Failure Analysis

```bash
# Analyze failed jobs
deepr analytics failures
```

**Provides:**
- Common error patterns
- Affected models
- Recent failures
- Actionable insights

## Export and Integration

### Export Research

```bash
# Print the stored result for a completed job
deepr jobs get <job-id>
```

Completed reports remain under the configured reports root, which defaults to
`data/reports/`. Deepr currently has no `jobs export` subcommand.

### Cancel Jobs

```bash
# Cancel running job
deepr jobs cancel <job-id>
```

The command exits successfully only after Deepr confirms cancellation,
cost-reservation closure, and provider-resource cleanup. On a nonzero exit, inspect `deepr jobs status
<job-id>` before retrying.

## Command Reference

### Global Options

```bash
deepr --version    # Show version
deepr -h           # Short help
deepr --help       # Full help
```

### Semantic Commands (Primary Interface)

```bash
deepr research     # Exact preview and one bounded supported research request
deepr learn        # Metered multi-phase execution gated in v2.36
deepr team         # Metered multi-perspective execution gated in v2.36
deepr check        # Legacy metered completion gated in v2.36
deepr make docs    # Legacy metered completion gated in v2.36
deepr make strategy # Legacy metered completion gated in v2.36
deepr expert       # Domain expert management
deepr skill        # Expert skill management
```

### Supporting Commands

```bash
deepr run          # Low-level compatibility modes; only shared bounded paths dispatch
deepr jobs         # Job management (list, status, get, cancel)
deepr vector       # Inspect and clean existing provider vector stores
deepr prep         # Campaign preview/status; new metered execution is gated
deepr costs        # Cost estimation and dashboard (show, history, breakdown, timeline, alerts, expert)
deepr config       # Configuration
deepr analytics    # Usage analytics
deepr doctor       # System diagnostics
deepr web          # Start web dashboard
```

### Help for Commands

```bash
deepr <command> --help
deepr research --help
deepr expert --help
deepr make --help
```

## Advanced Usage

### Combining Features

```bash
# Create expert from documents
deepr expert make "Domain Expert" --local --files docs/*.md
deepr expert consult "What should we verify?" --experts "Domain Expert" --local

# Batch operations
deepr jobs list --status completed
```

### Automation

```bash
# Daily batch job
deepr jobs list --status queued

# Cost monitoring
deepr costs show
```

### Best Practices

1. **Use semantic commands** for intuitive workflows
2. **Create local experts** for document-based consultation
3. **Monitor costs** regularly with analytics
4. **Use one bounded research job at a time** until parent-run campaigns ship
5. **Validate config** with `deepr doctor`
6. **Export important results** in multiple formats

## Integration Patterns

### CI/CD Integration

```bash
# In CI, preview before any explicit bounded run
deepr research "Release notes" --provider openai --model o4-mini-deep-research --preview
# Check job status
deepr jobs list --status completed
```

### Batch Processing

```bash
# Process multiple queries
for query in "query1" "query2" "query3"; do
  deepr research "$query" --provider openai --model o4-mini-deep-research --budget 2 --yes
done

# Check results
deepr jobs list
```

Each loop iteration is an independent reservation. It is not an atomic batch
budget; metered auto-batch execution remains gated.

### Knowledge Management

```bash
# Build expert from knowledge base
deepr expert make "KB Expert" --local --files knowledge_base/*.md
deepr expert consult "Summarize current gaps" --experts "KB Expert" --local
```

## Troubleshooting

### Common Issues

**API key not found:**
```bash
deepr doctor              # Check configuration
deepr config show         # View current settings
```

**Job not completing:**
```bash
deepr jobs list           # Check job status
deepr jobs status <job-id>  # Detailed status
```

**High costs:**
```bash
deepr analytics report --period month
deepr costs breakdown --period week
# Consider using o4-mini model for routine queries
```

**Failed jobs:**
```bash
deepr analytics failures
deepr jobs list --status failed
```

## Next Steps

- Read [INSTALL.md](INSTALL.md) for setup
- See [ROADMAP.md](../ROADMAP.md) for upcoming features
- Check [CHANGELOG.md](CHANGELOG.md) for latest changes
- Visit [README.md](../README.md) for quick start
