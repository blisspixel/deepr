# Expert System Guide

> **Note**: Model information current as of February 2026. Verify current model capabilities at provider websites.

## Overview

Deepr's expert system creates domain experts from documents that can answer questions, recognize knowledge gaps, and autonomously research to fill them.

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
- Build on previous learning

## Quick Start

```bash
# Create expert from documents
deepr expert make "Azure Architect" --files docs/*.md

# Chat with expert
deepr expert chat "Azure Architect"

# Chat with research capability
deepr expert chat "Azure Architect" --agentic --budget 5
```

## Creating Experts

### Basic Creation
```bash
deepr expert make "Expert Name" --files path/to/docs/*.md
```

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
deepr expert chat "Azure Architect" --agentic --budget 5
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
# Scaffold a new skill in ~/.deepr/skills/
deepr skill create my-custom-skill
```

This creates:
- `skill.yaml` — metadata, triggers, tool definitions
- `prompt.md` — domain-specific reasoning instructions
- `tools/` — Python tool implementations

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
- **Three-tier storage**: Built-in skills ship with Deepr, user skills live in `~/.deepr/skills/`, expert-local skills in `data/experts/{name}/skills/`. Later tiers override earlier ones.
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
deepr/core/
├── contracts.py    # Canonical types: Claim, Gap, DecisionRecord, ExpertManifest, Source

deepr/experts/
├── profile.py      # Expert metadata, usage tracking, get_manifest()
├── curriculum.py   # Learning plan generation
├── learner.py      # Autonomous learning execution
├── chat.py         # Interactive Q&A
├── router.py       # Model selection
├── beliefs.py      # Belief formation, to_claim() adapter
├── metacognition.py # Gap awareness, to_gap() adapter
├── memory.py       # Conversation memory
├── synthesis.py    # Knowledge synthesis, to_claim()/to_gap() adapters
├── gap_scorer.py   # EV/cost ranking for knowledge gaps
├── thought_stream.py # Decision records, reasoning traces
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
deepr expert chat "Name" --agentic --budget 5
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

Experts track structured **claims** — atomic assertions with confidence scores, source provenance, and contradiction tracking. Claims are canonical types defined in `core/contracts.py`:

- Each claim has a confidence score (0.0-1.0) with time-based decay
- Sources carry a `TrustClass` (primary, secondary, tertiary, self_generated) and content hash
- Claims track contradictions and supersession chains
- View claims via web API: `GET /api/experts/<name>/claims?min_confidence=0.7`

### Knowledge Gap Scoring

Gaps are prioritized by **EV/cost ratio** — expected value relative to the estimated cost to fill:

```
ev_cost_ratio = expected_value / estimated_cost
expected_value = (priority / 5.0) + frequency_boost
estimated_cost = domain velocity lookup (fast=$0.25, medium=$1.00, slow=$2.00)
```

Higher-ratio gaps are filled first, making `expert fill-gaps --top N` a rational allocation rather than arbitrary ordering.

### Decision Records

Every autonomous action — routing decisions, source trust evaluations, stop conditions, gap fills — is captured as a structured **decision record**:

- Type: routing, stop, pivot, budget, belief_revision, gap_fill, conflict_resolution, source_selection
- Includes: title, rationale, confidence, alternatives considered, evidence refs, cost impact
- Viewable via `--explain` flag in CLI (Rich table) and decision sidebar in Trace Explorer
- Queryable via web API: `GET /api/experts/<name>/decisions`
- Stored as `decisions.json` alongside `decisions.md` in expert logs

### Expert Manifests

An expert's full state is available as a typed **manifest** — a snapshot composing claims, scored gaps, decision records, and policies:

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

### Expert Council (Future)

Assemble multiple experts to deliberate on complex decisions:
```bash
deepr council "Build vs buy?" \
  --experts "Tech Architect,Business Strategist,Legal Counsel" \
  --budget 10
```

## Limitations

- Early-stage software — more testing needed
- Vector search quality depends on document quality
- Research costs can add up with agentic mode
- Decision records are generated during agentic operations; non-agentic queries produce reports but not decisions

## See Also

- [FEATURES.md](FEATURES.md) - Full command reference
- [MODELS.md](MODELS.md) - Model selection guide
- [../ROADMAP.md](../ROADMAP.md) - Development priorities
