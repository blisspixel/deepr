# Deepr Features Guide

Complete guide to all Deepr features as of v2.3

## Table of Contents

- [Research Operations](#research-operations)
- [Vector Store Management](#vector-store-management)
- [Campaign Management](#campaign-management)
- [Cost Management](#cost-management)
- [Queue Operations](#queue-operations)
- [Configuration](#configuration)
- [Analytics](#analytics)
- [Export and Integration](#export-and-integration)

## Research Operations

### Single Research Jobs

Submit individual deep research queries:

```bash
# Basic submission
deepr research submit "Your research question" --yes

# With automatic prompt refinement
deepr research submit "Your question" --refine-prompt --yes

# Preview refinement without submitting
deepr research submit "Your question" --refine-prompt --dry-run

# With file uploads
deepr research submit "Question" -f file1.pdf -f file2.md --yes

# Using existing vector store
deepr research submit "Question" --vector-store company-docs --yes

# Choose model
deepr research submit "Question" --model o3-deep-research --yes
```

**Available models:**
- `o4-mini-deep-research` (faster, cheaper, $0.50-2)
- `o3-deep-research` (comprehensive, $5-15)

### Checking Results

```bash
# Get results (checks provider once)
deepr research get <job-id>

# Download all completed jobs
deepr research get --all

# Wait for completion
deepr research wait <job-id>

# Check local status
deepr research status <job-id>

# Display saved result
deepr research result <job-id>

# Show detailed cost breakdown
deepr research result <job-id> --cost
```

### Automatic Prompt Refinement

Always-on optimization for all queries:

```bash
# Enable in .env
DEEPR_AUTO_REFINE=true
```

**What it adds:**
- Temporal context ("As of October 2025...")
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
deepr research submit "Query" --vector-store vs_abc123 --yes

# By name
deepr research submit "Query" --vector-store company-docs --yes
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

### Cost Tracking

```bash
# Overall summary
deepr cost summary

# By time period
deepr cost summary --period today
deepr cost summary --period week
deepr cost summary --period month
```

**Shows:**
- Total spending and breakdown
- Cost by model
- Budget percentage used
- Average cost per job
- Completed vs pending costs

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
deepr research export <job-id>

# Specific format
deepr research export <job-id> --format json
deepr research export <job-id> --format html
deepr research export <job-id> --format txt

# Custom output
deepr research export <job-id> --format html --output report.html
```

**Formats:**
- `markdown` - Markdown with citations
- `txt` - Plain text
- `json` - Structured JSON with metadata
- `html` - Formatted HTML report

### Cancel Jobs

```bash
# Cancel running job
deepr research cancel <job-id>
deepr research cancel <job-id> --yes
```

## Command Reference

### Global Options

```bash
deepr --version    # Show version
deepr --help       # Show help
```

### Command Groups

```bash
deepr research     # Research operations
deepr vector       # Vector store management
deepr queue        # Queue operations
deepr prep         # Campaign management
deepr team         # Team research (experimental)
deepr cost         # Cost management
deepr config       # Configuration
deepr analytics    # Usage analytics
deepr interactive  # Interactive mode
deepr docs         # Documentation
```

### Help for Commands

```bash
deepr <command> --help
deepr research submit --help
deepr vector --help
```

## Advanced Usage

### Combining Features

```bash
# Create persistent store, use for research
deepr vector create --name "docs" --files *.pdf
deepr research submit "Query" --vector-store docs --refine-prompt --yes

# Batch operations
deepr queue sync              # Update all statuses
deepr research get --all      # Download all completed

# Analytics-driven optimization
deepr analytics report --period month
deepr analytics failures
# Adjust based on insights
```

### Automation

```bash
# Daily batch job
deepr queue sync && deepr research get --all

# Cost monitoring
deepr cost summary --period today
```

### Best Practices

1. **Use prompt refinement** for better results
2. **Create vector stores** for document-based research
3. **Monitor costs** regularly with analytics
4. **Use pause/resume** for expensive campaigns
5. **Validate config** before production use
6. **Export important results** in multiple formats
7. **Sync queue** regularly if not using worker

## Integration Patterns

### CI/CD Integration

```bash
# In CI pipeline
deepr research submit "Release notes for v2.3" --yes > job_id.txt
job_id=$(cat job_id.txt | grep "Job ID:" | cut -d':' -f2)
deepr research wait $job_id
deepr research export $job_id --format markdown --output release_notes.md
```

### Batch Processing

```bash
# Process multiple queries
for query in query1 query2 query3; do
  deepr research submit "$query" --yes
done

# Later, download all
deepr research get --all
```

### Knowledge Management

```bash
# Build knowledge base
deepr vector create --name "kb" --files knowledge_base/*.md
deepr research submit "Summarize our architecture" --vector-store kb --yes
```

## Troubleshooting

### Common Issues

**API key not found:**
```bash
deepr config validate    # Check configuration
deepr config set OPENAI_API_KEY sk-...
```

**Job not completing:**
```bash
deepr queue sync         # Sync with provider
deepr research get <job-id>  # Check manually
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
deepr queue list --status failed
```

## Next Steps

- Read [INSTALL.md](../INSTALL.md) for setup
- See [ROADMAP.md](../ROADMAP.md) for upcoming features
- Check [CHANGELOG.md](../CHANGELOG.md) for latest changes
- Visit [README.md](../README.md) for quick start
