# External Harness Bridge for Expert Investigations

Status: proposed boundary refinement, researched 2026-09-01. No remote
investigation bridge or direct Grok Bot integration is shipped by this note.

Read [AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md),
[agentic-harness-boundary.md](agentic-harness-boundary.md),
[hosted-mcp-endpoint.md](hosted-mcp-endpoint.md), and
[evidence-first-expert-investigations.md](evidence-first-expert-investigations.md)
first.

## Decision

Deepr should make its existing evidence-first investigation lifecycle easy for
external agent harnesses to observe and invoke. It should not become a generic
actor runtime, shared computer service, chat scheduler, plugin kernel, or
personal-agent gateway.

The useful composition is:

```text
external harness
  owns conversation, task decomposition, schedules, computers, and handoff UX
  calls Deepr through a narrow MCP host profile

Deepr investigation
  owns one bounded evidence transaction, expert state, sources, checking,
  synthesis, artifacts, budget, lifecycle, and staged learning
```

This is a refinement of Deepr's current role, not a replacement architecture.
The current investigation runtime already has an immutable plan, explicit
roster, one parent capacity envelope, bounded parallel research, independent
checking, content-addressed artifacts, append-only events, pause, resume,
cancel, and explicit staged learning. A second general scheduler would
duplicate those controls and create competing sources of truth.

## What current harnesses establish

### Grok Bot and Grok Build

