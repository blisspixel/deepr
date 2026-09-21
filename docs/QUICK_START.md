# Quick Start Guide

Set up local capacity, build one consultable expert from a source you trust,
and optionally preview a bounded provider request without dispatch.

This guide follows v2.50.19. Release installers include default research
formation, `expert build`, and `expert knowledge`. Research completion does
not certify practical guidance; review retained evidence and answers.

---

## Prerequisites

- Python 3.12 or higher
- Owned local Ollama with an installed model and cloud execution disabled
- An API key only when intentionally running supported live credential checks

Local expert workflows do not require an API key. No production plan adapter
is currently execution-eligible. Attended OpenRouter research is a separate
one-completion surface after explicit wallet and provider authorization;
expert formation cannot use it or fall back to a paid provider.

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

### 2. Optionally Configure API Credentials

```bash
cp .env.example .env
```

For an intentional provider readiness check, edit `.env` and add only the key
you intend to inspect. This does not enable production metered dispatch:

```bash
# Configure only providers you intend to use:
OPENAI_API_KEY=sk-...       # OpenAI readiness checks - https://platform.openai.com/api-keys
GEMINI_API_KEY=...          # Gemini readiness checks - https://aistudio.google.com/app/apikey
XAI_API_KEY=...             # xAI readiness checks - https://console.x.ai/
ANTHROPIC_API_KEY=...       # Anthropic configuration - https://console.anthropic.com/settings/keys
```

### 3. Verify Local Setup

```bash
deepr doctor --skip-connectivity
deepr capacity
```

The offline doctor command makes no provider call. Run plain `deepr doctor`
only when you intentionally want supported live checks for configured OpenAI,
Gemini, and xAI credentials. Anthropic and Azure remain configuration-only in
doctor. Base capacity directs local users to `capacity next`, registered plan
adapters to `capacity fleet`, and API research users to an exact preview.

Cancellation succeeds only when Deepr confirms the job transition,
cost-reservation closure, and provider-resource cleanup. A nonzero exit means cancellation was not fully
confirmed and the job should still be treated as active until its status is
checked again.

If at least one intended capacity path is ready, continue.

---

## Build Your First Expert

Local creation connects research, study, a reasoned perspective, and linked
knowledge in one bounded operation. Creating an empty profile is still available
when that is intentional.

### 1. Build The Research Foundation

```bash
deepr expert make "Web Dev Expert" --local -d "Decisions about reliable web platform architecture"
```

This uses free web search and your installed local model. It records progress
while retaining sources, studying source summaries, mechanisms and failures,
forming positions, and writing an evidence graph and linked Markdown. Defaults
allow at most 12 queries, 12 URLs, 120,000 study characters, 40 model calls, and
45 minutes. A failed or interrupted build retains its evidence and reason.
It never falls back to a paid provider. Review the resulting guidance before use.

### 2. Inspect The Knowledge And Build Record

Regenerate the linked knowledge view without inference:

```bash
deepr expert knowledge "Web Dev Expert"
```

The command prints the index path. Follow its positions to findings and retained
source identities. The expert directory also contains `formation/current.json`
and a dated `formation/runs/<operation>/review.md`. Unmatched excerpts, unknown
dates and missing coverage stay visible. These are research records, not an
automatic certificate of expertise.

### Optional: Start From Chosen Sources

```bash
deepr expert make "Another Expert" --local --profile-only
deepr expert retain "Another Expert" ./source.md --title "Trusted starting source"
deepr expert build "Another Expert" --no-discovery
```

Save a UTF-8 source you are allowed to use as `source.md` first. Retention is
content-addressed. `--no-discovery` suppresses new search; it does not imply
that retained material is current. For explicit later maintenance, the separate
`expert study --local` and `expert brief --local` commands remain available.

### Recover An Incomplete Build

```bash
deepr expert build "Web Dev Expert"
```

Each retry has a new operation record and limits. It retains earlier attempts
and offers completed study lenses for reuse only when model and corpus
fingerprint match. Existing formed experts require explicit maintenance.

### 3. Consult The Expert

```bash
deepr expert consult "What should I verify next?" --expert "Web Dev Expert" --local
```

This is a one-shot bounded consult over stored expert state followed by one
synthesis call. With several `--expert` options, Deepr selects one stored-state
packet per expert, but the experts do not exchange turns and the consult does
not write beliefs or graph state. Use `--output FILE` to save the complete
artifact explicitly. See [Three Expert Council And Learning Workflow](THREE_EXPERT_COUNCIL.md)
for a three-domain example and strict `$5` monthly cap.

