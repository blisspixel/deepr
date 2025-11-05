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

### Research for Understanding

```bash
deepr run project "What are the emerging patterns in multimodal reasoning architectures?"
```

Deepr plans a structured sequence, runs deep reasoning models, and produces a full cited report.

**Outcome**

- Summary of current multimodal architectures  
- Analysis of design tradeoffs and model strategies  
- Evaluation of benchmarks and active research directions  
- Cited Markdown document ready for inclusion in retrieval or agentic workflows  

---

### Documentation for Systems

```bash
deepr run docs "Gemini API reference with updated quotas and example usage"
```

Deepr generates living documentation that can serve as a retrieval-ready knowledge base.

**Outcome**

- API overview with structured fields and examples  
- Current pricing, quotas, and limits  
- Integration steps and troubleshooting  
- Formatted output ready for ingestion into RAG systems or internal documentation  

---

### Expert-Level Learning Loop

```bash
deepr run team "How should enterprise AI systems approach dynamic governance?"
```

Deepr assembles a team of virtual experts, each contributing from a different reasoning perspective.

**Outcome**

- Policy recommendations synthesized from multiple roles such as strategist, ethicist, and architect  
- Traceable reasoning and transparent disagreements  
- A single synthesized report usable by both humans and agents  

This creates reusable expertise that can power a “Talk to an Expert” agent or a knowledge assistant grounded in verified research.

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

### 4. Run

```bash
deepr run focus "Advances in small language models for local inference"
deepr list
deepr get <job-id>
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

| Mode | Description | Example |
|------|--------------|----------|
| Focus | Targeted research on a specific topic | `deepr run focus "Latest trends in retrieval-augmented reasoning"` |
| Docs | Live technical documentation | `deepr run docs "Gemini 2.5 Flash API capabilities and pricing"` |
| Project | Multi-phase, context-linked research | `deepr run project "Comparative analysis of open-source reasoning agents"` |
| Team | Multi-perspective collaboration between expert roles | `deepr run team "Frameworks for safe and open AI collaboration"` |

---

## Core Features

### Multi-Provider Orchestration

Deepr works across multiple reasoning engines.

```bash
deepr run focus "Hybrid retrieval approaches" --provider openai
deepr run focus "Scaling inference efficiency" --provider gemini
deepr run focus "Autonomous systems and safety" --provider grok
deepr run focus "AI policy and governance" --provider azure
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
deepr run focus "Analyze our latest architecture proposal and recommend improvements"   --upload system-design.pdf --upload requirements.md
```

Deepr indexes uploaded content and integrates it directly into the reasoning process.

---

### Prompt Refinement

```bash
echo "DEEPR_AUTO_REFINE=true" >> .env
deepr run focus "compare open-source reasoning frameworks"
```

Automatically improves vague prompts into detailed, structured research instructions.

---

### Vector Knowledge Stores

```bash
deepr vector create --name "company-insights" --files reports/*.md
deepr run focus "Extract recurring product challenges" --vector-store company-insights
```

These stored vectors allow Deepr and other agents to query past research directly.

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

Poor example:

```bash
deepr run focus "Research AI models"
```

Better example:

```bash
deepr run focus "
Investigate current open-weight reasoning models.
Include major providers, architecture summaries, licensing, and known limitations.
Highlight adoption trends and performance tradeoffs.
Output a structured, cited report with an executive summary."
```

**Best practices**

- Define objectives clearly.  
- Include what matters to your organization or system.  
- Use uploaded files for context.  
- Prefer "current" or "latest" phrasing for freshness.  

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
- **MCP Server** - Model Context Protocol integration for AI agents (async research infrastructure)

### MCP Integration for AI Agents

Deepr exposes an MCP server that allows AI agents to submit long-running research jobs asynchronously:

```python
# Agent submits research and continues working
job = deepr_submit_research("Analyze competitor X's strategy")
# ... agent does other work ...
result = deepr_get_result(job.id)  # Retrieve comprehensive report when ready
```

**Key Benefits:**
- Async by design - agents don't block waiting for research
- Comprehensive reports with citations
- Unique capability - most MCP tools are synchronous
- Positions Deepr as research infrastructure for agentic workflows

See [ROADMAP.md](ROADMAP.md) for MCP implementation details.

All interfaces use the same governed workflow and artifact system.

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
