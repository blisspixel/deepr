# Quick Start Guide

Get started with Deepr in 5 minutes.

---

## Prerequisites

- Python 3.9 or higher
- **One API key** from any supported provider (OpenAI, Gemini, Grok, Anthropic, or Azure)
- 10-15 minutes for first research run

> **One key is all you need.** Deepr works with any single provider. Add more keys later and auto mode will route queries to the best available model for each task.

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

Edit `.env` and add at least one API key:

```bash
# Pick one to start (add more later for smarter auto-routing):
OPENAI_API_KEY=sk-...      # Deep research + GPT models — https://platform.openai.com/api-keys
GEMINI_API_KEY=...          # Cost-effective research    — https://aistudio.google.com/app/apikey
XAI_API_KEY=...             # Cheapest, web search       — https://console.x.ai/
ANTHROPIC_API_KEY=...       # Complex reasoning          — https://console.anthropic.com/settings/keys
```

### 3. Verify Setup

```bash
deepr doctor
```

If all checks pass, you're ready.

---

## Your First Research (3 minutes)

### Set Budget Protection

```bash
deepr budget set 5
```

Start with $5 to stay safe. You can increase later.

### Run Simple Research

```bash
deepr research "What are the top 3 programming languages for web development in 2026 and why?"
```

This will:
1. Submit research job to AI provider
2. Take 5-15 minutes to complete
3. Cost approximately $0.50-$2.00
4. Produce a comprehensive cited report

### Check Status

While research runs:

```bash
deepr research list
```

### Get Results

When status shows "completed":

```bash
deepr research get <job-id>
```

Results are saved to `reports/` directory with citations and sources.

---

## Next Steps

### Try Multi-Phase Learning

```bash
deepr learn "GraphQL vs REST APIs: architecture, performance, developer experience" --phases 3
```

More comprehensive (15-30 min, $2-$5), connects multiple research phases.

### Create a Domain Expert

```bash
deepr expert make "Web Dev Expert" --files "./docs/*.md"
```

Upload your documents to create an expert you can chat with.

### Chat with Expert

```bash
deepr expert chat "Web Dev Expert"
```

Interactive Q&A with your custom knowledge base.

### Enable Autonomous Research

```bash
deepr expert chat "Web Dev Expert" --agentic --budget 3
```

Expert can trigger research when it encounters knowledge gaps.

---

## Common Commands

```bash
# List research jobs
deepr research list

# Check job status
deepr research status <job-id>

# Cancel running job
deepr research cancel <job-id>

# List experts
deepr expert list

# Get expert info
deepr expert info "Expert Name"

# View cost analytics
deepr cost summary

# Check configuration
deepr doctor
```

---

## Cost Guidance

| Task | Estimated Cost | Time |
|------|---------------|------|
| Simple research | $0.50-$2 | 5-15 min |
| Multi-phase learning | $2-$5 | 15-30 min |
| Expert creation (basic) | Free | 1 min |
| Expert with autonomous learning | $5-$20 | 30-90 min |
| Expert chat (no research) | $0.01-$0.10 | Instant |
| Expert chat (with research) | $0.50-$2 | 5-15 min |

Always set a budget: `deepr budget set <amount>`

---

## Troubleshooting

### "No API key found"

Check your `.env` file has at least one provider key set.

### "Budget exceeded"

Increase budget: `deepr budget set 10`

### "Job failed"

Check status for error details: `deepr research status <job-id>`

### Research taking too long

Deep research can take 15-30 minutes. This is normal. Check status periodically.

### Need help?

```bash
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
deepr budget set 10

# 2. Research a topic
deepr research "Python async/await best practices" --provider grok

# 3. Check results
deepr research list
deepr research get <job-id>

# 4. Create expert from results
deepr expert make "Python Async Expert" --files "reports/*/*.md"

# 5. Have expert learn more
deepr expert make "Python Async Expert" --files "./docs/*.md" --learn --budget 5

# 6. Chat with expert
deepr expert chat "Python Async Expert" --agentic --budget 3
```

---

## What's Next?

- [EXAMPLES.md](EXAMPLES.md) - Real-world use cases
- [EXPERTS.md](EXPERTS.md) - Expert system guide
- [FEATURES.md](FEATURES.md) - Complete command reference
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical details

---

## Tips for Success

1. **Start small** — Use `deepr research` with small budgets first
2. **Be specific** — Vague prompts produce vague results (see [EXAMPLES.md](EXAMPLES.md))
3. **Add more API keys** — Each key you add makes auto mode smarter (routes to best model per task)
4. **Monitor costs** — Check `deepr cost summary` regularly
5. **Use `--auto`** — Auto mode routes simple queries to $0.01 models, saves 90%+ on batch jobs
6. **Build experts gradually** — Start with documents, add learning later
7. **Set session budgets** — Always use `--budget` with agentic chat

---

## Getting Help

- `deepr --help` - CLI help
- [GitHub Issues](https://github.com/blisspixel/deepr/issues) - Report bugs
- [README.md](../README.md) - Full documentation
- [ROADMAP.md](../ROADMAP.md) - Future plans

---

**Ready to go deeper?** Check out [EXAMPLES.md](EXAMPLES.md) for advanced workflows and real-world scenarios.
