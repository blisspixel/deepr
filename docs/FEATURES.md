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

**Research Studio** - Submit research with mode selection (research, check, learn, team, docs), model picker, priority, and web search toggle. Drag-and-drop file upload with type filtering (.txt, .md, .json, .csv). Ctrl+Enter / Cmd+Enter keyboard shortcut to submit. Real-time cost estimation as you type. Supports pre-filled prompts via URL query parameter.

**Research Live** - Real-time progress tracking for running jobs via WebSocket push (no polling). Background poller checks provider API every 15 seconds. Completed jobs show enriched summary with cost, tokens, model, completion date, and content preview.

**Results Library** - Browse and search completed research with sorting (date, cost, model). Paginated grid view (12 per page). Total result count in header.

**Result Detail** - Full markdown report viewer with citation sidebar showing source URLs and snippets. Copy-to-clipboard button for the full report content. Export dropdown for downloading results.

**Expert Hub** - List all domain experts with document counts, finding counts, knowledge gaps, and cost stats. Search and sort controls. Navigate to individual expert profiles.

**Expert Profile** - Seven tabs: Chat (agentic streaming chat with slash commands, mode switching, visible reasoning panel, approval dialogs, context compaction, follow-up suggestions), Claims (tracked assertions with confidence scores and source provenance), Knowledge Gaps (view gaps with EV/cost priority, click to research), Decisions (reasoning audit trail with rationale and alternatives), History (learning timeline with costs), Skills (install/remove domain-specific capability packages), and Conversations (browse and resume past chat sessions).

**Cost Intelligence** - Spending trends over configurable time ranges (7/30/90 days), per-model cost breakdown with charts, budget limit controls with debounced sliders, success rate, and average cost per job. Accuracy disclaimer noting costs are Deepr-internal estimates.

**Models & Benchmarks** - Model registry browser with provider grouping, benchmark results with quality rankings by tier (chat/news/research), quality bar charts and radar charts, run benchmarks from the UI with tier and budget controls, benchmark history file selector, routing configuration display.

**Trace Explorer** - Inspect research execution traces. View span hierarchy with timing, cost attribution, token counts, and model info for each operation. Collapsible decision sidebar showing reasoning audit trail.

**Help** - API key setup guide with provider links, CLI quick reference with common commands, model tier explanations (research/news/chat), and getting-started walkthrough.

**Settings** - Theme selection (light/dark/system), default model, web search toggle, budget limit configuration, environment info (provider, queue, storage, API key status), and demo data loader for populating the UI with sample data.

### Keyboard Shortcuts

- **Ctrl+K** - Open command palette for quick navigation to any page
- **Ctrl+Enter** / **Cmd+Enter** - Submit research from the Research Studio textarea
- Theme cycles through light, dark, and system modes via the header button

### Technical Details

- Code-split routing: each page loads independently via React.lazy and Suspense
- Real-time updates: WebSocket (Socket.io) with Flask-SocketIO backend push for job events
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
# Basic research (auto-detects mode)
deepr research "Your research question"

# With file uploads for context
deepr research "Question" --upload file1.pdf --upload file2.md

# Specify provider and model
deepr research "Question" --provider openai --model o3-deep-research

# Company research mode
deepr research company "Company Name" "https://company.com"

# With web scraping for primary sources
deepr research "Strategic analysis" --scrape https://example.com
```

### Fact Verification

```bash
# Quick fact check
deepr check "PostgreSQL supports JSONB indexing since version 9.4"

# With verbose reasoning
deepr check "Kubernetes 1.28 deprecated PodSecurityPolicy" --verbose
```

### Documentation Generation

```bash
# Generate documentation
deepr make docs "API reference guide"

# Preview outline first
deepr make docs "Architecture overview" --outline

