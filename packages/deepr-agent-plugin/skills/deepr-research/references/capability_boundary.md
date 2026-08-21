# Capability boundary

This Agent Plugin is a narrow installation bridge. It does not turn host chat,
plugin state, MCP sessions, or external artifacts into Deepr authority.

The profile permits only tools that the running MCP server classifies as
allowed in `read_only` mode and exposes through mode-filtered discovery. Tool
calls cannot widen authority through `_approved`, auto-approval, inherited
spend caps, or an invalid mode value.

Expected local effects are limited to Deepr runtime and audit state beneath
`${PLUGIN_DATA}/deepr`. Long-lived secrets must not appear in the manifest,
skill, model context, logs, or artifacts.

Use a separately reviewed host profile for write, execute, sensitive, remote,
or metered capability. Deepr's canonical task, belief, evidence, budget,
credential, approval, and audit contracts remain authoritative.
