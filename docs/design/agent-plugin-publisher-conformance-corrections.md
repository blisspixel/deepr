# Agent Plugin publisher conformance corrections

Status: accepted for implementation, 2026-09-13.

The published Agent Plugins 1.0.0 schemas still match the vendored copies.
This change corrects the existing package validator and publisher install
check; it does not add a general plugin loader or change Deepr's read-only
MCP package.

## Problem

The package validator treats explicit null `keywords` and `extensions` as if
the optional properties were absent. The official schema requires an array
and object respectively when those properties are present.

The installed-package check expands `PLUGIN_ROOT` and then `PLUGIN_DATA`
with chained replacements. A path containing literal placeholder text can
therefore be expanded twice. It also resolves a declared `./` working
directory against the check process's working directory rather than the
plugin root.

## Decision

Validate present optional fields even when their value is null. Preserve the
closed publisher contract and existing violations.

Expand exact `${PLUGIN_ROOT}` and `${PLUGIN_DATA}` occurrences in one pass
across `args`, `env` values, and `cwd`. Leave unknown placeholder text and
replacement text literal. Never expand the executable command or env names.

Resolve `./` and `${PLUGIN_ROOT}` working directories against the resolved
plugin root, and `${PLUGIN_DATA}` working directories against the resolved
data root. Reject unsupported forms, resolved escapes, and non-directories.
Continue resolving the declared executable through the supplied installed
runtime's search path, preserving argument tokens and avoiding a shell.

The existing package's `${PLUGIN_DATA}` working directory and environment
remain unchanged. No credentials, new tool authority, or provider access is
introduced. This is deterministic configuration handling, not semantic
judgment; the agentic boundary remains unchanged.

## Alternatives and verification

Recursive environment expansion is rejected because it changes literal
paths and violates the standard. Resolving `./` against process cwd is
rejected because a publisher check must reproduce the declared plugin launch.
Installing a real external host is unnecessary for these bounded regressions
and would test a different integration boundary.

Tests use synthetic executables that are resolved but never run. Cover null
metadata, literal placeholders inside replacement paths, unknown placeholders,
argument boundaries, all allowed cwd roots, traversal, and invalid cwd kinds.
The existing installed-wheel MCP smoke remains the end-to-end publisher
check, subject to its normal platform and socket constraints.

References: [manifest schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json),
[MCP runtime](https://agent-plugins.org/client-implementers/mcp-runtime), and
[normative specification, sections 7.2.1 and 9](https://agent-plugins.org/specification).
