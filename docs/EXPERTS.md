# Expert System Guide

> **Note**: Model names and capabilities live in the registry (`../src/deepr/providers/registry.py`), the single source of truth. AI moves fast - verify at provider websites.

## Overview

Deepr's expert system creates domain experts from documents that can answer
questions, recognize knowledge gaps, and propose the next bounded research or
maintenance step. Explicit local and non-metered plan workflows can execute
documented updates; metered autonomous expert work is gated in v2.36.
Expert learning is not passive document accumulation. New material is processed
into canonical beliefs, concepts, hypotheses, stance, original ideas,
provenance refs, temporal graph edges, contradiction signals, gap backlogs, freshness watchlists, and
regenerated digest, memory-card, or handoff views.

Every serious expert should start with an explicitly unreviewed blueprint draft
that names its proposed mission, non-goals, real decision use cases, source
policy, update cadence, and held-out acceptance cases. A zero-call preflight
validates structure and packages the draft for review without claiming semantic
quality or authority. Only an operator-attested applied blueprint becomes
canonical evaluation intent. Later, operator-attested outcome records capture
whether an expert-supported decision succeeded, failed, was mixed, or remains
unresolved. Deepr does not verify reviewer identity or claim human authorship.
Neither canonical artifact authorizes spend, provider dispatch, belief changes,
routing changes, or external actions.

`deepr expert memory-card NAME` previews a generated `EXPERT.md` orientation
view. Add `--write` to atomically write it under the expert directory. The card
is a `$0`, read-only derived view over profile, manifest, belief events,
self-model state, and metacognitive perspective state such as original ideas.
It is useful for humans and host agents, but it is never canonical memory and
should not be hand-edited as authority.

## What Makes It Different

Traditional RAG systems:
- Static documents in vector store
- Query - retrieve - answer
- Never changes, never grows

Deepr experts:
- Recognize knowledge gaps
- Propose research when needed; execution remains capacity- and user-gated
- Integrate verified knowledge through an explicit graph-commit apply boundary
- Track what they know vs don't know
- Maintain concepts, hypotheses, stance, original ideas, and tradeoffs
- Keep up with current developments on their topic
- Explore new possibilities instead of only recalling stored claims
- Build on previous learning

The point is not to preserve old answers. A stale expert can be worse than no
expert because it may confidently carry forward assumptions it does not know are
wrong. Deepr treats older beliefs and summaries as revisable priors, then uses
freshness checks, contradiction surfacing, perspective deltas, and watchlists to
find where the expert needs to update its understanding.

## Quick Start

```bash
# Generate and edit an explicitly unreviewed purpose draft.
deepr expert blueprint "Azure Architect" --template --output expert-blueprint.json
# Perform every available deterministic pre-review check and save the result.
deepr expert blueprint "Azure Architect" --from-file expert-blueprint.json --output expert-blueprint-preflight.json
# Apply only after actual review, recording an operator attestation.
deepr expert blueprint "Azure Architect" --from-file expert-blueprint.json --apply --attested-by operator

# Create a local expert from documents.
deepr expert make "Azure Architect" --local --files docs/*.md

# Create a local-only expert profile with no provider API calls
deepr expert make "UI Experience Expert" --local -d "UI/UX for agentic research tools"

# Consult stored expert knowledge on local capacity.
deepr expert consult "How should we review this architecture?" --expert "Azure Architect" --local

# Or use an explicit plan-quota CLI for synthesis.
deepr expert consult "What evidence is missing?" --expert "Azure Architect" --plan claude

# Record the later observed decision result without changing expert knowledge.
deepr expert record-outcome "Azure Architect" --decision-id migration-2026 --summary "Choose the migration architecture" --result mixed --observation "Availability improved, but recovery time missed its target." --attested-by operator
deepr expert outcomes "Azure Architect"

# Regenerate the expert's derived memory card for humans and host agents
deepr expert memory-card "Azure Architect" --write

# Ask Deepr for the highest-value next actions from current structural evidence
deepr expert next "Azure Architect"
```

Claude Code is the current safety-eligible plan adapter. `deepr capacity`
lists other detected CLIs with their pre-dispatch refusal or explicit-only
status. A zero-dollar budget does not override those decisions.

## What Should This Expert Do Next?

```bash
deepr expert next "Azure Architect"
deepr expert next "Azure Architect" --limit 5 --json
```

The command reads operator-attested-blueprint presence, the current claim count,
freshness, open gaps,
contradictions, and durable loop outcomes, then returns a short list of
argument arrays. It costs `$0`, runs no recommended command, and changes no
state. The capacity check precedes scheduled compiled sync so the navigator
does not assume local Ollama is available or fall through to metered use.
`foundation`, `recovery`, `learning`, and `maintenance` are operational
navigation stages only. They are not semantic maturity scores and cannot prove
that an expert's perspective is accurate or improved.

## Creating Experts

### Define Purpose And Acceptance First

```bash
deepr expert blueprint "Expert Name" --template --output expert-blueprint.json
# Edit every blank required field, then create a non-authoritative preflight.
deepr expert blueprint "Expert Name" --from-file expert-blueprint.json --output expert-blueprint-preflight.json
# Apply only after actual review.
deepr expert blueprint "Expert Name" --from-file expert-blueprint.json --apply --attested-by operator
```

Templates are intentionally incomplete so a generic domain label cannot become
false precision. A completed draft uses `deepr-expert-blueprint-draft-v1`, not
the canonical blueprint schema. Preflight strictly validates, normalizes,
hashes, summarizes, and adds review questions without writing canonical state.
Its status is `structurally_valid_unreviewed`; it explicitly denies human-review
claims, semantic assessment, and scope authority. Apply appends a complete
operator-attested revision under the canonical expert directory and reapplying
identical content is idempotent. The canonical record says
`identity_verified: false` and `human_authorship_claimed: false`. A draft and
preflight can be prepared before the expert profile exists.
See [expert-purpose-and-value-loop.md](design/expert-purpose-and-value-loop.md)
for the contract and longitudinal evaluation plan.

### Basic Creation
```bash
deepr expert make "Expert Name" --local --files path/to/docs/*.md
```

### Local-Only Creation
```bash
deepr expert make "Expert Name" --local -d "Domain description"
deepr expert subscribe "Expert Name" "Domain topic"
deepr expert sync "Expert Name" --local --fresh-context -y
deepr expert sync "Expert Name" --local --deep-context -y
```

`--local` creates the expert profile and local document folders without
creating a provider vector store or uploading files. If you pass `--files`,
Deepr copies the seed documents into the expert's local documents folder and
records them in the profile. Local creation does not run the API-backed
`--learn` curriculum; use subscriptions plus `expert sync --local` for $0
maintenance.

