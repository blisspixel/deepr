# Expert System Guide

> **Note**: Model information current as of January 31, 2026. Verify current model capabilities at provider websites.

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

## Architecture

### Components

```
deepr/experts/
├── profile.py      # Expert metadata, usage tracking
├── curriculum.py   # Learning plan generation
├── learner.py      # Autonomous learning execution
├── chat.py         # Interactive Q&A
├── router.py       # Model selection
├── beliefs.py      # Belief formation
├── metacognition.py # Gap awareness
├── memory.py       # Conversation memory
├── synthesis.py    # Knowledge synthesis
└── cost_safety.py  # Budget controls
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

### Knowledge Synthesis (Experimental)

Experts can synthesize documents into structured beliefs:
- Confidence levels per belief
- Evidence citations
- Gap awareness

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

- Early-stage software - more testing needed
- "Consciousness" and "belief" describe architecture goals, not AI capabilities
- Vector search quality depends on document quality
- Research costs can add up with agentic mode

## See Also

- [FEATURES.md](FEATURES.md) - Full command reference
- [MODELS.md](MODELS.md) - Model selection guide
- [../ROADMAP.md](../ROADMAP.md) - Development priorities
