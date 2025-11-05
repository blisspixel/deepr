# Deepr

**Autonomous Learning and Knowledge Infrastructure**

---

## Overview

Deepr is a learning and research operating system that turns curiosity into structured, verifiable knowledge. It coordinates models, data, and reasoning workflows across multiple AI providers and local sources to help both humans and intelligent systems learn, document, and improve continuously.

Each Deepr run plans, searches, analyzes, and synthesizes information into a cited, versioned artifact. These artifacts can be reused by humans or connected directly into agentic workflows through the Model Context Protocol (MCP) or retrieval systems.

Deepr runs locally, integrates with providers such as OpenAI, Google Gemini, xAI Grok, and Azure OpenAI, and extends easily to new APIs. It transforms learning from a one-time process into a continuous, governed cycle of improvement.

Deepr’s purpose is simple: to build lasting knowledge infrastructure for people and agents. It is the foundation of systems that do not just react, but grow in understanding over time.

---

## Why Deepr

Modern AI can reason and generate, but it often lacks continuity. Deepr provides that missing layer. It gives both humans and agents a way to create, manage, and reuse structured knowledge that evolves as the world changes.

**Core principles**

- Learning as infrastructure: Every run produces artifacts that persist and grow over time.  
- Human and agent compatible: Runs locally for humans, connects through MCP for AI systems.  
- Model agnostic: Works with multiple providers and adapts as new ones emerge.  
- Transparent and governed: All output includes citations, budgets, and context.  
- Extensible: Can integrate with external data, APIs, or reasoning pipelines for retrieval and learning.  

---

## Example: Knowledge Creation in Action

### Competitive Market Analysis

```bash
deepr learn "EV battery technology landscape 2025: major suppliers, cost trends, chemistry innovations"
```

A startup founder needs to understand the EV battery market before supplier negotiations. Deepr researches suppliers, cost trajectories, emerging solid-state technologies, and competitive positioning across multiple phases.

**Outcome**

- Market landscape with current pricing and projected trends
- Technical comparison of LFP vs NMC vs solid-state chemistries
- Supplier profiles with capacity, reliability, and contract terms
- Strategic recommendations for sourcing decisions
- Complete cited report ready for board presentation

**Real benefit:** What would take a team days of research, Deepr delivers in 30 minutes for under $5.

---

### Technical Documentation

```bash
deepr research "Azure API Management best practices for multi-region SaaS deployment"
```

A platform team needs current Azure APIM patterns for their global expansion. Deepr searches latest docs, synthesizes multi-region patterns, cost implications, and implementation steps.

**Outcome**

- Architecture patterns with diagrams and decision trees
- Multi-region routing and failover strategies
- Cost analysis with scaling projections
- Security and compliance considerations
- Implementation checklist with Azure CLI commands

**Real benefit:** Team gets production-ready architecture guidance without weeks of trial-and-error.

---

### Strategic Decision Support

```bash
deepr team "Should we migrate from AWS to Google Cloud for our ML workloads?"
```

Leadership needs diverse perspectives on a major infrastructure decision. Deepr analyzes from technical, financial, operational, risk, and timeline perspectives simultaneously.

**Outcome**

- Technical assessment: ML service capabilities, performance, integration
- Financial analysis: TCO comparison, migration costs, ROI timeline
- Operational perspective: team training, downtime, complexity
- Risk evaluation: vendor lock-in, data sovereignty, compliance
- Synthesis: weighted recommendation with decision criteria

**Real benefit:** Compressed weeks of analysis into a comprehensive report, exposing blind spots and quantifying tradeoffs.

---

## From Research to Reuse

Deepr does not stop at research. Each run creates a structured artifact that can be indexed, retrieved, and extended.  
These outputs form the **knowledge substrate** for intelligent systems.

| Integration | Description |
|--------------|--------------|
| RAG systems | Feed Deepr artifacts into retrieval databases to provide grounded, cited answers. |
| MCP | Allow agents to call Deepr for deep reasoning, learning, and documentation on demand. |
| Knowledge graphs | Use Deepr outputs to populate and evolve domain-specific knowledge stores. |
| Team collaboration | Maintain shared learning archives that evolve as new research appears. |

---

## Quick Start

**Prerequisites**: Python 3.9+ required

### 1. Install

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr
pip install -e .
deepr --version
```

### 2. Configure Providers

```bash
cp .env.example .env
```

Edit `.env` and add your provider keys.

```bash
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
XAI_API_KEY=...
AZURE_OPENAI_API_KEY=...
```

### 3. Set a Budget

```bash
deepr budget set 25
```

### 4. Run Research

**Simple Semantic Commands** (Recommended - Natural Intent-Based Interface):

```bash
# Market analysis for investor pitch
deepr learn "AI coding assistant market: competitors, pricing, differentiation strategies"

# Technical implementation guide
deepr research "Kubernetes autoscaling best practices for microservices under variable load"

# Strategic decision with multiple viewpoints
deepr team "Should we build in-house ML infrastructure or use managed services?"

