# Architecture

Technical architecture and design decisions for Deepr.

---

## System Overview

Deepr is a local-first research automation system with multi-provider AI orchestration. It coordinates reasoning models, data sources, and workflows to produce comprehensive, cited research artifacts.

```
Query - Refinement - Planning - Execution - Synthesis - Artifact
```

All operations run locally using SQLite queue and filesystem storage. Results are transparent, reproducible, and traceable.

---

## Core Principles

1. **Context before automation** - Understand before acting
2. **Quality before quantity** - Deep over broad
3. **Transparency before confidence** - Show reasoning, not just results
4. **Learning should converge** - Research builds toward understanding

---

## Project Structure

```
deepr/
├── deepr/                    # Core package
│   ├── cli/                  # Command-line interface
│   │   ├── commands/         # Individual commands
│   │   │   ├── jobs.py       # Job management
│   │   │   ├── semantic.py   # Semantic commands and expert system
│   │   │   ├── run.py        # Direct mode commands
│   │   │   └── doctor.py     # Diagnostics
│   │   └── main.py           # CLI entry point
│   │
│   ├── core/                 # Core research logic
│   │   ├── research.py       # ResearchOrchestrator
│   │   ├── documents.py      # Document management
│   │   └── reports.py        # Report generation
│   │
│   ├── experts/              # Expert system
│   │   ├── profile.py        # ExpertStore, Expert profiles
│   │   ├── synthesis.py      # Knowledge synthesis
│   │   ├── learner.py        # Autonomous learning
│   │   ├── curriculum.py     # GPT-5 curriculum generation
│   │   └── chat.py           # Expert chat interface
│   │
│   ├── providers/            # AI provider integrations
│   │   ├── openai_provider.py
│   │   ├── gemini_provider.py
│   │   ├── grok_provider.py
│   │   ├── anthropic_provider.py
│   │   └── azure_provider.py
│   │
│   ├── storage/              # Storage backends
│   │   ├── local.py          # LocalStorage (reports/)
│   │   └── blob.py           # Cloud storage
│   │
│   ├── queue/                # Job queue
│   │   └── local_queue.py    # SQLite queue
│   │
│   ├── mcp/                  # Model Context Protocol
│   │   └── server.py         # MCP server for AI agents
│   │
│   └── utils/                # Utilities
│       ├── scrape/           # Web scraping
│       ├── check_expert_status.py
│       └── retrieve_expert_reports.py
│
├── data/                     # Local data
│   └── experts/              # Expert system data
│       └── [expert_name]/    # Per-expert folders
│           ├── profile.json
│           ├── documents/
│           ├── knowledge/
│           └── conversations/
│
├── reports/                  # Research outputs
│   ├── [job_id]/            # Human-readable directories
│   │   ├── report.md
│   │   ├── report.txt
│   │   └── metadata.json
│   └── campaigns/           # Multi-phase research
│
├── docs/                    # Documentation
├── tests/                   # Test suite
└── mcp/                     # MCP configuration templates
```

---

## Component Architecture

### CLI Layer

Entry point for all user interactions. Handles argument parsing, validation, and dispatch to core services.

**Key Components:**
- `cli/main.py` - CLI entry point with Click
- `cli/commands/semantic.py` - Intent-based commands (research, learn, team, expert)
- `cli/commands/run.py` - Direct mode commands (focus, docs, project, team)
- `cli/commands/jobs.py` - Job management (list, status, get, cancel)

### Core Research Layer

Orchestrates research workflows and manages execution lifecycle.

**Key Components:**
- `core/research.py` - `ResearchOrchestrator` coordinates providers and workflows
- `core/documents.py` - Document parsing and context management
- `core/reports.py` - Report generation and formatting

### Expert System

Self-improving domain experts with autonomous learning capabilities.

**Key Components:**
- `experts/profile.py` - `ExpertStore` manages expert profiles and metadata
- `experts/chat.py` - Interactive Q&A with vector store retrieval
- `experts/learner.py` - Autonomous curriculum-based learning
- `experts/curriculum.py` - GPT-5 curriculum generation
- `experts/synthesis.py` - Knowledge synthesis (experimental)

