

# Deepr CLI Guide

## Overview

Deepr provides a modern, powerful command-line interface for research automation. The CLI follows the **verb-noun** command structure and provides cost estimates before executing expensive operations.

## Installation

```bash
# Install package
pip install -e .

# Verify installation
deepr --version

# Get help
deepr --help
```

## Command Structure

```
deepr <verb> <noun> [options]
```

**Examples:**
- `deepr research submit "Your prompt"`
- `deepr queue list`
- `deepr prep plan "Meeting scenario"`
- `deepr cost estimate "Research topic"`

## Quick Start

### Single Research Job

```bash
# Basic research
deepr research submit "What are the latest AI trends?"

# With options
deepr research submit "Kubernetes best practices" \
  --model o3-deep-research \
  --priority 1 \
  --no-web-search

# Skip confirmation
deepr research submit "Quick research" -y
```

### Multi-Angle Research (Prep)

```bash
# Plan research
deepr prep plan "Meeting with Company X about implementing Kubernetes"

# Execute all tasks
deepr prep execute "Meeting scenario" --all -y

# Execute specific tasks
deepr prep execute "Meeting scenario" --tasks 1,2,4

# Track batch
deepr prep status batch-abc123
```

### Queue Management

```bash
# List jobs
deepr queue list

# Filter by status
deepr queue list --status pending
deepr queue list --status completed --limit 20

# Statistics
deepr queue stats

# Watch in real-time
deepr queue watch

# Clear failed jobs
deepr queue clear --status failed -y
```

### Cost Tracking

```bash
# Estimate before submitting
deepr cost estimate "Research prompt"

# Cost summary
deepr cost summary
```

### Interactive Mode

```bash
# Guided workflow
deepr interactive
```

## Commands Reference

### research

Submit and manage individual research jobs.

#### research submit

Submit a new research job with cost estimation.

```bash
deepr research submit <prompt> [options]

Options:
  -m, --model [o4-mini-deep-research|o3-deep-research]
                                  Research model (default: o4-mini)
  -p, --priority INTEGER RANGE    Priority 1-5 (default: 3)
  --web-search / --no-web-search  Enable web search (default: enabled)
  -y, --yes                       Skip confirmation

Examples:
  deepr research submit "AI trends in 2025"
  deepr research submit "Technical analysis" --model o3-deep-research
  deepr research submit "Quick lookup" --priority 5 --no-web-search -y
```

**Output:**
```
########   ##########  ##########  ########      #######
               Submit Research Job

✓ Estimating cost...

📊 Cost Estimate:
   Expected: $0.12
   Range: $0.08 - $0.18

⚙️  Configuration:
   Model: o4-mini-deep-research
   Priority: 3 (normal)
   Web Search: enabled
   Prompt: AI trends in 2025

❓ Submit job for ~$0.12? [y/N]: y

✓ Submitting job...

✓ Job submitted successfully!

📋 Job ID: 7a3f9b2c-1d4e-5f6a-8b9c-0d1e2f3a4b5c

💡 Track status: deepr research status 7a3f9b2c
💡 View queue: deepr queue list
```

#### research status

Check status of a job.

```bash
deepr research status <job-id>

Example:
  deepr research status 7a3f9b2c
```

#### research result

View completed research result.

```bash
deepr research result <job-id>

Example:
  deepr research result 7a3f9b2c
```

#### research cancel

Cancel a pending or in-progress job.

```bash
deepr research cancel <job-id> [-y]

Example:
  deepr research cancel 7a3f9b2c -y
```

### prep

Plan and execute multi-angle research using GPT-5.

#### prep plan

Generate research plan from scenario.

```bash
deepr prep plan <scenario> [options]

Options:
  -n, --max-tasks INTEGER RANGE  Max tasks 1-10 (default: 5)
  -c, --context TEXT             Additional context
  -p, --planner [gpt-5|gpt-5-mini|gpt-5-nano]
                                 GPT-5 planner model (default: gpt-5-mini)
  -m, --model [o4-mini-deep-research|o3-deep-research]
                                 Research model (default: o4-mini)

Examples:
  deepr prep plan "Meeting with Company X about Kubernetes"
  deepr prep plan "Investor pitch" --max-tasks 3
  deepr prep plan "Technical review" --context "Focus on security"
  deepr prep plan "Complex scenario" --planner gpt-5 --model o3-deep-research
```

