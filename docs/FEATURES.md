# Deepr Features Guide

Complete guide to all Deepr features as of v2.8

## Table of Contents

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

A local web interface for managing research operations visually. Built with React, TypeScript, Vite, and Tailwind CSS.

### Starting the Dashboard

```bash
pip install -e ".[web]"
python -m deepr.web.app
# Open http://localhost:5000
```

### Pages

**Overview** - Landing page with active jobs, recent activity feed, spending summary, and system health status.

**Research Studio** - Submit new research with mode selection (research, check, learn, team, docs), model picker, priority, and web search toggle. Supports pre-filled prompts via URL query parameter.

**Research Live** - Real-time progress tracking for running jobs. Uses WebSocket for live status updates without polling.

**Results Library** - Browse and search completed research. Grid and list views with sorting and filtering by status.

**Result Detail** - Full markdown report viewer with a citation sidebar showing source URLs and snippets. Export dropdown for downloading results.

**Expert Hub** - List all domain experts with document counts, finding counts, knowledge gaps, and cost stats. Navigate to individual expert profiles.

**Expert Profile** - Three tabs: Chat (ask questions, get answers from the expert's knowledge), Knowledge Gaps (view gaps with priority, click to research), and History (learning timeline with costs).

**Cost Intelligence** - Spending trends over configurable time ranges, per-model cost breakdown with charts, budget limit controls with sliders, and anomaly detection.

**Trace Explorer** - Inspect research execution traces. View span hierarchy with timing, cost attribution, token counts, and model info for each operation.

**Settings** - Theme selection (light/dark/system), default model, web search toggle, and budget limit configuration.

### Keyboard Shortcuts

- **Ctrl+K** - Open command palette for quick navigation to any page
- Theme cycles through light, dark, and system modes via the header button

### Technical Details

- Code-split routing: each page loads independently via React.lazy
- Real-time updates: WebSocket (Socket.io) connection managed in the app shell
- State management: Zustand for UI state, React Query for server data
- Component library: Radix UI primitives (shadcn/ui pattern) with Tailwind CSS
- Charts: Recharts for cost trends, model breakdown, and utilization

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
- `o4-mini-deep-research` (faster, cheaper, $0.50-2)
- `o3-deep-research` (comprehensive, $5-15)

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

**--explain:** Shows task hierarchy with model, cost, and context sources per operation

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
deepr expert chat "Azure Architect" --agentic --budget 5
```

### Update Expert Knowledge

```bash
# Add knowledge via topic research
deepr expert learn "Azure Architect" "Azure AI Agent Service 2026"

# Fill knowledge gaps proactively
deepr expert fill-gaps "Azure Architect" --budget 5 --top 3

# Resume paused learning
deepr expert resume "Azure Architect"
```

### Export/Import Experts

```bash
# Export expert for sharing
deepr expert export "Azure Architect" --output ./exports/

# Import expert from corpus
deepr expert import "New Expert" --corpus ./exports/azure_architect/
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

## Cost Management

### Cost Estimation

```bash
# Estimate before submitting
deepr cost estimate "Your prompt"
deepr cost estimate "Prompt" --model o3-deep-research
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
```

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
deepr --help       # Show help
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
```

### Supporting Commands

```bash
deepr run          # Low-level research modes (focus, docs, project, team)
deepr jobs         # Job management (list, status, get, cancel)
deepr vector       # Vector store management
deepr prep         # Campaign management
deepr cost         # Cost estimation
deepr costs        # Cost dashboard (show, history, breakdown, timeline, alerts, expert)
deepr config       # Configuration
deepr analytics    # Usage analytics
deepr doctor       # System diagnostics
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
deepr expert chat "Domain Expert" --agentic --budget 5

# Batch operations
deepr jobs list --status completed
```

### Automation

```bash
# Daily batch job
deepr jobs list --status pending

# Cost monitoring
deepr cost summary --period today
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
deepr cost summary --period week
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
