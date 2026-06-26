# Expert System Guide

> **Note**: Model names and capabilities live in the registry (`../deepr/providers/registry.py`), the single source of truth. AI moves fast - verify at provider websites.

## Overview

Deepr's expert system creates domain experts from documents that can answer questions, recognize knowledge gaps, and autonomously research to fill them.
Expert learning is not passive document accumulation. New material is processed
into canonical beliefs, concepts, hypotheses, stance, provenance refs, temporal
graph edges, contradiction signals, gap backlogs, freshness watchlists, and
regenerated digest or handoff views.

## What Makes It Different

Traditional RAG systems:
- Static documents in vector store
- Query - retrieve - answer
- Never changes, never grows

Deepr experts:
- Recognize knowledge gaps
- Can trigger research when needed
- Integrate new knowledge permanently
- Track what they know vs don't know
- Maintain concepts, hypotheses, stance, and tradeoffs
- Keep up with current developments on their topic
- Explore new possibilities instead of only recalling stored claims
- Build on previous learning

## Quick Start

```bash
# Create expert from documents
deepr expert make "Azure Architect" --files docs/*.md

# Create a local-only expert profile with no provider API calls
deepr expert make "UI Experience Expert" --local -d "UI/UX for agentic research tools"

# Chat with expert
deepr expert chat "Azure Architect"

# Chat with research capability
deepr expert chat "Azure Architect" --budget 5  # agentic by default
```

## Creating Experts

### Basic Creation
```bash
deepr expert make "Expert Name" --files path/to/docs/*.md
```

### Local-Only Creation
```bash
deepr expert make "Expert Name" --local -d "Domain description"
deepr expert subscribe "Expert Name" "Domain topic"
deepr expert sync "Expert Name" --local --fresh-context -y
deepr expert sync "Expert Name" --local --deep-context -y
```

`--local` creates the expert profile and local document folders without
creating a provider vector store or uploading files. If you pass `--files`,
Deepr copies the seed documents into the expert's local documents folder and
records them in the profile. Local creation does not run the API-backed
`--learn` curriculum; use subscriptions plus `expert sync --local` for $0
maintenance.

Use `--fresh-context` when a local sync needs current web grounding. Use
`--deep-context` when the topic needs broader source coverage before the local
model synthesizes. Both modes stay free inside Deepr: explicit URLs are fetched,
`DEEPR_SEARXNG_URL` can point at a self-hosted SearXNG instance, and DuckDuckGo
is used only when the optional package is installed. API-key search backends are
not used.

### With Autonomous Learning
```bash
deepr expert make "FDA Regulations" \
  --files docs/*.pdf \
  --learn \
  --budget 10 \
  --topics 10
```

This will:
1. Upload documents to vector store
2. Generate a learning curriculum (GPT-5.2)
3. Research each topic autonomously
4. Integrate findings into expert's knowledge

### Learning Curriculum

When using `--learn`, GPT-5.2 generates a curriculum:

```
Learning Curriculum (10 topics):
1. FDA 510(k) clearance process     Est: $0.20, 10 min
2. Pre-market approval requirements Est: $0.25, 12 min
3. Quality system regulations       Est: $0.15, 8 min
...

Total: $2.45
Budget limit: $10.00  WITHIN BUDGET

Proceed? [y/N]
```

## Expert Chat

### Basic Q&A
```bash
deepr expert chat "Azure Architect"
```

Expert searches its knowledge base and answers from documents.

### Agentic Mode
```bash
deepr expert chat "Azure Architect" --budget 5  # agentic by default
```

Expert can trigger research when it recognizes knowledge gaps:

```
You: How should we handle OneLake security for multi-tenant SaaS?

Expert: "I don't have specific guidance on this. Let me research..."

[Triggers: standard_research "OneLake multi-tenant security SaaS"]
[Cost: $0.15]

Expert: "Based on my research, there are three approaches:
1. Workspace-per-tenant isolation
2. Lakehouse-per-tenant with RLS
3. Shared lakehouse with strict RLS
..."
```

### Research Tiers

Experts choose appropriate research depth:

| Tier | Cost | Time | Use Case |
|------|------|------|----------|
| `quick_lookup` | FREE | <5s | Simple factual questions |
| `standard_research` | $0.01-0.05 | 30-60s | Moderate complexity |
| `deep_research` | $0.10-0.30 | 5-20 min | Complex topics |