**Output:**
```
########   ##########  ##########  ########      #######
         Research Planning (GPT-5)

🎯 Scenario: Meeting with Company X about Kubernetes
🤖 Planner: gpt-5-mini
🔬 Research Model: o4-mini-deep-research

⏳ Generating 5 research tasks...

✓ Generated 5 research tasks:

1. Company X Infrastructure and Tech Stack Analysis
   Research Company X's current infrastructure, technology stack, and existing container...
   💰 ~$0.12

2. Kubernetes Best Practices for Enterprise Deployment
   Research Kubernetes deployment best practices specifically for enterprise environments...
   💰 ~$0.14

3. Migration Strategy and Rollout Planning
   Research proven strategies for migrating from legacy systems to Kubernetes...
   💰 ~$0.13

4. Cost Analysis and ROI Projections
   Research costs associated with Kubernetes deployment including licensing, infrastructure...
   💰 ~$0.11

5. Training Resources and Team Enablement
   Research training programs, certifications, and resources for upskilling teams...
   💰 ~$0.10

💰 Total Estimated Cost: $0.60

💡 Execute plan: deepr prep execute "<scenario>" --tasks <task-numbers>
💡 Execute all: deepr prep execute "Meeting with Company X about Kubernetes" --all

💾 Plan saved temporarily for execution
```

#### prep execute

Execute research plan.

```bash
deepr prep execute <scenario> [options]

Options:
  -t, --tasks TEXT               Task numbers (e.g., '1,2,4')
  -a, --all                      Execute all tasks
  -p, --priority INTEGER RANGE   Priority 1-5 (default: 3)
  -y, --yes                      Skip confirmation

Examples:
  deepr prep execute "Meeting scenario" --all
  deepr prep execute "Meeting scenario" --tasks 1,2,4
  deepr prep execute "Meeting scenario" --all --priority 1 -y
```

#### prep status

Track batch progress.

```bash
deepr prep status <batch-id>

Example:
  deepr prep status batch-abc123
```

**Output:**
```
########   ##########  ##########  ########      #######
         Batch Status: batch-abc123

🎯 Scenario: Meeting with Company X about Kubernetes

📊 Progress:
   Total: 5 tasks
   ⏳ Pending: 0
   🔄 In Progress: 2
   ✅ Completed: 3
   ❌ Failed: 0

📈 60% complete
💰 Total Cost: $0.36

📋 Tasks:
   ✅ Company X Infrastructure and Tech Stack Analysis
   ✅ Kubernetes Best Practices for Enterprise Deployment
   🔄 Migration Strategy and Rollout Planning
   ✅ Cost Analysis and ROI Projections
   🔄 Training Resources and Team Enablement

💡 View results: deepr research result <job-id>
```

### queue

Manage job queue.

#### queue list

List jobs in queue.

```bash
deepr queue list [options]

Options:
  -s, --status [all|pending|in_progress|completed|failed]
                        Filter by status (default: all)
  -n, --limit INTEGER   Max jobs to show (default: 10)

Examples:
  deepr queue list
  deepr queue list --status pending
  deepr queue list --limit 50
```

#### queue stats

Show queue statistics.

```bash
deepr queue stats
```

**Output:**
```
📊 Job Statistics:
   Total Jobs: 47
   ⏳ Pending: 5
   🔄 In Progress: 2
   ✅ Completed: 38
   ❌ Failed: 2

💰 Total Cost: $12.45
   Average per job: $0.33
```

#### queue clear

Clear jobs by status.

```bash
deepr queue clear [options]

Options:
  -s, --status [pending|failed]  Status to clear (default: failed)
  -y, --yes                      Skip confirmation

Examples:
  deepr queue clear --status failed
  deepr queue clear --status pending -y
```

#### queue watch

Watch queue in real-time.

```bash
deepr queue watch [--interval SECONDS]

Example:
  deepr queue watch
  deepr queue watch --interval 10
```

Press `Ctrl+C` to stop watching.

### cost

Estimate and track costs.

#### cost estimate

Estimate cost for a prompt.

```bash
deepr cost estimate <prompt> [options]

Options:
  -m, --model [o4-mini-deep-research|o3-deep-research]
  --web-search / --no-web-search

Examples:
  deepr cost estimate "AI trends"
  deepr cost estimate "Deep analysis" --model o3-deep-research
```

#### cost summary

Show cost summary.

```bash
deepr cost summary
```

**Output:**
```
💰 Total Spending: $12.45
   ✅ Completed: $11.20
   ⏳ Pending: $1.25

📊 Statistics:
   Completed Jobs: 34
   Average per job: $0.33
```

### interactive

Guided interactive mode.

```bash
deepr interactive
```

**Interactive Menu:**
```
👋 Welcome to Deepr Interactive Mode!
   Let's set up your research.

What would you like to do?

1. Submit single research job
2. Plan multi-angle research (Prep)
3. View queue status
4. Exit

Select option [1]:
```

## Common Workflows

### Workflow 1: Quick Research

```bash
# Single command with defaults
deepr research submit "Latest Kubernetes features" -y

# Check status
deepr research status <job-id>

# View result when done
deepr research result <job-id>
```

### Workflow 2: Comprehensive Prep

```bash
# Plan research
deepr prep plan "Preparing for technical interview at Company X"

# Review plan, then execute
deepr prep execute "Preparing for technical interview at Company X" --all

# Track progress
deepr queue watch

# Or check batch status
deepr prep status batch-abc123
```

