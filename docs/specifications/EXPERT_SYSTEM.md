# Expert System

Domain experts that learn autonomously from research and synthesize knowledge into beliefs.

---

## Overview

Deepr's expert system creates domain experts that go beyond simple document retrieval. Experts learn autonomously, form beliefs with confidence levels, and track knowledge gaps.

**What experts do:**
- Research topics autonomously and form beliefs from synthesis
- Speak from understanding with confidence levels, not just document quotes
- Track what they know vs. what they need to learn
- Monitor knowledge freshness and can trigger research when information is stale
- Provide answers grounded in both documents and synthesized beliefs

**Current status:**
- Core features implemented: autonomous learning, knowledge synthesis, belief formation
- Basic testing complete: One expert successfully created and tested
- Needs more testing: Agentic research triggers, knowledge refresh, multi-conversation learning

---

## Creating Experts

### Basic Expert Creation

```bash
deepr expert make "Azure Architect" \
  --files "./docs/*.md" \
  --description "Azure Landing Zones and Fabric governance"
```

Creates an expert from your proprietary documents. The expert indexes all documents into a vector store for semantic search and retrieval.

### Autonomous Learning Expert

```bash
deepr expert make "Supply Chain Management" \
  --files "C:\Docs\*.pdf" \
  --learn \
  --budget 10 \
  --topics 8
```

**What happens:**

1. Expert analyzes initial documents
2. GPT-5 generates learning curriculum (8 research topics in this example)
3. Shows estimated costs per topic and total before submission
4. Requires confirmation if total exceeds $1 or budget limit
5. Submits deep research jobs in parallel (each takes 5-20 minutes)
6. Polls for completion every 30 seconds
7. Downloads completed research and integrates into knowledge base
8. Expert is now ready with comprehensive domain knowledge

**Cost:** $5-$20 depending on domain complexity and number of topics (default: 5)

**Time:** 20-60 minutes depending on research depth and parallelization

---

## Expert Management

### List All Experts

```bash
deepr expert list
```

Shows all experts with statistics:
- Number of documents in knowledge base
- Number of conversations
- Total cost incurred
- Last updated timestamp

### Get Expert Details

```bash
deepr expert info "Azure Architect"
```

Shows detailed information:
- Description and domain
- Vector store ID
- Document count
- Conversation history
- Usage statistics
- Provider configuration

### Delete Expert

```bash
deepr expert delete "Azure Architect"
```

Removes expert profile and associated data. Vector store remains intact (can be reused or deleted separately).

---

## Interactive Expert Chat

### Basic Chat

```bash
deepr expert chat "Azure Architect"
```

Interactive Q&A session with your expert. The expert answers from its knowledge base and cites sources.

**Example session:**

```
You: How should we structure Landing Zones?

Expert: According to azure-lz-best-practices.md, Landing Zones should follow a hub-and-spoke topology with:

1. Central hub for shared services (section 3.2)
2. Spoke VNets for workload isolation (section 3.4)
3. Network segmentation with NSGs (section 4.1)

Source: azure-lz-best-practices.md (lines 145-203)
Confidence: High

You: /quit
```

**Interactive commands:**
- `/status` - Show session budget and usage
- `/quit` - End conversation
- `/clear` - Clear conversation history

### Agentic Chat (Autonomous Research)

```bash
deepr expert chat "AWS Expert" --agentic --budget 5
```

Expert can autonomously trigger research when encountering knowledge gaps.

**Example session:**

```
You: How should we handle OneLake security for multi-tenant SaaS?

Expert: I have general OneLake concepts, but not specific multi-tenant SaaS patterns.
Let me research this to give you accurate guidance...

[Triggers research automatically]
[Cost: $0.15, Time: ~8 minutes]

Expert: My research found three approaches:

1. Workspace-per-tenant isolation
   - Complete data separation
   - Simplest security model
   - Higher management overhead
   [Source: Research job-abc123, section 2.1]

2. Lakehouse-per-tenant with RLS
   - Balanced approach
   - Row-level security enforcement
   - Moderate complexity
   [Source: Research job-abc123, section 2.2]

3. Shared lakehouse with strict RLS
   - Most efficient
   - Requires careful implementation
   - Complex security model
   [Source: Research job-abc123, section 2.3]

For your SaaS scenario, I recommend approach 2 because...

Should I add this to my permanent knowledge base? [y/N]

You: yes

Expert: Research integrated. I can now answer OneLake multi-tenant questions immediately.

Session budget remaining: $4.83
```

---

## Three-Tier Research System

When in agentic mode, experts choose the appropriate research depth:

