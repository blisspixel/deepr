# Deepr

[![CI](https://github.com/blisspixel/deepr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/deepr/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.38.0-blue)](https://github.com/blisspixel/deepr/releases/tag/v2.38.0)

**Domain experts that remember, not another chat window.**

Deepr runs bounded research across local models, proven subscription quota,
and explicitly authorized paid APIs. It turns useful results into persistent
experts with beliefs, gaps, contradictions, confidence, citations, provenance,
and portable local artifacts.

Use Deepr when research must be reusable, auditable, current, and governed by
hard cost limits. For a casual one-off question, a normal chat product is
simpler.

<p align="center">
  <img src="assets/dashboard.png" width="49%" alt="Dashboard with cost trends, job status, and activity" />
  <img src="assets/expert-hub.png" width="49%" alt="Persistent expert hub with maintained domain knowledge" />
</p>

## Capacity and cost

| Capacity | Intended use | Safety posture |
| --- | --- | --- |
| Local Ollama | Routine expert setup, maintenance, evaluation, and consultation | Preferred owned-capacity path. Endpoint ownership must be proven. |
| Prepaid plan quota | Selected expert workflows using an existing subscription | Runs only when authentication, tool confinement, and paid-overage posture are proven safe. |
| Metered API | Premium bounded research and synthesis | Explicit opt-in only. Never selected as automatic fallback. |

A budget is a ceiling, not permission to spend. Supported paid dispatch
requires explicit consent, trusted pricing, finite input and output bounds, a
durable reservation, and append-only settlement. Settled spend and concurrent
holds are checked together across per-job, day, week, and month limits.
Unknown or unreadable money state fails closed.

```bash
deepr budget set 10
deepr budget status
deepr budget freeze --reason "operator stop"
deepr costs doctor
```

`budget set 0` is a persistent paid freeze. Paid composed fan-out remains
disabled until one durable parent reservation can cover every child, retry,
verifier, tool, and synthesis call. See [Capacity and Cost](docs/CAPACITY.md)
and the [spend authority design](docs/design/no-surprise-spend-authority.md).

## Install

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"
```

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash
```

The installers fetch the latest verified wheel from GitHub Releases and use an
isolated pipx environment. They stop without changing an existing installation
if a supported release asset is unavailable. PyPI publication is not enabled.

For platform details and source installation, see the
[Installation Guide](docs/INSTALL.md).

## Quick start

Inspect capacity before running work:

```bash
deepr init
deepr doctor --skip-connectivity
deepr capacity
```

Create and consult a local expert:

```bash
deepr expert blueprint "My Domain Expert" --template --output expert-blueprint.json
# Review and edit the blueprint before recording an attestation.
deepr expert blueprint "My Domain Expert" --from-file expert-blueprint.json --apply --attested-by operator
deepr expert make "My Domain Expert" --local -d "The decisions this expert supports"
deepr expert subscribe "My Domain Expert" "The first topic to keep current"
deepr expert sync "My Domain Expert" --local --fresh-context -y
deepr expert consult "What should we decide next?" --expert "My Domain Expert" --local
```

Preview one bounded paid research request without dispatching it:

```bash
deepr research "What changed in this field this month?" \
  --provider openai \
  --model o4-mini-deep-research \
  --preview
```

Preview and dispatch use the same hard request envelope. A provider key,
positive budget, and explicit confirmation are still required for a paid call.

See [Quick Start](docs/QUICK_START.md), [Features](docs/FEATURES.md), and
[Experts](docs/EXPERTS.md) for complete workflows.

## What works now

| Area | Current contract |
| --- | --- |
| Bounded research | Single provider jobs work when model, token, tool, and payload pricing can be bounded completely. |
| Persistent experts | Blueprint, local creation, maintenance, consultation, beliefs, gaps, outcomes, handoffs, and derived views are available. |
| Local investigations | Experimental multi-expert research, bounded discussion, checking, synthesis, and staged learning run at `$0` provider cost. |
| Plan quota | Claude Code is executable only after a live proof that paid extra usage is disabled. Other adapters remain visible with typed refusal reasons. |
| MCP and A2A | Read, consult, handoff, validation, and scoped transport surfaces are available. Deepr exposes 36 MCP tools. |
| Paid multi-call work | Batch, campaign, team, and other composed paid graphs remain gated pending one aggregate parent budget. |

The exact stable, experimental, visible, and planned boundaries live in
[Supported Surface](docs/SUPPORTED_SURFACE.md). Roadmap items must not be
marketed as shipped behavior.

## How experts differ from fact lists

A maintained expert tracks change, contradiction, uncertainty, gaps, and the
decisions its knowledge supports. Factual beliefs require evidence and
provenance. Hypotheses, concepts, theories, and stances may remain useful, but
they stay explicitly non-factual with uncertainty and disconfirming tests.
Generated reports and digests are derived views of structured state, not the
authority themselves.

For councils, learning lanes, evaluation, and expert-value measurement, see
[Experts](docs/EXPERTS.md) and the
[Three Expert Council workflow](docs/THREE_EXPERT_COUNCIL.md).

## Privacy and ownership

Deepr has no product telemetry, analytics account, or automatic phone-home.
Network calls occur only for operator-invoked provider work, configured search
or MCP services, the explicit release update check, and an optional
operator-owned heartbeat endpoint.

Reports, experts, beliefs, ledgers, and audit records remain local JSON, JSONL,
and Markdown under the configured data root. Published schemas and OKF exports
keep that state portable.

See the [Threat Model](docs/security/THREAT_MODEL.md) for precise trust
boundaries and exceptions.

## Documentation

| Guide | Purpose |
| --- | --- |
| [Installation](docs/INSTALL.md) | Supported installation and upgrade paths |
| [Quick Start](docs/QUICK_START.md) | First research and expert workflow |
| [Supported Surface](docs/SUPPORTED_SURFACE.md) | Stable, experimental, visible, planned, and gated behavior |
| [Capacity and Cost](docs/CAPACITY.md) | Local, subscription, metered, scheduler, and budget contracts |
| [Experts](docs/EXPERTS.md) | Persistent expert lifecycle and commands |
| [Features](docs/FEATURES.md) | Full feature and command reference |
| [Models](docs/MODELS.md) | Provider models, pricing posture, and selection |
| [MCP Agent Guide](docs/MCP_AGENT_TEST_GUIDE.md) | Host integration and validation |
| [Architecture](docs/ARCHITECTURE.md) | Components, data flow, and design boundaries |
| [Threat Model](docs/security/THREAT_MODEL.md) | Security boundaries and mitigations |
| [Agentic Balance](docs/plans/AGENTIC_BALANCE.md) | Deterministic control versus model judgment |
| [Changelog](docs/CHANGELOG.md) | Released behavior and migration notes |
| [Roadmap](ROADMAP.md) | Active priorities and planned work |
| [Contributing](CONTRIBUTING.md) | Development workflow and Definition of Done |

## Development

```bash
uv pip install -e ".[dev,full]"
pytest tests/unit/ --ignore=tests/data -q
ruff check src/deepr/
ruff format --check src/deepr/
python scripts/check_file_sizes.py
python scripts/check_ratchets.py
python scripts/check_paid_api_boundaries.py
```

Do not run bare `pytest`: integration tests can contact real providers. CI
runs 8,000+ tests (Python 3.12-3.14) with an 80 percent branch coverage gate,
strict type islands, security checks, frontend validation, and package
verification.

## License

[Apache 2.0](LICENSE)

[GitHub](https://github.com/blisspixel/deepr) |
[Issues](https://github.com/blisspixel/deepr/issues) |
[Discussions](https://github.com/blisspixel/deepr/discussions)
