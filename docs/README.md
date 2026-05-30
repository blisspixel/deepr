# Deepr Documentation

> **Note**: Model information current as of March 2026. AI evolves rapidly - verify at provider websites.

## Getting Started

1. **[INSTALL.md](INSTALL.md)** - Installation and setup
2. **[QUICK_START.md](QUICK_START.md)** - Your first research job
3. **[EXAMPLES.md](EXAMPLES.md)** - Real-world usage examples

## Core Documentation

- **[FEATURES.md](FEATURES.md)** - Complete feature reference
- **[EXPERTS.md](EXPERTS.md)** - Domain expert system guide
- **[MODELS.md](MODELS.md)** - Model selection and provider guide

## Technical

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture and security
- **[BENCHMARKS.md](BENCHMARKS.md)** - Model benchmarks, scoring methodology, and results
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

## Project

- **[../ROADMAP.md](../ROADMAP.md)** - Development priorities and status
- **[INTEGRATIONS.md](INTEGRATIONS.md)** - First-party tool integrations (recon, distillr, primr)
- **[AGENTIC_VISION.md](AGENTIC_VISION.md)** - Agentic architecture, A2A protocol, reflection, campaigns
- **[VISION.md](VISION.md)** - Future direction (aspirational)

## Source of Truth (avoid drift)

Volatile facts live in exactly one canonical place. Other docs link to it or
describe it qualitatively rather than restating the number, so a single update
keeps everything correct. `scripts/check_docs_consistency.py` (run in CI)
derives each number from the code and fails the build if a doc overstates it.

| Fact | Canonical home | Derived from |
|------|----------------|--------------|
| Model names / pricing | `deepr/providers/registry.py` | the registry itself |
| Test count, coverage gate | [../ROADMAP.md](../ROADMAP.md) "Current Status" | `tests/`, `pyproject.toml` `fail_under` |
| MCP tool count + breakdown | [../mcp/README.md](../mcp/README.md) | `deepr/mcp/server.py` `tool_dispatch` |
| Web page count | [FEATURES.md](FEATURES.md) | `deepr/web/frontend` routes |
| Skills, slash commands | [EXPERTS.md](EXPERTS.md) | `experts/commands.py`, skills dir |

The front-door [../README.md](../README.md) may quote headline counts; those
references are covered by the CI check so they cannot go stale. Secondary docs
(SECURITY, VISION, AGENTIC_VISION) should stay qualitative and link here.

## Reference

- **[reference/](reference/)** - Technical reference docs

## Archive

- **[archive/](archive/)** - Historical docs, completed work, old specifications ([policy](ARCHIVE.md))

---

**Keeping Current**: When new AI models are released, update the model registry at `deepr/providers/registry.py`. Never hardcode model names elsewhere. For other volatile facts (counts, thresholds), see the "Source of Truth" table above and run `python scripts/check_docs_consistency.py` to verify docs match the code.
