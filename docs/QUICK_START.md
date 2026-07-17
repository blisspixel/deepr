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
deepr expert blueprint "Web Dev Expert" --template --output expert-blueprint.json
# Edit the mission, decision use cases, source policy, and acceptance cases.
deepr expert blueprint "Web Dev Expert" --from-file expert-blueprint.json --output expert-blueprint-preflight.json
# Apply only after actual review; the resulting operator identity is not verified.
deepr expert blueprint "Web Dev Expert" --from-file expert-blueprint.json --apply --attested-by operator
deepr expert make "Web Dev Expert" --local --files "./docs/*.md"
```

The template and preflight are explicitly unreviewed and non-authoritative.
Preflight performs strict structural validation, normalization, hashing, and a
review checklist at `$0`. After an operator attests that review occurred, copy
your documents into a local expert profile without a provider call.

### Consult an Expert

```bash
deepr expert consult "What should I verify next?" --expert "Web Dev Expert" --local
```

This is a one-shot bounded consult over stored expert state followed by one
synthesis call. With several `--expert` options, Deepr selects one stored-state
packet per expert, but the experts do not exchange turns and the consult does
not write beliefs or graph state. Use `--output FILE` to save the complete
artifact explicitly. See [Three Expert Council And Learning Workflow](THREE_EXPERT_COUNCIL.md)
for a three-domain example and strict `$10` cap.

### Prepare A Longitudinal Value Review

```bash
deepr eval expert-value "Web Dev Expert" --template --output expert-value-review.json
# After all four arms and the operator semantic and protocol attestations:
deepr eval expert-value "Web Dev Expert" --from-file expert-value-review.json --output expert-value-report.json
deepr eval expert-value "Web Dev Expert" --from-file expert-value-review.json --artifact-root ./eval-artifacts --output expert-value-verified.json
```

Template generation and aggregation cost `$0` and make no model or provider
calls. Semantic and protocol attestations explicitly deny verified identity and
human-authorship claims. Operator-attested aggregation does not open referenced
files or verify the attester identity;
`--artifact-root` recomputes every declared SHA-256 digest inside that root
without network access. The evaluator does not run the arms, inspect answer
text, select a winner, or change a default. Arm execution is a separate
capacity decision.

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

`deepr budget set <amount>` controls monthly approval behavior. For an
authoritative hard cap, set `DEEPR_MAX_COST_PER_JOB`,
`DEEPR_MAX_COST_PER_DAY`, and `DEEPR_MAX_COST_PER_MONTH`; use
`DEEPR_COST_TRACKING_STRICT=1` so a required ledger write fails closed.

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
deepr expert consult "Which asyncio pitfalls matter most?" --expert "Python Async Expert" --local
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
