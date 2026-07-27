# Deepr

[![CI](https://github.com/blisspixel/deepr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/deepr/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.38.2-blue)](https://github.com/blisspixel/deepr/releases/tag/v2.38.2)

**Persistent domain experts built from bounded, auditable research.**

Deepr uses local models, proven subscription quota, and explicitly authorized
paid APIs to build experts with beliefs, gaps, contradictions, confidence,
citations, and provenance. Use it when research must stay useful, current, and
inside hard cost limits.

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

A budget is a ceiling, not permission to spend. Paid dispatch requires explicit
consent, trusted pricing, finite bounds, a durable reservation, and append-only
settlement. Spend and concurrent holds are checked together. Unknown money
state fails closed.

```bash
deepr budget set 10
deepr budget status
deepr budget freeze --reason "operator stop"
deepr costs doctor
```

`budget set 0` freezes paid work. Paid composed fan-out stays disabled until one
durable parent reservation covers every child, retry, verifier, tool, and
synthesis call. Details: [Capacity and Cost](docs/CAPACITY.md) and
[spend authority design](docs/design/no-surprise-spend-authority.md).

## Install

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"
```

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash
```

The installers use the latest verified GitHub Release wheel in an isolated pipx
environment. PyPI publication is not enabled. See
[Installation](docs/INSTALL.md) for source and platform-specific setup.

## Quick start

```bash
deepr init
deepr doctor --skip-connectivity
deepr capacity
deepr expert blueprint "My Domain Expert" --template --output expert-blueprint.json
deepr expert blueprint "My Domain Expert" --from-file expert-blueprint.json --apply --attested-by operator
deepr expert make "My Domain Expert" --local -d "The decisions this expert supports"
deepr expert consult "What should we decide next?" --expert "My Domain Expert" --local
```

Preview paid work without dispatching it:

```bash
deepr research "What changed in this field this month?" \
  --provider openai \
  --model o4-mini-deep-research \
  --preview
```

Preview and dispatch share the same hard request envelope. A provider key,
positive budget, and explicit confirmation are still required. See
[Quick Start](docs/QUICK_START.md) and [Experts](docs/EXPERTS.md).

## What works now

| Area | Current contract |
| --- | --- |
| Bounded research | Single provider jobs work when model, token, tool, and payload pricing can be bounded completely. |
| Persistent experts | Blueprint, local creation, maintenance, consultation, beliefs, gaps, outcomes, handoffs, and derived views are available. |
| Local investigations | Experimental multi-expert research, checking, synthesis, and staged learning run at `$0` provider cost. |
| Plan quota | Claude Code is executable only after a live proof that paid extra usage is disabled. Other adapters remain visible with typed refusal reasons. |
| MCP and A2A | Read, consult, handoff, validation, and scoped transport surfaces are available. Deepr exposes 36 MCP tools. |
| Paid multi-call work | Batch, campaign, team, and other composed paid graphs remain gated pending one aggregate parent budget. |

The authoritative boundary between shipped, experimental, visible, and planned
behavior is [Supported Surface](docs/SUPPORTED_SURFACE.md).

## Documentation

| Guide | Purpose |
| --- | --- |
| [Installation](docs/INSTALL.md) | Supported installation and upgrade paths |
| [Quick Start](docs/QUICK_START.md) | First research and expert workflow |
| [Supported Surface](docs/SUPPORTED_SURFACE.md) | Stable, experimental, visible, planned, and gated behavior |
| [Capacity and Cost](docs/CAPACITY.md) | Local, subscription, metered, scheduler, and budget contracts |
| [Experts](docs/EXPERTS.md) | Persistent expert lifecycle and commands |
| [Models](docs/MODELS.md) | Provider models, pricing posture, and selection |
| [Architecture](docs/ARCHITECTURE.md) | Components, data flow, and design boundaries |
| [Threat Model](docs/security/THREAT_MODEL.md) | Security boundaries and mitigations |
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

Do not run bare `pytest`: integration tests can contact real providers. See
[Contributing](CONTRIBUTING.md) for every required gate.

## License

[Apache 2.0](LICENSE)

[GitHub](https://github.com/blisspixel/deepr) |
[Issues](https://github.com/blisspixel/deepr/issues) |
[Discussions](https://github.com/blisspixel/deepr/discussions)
