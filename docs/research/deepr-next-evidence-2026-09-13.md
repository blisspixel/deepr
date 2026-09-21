# Deepr's next evidence milestone

Sequencing note, 2026-09-20: this remains the rationale for the S0 baseline.
The [active roadmap](../../ROADMAP.md#active-release-plan) now places default
preparation, durable temporal learning, and perspective synthesis before wider
authority. Future version assignments below describe the September 13 plan;
current delivery contracts are in [S0-S5](../plans/living-expertise.md).

Deepr should finish v2.51: measure whether maintaining one expert improves
recurring decisions enough to justify its maintenance and review effort.
Its distinctive promise is durable, revisable judgment with inspectable
evidence. The code already persists much of the needed state, but persistence
is not evidence of better decisions. Expanding providers, runtime control, or
autonomous learning before this comparison would leave that uncertainty intact.

This assessment checks the README, active roadmap, governing contracts, and
relevant implementation against primary evidence available on September 13,
2026. It is a planning assessment, not a completed experiment or a finding of
improved expert quality. The active release order remains in
[ROADMAP](../../ROADMAP.md#active-release-plan); this document explains the
evidence and does not create a competing backlog.

## What should happen next

| Order | Concrete result | Why it earns the work | Evidence required to finish |
| --- | --- | --- | --- |
| Immediate safety correction | Refuse Claude plan execution before account or subprocess work | Current safe mode preserves managed-policy commands, invalidating complete confinement | Production-adapter refusal tests, automatic-routing refusal, preserved dormant transport tests, accurate current docs |
| Next v2.51 increment | Equal neutral source inventories in isolated arm roots, followed by exact blinded answer bindings | Nested-source verification exists; what each arm actually receives and what each reviewer actually scores remain separate gaps | Source hashes, no organizer/future-world inputs, explicit model and memory bindings, one-to-one case/world/answer mapping, failure and cancellation fixtures |
| v2.51 experiment | One same-model, four-arm local pilot across three worlds and 12 cases | This directly tests the contribution and risks of maintained state | Forty-eight terminal cells, complete failure denominators, frozen review labels, separate quality/harm/effort results, reconstruction from artifacts |
| Evidence-led follow-up | Repair the observed failure or replicate a promising result on a new held-out history | Repeated tuning on the same cases can manufacture an apparent benefit | Regression evidence plus fresh held-out evaluation; no default changes on the pilot alone |
| v2.52 and later | Grounded prediction resolutions as review-required proposals, then the existing transaction and host gates | Outcome interpretation and remote authority depend on trustworthy measurement | Original prediction and later evidence bindings, preserved temporal reconstruction, reviewed changes with held-out benefit |

An operationally valid negative pilot is useful. It can show that maintenance
adds no useful benefit, that false support offsets a correctness gain, or that
review overhead dominates the value. Such a result should redirect the next
increment without being marketed as an improvement.

## What the repository review found

The README is strongest where it explains recurring use and gives a complete
retain, study, brief, and consult path. It correctly separates inspectable
records from demonstrated learning. The active roadmap also has a coherent
dependency order. The main editorial problem was inconsistency deeper in the
documents: completed nested-source preflight was still grouped with unfinished
preparation, and the approach thesis could read as established superiority.
Those descriptions are corrected in this change.

The remaining gap is specific. `eval expert-value-sources` verifies actual
nested bytes, source-version continuity, and declared cutoff ordering. Its
report correctly does not claim runnable arms, isolation, blinding, or semantic
quality. The generic value evaluator can aggregate unblinded descriptive
reviews and hashes a review-assignment artifact without verifying the mapping
inside it. That generic behavior is useful and need not be removed. v2.51
needs additional saved evidence that its stricter blinded protocol was followed.
See the [source preflight](../design/source-world-preflight.md) and
[repository gap analysis](product-direction-evidence-2026-09-13.md#top-three-repository-gaps).

The first rehearsal already has a useful arm policy. Fresh research rebuilds
local study and briefing per case. Static history keeps raw cumulative sources.
The compiled expert stays at its world-1 checkpoint. The maintained expert
starts from that same checkpoint and updates before later worlds. Final answers
receive the same complete current-world source packet. This isolates the
effect of state under the selected model while avoiding a small-fixture
retrieval-access confound. It cannot establish retrieval scalability or a win
against frontier web research. Preserve the
[local rehearsal policy](../design/local-four-arm-rehearsal.md).

## What the latest evidence changes

Memory quality needs more than recall. Memora studies repeated changes and
obsolete-memory reuse; MemoryArena tests later tasks that depend on earlier
experience. Together they motivate measuring whether remembered information
supports the right action under a changed world. They do not imply that all
memory helps or all memory harms. LongMemEval-V2 adds useful premise-awareness
and dynamic-state cases, but remains a work in progress with a narrower task
than Deepr's product claim.
[Memora](https://arxiv.org/abs/2604.20006),
[MemoryArena](https://arxiv.org/abs/2602.16313),
[LongMemEval-V2](https://arxiv.org/abs/2605.12493).

Resource accounting can change the conclusion. A study revised August 30,
2026 compares online memory and skill modules with an actor receiving the
same total inference-token budget. Its reported benefits often disappear
against that stronger baseline. The setting is web agents, not Deepr, so it
does not settle this project question. It does show why equal answer limits
are insufficient: record preparation and maintenance computation, retries,
and review effort separately. A local pilot with zero API dollars still has
real time and hardware costs.
[Budget-constrained web-agent study, v2](https://arxiv.org/abs/2606.15017v2).

The newest memory findings warrant targeted probes. The August compaction
study and September model-portability study raise distinct risks: information
can degrade during repeated compression or become harder for a replacement
model to use. Preserve raw source history and bind the effective writer,
reader, model digest, context, and preprocessing policy. Do not add a new
memory backend on the strength of those papers; their tasks and tested models
are limited.
[Compaction study](https://arxiv.org/abs/2608.22752),
[model-portability study](https://arxiv.org/abs/2609.05339).

Review quality is itself measurable. The August 31 rubric-artifacts paper
reports cases where judgment can follow rubric signals instead of the intended
answer evidence. An opaque answer id therefore cannot certify an unbiased
review. Use a separate calibration set, preserve reviewer disagreements, and
record suspected arm inference before revealing the key. Human-anchored review
remains necessary before model labels affect defaults.
[Rubric-artifacts study](https://arxiv.org/abs/2609.02942),
[full evaluation evidence and limitations](memory-evaluation-evidence-2026-09-13.md).

Current product comparisons reinforce the same distinction. Letta's July 28
evaluation separates memory use from memory generation, while its August SDK
emphasizes persistent operation across clients. LangChain similarly describes
capturing experience, selecting useful updates, and ensuring later runs load
them. These are useful workflow lessons, not independent evidence that Deepr
should adopt those products or change its canonical storage.
[Letta evaluation](https://www.letta.com/blog/evaluating-memory-in-production-agents/),
[Letta SDK](https://www.letta.com/blog/introducing-the-letta-agent-sdk/),
[LangChain memory guidance](https://www.langchain.com/blog/how-to-give-your-agent-memory).

## The capacity finding that needs immediate action

Claude Code's current CLI documentation explicitly preserves managed-policy
hooks in safe mode. Session-start hooks execute independently of model tool
selection, and lower-precedence settings cannot disable managed hooks. Deepr's
previous adapter combined safe mode with empty model tools/MCP, a sanitized
environment, and a live paid-overage check, but did not confine these independent
commands. The production adapter is now blocked. This correction does not
claim that a hook was present on any particular machine or that an exploit
was executed.
[CLI contract](https://code.claude.com/docs/en/cli-reference),
[hook contract](https://code.claude.com/docs/en/hooks),
[decision and restoration requirements](../design/claude-managed-policy-containment.md).

OpenRouter's newer workspace budget option can include BYOK, but its official
documentation still permits in-flight requests to finish beyond the budget.
That does not prove a hard total liability cap. Keep its current preview and
offline reconciliation posture. A renamed usage-credit feature or a new
configuration knob is not provider-account proof and cannot authorize paid
dispatch.
[Workspace budget contract](https://openrouter.ai/docs/guides/features/workspaces/workspace-budgets),
[runtime and capacity evidence](runtime-capacity-evidence-2026-09-13.md).

MCP, portable plugins, and durable workflow engines remain later integration
tools. Protocol support does not demonstrate correct expert judgment, an
installed skill does not supply execution confinement, and a retryable step
does not make an external effect exactly once. The existing release sequence
already gives these concerns a place after value measurement and authority
proof. There is no evidence-driven reason to widen that sequence now.
[MCP release](https://blog.modelcontextprotocol.io/posts/2026-07-28/),
[Agent Skills specification](https://agentskills.io/specification),
[durable workflow rules](https://developers.cloudflare.com/workflows/build/rules-of-workflows/).

## Current protocol and package compatibility

Current MCP and Agent Plugins compatibility is part of this work, independent
of later host-control expansion. MCP `2026-07-28` is the published modern
protocol; Deepr also retains its documented legacy eras. Agent Plugins `1.0.0`
is published, while `1.1.0` is a working draft. A draft is useful preparation
evidence and does not silently replace the package's supported contract.
[MCP release](https://blog.modelcontextprotocol.io/posts/2026-07-28/),
[Agent Plugins specification](https://agent-plugins.org/specification).

The compatibility audit checks the actual pinned schema bytes and repairs
concrete supported-path defects: legacy MCP ping, invalid JSON-RPC request
envelopes, plugin optional-field validation, single-pass placeholder expansion,
and plugin-root-relative working directories. Published and draft contracts,
packaging conformance, installed stdio behavior, and certification by an
external host are separate claims. Exact evidence and limitations are in the
[MCP audit](mcp-compatibility-evidence-2026-09-13.md) and
[Agent Plugins audit](agent-plugins-compatibility-evidence-2026-09-13.md).

## A bounded improvement loop

Freeze the experimental question and constraints before collecting answers.
The immediate question is whether maintained state improves paired decision
correctness or reduces human effort under one local configuration without
unacceptable stale reuse, false support, or negative transfer. The accountable
reviewer must define practically meaningful benefit and harm thresholds before
seeing the results. This assessment does not invent those attestations.

Complete source materialization and blinded binding using synthetic development
fixtures. Keep the organizer mapping and rubric outside worker inputs. Preserve
exact answer bytes; if a neutral display wrapper is necessary, hash the wrapper
and its binding separately. Record blocked, failed, and answered cells, including
failed maintenance that falls back to the last completed checkpoint. File
hashes establish byte identity, not truthful sources or actual reviewer identity.

Run and review the frozen 48 cells through proven local capacity, then stop
collection. Do not keep adding trials until a favorable result appears. Twelve
cases across three related worlds are a pilot; the 48 arm cells are not 48
independent cases. Report paired case deltas, world trajectories, and the
limitations of existing case-bootstrap intervals. Separate replicated runtime
variation from new independent domain evidence.

Choose one next change from the observed failures. A source passage lost from
context calls for a context-assembly fix. Retaining a reversed claim calls for
inspection of update and invalidation behavior. Disagreement about factual
support calls for better reviewer calibration. Preserve a used pilot as
development evidence and use a fresh held-out history before claiming a learning
policy improved the system. This loop is finite, inspectable, and can make
progress without granting automatic belief, prompt, skill, or routing writes.

## Spending and evidence limits

The authorized ceiling for this effort is $10, not a target to consume. The
repository's no-paid-API rule remains binding, and active examples keep their
existing $5 monthly maximum. Research, fixtures, and offline tests here do not
authorize paid inference. Hosted services, underlying conversation/agent
billing, and local electricity are separate costs; this repository cannot
measure or cap them through its application ledger. No all-inclusive $10
billing guarantee is claimed.

No pilot was executed or semantically reviewed for this assessment. No answer
key, reviewer identity, held-out benefit, production account control, or source
historical-availability proof was fabricated. The supporting notes contain
source dates, version status, direct links, and applicability limits:

- [Memory and evaluation evidence](memory-evaluation-evidence-2026-09-13.md)
- [Product direction and repository gaps](product-direction-evidence-2026-09-13.md)
- [Runtime and capacity evidence](runtime-capacity-evidence-2026-09-13.md)

Validation results for the implementation belong in the accompanying
[verification record](../validation/research-review-2026-09-13.md), separate
from experimental quality evidence.
