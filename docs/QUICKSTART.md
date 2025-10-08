# Deepr Quickstart Guide

Get started with Deepr research automation.

**Important:** Deepr uses OpenAI Deep Research models (o3-deep-research, o4-mini-deep-research), which conduct multi-step agentic research. These jobs can take **tens of minutes** to complete and may cost more than regular GPT calls.

## Prerequisites

- Python 3.10+
- OpenAI API key
- ~$0.10-$1.00 for testing

## Installation

```bash
# Clone the repo
git clone <your-repo-url>
cd deepr

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

## Basic Usage

### 1. Start the Research Agent

The research agent polls for completed jobs and updates the queue:

```bash
# Start in a separate terminal
python bin/start-research-agent.py

# Or in background (Windows)
start /B python bin/start-research-agent.py

# Linux/Mac background
python bin/start-research-agent.py &
```

### 2. Submit a Research Job

```bash
# Submit a simple research query
deepr research submit "What are the benefits of cloud computing?"

# With options
deepr research submit "Kubernetes best practices" \
  --model o3-deep-research \
  --priority 1 \
  --yes
```

Output:
```
Job ID: abc12345-...
Provider Job ID: resp_...

Next steps:
   deepr research status abc12345
   deepr queue list
```

### 3. Check Status

```bash
# Check specific job
deepr research status abc12345

# List all jobs
deepr queue list

# View statistics
deepr queue stats
```

### 4. Wait for Results (Recommended)

```bash
# Wait for job to complete and show result
deepr research wait abc12345

# Output:
  [0s] Status: PROCESSING...
  [10s] Status: PROCESSING...
  [20s] Status: PROCESSING...

  [OK] Job completed!

  # Cloud Computing Benefits

  Cloud computing offers several key advantages...

  Cost: $0.0524 | Tokens: 12,249
```

### 5. View Completed Results

```bash
# Get the full research report
deepr research result abc12345
```

## Complete Workflow Example

```bash
# Terminal 1: Start research agent
python bin/start-research-agent.py

# Terminal 2: Submit and wait
deepr research submit "Compare Docker vs Kubernetes" --yes
# Note the Job ID: abc12345

deepr research wait abc12345
# Waits and displays result when done
```

## CLI Commands Reference

### Research Commands

```bash
# Submit research job
deepr research submit "<prompt>" [options]
  --model o4-mini-deep-research|o3-deep-research
  --priority 1-5  (1=high, 5=low)
  --web-search/--no-web-search
  --yes  (skip confirmation)

# Check job status
deepr research status <job-id>

# Wait for completion (recommended)
deepr research wait <job-id>
  --timeout SECONDS  (default: 300)

# View completed result
deepr research result <job-id>
```

### Queue Commands

```bash
# List jobs
deepr queue list
  --status queued|processing|completed|failed
  --limit N  (default: 10)

# View statistics
deepr queue stats
```

## Cost Expectations

| Model | Input | Output | Typical Job |
|-------|-------|--------|-------------|
| o4-mini-deep-research | $1.10/M | $4.40/M | $0.05 - $0.50 |
| o3-deep-research | $11.00/M | $44.00/M | $0.50 - $5.00 |

### Example Costs

- Simple query (2 sentences): **$0.05 - $0.10**
- Medium research (5 paragraphs): **$0.20 - $0.50**
- Comprehensive report (10+ pages): **$1.00 - $5.00**

## Tips & Best Practices

### 1. Always Run the Research Agent

The research agent updates job status automatically. Without it, you must manually check if jobs complete.

```bash
# Keep research agent running in background
python bin/start-research-agent.py &
```

### 2. Use `wait` for Interactive Use

Instead of repeatedly checking status:

```bash
# Don't do this:
deepr research submit "..." --yes
deepr research status abc123  # check
deepr research status abc123  # check again
deepr research status abc123  # still checking...

# Do this:
deepr research submit "..." --yes
deepr research wait abc123  # waits and shows result
```

### 3. Monitor Costs

```bash
# Check recent job costs
deepr queue list --status completed

# View cost statistics
deepr queue stats
```

### 4. Start Small

Test with cheap queries first:

```bash
# Good first test (~$0.05)
deepr research submit "Write a haiku about programming" --yes
deepr research wait <job-id>
```

## Troubleshooting

### "Job not found" Error

The job might not be submitted yet. Check:

```bash
deepr queue list
```

### Job Stuck in "PROCESSING"

1. Check if research agent is running:
   ```bash
   # Should see "Job poller started" in research agent output
   ```

2. Check provider status manually:
   ```bash
   python tests/check_job_status.py <provider-job-id>
   ```

3. Restart research agent:
   ```bash
   # Kill existing research agent
   # Start new one
   python bin/start-research-agent.py
   ```

### "No API key" Error

1. Check .env file exists
2. Verify OPENAI_API_KEY is set:
   ```bash
   python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('Key:', os.getenv('OPENAI_API_KEY')[:10] + '...')"
   ```

## What's Next?

- [Architecture Overview](docs/ARCHITECTURE.md) - Understand how it works
- [API Documentation](docs/API.md) - Integrate with your apps
- [Advanced Usage](docs/ADVANCED.md) - Templates, batches, webhooks

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/your-org/deepr/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/deepr/discussions)
- **Docs**: [Full Documentation](docs/)

## Quick Reference Card

```bash
# Essential Commands
python bin/start-research-agent.py              # Start research agent
deepr research submit "..." --yes       # Submit job
deepr research wait <id>                # Wait for result
deepr queue list                        # List jobs
deepr queue stats                       # View stats

# File Locations
.env                                    # Configuration
queue/research_queue.db                 # Job queue (SQLite)
results/<job-id>/                       # Research outputs
logs/                                   # Research Agent logs
```

---

**Ready to automate your research? Start with a simple query and go from there!** 