The v2.36 safety gate also blocks provider-backed `expert refresh` and
`--synthesize`, API `fill-gaps` including consensus and deep modes, and API
`expert sync --compile-claims`. Paid `deepr eval calibrate --corpus` is gated;
`deepr eval calibrate --from` remains a `$0` read of existing graded pairs.
Each metered surface returns only after it has migrated to one durable per-call
and parent-run budget transaction with storage and tool pricing. Local and
explicit plan-quota expert paths remain available.

After creation, `deepr expert next NAME` is the shortest path through the
available controls. An empty local profile receives a subscription plus local
fresh-context compiled-sync plan; a stale or failed expert receives repair
actions before new unattended work.

### Record Decision Outcomes

```bash
deepr expert record-outcome "Expert Name" \
  --decision-id stable-decision-id \
  --summary "What was decided" \
  --result succeeded \
  --observation "What happened after the decision" \
  --attested-by operator \
  --trace-id optional-consult-trace \
  --evidence-ref optional-outcome-evidence
deepr expert outcomes "Expert Name" --json
```

Outcome observations are operator attestations, not deterministic conclusions
from text or proof of reviewer identity. Corrections append a new record with
`--supersedes`; earlier observations remain intact. The summary reports counts
and evidence linkage only. It does not infer semantic quality, update
confidence, learn a lesson, or change routing.

### Evaluate Longitudinal Expert Value

```bash
deepr eval expert-value "Expert Name" --template --output expert-value-review.json
# Run every case under the four frozen arms, add blinded operator semantic
# attestations, attest the protocol, then verify hashes and aggregate.
deepr eval expert-value "Expert Name" --from-file expert-value-review.json --output expert-value-report.json
deepr eval expert-value "Expert Name" --from-file expert-value-review.json --artifact-root ./eval-artifacts --output expert-value-verified.json
deepr eval expert-value "Expert Name" --from-file expert-value-review.json --json
```

The template binds to the exact latest blueprint revision and is intentionally
invalid until every source world, arm policy, trial artifact, measurement,
operator semantic attestation, and protocol attestation is complete. Both
attestation objects record `identity_verified: false` and
`human_authorship_claimed: false`; Deepr does not convert them into a
human-review claim. The four arms are `fresh_research`, `static_history`,
`compiled_expert`, and `maintained_expert`. Each blueprint acceptance case must
appear once under every arm, using a linear sequence of at least two hashed
source worlds that include supportive evidence, distractors, and noise.

The evaluator reports correctness, source relevance, factual support,
uncertainty calibration, false support, invalidated-belief reuse, abstention,
retention, forward and negative transfer, update latency, reviewer effort,
construction and maintenance cost, per-consultation cost, observed outcome
links, pairwise deltas, reproducible 95 percent paired-bootstrap intervals, and
cost-only break-even estimates. Failed updates remain in the completion
denominator without a fabricated latency, and stale-memory rates exclude cases
with no operator-attested invalidation. It does not run an arm, infer a semantic
label, emit a superiority flag, rank arms, assess statistical sufficiency,
claim causal attribution, or change a default. Operator-attested mode does not
open referenced files or verify attester identity. `--artifact-root` is the
explicit independent mode: it
recomputes every declared SHA-256 digest within one root and rejects absolute
paths, traversal, root or symlink escape, missing files, conflicting
declarations, and mismatches before writing a report. Both modes cost `$0` and
make no model, provider, or network calls; external arm execution can consume
recorded local, plan, or paid capacity.

Use `--fresh-context` when a local sync needs current web grounding. Use
`--deep-context` when the topic needs broader source coverage before the local
model synthesizes. Both modes stay free inside Deepr: explicit URLs are fetched,
`DEEPR_SEARXNG_URL` can point at a self-hosted SearXNG instance, and DuckDuckGo
is used only when the optional package is installed. API-key search backends are
not used.

Search receives the subscription topic plus a bounded focus, while the local or
plan model retains the full synthesis prompt. Search-discovered fresh packs need
two content-addressed sources and deep packs need three before generation;
explicit URL review retains a one-source path. If retrieval is thinner, Deepr
persists the attempted source pack and returns a retryable no-metered failure
without calling the model or advancing the subscription cadence.

### Gated Metered Autonomous Learning

Nonlocal `expert make` and `--learn` fail closed in v2.36 while hosted storage,
curriculum calls, nested research, and absorption move to one durable parent-run
budget transaction. Use local profile creation plus local or explicit plan
maintenance:

```bash
deepr expert make "FDA Regulations" --local --files docs/*.pdf
deepr expert subscribe "FDA Regulations" "FDA regulatory changes"
deepr expert sync "FDA Regulations" --local --fresh-context -y
```

An explicit plan-quota sync can replace `--local` when approved subscription
capacity is available. Neither path falls through to a metered API.

### Learning Curriculum

The gated `--learn` design uses a synthesis model to generate a curriculum. The
example below illustrates the intended preview, not a v2.36 dispatchable path:

```
Learning Curriculum (10 topics):
1. FDA 510(k) clearance process     Est: $0.20, 10 min
2. Pre-market approval requirements Est: $0.25, 12 min
3. Quality system regulations       Est: $0.15, 8 min
...

Total: $2.45
Budget limit: $10.00  WITHIN BUDGET

Proceed? [y/N]
```

## Expert Query and Chat

Standalone metered expert chat is gated in v2.36. `deepr expert chat`, browser
Socket.IO/REST chat, and `deepr_query_expert backend=api` fail closed before a
provider dispatch. This release does not claim live metered chat validation.
Restoration requires durable reserve, dispatch-mark, and settlement for every
provider call, hard output ceilings, all auxiliary calls charged to the parent
session budget, and serialized turns per session.

### Available Read-Only Paths
```bash
deepr expert consult "How should we handle tenant isolation?" --expert "Azure Architect" --local
deepr expert consult "Which assumptions need evidence?" --expert "Azure Architect" --plan claude
```

MCP hosts can also call `deepr_query_expert` with explicit `backend=local` or
`backend=plan`. These modes compile stored expert context into one read-only,
no-tool turn and never fall through to a metered API. API council synthesis is
a separate bounded surface and remains available with explicit approval.

### Gated Interactive Design

The interactive design can trigger research when it recognizes knowledge gaps,
but its metered provider dispatch is disabled in v2.36:

```
You: How should we handle OneLake security for multi-tenant SaaS?

Expert: "I don't have specific guidance on this. Let me research..."

[Triggers: standard_research "OneLake multi-tenant security SaaS"]
[Cost: $0.15]

Expert: "Based on my research, there are three approaches:
1. Workspace-per-tenant isolation
2. Lakehouse-per-tenant with RLS
3. Shared lakehouse with strict RLS
..."
```

