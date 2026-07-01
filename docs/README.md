# Deepr Documentation

> Model names and pricing live in the registry (`src/deepr/providers/registry.py`),
> which is the single source of truth. AI moves fast - verify at provider
> websites and treat the registry, not prose, as canonical.

Organized by what you are trying to do: learn it, look something up, or
understand why it works the way it does.

## Getting started (learning)

1. **[INSTALL.md](INSTALL.md)** - Installation and setup
2. **[QUICK_START.md](QUICK_START.md)** - Your first research job
3. **[EXAMPLES.md](EXAMPLES.md)** - Real-world usage examples

## Core reference (looking things up)

- **[FEATURES.md](FEATURES.md)** - Complete feature and command reference
- **[CAPACITY.md](CAPACITY.md)** - Local, plan-quota, metered API, scheduler, and no-surprise-bills behavior
- **[EXPERTS.md](EXPERTS.md)** - Domain expert system guide
- **[MODELS.md](MODELS.md)** - Model selection and provider guide
- **[../mcp/README.md](../mcp/README.md)** - MCP server setup and tools
- **[MCP_A2A_INTEROP_CHECKLIST.md](MCP_A2A_INTEROP_CHECKLIST.md)** - Current MCP and A2A host interop review checklist

## Technical

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture and security
- **[security/THREAT_MODEL.md](security/THREAT_MODEL.md)** - Repository threat model and severity calibration
- **[BENCHMARKS.md](BENCHMARKS.md)** - Model benchmarks, scoring methodology, results
- **[CALIBRATION.md](CALIBRATION.md)** - Measured extraction-confidence calibration (reliability curve, ECE, threshold)
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

## Design notes and decisions (understanding why)

The reasoning behind contract-spanning choices, kept versioned with the code.

- **[plans/AGENTIC_BALANCE.md](plans/AGENTIC_BALANCE.md)** - Cross-cutting
  principle: workflow vs agent, what deepr hardcodes vs lets the model decide
  (determinism on side-effects, not meaning).
- **[design/level-5-6-expert-maturity.md](design/level-5-6-expert-maturity.md)** -
  concrete gates for bounded self-improving experts, self-models,
  metacognitive monitoring, and the expert-fleet control plane.
- **[design/evidence-correlation-and-hypothesis-memory.md](design/evidence-correlation-and-hypothesis-memory.md)** -
  how Deepr uses correlation math for evidence dependence, hypothesis memory,
  freshness priority, and candidate routing without turning scores into meaning
  verdicts.
- **[design/expert-chat-capacity-backends.md](design/expert-chat-capacity-backends.md)** -
  how expert consult and chat should support local, plan-quota, and paid API
  backends without silent fallback or provider-shaped cost leaks.
- **[design/](design/)** - Design notes (the why, with literature grounding):
  belief lifecycle, temporal knowledge graph, calibration and trust,
  deterministic-vs-agentic checks, capacity waterfall, local fresh context,
  verified expert loops, hosted MCP endpoint, code health, web UI refinement.
- **[decisions/](decisions/)** - Architecture Decision Records (ADRs) and the
  [ADR log](decisions/README.md): the decision, and the alternatives rejected.

## Project direction

- **[../ROADMAP.md](../ROADMAP.md)** - Development priorities and status (single source of truth for active work)
- **[INTEGRATIONS.md](INTEGRATIONS.md)** - First-party tool integrations (recon, distillr, primr)
- **[AGENTIC_VISION.md](AGENTIC_VISION.md)** - Agentic architecture, A2A protocol, reflection, campaigns
- **[VISION.md](VISION.md)** - Long-term direction (aspirational)

## Source of truth (avoid drift)

Volatile facts live in exactly one canonical place. Other docs link to it or
describe it qualitatively rather than restating the number, so a single update
keeps everything correct. `scripts/check_docs_consistency.py` (run in CI)
derives each number from the code and fails the build if a doc overstates it.

| Fact | Canonical home | Derived from |
|------|----------------|--------------|
| Model names / pricing | `src/deepr/providers/registry.py` | the registry itself |
| Test count, coverage gate | [../ROADMAP.md](../ROADMAP.md) "Current Status" | `tests/`, `pyproject.toml` `fail_under` |
| MCP tool count + breakdown | [../mcp/README.md](../mcp/README.md) | `src/deepr/mcp/server.py` `tool_dispatch` |
| Web page count | [FEATURES.md](FEATURES.md) | `src/deepr/web/frontend` routes |
| Skills, slash commands | [EXPERTS.md](EXPERTS.md) | `experts/commands.py`, skills dir |

The front-door [../README.md](../README.md) may quote headline counts; those
references are covered by the CI check so they cannot go stale. Secondary docs
(SECURITY, VISION, AGENTIC_VISION) should stay qualitative and link here.

## Archive

Historical docs, completed work, and superseded specifications follow the
[archive policy](ARCHIVE.md).

---

**Keeping current**: when new AI models are released, update the model registry
at `src/deepr/providers/registry.py` - never hardcode model names elsewhere. For
other volatile facts (counts, thresholds), see the "Source of truth" table
above and run `python scripts/check_docs_consistency.py` to verify docs match
the code.
