# Quick Start Guide

Get started with Deepr in 5 minutes.

---

## Prerequisites

- Python 3.9 or higher
- At least one AI provider API key (OpenAI, Gemini, Grok, or Azure)
- 10-15 minutes for first research run

---

## Installation (2 minutes)

### 1. Clone and Install

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr
pip install -e .
```

### 2. Configure API Key

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```bash
# Choose at least one:
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
XAI_API_KEY=...
AZURE_OPENAI_API_KEY=...
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
deepr jobs list
```

### Get Results

When status shows "completed":

```bash
deepr jobs get <job-id>
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
# List all jobs
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

Check status for error details: `deepr jobs status <job-id>`

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
deepr jobs list
deepr jobs get <job-id>

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

1. **Start small** - Use `deepr research` with small budgets first
2. **Be specific** - Vague prompts produce vague results (see [EXAMPLES.md](EXAMPLES.md))
3. **Monitor costs** - Check `deepr cost summary` regularly
4. **Use fast models** - Grok and Gemini are 96-99% cheaper for most tasks
5. **Build experts gradually** - Start with documents, add learning later
6. **Set session budgets** - Always use `--budget` with agentic chat

---

## Getting Help

- `deepr --help` - CLI help
- [GitHub Issues](https://github.com/blisspixel/deepr/issues) - Report bugs
- [README.md](../README.md) - Full documentation
- [ROADMAP.md](../ROADMAP.md) - Future plans

---

**Ready to go deeper?** Check out [EXAMPLES.md](EXAMPLES.md) for advanced workflows and real-world scenarios.
