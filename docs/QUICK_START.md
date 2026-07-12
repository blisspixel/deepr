# Quick Start Guide

Get started with Deepr in 5 minutes.

---

## Prerequisites

- Python 3.12 or higher
- At least one capacity source: local Ollama, a supported non-metered plan CLI,
  or an API key for a provider/model/tool envelope Deepr can bound completely
- Provider-dependent time for a live research run

Local and explicit plan expert workflows do not require an API key. Direct API
research fails closed when pricing, tools, output, or context cannot be bounded.

---

## Installation (2 minutes)

### 1. Clone and Install

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr
pip install -e .                        # Core CLI (minimal dependencies)
```

Optional extras for additional features:

```bash
pip install -e ".[web]"                 # Web UI and MCP server
pip install -e ".[azure]"               # Azure cloud deployment
pip install -e ".[docs]"                # Document processing for experts
pip install -e ".[full]"                # All features
```

### 2. Configure API Key

```bash
cp .env.example .env
```

For direct API research, edit `.env` and add the key you intend to use:

```bash
# Configure only providers you intend to use:
OPENAI_API_KEY=sk-...      # Deep research + GPT models - https://platform.openai.com/api-keys
GEMINI_API_KEY=...          # Cost-effective research - https://aistudio.google.com/app/apikey
XAI_API_KEY=...             # Cheapest, web search - https://console.x.ai/
ANTHROPIC_API_KEY=...       # Complex reasoning - https://console.anthropic.com/settings/keys
```

### 3. Verify Setup

```bash
deepr doctor
```

Cancellation succeeds only when Deepr confirms the job transition,
cost-reservation closure, and provider-resource cleanup. A nonzero exit means cancellation was not fully
confirmed and the job should still be treated as active until its status is
checked again.

If at least one intended capacity path is ready, continue.

---

## Your First Research (3 minutes)

### Set Budget Protection

```bash
deepr budget set 5
```

Start with $5 to stay safe. You can increase later.

### Preview and Run One Bounded Job

```bash
deepr research "What are the top 3 programming languages for web development in 2026 and why?" --provider openai --model o4-mini-deep-research --preview
deepr research "What are the top 3 programming languages for web development in 2026 and why?" --provider openai --model o4-mini-deep-research --budget 2
```

This will:
1. Show the exact hard request maximum without spending.
2. Submit only if the same request envelope fits the explicit and configured budgets.
3. Settle provider-reported usage or the conservative held maximum.
4. Produce a cited report when the provider completes successfully.

### Check Status

While research runs:

```bash
deepr jobs list
```

### Get Results

When status shows "completed":

```bash
deepr jobs get <job-id>
```

Results are saved to the `data/reports/` directory with citations and sources.

---

## Next Steps

### Preview Batch Routing at $0

```bash
deepr research --auto --batch queries.txt --preview
```

Metered batch and multi-phase execution are gated in v2.36 until every nested
call belongs to one durable parent reservation.

### Create a Domain Expert

```bash
deepr expert make "Web Dev Expert" --local --files "./docs/*.md"
```

Copy your documents into a local expert profile without a provider call.

### Consult an Expert

```bash
deepr expert consult "What should I verify next?" --experts "Web Dev Expert" --local
```

This is a bounded local consult over stored expert state.

### Add Local Fresh Context

```bash
deepr expert subscribe "Web Dev Expert" "modern web development"
deepr expert sync "Web Dev Expert" --local --fresh-context -y
```

Standalone metered expert chat and unsafe metered expert lifecycle commands are
gated in v2.36. Local, explicit plan-quota, scheduled, dry-run, history-only,
and graded-file paths remain available where the command supports them.

Use `deepr expert next NAME` to inspect safe follow-up actions. No local or plan
query silently falls through to a paid provider.

---

## Common Commands

```bash
# List research jobs
deepr jobs list

# Check job status
deepr jobs status <job-id>

# Cancel running job
deepr jobs cancel <job-id>

# List experts
deepr expert list

# Get expert info
deepr expert info "Expert Name"

# View cost analytics
deepr costs show

# Check configuration
deepr doctor
```

---

## Cost Guidance

| Task | Deepr cost posture | Availability |
|------|-------------------|--------------|
| Direct bounded research | Exact maximum from `--preview`; actual provider billing varies | Works for supported finite envelopes |
| Local expert setup and maintenance | `$0` provider cost | Works with local capacity |
| Explicit plan expert maintenance and consult | `$0` Deepr ledger cost; consumes external plan quota | Works for supported non-metered adapters |
| Local expert consult | `$0` provider cost | Works |
| Metered batch, campaign, team, and agentic research | No dispatch | Gated in v2.36 |
| Standalone metered expert chat and unsafe lifecycle paths | No dispatch | Gated in v2.36 |

Always set a budget: `deepr budget set <amount>`

---

## Troubleshooting

### "No API key found"

Check your `.env` file has at least one provider key set.

### "Budget exceeded"

Inspect the exact preview first. Choose a cheaper bounded model or intentionally
raise the configured budget only if the maximum is acceptable.

### "Job failed"

Check status for error details: `deepr jobs status <job-id>`

### Research taking too long

Deep research can take 15-30 minutes. This is normal. Check status periodically.

### Need help?

```bash
deepr -h
deepr --help
deepr research --help
deepr expert --help
```

Or check [GitHub Issues](https://github.com/blisspixel/deepr/issues).

---

## Example Workflow

Complete workflow from zero to expert:

```bash
# 1. Set budget
deepr budget set 2

# 2. Research a topic
deepr research "Python async/await best practices" --provider openai --model o4-mini-deep-research --budget 2

# 3. Check results
deepr jobs list
deepr jobs get <job-id>

# 4. Create a local expert from results
deepr expert make "Python Async Expert" --local --files "data/reports/*/*.md"

# 5. Ask for the safest next learning or repair actions at $0
deepr expert next "Python Async Expert"

# 6. Consult the expert on local capacity
deepr expert consult "Which asyncio pitfalls matter most?" --experts "Python Async Expert" --local
```

---

## What's Next?

- [EXAMPLES.md](EXAMPLES.md) - Real-world use cases
- [EXPERTS.md](EXPERTS.md) - Expert system guide
- [FEATURES.md](FEATURES.md) - Complete command reference
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical details

---

## Tips for Success

1. **Start small** - Use `deepr research` with small budgets first
2. **Be specific** - Vague prompts produce vague results (see [EXAMPLES.md](EXAMPLES.md))
3. **Add useful capacity** - Configure only the provider keys, admitted local models, or explicit plan backends you intend to use
4. **Monitor costs** - Check `deepr costs show` regularly
5. **Use `--auto --preview` first** - Routing is advisory until the selected request clears exact admission
6. **Build experts gradually** - Start with local documents, then use local or explicit plan maintenance
7. **Keep metered chat gated** - Use local or explicit plan query and consult paths
8. **Switch devices sequentially** - If `DEEPR_DATA_DIR` is synced, stop Deepr services, use one writer at a time, and wait for sync before changing devices

---

## Getting Help

- `deepr -h` / `deepr --help` - CLI help
- [GitHub Issues](https://github.com/blisspixel/deepr/issues) - Report bugs
- [README.md](../README.md) - Full documentation
- [ROADMAP.md](../ROADMAP.md) - Future plans

---

**Ready to go deeper?** Check out [EXAMPLES.md](EXAMPLES.md) for advanced workflows and real-world scenarios.
