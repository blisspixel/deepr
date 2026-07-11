# Agent Harness Lessons for Deepr

Status: researched roadmap design, 2026-07-10. Nothing in this document is
shipped merely because it is described here.

## Goal

Deepr should learn from current agent harnesses without becoming a generic
coding-agent shell or widening ahead of its research-verification loop. The
useful question is not which harness to copy. It is which proven interaction
and control patterns make expert research more reproducible, steerable, and
safe.

## Current landscape

- Hermes Agent v0.18.1, released 2026-07-07, combines persistent recall,
  scheduling, isolated subagents, skill creation, and multiple execution
  backends behind one personal-agent gateway
  ([repository](https://github.com/NousResearch/hermes-agent),
  [release](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.7.7)).
- OpenClaw 2026.6.6, released 2026-06-12, emphasizes an always-on local
  gateway, scoped skills, session snapshots, device pairing, sandboxing,
  prepared approvals, fail-closed execution, and release-integrity evidence
  ([repository](https://github.com/openclaw/openclaw),
  [security model](https://github.com/openclaw/openclaw/blob/main/docs/gateway/security/index.md),
  [skills](https://github.com/openclaw/openclaw/blob/main/docs/tools/skills.md),
  [release](https://github.com/openclaw/openclaw/releases/tag/v2026.6.6)).
- Pi v0.73.1, released 2026-05-07, keeps the harness composable across model
  APIs, core loop, TUI, SDK, and JSON-RPC. Its session model distinguishes
  steering from follow-up input and supports abort recovery, trees, and forks
  ([repository](https://github.com/earendil-works/pi),
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

## Adopt

### Run-start capability snapshots

Every expert or research run should persist an immutable snapshot of eligible
skills and tools, their sources and precedence, provider and model, capacity
source, auth mode, context mode, approval policy, configuration hash, and
schema versions. This makes run behavior explainable and replayable.

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
- Reject hidden telemetry, updates, or trajectory sharing.
- Defer broad messaging, voice, and mobile gateways until identity,
  authorization, privacy, and delivery boundaries are designed.
- Defer a general ACP control center until one narrow research adapter and
  evidence envelope are stable.
- Defer unconstrained subagent fan-out until children inherit bounded budget,
  capability snapshot, trace parent, cancellation, and evidence-merge rules.

## Recommended order

1. Run-start capability snapshots.
2. Prepared approval artifacts.
3. One control-plane evidence contract.
4. Steering, follow-up, abort restoration, and fork lineage.
5. Verified skill candidates after the held-out expert acceptance harness.
6. Release-evidence manifest.

This order improves reproducibility and user control before adding more
execution surfaces.