Consultation does not automatically check the latest sources yet. Explicit
fresh-context maintenance is available when currency matters; inspect its
coverage before relying on updated guidance. Default preparation before advice
is the [next user-facing milestone](../ROADMAP.md#living-expertise-and-evolving-perspective).

These steps avoid paid API calls. Research building and consultation require an
available local Ollama model. Use `deepr capacity` when local capacity is not
ready.

### Optional: Define Purpose And Acceptance Cases

For a long-lived expert, review a blueprint before or after creating the local
profile:

```bash
deepr expert blueprint "Web Dev Expert" --template --output expert-blueprint.json
# Edit the mission, decision use cases, source policy, and acceptance cases.
deepr expert blueprint "Web Dev Expert" --from-file expert-blueprint.json --output expert-blueprint-preflight.json
# Apply only after actual review; the resulting operator identity is not verified.
deepr expert blueprint "Web Dev Expert" --from-file expert-blueprint.json --apply --attested-by operator
```

The template and preflight are explicitly unreviewed and non-authoritative.
Preflight validates structure, normalization, hashing, and the review checklist
at `$0`.

---

## Optional Bounded API Preview

Skip this section when you want only local or explicit plan expert workflows.

### Set Budget Protection

```bash
deepr budget set 5
```

Keep the binding monthly ceiling at $5 or less and use a smaller per-job
ceiling for each previewed request. Preview does not need wallet funding and
does not create a reservation. A wallet, calendar ceilings, and job ceilings
are independent. None of them buys provider credits or proves that provider
overage is disabled.

### Preview One Bounded Job

```bash
deepr research "What are the top 3 programming languages for web development in 2026 and why?" --provider openai --model o4-mini-deep-research --preview
```

This will:

1. Show the exact hard request maximum without spending.
2. Validate whether the provider, model, tools, and payload have a finite envelope.
3. Make no provider request and write no paid result.

General production metered dispatch is blocked until a provider-specific
authenticated account-control verifier and current account, scope, and
credential resolver are installed. A budget or local evidence file cannot
remove that block. The attended absorb transaction additionally requires a
funded wallet, a finite job ceiling, and provider-authenticated prepaid or hard
stop evidence. No such production account-control adapter ships today. Local
and safety-eligible plan workflows remain available.

### Preview Batch Routing At $0

```bash
deepr research --auto --batch queries.txt --preview
```

Metered batch and multi-phase execution are gated until every nested call
belongs to one durable parent reservation.

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
gated. Local, explicit plan-quota, scheduled, dry-run, history-only,
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

# Check local configuration without provider calls
deepr doctor --skip-connectivity
```

---

## Cost Guidance

| Task | Deepr cost posture | Availability |
|------|-------------------|--------------|
| Direct bounded research preview | Exact maximum from `--preview`; no provider call | Works for supported finite envelopes |
| Local expert setup and maintenance | `$0` provider cost | Works with local capacity |
| Explicit plan expert maintenance and consult | `$0` Deepr ledger cost; consumes external plan quota | Works for supported non-metered adapters |
| Local expert consult | `$0` provider cost | Works |
| Attended API expert absorption | Complete transaction, but no provider dispatch with the adapters shipped today | Requires a funded cumulative wallet, finite job ceiling, explicit confirmation, and authenticated provider prepaid-no-overage or hard-stop proof |
| Other metered API dispatch | No dispatch | Gated pending complete transaction ownership and authenticated account controls |

`deepr budget set <amount>` controls monthly approval behavior and binds
`deepr run`, `deepr research`, and MCP research. For an authoritative hard
cap on every surface (CLI, web, REST), set `DEEPR_MAX_COST_PER_JOB`,
`DEEPR_MAX_COST_PER_DAY`, and `DEEPR_MAX_COST_PER_MONTH`. Ledger writes fail
closed with no lenient opt-out. Audit spend vs
artifacts anytime with `deepr costs doctor`; `deepr doctor` and the web
dashboard surface over-budget and orphaned spend loudly.

---

## Troubleshooting

### "No API key found"

Some live API readiness checks require a configured provider key. Production
API research remains blocked. Local and explicit plan expert workflows do not
require a key; run `deepr capacity` to see the appropriate next inspection.

### "Budget exceeded"

Inspect the exact preview first. Choose a cheaper bounded model or lower the
per-job request. Keep the binding monthly ceiling at `$5` or less.

### "Job failed"

Check status for error details: `deepr jobs status <job-id>`

### Research taking too long

Deep research can take 15 to 30 minutes after the local setup is complete. Check
status periodically.

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
# 1. Inspect executable capacity
deepr capacity

# 2. Create a local expert profile
deepr expert make "Python Async Expert" --local -d "Python asynchronous system design"

# 3. Retain one trusted UTF-8 source
deepr expert retain "Python Async Expert" ./source.md --title "Trusted asyncio source"

# 4. Extract cited findings on local capacity
deepr expert study "Python Async Expert" --local

# 5. Form the inspectable view the consult will use
deepr expert brief "Python Async Expert" --local

# 6. Consult the expert on local capacity
deepr expert consult "Which asyncio pitfalls matter most?" --expert "Python Async Expert" --local

# 7. Optionally preview a bounded premium request without dispatch
deepr research "Python async/await best practices" --provider openai --model o4-mini-deep-research --preview
```

---

## What's Next?

- [EXAMPLES.md](EXAMPLES.md) - Real-world use cases
- [EXPERTS.md](EXPERTS.md) - Expert system guide
- [FEATURES.md](FEATURES.md) - Complete command reference
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical details

---

## Tips for Success

1. **Start from evidence you trust** - Retain one source, study it, brief it, then consult
2. **Be specific** - Vague prompts produce vague results (see [EXAMPLES.md](EXAMPLES.md))
3. **Add useful capacity** - Configure only the provider keys, admitted local models, or explicit plan backends you intend to use
4. **Monitor costs** - Check `deepr costs show` regularly
5. **Preview every metered request** - Routing is advisory and production dispatch remains gated
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