# Check results
deepr jobs list
deepr jobs get <job-id>
```

**Advanced: Direct Mode Selection** (For when you know exactly what you need):

```bash
deepr run focus "Targeted research query"
deepr run docs "Create comprehensive documentation for X"
deepr run project "Multi-phase research scenario"
deepr run team "Complex decision requiring multiple perspectives"
```

---

## The Learning Workflow

| Phase | Purpose |
|-------|----------|
| Plan | Define the goal and strategy for learning |
| Search | Retrieve and evaluate data and evidence |
| Analyze | Compare and interpret findings |
| Synthesize | Combine insights into a coherent whole |
| Publish | Save versioned, cited Markdown ready for reuse |

This structure makes research repeatable and extendable, turning one-off questions into an expanding base of understanding.

---

## Modes of Operation

Deepr offers both **semantic commands** (natural, intent-based) and **direct mode commands** (explicit control).

### Semantic Commands (Recommended)

| Command | Description | Example |
|---------|--------------|----------|
| `deepr research` | Auto-detects focus vs docs mode | `deepr research "Latest trends in RAG"` |
| `deepr learn` | Multi-phase structured learning | `deepr learn "Rust programming" --phases 4` |
| `deepr team` | Multi-perspective analysis | `deepr team "Strategic decision: cloud migration"` |

### Direct Mode Commands (Advanced)

| Mode | Description | Example |
|------|--------------|----------|
| Focus | Targeted research on a specific topic | `deepr run focus "Latest trends in retrieval-augmented reasoning"` |
| Docs | Live technical documentation | `deepr run docs "Gemini 2.5 Flash API capabilities and pricing"` |
| Project | Multi-phase, context-linked research | `deepr run project "Comparative analysis of open-source reasoning agents"` |
| Team | Multi-perspective collaboration between expert roles | `deepr run team "Frameworks for safe and open AI collaboration"` |

---

## Core Features

### Multi-Provider Orchestration

Deepr works across multiple reasoning engines. Use the best model for your specific task and budget.

```bash
# Deep technical analysis (OpenAI o1)
deepr research "Database indexing strategies for time-series data at 1M events/sec" --provider openai

# Large-context documentation review (Gemini 2.5-pro)
deepr research "Summarize security vulnerabilities in our 500-page audit report" --provider gemini

# Real-time competitive intelligence (Grok with X search)
deepr research "Current social media sentiment on autonomous vehicle safety" --provider grok

# Enterprise compliance analysis (Azure o1)
deepr research "GDPR implications of our new EU data processing workflow" --provider azure
```

| Provider | Example Models | Typical Use |
|-----------|----------------|--------------|
| OpenAI | o1, o1-mini | Deep reasoning and synthesis |
| Gemini | 2.5-flash, 2.5-pro | Structured, large-context research |
| Grok | grok-beta | Real-time search and analysis |
| Azure | o1, o1-mini | Enterprise and regulated environments |

---

### Contextual Document Integration

```bash
# Analyze internal documents with external research
deepr research "Review our Q4 product roadmap against competitor capabilities and market trends" \
  --upload q4-roadmap.pdf \
  --upload competitor-analysis.xlsx
