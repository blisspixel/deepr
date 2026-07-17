# Expert Next Actions

Status: implemented for v2.34.4, 2026-07-10.

## Problem

Deepr already exposes the pieces of a bounded learning expert: creation,
subscriptions, compiled sync, gap routing, continuity evals, loop status,
metacognitive monitoring, self-model review, and derived memory cards. The
operator still has to know which of those commands matters now. That is a
quality-of-life failure, especially immediately after `expert make` and after a
failed scheduled loop.

A useful expert should not merely expose more controls. It should explain the
smallest next action that improves or repairs its current learning state.

## Current research

The 2026 memory literature warns against treating accumulation as improvement:

- MemoryAgentBench identifies accurate retrieval, test-time learning,
  long-range understanding, and selective forgetting as separate competencies
  that must be evaluated incrementally, not collapsed into one recall score
  ([ICLR 2026 paper page, accessed 2026-07-10](https://mlanthology.org/iclr/2026/hu2026iclr-evaluating/)).
- Memora reports that agents frequently reuse obsolete memory and proposes a
  forgetting-aware metric that penalizes reliance on invalidated state
  ([arXiv 2604.20006, 2026-04-21](https://arxiv.org/abs/2604.20006)).
- Recent on-device work treats retention, sharing, and trust as separate
  budgeted decisions, with provenance gating peer memory
  ([arXiv 2606.25115, 2026-06-23](https://arxiv.org/abs/2606.25115)).
- Anthropic's agent-eval guidance recommends complete trajectories, distinct
  trial analysis, and evaluation-driven development rather than one-shot output
  grading
  ([Anthropic Engineering, 2026-01-09](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).

The product consequence is narrow: Deepr should guide operators from measured
state to a next experiment, but deterministic code must not award a semantic
"Level 5" badge.

## Decision

Ship `deepr expert next NAME` as a `$0`, read-only navigator.

The command emits `deepr-expert-next-v1` and uses only structural evidence:

- canonical claim count;
- presence of an operator-attested expert blueprint;
- open gap count;
- freshness state;
- active contradiction count;
- completed, waiting, and failed expert loop records;
- verifier-passed loop records with accepted changes.

It assigns one operational stage:

- `foundation`: no canonical claims exist;
- `recovery`: freshness is stale or incomplete, or a loop failed;
- `learning`: knowledge exists but no stored loop proves a verifier-passed
  accepted change;
- `maintenance`: the structural learning evidence is healthy.

Stages are navigation labels, not maturity scores. The payload states
`semantic_maturity_verdict=false` and `default_policy_change_allowed=false`.

## Action policy

The command returns at most three ordered actions by default:

1. define the expert purpose and held-out acceptance cases when no reviewed
   blueprint exists;
2. establish a compiled knowledge foundation;
3. inspect failed or waiting loops;
4. refresh stale sources;
5. route high-value gaps;
6. inspect contradictions;
7. establish continuity and monitor evidence;
8. refresh the derived memory card when no repair action is due.

Every action includes canonical argv arrays, a reason, and a stable id. The
human view renders the arrays as JSON instead of inventing a supposedly
portable shell string. Foundation and refresh plans inspect capacity first,
then use the scheduled sync path that waits instead of falling through to
metered use. The navigator never runs those commands, mutates state, calls a
model, or spends money.

## Agentic boundary

Workflow code may determine that a claim count is zero, a loop failed, or a
freshness deadline passed. It may route those facts to a safe command. Workflow
code may not conclude that the expert is wise, accurate, mature, coherent, or
improved. Those are semantic judgments that require human or calibrated-model
evaluation with before and after evidence.

## Verification

- Empty experts receive a capacity check followed by a scheduled compiled-learning path.
- Experts without an operator-attested blueprint receive a purpose-definition action
  before knowledge accumulation.
- Failed or waiting loops outrank new work.
- A verifier-passed accepted change is required before the navigator describes
  the expert as being in maintenance.
- JSON output validates against the published schema.
- A real CLI filesystem snapshot proves that the command is read-only and costs `$0`.

## Follow-up

Add forgetting-aware and negative-transfer evals before any structural signal
is allowed to change default learning policy. The next eval should test whether
new learning preserves previously correct answers, stops using invalidated
beliefs, improves held-out consults, and avoids harmful context competition.
