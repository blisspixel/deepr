# Diverse expert councils (meaningful multi-perspective review)

Status: design + CLI shipped (scaffold + optional --local composition), 2026-08-05.  
Plan order: Step 3 in [../plans/living-expert-research-stack.md](../plans/living-expert-research-stack.md).  
Parent: [exceptional-expert-quality.md](exceptional-expert-quality.md).

CLI: `deepr expert council-plan [GOAL] [--from-file PATH] [--local] [--roles N]`

## Problem

Default expert selection optimizes for **domain similarity** ("this question is
about Kubernetes, pick Kubernetes experts"). That produces thin, correlated
perspectives.

Operators often want something different: a **mock team with adversarial and
outsider lenses** reviewing a README/roadmap, for example:

- PhD computer scientist (rigor, claims, evaluation)
- DoD network analyst (adversary model, degraded ops)
- Black Hat-style security researcher (abuse cases, threat model honesty)
- Telecom architect (carrier-grade, standards, scale)
- Extreme prepper / field resilience user (off-grid reality, UX under stress)

Those are not "five copies of Mesh Expert." They are **diverse axes**. Without
diversity, consults restate the project narrative plus generic best practice.

## Product intent

Given an idea, README, or roadmap text, Deepr proposes a **council roster** that:

1. Covers the domain **and** at least several non-obvious axes
2. Names each role, domain description, perspective lens, and dissent style
3. Emits `expert make --local` commands
4. Emits per-role `deepen-plan` queries (what each would research)
5. Emits a **challenge consult** question for README/roadmap review
6. Does **not** auto-spend or auto-absorb until the operator runs those steps

Composition is model judgment when local/plan capacity is available; structure
and diversity constraints are deterministic gates (AGENTIC_BALANCE).

## Diversity axes (deterministic checklist)

A valid council plan for project review must include roles spanning **at least
four** of these axes (not necessarily with these titles):

| Axis | What they protect against |
|---|---|
| Domain practitioner | Missing core technical truth |
| Adversary / red team | Missing abuse, threat, failure under attack |
| Ops / reliability | Missing runbooks, degraded mode, observability |
| Standards / institutional | Missing regulation, carrier, compliance reality |
| Extreme end-user | Missing field UX, off-grid, non-lab constraints |
| Scientific rigor | Missing evaluation, overclaim, unfalsifiable marketing |
| Economic / adoption | Missing who pays, who runs it, who walks away |
| Historical / lineage | Missing prior art, reinventing known dead ends |

"Five Meshtastic experts" fails the axis check even if names differ.

## Outputs

Schema: `deepr-expert-council-plan-v1`

```text
goal
axes_covered[]
roles[]:
  name
  domain_description
  axis
  perspective_lens   # how they read the problem
  dissent_style       # what they attack in a review
  make_description    # -d for expert make
  deepen_query        # for expert deepen-plan --query
  existing_expert     # optional match if already in store
consult_prompt        # full challenge question for README/roadmap
next_operator_steps[] # ordered
capacity_posture
```

## Capacity

| Mode | Behavior |
|---|---|
| `--local` | Prefer Ollama to invent concrete roles for the goal; $0 API |
| `--plan claude` | When executable and overage-off proven |
| No model | Structural scaffold of axes + placeholders; honest that names are templates |

Never invent that a diverse council ran when only a scaffold was emitted.

## Relation to consult

Today `expert consult` is one-shot, no cross-talk between experts. That stays.
Diversity improves **input perspectives**, not multi-turn debate.

Bounded multi-turn deliberation remains a separate design
([bounded-expert-deliberation.md](bounded-expert-deliberation.md)).

## Operator order (runtime)

1. `deepr expert council-plan --from-file README.md --local`
2. Review axes_covered
3. `make --local` each role (or reuse existing_expert)
4. `deepen-plan` + Distill no-metered + absorb secondary for critical roles
5. `consult "<consult_prompt>" -e ... -e ... --local`
6. Apply README/roadmap edits from agreements + dissent

## Non-goals

- Replacing human judgment with "the prepper said so"
- Autonomously creating and learning five experts without confirmation
- Lexical "diversity score" as a quality gate for content meaning
- Requiring paid API for composition when local is available
