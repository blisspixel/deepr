# The expert library: a roster of always-fresh domain experts agents consult as a team

Status: design / vision note, 2026-06-20. Grounded in a live validation this
session (see PROGRESS-LOG). Cross-cuts the expert system, capacity waterfall, and
MCP/A2A surfaces. Read [AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) and the
ROADMAP Planning Principles first - this note must not turn deepr into an
orchestrator; it sharpens deepr's role as the *knowledge layer*.

## The shift: the cost floor is gone

A Deepr expert is not a chat persona - it is durable, calibrated epistemic state
(beliefs with confidence, provenance, recency, gaps, contradictions). Historically
the reason you wouldn't keep *dozens* of such experts perpetually current is
cost: every refresh is a research call.

This session removed that floor. Proven live, end to end, at **$0.000**:

- **Create** an expert: `expert make --local` (provider-free profile).
- **Populate** it with sourced, calibrated beliefs: `expert sync --local
  --fresh-context` - free `ddgs` web search + a local Ollama model + the
  comprehensive first-sync baseline. Fifteen experts, 13-25 grounded beliefs
  each, all $0.
- **Keep it current**: delta `sync` (only what changed), schedulable, $0 on local
  or prepaid plan capacity (`capacity admit-plan`).
- **Consult** it: MCP `query_expert`, `health-check`, `what-changed`, `why`,
  versioned handoff - the agent-facing surface already exists.

So the unit of value flips from *one* expert to a **library**: a roster of
domain experts maintained for ~nothing, that any agent can consult - individually
or as a **team assembled per question**. That is the interesting thing.

## Why this matters for agents

Host agents (Claude Code, Copilot, Cursor, the autopilots) have ephemeral context
and shallow memory. A Deepr expert library is the durable, shared, *verified*
epistemic layer underneath them:

- **Discoverable**: `list_experts` / handoff tells an agent which domains exist.
- **Consultable as a team**: a cross-domain question fans out to the relevant
  experts and comes back synthesized, each claim carrying provenance and a
  trust-floor-capped confidence.
- **Always current**: the roster self-maintains on owned/prepaid capacity, so an
  agent that checks back next week gets a `what_changed` delta, not stale data.
- **Portable and owned**: experts are local files (OKF export, SKILL.md export);
  the knowledge moves with you across tools and vendors.

## What exists vs what to refine

| Capability | Today | Refinement |
|---|---|---|
| Create / populate / refresh at $0 | yes (local + free search + plan-quota) | - |
| Per-expert maintenance | yes: `sync`, `health-check`, `route-gaps`, `reflect` | **Library-wide** maintenance in one pass |
| Consult one expert | yes: MCP `query_expert`, `chat` | - |
| Consult several experts | `~` `/council` inside chat; `council.py` | A first-class **team-assembly** surface |
| Pick the right expert(s) for a question | no caller chooses | **Expert routing** (relevance selection) |
| Discovery for agents | yes: `list_experts`, handoff, SKILL export | A single "consult the library" MCP verb |

The two gaps that turn "a pile of experts" into "a team an agent engages
dynamically" are **expert routing** (which experts are relevant to a question)
and **library-wide maintenance** (keep the whole roster fresh in one scheduled,
capacity-aware pass). Both are compositions of parts that already exist.

## Proposed refinements (sequenced, each bounded)

1. **Library-wide maintenance** - `deepr expert sync-all` / a roster loop that
   runs each due expert's maintenance through the capacity waterfall (local ->
   plan -> metered), respecting per-expert budgets and skip-not-fail, and emits
   one roll-up `ExpertLoopRun`. Closes "keep them all up to date" with a single
   schedulable command. Reuses `choose_maintenance_backend` + the existing sync
   loop; no new execution machinery.

2. **Expert routing (relevance selection)** - given a question, score each
   expert's domain/manifest for relevance and return the top-k. Deterministic
   prefilter (lexical/embedding over expert descriptions + claim coverage) that
   *routes into* a model confirmation, never a brittle lexical *verdict*
   (AGENTIC_BALANCE: a cheap check may route but never conclude). Output is a
   ranked, explainable shortlist.

3. **Team assembly = routing + bounded council** - `deepr expert consult
   "<question>"` (and an MCP `consult_library` verb): route to the relevant
   experts, run the existing bounded `council.py` across them with a budget
   contract + trace IDs, synthesize a handoff-ready answer that cites which
   expert contributed what. Bounded fan-out, no unbounded swarm; deepr remains a
   role on the team, not the orchestrator. This is the dynamic-team primitive.

4. **Roster freshness economics** - default library maintenance to local/plan
   capacity (`admit-plan`), so N experts stay current at ~$0 marginal; metered is
   reserved for interactive/high-priority. Surfaced in `capacity fleet` /
   loop-status so the operator can see "the whole roster is fresh, $0 this week."

5. **Trust at roster scale** - continuity metrics, source-trust floors, and
   contradiction surfacing already apply per expert; expose a library roll-up so
   an agent can weight experts by calibrated reliability when composing a team.

## Boundaries (so this stays deepr's role, not an orchestrator)

- Team assembly is a **bounded council** that returns one handoff artifact - the
  host agent still owns the outer workflow (ROADMAP non-goal: not the orchestrator).
- Routing/selection is model judgment over a deterministic prefilter, calibrated;
  spend, writes, and capacity stay deterministically gated.
- Every consulted claim keeps provenance and a trust-floor-capped confidence; the
  library never emits unsourced authority.
- Auto-maintenance only on capacity the operator opted into (local admission,
  `admit-plan`); no surprise bills at roster scale.

## Relationship to the roadmap

This is the connective tissue over Phase 4 (expert intelligence), Phase 4c
(Expert Crews - a *named, exportable* team; library routing is the *dynamic,
per-question* counterpart), Phase 6 (capacity - what makes roster upkeep free),
and Phase 2 (MCP/A2A - how agents consume the library). Crews are the curated,
shippable team; the library + routing is the ad-hoc team assembled on demand.
