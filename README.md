# Deepr

[![CI](https://github.com/blisspixel/deepr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/deepr/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.48.0-blue)](https://github.com/blisspixel/deepr/releases/tag/v2.48.0)

**Persistent domain experts built from bounded, auditable research.**

Deepr turns research into durable beliefs, gaps, contradictions, confidence,
citations, provenance, and outcomes. It prefers owned local models, then proven
subscription quota, with no automatic fallback to a paid API.

<p align="center">
  <img src="assets/cli-demo.png" width="92%" alt="Bounded attended API run: one $2 total grant, exact ledger settlement, expert improvement, and immediate revocation" />
</p>

<p align="center">
  <img src="assets/expert-hub.png" width="70%" alt="Live roster of 49 experts with the improved cost expert at 173 findings and API grant exposure of $0.01 against one $2 total limit" />
</p>

## Capacity

| Class | Current posture |
| --- | --- |
| Local Ollama | Preferred for expert setup, maintenance, evaluation, and consultation after endpoint ownership is proven. Records $0 and does not consume an API grant. |
| Prepaid plan quota | Runs only when authentication, tool confinement, remaining quota, and disabled paid overage are proven. Claude Code is the current executable adapter. Successful work records $0 and does not consume an API grant. |
| Metered API | No automatic fallback. Attended `expert absorb --api` can run only under a typed, expiring grant with a hard $2 total maximum. Other metered surfaces remain gated. |

A grant is one total drawdown, not $2 per call. Every settled API dollar and
every active paid hold consumes the same grant across provider calls and time
windows. Each call still needs its own finite reservation and explicit consent.
MCP, schedules, loops, and automatic fallback cannot use attended authority.

```bash
deepr budget allow --amount 2.00 --minutes 60 --provider openai
deepr expert absorb "My Domain Expert" --file report.md --api --budget 0.30
deepr costs show
deepr costs doctor
deepr budget revoke
```

See [Capacity and Cost](docs/CAPACITY.md) for billing reconciliation and the
complete no-surprise-spend contract.

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
deepr expert make "My Domain Expert" --local -d "The decisions this expert supports"
deepr expert consult "What should we decide next?" --expert "My Domain Expert"
```

See [Quick Start](docs/QUICK_START.md), [Supported Surface](docs/SUPPORTED_SURFACE.md),
and the [MCP Agent Guide](docs/MCP_AGENT_TEST_GUIDE.md) for workflows across the
current 36 MCP tools. The MCP server implements the final `2026-07-28`
protocol revision (stateless per-request negotiation, `server/discover`,
`subscriptions/listen`, Streamable HTTP header and Origin validation) while
still serving legacy `initialize`-era clients on both transports. Operators can
prove the offline host-interop posture with `deepr mcp conformance` (`$0`, no
network, no model).

## Documentation

- [Approach contract](docs/APPROACH.md) - what the method claims, refuses, and leaves experimental
- [Supported Surface](docs/SUPPORTED_SURFACE.md) - what currently runs
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
