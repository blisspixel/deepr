# External standards pins

Last reviewed: 2026-08-21.

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

Agent Plugins 1.0.0 and Agent Skills remain current at the pinned revisions.
The MCP repository head has advanced through SDK and proposal guidance changes,
but its published 2026-07-28 normative schema remains byte-identical to Deepr's
pin. Deepr does not repin a normative fixture solely because an unrelated
upstream head moved.

These standards define installation and transport boundaries. They do not
replace Deepr's authoritative runs, tasks, beliefs, evidence, budgets,
credentials, approvals, or audit records.