**Data Flow:**
```
User creates expert - Profile stored in data/experts/
  |
Expert analyzes docs - GPT-5 generates curriculum
  |
Curriculum validated - Research jobs submitted
  |
Jobs complete - Results downloaded to documents/
  |
Documents uploaded - Vector store for retrieval
  |
Expert ready - Interactive chat with knowledge base
```

### Provider Layer

Multi-provider abstraction supporting OpenAI, Gemini, Grok, Azure, Anthropic.

**Architecture Pattern:**
```python
class DeepResearchProvider:
    def submit_research(prompt, context) -> job_id
    def check_status(job_id) -> status
    def retrieve_result(job_id) -> report
```

**Provider-Specific:**
- `OpenAIProvider` - GPT-5 models, o3/o4-mini deep research
- `GeminiProvider` - Gemini 2.5 flash/pro
- `GrokProvider` - Grok 4 fast with X search integration
- `AzureProvider` - Azure OpenAI with GPT-5
- `AnthropicProvider` - Claude with extended thinking

### Storage Layer

Local-first storage with optional cloud backends.

**LocalStorage:**
- Reports stored in `reports/[job_id]/`
- Expert data in `data/experts/[name]/`
- Vector stores managed by provider (OpenAI, Pinecone, etc.)

**BlobStorage (optional):**
- Azure Blob Storage
- AWS S3
- Google Cloud Storage

### Queue Layer

SQLite-based job queue for async execution.

**Schema:**
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    status TEXT,
    prompt TEXT,
    provider TEXT,
    model TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    cost REAL,
    metadata JSON
);
```

**Operations:**
- `submit(job)` - Add job to queue
- `get_status(job_id)` - Check job state
- `update_status(job_id, status)` - Update state
- `list_jobs(filters)` - Query jobs

---

## Multi-Provider Strategy

### Dual Provider Architecture

**Deep Research (OpenAI/Azure):**
- Models: o4-mini-deep-research, o3-deep-research
- Use cases: Novel problem-solving, critical decisions, complex synthesis
- Cost: $0.50-$5.00 per query
- Execution: Async (5-15 minutes)
- When: ~20% of operations requiring extended reasoning

**Fast/General Operations (xAI, Gemini, Anthropic):**
- Models: grok-4-fast, gemini-2.5-flash, claude-sonnet-4-5
- Use cases: News, docs, team research, learning, expert chat, planning
- Cost: $0.0005-$0.003 per query (96-99% cheaper)
- Execution: Immediate (10-60 seconds)
- When: ~80% of operations

**Planning & Orchestration (GPT-5 or Grok):**
- Models: gpt-5, gpt-5-mini, grok-4-fast
- Use cases: Research planning, curriculum generation, adaptive workflows
- Cost: $0.01-$0.05 per plan
- Execution: Immediate
- When: Planning before execution

### Provider Selection Logic

```python
def select_provider(task_type, budget, quality_requirement):
    if task_type == "deep_research":
        return OpenAIProvider("o4-mini-deep-research")

    elif task_type == "planning":
        # Prefer Grok for cost efficiency
        if grok_available():
            return GrokProvider("grok-4-fast")
        return OpenAIProvider("gpt-5-mini")

    elif task_type == "quick_research":
        # Prefer Grok for cost + X search integration
        if grok_available():
            return GrokProvider("grok-4-fast")
        return GeminiProvider("gemini-2.5-flash")

    elif task_type == "extended_thinking":
        # Use Anthropic for reasoning transparency
        return AnthropicProvider("claude-sonnet-4-5")
```

---

## Workflow Patterns

### Single Research Job

```
User submits - Refinement (optional) - Provider submission
    |
Provider queued - Background polling - Status updates
    |
Research complete - Download report - Save to reports/
    |
User retrieves - Markdown with citations
```

### Multi-Phase Research

```
User goal - GPT-5 generates Phase 1 plan
    |
Phase 1 execution - Multiple jobs in parallel
    |
Results complete - GPT-5 reviews findings
    |
GPT-5 plans Phase 2 - Based on Phase 1 gaps
    |
Phase 2 execution - Context from Phase 1 injected
    |
