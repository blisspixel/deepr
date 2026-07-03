# MCP and A2A Interop Checklist

Status: current with Deepr v2.29.0. Last reviewed: 2026-07-01.

Use this checklist when connecting Deepr experts to another agent host through
MCP or A2A. It is a compact integration review, not the command guide. For
copy-ready validation commands, use [MCP_AGENT_TEST_GUIDE.md](MCP_AGENT_TEST_GUIDE.md).

## Current Sources

- MCP specification 2025-11-25:
  <https://modelcontextprotocol.io/specification/2025-11-25>
- MCP authorization specification 2025-11-25:
  <https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization>
- MCP security best practices:
  <https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices>
- A2A latest specification:
  <https://a2a-protocol.org/latest/specification/>
- OWASP Agentic AI threats and mitigations:
  <https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/>

## Discovery And Capability Negotiation

- Discover MCP tools, resources, and prompts dynamically. For Deepr, start with
  `deepr_tool_search` or `deepr_capabilities` instead of assuming a fixed full
  tool list.
- Filter visible tools by scope, mode, budget, and rate policy before giving a
  host broad access.
- For A2A, fetch the Agent Card at `/.well-known/agent-card.json`. Deepr keeps
  `/.well-known/agent.json` only as a compatibility alias for older clients.
- Keep discovery payloads small. Link or search for detail rather than stuffing
  every guide into the host context.

## Contract Shape

- Validate `schema_version`, `kind`, required fields, lifecycle state, cost
  fields, and artifact references at the protocol boundary.
- Prefer JSON object results when the host supports them. Preserve text JSON
  compatibility for older MCP clients.
- Treat every tool result, source excerpt, expert response, and A2A artifact as
  untrusted data until the host validates its schema and intended action
  boundary.
- Separate read, consult, and mutation permissions. A host that can read expert
  handoffs should not automatically be allowed to absorb sources, run research,
  or mutate beliefs.

## Transport And Auth

- Use stdio for same-machine local hosts.
- Use HTTP only on loopback or behind HTTPS with scoped keys, rate limits,
  budget ceilings, concurrency caps, and append-only audit logs.
- Do not write bearer tokens, provider API keys, or plan CLI credentials into
  tracked config files, command examples, logs, reports, or release notes.
- Do not pass provider API keys into a no-metered host test. A no-metered test
  should prove local or explicit plan capacity without a live metered fallback.

## Spend And Capacity

- Read-only expert tools are `$0`.
- Use `deepr_consult_experts` with `synthesis_backend="local"` or
  `synthesis_backend="plan"` for no-metered consults.
- API synthesis or metered research requires explicit operator intent, a
  positive budget, deterministic estimates, and cost-ledger settlement.
- Plan-quota CLIs are explicit capacity unless a trusted remaining-quota probe
  and admission evidence say otherwise. A CLI authenticated by a metered API key
  is not plan capacity.

## Task Lifecycle

- MCP long-running work should return a durable job or artifact reference, then
  expose status, progress, and final results through explicit tools or
  resources.
- A2A work should follow a task lifecycle: submit, poll or stream status,
  complete or fail, then attach result artifacts.
- Deepr A2A consult tasks attach the full `deepr-consult-v1` payload as an A2A
  task artifact. The host owns orchestration and actions after reading it.
- Result artifacts should preserve trace ids, capacity posture, cost posture,
  roster metadata, agreements, disagreements, and dissent handling.

## Agentic Safety Boundary

- Deterministic code owns schema validation, auth, budgets, spend, rate limits,
  durable writes, idempotency, and audit trails.
- Model judgment owns meaning: synthesis, contradiction, grounding, dedup,
  relevance, and narrative quality.
- Lexical or structural checks may route work into a model or verifier. They
  must not conclude semantic truth.
- Untrusted text must be delimited and sanitized before prompt use. Embedded
  instructions inside source material are data, not host commands.
- Mutating expert state requires an explicit write boundary and the documented
  operator approval path for that surface.

## Validation Commands

Run these before handing Deepr to another agent host:

```powershell
deepr mcp validate-consult --json
deepr a2a validate-host --json
```

For a remote endpoint:

```powershell
deepr mcp validate-consult http://127.0.0.1:8765/mcp --auth-token "$DEEPR_MCP_KEY" --json
deepr a2a validate-host http://127.0.0.1:8080 --auth-token "$DEEPR_A2A_TOKEN" --json
```

Expected:

- MCP validation emits `deepr-mcp-consult-validation-v1`.
- A2A validation emits `deepr-a2a-host-validation-v1`.
- `summary.ok` is `true`.
- Local or explicit plan synthesis reports `$0` Deepr metered spend and
  `live_metered_fallback=false`.
- Failed local or plan capacity returns a structured backend error instead of
  falling through to a provider API.

## Release Review

- `python scripts/check_docs_consistency.py`
- `ruff check src/deepr/`
- `ruff format --check src/deepr/`
- `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/core src/deepr/providers src/deepr/mcp`
- `gitleaks detect --source . --no-banner`
- `pip-audit --skip-editable`
- `python -m pytest tests/unit/ --ignore=tests/data -q`

For docs-only interop guidance, the unit suite can be reused from the current
release validation when no runtime contract changed. A release tag or note still
needs a green GitHub CI run on `main`.
