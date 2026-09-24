# Coordination failures and cheap routing

Status: research note, 2026-09-23. Not shipped capability. This review does not
move the [active release plan](../../ROADMAP.md#active-release-plan). Parallel
reading may record a refusal; it may not widen consult routing, host runtimes,
or capacity classes ahead of v2.51.

## Sources

- OPENRIG, "I Run an AI Civilization in Herdr", 18 September 2026,
  [video](https://www.youtube.com/watch?v=AL-PQuB2wy0) and
  [written argument](https://www.openrig.dev/blog/agent-civilizations).
  The video description also names later chapters on context as world-building,
  distributed context, refocus, mind viruses, and agent productivity monitoring.
  Those titles are not a specification. The post is the citable argument.
- [Herdr](https://herdr.dev/): a terminal runtime. Existing coding-agent
  sessions keep running across machines. Herdr classifies a pane as working,
  blocked, done, or idle. It does not replace the agent.
- [OpenRig](https://www.openrig.dev/): a local control plane for ordinary
  Claude Code, Codex, and Pi sessions. Seats outlive sessions. Pods share a
  context domain. Handoffs, context packs, and mission scope are explicit.
- LangChain, "Building a Harness with Jev", 17 September 2026,
  [post](https://www.langchain.com/blog/building-a-harness-with-jev) and
  [video](https://www.youtube.com/watch?v=VE5dsWll06M).
- TypeSafe, "Introducing System One Models & Jev", 15 September 2026,
  [post](https://typesafe.ai/blog/introducing-system-one-models-and-jev).
  Jev is an early-access hosted model: program state in, typed choice, score,
  and yes/no probabilities out, with no generated text. TypeSafe reports about
  200x speed and 400x cost against LLMs on its own workflow evals, and says
  those multiples are the high end, the workflows were written by its team, and
  the reference answers are other vendors' models. Pricing sustainability is
  unproven on their own account.
- Open substitutes, inspected as repositories rather than as Deepr dependencies:
  [system-one-adapter](https://github.com/typesafe-ai/system-one-adapter-python)
  (MIT, calls OpenAI, Anthropic, or Gemini through the TypeSafe question
  shape), [system-one](https://github.com/sgoedecke/system-one) (local
  single-forward-pass classification over an open chat model), and
  [open-jev](https://github.com/kyegomez/open-jev) (a PyTorch sketch with
  random weights, explicitly not the production model).

## What Deepr already is

Deepr is one role on a larger team. An external harness owns chat, terminals,
computers, and cross-project decomposition. Deepr owns the expert's beliefs,
the investigation plan, the capacity envelope, and the evidence
([external harness bridge](external-harness-investigation-bridge.md)).

The consultable team is already a bounded fan-out. `ExpertCouncil` selects a
roster, reads stored packets, allows zero peer turns, and makes at most one
synthesis call. Automatic breadth defaults to 3 and caps at 10. Keyword overlap
is a high-recall selector. `deepr route explain` and `deepr route collapse` are
`$0` inspections. A trained gate over that roster is already refused until
v2.51 produces usable evidence
([mixture note](mixture-of-experts-and-deepr-experts.md)).

Spend, tool permission, and memory writes stay deterministic. A probability is
not authority
([agentic balance](../plans/AGENTIC_BALANCE.md)). Peer packets cannot authorize
tools, spend, or factual writes. An upstream "verified" label grants no local
authority
([semantic firewall](epistemic-interchange-and-semantic-firewall.md)).

Purpose is an operator-attested blueprint. An investigation charter binds one
question to one expert domain. Global cheapest-first routing is an explicit
non-goal: on 2026-06-11 an unverified improvement loop routed work onto a nano
model.

## Diagnoses worth keeping

These are names for failures Deepr already has machinery for. They are not new
subsystems.

- **Scope inflation.** A locally reasonable next step leaves the original
  decision, and the chain ends somewhere nobody asked for. The stop is the
  attested purpose, the immutable plan, and a typed stop condition.
- **Split-context approval.** The worker holds the details and the approver
  holds the mission, so each half says yes. Prepared approvals already bind the
  exact action, budget, and writes. A second model that only returns "probably
  safe" splits the picture again.
- **Peer contagion.** "Other agents are already doing it" is not evidence.
  Taking a goal from a neighboring seat is the same failure as trusting an
  upstream verified label. Candidate-only admission is the firewall.
- **Refocus.** After compaction, the seat has to see the original mission
  again. OpenRig owns that reload. Deepr's job is to hand back the expert's
  purpose, freshness, gaps, and citations in a section the seat can store.
- **System One shape.** Many typed questions, a probability, and an abstain
  path match how Deepr already wants calibrated model judgment to look. The
  classifier that asks those questions can live in the host. Deepr answers
  with a routing card the host can score.

## Work alongside a fleet and an external router

Herdr and OpenRig stay outside Deepr. A seat inside them should still be able
to call Deepr as the specialist, the way it calls any other MCP server. Jev, or
a local classifier in that harness, stays the host's router. Deepr does not
call it, and Deepr does not drive `rig_*` tools.

Three gaps were closed without widening the ten-tool read-only profile:

- That profile still lists capabilities, roster, status, and search, and it
  still omits consult. `DEEPR_RESEARCH_MODE=seat` is the separate allowlist:
  local consult, handoff, what-changed, belief explanation, and
  `deepr_route_explain`. Research dispatch, absorb, skill install, and metered
  reflection stay denied.
- `deepr_capabilities` no longer names Claude as an executable `$0` plan.
  `prepaid_plans` is empty and `blocked_plan_synthesis.status` is
  `execution_blocked`. Offline conformance requires that.
- `deepr_expert_handoff` adds `context_section`. An operator-attested blueprint
  supplies the mission and decision questions. A missing or unreadable
  blueprint is labeled. The section's authority flags stay false.

The profile is `deepr mcp seat-profile`. In seat mode, consult and query refuse
`plan` and `api` before a provider client or consult transaction is created.
`deepr_route_explain` returns the existing `$0` card: candidates, overlap, and
capacity class. Overlap remains a hint. A host classifier may abstain or
escalate. It cannot change Deepr's default, and Deepr does not treat that
probability as permission.

Herdr and OpenRig can be named as unvalidated consumers of that profile.
Pinning a host version and claiming support stays the existing v2.54 evidence
rule. No new runtime joins Deepr.

## Refusals

- Herdr is a terminal host and OpenRig is a seat control plane. Neither is a
  runtime to rebuild inside Deepr. Experts do not gain processes, terminals,
  filesystems, or subagents. Live research agents do not become a civilization.
  The team surface remains bounded council consult over stored packets.
- Jev does not become a provider, a model router, an expert-roster gate, a
  tool-risk gate, or an eval judge. It would be a new metered API, admitted on
  vendor-built evals, able to downgrade the model or bless a tool call.
- The open substitutes do not become that router either. The adapter still
  calls a metered chat API. The local single-pass classifiers are uncalibrated.
  Random-weight sketches are not a model. Any of them choosing a cheaper
  synthesis model, a roster, a tool, or a belief write is the 2026-06-11
  degradation loop with a new name.
- Routing defaults, learning policy, and capacity classes stay where they are
  until v2.51 evidence exists.

## Consumers of one contract

These hosts call the same seat profile. None is certified by generating the
profile. Open-source seats and commercial harnesses are the same kind of
caller: a process that speaks MCP and must not receive spend tools.

| Host | Class | Role |
| --- | --- | --- |
| OpenRig | Open source | Control plane for ordinary coding-agent seats |
| Herdr | Open source | Terminal runtime those seats keep running in |
| OpenClaw | Open source | Gateway. Its pinned profile remains the ten-tool read-only reference |
| OpenCode | Open source | Coding harness |
| Goose | Open source | Coding harness |
| Pi | Open source | Coding harness |
| Hermes | Open source | Personal-agent gateway |
| DeepSeek Harness | Open source | Coding harness |
| Claude Code | Commercial | Coding harness. Plan execution stays blocked |
| Codex | Commercial | Coding harness. Plan execution stays blocked |
| Cursor | Commercial | Coding harness |
| Grok Build | Commercial | Coding harness and workflow host |

NemoClaw's managed remote MCP does not launch this stdio profile. That remains
a separate gate. A host-side classifier, including a local open-weight
stand-in for Jev, may read `deepr_route_explain` and `deepr_capabilities`.
Deepr does not call that classifier.

## Roadmap effect

The active sequence remains the living-expertise plan: preserve the value
baseline, then prepare consultation before widening autonomy. The seat profile
is a patch on that sequence. It removes the measured limitation that a safe
install could list experts and could not ask them, and that the capability
card advertised a blocked plan as executable. Named-host certification stays
deferred until a pinned host version has `$0` evidence. Host observation,
remote control, and workspace evidence stay on the deferred list.

A later selector comparison inside Deepr, if one is ever justified, stays the
mixture note: local, write-free, abstaining, and scored as selection recall
against keyword overlap. An external classifier may read the routing card
before that comparison exists. It cannot move a default, a dollar, or a tool
boundary.