Repeat until comprehensive - Final synthesis
```

**Key Components:**
- `ResearchPlanner` - GPT-5 generates initial plans
- `ResearchReviewer` - GPT-5 reviews results, plans next phase
- `ContextBuilder` - Summarizes for context injection
- `BatchExecutor` - Orchestrates multi-phase execution

### Expert Learning Workflow

```
User creates expert - Expert analyzes seed docs
    |
GPT-5 generates curriculum - 5-20 research topics
    |
User approves budget - Research jobs submitted
    |
Jobs execute (5-20 min each) - Polling for completion
    |
Results download - Saved to expert documents/
    |
Upload to vector store - Knowledge base updated
    |
Expert ready - Interactive chat enabled
```

### Agentic Expert Chat

```
User asks question - Expert searches knowledge base
    |
Knowledge gap detected - Expert decides research depth
    |
    +-- Quick lookup (FREE, <5s) - GPT-5 + web search
    +-- Standard research ($0.01-0.05) - GPT-5 focused
    +-- Deep research ($0.10-0.30) - o4-mini comprehensive
    |
Research completes - Results integrated to knowledge base
    |
Expert answers - With citations and confidence level
```

---

## Budget Protection

Multi-layer controls prevent runaway costs:

### Layer 1: Job-Level Budgets

```python
def submit_research(prompt, budget=None):
    estimate = estimate_cost(prompt)
    if budget and estimate > budget:
        raise BudgetExceededError(estimate, budget)
    return submit_to_provider(prompt)
```

### Layer 2: Session-Level Budgets

```python
class ExpertSession:
    def __init__(self, budget):
        self.budget = budget
        self.spent = 0.0

    def trigger_research(self, cost_estimate):
        if self.spent + cost_estimate > self.budget:
            raise SessionBudgetExceededError()
        self.spent += cost_estimate
```

### Layer 3: Monthly Budgets

```python
class ExpertProfile:
    monthly_budget: float
    monthly_spent: float

    def can_research(self, cost_estimate):
        return (self.monthly_spent + cost_estimate) <= self.monthly_budget
```

### Layer 4: Global Limits

```bash
# .env configuration
DEEPR_GLOBAL_BUDGET=100.00
DEEPR_ALERT_THRESHOLD=0.8
DEEPR_AUTO_PAUSE_THRESHOLD=1.0
```

---

## Observability

### Metadata Generation

Every task automatically emits structured JSON:

```json
{
  "job_id": "job_abc123",
  "prompt": "...",
  "context_used": ["doc1.md", "doc2.pdf"],
  "model": "gpt-5",
  "provider": "openai",
  "tokens": {
    "input": 12000,
    "output": 8000
  },
  "cost": 2.15,
  "citations": 47,
  "sources": 23,
  "phases": [
    {
      "phase": "planning",
      "duration": "45s",
      "cost": 0.05
    },
    {
      "phase": "research",
      "duration": "12m 30s",
      "cost": 2.00
    },
    {
      "phase": "synthesis",
      "duration": "2m 15s",
      "cost": 0.10
    }
  ]
}
```

### Reasoning Timelines

Phase transitions logged automatically:

```
[00:00:00] Job submitted
[00:00:45] Planning complete → 3 research tasks identified
[00:01:00] Phase 1 execution started → 3 parallel jobs
[00:13:30] Phase 1 complete → Reviewer analyzing gaps
[00:14:15] Phase 2 planned → 2 additional tasks
[00:14:30] Phase 2 execution started
[00:26:45] Phase 2 complete → Final synthesis
[00:29:00] Report generated
```

### Cost Attribution

Per-phase, per-perspective, per-provider tracking:

```
Total Cost: $5.23

By Phase:
  Planning:   $0.08  (1.5%)
  Research:   $4.50  (86.0%)
  Synthesis:  $0.65  (12.5%)

By Provider:
  OpenAI:     $4.50  (86.0%)
  Grok:       $0.73  (14.0%)

By Task:
  Market analysis:        $1.50
  Competitor research:    $1.20
  Regulatory review:      $1.80
  Synthesis:              $0.65