### Workflow 3: Cost-Conscious Research

```bash
# Estimate first
deepr cost estimate "Complex research topic"

# If too expensive, adjust
deepr research submit "Complex research topic" \
  --model o4-mini-deep-research \
  --priority 5 \
  --no-web-search

# Check budget
deepr cost summary
```

### Workflow 4: Queue Management

```bash
# Check queue
deepr queue stats

# Clear failures
deepr queue clear --status failed -y

# Watch progress
deepr queue watch --interval 15
```

## Configuration

### Environment Variables

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Or Azure
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
```

### Config File

Edit `config/deepr.yaml`:

```yaml
# Cost limits
cost:
  daily_limit: 100.0
  monthly_limit: 1000.0
  per_job_limit: 10.0

# Defaults
defaults:
  model: o4-mini-deep-research
  priority: 3
  enable_web_search: true

# Planner
planner:
  model: gpt-5-mini  # gpt-5, gpt-5-mini, gpt-5-nano
  max_tasks: 5
```

## Tips & Best Practices

### Cost Optimization

1. **Estimate first**: Always run `deepr cost estimate` for expensive prompts
2. **Use o4-mini**: Default to o4-mini unless you need maximum depth
3. **Adjust priority**: Use priority 5 for non-urgent research
4. **Disable web search**: If you don't need current data
5. **Use prep wisely**: Plan once, execute only needed tasks

### Efficient Workflows

1. **Use `-y` flag**: Skip confirmations for trusted workflows
2. **Save aliases**: Create shell aliases for common commands
3. **Batch operations**: Use prep for related research
4. **Watch mode**: Use `queue watch` for long-running batches
5. **Interactive mode**: Use for exploration and learning

### Prompt Engineering

**Good Prompts:**
```bash
deepr research submit "Analyze Kubernetes security best practices for financial services"
deepr research submit "Compare React vs Vue for enterprise dashboards with specific criteria"
```

**Poor Prompts:**
```bash
deepr research submit "kubernetes"  # Too vague
deepr research submit "tell me about AI"  # Too broad
```

### Prep Scenarios

**Good Scenarios:**
```bash
deepr prep plan "Presenting AI roadmap to executive team next week"
deepr prep plan "Technical review of microservices migration for legacy app"
deepr prep plan "Due diligence for acquiring SaaS competitor"
```

**Poor Scenarios:**
```bash
deepr prep plan "AI stuff"  # Too vague
deepr prep plan "Research everything about topic X"  # Too broad
```

## Troubleshooting

### Command not found

```bash
# Ensure package is installed
pip install -e .

# Or run directly
python -m deepr.cli.main
```

### Permission denied (Unix/Linux)

```bash
chmod +x bin/deepr
```

### API key errors

```bash
# Check environment
echo $OPENAI_API_KEY

# Or set in .env file
cp .env.example .env
# Edit .env with your keys
```

### Job not found

```bash
# Check queue
deepr queue list

# Use full job ID
deepr research status 7a3f9b2c-1d4e-5f6a-8b9c-0d1e2f3a4b5c
```

### High costs

```bash
# Check summary
deepr cost summary

# Review limits
cat config/deepr.yaml

# Clear pending expensive jobs
deepr queue clear --status pending
```

## Advanced Usage

### Scripting

```bash
#!/bin/bash
# research_pipeline.sh

# Plan research
deepr prep plan "Market analysis for product X" \
  --max-tasks 3 \
  --planner gpt-5-mini

# Execute with high priority
deepr prep execute "Market analysis for product X" \
  --all \
  --priority 1 \
  -y

# Wait and check
sleep 60
deepr prep status batch-abc123
```

### CI/CD Integration

```yaml
# .github/workflows/research.yml
name: Automated Research

on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday 9am

jobs:
  research:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run research
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pip install -e .
          deepr research submit "Weekly AI news summary" -y
```

### Monitoring

```bash
# Cron job for monitoring
*/15 * * * * /usr/local/bin/deepr queue stats >> /var/log/deepr_stats.log
```

## Command Cheat Sheet

```bash
# QUICK REFERENCE

# Single research
deepr research submit "prompt" -y
deepr research status <id>
deepr research result <id>

# Multi-angle (Prep)
deepr prep plan "scenario"
deepr prep execute "scenario" --all -y
deepr prep status <batch-id>

# Queue
deepr queue list
deepr queue stats
deepr queue watch
deepr queue clear --status failed -y

# Cost
deepr cost estimate "prompt"
deepr cost summary

# Interactive
deepr interactive

# Help
deepr --help
deepr research --help
deepr prep --help
```

## Support

For issues or questions:
- GitHub: https://github.com/your-org/deepr
- Docs: `docs/` directory
- Help: `deepr --help`

---

**Knowledge is Power. Automate It.**