### Slash Commands and Chat Modes

Agentic chat supports 27 slash commands (use `/` in web, `\` in CLI). Chat modes control the expert's behavior:

- **`/ask`** - Quick answers from knowledge base only
- **`/research`** - Default mode with all tools available
- **`/advise`** - Structured consulting recommendations with pros/cons
- **`/focus`** - Always-on chain-of-thought reasoning for complex analysis

Other useful commands:
- `/compact` - Summarize earlier messages to free token budget for longer sessions
- `/council "question"` - Consult multiple experts on cross-domain questions (see Expert Council below)
- `/plan "question"` - Break complex queries into parallel subtasks with live progress
- `/remember <text>` - Pin facts to the session context
- `/status` - Show session stats (messages, tokens, mode, budget remaining)
- `/help` - List all available commands

### Approval Flows

Expensive operations require approval before proceeding. The system uses three tiers:

| Tier | Behavior | Example |
|------|----------|---------|
| Auto-approve | Proceeds immediately | KB search, standard research |
| Notify | Shows cost, proceeds unless budget critically low | Deep research under $1 |
| Confirm | Blocks until user approves or denies | Deep research over $1, council over $3 |

In the web UI, confirmation appears as an inline card in the chat. In CLI, it's a simple y/n prompt.

### Context Compaction

Long conversations can exhaust the model's token budget. The `/compact` command summarizes earlier messages while keeping recent context intact:

```
/compact
# Compacted: 32 messages -> summary (kept last 4 messages)
```

The system suggests compaction automatically after 30+ messages or when estimated tokens exceed 80K.

## Preview a Curriculum

Before creating an expert with `--learn`, preview what it would research:

```bash
# See the full research plan (no expert created, no cost)
deepr expert plan "Azure Architect"

# Budget-constrained plan
deepr expert plan "Cloud Security" --budget 10

# JSON output for scripting
deepr expert plan "Kubernetes" --json

# Just the prompts
deepr expert plan "FastAPI" -q
```

## Managing Experts

```bash
# List all experts
deepr expert list

# Get expert details
deepr expert info "Azure Architect"

# Delete expert
deepr expert delete "Azure Architect" --yes
```

## Updating Knowledge

### Manual Learning
```bash
# Research a topic and add to expert
deepr expert learn "Azure Architect" "Azure AI Agent Service 2026"

# Upload additional files
deepr expert learn "Azure Architect" --files new_docs/*.md
```

### Fill Knowledge Gaps
```bash
# Expert identifies and researches its gaps
deepr expert fill-gaps "Azure Architect" --budget 5 --top 3
```

### Resume Paused Learning
```bash
# If learning hit budget limits
deepr expert resume "Azure Architect"
```

### Absorb a Report into Knowledge
Promote a completed research report into the expert's permanent beliefs instead
of leaving it a terminal artifact. Verification-gated: report-grounded claims are
extracted and weak claims dropped. The free word-overlap heuristics only *route*
- a cheap model verdict concludes, so phrasing-level false contradictions are not
recorded as contested beliefs and two different facts that merely share words
(e.g. "$10/M" vs "$30/M") are not silently merged. Genuine conflicts are flagged
contested (the existing belief is never overwritten without approval); the rest
are integrated (deduped) with the report id as provenance.
```bash
# Preview what would be absorbed (writes nothing)
deepr expert absorb "Azure Architect" <job_id> --dry-run

# Absorb (REPORT_ID is the job id, same one you pass to --context; see deepr search)
deepr expert absorb "Azure Architect" <job_id> --min-confidence 0.7
```

### Reflect on a Report (quality gate)
Self-evaluate a report against its question before relying on or absorbing it:
scores grounding, completeness, calibration, and directness, then returns a
verdict (accept / revise / re-research) with issues and follow-up queries. A
natural pre-step to `absorb`. Costs one small evaluation call.
```bash
deepr expert reflect "Azure Architect" <job_id>
deepr expert reflect "Azure Architect" <job_id> --depth 2 --json
```

## Knowledge Maintenance

### Health Check
Read-only, cost-$0 audit of an expert's knowledge state: freshness, belief
contradictions, claims missing source provenance, decayed beliefs, lifecycle
archive candidates, the open-gap backlog, and documents ingested but never
synthesized. Prints findings plus a recommended-action menu (each action shows
its command, estimated cost, and the approval tier that would gate it).
Schedulable for periodic self-maintenance.
```bash
deepr expert health-check "Azure Architect"
deepr expert health-check "Azure Architect" --json   # structured, for agents
```

### Lifecycle Archival (consolidation pass)
Belief stores must not grow monotonically - the documented root failure mode
of agent memory. The audit lists beliefs eligible for archival, and
`--archive-stale` archives them ($0, no LLM). A belief qualifies only if it
passes every gate: decayed below the confidence floor, not updated or
re-evidenced in 90+ days, no recorded usage, and not a side of an open
contradiction (contested beliefs are signal, never garbage). Every archival is
event-logged with a full snapshot, so it is reversible belief-by-belief.
```bash
deepr expert health-check "Azure Architect" --archive-stale     # confirm first
deepr expert health-check "Azure Architect" --archive-stale -y  # no prompt
```
Design: [docs/design/belief-lifecycle.md](design/belief-lifecycle.md).

### Route Gaps to Instruments (and Execute the Fills)
Advisory by default (read-only, $0): map each open knowledge gap to the best
instrument to fill it - recon (infrastructure), distillr (academic), primr
(strategic), or general research (default) - with availability, cost estimate,
and rationale. With `--execute`, the highest-value research-route fills
actually run (budget-bounded, skip-not-fail) and their findings absorb through
the verification-gated pipeline. Specialist-instrument routes are deliberately
deferred with their command printed - paid multi-minute jobs never start as a
side effect of a sweep.
```bash
deepr expert route-gaps "Azure Architect"
deepr expert route-gaps "Azure Architect" --execute --dry-run    # preview, $0
deepr expert route-gaps "Azure Architect" --execute --budget 1 -y
```

### Stay Current: Subscriptions and Sync
Subscribe an expert to topics with a refresh cadence and per-sync budget; sync
researches only what is DUE with a delta-only prompt ("what changed since the
last sync; if nothing meaningful, say exactly so"), absorbs through the
verification gate, and reports the perspective delta. Idempotent per cadence
window - run it from cron or a host platform's scheduler and only due topics
spend money. A "no significant changes" answer skips the paid extraction.
```bash
deepr expert subscribe "Azure Architect" "Azure Landing Zone updates" --every 7 --budget 0.50
deepr expert subscriptions "Azure Architect"          # list, with due markers
deepr expert sync "Azure Architect" --dry-run         # preview, $0
deepr expert sync "Azure Architect" -y                # run due topics
```

### Auto Re-Research from Reflection
When `expert reflect` finds a report weak, it emits follow-up queries. With
`--execute-followups` they actually run (same budget discipline) and absorb -
reflection stops being advisory exactly when the report needs reinforcement.
```bash
deepr expert reflect "Azure Architect" <job_id> --execute-followups --budget 1 -y
```

## Temporal Perspective Queries

A corpus is what was read; a perspective is what is *believed* - claims with
calibrated confidence, provenance, recency, and open conflicts. Three
read-side, cost-$0 queries expose the perspective (CLI and MCP):

### What Changed (re-sync)
The perspective delta since a timestamp: beliefs added / revised / contested /
archived, each with its reason and current snapshot. The cheap way for you (or
a host agent) to catch up with an expert instead of re-reading everything.
Exact with no window limit on stores with the belief event log.
```bash
deepr expert what-changed "Azure Architect" --since 7d
deepr expert what-changed "Azure Architect" --since 2026-06-01 --json
```

### Contested (open conflicts)
Open contradiction pairs with both sides' claims, confidence, and provenance -
live conflicts surfaced deliberately, never smoothed into a narrative.
Resolution stays with `expert resolve-conflicts`.
```bash
deepr expert contested "Azure Architect"
```

### Why (introspection)
Why the expert believes something: evidence roots, the confidence trajectory
from the append-only event log, supporting/derived-from chains walked over the
typed belief graph, and any open contradictions. Accepts a belief id or claim
text (fuzzy matched). Use it to debug trust in a claim instead of taking the
confidence number on faith.
```bash
deepr expert why "Azure Architect" "landing zone subscription vending"
deepr expert why "Azure Architect" belief-a1b2c3 --depth 3 --json
```

### Self-Model (read-only current state)
Build a derived `deepr-expert-self-model-v1` record from the profile and
manifest. It reports capabilities, limits, current goals, calibration, learning
strategy, continuity, blockers, unresolved risks, and a bounded current-focus
packet for consults, sync learning loop records, and sync capacity waits. It
does not change goals, write expert state, or run a model.
```bash
deepr expert self-model "Azure Architect"
deepr expert self-model "Azure Architect" --focus-limit 3 --json
```

### Monitor (read-only proposal review)
Build a derived `deepr-metacognitive-monitor-v1` artifact from the self-model,
recent loop runs, and sanitized consult trace candidates. It emits
`review_required` proposals for self-model blockers, calibration review, failed
learning loops, capacity blocks, and gap/eval candidates. It does not apply
goal, strategy, prompt, tool, or skill changes.
```bash
deepr expert monitor "Azure Architect"
deepr expert monitor "Azure Architect" --json
```

### Promote Monitor Proposals (reviewed gap/eval promotion)
Preview or apply one selected monitor proposal. Preview is the default and
writes nothing. `--apply` is required to promote a `gap_or_eval_candidate` into
the metacognition gap backlog, a local eval-case artifact under
`data/benchmarks`, or both. Other proposal types stay review-only until their
own verifier-gated commands exist.
```bash
deepr expert promote-monitor "Azure Architect" meta_abc123 --target gap
deepr expert promote-monitor "Azure Architect" meta_abc123 --target gap --apply
deepr expert promote-monitor "Azure Architect" meta_abc123 --target eval --apply --json
deepr expert promote-monitor "Azure Architect" meta_abc123 --target both --apply
```

### Propose Self-Model Updates (review record)
Preview or write a verifier-gated self-model update review record for a
self-model-related monitor proposal. The command costs `$0`, never calls a
model, and never mutates the derived self-model. `--apply` writes an append-only
`deepr-expert-self-model-update-v1` artifact only after deterministic gates pass
for proposal type, target path, evidence refs, human review, zero cost, no
authority expansion, and no derived self-model mutation.
```bash
deepr expert propose-self-model "Azure Architect" meta_def456
deepr expert propose-self-model "Azure Architect" meta_def456 --apply --json
```

### Accept Self-Model Updates (outcome evidence gate)
Preview or write a separate acceptance artifact for a recorded self-model
update. Acceptance requires explicit outcome evidence refs such as
`loop_run:...`, `eval:...`, `source_pack:...`, or `human_review:...`, plus a
reviewer. `--apply` writes `deepr-expert-self-model-update-acceptance-v1`;
accepted records are later attached to sync loop-run context as read-only
guidance. They do not grant new authority or mutate the derived self-model.
```bash
deepr expert accept-self-model "Azure Architect" data/self_model_updates/azure-architect/self_model_update_meta_def456_20260626_120000000000.json --outcome-evidence loop_run:loop_123 --reviewer operator
deepr expert accept-self-model "Azure Architect" data/self_model_updates/azure-architect/self_model_update_meta_def456_20260626_120000000000.json --outcome-evidence loop_run:loop_123 --outcome-evidence human_review:review_1 --reviewer operator --apply --json
```

### Digest (browsable derived view)
Compile the belief store into a browsable Markdown digest: beliefs by domain
sorted by confidence, open contradictions with both sides, graph stats. $0, no
LLM call, byte-stable for an unchanged store. The digest is a derived view -
the belief store stays canonical, and the CLI refuses to overwrite a digest
that lost its derived-view marker (a hand-edited artifact must never silently
become canonical knowledge).
```bash
deepr expert digest "Azure Architect"            # writes <knowledge dir>/digest.md
deepr expert digest "Azure Architect" --print
```

## Sharing Experts as Skills

Package an expert as an installable agentskills.io SKILL.md for any compatible
host (Claude Code, Codex CLI, Gemini CLI, VS Code Copilot, Cursor, OpenClaw).
The skill triggers on the expert's domain and consults it through Deepr's MCP
tools - so the host needs a running Deepr MCP server with this expert present.
```bash
deepr expert export-skill "Azure Architect"                 # -> ./skills/deepr-expert-azure-architect/SKILL.md
deepr expert export-skill "Azure Architect" -o ~/.claude/skills/azure
deepr expert export-skill "Azure Architect" --print         # preview to stdout
```

## Export/Import

### Export for Sharing
```bash
deepr expert export "Azure Architect" --output ./exports/
```

Creates a portable package:
- Documents
- Worldview/beliefs
- Metadata
- README

### Import Expert
```bash
deepr expert import "New Expert" --corpus ./exports/azure_architect/
```

## Expert Skills

Skills are domain-specific capability packages that give experts unique tools and reasoning. A "Financial Analyst" expert with the `financial-data` skill can calculate ratios; a "Dev Lead" with `code-analysis` can audit dependencies and measure complexity.

### Managing Skills

```bash
# List all available skills
deepr skill list

# List skills on a specific expert
deepr skill list "Financial Analyst"

# Install a skill
deepr skill install "Financial Analyst" financial-data

# Remove a skill
deepr skill remove "Financial Analyst" financial-data

# Show skill details
deepr skill info code-analysis

# Run a skill tool directly
deepr expert run-skill "Dev Lead" code-analysis complexity_report --args '{"code": "def foo(): pass"}'
```

### Creating Custom Skills

```bash
# Scaffold a new skill in ~/.src/deepr/skills/
deepr skill create my-custom-skill
```

This creates:
- `skill.yaml` - metadata, triggers, tool definitions
- `prompt.md` - domain-specific reasoning instructions
- `tools/` - Python tool implementations

Before writing one, read [docs/design/skill-authoring.md](design/skill-authoring.md) -
how to make a skill measurably good: narrow scope, trigger-style descriptions,
deterministic `tools/` (never a meaning-verdict), a verification-first design, and
a `## Gotchas` section seeded from real failures.

### Built-in Skills

| Skill | Tools | Purpose |
|-------|-------|---------|
| `web-search-enhanced` | `structured_extract` | Extract tables/facts from research text |
| `code-analysis` | `analyze_dependencies`, `complexity_report` | Dependency audit + cyclomatic complexity |
| `financial-data` | `calculate_ratios` | P/E, P/B, debt-to-equity, ROE, margins |
| `data-visualization` | `markdown_table`, `ascii_chart` | Format data as tables and charts |

### How Skills Work

- **Progressive disclosure**: Skill summaries are always visible in the expert's system prompt. Full prompt and tools load only when a skill activates.
- **Auto-activation**: Skills activate when user queries match keyword or regex triggers.
- **Three-tier storage**: Built-in skills ship with Deepr, user skills live in `~/.src/deepr/skills/`, expert-local skills in `data/experts/{name}/skills/`. Later tiers override earlier ones.
- **MCP bridging**: Skills can connect experts to external MCP servers for tools no generic expert would have.

### Skill Definition Format

```yaml
name: my-skill
version: "1.0.0"
description: "What this skill does"
domains: ["finance", "analysis"]
triggers:
  keywords: ["earnings", "P/E ratio"]
  patterns: ["compare .+ stocks"]
prompt_file: "prompt.md"
tools:
  - name: my_tool
    type: python          # or "mcp" for external servers
    module: tools.my_tool
    function: run
    description: "What this tool does"
    cost_tier: free       # free/low/medium/high
budget:
  max_per_call: 0.50
  default_budget: 2.00
```

## Architecture

### Components

```
src/deepr/core/
├── contracts.py    # Canonical types: Claim, Gap, DecisionRecord, ExpertManifest, Source

src/deepr/experts/
├── profile.py      # Expert metadata, usage tracking, get_manifest()
├── curriculum.py   # Learning plan generation
├── learner.py      # Autonomous learning execution
├── chat.py         # Interactive Q&A with streaming, modes, compaction
├── commands.py     # Command registry, ChatMode, MODE_CONFIGS
├── command_handlers.py # 27 slash command handler functions
├── approval.py     # ApprovalManager with three-tier policies
├── council.py      # Multi-expert consultation and synthesis
├── task_planner.py # Hierarchical task decomposition
├── portraits.py    # AI-generated SVG expert portraits
├── constants.py    # Shared model names, tool identifiers, budget fractions
├── router.py       # Model selection
├── beliefs.py      # Belief formation, to_claim() adapter
├── metacognition.py # Gap awareness, to_gap() adapter
├── memory.py       # Conversation memory
├── synthesis.py    # Knowledge synthesis, to_claim()/to_gap() adapters
├── gap_scorer.py   # EV/cost ranking for knowledge gaps
├── thought_stream.py # Decision records, reasoning traces (with callbacks)
├── cost_safety.py  # Budget controls
└── skills/         # Expert skills system
    ├── definition.py  # SkillDefinition, SkillTool, SkillTrigger
    ├── manager.py     # Discovery, indexing, trigger matching
    └── executor.py    # Python + MCP tool execution
```

### Knowledge Storage

```
data/experts/<name>/
├── profile.json        # Expert metadata
├── documents/          # Source documents
├── knowledge/
│   ├── worldview.json  # Synthesized beliefs
│   ├── gaps.json       # Known knowledge gaps
│   └── learning_progress.json
└── conversations/      # Chat history
```

## Beginner's Mind Philosophy

Experts are prompted with intellectual humility:

1. **Admit gaps**: Say "I don't know" when uncertain
2. **Source transparency**: Distinguish knowledge sources
3. **Research-first**: Research instead of guessing
4. **Question assumptions**: Verify potentially outdated info
5. **Depth over breadth**: Better to research deeply than answer superficially

## Budget Protection

Multiple layers prevent runaway costs:

### Per-Session Limits
```bash
deepr expert chat "Name" --budget 5  # agentic by default; pass --no-research to disable
```

### Hard Limits (Cannot Override)
- Per operation: $10 max
- Per day: $50 max
- Per month: $500 max

### Pause/Resume
When learning hits limits, progress is saved:
```bash
# Resume next day
deepr expert resume "Azure Architect"
```

See [ARCHITECTURE.md](ARCHITECTURE.md#security) for full budget protection details.

## Advanced Features

### Claims and Confidence

Experts track structured **claims** - atomic assertions with confidence scores, source provenance, and contradiction tracking. Claims are canonical types defined in `core/contracts.py`:

- Each claim has a confidence score (0.0-1.0) with time-based decay
- Sources carry a `TrustClass` (primary, secondary, tertiary, self_generated) and content hash
- Claims track contradictions and supersession chains
- View claims via web API: `GET /api/experts/<name>/claims?min_confidence=0.7`

**Source-trust ceilings (deterministic, applied at read time like decay):**
a belief's displayed confidence is capped by its provenance tier, and no model
judgment can lift the cap - only new, better-sourced evidence can.

| Trust tier | Ceiling | Typical sources |
|---|---|---|
| tertiary, one source | 0.60 | web search results, research syntheses (the default) |
| tertiary, 2+ independent sources | 0.80 | the same claim absorbed from different reports |
| secondary / primary | uncapped | official docs, first-party instruments / operator-supplied documents |

This is also the deterministic backstop against ingestion-time prompt
injection: a single poisoned web result cannot mint a near-certain belief, no
matter how confidently the extraction rates it. Honest framing throughout:
extraction confidence means "how strongly this report supports the claim",
never "how likely the claim is true" - calibration evidence for those numbers
is the v2.15 harness (see docs/design/calibration-and-trust.md).

Untrusted source and tool text is also bounded before it reaches model prompts:
fresh retrieval snippets, report text passed into absorption, first-party tool
findings, local document previews, prior campaign reports, completed research
summaries, company-intelligence snippets, and team findings are sanitized and
delimited as source data, not instructions. That boundary does not decide truth.
It only prevents embedded directives from blending into the instruction
hierarchy while the existing extraction, grounding, contradiction, dedup, and
trust-floor gates decide what becomes a belief.

Run `deepr eval red-team` to exercise the current local `$0` adversarial
canaries for those boundaries. The suite reports attack-success-rate for
prompt-boundary, MCP handoff and loop-status read-path, tool-spoofing, and
trust-floor probes, fails if a built-in attack succeeds, and can save a local
trend artifact with `--save`.

**Storage (the temporal knowledge graph):** the belief store is canonical  - 
`beliefs.json` (claims + typed edges: supports / contradicts / enables /
derived_from) plus an append-only `events.jsonl` recording every change.
Everything else (digest, SKILL.md export, reports) is a derived, regenerable
view.

### Knowledge Gap Scoring

Gaps are prioritized by **EV/cost ratio** - expected value relative to the estimated cost to fill:

```
ev_cost_ratio = expected_value / estimated_cost
expected_value = (priority / 5.0) + frequency_boost
estimated_cost = domain velocity lookup (fast=$0.25, medium=$1.00, slow=$2.00)
```

Higher-ratio gaps are filled first, making `expert fill-gaps --top N` a rational allocation rather than arbitrary ordering.

### Decision Records

Every autonomous action - routing decisions, source trust evaluations, stop conditions, gap fills - is captured as a structured **decision record**:

- Type: routing, stop, pivot, budget, belief_revision, gap_fill, conflict_resolution, source_selection
- Includes: title, rationale, confidence, alternatives considered, evidence refs, cost impact
- Viewable via `--explain` flag in CLI (Rich table) and decision sidebar in Trace Explorer
- Queryable via web API: `GET /api/experts/<name>/decisions`
- Stored as `decisions.json` alongside `decisions.md` in expert logs

### Expert Manifests

An expert's full state is available as a typed **manifest** - a snapshot composing claims, scored gaps, decision records, and policies:

```bash
# Via MCP (for AI agents)
deepr_expert_manifest(expert_name="AI Policy Expert")
deepr_rank_gaps(expert_name="AI Policy Expert", top_n=5)
```

```bash
# Via web API
GET /api/experts/AI%20Policy%20Expert/manifest
```

The manifest includes computed properties: `claim_count`, `open_gap_count`, `avg_confidence`, and `top_gaps(n)`.

### Continuous Learning

After research conversations, experts can re-synthesize to integrate new knowledge.

### Expert Council

Consult multiple experts on cross-domain questions. The system selects relevant experts (or you specify them), queries each in parallel, and synthesizes the perspectives into agreements, disagreements, and a unified recommendation.

```bash
# Via slash command in chat
/council "How will AI regulation affect our cloud architecture?"

# Via CLI subcommand
deepr expert council "Build vs buy?" --experts "Tech Architect,Business Strategist" --budget 5

# Via REST API
POST /api/experts/council
```

Budget is split evenly among consulted experts with a 10% reserve for synthesis,
reserved upfront against the global cost-safety manager so a parallel fan-out
cannot over-commit the daily cap. Auto-selection fans out to up to 10 experts
(default 3; pass `--max-experts`), with a relevance floor so a wide fan-out drops
zero-overlap experts instead of padding the council; naming experts explicitly is
uncapped. Parallelism is bounded so a 10-expert fan-out runs in waves, not all at
once.

#### Consulting on owned or prepaid capacity ($0)

`deepr expert consult` and the `deepr_consult_experts` MCP tool share one core, so
an external agent gets the same calibrated, versioned `deepr-consult-v1` artifact
(answer, each expert's perspective with confidence, agreements, dissent, cost).
Run the synthesis without touching a metered API key:

```bash
deepr expert consult "How do we keep expert knowledge current and cheap?" --plan claude
deepr expert consult "Cost vs quality tradeoff?" --local --max-experts 8
```

`--plan <id>` (codex, claude, ...) and `--local` run synthesis on prepaid or local
capacity and disable live metered fallback, so a consult never silently bills an
API key. Over MCP this is `synthesis_backend: "plan" | "local"`. This is also how
Deepr consults its own experts about its own work (the self-consultation loop).
Every CLI and MCP consult writes a local `deepr-consult-trace-v1` record for the
improvement loop: question, requested experts, selected context metadata, capacity
posture, checks run, output artifact, and first-class synthesis failure events.
When the consulted expert profile exists, the perspective context also includes a
bounded read-only `self_model` block with current goals, calibration, blockers,
risks, and the current-focus packet. This is trace and handoff metadata, not an
automatic goal update.
Review those traces with:

```bash
deepr expert consult-traces --json
deepr expert self-model "AI Strategy Expert" --json
```

The review output is `deepr-consult-trace-candidates-v1`: sanitized gap and eval
candidates for failed or low-context consults. It does not expose the local trace
file path or dump raw trace payloads into the host artifact.

## Limitations

- Early-stage software - more testing needed
- Vector search quality depends on document quality
- Research costs can add up with agentic mode
- Decision records are generated during agentic operations; non-agentic queries produce reports but not decisions

## See Also

- [FEATURES.md](FEATURES.md) - Full command reference
- [MODELS.md](MODELS.md) - Model selection guide
- [../ROADMAP.md](../ROADMAP.md) - Development priorities
