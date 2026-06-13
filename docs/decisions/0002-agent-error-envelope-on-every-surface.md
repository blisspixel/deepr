# 0002. Agent error envelope on every error surface

- Status: Accepted
- Date: 2026-06-12

## Context

Deepr is explicitly callable by AI agents (MCP, CLI `--json`). A 2026 CLI
best-practices review (clig.dev plus the RFC 9457 / agent-error pattern)
found that machine consumers need to classify a failure and drive backoff
without parsing prose: a broad `category` to branch on and a boolean
`retryable` (plus `retry_after` when known). Deepr had two unrelated error
representations - `deepr.core.errors.DeeprError` (code + message + details)
and a separate `providers.base.ProviderError` - and the MCP `ToolError` had
only human-readable `retry_hint`/`fallback_suggestion` strings, not machine
fields. The classification was therefore unavailable to agents, and where it
existed it was inconsistent across surfaces.

## Decision

Every error surface emits the same envelope - `category`, `retryable`, and
`retry_after` (when known) - additively, alongside existing keys:
`DeeprError`, `providers.ProviderError`, the MCP `ToolError`, and the CLI
`OperationResult` JSON. `ProviderError` auto-classifies from its wrapped
`original_error` via a shared `classify_provider_exception()` helper, so
every adapter's existing `raise ProviderError(..., original_error=e)` gets
correct classification with no per-site edits.

## Alternatives considered

- **Unify the two hierarchies** (make `ProviderError` extend `DeeprError`).
  Rejected for now: broad, risky refactor touching every adapter and its
  tests; the envelope gives agents what they need without it. Left as a
  possible future ADR.
- **Populate classification at each `raise` site.** Rejected: ~50 sites
  across 7 adapters, easy to miss one. Auto-classifying in `__init__` from
  `original_error` covers them all and stays correct as adapters change.
- **Only enrich the surface agents hit most (MCP).** Rejected: scripts use
  CLI `--json` and library callers see exceptions directly; a reliable
  contract must be consistent everywhere or consumers cannot depend on it.

## Consequences

- The envelope fields are always present where they form a contract (MCP
  `ToolError`, CLI error JSON), so an agent can rely on them; existing keys
  are unchanged, so nothing breaks.
- Transient provider failures (timeout, unavailable, rate-limit) are
  `retryable`; auth/budget/config/validation are actionable and not.
- Follow-on (not blocking): if a need arises, unify the two error
  hierarchies under one base - tracked as a possible future decision.
