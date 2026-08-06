# Exceptional expert quality (research, plan, improve)

Status: design + partial implementation (2026-08-05).  
Trigger: live NephMesh / Claude Code validation - consults ran correctly at $0
but felt only "moderately useful": flat confidence, circular sources, generic
local best-practice synthesis, no adversarial depth.

## Research findings (what we learned)

### 1. Correct machinery is not exceptional knowledge

The consult contract worked: local, read-only, no mutation, provenance present.
Usefulness was moderate because the **belief inventory** was shallow:

| Failure mode | Symptom | Root cause |
|---|---|---|
| Confidence looks like trash | Everything ~0.60 | Tertiary trust ceiling on all absorb-file (fixed: secondary default + reclassify) |
| Echo chamber | "Confirms our CRD design" | High share of `nephmesh-intent.md` (project stance fed back as domain truth) |
| Generic best practice | kpt/CRD platitudes | Local synthesis fills holes when primary multi-source depth is missing |
| False empty refuse | Documents: 0 → skip consult | Inventory UX lied (fixed: Claims primary) |
| MCP mid-session miss | Skills load, tools absent | Host install/restart (fixed: install-host) |
| No debate | One-shot council | Product choice; deliberation is a separate surface |

### 2. What "exceptional" must mean (operational)

Not vibes. An expert is exceptional for **agentic development** when:

1. **Primary multi-source domain truth** - official docs, specs, first-party
   tools, multiple independent origins - not project README alone.
2. **Honest effective confidence** - trust ceilings match provenance; raw
   extraction scores are not the UX number agents see without context.
3. **Stance vs truth separation** - project intent is PRIMARY stance; domain
   mechanics are SECONDARY/multi-source. Consults must not conflate them.
4. **Challengeable** - can dissent from the operator's current design, cite why.
5. **Self-improving** - research → plan → absorb/sync → measure → repeat at $0
   local (or explicit plan), with structural + eval gates.
6. **Coding-agent consumable** - handoff-fast, council-at-milestones, actions
   map to CRDs/tests/PRs, not essays.

### 3. Literature / prior Deepr design already points here

- `calibration-and-trust.md`: confidence is not "verified fact"; floors exist
  for a reason; calibration harness still unfinished.
- `expert-fleet.md` pillar 4: $0 local can be *faithful* to sources; the gap is
  **calibration and multi-source depth**, not raw model brand.
- `AGENTIC_BALANCE.md`: meaning is model-owned; side-effects and form are
  deterministic. Quality gates must not become lexical "maturity" theater.
- `bounded-expert-deliberation.md`: one-shot consult is intentional; debate is
  later and bounded.
- Existing loop tools: `plan`, `next`, `discover-gaps`, `route-gaps --execute`,
  `sync --local`, `health-check`, `reflect`, `eval continuity` - **not packaged
  as one exceptional-quality loop**.

### 4. The meta-insight (user)

> The same flow - research, plan, improve - is what Deepr experts themselves
> need to do.

Correct. Exceptional experts are not a one-shot absorb. They are a **maintained
role** with a closed improvement loop and quality scorecard.

### 5. The sharpened ask (user, 2026-08-05)

> An expert is more like using the Distill process to get the latest on topics
> from multiple sources, and the Learny example to talk over all that content
> and get insights and learn from it. Think about it in multiple ways to learn
> and understand more. It is not at all just about facts; it is grounded
> perspective and the latest on it, with insights not just raw content.

This identifies a missing stage, not a missing feature. Deepr can acquire and it
can store, but it has **no reasoning pass between them**, and its one ingestion
path shreds documents into atomic single-sentence claims by construction. That
is why depth does not survive absorb. Design:
[expert-insight-layer.md](expert-insight-layer.md).

## Plan (phased)

### Phase A - Scorecard (structural, $0, ship first)

`deepr expert quality NAME` emits `deepr-expert-quality-v1`:

| Signal | Exceptional direction | Notes |
|---|---|---|
| claim_count | enough domain coverage | not a quality floor alone |
| trust_mix | high secondary+primary share | tertiary-only fleet fails |
| multi_source_share | share of claims with 2+ origins | raises tertiary ceiling honestly |
| circularity_risk | share of claims only from project-intent filenames | high = echo chamber |
| open_gaps | non-zero discovery over time | zero gaps + thin claims = false healthy |
| learning_loops | verified_improvement_count > 0 | structural proof of improvement |
| grounding_assurance | share beyond unverified | when checkers used |

**No semantic maturity verdict.** Scorecard is structural + provenance. Human
or calibrated eval owns "exceptional meaning."

### Phase B - Improve loop command (orchestrate existing tools)

`deepr expert improve NAME --local`:

1. quality scorecard (before)
2. plan curriculum for domain (`expert plan` / gaps)
3. execute bounded fills: route-gaps / sync / absorb primary file packs
4. quality scorecard (after)
5. emit delta + next actions

Hard rules: budget 0 default with --local; no absorb of project-intent as sole
domain source; never claim semantic excellence.

### Phase C - Primary corpus packs (domain packs)

Per expert domain, maintain a **primary source pack** (URLs + local mirrors):

- Meshtastic: official docs CLI/MQTT/config (not project README)
- Nephio: docs.nephio.org architecture/Porch/exercises
- kpt: package/functions docs
- HackRF: readthedocs + product page

Absorb with `--trust-class secondary`. Project intent absorb with
`--trust-class primary` into hybrid only as **stance**, tagged.

### Phase D - Consult modes for coding agents