### Quick Lookup (FREE, <5 seconds)

For simple factual questions:
- Uses GPT-5 with web search
- No deep research API call
- Answers: "What year was X founded?", "What's the current version of Y?"

### Standard Research ($0.01-$0.05, 30-60 seconds)

For technical deep-dives:
- Uses GPT-5 focused research
- Moderate depth analysis
- Answers: "How does X work?", "Compare X and Y"

### Deep Research ($0.10-$0.30, 5-20 minutes)

For complex strategic analysis:
- Uses o4-mini-deep-research
- Comprehensive multi-source synthesis
- Answers: "Should we adopt X?", "What's the optimal strategy for Y?"

The expert automatically chooses the cheapest tool that will answer your question adequately.

---

## Budget Protection

Multiple layers prevent runaway costs:

### Creation Budget

```bash
deepr expert make "Expert" -f docs/*.md --learn --budget 5.00
```

Shows estimated costs before submission:

```
Learning Curriculum (15 topics):
1. Topic A - Est: $0.20, 10 min
2. Topic B - Est: $0.15, 8 min
...
15. Topic O - Est: $0.30, 15 min

Total: $3.45, ~2.5 hours
Budget limit: $5.00  [WITHIN BUDGET]

Proceed? [y/N]
```

Safety mechanisms:
- Show cost estimate per topic
- Require confirmation if total exceeds $1
- Hard fail if total exceeds budget limit
- Pause if any single topic costs 2x estimate

### Session Budget

```bash
deepr expert chat "Expert" --agentic --budget 3.00
```

Tracks cumulative cost during conversation:

```
Session budget: $3.00
Research triggered: "OneLake security" ($0.15)
Remaining: $2.85

[Expert wants to research again]
Expert: I should also research Fabric capacity planning ($0.20).
Remaining budget: $2.65. Proceed? [y/N]
```

Safety mechanisms:
- Warn at 80% budget consumed
- Block research when budget exhausted
- Show remaining budget after each research

### Emergency Controls

```bash
deepr expert pause "Expert"          # Stop all autonomous activity
deepr expert resume "Expert"         # Resume
deepr expert reset-budget "Expert"   # Reset monthly counter
deepr expert usage "Expert"          # Show cost breakdown
```

---

## Beginner's Mind Philosophy

Experts are designed with intellectual humility and transparency:

### Core Principles

1. **Admit Ignorance**
   - Say "I don't know" when uncertain
   - Never guess beyond knowledge base
   - Acknowledge expertise limits

2. **Source Transparency**
   - "According to [document]..." (from knowledge base)
   - "I just researched this..." (from fresh research)
   - "Based on combining..." (from synthesis)

3. **Research-First Approach**
   - Trigger research instead of guessing
   - Wait for research completion before answering
   - Prefer accuracy over speed

4. **Question Assumptions**
   - "My docs are from Oct 2024, let me verify current info..."
   - "Are you asking about X or Y?"
   - "That was true in 2023, checking 2025 sources..."

5. **Depth Over Breadth**
   - Better to research deeply than answer superficially
   - Take time for nuanced analysis
   - Comprehensive, well-reasoned answers

---

## Knowledge Base Management

### Refresh Expert Knowledge

```bash
deepr expert refresh "Azure Architect"
```

Scans the expert's documents folder for new files and uploads them to the vector store. Useful for:
- Adding research results manually downloaded
- Integrating externally-created documents
- Closing the learning loop after batch research

### Manual Document Addition

```bash
deepr expert refresh "Expert" --files "new-docs/*.pdf"
```

Adds specific documents to the expert's knowledge base.

---

## Learning Loop Architecture

Experts close the learning loop through multiple pathways:

### Real-Time Learning (Agentic Chat)

When using `--agentic` mode with standard research:
1. Expert triggers research
2. Results saved to `data/experts/<name>/documents/`
3. Results immediately uploaded to vector store
4. Available in knowledge base for next question

### Batch Learning (Manual Refresh)

For externally-added research or deep research jobs:
1. Add documents to `data/experts/<name>/documents/`
2. Run `deepr expert refresh <name>`
3. Expert scans for new files
4. Uploads missing documents to vector store

### Curriculum Learning (Autonomous)

With `--learn` flag during creation:
1. Expert generates curriculum
2. Submits multiple research jobs
3. Polls for completion
4. Downloads results automatically
5. Integrates into knowledge base
6. Expert now has comprehensive domain knowledge

---

## Expert Data Structure

```
data/experts/
└── [expert_name]/
    ├── profile.json          # Metadata and configuration
    ├── documents/            # Downloaded research reports
    ├── knowledge/            # Knowledge base and synthesis data
    └── conversations/        # Chat history
```