xAI documents Grok Bot as persistent named Bots on one shared user computer
with browser, filesystem, terminal, peer messaging, handoffs, skills, and
routines. xAI also states that the shared computer is not a security boundary.
These are useful host interaction patterns, not a safe internal state model for
Deepr. Sources: [overview](https://docs.x.ai/grok-bot/overview),
[collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration),
[computer](https://docs.x.ai/grok-bot/computer-and-apps), and
[security](https://docs.x.ai/grok-bot/approvals-security-and-privacy).

Agent Plugins now lists Grok Bot as a compatible client for Agent Skills and
stdio, Streamable HTTP, and legacy SSE MCP. This makes manual Deepr plugin or
MCP installation a real host target. It does not add a public Bot lifecycle API
or make the shared VM a Deepr security boundary. Source:
[compatible clients](https://agent-plugins.org/compatible-clients).

Grok Build 1.0.6 supports project MCP configuration in `.grok/config.toml`,
resolved-configuration evidence through `grok inspect --json`, and workflow
files that can coordinate parallel agents with verification. Controlled host
evidence must disable auto-update and bind the inspected executable version.
The documented MCP configuration has no exact tool filter, so Deepr's scoped
server surface remains authoritative. It does not make Grok Build's hidden
children or tools eligible Deepr capacity. Sources:
[settings](https://docs.x.ai/build/settings),
[MCP servers](https://docs.x.ai/build/features/mcp-servers),
[headless operation](https://docs.x.ai/build/cli/headless-scripting), and
[workflows](https://x.ai/news/workflows).

No documented public Grok Bot management API was found in the official Grok
Bot material reviewed on 2026-08-21. Automated Bot creation, routing, takeover,
and routine management are therefore not current implementation targets. A
Grok Bot operator may install or supervise a Deepr plugin or MCP connection
manually, but Deepr must not claim automated lifecycle support without a
published and testable interface. Grok Bot also lacks a documented per-product
spend cap, so its host controls cannot replace Deepr's zero-spend or bounded
server-side authority. Source:
[team controls](https://docs.x.ai/grok-bot/teams-and-enterprises).

### DeepSeek Harness

DeepSeek Harness `dsh-v0.1.1-rc.2` is a developer preview built around
replaceable plugins and profiles. Its append-only session log drives resume,
fork, search, replay, and UI trajectory projections. Its MCP client maps remote
server tools into the host tool registry. A Deepr profile should fail on MCP
startup errors instead of silently degrading. Harness tool restriction is a
visibility mechanism, not Deepr authorization. These are strong evidence for
two narrow Deepr additions:

- a versioned host profile with an exact tool allowlist; and
- replayable UI or chat projections over Deepr's authoritative event journal.

Deepr should not copy the Cordis plugin kernel, record private model reasoning,
or let plugins replace budget, evidence, or memory authority. The Harness is in
developer preview and states that its APIs will continue to evolve. Sources:
[product overview](https://deepseek.com/harness/en/),
[release](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.1-rc.2),
[architecture](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.1-rc.2/docs/architecture.md),
and
[MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.1-rc.2/packages/mcp/mcp-client/README.md).

### OpenClaw

OpenClaw stable `v2026.8.2` is an external gateway, channel, session,
workspace, tool, skill, and agent runtime. Its configuration supports stdio and
remote MCP servers, per-server timeouts, tool include and exclude filters,
OAuth configuration and token-storage posture, TLS controls, and a Codex app-server-specific agent
projection block. That block is not generic per-agent OpenClaw authority. Its
sandbox, tool policy, and elevated execution controls are intentionally
distinct.

That makes OpenClaw a practical first host integration. The implemented
`v2026.7.1-2` reference remains a pinned offline artifact. The conformant Agent
Plugin now makes ordinary MCP `tools/list` advertise the exact ten-tool general
read-only catalog because current OpenClaw materializes only tools returned by
that standard call. Hosts may prefix raw MCP names as `deepr__<tool>`. The
closed Agent Plugins MCP schema has no per-server tool filter, so Deepr's
policy-filtered catalog and independent call-time denial remain authoritative.
The later investigation observer profile should use the existing exported
`SKILL.md` with its narrower three-tool allowlist. Native Agent Plugins support
is stable upstream, but Deepr must not claim compatible execution until an
isolated `v2026.8.2` gateway fixture proves discovery, calls, restart behavior,
blocked tools, zero provider contact, and zero ledger delta. The host still
needs an installed `deepr-mcp` executable. Sources:
[stable release](https://github.com/openclaw/openclaw/releases/tag/v2026.8.2),
[MCP configuration](https://docs.openclaw.ai/gateway/configuration-reference),
[tool naming](https://github.com/openclaw/openclaw/blob/v2026.8.2/docs/plugins/bundles.md#tool-naming),
[MCP catalog](https://github.com/openclaw/openclaw/blob/v2026.8.2/src/agents/agent-bundle-mcp-runtime.ts),
and [tool materialization](https://github.com/openclaw/openclaw/blob/v2026.8.2/src/agents/agent-bundle-mcp-materialize.ts).

### NemoClaw and OpenShell

NVIDIA NemoClaw `v0.0.113` pins OpenShell 0.0.106 as the supported boundary,
even though a newer standalone OpenShell release exists. It runs supported
harnesses, including OpenClaw, inside sandboxes with network, filesystem,
process, inference, snapshot, and lifecycle controls. Its managed MCP flow
accepts authenticated HTTPS Streamable HTTP, keeps the secret value outside
sandbox configuration, and resolves a credential alias at egress.

NemoClaw is therefore a deployment and isolation profile for an external host,
not a Deepr runtime dependency. A first recipe should connect a NemoClaw
sandbox to Deepr's HTTP MCP endpoint using a dedicated scoped key and explicit
egress rule. It remains reference-only until Deepr validates that exact
NemoClaw and OpenShell pair, including its managed-MCP path and release
exceptions. Sources:
[release](https://github.com/NVIDIA/NemoClaw/releases/tag/v0.0.113),
[OpenShell pin](https://github.com/NVIDIA/NemoClaw/blob/v0.0.113/scripts/install-openshell.sh), and
[managed MCP](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/manage-sandboxes/mcp-servers/about-managed-mcp-servers).

### Other hosts and protocols

OpenHands treats the workspace, shell, browser, and repository as parts of an
outer agent harness. Firecracker provides a stronger Linux KVM microVM boundary
when an external host needs to run untrusted workloads. Neither is a reason for
Deepr to own computers per expert. Sources:
[OpenHands](https://github.com/OpenHands/OpenHands) and
[Firecracker](https://github.com/firecracker-microvm/firecracker).

OpenAI's current model guidance recommends bounded parallel subagents for
cleanly separable work, with explicit tools, output contracts, evidence,
concurrency, retries, and stop conditions. A2A is useful for communication among
separately operated opaque agents. MCP is the nearer fit for exposing Deepr
tools and resources. None of these replaces Deepr's run, artifact, authority,
and evidence contracts. Sources:
[OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model),
[A2A](https://github.com/a2aproject/A2A), and
[MCP](https://modelcontextprotocol.io/specification/2026-07-28).

## Standards alignment

The bridge uses three current external standards for separate jobs. They are
complementary, not competing orchestration models.

| Layer | Normative target | Deepr use | Boundary |
|---|---|---|---|
| Knowledge interchange | [OKF 0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) | Export selected expert knowledge and ingest external bundles as untrusted evidence | The canonical belief, event, and edge stores remain authoritative. |
| Installation and discovery | [Agent Plugins 1.0.0](https://agent-plugins.org/specification), Published | Package Agent Skills and an MCP server for conforming clients | A plugin packages code, skills, and MCP declarations, not canonical expert knowledge or credentials. |
| Runtime protocol | [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) | Expose bounded tools, resources, lifecycle projections, and later negotiated extensions | MCP transport state never becomes run, spend, credential, or verification authority. |

OKF 0.2 is a minimal Markdown and YAML specification, not a schema registry.
Deepr implements spec-derived validation and frozen interoperability fixtures
rather than inventing a canonical OKF JSON Schema. `deepr-okf-profile-v2`
moves concept frontmatter to the first line, restricts root `index.md`
frontmatter to `okf_version`, emits a frontmatter-free newest-first log,
replaces `timestamp` with `generated.at`, and publishes stored evidence as
frontmatter `sources`. `verified` is emitted only when canonical grounding
assurance records an actual checker. Lifecycle, staleness, and Attested
Computation fields remain absent because current canonical state does not
support their exact OKF meanings. Import stays permissive about optional
fields, unknown types, unknown keys, and broken links, then passes every
candidate through Deepr's verification-gated absorb path. The former
`deepr-okf-profile-v1` schema remains available as a deprecated compatibility
record, not the current export contract.

Agent Plugins 1.0.0 has a closed root manifest and locally pinned canonical
schemas. A Deepr package needs root `plugin.json`, optional root `mcp.json`, and
immediate `skills/<name>/SKILL.md` children. Paths remain inside `PLUGIN_ROOT`;
fresh plugin-owned persistent state may use `PLUGIN_DATA`. The package must not
silently bind an existing global expert root, embed credentials in environment
or HTTP headers, or represent OKF as a portable plugin component because the
1.0.0 core defines only Agent Skills and MCP servers. Clients must not fetch
schemas while loading the package.

MCP 2026-07-28 makes each request self-contained through per-request `_meta`
negotiation, explicit identifiers for state that spans requests, deterministic
list ordering and cache hints, and bounded JSON Schema 2020-12 inputs. The
canonical observer therefore remains a stateless read over explicit `run_id`
and cursor values. `subscriptions/listen` may announce that a cursor advanced,
but gap recovery always rereads the canonical journal. Optional Tasks, Skills
over MCP, MCP Apps, and multi-round tool requests are later negotiated
adapters. They do not belong in the first bridge and cannot grant spend,
credential, side-effect, or learning authority.

The practical rule is:

```text
OKF carries selected knowledge.
Agent Plugins installs discoverable skills and MCP declarations.
MCP carries bounded runtime requests and projections.
Deepr's typed stores and gates retain authority.
```

## Capability allocation

| Capability | External harness | Deepr | Rule |
|---|---|---|---|
| User chat, channels, team room, notifications | Owns | Projects events | Chat is never the scheduler or evidence store. |
| Cross-project task graph and schedules | Owns | None | Deepr accepts one bounded knowledge transaction. |
| Expert roster and frozen state | Proposes roster | Owns and validates | The plan fixes canonical identities and hashes. |
| Research fan-out | Requests | Owns within plan | The current five-expert maximum and parent envelope remain. |
| Browser, shell, repository workspace | Owns | None by default | Export immutable evidence artifacts into Deepr. |
| Credentials and external side effects | Owns | Refuses by default | A host request cannot grant Deepr new authority. |
| Source snapshots and claim evidence | Supplies or requests | Owns | Content hashes and locators remain authoritative. |
| Checking and synthesis | Observes | Owns | Agreement is not verification. |
| Budget and capacity admission | Supplies ceiling | Owns enforcement | Child work cannot widen the parent ceiling. |
| Pause, resume, cancel | Requests | Owns transition | The event journal is authoritative. |
| Learning | Proposes | Stages and explicitly applies | No transcript or host message becomes memory directly. |

## Portable plugin and host profile

The 2026-09-04 package review found no drift from the published Agent Plugins
1.0.0 schemas. It did find a validation gap: the clean-install check bypassed
the manifest's executable search and working directory, omitted the reserved
plugin environment variables, and covered only legacy MCP. The install check
now exercises the declared launch with the installed wheel on the host's
search path, completes the legacy handshake, and probes modern per-request
negotiation in a separate process. Extracted package and persistent data
directories containing spaces exercise argument and path handling. Repeated
launches retain a saved offline expert, verify its discovery, and leave its
bytes and the package unchanged. This is a bounded publisher check of Deepr's exact manifest,
not a new general plugin loader or a claim that an external host was tested.
The distributable also includes the project license.

The install guide states the external runtime prerequisite and the empty
initial expert inventory. Silently reconnecting ambient expert roots is
rejected because it changes which knowledge a host can inspect. Broadening the
ten-tool profile to make generative consultation available is separate
capability work. These checks follow the published
[stdio runtime rules](https://agent-plugins.org/client-implementers/mcp-runtime).

For clients that implement Agent Plugins 1.0.0, the preferred installation
artifact is a conformant Deepr plugin containing the generic Deepr skill and
stdio MCP declaration. Selected expert data is exported separately as OKF or
queried through MCP. The initial plugin is code and discovery only: it contains
no expert database, bearer credential, host account, remote route, or implied
metered authority.

Some popular hosts do not implement Agent Plugins, and even conforming clients
need an exact record of the policy used for one deployment. Deepr now publishes
a generated `deepr-mcp-host-profile-v1` reference alongside the existing
token-redacted `deepr-mcp-registration-manifest-v1`. A host profile is a derived
compatibility and capability artifact, not a competing plugin format,
canonical configuration, or claim of live support.

It records:

- pinned target host release, signed tag evidence, package version, and target
  commit;
- Deepr package version, explicit absent source-revision evidence, installed
  runtime dependency, and transport;
- credential and scoped-key posture without a secret;
- exact tool include list and explicit denied tool classes;
- scoped-key mode, expert allowlist, rate limit, and budget ceiling;
- request timeout, concurrency posture, and retry posture;
- host sandbox, filesystem, network, and approval posture when observable;
- local contract and host-conformance results.

The ordinary generator emits only `reference`. It has no input or flag that
can promote its own status. A later fixture or live validator must issue a
separate evidence record bound to the canonical profile SHA-256, exact host and
Deepr identities, validator identity, commands, result hashes, and all-pass
checks before a projection may derive `fixture_validated` or `live_validated`.

The first implemented profile is the local read-only OpenClaw reference. It
sets `DEEPR_MCP_ADVERTISE_FULL_TOOL_LIST=1`, so a standard `tools/list` request
receives the same ten policy-filtered tools recorded in the profile. This does
not widen the allowlist or change task, spend, credential, or evidence
authority.

The later investigation observer profile remains planned. Proposed read-side
tools are:

```text
deepr_investigation_status(run_id)
deepr_investigation_events(run_id, after_sequence, limit)
deepr_investigation_artifacts(run_id, after_name, limit)
```

The first release returns artifact metadata and hashes, not arbitrary artifact
content. A later content-read surface needs classification, size, media type,
taint, export policy, and exact run ownership checks.

Host-specific generated fragments are compatibility paths limited to
configuration shape:

- Grok Build project MCP configuration;
- DeepSeek Harness MCP client plugin row and observer profile overlay;
- OpenClaw `mcp.servers` entry with `toolFilter.include`;
- NemoClaw managed remote MCP command inputs and egress prerequisites;
- Codex MCP configuration;
- the existing portable expert `SKILL.md` for instruction-level discovery.

No plugin or generated profile installs a host, writes into a host
configuration, creates a remote account, opens a public network route, or
copies a bearer credential. An operator reviews and applies it. Live remote
validation remains blocked until Deepr has independent endpoint-cost authority
as required by the hosted MCP design.

## Projection seam

Every observer response has a versioned envelope and includes:

- canonical run id and immutable plan hash;
- lifecycle state, phase, attempt, and terminal reason;
- monotonically ordered cursor or artifact page position;
- observed and remaining deterministic ceilings;
- capability snapshot hash and control-evidence record hash;
- no private reasoning, credential, raw prompt, or local path;
- an explicit `projection_only: true` marker.

The event feed projects the existing append-only, content-free investigation
journal. It does not invent a second message history. A host may cache a team
room, trajectory, or task view, but deleting that cache and replaying from
sequence zero must reconstruct the same visible lifecycle.

Every modern MCP request supplies the negotiated protocol version and client
capabilities in request `_meta`; legacy initialization remains a compatibility
path already owned by the MCP server. Observer results use stable ordering,
bounded page sizes, explicit result types, and cache metadata from the current
core contract. If a client negotiates subscriptions, notifications carry only
enough information to resume from a cursor. They never replace the read tool or
deliver otherwise inaccessible content.

DeepSeek Harness supports replay from one append-only session log. Deepr should
adopt the projection seam but preserve a stricter content boundary: lifecycle
events remain content-free, while prompts, sources, results, and checks remain
separate content-addressed artifacts with independent access policy.

## Run-start capability evidence

Before remote start or control is considered, every investigation plan should
bind two additional derived artifacts.

### Capability snapshot

`deepr-investigation-capability-snapshot-v1` records:

- Deepr commit and package version;
- investigation schema versions;
- selected provider, model, capacity source, and auth mode;
- allowed Deepr verbs and explicit absence of unplanned tools;
- configured retrieval backends and network policy;
- roster and expert snapshot hashes;
- local or plan adapter identity and executable version when applicable;
- configuration hash, approval posture, and parent ceilings.

The snapshot is evidence about the admitted environment. It cannot create
authority. A changed executable, configuration, provider, model, or tool set
invalidates an approved plan and requires a new preview.

### Control-evidence record

`deepr-investigation-control-evidence-v1` joins the immutable plan, capability
snapshot, lifecycle journal, capacity decisions, approvals, artifacts,
verification, and learning dispositions. It is a generated audit projection,
not a canonical store that may rewrite its inputs.

## Steering without mutable runs

An active investigation plan remains immutable. Natural-language steering from
a host is represented by one of four typed requests:

```text
control.pause
control.cancel
run.follow_up
run.fork
```

Pause and cancel request existing lifecycle transitions. They cannot alter the
question, roster, tools, capacity, or learning policy.

A follow-up creates a new preview after the parent reaches a terminal state. It
may reference accepted parent artifacts, but it receives a new run id, plan
hash, capability snapshot, and explicit capacity envelope.

A fork may start only from a completed phase checkpoint. It creates a new run
with parent run, phase, and artifact lineage. It never edits or resumes the
parent under changed instructions. The caller may reuse remaining parent
capacity only when deterministic admission can bind that amount to the child.
Otherwise the child requires fresh explicit authority.

Free-form messages can propose one of these requests, but deterministic code
validates the typed form. No message can add experts, enable tools, grant
credentials, increase budget, apply learning, or mark a result verified.

## External workspace evidence

Deepr should not lease a computer to every expert. When a repository, browser,
or GUI task is useful, the external harness owns the workspace and exports an
immutable evidence bundle for a new or follow-up investigation.

A future `deepr-external-evidence-bundle-v1` should include:

- workspace provider and isolation class;
- base image or environment digest where available;
- repository URL and exact commit or archive hash;
- command and test-result artifacts with bounded output;
- browser source snapshots with retrieval time and final URL;
- exported file hashes, sizes, media types, and taint labels;
- declared credential aliases used, never secret values;
- actor identity and control-lease interval;
- an explicit statement of unverified external side effects.

Deepr treats the bundle as untrusted input. Claims still require source or
artifact evidence and independent checking. The initial Windows path should use
host-owned worktrees, containers, browsers, or WSL. Firecracker is a possible
remote Linux isolation tier after measured need, not a Windows-first Deepr
dependency.

## Grok capacity boundary

Grok Build has two separate potential roles:

1. external MCP host that calls Deepr; or
2. plan-capacity adapter that Deepr launches for one bounded generation.

The first role does not grant the second. Before either role is promoted, the
current adapter and documentation must agree. If the installed executable can
load ambient skills, agents, MCP servers, or native tools, the plan adapter must
remain blocked unless preflight proves the exact admitted capability set,
disables subagents, prevents ambient configuration inheritance, and confines
filesystem, network, process, output, and cancellation behavior. Explicit user
selection is not proof of safe marginal cost or confinement.

## Delivery plan

This is a dependency graph, not a duration estimate. A stage begins only after
its predecessor's acceptance gate is recorded.

### Bridge 0: standards truth and offline fixtures

Status: implemented 2026-08-20. OKF 0.2, Agent Plugins 1.0.0, Agent Skills,
and MCP 2026-07-28 have immutable upstream revisions, byte lengths, and hashes.
The exact Agent Plugins schemas are vendored for offline validation, and the
representative skill, plugin package, and modern MCP contracts are blocking.

- Pin the Agent Plugins 1.0.0 plugin and MCP schemas locally with their
  canonical identifiers and checksums.
- Freeze representative OKF 0.2, Agent Skill, Agent Plugin, and MCP fixtures.
- Implement an OKF spec-derived validator without claiming an external schema
  that the specification does not publish.
- Keep current MCP 2026-07-28 conformance blocking and add no model, paid, or
  network calls.

Gate: a clean checkout validates every pinned fixture offline and detects each
known legacy OKF violation.

### Bridge 1: OKF 0.2 migration

Status: implemented 2026-08-20 as `deepr-okf-profile-v2`, with the v1 schema
retained as a deprecated compatibility record.

- Repair reserved files, concept frontmatter placement, `generated.at`, and
  `sources` output while preserving Deepr extensions as unknown permitted keys.
- Add permissive import, export, round-trip, regeneration, path-containment,
  unknown-field preservation, and malformed-bundle fixtures.
- Emit `verified`, status, staleness, and attestation data only from supporting
  canonical state.
- Keep the belief, event, and edge stores authoritative and absorb verification
  mandatory.

Gate: externally shaped 0.2 fixtures round-trip without authority inversion;
the legacy profile label is retired only when conformance evidence passes.

### Bridge 2: Agent Skill and Agent Plugin packaging

Status: implemented 2026-08-20 for the contained, local, read-only foundation.

- Validate generated skills against the current Agent Skills specification,
  immediate-child discovery, and progressive-disclosure layout.
- Add a root `plugin.json`, stdio-first `mcp.json`, locally pinned schema
  validation, path containment, reproducible manifests, and clean-install
  tests.
- Keep expert data and OKF exports outside the plugin core. Use `PLUGIN_DATA`
  only for newly created plugin-owned state and never for hidden migration of
  an existing expert root.
- Prove that the package contains no credentials, schema-load network access,
  remote route, or implied paid authority.

Gate: a clean environment can inspect and invoke the local no-metered surface
through the package with byte-reproducible output and no secret material.

### Bridge 3: contracts and drift audit

Status: implemented 2026-08-21 for zero-call schemas and local projection
builders. The 2026-08-21 re-audit restored explicit production blocks
for Codex, Grok Build, and Antigravity. The first closed host-profile schema,
runtime-derived tool inventory, deterministic generator, and reference-only
OpenClaw stable artifact are implemented. Capability snapshot, control
evidence, status projection, event page, artifact metadata page, follow-up,
and fork lineage now have published schemas and read-only builders in
`deepr.experts.investigation.projection`. Follow-up and fork remain
preview-only (`implemented: false`) until Bridge 7.

- Publish zero-call schemas for capability snapshot, control
  evidence, event page, artifact metadata page, follow-up, and fork lineage.
- Add fixture validation proving projections cannot mutate a run or imply
  semantic acceptance.
- Keep every non-Claude plan adapter blocked until its exact ambient capability
  set, provider identity, and marginal-cost posture are proven before dispatch.

Gate: all contracts are versioned, bounded, path-safe, backward-compatible, and
accepted by the approach and supported-surface documents.

### Bridge 4: read-only investigation projection

- Expose status, event cursor, and artifact metadata through existing scoped
  MCP keys.
- Bind every read to an exact run owner and allowed expert scope.
- Keep event payloads content-free and paths redacted.
- Prove modern per-request negotiation, legacy compatibility, replay
  equivalence, deterministic pagination and cache metadata, cancellation
  visibility, cross-run denial, malformed journal failure, and bounded response
  size.
- Add negotiated cursor notifications only as an optimization over canonical
  reads.

Gate: deleting every host-side projection and replaying from sequence zero
reconstructs the same visible lifecycle without changing canonical state.

### Bridge 5: popular host conformance

- Prefer the conformant Agent Plugin package only where an exact stable host
  release passes Deepr's isolated evidence lane.
- Retain the implemented reference-only OpenClaw `v2026.7.1-2` fragment, then
  independently validate the Agent Plugin against stable `v2026.8.2` before
  promotion. The fixture must use ordinary `tools/list`, observe the exact ten
  `deepr__`-prefixed read-only tools, call status, deny paid and write tools,
  survive restart, make zero external provider requests, and leave zero ledger
  delta.
  Generate offline observer profiles and exact fragments for DeepSeek Harness
  `dsh-v0.1.1-rc.2`, Grok Build 1.0.6, and Codex where needed.
- Treat NemoClaw `v0.0.113` plus its pinned OpenShell 0.0.106 as a remote
  isolation recipe after HTTP auth, egress, and endpoint-cost prerequisites
  pass. Do not substitute a newer standalone OpenShell release.
- Record host version, transport, exact tool inventory, and validation
  evidence. Profiles remain `reference`; a separately validated,
  digest-bound evidence artifact derives any stronger status.
- Allow a manual Grok Bot Agent Plugin or MCP host profile, but do not claim Bot
  lifecycle automation or supported public hosting.

Gate: every advertised host claim has a reproducible fixture or live evidence;
reference-only recipes remain labeled as such.

### Bridge 6: shared parent transaction and remote authority

- Move every multi-call or metered lifecycle behind one durable parent
  reservation, settlement, reconciliation, cancellation, and maximum-charge
  contract.
- Complete scoped HTTP authentication, credential aliases, endpoint ownership,
  rate limits, and independent provider-cost evidence before remote mutation.
- Keep observer reads unable to spend, widen a roster, or select hidden model
  capacity.

Gate: crash, retry, timeout, and ambiguous-provider tests cannot overshoot the
parent ceiling or duplicate an external effect.

### Bridge 7: lineage-only steering

- Add preview-only follow-up and fork requests over MCP.
- Add pause, resume, and cancel only after ownership, idempotency, race, and
  audit tests pass.
- Keep remote start behind a separately hashed plan preview, capability
  snapshot, and exact per-key ceilings.
- Keep learning apply out of every convenience profile.
- Use negotiated multi-round tool requests only for missing input or approval
  presentation, never as authority.

Gate: every control transition is idempotent, hash-bound, race-tested, and
reconstructible from the canonical journal.

### Bridge 8: external evidence bundles

- Admit bounded, hash-verified workspace output as untrusted investigation
  input.
- Compare repository and browser cases with and without computer-produced
  evidence under matched total resources.
- Add artifact-content reads only after classification and export policy pass
  red-team and cross-run tests.

Gate: workspace artifacts cannot cross run boundaries, carry instructions into
policy, or become accepted claims without independent checking.

### Bridge 9: optional protocol extensions

- Evaluate MCP Tasks as an adapter over the existing investigation handle only
  after host negotiation and recovery behavior are interoperable.
- Evaluate Skills over MCP only after static Agent Skill and Agent Plugin
  packaging is stable.
- Evaluate MCP Apps only when a host projection has measured user value that a
  normal tool or resource cannot express.
- Keep A2A, general actor runtimes, shared brokers, and multi-tenant scheduling
  behind their separate evidence gates.

Gate: each extension removes a measured limitation without duplicating or
weakening Deepr's canonical lifecycle and authority model.

## Evaluation

Extend the existing investigation comparison instead of creating a new generic
multi-agent benchmark stack. Add these host conditions:

```text
existing local investigation through CLI
the same immutable plan observed through an MCP host profile
external host decomposition into bounded Deepr investigations
```

The first two must be behaviorally equivalent for plan hash, events, artifacts,
cost, result, and learning disposition. The third must justify its coordination
cost against one Deepr investigation under matched total capacity.

Measure accepted claim precision, citation entailment, primary-source ratio,
source diversity, coverage gaps, dissent preservation, reproducibility, wall
time, calls, tokens, context, disk, network, dollars, duplicate work,
coordination overhead, recovery correctness, unsafe side effects, and human
interventions.

Chaos cases include duplicate remote requests, expired scoped keys, host death,
event replay after cache loss, cancellation at every phase boundary, malformed
external evidence, prompt injection in workspace artifacts, cross-run access,
and ambiguous host side effects.

## Deferred infrastructure and triggers

| Technology or pattern | Current decision | Reconsider only when |
|---|---|---|
| General actor runtime or tuple space | Reject for Deepr core | A measured Deepr protocol cannot use the existing phase state machine and event journal. |
| DeepSeek Cordis plugin kernel | Reject | Deepr needs stable internal replacement seams beyond its current interfaces and can preserve authority across dynamic unload. |
| Temporal | Defer | Multi-day, multi-service recovery repeatedly fails under the current owned lifecycle. |
| NATS JetStream | Defer | Independent consumers and measured throughput exceed direct MCP projection after idempotent handlers exist. |
| PostgreSQL scheduler or RLS | Defer for investigations | Multi-tenant deployment is approved and file-backed ownership is insufficient. |
| Firecracker per expert | Reject | A high-risk external workspace may use a remote Linux microVM, but the expert is not the computer. |
| Generated TLA+ per user task | Reject | Formal methods may verify one stable lease, cancellation, or effect-ordering protocol, not generated research topology. |
| Process reward model or RLSVR training | Reject for roadmap | Synthetic latent-variable fixtures may improve evals, but Deepr is not a model-training platform. |
| A2A investigation surface | Defer | MCP parity, durable service conformance, and ownership semantics pass first. |
| IM-style Deepr scheduler | Reject | A host may project events as chat, but typed runs and events remain authoritative. |

## Acceptance criteria

- Existing local CLI investigation behavior and artifacts remain backward
  compatible.
- The bridge cannot widen a plan's roster, capacity, tools, retrieval, network,
  write, or learning authority.
- Projection replay from sequence zero reconstructs the same visible lifecycle
  after deleting all host-side state.
- No host message, transcript, external artifact, or agent agreement becomes a
  belief or verification decision.
- A remote caller cannot read or control a run outside its exact scope.
- Every control request is idempotent, audited, hash-bound, and race-tested.
- A child or fork has explicit parent lineage and never mutates its parent.
- External workspace results remain immutable, tainted evidence until checked.
- Host profiles contain no secrets, make no unvalidated support claims, and do
  not install or mutate the target host.
- OKF export passes 0.2 fixtures without treating OKF as canonical state or
  inventing a schema-registry claim.
- Agent Plugin packaging passes pinned 1.0.0 schemas offline, contains only
  defined component types, keeps paths inside the package, and carries no
  credentials or expert database.
- Modern MCP requests remain self-contained and explicit about run identity;
  subscriptions and optional extensions cannot become authority.
- The Grok plan adapter is blocked whenever ambient capability confinement or
  marginal-cost posture cannot be proved before dispatch.
- No distributed runtime, workspace service, or new protocol is added without a
  measured failure that the smaller bridge cannot solve.