### Research Tiers

Experts choose appropriate research depth:

| Tier | Cost posture | Use Case |
|------|--------------|----------|
| `quick_lookup` | Cheapest allowed lookup path; not assumed free | Simple factual questions |
| `standard_research` | Estimated and bounded before dispatch | Moderate complexity |
| `deep_research` | Highest-cost tier; budget and confirmation gates apply | Complex topics |

Exact price and latency depend on the current provider, model, search tools,
and response bounds. The provider registry and preflight estimate are
authoritative; this guide intentionally does not hardcode volatile dollar or
time ranges.

### Gated Slash Commands and Chat Modes

The interactive design includes 27 slash commands (use `/` in web, `\` in
CLI). These commands do not authorize a metered provider dispatch in v2.36.
Chat modes describe the intended expert behavior:

- **`/ask`** - Quick answers from knowledge base only
- **`/research`** - Default mode with all tools available
- **`/advise`** - Structured consulting recommendations with pros/cons
- **`/focus`** - Always-on chain-of-thought reasoning for complex analysis

Other useful commands:
- `/compact` - Summarize earlier messages to free token budget for longer sessions
- `/council "question"` - Consult multiple experts on cross-domain questions (see Expert Council below)
- `/plan "question"` - Break complex queries into parallel subtasks with live progress
- `/remember <text>` - Pin facts to the session context
- `/status` - Show session stats (messages, tokens, mode, budget remaining)
- `/help` - List all available commands

### Approval Flows

Expensive operations require approval before proceeding. The system uses three tiers:

| Tier | Behavior | Example |
|------|----------|---------|
| Auto-approve | Proceeds immediately | KB search, standard research |
| Notify | Shows cost, proceeds unless budget critically low | Deep research under $1 |
| Confirm | Blocks until user approves or denies | Deep research over $1, council over $3 |

In the web UI, confirmation appears as an inline card in the chat. In CLI, it's a simple y/n prompt.

### Context Compaction

Long conversations can exhaust the model's token budget. The `/compact` command summarizes earlier messages while keeping recent context intact:

```
/compact
# Compacted: 32 messages -> summary (kept last 4 messages)
```

The system suggests compaction automatically after 30+ messages or when estimated tokens exceed 80K.

## Preview a Curriculum

API curriculum `expert plan` is gated in v2.36. It cannot yet bind curriculum
generation and every resulting call to one durable run ceiling. Use the `$0`
structural navigator instead:

```bash
deepr expert next "Azure Architect" --json
```

## Managing Experts

```bash
# List all experts
deepr expert list

# Get expert details
deepr expert info "Azure Architect"

# Delete expert
deepr expert delete "Azure Architect" --yes
```

## Updating Knowledge

### Manual Learning
```bash
# Research a topic and add to expert
deepr expert learn "Azure Architect" "Azure AI Agent Service 2026"

# Upload additional files
deepr expert learn "Azure Architect" --files new_docs/*.md
```

Topic learning and the explicit `expert learn-web` alias require two fetched,
content-addressed sources before local or plan synthesis. Supplying a URL keeps
the one-source review path. Every attempt writes a source pack, manifest,
source notes, and snapshots below the configured expert root; successful runs
also write the synthesized report. Sparse retrieval exits retryably before a
model call and does not advance knowledge freshness. During absorption the
model selects the supporting source label for each candidate claim, and Deepr
stores only that durable source-note pointer rather than attaching every search
result to every belief.

### Fill Knowledge Gaps
```bash
# Preferred no-surprise path: local or plan-quota first
deepr expert route-gaps "Azure Architect" --execute --scheduled --top 3
```

API `fill-gaps`, including consensus and deep modes, fails closed in v2.36.
Use `route-gaps --execute` with local or explicit plan-quota capacity.

### Resume Paused Learning
Saved progress remains intact, but direct API `deepr expert resume` fails closed
in v2.36 pending the shared durable transaction. Continue maintenance through
local or explicit plan-quota sync while the resume path is migrated.

### Absorb a Report into Knowledge
Promote a completed research report into the expert's permanent beliefs instead
of leaving it a terminal artifact. Verification-gated: report-grounded claims are
extracted and weak claims dropped. The free word-overlap heuristics only *route*.
An initial model YES receives a fresh-context structured disconfirmation pass;
only two agreeing judgments can record a model-confirmed contradiction edge, so
phrasing-level false contradictions are not recorded as contested beliefs and
two different facts that merely share words
(e.g. "$10/M" vs "$30/M") are not silently merged. Genuine conflicts are flagged
contested (the existing belief is never overwritten without approval); the rest
are integrated (deduped) with the report id as provenance. Metered runs apply
one `--budget` ceiling across extraction and every dynamically routed semantic
verdict, then report aggregate settled cost. Local and explicit non-metered plan
capacity remain `$0`.
```bash
# Preview what would be absorbed (writes nothing)
deepr expert absorb "Azure Architect" <job_id> --dry-run

# Absorb (REPORT_ID is the job id, same one you pass to --context; see deepr search)
deepr expert absorb "Azure Architect" <job_id> --min-confidence 0.7 --budget 0.10
```

### Reflect on a Report (quality gate)
Self-evaluate a report against its question before relying on or absorbing it:
scores grounding, completeness, calibration, and directness, then returns a
verdict (accept / revise / re-research) with issues and follow-up queries. A
natural pre-step to `absorb`. Normal metered reflection fails closed in v2.36;
the scheduled capacity waterfall can run on admitted local or trusted explicit
plan capacity, or return a wait payload without spending.
```bash
deepr expert reflect "Azure Architect" <job_id> --scheduled
deepr expert reflect "Azure Architect" <job_id> --depth 2 --scheduled --json
```

## Knowledge Maintenance

### Health Check
Read-only, cost-$0 audit of an expert's knowledge state: freshness, recorded
contradiction candidates plus advisory router hits, claims missing source
provenance, decayed beliefs, lifecycle
archive candidates, the open-gap backlog, and documents ingested but never
synthesized. Prints findings plus a recommended-action menu (each action shows
its command, estimated cost, and the approval tier that would gate it).
Audit-only human and scheduled JSON output does not create a loop run or imply
that a recommended action is executing. Scheduled JSON uses
`deepr-health-check-action-plan-v2`. Explicit `--archive-stale` is a separate
mutation path and retains durable confirmation, overlap, and completion records.
Schedulable for periodic self-maintenance.
```bash
deepr expert health-check "Azure Architect"
deepr expert health-check "Azure Architect" --json   # structured, for agents
```

### Reconcile Missing Freshness Metadata

If a legacy or interrupted accepted write left an expert with live beliefs but
no knowledge cutoff, preview a cost-$0 reconciliation from the append-only
belief event log. The command accepts only an accepted create, update, or
revision event for a belief that is still live. `--apply` updates profile
freshness metadata and regenerates a Deepr-derived system message; it does not
call a provider, edit beliefs, or replace a custom system message.

```bash
deepr expert reconcile-freshness "Azure Architect"
deepr expert reconcile-freshness "Azure Architect" --apply -y
```

### Lifecycle Archival (consolidation pass)
Belief stores must not grow monotonically - the documented root failure mode
of agent memory. The audit lists beliefs eligible for archival, and
`--archive-stale` archives them ($0, no LLM). A belief qualifies only if it
passes every gate: decayed below the confidence floor, not updated or
re-evidenced in 90+ days, no recorded usage, and not a side of an open
contradiction (contested beliefs are signal, never garbage). Every archival is
event-logged with a full snapshot, so it is reversible belief-by-belief.
```bash
deepr expert health-check "Azure Architect" --archive-stale     # confirm first
deepr expert health-check "Azure Architect" --archive-stale -y  # no prompt
```
Design: [docs/design/belief-lifecycle.md](design/belief-lifecycle.md).

### Route Gaps to Instruments (and Execute the Fills)
Advisory by default (read-only, $0): map each open knowledge gap to the best
instrument to fill it - recon (infrastructure), distillr (academic), primr
(strategic), or general research (default) - with availability, cost estimate,
and rationale. With `--execute`, the highest-value research-route fills
actually run (budget-bounded, skip-not-fail) and their findings absorb through
the verification-gated pipeline. Specialist-instrument routes are deliberately
deferred with their command printed - paid multi-minute jobs never start as a
side effect of a sweep.
```bash
deepr expert route-gaps "Azure Architect"
deepr expert route-gaps "Azure Architect" --execute --dry-run    # preview, $0
deepr expert route-gaps "Azure Architect" --execute --budget 1 -y
```

### Stay Current: Subscriptions and Sync
Subscribe an expert to topics with a refresh cadence and per-sync budget; sync
researches only what is DUE with a delta-only prompt ("what changed since the
last sync; if nothing meaningful, say exactly so"), absorbs through the
verification gate, and reports the perspective delta. Idempotent per cadence
window - run it from cron or a host platform's scheduler and only due topics
spend money. A "no significant changes" answer skips the paid extraction.
```bash
deepr expert subscribe "Azure Architect" "Azure Landing Zone updates" --every 7 --budget 0.50
deepr expert subscriptions "Azure Architect"          # list, with due markers
deepr expert sync "Azure Architect" --dry-run         # preview, $0
deepr expert sync "Azure Architect" --local -y        # run due topics locally
```

### Auto Re-Research from Reflection
When `expert reflect` finds a report weak, it emits follow-up queries. With
`--execute-followups` they actually run (same budget discipline) and absorb -
reflection stops being advisory exactly when the report needs reinforcement.
```bash
deepr expert reflect "Azure Architect" <job_id> --execute-followups --scheduled --budget 1 -y
```

## Temporal Perspective Queries

A corpus is what was read; a perspective is what is *believed* - claims with
source-capped confidence, provenance, recency, and open conflicts. Three
read-side, cost-$0 queries expose the perspective (CLI and MCP):

### What Changed (re-sync)
The perspective delta since a timestamp: beliefs added / revised / contested /
archived, each with its reason and current snapshot. The cheap way for you (or
a host agent) to catch up with an expert instead of re-reading everything.
Exact with no window limit on stores with the belief event log.
```bash
deepr expert what-changed "Azure Architect" --since 7d
deepr expert what-changed "Azure Architect" --since 2026-06-01 --json
```

### Contested (recorded candidates)
Recorded contradiction candidates with both sides' claims, confidence,
provenance, and `model_confirmed` or `unverified` assurance are surfaced
deliberately, never smoothed into a narrative. The assurance label describes
the verification process, not independent semantic ground truth.
Resolution stays with `expert resolve-conflicts`.
```bash
deepr expert contested "Azure Architect"
```

### Why (introspection)
Why the expert believes something: evidence roots, the confidence trajectory
from the append-only event log, supporting/derived-from chains walked over the
typed belief graph, and any recorded contradiction candidates with assurance.
Accepts a belief id or claim
text (fuzzy matched). Use it to debug trust in a claim instead of taking the
confidence number on faith.
```bash
deepr expert why "Azure Architect" "landing zone subscription vending"
deepr expert why "Azure Architect" belief-a1b2c3 --depth 3 --json
```

### Recall Boundary
Local recall is a router, not a verdict. Belief, concept, and original-idea
recall candidates return `candidate_only` metadata for the next verifier or
context-selection step. Original-idea candidates are labeled as
`perspective_state`, carry the non-factual promotion policy, and cannot become
verified external facts without a later review or graph-commit path. Belief
recall can use a persisted local vector index when a caller supplies an
already-gated query embedding or asks for an explicit local `$0` query
embedding with `--local-embedding-model`; stale claim vectors are ignored, and
embedding generation remains explicit. Operators can refresh the local
belief-vector index from precomputed vectors with
`deepr expert refresh-semantic-recall --embeddings-json`, or compute the
vectors through a local Ollama embedding model at `$0` with
`--local-embedding-model`; neither path calls a metered embedding provider,
and the precomputed path reports the declared upstream estimate separately
from Deepr spend. Claim verification can
carry recall hits as read-only `recall_context`; the concrete sync verifier now
uses that context in its bounded prompt, and still owns support, contradiction,
deduplication, temporal scope, and edge judgment.
`deepr expert sync --local --compile-claims --recall-embedding-model MODEL` embeds
ready claim statements through the same local `$0` Ollama embedder so verifier
recall context can use the indexed belief vectors; if the local embedder fails,
recall degrades to lexical routing without blocking the gated verification
call. The persisted claim-verification sidecar records the exact recall
packets the verifier prompt used, so each packet's `method` field shows which
route actually produced it.
Host agents can call MCP `deepr_semantic_recall` for the same read-only
boundary.
```bash
deepr expert semantic-recall "Azure Architect" "subscription vending guardrails" --json
deepr expert semantic-recall "Azure Architect" "gpu deployment bottleneck" --query-embedding "[0.1,0.9]" --embedding-model local-test --no-lexical-fallback --json
deepr expert semantic-recall "Azure Architect" "gpu deployment bottleneck" --local-embedding-model nomic-embed-text --no-lexical-fallback --json
deepr expert refresh-semantic-recall "Azure Architect" --embedding-model local-test --embeddings-json ./belief-vectors.json --json
deepr expert refresh-semantic-recall "Azure Architect" --local-embedding-model nomic-embed-text --json
deepr eval recall "Azure Architect" --cases ./recall-cases.json --local-embedding-model nomic-embed-text --save
deepr expert sync "Azure Architect" --local --compile-claims --recall-embedding-model nomic-embed-text -y
```

### Self-Model (read-only current state)
Build a derived `deepr-expert-self-model-v1` record from the profile and
manifest. It reports capabilities, limits, current goals, calibration, learning
strategy, continuity, blockers, unresolved risks, and a bounded current-focus
packet for consults, sync learning loop records, and sync capacity waits. It
does not change goals, write expert state, or run a model.
```bash
deepr expert self-model "Azure Architect"
deepr expert self-model "Azure Architect" --focus-limit 3 --json
```

### Memory Card (generated `EXPERT.md`)
Preview or regenerate a durable orientation card for humans and host agents.
It includes identity policy, current stance, explicitly tagged theories and
insights, self-research agenda, what would change the expert's mind, agency
scope, calibration, goals, beliefs, gaps, contradictions, collaboration
guidance, and update policy. The card is derived from structured expert state,
costs `$0`, and is not canonical memory.
```bash
deepr expert memory-card "Azure Architect"
deepr expert memory-card "Azure Architect" --write
deepr expert memory-card "Azure Architect" --json
```

### Monitor (read-only proposal review)
Build a derived `deepr-metacognitive-monitor-v1` artifact from the self-model,
recent loop runs, and sanitized consult trace candidates. It emits
`review_required` proposals for self-model blockers, calibration review, failed
learning loops, capacity blocks, and gap/eval candidates. It does not apply
goal, strategy, prompt, tool, or skill changes.
```bash
deepr expert monitor "Azure Architect"
deepr expert monitor "Azure Architect" --json
```

### Promote Monitor Proposals (reviewed gap/eval promotion)
Preview or apply one selected monitor proposal. Preview is the default and
writes nothing. `--apply` is required to promote a `gap_or_eval_candidate` into
the metacognition gap backlog, a local eval-case artifact under
`data/benchmarks`, or both. Other proposal types stay review-only until their
own verifier-gated commands exist.
```bash
deepr expert promote-monitor "Azure Architect" meta_abc123 --target gap
deepr expert promote-monitor "Azure Architect" meta_abc123 --target gap --apply
deepr expert promote-monitor "Azure Architect" meta_abc123 --target eval --apply --json
deepr expert promote-monitor "Azure Architect" meta_abc123 --target both --apply
```

### Review Consult Quality (scored review artifact)
Score one sanitized consult quality case from a trace candidate. The command
costs `$0` and makes no model call. A human or calibrated-model judge supplies
the semantic scores; Deepr validates only schema, score ranges, known failure
labels, reviewer presence, and the acceptance policy. Preview is the default.
`--apply` writes a `deepr-consult-quality-review-v1` artifact, and accepted
reviews can promote a gap, an eval case, or both. This path never commits
beliefs.
```bash
deepr expert consult-traces --json
deepr expert review-consult-quality "Azure Architect" consult_abc123 \
  --score uses_expert_state=5 \
  --score surfaces_uncertainty=5 \
  --score preserves_dissent=5 \
  --score actionability=5 \
  --score grounded_when_factual=5 \
  --score original_thought=5 \
  --reviewer operator \
  --decision accept \
  --target both
deepr expert review-consult-quality "Azure Architect" consult_abc123 \
  --score uses_expert_state=5 \
  --score surfaces_uncertainty=5 \
  --score preserves_dissent=5 \
  --score actionability=5 \
  --score grounded_when_factual=5 \
  --score original_thought=5 \
  --reviewer operator \
  --decision accept \
  --target both \
  --apply
```

`deepr expert judge-consult-quality` runs the same review path with an explicit
calibrated-model judge. Use `--local-judge-model MODEL` for local Ollama at `$0`
or `--plan BACKEND` with optional `--plan-model MODEL` for an explicit
plan-quota CLI. The `--api-provider` implementation is gated in v2.36 pending
the shared durable transaction. Plan judges consume subscription quota, record
`$0` Deepr cost metadata, and never fall back to metered provider APIs. Deepr
stores only validated review fields and calibrated judge metadata, not the raw
judge response or raw trace answer.

For Claude plan judging, `--plan-model` currently accepts only `sonnet`. Every
call first records live provider metadata proving paid extra usage is disabled,
then runs in safe mode with empty tool and MCP surfaces, no persistence, and no
API credential.
Failure to prove any part of that posture stops before model dispatch.

### Propose Self-Model Updates (review record)
Preview or write a verifier-gated self-model update review record for a
self-model-related monitor proposal. The command costs `$0`, never calls a
model, and never mutates the derived self-model. `--apply` writes an append-only
`deepr-expert-self-model-update-v1` artifact only after deterministic gates pass
for proposal type, target path, evidence refs, human review, zero cost, no
authority expansion, and no derived self-model mutation.
```bash
deepr expert propose-self-model "Azure Architect" meta_def456
deepr expert propose-self-model "Azure Architect" meta_def456 --apply --json
```

### Accept Self-Model Updates (outcome evidence gate)
Preview or write a separate acceptance artifact for a recorded self-model
update. Acceptance requires explicit outcome evidence refs such as
`loop_run:...`, `eval:...`, `source_pack:...`, or `human_review:...`, plus a
reviewer. `--apply` writes `deepr-expert-self-model-update-acceptance-v1`;
accepted records are later attached to sync loop-run context as read-only
guidance. They do not grant new authority or mutate the derived self-model.
```bash
deepr expert accept-self-model "Azure Architect" data/self_model_updates/azure-architect/self_model_update_meta_def456_20260626_120000000000.json --outcome-evidence loop_run:loop_123 --reviewer operator
deepr expert accept-self-model "Azure Architect" data/self_model_updates/azure-architect/self_model_update_meta_def456_20260626_120000000000.json --outcome-evidence loop_run:loop_123 --outcome-evidence human_review:review_1 --reviewer operator --apply --json
```

### Digest (browsable derived view)
Compile the belief store into a browsable Markdown digest: beliefs by domain
sorted by confidence, recorded contradiction candidates with both sides and
verification assurance, graph stats. $0, no
LLM call, byte-stable for an unchanged store. The digest is a derived view -
the belief store stays canonical, and the CLI refuses to overwrite a digest
that lost its derived-view marker (a hand-edited artifact must never silently
become canonical knowledge).
```bash
deepr expert digest "Azure Architect"            # writes <knowledge dir>/digest.md
deepr expert digest "Azure Architect" --print
```

## Sharing Experts as Skills

Package an expert as an installable agentskills.io SKILL.md for any compatible
host (Claude Code, Codex CLI, Gemini CLI, VS Code Copilot, Cursor, OpenClaw).
The skill triggers on the expert's domain and consults it through Deepr's MCP
tools - so the host needs a running Deepr MCP server with this expert present.
```bash
deepr expert export-skill "Azure Architect"                 # -> ./skills/deepr-expert-azure-architect/SKILL.md
deepr expert export-skill "Azure Architect" -o ~/.claude/skills/azure
deepr expert export-skill "Azure Architect" --print         # preview to stdout
```

## Export/Import

### Export for Sharing
```bash
deepr expert export "Azure Architect" --output ./exports/
```

Creates a portable package:
- Documents
- Worldview/beliefs
- Metadata
- README

### Import Expert
```bash
deepr expert import "New Expert" --corpus ./exports/azure_architect/
```

## Expert Skills

Skills are domain-specific capability packages that give experts unique tools and reasoning. A "Financial Analyst" expert with the `financial-data` skill can calculate ratios; a "Dev Lead" with `code-analysis` can audit dependencies and measure complexity.

### Managing Skills

```bash
# List all available skills
deepr skill list

# List skills on a specific expert
deepr skill list "Financial Analyst"

# Install a skill
deepr skill install "Financial Analyst" financial-data

# Remove a skill
deepr skill remove "Financial Analyst" financial-data

# Show skill details
deepr skill info code-analysis

# Run a skill tool directly
deepr expert run-skill "Dev Lead" code-analysis complexity_report --args '{"code": "def foo(): pass"}'
```

### Creating Custom Skills

```bash
# Scaffold a new skill in ~/.src/deepr/skills/
deepr skill create my-custom-skill
```

This creates:
- `skill.yaml` - metadata, triggers, tool definitions
- `prompt.md` - domain-specific reasoning instructions
- `tools/` - Python tool implementations

Before writing one, read [docs/design/skill-authoring.md](design/skill-authoring.md) -
how to make a skill measurably good: narrow scope, trigger-style descriptions,
deterministic `tools/` (never a meaning-verdict), a verification-first design, and
a `## Gotchas` section seeded from real failures.

### Built-in Skills

| Skill | Tools | Purpose |
|-------|-------|---------|
| `web-search-enhanced` | `structured_extract` | Extract tables/facts from research text |
| `code-analysis` | `analyze_dependencies`, `complexity_report` | Dependency audit + cyclomatic complexity |
| `financial-data` | `calculate_ratios` | P/E, P/B, debt-to-equity, ROE, margins |
| `data-visualization` | `markdown_table`, `ascii_chart` | Format data as tables and charts |

### How Skills Work

- **Progressive disclosure**: Skill summaries are always visible in the expert's system prompt. Full prompt and tools load only when a skill activates.
- **Auto-activation**: Skills activate when user queries match keyword or regex triggers.
- **Three-tier storage**: Built-in skills ship with Deepr, user skills live in `~/.src/deepr/skills/`, expert-local skills in `data/experts/{name}/skills/`. Later tiers override earlier ones.
- **MCP bridging**: Skills can connect experts to external MCP servers for tools no generic expert would have.

### Skill Definition Format

```yaml
name: my-skill
version: "1.0.0"
description: "What this skill does"
domains: ["finance", "analysis"]
triggers:
  keywords: ["earnings", "P/E ratio"]
  patterns: ["compare .+ stocks"]
prompt_file: "prompt.md"
tools:
  - name: my_tool
    type: python          # or "mcp" for external servers
    module: tools.my_tool
    function: run
    description: "What this tool does"
    cost_tier: free       # free/low/medium/high
budget:
  max_per_call: 0.50
  default_budget: 2.00
```

## Architecture

### Components

```
src/deepr/core/
├── contracts.py    # Canonical types: Claim, Gap, DecisionRecord, ExpertManifest, Source

src/deepr/experts/
├── profile.py      # Expert metadata, usage tracking, get_manifest()
├── curriculum.py   # Learning plan generation
├── learner.py      # Autonomous learning execution
├── chat.py         # Interactive Q&A with streaming, modes, compaction
├── commands.py     # Command registry, ChatMode, MODE_CONFIGS
├── command_handlers.py # 27 slash command handler functions
├── approval.py     # ApprovalManager with three-tier policies
├── council.py      # Multi-expert consultation and synthesis
├── task_planner.py # Hierarchical task decomposition
├── portraits.py    # AI-generated SVG expert portraits
├── constants.py    # Shared model names, tool identifiers, budget fractions
├── router.py       # Model selection
├── beliefs.py      # Belief formation, to_claim() adapter
├── metacognition.py # Gap awareness, to_gap() adapter
├── memory.py       # Conversation memory
├── synthesis.py    # Knowledge synthesis, to_claim()/to_gap() adapters
├── gap_scorer.py   # EV/cost ranking for knowledge gaps
├── thought_stream.py # Decision records, reasoning traces (with callbacks)
├── cost_safety.py  # Budget controls
└── skills/         # Expert skills system
    ├── definition.py  # SkillDefinition, SkillTool, SkillTrigger
    ├── manager.py     # Discovery, indexing, trigger matching
    └── executor.py    # Python + MCP tool execution
```

### Knowledge Storage

```
data/experts/<name>/
├── profile.json        # Expert metadata
├── documents/          # Source documents
├── knowledge/
│   ├── worldview.json  # Synthesized beliefs
│   ├── gaps.json       # Known knowledge gaps
│   └── learning_progress.json
└── conversations/      # Chat history
```

## Beginner's Mind Philosophy

Experts are prompted with intellectual humility:

1. **Admit gaps**: Say "I don't know" when uncertain
2. **Source transparency**: Distinguish knowledge sources
3. **Research-first**: Research instead of guessing
4. **Question assumptions**: Verify potentially outdated info
5. **Depth over breadth**: Better to research deeply than answer superficially

## Budget Protection

Multiple layers prevent runaway costs:

### Per-Session Limits

The v2.36 fail-closed gate overrides metered chat session settings. Local and
explicit plan read-only query turns remain available. A future restored session
must reserve its full approved ceiling before every call, mark dispatch
durably, settle every outcome, bound output, charge auxiliaries to the same
parent budget, and serialize turns.

### Hard Limits (Cannot Override)
- Per operation: $10 max
- Per day: $50 max
- Per month: $500 max

### Pause/Resume
When learning hits limits, progress is saved. Direct API resume fails closed in
v2.36 while its durable transaction is migrated; saved progress is not deleted.

See [ARCHITECTURE.md](ARCHITECTURE.md#security) for full budget protection details.

## Advanced Features

### Claims and Confidence

Experts track structured **claims** - atomic assertions with confidence scores, source provenance, and contradiction tracking. Claims are canonical types defined in `core/contracts.py`:

- Each claim has a confidence score (0.0-1.0) with time-based decay
- Sources carry a `TrustClass` (primary, secondary, tertiary, self_generated) and content hash
- Claims track contradictions and supersession chains
- View claims via web API: `GET /api/experts/<name>/claims?min_confidence=0.7`

**Source-trust ceilings (deterministic, applied at read time like decay):**
a belief's displayed confidence is capped by its provenance tier, and no model
judgment can lift the cap - only new, better-sourced evidence can.

| Trust tier | Ceiling | Typical sources |
|---|---|---|
| tertiary, one source | 0.60 | web search results, research syntheses (the default) |
| tertiary, 2+ independent sources | 0.80 | the same claim absorbed from different reports |
| secondary / primary | uncapped | official docs, first-party instruments / operator-supplied documents |

This is also the deterministic backstop against ingestion-time prompt
injection: a single poisoned web result cannot mint a near-certain belief, no
matter how confidently the extraction rates it. Honest framing throughout:
extraction confidence means "how strongly this report supports the claim",
never "how likely the claim is true" - calibration evidence for those numbers
is the v2.15 harness (see docs/design/calibration-and-trust.md).

Untrusted source and tool text is also bounded before it reaches model prompts:
fresh retrieval snippets, report text passed into absorption, first-party tool
findings, local document previews, prior campaign reports, completed research
summaries, company-intelligence snippets, and team findings are sanitized and
delimited as source data, not instructions. That boundary does not decide truth.
It only prevents embedded directives from blending into the instruction
hierarchy while the existing extraction, contradiction, dedup, and trust-floor
gates decide what becomes a belief (grounding checks are advisory and never
block a write).

Run `deepr eval red-team` to exercise the current local `$0` adversarial
canaries for those boundaries. The suite reports attack-success-rate for
prompt-boundary, MCP handoff and loop-status read-path, tool-spoofing, and
trust-floor probes, fails if a built-in attack succeeds, and can save a local
trend artifact with `--save`.

**Storage (the temporal knowledge graph):** the belief store is canonical -
`beliefs.json` (claims + typed edges: supports / contradicts / enables /
derived_from, with optional temporal contexts on edges) plus an append-only
`events.jsonl` recording every change.
Everything else (digest, SKILL.md export, reports) is a derived, regenerable
view.

### Knowledge Gap Scoring

Gaps are prioritized by **EV/cost ratio** - expected value relative to the estimated cost to fill:

```
ev_cost_ratio = expected_value / estimated_cost
expected_value = (priority / 5.0) + frequency_boost
estimated_cost = domain velocity lookup (fast=$0.25, medium=$1.00, slow=$2.00)
```

Higher-ratio gaps are filled first, making `expert route-gaps --execute --top N`
a rational allocation rather than arbitrary ordering. The legacy metered API
`expert fill-gaps` command fails closed in v2.36; local and explicit plan routes
remain available.

### Decision Records

Every executed workflow action, including routing decisions, source-trust
metadata, stop conditions, and gap-fill outcomes, can be captured as a
structured **decision record**:

- Type: routing, stop, pivot, budget, belief_revision, gap_fill, conflict_resolution, source_selection
- Includes: title, rationale, confidence, alternatives considered, evidence refs, cost impact
- Viewable via `--explain` flag in CLI (Rich table) and decision sidebar in Trace Explorer
- Queryable via web API: `GET /api/experts/<name>/decisions`
- Stored as `decisions.json` alongside `decisions.md` in expert logs

### Expert Manifests

An expert's full state is available as a typed **manifest** - a snapshot composing claims, scored gaps, decision records, and policies:

```bash
# Via MCP (for AI agents)
deepr_expert_manifest(expert_name="AI Policy Expert")
deepr_rank_gaps(expert_name="AI Policy Expert", top_n=5)
```

```bash
# Via web API
GET /api/experts/AI%20Policy%20Expert/manifest
```

The manifest includes computed properties: `claim_count`, `open_gap_count`, `avg_confidence`, and `top_gaps(n)`.

### Continuous Learning

Local and explicit plan maintenance can re-synthesize new knowledge.
Provider-backed `expert refresh` and `--synthesize` are gated in v2.36 pending
the shared durable parent-run budget transaction.

### Expert Council

Consult multiple experts on cross-domain questions. The system selects relevant
experts, or uses the explicit roster, independently selects a bounded packet of
stored state from each, and runs one synthesis over those packets. The result
contains agreements, disagreements, assumptions, risks, and a unified proposal.
Council members do not run model-generated turns and do not see one another's
output.

```bash
# Local bounded consult with an explicit saved artifact
deepr expert consult "Build vs buy?" --expert "Tech Architect" --expert "Business Strategist" --local --budget 0 --output ./build-vs-buy.json -y

# Explicit plan-quota bounded consult
deepr expert consult "Which assumption is weakest?" --expert "Tech Architect" --expert "Business Strategist" --plan claude
```

Current expert perspectives are stored-state reads and make zero model calls.
API mode can make at most one metered call for final synthesis. The complete
requested transaction ceiling is reserved upfront, and synthesis has a fixed
10 percent sub-ceiling. Therefore `--budget 10` cannot spend more than `$10`
and the synthesis call cannot spend more than `$1`. Local and eligible explicit
plan synthesis record `$0` in Deepr. Plan CLIs can still consume external quota,
credits, or vendor-side metered credentials that Deepr cannot distinguish.

Auto-selection includes up to 10 experts, default 3, with a relevance floor;
explicit rosters use the same cap. Exact, case, and slug aliases for one
canonical expert are rejected before work starts. The returned contract states
`expert_generation_calls: 0`, `experts_exchange_turns: false`, and no belief or
graph write authority.

#### Consulting on owned or prepaid capacity ($0)

`deepr expert consult` and the `deepr_consult_experts` MCP tool share one core, so
an external agent gets the same calibrated, versioned `deepr-consult-v1` artifact
(answer, each expert's perspective with confidence, agreements, dissent, cost).
Run the synthesis without touching a metered API key:

```bash
deepr expert consult "How do we keep expert knowledge current and cheap?" --plan claude
deepr expert consult "Cost vs quality tradeoff?" --local --max-experts 8 --max-elapsed-seconds 600
```

`--plan <id>` (codex, claude, ...) and `--local` run synthesis on explicit plan or local
capacity and disable live metered fallback, so a consult never silently bills an
API key. Over MCP this is `synthesis_backend: "plan" | "local"`. When Deepr asks
its own experts, this is a one-shot self-consult, not a recursive loop.
Every CLI and MCP consult writes a local `deepr-consult-trace-v1` record for the
improvement loop: question, requested experts, selected context metadata, capacity
posture, checks run, output artifact, and first-class synthesis failure events.
It also opens `deepr-consult-lifecycle-event-v1` before cancellable local model
discovery or backend dispatch. The append-only journal uses the same trace id and
records phase heartbeats, process ownership, finite logical-work, time, and spend
ceilings, observed and remaining spend, one-way capacity resolution, and typed
cancellation or failure. The current one-shot wrapper does not measure aggregate
provider token or context totals, so it omits those optional lifecycle fields.
It stores no answer or private reasoning. CLI and MCP default the cumulative
elapsed ceiling to 600 seconds and allow up to 21,600 seconds. It bounds
cancellable setup and generation and is checked at lifecycle boundaries. CLI
and MCP durable operations run off the
event loop but are still awaited through cancellation, so no timed-out writer
continues invisibly. Cancellation never falls through to another backend.
Every local and cross-process trace lock wait is capped at five seconds. Active
lifecycle and final-trace writes also use the smaller remaining allowance.
Pre-dispatch contention is retryable; contention after provider work may have
run is non-retryable and path-safe until finalization-only resume exists. The
same rule applies to elapsed stops: only a stop before provider work is
retryable. Typed storage I/O failures distinguish an unambiguous pre-write
failure from a possibly partial append. A settled metered cancellation estimate
is copied into lifecycle spend evidence only after canonical settlement.
MCP consult results also return `structuredContent` for clients that support the
current MCP structured-result contract, while preserving text JSON for older
hosts.
When the consulted expert profile exists, the perspective context also includes a
bounded read-only `self_model` block with current goals, calibration, blockers,
risks, and the current-focus packet. This is trace and handoff metadata, not an
automatic goal update.
If the expert has active original ideas, consult context also includes
`deepr-expert-perspective-state-v1` and the council response labels those ideas
as planning inputs, not verified external facts. This lets a host agent ask for
creative expert synthesis while preserving the fact vs perspective boundary.
Validate an external-agent consult path before using it for real questions:

```bash
deepr mcp validate-consult --json
deepr mcp validate-consult --live --synthesis-backend local --expert "AI Strategy Expert" --json
deepr mcp validate-consult http://127.0.0.1:8765/mcp --auth-token "$DEEPR_MCP_KEY" --expert "AI Strategy Expert" --json
```

The validation report is `deepr-mcp-consult-validation-v1`. It checks schemas,
trace linkage, no-metered capacity posture, cost fields, dissent handling, host
action boundaries, and secret redaction. It does not score answer meaning.
Review those traces with:

```bash
deepr expert consult-traces --json
deepr expert self-model "AI Strategy Expert" --json
```

The review output is `deepr-consult-trace-candidates-v1`: sanitized gap and eval
candidates for failed or low-context consults. It does not expose the local trace
file path or dump raw trace payloads into the host artifact.

A successful consult does not automatically become a gap, subscription, claim,
or graph edge. Save the full artifact with `--output`, review its unknowns, and
add source-seeking subscriptions explicitly. Never absorb council prose as
factual evidence. See
[Three Expert Council And Learning Workflow](THREE_EXPERT_COUNCIL.md) for a
copyable Temporal Knowledge Graphs, Digital Consciousness, and Model Context
Protocol setup with a strict `$10` cap.

Before adding live expert-to-expert rounds, run:

```bash
deepr eval deliberation --json
```

This emits `deepr-deliberation-eval-v1` from eleven frozen-fixture structural
checks at `$0`. The report validates bounds, lineage, independent first
positions, targeted challenges, the default evidence-seeking skeptic, dissent
preservation, typed stops, inert untrusted text, and proposal-only authority.
The report marks semantic quality `unreviewed` and does not enable the generic
deliberation design. The separate experimental investigation runtime below has
its own exact provider-call, token, context, and lifecycle contract.

### Experimental Evidence-First Investigations

`deepr expert investigate` is the local-only, bounded surface for a question
that needs actual fresh research and one expert-to-expert exchange. It differs
from `expert consult`: consult selects stored packets and makes no expert
generation calls, while investigate freezes expert snapshots, retrieves
separate source packs, records independent positions, routes one blinded
targeted challenge, checks the result, and synthesizes all named contributions.

```powershell
deepr expert investigate plan "What should Deepr improve next?" `
  --expert "Temporal Knowledge Graphs" `
  --expert "Digital Consciousness" `
  --expert "Model Context Protocol" `
  --local-model "qwen2.5:14b" `
  --review-model "qwen3-coder:30b" `
  --protocol discuss `
  --learning stage `
  --budget-usd 0 `
  --out .\investigation-plan.json
deepr expert investigate run .\investigation-plan.json -y
deepr expert investigate status <run-id>
deepr expert investigate inspect <run-id>
```

The plan preview makes zero model calls and zero network requests. The first
runtime supports native Ollama only, exact `$0` provider cost, and no fallback.
It owns one aggregate call, search, page, token, context, elapsed, disk, and
cost envelope across the entire roster. Pause, resume, and cancel operate on
durable phase artifacts.

`--learning stage` does not mean every expert is forced to mutate. Each expert
gets a separate compiler and verifier attempt over retrieved source evidence;
the result may be ready, blocked, or a no-op. Conversation, agreement, checker
prose, and synthesis are never evidence. No expert state is written until a
positive graph commit envelope is separately previewed and explicitly applied.
Extraction receives the target expert domain, and a separate verifier model
must judge a candidate materially relevant before deterministic code can admit
it. Word overlap never decides relevance.
The model orders candidates by usefulness. Deterministic form enforcement then
retains at most the first five per expert and records raw and dropped counts
before the separate verifier runs.

Both the answer and local model check remain semantically `unreviewed`. Do not
describe either as human-reviewed. Run `deepr eval investigation --json` for
the `$0` structural gate, then use held-out semantic comparison before making a
quality claim. See
[Three Expert Council And Learning Workflow](THREE_EXPERT_COUNCIL.md) for the
complete input, context, control, and staged-apply workflow.

## Limitations

- Early-stage software - more testing needed
- Vector search quality depends on document quality
- Standalone metered agentic chat is gated in v2.36; local and plan read-only
  turns cannot launch research.
- Deliberation and consult traces are derived proposal artifacts, not authority
  to spend, call tools, or write beliefs.
- Experimental investigation artifacts have the same proposal-only boundary.
  Local completion and automatic verification do not establish answer quality
  or human review.

## See Also

- [FEATURES.md](FEATURES.md) - Full command reference
- [MODELS.md](MODELS.md) - Model selection guide
- [../ROADMAP.md](../ROADMAP.md) - Development priorities
