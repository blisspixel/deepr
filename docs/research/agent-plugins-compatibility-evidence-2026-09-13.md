# Agent Plugins compatibility evidence

Deepr's package targets the current published Agent Plugins 1.0.0 format.
Its manifest, portable skill, stdio declaration, and contained read-only
profile match that target. This review corrected three publisher validation
defects and added passing regressions. It does not certify every external
client or claim a fresh installed-wheel runtime result.

No host was installed or configured, no credentials were inspected, and no
research, model, or paid provider call was made. Official documentation and
public specification files were read. Temporary tests resolved inert fixture
executables without launching them.

## Current standard and revision evidence

The official site describes 1.0.0 as Published. The upstream repository lists
1.1.0 as a Working Draft. Continuing to target 1.0.0 is appropriate; a draft
does not supersede the published contract. The upstream conformance checklist
is guidance for clients, while the normative specification determines package
requirements. These pages were checked on 2026-09-13; their access date is
not an inferred publication date. Sources:
[published specification](https://agent-plugins.org/specification),
[repository status](https://github.com/agentplugins/agent-plugins-spec),
[working draft](https://github.com/agentplugins/agent-plugins-spec/blob/main/spec/1.1.0.md),
and [client checklist](https://agent-plugins.org/client-implementers/conformance).

Both vendored 1.0.0 schemas were compared with the public upstream `main`
files and the repository's pinned revision
`ff8ab5e392cc87bd88d87c060815a87490e51003`. All three copies matched byte for
byte in each comparison:

| Schema | SHA-256 |
| --- | --- |
| `plugin.schema.json` | `0a4aad95ce337878ad38802ebf0daa3fde76abe3f65400c86bcbb1ec0b3ab883` |
| `mcp.schema.json` | `6539175bfcdf43085855183e86da40ea94b166547a72b47ae9a0a390516d3acb` |

Canonical sources are the [plugin schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json)
and [MCP schema](https://agent-plugins.org/schemas/1.0.0/mcp.schema.json).
The live upstream HEAD commit lookup returned GitHub's unauthenticated API
rate-limit response, so this record makes no claim about its exact commit id.
The actual downloaded schema digests above were obtained successfully.

## Package assessment

| Area | Deepr evidence | Result |
| --- | --- | --- |
| Portable root | `packages/deepr-agent-plugin/plugin.json`, `mcp.json`, and one immediate `skills/deepr-research/SKILL.md` | Correct fixed layout; no alternative core manifest or host-specific discovery override. |
| Manifest | Canonical 1.0.0 schema id, valid `deepr-research` name, matching package version, typed metadata | Existing package validates against the official schema. Publisher validation now also rejects explicit null optional collections. |
| Skill | Required name/description, matching directory name, bounded compatibility text, string metadata, relative capability reference | Passes the offline skill contract; no executable scripts or portable preapproval claim is required. |
| MCP command | `type: stdio`, bare `deepr-mcp` executable, no shell command text | Correct external-runtime declaration. The installed executable must already be visible to the host. |
| Persistent state | `cwd: ${PLUGIN_DATA}` and explicit Deepr roots beneath `${PLUGIN_DATA}/deepr` | The runtime does not depend on an ambient expert root. The package documents its initially empty expert inventory. |
| Authority | Explicit `read_only`, auto-approval disabled, zero spend limits, exact ten-tool discovery profile | Compatibility does not grant generative consultation, paid dispatch, arbitrary skill execution, or expert writes. |
| Package integrity | Closed file inventory, checksums, bundled license, reproducible archive, path and output-alias tests | Passing publisher checks; archive generation leaves the source package unchanged. |

The [Agent Skills specification](https://agentskills.io/specification) defines
the portable skill format. It describes `allowed-tools` as experimental, so
the package correctly relies on the MCP server's actual policy-filtered
catalog instead of treating optional skill metadata as an enforcement layer.

The current [MCP runtime guidance](https://agent-plugins.org/client-implementers/mcp-runtime)
requires single executable-token handling, persistent plugin data, and
well-defined placeholder/cwd behavior. The publisher check emulates these
parts of Deepr's declared launch; it is not a general Agent Plugins client.
Its strict rejection of invalid distributable metadata is therefore not an
attempt to replace the more permissive failure handling required of client
loaders.

## Corrections made

The design was recorded before implementation in
[agent-plugin-publisher-conformance-corrections.md](../design/agent-plugin-publisher-conformance-corrections.md).

1. `src/deepr/skills/agent_plugin.py`: distinguish an omitted optional field
   from an explicit null. `keywords` and `extensions` must satisfy their
   existing type checks whenever present. The previous implementation could
   package a manifest that the pinned schema rejects after checksums were
   refreshed.
2. `scripts/check_agent_plugin_install.py`: expand exact plugin placeholders
   in one pass. A real path containing literal `${PLUGIN_DATA}` or
   `${PLUGIN_ROOT}` now survives insertion unchanged. Unknown placeholder
   text remains literal, and argument tokens remain separate.
3. The same publisher check now resolves `./` cwd declarations from the
   plugin root, supports the existing root/data placeholder forms, resolves
   filesystem aliases before checking containment, and rejects unsupported
   roots, escapes, and non-directory targets. The existing package's cwd and
   environment declarations did not change.

These changes preserve the deployed capability boundary. They correct
configuration handling and package validation rather than adding a new
runtime or semantic rule.

## Verification and practical limits

The new regression run reproduced 11 failures before the fixes. After the
fixes, both package and installed-launch test modules passed: **31 passed,
zero skipped**, using Python 3.12.13 on Windows. The external standards pin
and Agent Skills contract modules also passed: **11 passed, zero skipped**.
The normal unit socket guard remained enabled. Targeted runs used
`--no-cov`; they do not establish the repository's 80% global coverage gate.
Ruff format and Ruff check passed for all four edited Python files.

The existing `.github/workflows/ci.yml` `agent-plugin` job performs the
separate clean-wheel installation and actual stdio exchange on Ubuntu. It
tests executable resolution, ordinary and full catalog agreement, blocked
research despite approval arguments, both supported MCP eras, paths with
spaces, and expert-data preservation after package replacement. Those are
existing configured checks, not a newly observed green CI run.

An initial Windows installed-wheel check stalled during Proactor/socketpair
initialization. A bounded retry passed the actual stdio exchange for both
protocol eras and retained data across package replacement. This verifies
the packaged subprocess profile, not certification by an external host.
See the final [verification record](../validation/research-review-2026-09-13.md)
for the release candidate and remaining platform limits.

The [official client directory](https://agent-plugins.org/compatible-clients)
currently lists VS Code, Cursor, GitHub Copilot, ChatGPT and Codex, Kiro,
Hermes Agent, OpenClaw, Grok Bot, and NanoClaw with component/transport
support. This is upstream compatibility information, not evidence that each
has loaded Deepr successfully. Deepr requires a host that supports both
skills and stdio MCP for the complete package experience. Installation,
enablement, prompts, and host permissions remain host-specific.

The next release claim should be precise: published Agent Plugins 1.0.0
package conformance with a bounded read-only stdio profile, verified
publisher checks, and individually recorded host smoke results when those
exist. Full test coverage and exact-commit CI remain release gates.