### profile.json

```json
{
  "name": "Azure Architect",
  "description": "Azure Landing Zones and Fabric governance",
  "domain": "cloud architecture",
  "vector_store_id": "vs_abc123",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-20T14:22:00Z",
  "document_count": 15,
  "conversation_count": 8,
  "total_cost": 4.25,
  "provider": "openai",
  "model": "gpt-5"
}
```

---

## Advanced Features

### Expert Council Mode (Planned v2.6)

Assemble multiple experts to deliberate on complex decisions:

```bash
deepr council "Should we build vs buy for our data platform?" \
  --experts "Tech Architect,Business Strategist,Legal Counsel" \
  --budget 10 \
  --rounds 3
```

**What happens:**
1. Each expert provides perspective from their knowledge base
2. GPT-5 facilitates debate, experts respond to each other
3. GPT-5 synthesizes consensus and dissenting opinions

**Output:**
- Consensus recommendations
- Key disagreements highlighted
- Risk factors from each perspective
- Sourced evidence from each expert's knowledge

### Temporal Knowledge Tracking (Planned v2.7)

Track when knowledge was learned:
- Document timestamps (source publication dates)
- Research timestamps (when expert learned each topic)
- Knowledge freshness and confidence levels
- Enable "I learned X in Jan 2025, but this might have changed" awareness

### Meta-Cognitive Awareness (Planned v2.8)

Track expert's self-knowledge:
- Per-domain confidence levels
- Known topics vs. knowledge gaps
- Times expert said "I don't know"
- Proactive research triggers based on patterns

---

## Cost Examples

### Small Expert (5 documents, no learning)
- Creation: FREE (vector store creation)
- Chat (10 questions, no research): $0.10-$0.20
- Chat (10 questions, 2 research triggers): $0.40-$0.80

### Medium Expert (20 documents, 5 research topics)
- Creation: $2.50-$5.00 (autonomous learning)
- Chat (20 questions, 5 research triggers): $1.00-$2.50

### Large Expert (50 documents, 15 research topics)
- Creation: $7.50-$15.00 (comprehensive learning)
- Chat (50 questions, 10 research triggers): $3.00-$6.00

---

## Best Practices

1. **Start with focused domains** - "AWS Security" not "All of AWS"
2. **Provide quality seed documents** - Your best internal docs and research
3. **Use autonomous learning for comprehensive coverage** - Let expert fill gaps
4. **Set appropriate budgets** - $5-$10 for creation, $3-$5 for sessions
5. **Review research before integration** - Use "Should I remember this?" prompts
6. **Refresh experts quarterly** - Keep knowledge current
7. **Use agentic mode sparingly** - When you need current/deep information
8. **Monitor costs** - Check `deepr expert usage <name>` regularly

---

## Troubleshooting

### Expert gives outdated answers

```bash
deepr expert refresh "Expert" --synthesize
```

Triggers knowledge synthesis to detect and flag outdated information.

### Expert triggers too much research

Reduce budget or use basic chat mode (without `--agentic`):

```bash
deepr expert chat "Expert"  # No autonomous research
```

### Expert doesn't find relevant information

Check document quality and coverage:

```bash
deepr expert info "Expert"
```

Add more documents if knowledge base is sparse.

### Cost exceeded expectations

Review usage breakdown:

```bash
deepr expert usage "Expert"
```

Set lower budgets for future sessions.

---

## Testing Status

**What has been tested (2026-01-21):**
- Expert creation with autonomous learning (10 topics)
- Knowledge synthesis creating beliefs with confidence levels
- Knowledge gap identification
- Basic chat showing expert speaks from beliefs
- Cost estimation before research
- Document persistence for synthesis

**What needs more testing:**
- Agentic research triggers during conversation
- Knowledge refresh workflow
- Multi-conversation learning and belief updates
- Research tool selection (quick vs standard vs deep)
- Cross-expert knowledge sharing
- Large-scale expert deployments

**Known limitations:**
- Only one expert fully tested end-to-end
- Agentic mode research triggers not validated in practice
- Knowledge refresh tested manually, not through normal workflow
- Cost tracking in chat sessions needs validation

This is early-stage functionality. Test thoroughly with small budgets before relying on it for critical work.

---

See also:
- [expert_learning_architecture.md](expert_learning_architecture.md) - Technical architecture details
- [EXAMPLES.md](EXAMPLES.md#creating-domain-experts) - Expert creation examples
- [LEARNING_WORKFLOW.md](LEARNING_WORKFLOW.md) - Structured learning strategies
