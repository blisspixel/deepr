License: Apache 2.0  
Author: Nick Seal (nick@pueo.io)  
Free to use, build on, fork, and share patterns.  
For commercial or enterprise use, contact nick@pueo.io

# Deepr

[![CI](https://github.com/blisspixel/deepr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/deepr/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.19.0-blue)](https://github.com/blisspixel/deepr/releases/tag/v2.19.0)

**Domain experts, not another chat window.**

In plain terms: you bring the capacity you already have. Cloud APIs give Deepr
the strongest full research path when you provide keys and a budget ceiling.
Plan-quota agent services are modeled as prepaid capacity and are being wired
behind quota probes. Local Ollama gives Deepr a true `$0` marginal-cost path for
high-volume expert maintenance. Deepr routes each research question toward the
cheapest capable option, then builds experts that remember what they learned.

ChatGPT, Gemini, and Copilot each give you deep research from one vendor behind a chat UI. Deepr is the layer underneath - it routes across all of them and builds persistent expert agents that learn over time. Each expert is a named role ("AI Strategy Expert", "Security Specialist", "Fabric Architect") that accumulates domain knowledge, tracks its own gaps, and can be consulted by humans or other agents alike. Deepr runs from scripts, cron jobs, and AI agent workflows - so your experts are always available as team members, not just tools you invoke manually.

```bash
# Auto-routes to the best model per query: Grok 4.20 Non-Reasoning -> GPT-5.4 -> o3-deep-research
# (--budget is a ceiling, not a price: most queries cost far less than the cap)
deepr research "Will open-weight frontier models erode OpenAI/Anthropic enterprise margins by 2027?" --auto --budget 3

# Expert accumulates knowledge across sessions, fills its own gaps
deepr expert chat "AI Strategy Expert" --budget 3

# Batch 50 queries overnight - auto mode picks the right model for each
deepr research --auto --batch queries.txt --budget 10
```

Multi-provider (OpenAI, Gemini, Grok, Anthropic, Azure). Callable from AI agents via MCP. Reports and experts saved locally as artifacts you own.

<p align="center">
  <img src="assets/dashboard.png" width="49%" alt="Dashboard - cost trends, job stats, activity feed" />
  <img src="assets/expert-hub.png" width="49%" alt="Expert Hub - persistent domain experts with knowledge tracking" />
</p>
<p align="center">
  <img src="assets/expert-profile.png" width="49%" alt="Expert Chat - agentic chat with slash commands and visible reasoning" />
  <img src="assets/models.png" width="49%" alt="Models & Benchmarks - provider comparison and quality rankings" />
</p>

## Why Deepr?

**If you need one research report, use ChatGPT Deep Research or Gemini.** They're easier. For a single question, they're the right tool.

**Who Deepr is for:** analysts and research teams who batch dozens of queries; developers building agents that need grounded, citable knowledge mid-task; anyone running research on a schedule instead of in a chat window. You should be comfortable with a terminal - or use the web dashboard once it's set up. If you ask ChatGPT one question a day on your phone, Deepr is more tool than you need.

**Deepr is for when research is infrastructure, not a one-off:**

- **Scaling research** - Batch 50 queries at $2 instead of clicking "Deep Research" 50 times. Auto-mode routes each query to the cheapest model that can handle it.
- **Building persistent experts** - Agents that accumulate knowledge across sessions, track beliefs with confidence, detect their own gaps, and research to fill them.
- **Feeding AI workflows** - Your coding agents call Deepr experts via MCP mid-task. They get living knowledge with citations, not hallucinations or stale training data.
- **Grounding always-on agents** - The autopilot platforms (Microsoft Autopilots, OpenAI Workspace Agents, Google Antigravity, AWS AgentCore) run agents for months, but their memory is shallow session state. An always-on agent has exactly the problem Deepr experts solve: it needs durable, verified, current domain knowledge with provenance, and a cheap way to re-sync with what changed since it last asked.
- **Composing into agent teams** - Experts expose structured outputs with handoff-ready artifacts. An upstream signal agent can feed findings into a Deepr expert, which produces research that a downstream strategy or proposal agent consumes. Deepr doesn't orchestrate the team - it plays a role on it.
- **Running continuously** - Scripts, cron jobs, CI pipelines. No browser, no manual clicking.
- **Auditing everything** - Every routing choice, source trust decision, and cost is captured as a structured decision record.
- **Avoiding lock-in** - Reports and experts are local files you own. If one provider goes down, auto-fallback routes to another. If a better tool comes along, your experts move with you.

**Where this is headed, honestly:** the ideas here - persistent experts, budget-bounded autonomy, routing across providers - may well get absorbed into the big platforms over time, and that's fine. The part that stays yours either way is the knowledge: experts are local files you own, portable across tools rather than tied to one vendor's memory. And as subscription plans and local models keep improving, the plan (see the [roadmap](ROADMAP.md) capacity release) is to route more of the work onto capacity you already pay for or own, so keeping a roster of experts current costs close to nothing extra. Deepr is one person's working answer to how those pieces should fit together - if part of it is useful to you, take it.

## Quick Start

**One-line install**

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"
```

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash
```

After the installer finishes, open a **new** terminal and run `deepr init` (guided setup: detects your keys, writes `.env`, sets a budget ceiling), then `deepr doctor` to verify.

**Updating:** run `deepr upgrade` (or `deepr upgrade --check` to just see if a newer version exists). Re-running the install one-liner above also updates an existing install. To remove it, re-run the one-liner with `-Uninstall` (Windows) or `-- --uninstall` (macOS/Linux).

---

**Deepr runs on Windows, macOS, and Linux** (Python 3.12+) and **works with whatever capacity you have** - it adapts and routes cheapest-first:

- **Local model** via [Ollama](https://ollama.com) - `$0` at the margin (expert creation/maintenance, `--local` flows). No API key needed.
- **Subscription CLIs** you already pay for (Codex, Claude Code, OpenCode, ...) - prepaid quota, opt-in per run.
- **Cloud API keys** (OpenAI, Gemini, Grok, Anthropic) - metered, the last resort.

You need **at least one** of these - not specifically an API key. `deepr init` detects what you have and `deepr capacity` shows exactly what Deepr will run on. Maybe you have a GPU and Ollama; maybe just a Claude subscription; maybe only an API key - Deepr works with what you've got and prefers the cheapest path.

### Install from source

If you are not using the one-line installer above, install from a clone. Pick
the path that matches what you want to do.

> **Where to run install:** `git clone` creates a `deepr/` directory with
> `pyproject.toml` at its root - `cd deepr` and run install commands from
> there. The package source lives under `src/deepr/` (src layout); you do not
> `cd` into it. (If you cloned into a folder you also named `deepr`, your shell
> path will read `deepr/deepr` - that outer level is just your clone location,
> not part of the project.)

**Just use `deepr` (recommended): a global command via pipx.**

```bash
# from the repo root (the deepr/ directory you cloned)
pipx install -e .
# or, once released:  pipx install deepr-research
```

`pipx` puts `deepr` on your PATH so it works in any terminal with no
activation, and `-e` tracks your local changes. If `pipx` is missing, run the
one-line installer above once - it installs pipx for you.

**Develop and run the test suite: a virtual environment.**

```bash
python -m venv .venv
# Windows (PowerShell):  .\.venv\Scripts\Activate.ps1
# Windows (cmd):         .venv\Scripts\activate.bat
# macOS / Linux:         source .venv/bin/activate
pip install -e ".[dev,full]"   # dev tooling + all extras
```

> With a venv, `deepr` only works while the venv is **activated**. If you see
> `deepr: not recognized` (Windows) or `command not found` (macOS/Linux),
> either activate the venv (commands above) or use the `pipx` install instead.

**Then, however you installed:**

```bash
deepr init                 # guided setup: detects keys, writes .env, sets a budget ceiling
deepr doctor               # verify connectivity
deepr research "Your question here"
```

Results saved to `data/reports/` as markdown with citations. **You only need one API key to start API-backed research**. Add more later and auto-mode routes to the best/cheapest model per task. Local expert maintenance can run without provider keys once Ollama is installed and a local model has been evaluated and admitted.

See [docs/QUICK_START.md](docs/QUICK_START.md) and [docs/INSTALL.md](docs/INSTALL.md) for guided setup, Windows notes, and extras.

## Features

### Research

Orchestrates deep research across providers. Auto mode routes by complexity - simple lookups at $0.01, deep analysis at $0.50-$2. Reports saved locally as markdown with citations.

```bash
deepr research "What bottlenecks could constrain NVIDIA Blackwell deployment at hyperscale?" --auto --explain
deepr research --auto --batch queries.txt --dry-run   # Preview routing, no cost
```

See [docs/FEATURES.md](docs/FEATURES.md) for the full command reference.

### Domain Experts

Deepr experts persist across sessions. They recognize knowledge gaps, research to fill them, and integrate findings permanently.

```bash
# Create an expert with autonomous learning
deepr expert make "AI Policy Expert" -d "EU AI Act enforcement timeline" --learn --budget 5

# Chat with it - slash commands, chat modes, visible reasoning, approval flows
deepr expert chat "AI Policy Expert" --budget 3

# Fill the highest-value knowledge gaps
deepr expert fill-gaps "Energy Transition Expert" --top 2 --budget 4

# Create from your own docs
deepr expert make "Platform Team Expert" --files docs/*.md

# Create a $0 local expert profile, then maintain it through Ollama
deepr expert make "UI Experience Expert" --local -d "UI/UX for agentic research tools"
deepr expert subscribe "UI Experience Expert" "UI/UX for agentic research tools"
deepr expert sync "UI Experience Expert" --local --fresh-context -y
deepr expert sync "UI Experience Expert" --local --deep-context -y
deepr expert loop-status "UI Experience Expert" --json
deepr expert export-okf "UI Experience Expert" ./okf/ui-experience
deepr expert absorb-okf "UI Experience Expert" ./okf/ui-experience --local --dry-run
```

Agentic chat supports 27 slash commands (`/ask`, `/research`, `/advise`, `/focus`, `/council`, `/plan`, `/compact`, and more), visible reasoning, human-in-the-loop approval for expensive operations, multi-expert council, and hierarchical task decomposition.

See [docs/EXPERTS.md](docs/EXPERTS.md) for the full expert system guide.

### MCP Integration - Experts as Consultable Roles

Your AI agents (Claude Code, Cursor, VS Code) can call Deepr experts via MCP - not as a generic "research tool" but as named domain roles. An agent working on a proposal can consult "AI Strategy Expert" for market context, then hand that context to a downstream agent for solution design. 29 MCP tools, resource subscriptions, prompt templates, budget propagation, and trace ID stitching across agent boundaries. See [mcp/README.md](mcp/README.md) for setup.

This matters most for the new generation of always-on agents: an agent that runs for months needs durable, verified, current domain knowledge with provenance - and a cheap way to re-sync ("what changed since I last consulted you?") instead of re-reading everything. Deepr experts are that knowledge layer; the host platform keeps the schedule, Deepr keeps the perspective.

For remote hosts, `deepr mcp serve --http` exposes the same server over
HTTP/SSE, and `deepr mcp smoke-http URL` validates a local or TLS-proxied
endpoint without provider calls. The hosted recipe includes a loopback
container variant under [deploy/mcp-http/](deploy/mcp-http/) for reverse-proxied
remote agents, an Azure Container Apps template under
[deploy/mcp-http/azure-container-apps/](deploy/mcp-http/azure-container-apps/),
`deepr mcp registration-manifest URL` for token-redacted remote host setup
packets, plus `deepr mcp audit list` and `summary` for reviewing scoped-key
remote-call audit records. Scoped-key budgets use audited spend plus
deterministic tool estimates before dispatch, and fail closed for metered tools
without an estimate. HTTP serve mode also has a global POST concurrency cap
configured by `--max-concurrency` or `DEEPR_MCP_HTTP_MAX_CONCURRENCY`.

### Web Dashboard

```bash
deepr web                # http://localhost:5000
```

12 pages: research submission, real-time progress, results library, expert chat with streaming and visible reasoning, cost analytics, model benchmarks, trace explorer, and more. Built with React, TypeScript, Tailwind CSS, and WebSocket push.

See [docs/FEATURES.md](docs/FEATURES.md) for the full page list.

### Benchmarking and Evals

Deepr includes a cost-safe benchmark workflow for keeping routing current as models change.

```bash
# Evaluate only new/missing model+tier combinations (default $1 preflight cap)
deepr eval new

# Compare local Ollama models with a local judge at $0
deepr eval local --model qwen2.5:14b --model qwen3-coder:30b --judge-model qwen2.5:14b

# Compare no context, fresh context, and deep context for one local model
deepr eval local-context --model qwen2.5:14b --judge-model qwen2.5:14b --save

# Run the built-in $0 prompt-boundary, MCP read-path, and trust-floor red-team gate
deepr eval red-team --json

# Save the $0 red-team report for release-to-release trend review
deepr eval red-team --save

# Or use an explicitly approved non-API CLI judge such as Grok
deepr eval local --model qwen2.5:14b --judge-cli grok --allow-cli-judge

# Estimate first, no spend
deepr eval new --dry-run --tier all

# Intentionally allow larger spend when needed
deepr eval new --max-estimated-cost 3
```

The dashboard reads `data/benchmarks/routing_preferences.json` and shows per-task best quality and best value picks. Local comparison artifacts can be saved under `data/benchmarks` for review before admitting a local model. Local context eval artifacts compare whether no context, fresh context, or deep context is the right envelope for a model before schedulers use that mode automatically. `deepr eval red-team` is a local `$0` verifier over built-in prompt-boundary, MCP handoff and loop-status read-path, tool-spoofing, and memory trust-floor probes; it tracks attack-success-rate, exits non-zero if a built-in attack succeeds, and can save `data/benchmarks/red_team_*.json` artifacts for release-to-release trend review. CLI judges are explicit opt-in because Deepr cannot prove whether a vendor CLI is using subscription quota or metered credentials.

### Setup and Capacity

`deepr init` detects API keys, writes `.env`, sets a budget ceiling, and can point your data at a synced folder. `deepr doctor` verifies connectivity and storage. `deepr capacity` shows local hardware, plan-based CLIs, and metered APIs. Automatic execution is local-first today: a scored, admitted Ollama model can run expert maintenance at `$0`. Plan-quota CLIs now execute too, via explicit opt-in: `deepr expert sync "Expert" --plan codex` (also `claude`, `opencode`, and more; `expert absorb --plan` as well) runs the whole job on a subscription you already pay for, behind a deterministic auth-mode + no-surprise-bills gate. `deepr capacity probe-plan codex` validates one works, and `deepr capacity fleet` shows every plan CLI at a glance - installed, auth mode, routable, and quota state (e.g. "codex exhausted, resets ~2h41m") in one read-only $0 view. To let scheduled maintenance route to a plan automatically, opt in with `deepr capacity admit-plan codex` (codex/claude/opencode; reset-aware, revocable) - the honest stand-in for a remaining-quota meter the vendors don't expose. *Automatic* routing to a plan CLI is still gated off (vendors don't expose remaining quota reliably) - that and live quota probes are on the roadmap.

Current capacity support:

| Capacity source | Deepr status today | Best use |
|---|---|---|
| Local Ollama | Works for local expert profiles, `sync`/`absorb --local`, `sync --local --fresh-context`, `sync --local --deep-context`, `eval local`, `eval local-context`, and scored local admission | High-volume `$0` expert maintenance and validation loops |
| Provider APIs | Works for full research when you provide keys and a budget ceiling | Deep research, high-quality synthesis, fallback |
| Plan CLIs: Codex, Claude Code, OpenCode (auto-routable); Kiro, Grok Build, Antigravity, GitHub Copilot (explicit only) | Execute via `expert sync --plan <id>` behind an auth-mode + no-surprise-bills gate; auto-routing still gated pending live quota probes | $0-at-margin expert maintenance on subscriptions you already pay for |
| Explicit CLI judge | Opt-in only for local evals with `--allow-cli-judge` | Human-approved comparison signal, not automatic routing |

```bash
deepr init --yes --budget 5 --data-dir ~/OneDrive/deepr   # scripted setup, portable data
deepr doctor                                               # connectivity + storage health
deepr capacity --probe                                     # what's available, incl. local models
deepr capacity next --task-class sync                      # ranked next actions for cheap capacity
deepr capacity next --task-class sync --context-mode fresh --scheduled
deepr expert sync "Platform Team Expert" --scheduled --fresh-context -y
deepr expert route-gaps "Platform Team Expert" --execute --scheduled --json
deepr expert reflect "Platform Team Expert" <job_id> --execute-followups --scheduled --json
deepr expert health-check "Platform Team Expert" --scheduled --json
```

Local-model execution runs quality-tolerant expert maintenance at $0 against a local Ollama endpoint. This is the usable capacity waterfall rung today:

```bash
deepr expert make "Platform Team Expert" --local -d "Platform engineering knowledge"
deepr expert absorb "Platform Team Expert" report.md --local
deepr expert sync "Platform Team Expert" --local
deepr expert sync "Platform Team Expert" --local --fresh-context
deepr expert sync "Platform Team Expert" --local --deep-context
deepr expert sync "Platform Team Expert" --scheduled --fresh-context -y
deepr eval local --max-models 2 --max-prompts 2 --save
deepr eval local-context --model qwen2.5:14b --judge-model qwen2.5:14b --save
deepr capacity admit --from-eval latest --task-class sync --yes
deepr capacity next --task-class sync
deepr capacity next --task-class sync --context-mode deep --expert "Platform Team Expert" --scheduled
deepr expert reflect "Platform Team Expert" <job_id> --execute-followups --scheduled --json
deepr expert health-check "Platform Team Expert" --archive-stale --scheduled --json
```

Local models do not browse on their own. `--fresh-context` builds a small
free-only retrieval pack before the local model call. `--deep-context` does a
bounded multi-query retrieval pass for topics that need more coverage. Both can
fetch explicit URLs, can use a configured self-hosted SearXNG endpoint
(`DEEPR_SEARXNG_URL`), and otherwise fall back to DuckDuckGo when the optional
package is installed. They never use Brave/Tavily API-key search. If no fresh
sources are retrieved, sync records no changes instead of absorbing the local
model's uncertainty as expert beliefs. Use `deepr eval local-context` to
measure that context envelope before relying on it in automation. Context-bearing
sync runs also write a bounded source-pack artifact into the expert knowledge
directory, and absorption is blocked if that source trail cannot be persisted.
See
[docs/FEATURES.md#setup-and-capacity](docs/FEATURES.md#setup-and-capacity)
for commands and [docs/design/capacity-waterfall.md](docs/design/capacity-waterfall.md)
for the full routing model.

Saved local eval artifacts can now be admitted directly. Use `--from-eval latest`
to select the newest `data/benchmarks/local_compare_*.json` artifact, or pass a
specific artifact path when you want to admit a named model from an older run.
Automatic local routing requires a measured admission score that clears the
quality floor; scoreless manual admissions stay visible but do not silently take
over the automatic path. `--local` remains the explicit override.

The QOL goal is one command that explains the cheapest safe route for the job in
front of you. `deepr capacity next` does not run work, but it tells you whether
local is blocked by setup, missing eval evidence, expired admission, or quality
floor. It also accepts concrete job context such as `--context-mode fresh` /
`deep`, `--expert`, `--report-id`, and `--scheduled`, so recurring jobs can see
when to use fresh/deep local context, wait for cheap capacity, or deliberately
fall back to metered API behind a budget gate. `deepr expert sync --scheduled`
now consumes the same guidance: a due scheduled sync waits with structured next
actions when owned/prepaid capacity is blocked, unless the operator explicitly
chooses `--api`. `deepr expert route-gaps --execute --scheduled` applies the
same scheduler default to gap-fill sweeps: it returns pending routes and a wait
state instead of starting metered research until a cheap gap-fill backend exists
or the operator reruns the command without `--scheduled`. `deepr expert reflect
--scheduled` waits before the reflection evaluator runs, so recurring
reflection follow-up jobs never make a metered evaluation call or start
follow-up research unless the operator removes `--scheduled`. `deepr expert
health-check --scheduled` adds a scheduler action plan: paid recommendations
wait for capacity, confirm-gated local writes wait for confirmation, and
`--archive-stale --scheduled` will not mutate unless `--yes` is explicit.
These scheduled wait and action-plan payloads now include durable `loop_run`
records plus published `schema_version` and `kind` values for sync capacity
gates, scheduled gap-fill waits, scheduled reflection waits, health-check
action plans, and archive confirmations. `deepr expert loop-status NAME --json`
can show the latest blocked or waiting maintenance work without re-running it.
Host agents can read the same state through `deepr_expert_loop_status`.
Successful `deepr expert sync` runs, non-dry `deepr expert route-gaps
--execute` runs, and `deepr expert reflect` runs also record loop snapshots.
`deepr expert health-check` and confirmed `--archive-stale` runs now do the
same, with spend, capacity source, verifier outcome, accepted-change counts
where applicable, and typed stop actions for failures, deferred specialist
routes, weak verifier results, human gates, no corrective work, or exhausted
budgets. The dashboard API now
exposes `/api/experts/{name}/loop-status`, a read-only rollup over the same
records with latest run, last sync result, waiting scheduled action, failure,
capacity source, spend, acceptance, verifier failure metrics, and `expert_state`
telemetry for freshness, gap velocity, and contested/open claims. The dashboard
API also exposes `/api/experts/{name}/handoff`, and MCP exposes
`deepr_expert_handoff`, a `$0` versioned `deepr-expert-handoff-v1` payload with
profile summary, manifest counts, bounded claims/gaps, loop status, OKF
interchange hints, and an additive compatibility contract. MCP handoff and
loop-status reads validate their published envelope before returning to a host
agent and fail closed on schema drift. Terminal loop
records now require status-compatible typed stop reasons before they can be
stored. The same API includes `admission_contracts` for the four autonomy gates:
repeat demand, automated verification, explicit budget/capacity, and
failure-diagnosis state. `deepr expert export-okf NAME PATH` now writes a
regenerated OKF Markdown bundle from the belief/event/edge store, gaps, and
contested claims at `$0`; `deepr expert absorb-okf NAME PATH` parses OKF
concepts as source text and routes them through the verified absorb gates. The
structured store remains canonical. Published contracts for expert handoff,
loop status, the OKF profile mapping, hosted MCP audit/registration payloads,
A2A task/result envelopes, capacity guidance, sync gates, scheduled maintenance
payloads, and the shared CLI result envelope live under `docs/schemas/`.

### Evidence and Calibration

Three evals make trust measurable instead of asserted. `deepr eval continuity` scores an expert's staleness honesty, abstention, contradiction-surfacing, and what-changed exactness from stored state at $0. `deepr eval calibrate` answers "does extraction confidence track actual grounding?" with a reliability curve, expected calibration error, and a Platt-derived threshold - `--from` grades existing pairs at $0, `--corpus` runs the paid extraction and pre-grade. `deepr eval red-team` tracks local attack-success-rate for prompt-boundary, MCP read-path, tool-spoofing, and trust-floor probes at $0, and `--save` writes a trend artifact.

```bash
deepr eval continuity "AI Policy Expert"
deepr eval calibrate --from data/calibration/graded.jsonl   # $0
deepr eval calibrate --corpus tests/data/calibration --max-cost 3 --yes
deepr eval red-team --json                                # $0
deepr eval red-team --save                                # $0 artifact
```

See [docs/CALIBRATION.md](docs/CALIBRATION.md) for the first measured curve and [docs/design/checks-deterministic-vs-agentic.md](docs/design/checks-deterministic-vs-agentic.md) for what belongs in deterministic code versus model judgment.

### Multi-Provider Support

Start with one API key. Add more to unlock smarter routing. OpenAI, Gemini, Grok, Anthropic, and Azure AI Foundry all supported. Auto-fallback on failures means no single provider outage stops your work.

See [docs/MODELS.md](docs/MODELS.md) for provider comparison and pricing.

## Design

Three patterns run through Deepr:

- **Budgeted autonomy** - Every autonomous job runs under a contract: max spend, stop conditions, acceptable uncertainty, required citations, audit trail.
- **Decision records as artifacts** - The system captures *why* it chose a model, trusted a source, stopped searching, or flagged a knowledge gap. These feed back into routing, expert learning, and cost optimization.
- **Experts as roles, not tools** - Each expert is a persistent, named role with its own knowledge state, beliefs, and gaps. You don't "run Deepr" - you consult a domain expert. This makes experts composable: they can receive structured input from upstream agents, produce handoff-ready artifacts for downstream agents, and participate in multi-agent workflows without being the orchestrator. Think of each as a tailored second brain (note the plural): instead of one generic vault you organize by hand, you get a roster of domain-scoped knowledge bases that stay current on their topics, verify what they ingest, and deploy as an agent team.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.

## Cost Controls

Research costs real money. Deepr has multi-layer budget protection: per-operation limits, daily and monthly caps, pre-submission estimates, pause/resume at boundaries, anomaly detection, and a canonical append-only cost ledger (`data/costs/cost_ledger.jsonl`).

```bash
deepr budget set 5                                  # Set $5 limit
deepr costs show                                    # See what you've spent
deepr costs doctor                                 # Validate tracker health + drift (no API spend)
deepr research --auto --batch queries.txt --dry-run # Preview costs before executing
```

Set `DEEPR_COST_TRACKING_STRICT=1` to fail fast when cost events cannot be persisted to the canonical ledger.

**Gemini large-context pricing note:** Gemini 3.1 Pro (the default Gemini pro model) charges 2x for prompts over 200K tokens ($4/$18 per 1M input/output vs $2/$12 under 200K). Most queries stay well under that threshold, but large document analysis (`--files` with big PDFs, 500+ page corpora) can cost ~2x more than shorter prompts - e.g., a 250K-token document analysis runs ~$1.18 vs ~$0.62 for a sub-200K prompt. Use `--dry-run` to preview costs before executing, and `--budget` to cap spend.

See [docs/FEATURES.md](docs/FEATURES.md) for the full cost command reference.

## Startup Banner

Deepr shows an animated startup banner by default in interactive terminals, with automatic fallbacks for CI, screen readers, no-color terminals, and low-capability terminals.

```bash
deepr interactive --banner     # Force-show banner once
deepr interactive --no-banner  # Skip banner
```

Optional env controls:
- `DEEPR_BANNER_MODE=off|static|light|full`
- `DEEPR_BANNER_DURATION=<seconds>` (applies to animated modes)
- `DEEPR_ANIMATIONS=off|light|full`
- `DEEPR_BRANDING=off|on|auto`

## What's Stable vs Experimental

**Production-ready:** Core research commands, cost controls, expert creation/chat, context discovery, auto mode routing, all providers, local SQLite storage, guided setup (`deepr init`/`deepr doctor`), and a portable data directory (one `DEEPR_DATA_DIR` relocates experts and research, so they follow you across machines via OneDrive/Dropbox/etc.). 6100+ tests (Python 3.12-3.14).

**Experimental:** Web dashboard, agentic expert chat (slash commands, modes, reasoning, approval, council, task planning), expert skills, MCP server, HTTP serve, scoped-key CLIs, HTTP smoke validation, per-key budget and rate guards, and remote-call audit primitives, auto-fallback circuit breakers, cloud deployment templates including hosted MCP Azure, AWS, and GCP variants, capacity visibility, local-model execution, capacity next actions (`deepr capacity next`), quota eligibility gates (`deepr capacity`, `--local` on expert sync/absorb), loop status records and API rollups (`deepr expert loop-status`, `/api/experts/{name}/loop-status`), versioned expert handoff (`/api/experts/{name}/handoff`, `deepr_expert_handoff`), OKF export/import (`deepr expert export-okf`, `deepr expert absorb-okf`), and the evidence layer (`deepr eval continuity`, `deepr eval calibrate`, `deepr eval red-team`).

See [docs/SUPPORTED_SURFACE.md](docs/SUPPORTED_SURFACE.md) for the supported
contract and [ROADMAP.md](ROADMAP.md) for detailed status.

## Documentation

| Guide | Description |
|-------|-------------|
| [Quick Start](docs/QUICK_START.md) | Installation and first research job |
| [Features](docs/FEATURES.md) | Complete command reference |
| [Experts](docs/EXPERTS.md) | Domain expert system |
| [Models](docs/MODELS.md) | Provider comparison and model selection |
| [Architecture](docs/ARCHITECTURE.md) | Technical architecture, security, budget protection |
| [MCP Integration](mcp/README.md) | MCP server setup and agent integration |
| [Integrations](docs/INTEGRATIONS.md) | First-party tool integrations (recon, distillr, primr) |
| [Agentic Vision](docs/AGENTIC_VISION.md) | Agentic architecture, A2A, reflection, campaigns |
| [Supported Surface](docs/SUPPORTED_SURFACE.md) | Stable, experimental, planned, and export guarantees |
| [Deployment](deploy/README.md) | Cloud deployment (AWS, Azure, GCP) |
| [Changelog](docs/CHANGELOG.md) | Release history |
| [Roadmap](ROADMAP.md) | Development priorities and future plans |

> **Note:** Model pricing changes frequently. The [model registry](src/deepr/providers/registry.py) is the source of truth for current pricing.

## Requirements

- Python 3.12+ (tested on 3.12-3.14)
- For full API-backed research, **one API key** from any supported provider:
  - [OpenAI](https://platform.openai.com/api-keys) - deep research + GPT models
  - [Gemini](https://aistudio.google.com/app/apikey) - cost-effective, large context
  - [xAI Grok](https://console.x.ai/) - Grok 4.3 flagship, Grok 4.20 research/freshness tiers, real-time web search
  - [Anthropic](https://console.anthropic.com/settings/keys) - complex reasoning
- For $0 local expert maintenance, optional [Ollama](https://ollama.com/) plus a local model. This supports `deepr capacity`, `deepr eval local` with a local judge, `deepr eval local-context`, `expert make --local`, explicit `expert sync`/`absorb --local`, and automatic local maintenance after scored admission.
- Plan-quota CLIs are optional. When installed, they execute via explicit `deepr expert sync --plan <id>` (Codex, Claude Code, OpenCode, Kiro, Grok Build, Antigravity, GitHub Copilot) behind an auth-mode + no-surprise-bills gate; `deepr capacity probe-plan <id>` validates one. *Automatic* routing to them is still gated off pending live quota probes (vendors don't expose remaining quota reliably).
- Optional: More API keys for smarter auto-routing and fallback
- Optional: Node.js 18+ for web dashboard development

## Contributing

Contributions welcome. Run `ruff check . && ruff format .` and `pytest` before submitting. See [ROADMAP.md](ROADMAP.md) for priorities.

## Security

6100+ tests (Python 3.12-3.14). Pre-commit hooks run ruff; CI also runs mypy (kernel is `--strict`) and pip-audit. Input validation, prompt-injection sanitization for user prompts and untrusted source/tool spans, including retrieved snippets, reports, document previews, campaign context, and team outputs. SSRF protection, API key redaction, and budget enforcement are covered in [Architecture](docs/ARCHITECTURE.md).

**Report vulnerabilities:** [nick@pueo.io](mailto:nick@pueo.io) (not via public issues)

## License

[Apache 2.0](LICENSE). Free to use, build on, fork, and share. For commercial or
enterprise use, contact Nick Seal (nick@pueo.io).

---

Deepr is an independent project by [Nick Seal](mailto:nick@pueo.io), maintained in spare time. It started as a weekend experiment with deep research APIs and grew into an exploration of how autonomous research systems should work - budgets, reliability, memory, auditability. The patterns here are transferable beyond research, but at minimum it's useful tooling for people who need research that goes beyond a chat window.

No SLA or commercial backing. If you find it useful, great. If you hit a rough edge, [open an issue](https://github.com/blisspixel/deepr/issues) or [start a discussion](https://github.com/blisspixel/deepr/discussions).

[GitHub](https://github.com/blisspixel/deepr) · [Issues](https://github.com/blisspixel/deepr/issues) · [Discussions](https://github.com/blisspixel/deepr/discussions)