```

---

## Security Considerations

### API Key Management

- Environment variables only (never in code)
- No API keys in logs or error messages
- Provider-specific key validation on startup

### Data Privacy

- All processing local-first
- Cloud providers used only for AI inference
- User documents never shared between jobs
- Vector stores isolated per expert

### Budget Controls

- Hard limits enforced before submission
- No automatic spending without confirmation
- Session-scoped budgets for agents
- Emergency pause controls

---

## Performance Characteristics

### Latency

- Quick research: 10-60 seconds
- Standard research: 5-15 minutes
- Deep research: 15-30 minutes
- Multi-phase: 30-90 minutes

### Throughput

- Parallel job execution within phases
- Context injection reduces redundant research
- Provider-side rate limits respected

### Cost Efficiency

- Fast models for 80% of operations (96-99% cheaper)
- Context reuse via summarization (70% token reduction)
- Intelligent provider routing (cost vs. quality optimization)

---

## Extension Points

### Adding New Providers

```python
class NewProvider(DeepResearchProvider):
    def __init__(self, api_key, model):
        self.client = NewProviderClient(api_key)
        self.model = model

    def submit_research(self, prompt, context):
        response = self.client.research.create(
            model=self.model,
            prompt=prompt,
            context=context
        )
        return response.job_id

    def check_status(self, job_id):
        return self.client.research.status(job_id)

    def retrieve_result(self, job_id):
        return self.client.research.retrieve(job_id)
```

### Adding New Commands

```python
@click.command()
@click.argument('topic')
@click.option('--budget', type=float)
def new_command(topic, budget):
    """Description of new command."""
    orchestrator = ResearchOrchestrator()
    result = orchestrator.execute(
        prompt=topic,
        budget=budget
    )
    click.echo(result)
```

### Adding New Storage Backends

```python
class NewStorageBackend(StorageBackend):
    def save_report(self, job_id, report):
        # Implementation
        pass

    def load_report(self, job_id):
        # Implementation
        pass

    def list_reports(self, filters):
        # Implementation
        pass
```

---

## Testing Strategy

### Unit Tests

- Provider abstractions
- Core logic (orchestration, synthesis)
- Budget validation
- Cost estimation

### Integration Tests

- End-to-end workflows
- Multi-provider scenarios
- Expert system workflows
- MCP server communication

### Test Isolation

- No real API calls in tests
- Mock provider responses
- Fixture-based test data
- Fast execution (<10s for full suite)

---

## Deployment Considerations

### Local Deployment

- Python 3.9+ required
- SQLite for queue (no external DB)
- Filesystem for storage (no external storage)
- Environment variables for configuration

### Cloud Deployment (Future)

- Container-based (Docker)
- Managed queue (SQS, Cloud Tasks)
- Managed storage (S3, Blob Storage)
- Multi-tenant support

---

## Future Architecture

### Level 5 Autonomy

Path from current Level 3 (Adaptive Planning) to Level 5 (Autonomous Meta-Researcher):

**Level 4 Requirements:**
- Lightweight memory (learn from past research)
- Basic verification (detect quality issues)
- Performance benchmarking (measure what works)

**Level 5 Requirements:**
- Continuous evaluation loop (self-assessment)
- Self-optimizing planner (improve strategies)
- Advanced verification (self-correcting research)
- Full cognitive autonomy (closed loop)

### Temporal Knowledge Graph

Track knowledge evolution over time:

```sql
CREATE TABLE claims (
    id UUID PRIMARY KEY,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    confidence REAL,
    learned_at TIMESTAMP,
    source_id UUID,
    valid_until TIMESTAMP
);

CREATE TABLE contradictions (
    id UUID PRIMARY KEY,
    claim_a UUID,
    claim_b UUID,
    detected_at TIMESTAMP,
    resolved BOOLEAN,
    resolution TEXT
);
```

### Expert Council Mode

Multi-expert deliberation:

```
User question → GPT-5 assembles optimal expert panel
    ↓
Round 1 → Each expert provides perspective
    ↓
Round 2 → GPT-5 facilitates debate
    ↓
Round 3 → Synthesis with consensus + dissent
```

---

See also:
- [expert_learning_architecture.md](expert_learning_architecture.md) - Expert system details
- [GROK_AS_DEFAULT.md](GROK_AS_DEFAULT.md) - Provider selection strategy
- [MODEL_SELECTION.md](MODEL_SELECTION.md) - Model selection guidelines
