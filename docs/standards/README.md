# External standards pins

Deepr validates external interoperability contracts offline. The pin registry
records the upstream version, immutable revision, canonical byte length, and
SHA-256 digest used by blocking checks. Network access is required only when an
operator deliberately refreshes a pin.

The Agent Plugins schemas are vendored because plugin packaging must be
validated without trusting a mutable URL. Agent Skills has a prose hard-form
contract, so Deepr pins the specification and implements its required fields,
types, lengths, and directory identity in `deepr.skills.contract`. MCP keeps its
existing dual-era conformance suite and pins the current 2026-07-28 schema as
the external dependency anchor.

These standards define installation and transport boundaries. They do not
replace Deepr's authoritative runs, tasks, beliefs, evidence, budgets,
credentials, approvals, or audit records.