- `fast`: handoff only
- `challenge`: prompt synthesis to prioritize dissent vs operator design
- `milestone`: full council with long timeout

### Phase E - Calibration + optional plan/frontier escalation

- Run `eval calibrate` when corpus exists
- Escalate synthesis to plan/frontier only when scorecard flags high stakes

## Non-goals

- Lexical "maturity level" that pretends to judge expertise
- Automatic paid research without operator authority
- Making the agent the live control loop
- Claiming local 32b is frontier-equal on open-ended strategy

## Success metrics

1. Coding-agent consults cite **non-intent** primary sources majority of the time
2. Effective confidence distribution not a delta at 0.60
3. `expert quality` circularity_risk < 0.25 for domain pillars
4. At least one verified learning loop per expert per 30 days in active use
5. Challenge-mode consults produce at least one design risk the operator had not
   already written into intent

## Living expert vision (product north star)

Confidence facts are a **substrate**, not the product. The target is closer to a
**Karpathy LLM wiki per expert**: a maintained body of research, notes,
stances, open questions, fail patterns, and elite standards - continuously
updated - that a coding (or research) agent can consult when the operator has
an idea.

### What an elite expert holds (Python example)

Not: 40 bullets at conf 1.0 from one README.

Yes:

| Layer | Contents |
|---|---|
| Canon / docs | Latest stable version surface, PEPs that matter, deprecations |
| Practices | Idioms that survive production, anti-patterns, performance traps |
| Fail patterns | Real breakage modes (packaging, async, typing, GIL myths) |
| Roadmap | What is coming and what is still experimental |
| Sources of truth | Official docs, PEPs, release notes, trusted blogs/trackers |
| Stance | What "elite" looks like; what the expert would reject in a PR |
| Open questions | Gaps the expert knows it does not know |
| History | What changed and when (temporal graph) |

Whale biology is the same shape: primary literature (distillr), field methods,
controversies, measurement limits, open research questions - not a fact dump.

### Idea → expert council (dynamic)

```text
operator idea
  -> expert plan (curriculum / domains)
  -> expert make --local  (or spawn council)
  -> research loop (docs, services, architecture, papers via distillr when allowed)
  -> absorb (trust-classed, multi-source)
  -> digest + memory-card (wiki views)
  -> subscribe + sync (stay current)
  -> quality scorecard + improve
  -> consult / handoff to coding agents
```

Capacity honesty still applies: default $0 local; plan-quota when safe; metered
and distillr only when authority and cost gates allow. Never pretend web
research is free if it is not.

### Derived wiki is regenerable

Per APPROACH.md: digests, EXPERT.md, wiki pages are **derived views**. The
belief store + source packs remain canonical. Exceptional UX is:

1. Rich structured memory (beliefs, gaps, stances, sources, temporal edges)
2. Regenerated wiki/digest that reads like a researched notebook, not a
   confidence ledger
3. Continuous research that updates both

Today `expert digest` is still mostly a belief bullet list. Closing that gap
(sectioned wiki: practices, fail patterns, sources, open questions, stance) is
part of "dramatically better experts."

## Implementation status

Authoritative order and checkpoint: [../plans/living-expert-research-stack.md](../plans/living-expert-research-stack.md).

Verified against code 2026-08-05. Items previously marked done that did not
survive that check are corrected here rather than deleted.

- [x] Trust-class on absorb + file default secondary + corroboration merge
- [x] Claims inventory UX; host install-host
- [x] `expert quality` scorecard CLI
- [x] `expert deepen-plan` (Distill/Learny recipe)
- [x] Wiki-shaped digest partitions (stance / multi-source / secondary / tertiary / sources)
- [x] `expert council-plan` diverse multi-axis roster (scaffold + optional --local)
- [x] Living stack design + plan: [living-expert-research-stack.md](living-expert-research-stack.md)
- [~] `expert improve` orchestrator - exists and registers, but has **no tests**,
  re-enters the CLI through `CliRunner` in production, and its `--execute` path
  invokes `discover-gaps`, which is metered-gated and accepts no `--local`. The
  docstring's "$0 unless `--api`" claim does not hold for that step.
- [~] NephMesh trust reclassify - done as a live re-absorb. There is **no
  `reclassify` command**; do not plan as if one exists.
- [ ] **Next (Step 3.5, blocking):** decide whether absorb routes through the
  source-pack pipeline so corpora can produce typed shapes at all. See
  [expert-insight-layer.md](expert-insight-layer.md)
- [ ] `absorb-okf --trust-class` (a directory absorb path already ships and caps
  every corpus at tertiary 0.60)
- [ ] `expert absorb-dir` batch secondary absorb, with publisher-collapsed origin
  identity so `distinct_origin_count` cannot be inflated (Step 4.1)
- [ ] CLI tests for `quality`, `improve`, `deepen-plan`, `council-plan`
- [ ] Primary source packs + re-absorb NephMesh pillars (operator Distill runs)
- [ ] Challenge consult mode - packet selection first, prompt last (Step 6.3)
- [ ] `expert spawn` (Step 6.1)
- [ ] Distill preflight verifier; printed command rather than Deepr-side
  invocation (Step 5)
- [ ] Fail patterns as a typed shape; revision and `evidence_refs` on the
  existing typed states first
- [ ] Subscriptions seeded from council-plan roles (not from metered `expert plan`)
- [x] Calibration harness - **built and run 2026-06-13**. Result was a
  single-bin degenerate curve; `docs/CALIBRATION.md` currently reads that as
  evidence of quality. Step 8 is now a set of honesty fixes, not a first run.