```

Deepr combines your proprietary documents with web research for comprehensive analysis.

---

### Prompt Refinement

```bash
echo "DEEPR_AUTO_REFINE=true" >> .env
deepr research "llm pricing"
```

Vague prompts are automatically expanded into detailed research plans. "llm pricing" becomes a structured analysis of pricing models, cost per token, volume discounts, and TCO comparisons across providers.

---

### Vector Knowledge Stores

```bash
# Build a searchable knowledge base from your research
deepr vector create --name "customer-feedback-2024" --files interviews/*.pdf reports/*.md
deepr research "What are the top 3 feature requests across all customer interviews?" \
  --vector-store customer-feedback-2024
```

Create persistent knowledge bases from documents and past research. Query them semantically without re-uploading files.

---

### Budgets and Analytics

```bash
deepr budget status
deepr analytics report
deepr cost summary
```

Monitor usage, cost, and performance.

---

## Writing Better Prompts

Vague prompt:

```bash
deepr research "cloud costs"
```

Specific prompt with clear outcome:

```bash
deepr research "
Compare AWS, Azure, and GCP compute costs for GPU-accelerated ML training.
Focus on H100 and A100 availability, spot pricing, and committed use discounts.
Include egress costs and storage implications for 5TB model checkpoints.
Provide TCO breakdown for 100 hours/month sustained training workload."
```

**Best practices**

- State the decision you need to make or question you need answered
- Specify the scope: technologies, timeframe, constraints
- Mention what you will do with the output
- Include cost, compliance, or performance requirements if relevant  

---

## Architecture

```
Query
  ↓
Refinement
  ↓
Planner
  ↓
Execution
  ↓
Synthesis
  ↓
Cited Artifact
```

Deepr runs locally using an SQLite queue and filesystem storage. All jobs are transparent, reproducible, and traceable.

**Principles**

- Context before automation  
- Quality before quantity  
- Transparency before confidence  
- Learning should converge toward understanding  

---

## Cost and Quality Profiles

Estimated costs based on typical research runs with reasoning models (o1, Gemini 2.5, etc.):

| Depth | Cost | Time | Output |
|-------|------|------|--------|
| Quick insight | $1–2 | 5–10 minutes | Focused summary with citations |
| Comprehensive | $2–5 | 15–30 minutes | Detailed structured report |
| Multi-phase | $5–15 | 45–90 minutes | Context-linked analysis |
| Expert level | $10–20 | 1–2 hours | Complete knowledge artifact |

Actual costs vary based on provider, model, prompt complexity, and context size.

---

## Vision

Deepr is provider-agnostic infrastructure for autonomous learning. It enables both humans and intelligent systems to learn, adapt, and reason at scale, creating a flywheel of insight, understanding, and progress. When knowledge becomes structured, reproducible, and shareable, it accelerates discovery across every domain.

By combining deep reasoning models with local artifact storage and retrieval integration, Deepr becomes living infrastructure for expertise. It can feed agents, support continuous education, or act as a foundation for RAG systems that truly understand their sources.

If Deepr is built well, it will help humans work with the precision and reach of superintelligence while giving AI systems the grounding they need to approach general intelligence. Not just clever—meta-clever. Systems that examine themselves, learn from their own patterns, and continuously improve. The research tool researching itself. The learner learning how to learn.

We are the universe trying to understand itself.

---

## Interfaces

- **CLI** - Direct research and automation from terminal
- **Web UI** - Local interface with `python -m deepr.api.app`
- **MCP Server** - Model Context Protocol integration for AI agents (coming in v2.2)

### MCP Integration for AI Agents (Coming Soon)

Deepr will expose an MCP server that allows AI agents to submit long-running research jobs asynchronously:

```python
# Agent submits research and continues working
job = deepr_research("Analyze competitor X's strategy")
# ... agent does other work ...
result = deepr_get_result(job.id)  # Retrieve comprehensive report when ready
```

**Why MCP for Deepr?**
- Async by design - agents don't block waiting for research
- Comprehensive reports with citations
- Unique capability - most MCP tools are synchronous
- Positions Deepr as research infrastructure for agentic workflows

See [ROADMAP.md](ROADMAP.md) for v2.2 development priorities and implementation details.

All interfaces use the same governed workflow and artifact system.

---

## What's Next: v2.2 Development Priorities

Deepr v2.3 is **STABLE and production ready**. v2.2 focuses on self-improving experts and agentic capabilities:

1. **Semantic Commands** [LAUNCHED] - Natural intent-based interface:
   - `deepr research` - Auto-detects focus vs docs mode
   - `deepr learn` - Multi-phase structured learning
   - `deepr team` - Multi-perspective analysis
   - `deepr expert make` - Create domain experts with knowledge bases
   - Intuitive aliases: `deepr brain`, `deepr knowledge`

2. **Self-Directed Learning Experts** [LAUNCHED] - Experts that autonomously learn:
   - Expert analyzes initial documents and generates learning curriculum
   - Autonomously researches 10-20 topics to build comprehensive knowledge
   - Builds temporal knowledge graph (tracks what it knows and when)
   - Budget-protected autonomous learning with multi-layer safeguards
   - Example: `deepr expert make "AWS Solutions Architect" -f internal-wiki/*.md --learn --budget 10`
   - Expert researches latest AWS services, pricing updates, and architecture patterns to supplement internal docs

3. **Agentic Expert Chat** [PLANNED] - Conversational experts that research gaps:
   - Interactive Q&A: `deepr chat expert "AWS Solutions Architect"`
   - Agentic research: `deepr chat expert "AWS Solutions Architect" --agentic --budget 5`
   - Expert admits knowledge gaps, researches current information, and updates its knowledge base
   - Example: "What's the current best practice for EKS autoscaling?" triggers research if docs are outdated
   - Maintains conversation during async research, cites sources, questions assumptions

4. **MCP Server** - Expose Deepr to AI agents via Model Context Protocol
5. **Observability** - Transparent reasoning timelines and cost tracking

**Why This Matters:** Experts become digital consciousnesses that continuously learn and improve, not just static document stores. They understand what they know, when they learned it, and when to research more.

See [ROADMAP.md](ROADMAP.md) for detailed architecture and budget protection design.

---

## Documentation

- [INSTALL.md](docs/INSTALL.md)
- [FEATURES.md](docs/FEATURES.md)
- [ROADMAP.md](ROADMAP.md)
- [CHANGELOG.md](docs/CHANGELOG.md)

---

## License

MIT License. See [LICENSE](LICENSE).

---

## About the Project

Deepr was created by **Nick Seal** to explore how humans and intelligent systems can learn, reason, and improve together.

The boundary between idea and reality is becoming thinner. Deepr exists to amplify knowledge with insight, clarity, and compassion as humans and AI learn together.

---

**[MIT License](LICENSE)** | **[GitHub](https://github.com/blisspixel/deepr)**
