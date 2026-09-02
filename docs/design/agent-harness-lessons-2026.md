# Agent Harness Lessons for Deepr

Status: researched roadmap design, updated 2026-09-01. Nothing in this document is
shipped merely because it is described here.

The current Deepr-specific integration decision is
[external-harness-investigation-bridge.md](external-harness-investigation-bridge.md).
It keeps persistent chat, cross-project orchestration, and computer workspaces
in the external host while exposing Deepr's bounded investigation lifecycle
through a narrow, projection-first MCP profile.

## Goal

Deepr should learn from current agent harnesses without becoming a generic
coding-agent shell or widening ahead of its research-verification loop. The
useful question is not which harness to copy. It is which proven interaction
and control patterns make expert research more reproducible, steerable, and
safe.

## Current landscape

- Hermes Agent v0.21.0, released 2026-08-31, combines persistent recall,
  scheduling, isolated subagents, skill creation, and multiple execution
  backends behind one personal-agent gateway
  ([repository](https://github.com/NousResearch/hermes-agent),
  [release](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.31),
  [commit](https://github.com/NousResearch/hermes-agent/commit/29112bef099274229cadff79cdff7bf7b99c4b77)).
- OpenClaw stable `v2026.8.2`, released 2026-09-01, emphasizes an always-on local
  gateway, scoped skills, session snapshots, device pairing, sandboxing,
  prepared approvals, fail-closed execution, and release-integrity evidence
  ([repository](https://github.com/openclaw/openclaw),
  [security model](https://github.com/openclaw/openclaw/blob/main/docs/gateway/security/index.md),
  [skills](https://github.com/openclaw/openclaw/blob/main/docs/tools/skills.md),
  [release](https://github.com/openclaw/openclaw/releases/tag/v2026.8.2),
  [commit](https://github.com/openclaw/openclaw/commit/0965053fe6b9341776df147a6934b7485c60b5ca)).
  Agent Plugins are stable upstream. Deepr's package remains unvalidated against
  that exact host release until the isolated gateway fixture passes.
- OpenCode v1.18.26 keeps provider, model, session, permission, plugin, and MCP
  selection visible, but its broad coding-agent surface and configurable
  providers are not a substitute for Deepr's spend and evidence authority
  ([repository](https://github.com/anomalyco/opencode),
  [release](https://github.com/anomalyco/opencode/releases/tag/v1.18.26),
  [commit](https://github.com/anomalyco/opencode/commit/774cc7c1914e4329eefde5a669f938b0cf566661)).
- Pi v0.84.4 keeps the harness composable across model
  APIs, core loop, TUI, SDK, and JSON-RPC. Its session model distinguishes
  steering from follow-up input and supports abort recovery, trees, and forks
  ([repository](https://github.com/earendil-works/pi),
  [release](https://github.com/earendil-works/pi/releases/tag/v0.84.4),
  [commit](https://github.com/earendil-works/pi/commit/b79e4cc834970cca69daebffab7df1da7d1e52c4),
  [session UX](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md),
  [SDK](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md)).
- OpenHands described a harness, orchestrator, and control-plane split on
  2026-04-03. Routing, budget, policy, and observability belong in the control
  plane rather than being implicit harness behavior
  ([architecture](https://www.openhands.dev/blog/agent-control-plane)).
- Goose v1.41.0, released 2026-07-03, demonstrates provider, MCP, ACP, desktop,
  CLI, and custom-distribution reach
  ([repository](https://github.com/aaif-goose/goose)).
- Letta's legacy repository points active development to its newer agent
  repository. That migration is a warning against freezing Deepr contracts
  around another project's unstable package surface
  ([repository, accessed 2026-07-10](https://github.com/letta-ai/letta)).
- Grok Bot now documents persistent named Bots, peer handoffs, routines, and a
  shared computer. The same documentation states that the shared computer is
  not a security boundary. Deepr should borrow the observable collaboration
  experience, not the shared authority model
  ([overview](https://docs.x.ai/grok-bot/overview),
  [security](https://docs.x.ai/grok-bot/approvals-security-and-privacy)).
- Grok Bot is now listed as an Agent Plugins client, making manual package or
  MCP installation a real host target. No public Bot lifecycle API is
  documented, so automated creation, routing, takeover, and routine management
  remain outside the implementation target
  ([compatible clients](https://agent-plugins.org/compatible-clients)).
- Grok Build 1.0.6 supports MCP configuration and reusable workflows with
  parallel agents and verification. Its inspected executable version and
  disabled auto-update state must be evidence, and its lack of an exact MCP
  tool filter leaves Deepr authorization authoritative. It is a plausible
  external Deepr host, separately from any eligibility as plan capacity
  ([MCP](https://docs.x.ai/build/features/mcp-servers),
  [workflows](https://x.ai/news/workflows)).
- DeepSeek Harness `dsh-v0.1.1-rc.2` makes capabilities profile-composed
  plugins and reconstructs resume, fork, search, replay, and UI views from an
  append-only session log. Deepr should adopt the narrower host-profile and
  projection seams, not the general plugin kernel or private-reasoning log
  ([overview](https://deepseek.com/harness/en/),
  [architecture](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.1-rc.2/docs/architecture.md)).
- OpenClaw now documents remote and stdio MCP servers with tool filters and
  distinct sandbox, tool-policy, and elevated-execution controls. NemoClaw
  `v0.0.113` pins OpenShell 0.0.106 for its managed-MCP boundary. Both are
  practical external host targets, not Deepr runtime dependencies, and the
  NemoClaw pair remains reference-only until Deepr validates it
  ([OpenClaw MCP](https://docs.openclaw.ai/gateway/configuration-reference),
  [NemoClaw release](https://github.com/NVIDIA/NemoClaw/releases/tag/v0.0.113)).

## Adopt

### Run-start capability snapshots

Every expert or research run should persist an immutable snapshot of eligible
skills and tools, their sources and precedence, provider and model, capacity
source, auth mode, context mode, approval policy, configuration hash, and
schema versions. This makes run behavior explainable and replayable.

Every child capability set must be a monotone subset of its parent snapshot.
Child creation declares and validates the expected result schema before spawn,
not after an unbounded transcript arrives.

### Settled terminal semantics

Keep `accepted`, `provider_finished`, `verified`, and `settled` distinct. A run
is settled only when it has no active child, queued continuation, retry,
unresolved hold, ambiguous provider attempt, pending artifact commit, pending
verification, or pending learning decision. Completion prose cannot override
that deterministic state.

Control delivery also needs typed `queued`, `rejected`, `pending`, and `missed`
outcomes. Durable result delivery is separate from durable execution.

### Bounded visible output and exact durable recall

Keep model-visible tool and child output bounded while retaining the complete
result as a content-addressed durable artifact. Summaries and compaction are
derived views bound to the exact source hash, never canonical replacements.
Evaluate compaction by later evidence recall and decision quality, not only by
token reduction.

Stall detection should measure progress checkpoints and repeated state, not
elapsed time alone. A long useful step and a short dead loop need different
outcomes.

### Prepared approval artifacts

An approval should bind the exact argv, working directory, model, auth mode,
budget ceiling, intended writes, input refs, expert snapshot, and capability
snapshot. Execution must reject any plan whose hash differs from the approved
artifact. Approval timeout fails closed.

### Steering, follow-up, and fork lineage

Long-running Deepr work should distinguish:

- steer after the current safe tool boundary;
- enqueue after the current run;
- cancel while restoring pending instructions;
- fork from a checkpoint with explicit parent lineage;
- inherit or reduce the parent budget, never silently reset it.

Each instruction records its delivery disposition and deterministic merge
position. A message that misses a child boundary must not be represented as
applied.

### Verified skill candidates

Hermes shows the appeal of learning skills from experience. Deepr should use a
stricter promotion flow:

`experience -> candidate -> isolated replay -> held-out evaluation ->
negative-transfer check -> reviewed approval -> active version`

Skill learning must not directly rewrite canonical expert beliefs.

### Control-plane evidence record

One versioned record should join routing, capacity, budget, policy, trace,
expert snapshot, capabilities, approvals, writes, and verification. It should
answer what ran, where, under whose authority, against which state, at what
ceiling, and with what result.

### Release-evidence manifest

Each release should publish a machine-readable manifest with commit, package
hashes, unit and coverage results, strict type scope, schema validation, docs
consistency, security scans, CI checks, and adapter compatibility.

## Reject or defer

- Reject automatic promotion of self-generated skills or memories.
- Reject one undifferentiated memory shared across users, sessions, channels,
  and experts.
- Reject treating a personal gateway as multi-tenant isolation.
- Reject arbitrary auto-discovered executable extensions.
- Reject plugins that silently override built-in tools or prepared approvals.
- Reject hidden retries or an `--auto` mode that can widen authority.
- Reject hidden telemetry, updates, or trajectory sharing.
- Defer broad messaging, voice, and mobile gateways until identity,
  authorization, privacy, and delivery boundaries are designed.
- Defer a general ACP control center until one narrow research adapter and
  evidence envelope are stable.
- Defer unconstrained subagent fan-out until children inherit bounded budget,
  capability snapshot, trace parent, cancellation, and evidence-merge rules.

## Recommended order

1. Run-start capability snapshots and declared child result schemas.
2. Settled terminal semantics plus typed control-delivery outcomes.
3. Prepared approval artifacts.
4. One control-plane evidence contract with bounded visible output and exact
   durable recall.
5. Progress-based stall detection and compaction-recall evaluation.
6. Steering, follow-up, abort restoration, and fork lineage.
7. Verified skill candidates after the held-out expert acceptance harness.
8. Release-evidence manifest.

This order improves reproducibility and user control before adding more
execution surfaces.
