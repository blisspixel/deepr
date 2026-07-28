# Deepr

[![CI](https://github.com/blisspixel/deepr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/deepr/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.39.0-blue)](https://github.com/blisspixel/deepr/releases/tag/v2.39.0)

**Persistent domain experts built from bounded, auditable research.**

Deepr turns research into durable beliefs, gaps, contradictions, confidence,
citations, provenance, and outcomes. It prefers owned local models, then proven
subscription quota, with no automatic fallback to a paid API.

<p align="center">
  <img src="assets/dashboard.png" width="49%" alt="Dashboard with cost trends, job status, and activity" />
  <img src="assets/expert-hub.png" width="49%" alt="Persistent expert hub with maintained domain knowledge" />
</p>

## Capacity

| Class | Current posture |
| --- | --- |
| Local Ollama | Preferred for expert setup, maintenance, evaluation, and consultation after endpoint ownership is proven. |
| Prepaid plan quota | Runs only when authentication, tool confinement, remaining quota, and disabled paid overage are proven. Claude Code is the current executable adapter. |
| Metered API | No automatic fallback. Production dispatch is currently blocked pending a provider-authenticated account-control adapter. |

A budget is a ceiling, never permission to spend. Metered work requires a
finite request envelope, durable reservation, immediate pre-dispatch recheck,
append-only settlement, and fresh account-control evidence bound to the exact
provider account, scope, and credential. A local assertion cannot create that
authority. Unknown or unreadable money state fails closed.

```bash
deepr budget set 10
deepr budget status
deepr budget freeze --reason "operator stop"
deepr costs show
deepr costs doctor
deepr costs reconcile-billing provider-statement.json
```

Billing reconciliation is offline and write-free by default. Paid fan-out stays
disabled until one durable parent reservation covers every child, retry,
verifier, tool, and synthesis call.

## Install

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"
```

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash
```

Installers use the latest verified GitHub Release wheel in an isolated pipx
environment. PyPI publication is not enabled.

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

Previewing a bounded API request makes no provider call:

```bash
deepr research "What changed in this field this month?" \
  --provider openai --model o4-mini-deep-research --preview
```

See [Quick Start](docs/QUICK_START.md), [Supported Surface](docs/SUPPORTED_SURFACE.md),
and [Capacity and Cost](docs/CAPACITY.md) for the exact shipped boundaries and
current 36 MCP tools.

## Documentation

- [Experts](docs/EXPERTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Models](docs/MODELS.md)
- [Threat Model](docs/security/THREAT_MODEL.md)
- [Roadmap](ROADMAP.md)
- [Changelog](docs/CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

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

Do not run bare `pytest`: integration tests can contact real providers. The
blocking unit suite requires at least 80 percent branch coverage.

## License

[Apache 2.0](LICENSE)