# Include existing files as context
deepr make docs "Migration guide" --files existing/*.md

# Specify output format
deepr make docs "User guide" --format html --output docs/guide.html
```

### Strategic Analysis

```bash
# Generate strategic analysis
deepr make strategy "Cloud migration roadmap"

# With specific perspective
deepr make strategy "Market expansion" --perspective technical

# With time horizon
deepr make strategy "Q1 priorities" --horizon 3mo
```

### Multi-Phase Learning

```bash
# Structured learning with multiple phases
deepr learn "Kubernetes networking" --phases 3

# With specific model
deepr learn "Machine learning fundamentals" --model o3-deep-research
```

### Team Analysis

```bash
# Multi-perspective analysis (Six Thinking Hats)
deepr team "Should we build vs buy our data platform?"

# With more perspectives
deepr team "Technology decision" --perspectives 8
```

## Context Discovery

Find and reuse prior research to avoid redundant work and build on existing knowledge.

### Search Prior Research

```bash
# Search for related prior research using semantic + keyword matching
deepr search query "kubernetes deployment patterns"

# More results with lower threshold
deepr search query "AWS security" --top 10 --threshold 0.6

# JSON output for scripting
deepr search query "machine learning" --json
```

### Index Reports

```bash
# Index new reports for search
deepr search index

# Force re-index all reports
deepr search index --force

# View index statistics
deepr search stats

# Clear the index
deepr search clear
```

### Use Prior Research as Context

When submitting new research, Deepr automatically detects related prior research:

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

# With file uploads
deepr run focus "Question" --upload file1.pdf --upload file2.md --yes

# Using existing vector store
deepr run focus "Question" --vector-store company-docs --yes

# Choose model
deepr run focus "Question" --model o3-deep-research --yes
```

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

Adaptive campaigns that mirror human research workflows:

```bash
# Manual workflow (recommended)
deepr prep plan "Research goal" --topics 3
deepr prep execute --yes
deepr prep continue --topics 2
deepr prep continue --topics 1

# With human oversight
deepr prep plan "Goal" --review-before-execute
deepr prep review  # Approve/reject tasks
deepr prep execute

# Autonomous workflow
deepr prep auto "Research goal" --rounds 3
```

## Real-Time Progress

Track long-running research operations with live progress updates.

### Progress Tracking

```bash
# Wait for job with real-time progress display
deepr research wait abc123 --progress

# With custom poll interval (default 5s)
deepr research wait abc123 --progress --poll-interval 10

# Simple wait without progress UI
deepr research wait abc123 --timeout 600
```

**Progress phases:** queued → initializing → searching → analyzing → synthesizing → finalizing → completed

The progress display shows:
- Current phase with completion indicators
- Progress bar with percentage estimate
- Elapsed time
- Partial results preview (when available)

## Research Observability

Understand how research was conducted with trace inspection tools.

### Trace Commands

```bash
# View research path explanation
deepr research trace abc123 --explain

# Show reasoning evolution timeline
deepr research trace abc123 --timeline

# Show temporal knowledge timeline (findings & hypotheses)
deepr research trace abc123 --temporal

# Show context lineage (which sources informed which tasks)
deepr research trace abc123 --lineage

# Show token budget utilization
deepr research trace abc123 --show-budget

# Export complete audit trail
deepr research trace abc123 --full-trace -o trace.json
```

### Understanding Traces

**--explain:** Shows task hierarchy with model, cost, and context sources per operation. Also displays a **decision table** (type, decision, confidence, cost impact) when decision records are available.

**--timeline:** Rich table showing offset, task type, status, duration, and cost

**--temporal:** Findings discovered over time with confidence scores and hypothesis evolution

**--lineage:** Tree visualization of context flow (which documents/findings informed each task)

**--show-budget:** Token usage breakdown by phase with budget utilization percentage

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
# Run quick benchmark (single request per provider)
deepr providers benchmark --quick

# Full benchmark with latency percentiles
deepr providers benchmark

# View historical benchmark data
deepr providers benchmark --history

# JSON output for scripting
deepr providers benchmark --json
```

### Auto-Disable & Exploration

Deepr automatically:
- **Disables failing providers:** >50% failure rate triggers 1hr cooldown
- **Explores alternatives:** 10% of requests try non-primary providers to discover better options
- **Records metrics:** Latency percentiles (p50, p95, p99) and success rates by task type

View disabled providers with `deepr providers status`.

## Expert System

Create and interact with domain experts that can answer questions from uploaded documents.

### Create Expert

```bash
# Create expert from documents
deepr expert make "Azure Architect" --files docs/*.md

# Create a local-only expert profile with no provider API calls
deepr expert make "UI Experience Expert" --local --description "UI/UX for agentic research tools"

# Create with autonomous learning
deepr expert make "FDA Regulations" --files docs/*.pdf --learn --budget 10

# With description
deepr expert make "Supply Chain Expert" --files *.md --description "Logistics and supply chain domain"
```

### Preview Curriculum

```bash
# Preview what an expert would learn (no cost, no expert created)
deepr expert plan "Azure Architect"

# With budget constraint
deepr expert plan "Cloud Security" --budget 10

# Output as JSON or CSV
deepr expert plan "Kubernetes" --json
deepr expert plan "Kubernetes" --csv

# Just the prompts, one per line
deepr expert plan "FastAPI" -q

# Skip source discovery (faster)
deepr expert plan "React hooks" --no-discovery
```

### Manage Experts

```bash
# List all experts
deepr expert list

# Get expert details
deepr expert info "Azure Architect"

# Delete expert
deepr expert delete "Azure Architect" --yes
```

### Chat with Expert

```bash
# Basic Q&A
deepr expert chat "Azure Architect"

# With agentic research capability
deepr expert chat "Azure Architect" --budget 5  # agentic by default
```

### Agentic Chat Features

Expert chat is agentic by default; it supports slash commands, chat modes, visible reasoning, and more. The same features are available in both CLI and web. Pass `--no-research` to disable autonomous research triggers and stay in plain-chat mode.

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
```

Selects relevant experts, queries each in parallel, synthesizes agreements and disagreements.

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
deepr expert learn "Azure Architect" "Azure AI Agent Service 2026"

# Fill knowledge gaps proactively (ranked by EV/cost ratio)
deepr expert fill-gaps "Azure Architect" --budget 5 --top 3

# Resume paused learning
deepr expert resume "Azure Architect"

# Absorb a completed report into permanent beliefs (verification-gated, deduped)
# The free word-overlap heuristics only ROUTE; a cheap model verdict concludes -
# it drops phrasing-level false contradictions and refuses to merge two different
# facts that merely share words (e.g. "$10/M" vs "$30/M"). The result reports how
# many false positives the verdicts caught. Pass --no-... equivalents in code via
# verify_contradictions / verify_dedup to disable.
deepr expert absorb "Azure Architect" <job_id> --dry-run   # preview
deepr expert absorb "Azure Architect" <job_id>             # apply

# Reflect on a report before absorbing (grounding/completeness/calibration/directness)
deepr expert reflect "Azure Architect" <job_id> --depth 2
```

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
deepr expert sync "Azure Architect" -y
deepr expert loop-status "Azure Architect"
deepr expert loop-status "Azure Architect" --json

# Run the follow-up queries reflection emits for weak reports
deepr expert reflect "Azure Architect" <job_id> --execute-followups --budget 1 -y
```

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

# Browsable derived view: beliefs by domain, conflicts surfaced, byte-stable
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
# parsed as source text, then extraction, grounding, dedup, and contradiction
# gates decide what enters the belief store.
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

Persistent document indexes for reuse:

### Create Vector Store

```bash
# Create from files
deepr vector create --name "company-docs" --files docs/*.pdf

# With specific files
deepr vector create --name "legal" --files contract1.pdf contract2.pdf
```

**Supported formats:** PDF, DOCX, TXT, MD, code files

### Manage Vector Stores

```bash
# List all stores
deepr vector list

# Show details
deepr vector info <vector-store-id>

# Delete store
deepr vector delete <vector-store-id> --yes
```

### Using Vector Stores

```bash
# By ID
deepr run focus "Query" --vector-store vs_abc123 --yes

# By name
deepr run focus "Query" --vector-store company-docs --yes

# Or use the semantic research command
deepr research "Query" --vector-store company-docs
```

**Benefits:**
- Index once, use multiple times
- Significant cost savings
- Organized knowledge management

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

# Execution checks pause status automatically
deepr prep execute
```

## Safe Eval Workflow

```bash
# New models only, default $1 preflight cap
deepr eval new

# Estimate only
deepr eval new --dry-run --tier all

# Intentional larger run
deepr eval new --max-estimated-cost 3

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

Saved artifacts can feed admission directly:

```bash
deepr eval local --max-models 2 --max-prompts 2 --save
deepr capacity admit --from-eval latest --task-class sync --yes
deepr capacity admit qwen2.5:14b --from-eval data/benchmarks/local_compare_20260618_120000.json --task-class absorb
```

`--from-eval latest` resolves the newest `data/benchmarks/local_compare_*.json` artifact. Deepr only accepts zero-cost local eval artifacts, enforces score ranges, rejects failed prompt results, applies a default minimum score of `0.70`, and records the artifact summary in the machine-local admission ledger. Use `--min-score` to raise or lower the floor for a specific admission.

Automatic local routing now uses the admitted score as runtime quality evidence. A scoreless manual admission is still visible in `deepr capacity admissions`, but it does not take over `expert sync` or `expert absorb` automatically because it cannot clear the measured quality floor. Use `--local` when you want an explicit one-off override.

CLI judges are supported for plan or subscription tools when the operator explicitly approves them with `--allow-cli-judge`. The Grok preset expands to a headless prompt-file command; custom commands must include `{prompt_file}` and run with `shell=False`. Deepr still records metered cost `$0`, but the external CLI may consume its own quota or credits, so this path is never auto-selected.

### Evidence Evals (Continuity and Calibration)

Two evals make expert trust measurable instead of asserted.

```bash
# Continuity: staleness honesty, abstention, contradiction-surfacing,
# what-changed exactness - measured from stored belief state at $0.
deepr eval continuity "AI Policy Expert"

# Calibration: does extraction confidence track grounding?
# Reliability curve + expected calibration error + Platt-derived threshold.
deepr eval calibrate --from data/calibration/graded.jsonl   # $0, grades existing pairs

# Run the paid extraction + strong-model pre-grade over a corpus.
deepr eval calibrate --corpus tests/data/calibration \
  --grader-model gpt-5 --sample 50 --max-cost 3 --yes
```

Calibration uses FActScore/SAFE-style atomic claim decomposition and a strong-model grader; the threshold fit is numpy Platt scaling (no sklearn). The first measured curve is in [CALIBRATION.md](CALIBRATION.md); the deterministic-vs-model check boundary is in [design/checks-deterministic-vs-agentic.md](design/checks-deterministic-vs-agentic.md).

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
deepr capacity next       # ranked next actions for making cheap capacity usable
deepr capacity next --task-class sync --context-mode fresh --scheduled
deepr expert sync "Platform Team Expert" --scheduled --fresh-context -y
deepr expert route-gaps "Platform Team Expert" --execute --scheduled --json
deepr expert reflect "Platform Team Expert" <job_id> --execute-followups --scheduled --json
deepr expert health-check "Platform Team Expert" --scheduled --json
deepr capacity --json
```

`deepr init` writes `DEEPR_DATA_DIR` (and `DEEPR_EXPERTS_PATH` / `DEEPR_REPORTS_PATH`). Pointing the data dir at a synced folder (OneDrive, Dropbox, iCloud) makes experts and research follow you across machines; cost ledger, queue, and traces stay machine-local ([ADR 0004](decisions/0004-one-experts-root-and-portable-data-dir.md)).

Capacity source status:

| Source | Status | Notes |
|---|---|---|
| Local Ollama | Execution works for local expert setup, local sync, deep/fresh local context, local absorb, local eval, local context eval, and scored admission | `$0` marginal cost, quality-gated before automatic routing |
| OpenAI, Gemini, Grok, Anthropic, Azure APIs | Execution works when configured with API keys and budget ceilings | Full research path, cost ledger writes every spend source |
| Claude Code, Codex, Antigravity, Grok Build, GitHub Copilot CLI, Kiro, and other plan CLIs | Visible or modeled, not execution backends yet | Adapter work must include auth-mode detection, quota probes, no-overage checks, and tests |
| CLI judge for local eval | Explicit opt-in only | `--allow-cli-judge` is required because Deepr cannot prove the vendor CLI's billing source |

Local-model execution runs quality-tolerant steps at $0 against a local Ollama endpoint. Force it with `--local`, force the metered API with `--api`, or admit a local model so maintenance uses it automatically (owned capacity before metered API):

```bash
deepr expert make "Platform Team Expert" --local -d "Platform engineering knowledge"
deepr expert absorb "Platform Team Expert" report.md --local   # force local, $0
deepr expert sync "Platform Team Expert" --api                 # force metered API
deepr expert sync "Platform Team Expert" --local --fresh-context # local model + free retrieval context
deepr expert sync "Platform Team Expert" --local --deep-context  # multi-query free retrieval context

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

`deepr capacity next` is the guided path when the safe cheap route is not ready. It ranks the current block reason, local setup commands, latest usable eval-artifact admission, eval refresh, scheduled-job wait guidance, and explicit metered fallback. It can preview a concrete job shape with `--expert`, `--report-id`, `--context-mode none|fresh|deep`, and `--scheduled`. It is read-only, runs no research, and makes no provider API calls. `deepr expert sync --scheduled` consumes the same preview automatically for due subscription syncs: when a recurring job would otherwise fall through to metered API, or when fresh/deep context needs local capacity, it exits successfully with a wait payload and next actions instead of spending. `deepr expert route-gaps --execute --scheduled` uses the same scheduler default for gap-fill sweeps by returning pending routes and a wait state instead of starting metered research. `deepr expert reflect --scheduled` waits before constructing the reflection evaluator, so recurring reflection follow-up jobs expose pending evaluation and follow-up work without making a metered call. `deepr expert health-check --scheduled` returns a scheduler action plan that separates metered recommendations, confirmation-gated local writes, and ready local actions. These scheduled JSON payloads include `loop_run` records viewable through `deepr expert loop-status`.

Local models do not automatically have current web context. For sync runs that
need freshness, add `--fresh-context`; for broader source coverage, add
`--deep-context`. Both require a local sync backend, either explicit `--local`
or an admitted local model, so a freshness request cannot silently fall through
to metered APIs. Deepr builds a bounded source pack first, then prepends it to
the local prompt and asks the model to cite source labels. This path is
free-only inside Deepr: it can fetch explicit URLs, can use a configured
self-hosted SearXNG endpoint (`DEEPR_SEARXNG_URL`), and otherwise can use
DuckDuckGo when `duckduckgo-search` is installed. It does not use Brave, Tavily,
or other API-key search providers. If no fresh sources are available, the
prompt tells the local model to say that current context is unavailable, and
sync records no changes instead of absorbing that uncertainty as permanent
beliefs.

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

Plan-quota adapters are still being wired. `deepr capacity` can detect or model the relevant CLIs and show the cost model, but Deepr does not execute work through those plan quotas yet. Their routing gates are already defined: selection orders local, plan-quota, and metered backends, then blocks execution on missing or unknown quota, exhaustion, quarantine, overage, reserve-floor breaches, unsupported task classes, missing measured quality, and metered fallback without a budget gate.

The intended QOL is simple: ask for a job, see the cheapest safe route, and get a
clear reason if Deepr should wait rather than pay. `deepr capacity next` is
read-only today and now accepts enough job context to preview sync context mode
and recurring scheduler intent. `deepr expert sync --scheduled` now consumes
that preview before launching due subscription syncs. `route-gaps --execute
--scheduled` now gives gap-fill sweeps the same no-surprise-spend wait behavior.
`expert reflect --scheduled` waits before reflection evaluation and follow-up
research until cheap evaluator capacity exists or the operator chooses a one-off
metered run. `expert health-check --scheduled` adds an action plan, and
`--archive-stale --scheduled` waits for confirmation instead of prompting or
mutating unless `--yes` is explicit. These scheduled wait/action-plan payloads
append `ExpertLoopRun` snapshots and include `loop_run` JSON. Successful-run
instrumentation now covers `deepr expert sync`, non-dry `deepr expert
route-gaps --execute`, `deepr expert reflect`, `deepr expert health-check`, and
confirmed `--archive-stale`; these append loop snapshots with spend, capacity
source, verifier outcome, accepted-change metrics where applicable, and typed
stop actions when work fails, waits on a human gate, has no corrective work,
fails the verifier, or exhausts the run budget. The dashboard API now exposes
`/api/experts/{name}/loop-status`, a read-only rollup over those records with
latest run, last sync result, next scheduled action, failure, capacity source,
spend, acceptance, verifier failure metrics, and `expert_state` telemetry for
freshness, gap velocity, and contested/open claims. Host agents can already
read the durable loop state through `deepr_expert_loop_status`. Terminal loop
records now require status-compatible typed stop reasons before they can be
stored. The dashboard API also exposes `admission_contracts` for repeat demand,
automated verification, explicit budget/capacity, and failure-diagnosis state.
For downstream agents that need one stable read contract before choosing a more
specific tool, `/api/experts/{name}/handoff` and MCP `deepr_expert_handoff`
return the versioned `deepr-expert-handoff-v1` payload: profile summary,
manifest counts, bounded claims/gaps, dashboard telemetry, loop-status rollup,
OKF interchange hints, and an additive compatibility contract. The schema is
published at [schemas/expert-handoff-v1.json](schemas/expert-handoff-v1.json).
The adjacent loop-status and OKF mapping contracts are published as
[schemas/loop-status-v1.json](schemas/loop-status-v1.json) and
[schemas/okf-profile-v1.json](schemas/okf-profile-v1.json), with the
machine-readable registry in [schemas/registry.json](schemas/registry.json).
The MCP HTTP transport also has an experimental scoped-key primitive:
configured key stores authenticate Bearer or `X-Api-Key` requests, enforce
key mode, expert allowlists, confirmation gates, per-key budget ceilings, and
per-key rate limits before `tools/call` dispatch, and append
`deepr-mcp-remote-audit-v1` records for remote calls with response cost
attribution when available.
Use `deepr mcp keys create/list/revoke` to manage those local key records, and
`deepr mcp audit list` to review the local append-only remote-call audit log
with key, tool, outcome, limit, and JSON filters. Use `deepr mcp serve --http`
to run the same MCP server over HTTP/SSE on loopback by default. Use
`deepr mcp smoke-http URL` to run `$0` health, initialize, tools/list, and free
tool-search checks against a local or TLS-proxied HTTP MCP endpoint. A
repeatable hosted container recipe lives in
[../deploy/mcp-http/](../deploy/mcp-http/); it publishes only loopback by
default, mounts one Deepr data directory at `/data`, and bootstraps scoped keys
before the service starts.

See [design/capacity-waterfall.md](design/capacity-waterfall.md) for the capacity model and [design/local-fresh-context.md](design/local-fresh-context.md) for the fresh-context loop.

## Cost Management

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
# Export to markdown (default)
deepr jobs export <job-id>

# Specific format
deepr jobs export <job-id> --format json
deepr jobs export <job-id> --format html
deepr jobs export <job-id> --format txt

# Custom output
deepr jobs export <job-id> --format html --output report.html
```

**Formats:**
- `markdown` - Markdown with citations
- `txt` - Plain text
- `json` - Structured JSON with metadata
- `html` - Formatted HTML report

### Cancel Jobs

```bash
# Cancel running job
deepr jobs cancel <job-id>
deepr jobs cancel <job-id> --yes
```

## Command Reference

### Global Options

```bash
deepr --version    # Show version
deepr -h           # Short help
deepr --help       # Full help
```

### Semantic Commands (Primary Interface)

```bash
deepr research     # Research with auto-mode detection
deepr learn        # Multi-phase structured learning
deepr team         # Multi-perspective analysis
deepr check        # Fact verification
deepr make docs    # Generate documentation
deepr make strategy # Strategic analysis
deepr expert       # Domain expert management
deepr skill        # Expert skill management
```

### Supporting Commands

```bash
deepr run          # Low-level research modes (focus, docs, project, team)
deepr jobs         # Job management (list, status, get, cancel)
deepr vector       # Vector store management
deepr prep         # Campaign management
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
# Create persistent store, use for research
deepr vector create --name "docs" --files *.pdf
deepr research "Query" --vector-store docs

# Create expert from documents
deepr expert make "Domain Expert" --files docs/*.md
deepr expert chat "Domain Expert" --budget 5  # agentic by default

# Batch operations
deepr jobs list --status completed
```

### Automation

```bash
# Daily batch job
deepr jobs list --status pending

# Cost monitoring
deepr costs show
```

### Best Practices

1. **Use semantic commands** for intuitive workflows
2. **Create experts** for document-based Q&A
3. **Monitor costs** regularly with analytics
4. **Use pause/resume** for expensive campaigns
5. **Validate config** with `deepr doctor`
6. **Export important results** in multiple formats

## Integration Patterns

### CI/CD Integration

```bash
# In CI pipeline - use run command for direct control
deepr run focus "Release notes for v2.3" --yes
# Check job status
deepr jobs list --status completed
```

### Batch Processing

```bash
# Process multiple queries
for query in "query1" "query2" "query3"; do
  deepr research "$query" --yes
done

# Check results
deepr jobs list
```

### Knowledge Management

```bash
# Build expert from knowledge base
deepr expert make "KB Expert" --files knowledge_base/*.md
deepr expert chat "KB Expert"
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

- Read [INSTALL.md](../INSTALL.md) for setup
- See [ROADMAP.md](../ROADMAP.md) for upcoming features
- Check [CHANGELOG.md](../CHANGELOG.md) for latest changes
- Visit [README.md](../README.md) for quick start
