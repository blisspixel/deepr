# Living expert research stack (Distillr + Learny + plan-quota + TKG)

Status: design + active implementation, 2026-08-05.
Parent: [exceptional-expert-quality.md](exceptional-expert-quality.md).
Implementation plan: [../plans/living-expert-research-stack.md](../plans/living-expert-research-stack.md).
Integrations baseline: [INTEGRATIONS.md](../INTEGRATIONS.md).

## Operator ask (compressed)

When I have an idea, spin up experts that actually know the field: latest docs,
services, architecture, papers. Wiki-depth second brain per expert (Karpathy
style), tied to the temporal knowledge graph. Prefer membership plan CLIs
(Claude Code, Codex, Grok, Antigravity, …) or local LLMs so marginal spend is
$0 API credits. Distillr and Learny should feed that depth.

## What Distillr is (latest, local repo)

**Distill** (PyPI `distillr`, CLI `distill` / `distill-mcp`, active beta ~0.19.x)
is a **persistent research corpus engine**, not a one-shot chat report.

Pipeline (same shape for every source):

```text
capture -> analyze -> verify -> synthesize -> audit
```

Sources: YouTube, websites (trusted-site expansion), arXiv papers, X, GitHub
repos, podcasts, newsletters/feeds, local files. Goal-aware discovery
(`distill discover` / `papers` / `site` / `latest`). Output is a **local
`library/` of plain Markdown** with per-source insights, receipts, and
cross-source synthesis. Query via `distill ask`, MCP, or read files in Obsidian.

Positioning (their docs): acquisition half of the LLM-wiki pattern. NotebookLM
and chat Deep Research do not leave a compoundable, receipted corpus you own.
Distill finds sources, keeps provenance, and refreshes on a cadence.

### Why Distillr is interesting for Deepr experts

| Distill output | Expert need |
|---|---|
| Per-source `_Insights.md` | Wiki-style notes with receipts |
| Cross-source synthesis | Multi-source depth (breaks single-digest mush) |
| arXiv + site + video + repo | Academic + product + talks in one topic |
| Plain Markdown library | Absorb as secondary corpus; regenerable views |
| MCP `distill-mcp` | Gap-route instrument already named in Deepr |
| Verify-before-write | Aligns with absorb verification gates |

**Yes:** Distill is the right engine for **wiki-style insights per topic** that
experts then promote into structured beliefs + TKG edges. Distill owns the
corpus; Deepr owns persistent role memory, temporal graph, consult, and coding
agent handoff.

### Cost truth (do you need $?)

| Route | Distill today | Marginal $ |
|---|---|---|
| Deterministic fetch/parse | Works | Network only |
| Local Ollama / LM Studio (loopback) | Works under `cost-mode no-metered` | $0 API; hardware/time |
| xAI / Gemini cloud | Works under `paid-ok` | Metered API |
| Anthropic API | Opt-in metered | Metered API |
| Plan-quota CLIs (Claude Code, Codex, Grok Build, Antigravity, Gemini CLI) | **Planned, not live providers** | Blocked in `no-metered` until adapter doctor + included-plan proof + eval |
| Host-managed agent worker | Explicit handoff | Cost unavailable to Distill; blocked in `no-metered` |

So: **you can run Distill without API spend** via local analysis + free
public sources. That is not the same as “subscription CLIs already work inside
Distill.” Plan-quota for Distill is still a roadmap item with the same
no-surprise-bills bar Deepr uses.

Also: local analysis still **fetches current public sources**. It is not offline
parametric memory pretending to be research.

## What Learny is

**Learny** is large-scale agentic reasoning over a big unfamiliar corpus under
time/cost constraints. Flagship shape: “AWS re:Invent / Ignite just happened -
process hundreds of sessions into long-form strategic learning material.”

Stages: discover/acquire sessions -> analyze each -> validate/improve ->
synthesize themes -> deep report -> export JSON/bundle for agents.

Vision in its ROADMAP: today a tool you run; tomorrow a **persistent domain
expert** you consult. That is explicitly Deepr-adjacent.

Current economics: Gemini-metered in the public README (~$77 for 286 Ignite
sessions). **Not** a free membership-CLI path out of the box today. Local or
plan-quota Learny would need the same capacity honesty as Distill/Deepr.

### Why Learny is interesting for Deepr experts

| Learny output | Expert need |
|---|---|
| Per-session insights | Dense short-form notes |
| Theme synthesis | Cross-cutting architecture/service narratives |
| Long-form deep report | Elite-bar analysis, fail patterns, “what actually changed” |
| Export bundle | Absorb into expert belief store + wiki sections |
| Conference-scale | “Latest services and architecture” after big vendor events |

Learny is the **event/corpus-scale exoskeleton**. Distill is the **ongoing
topic corpus**. Deepr is the **persistent expert + TKG + consult surface**.

## Target compound loop

```text
idea / domain
    |
    +-- Distill: discover + ingest docs/papers/videos/repos -> library/topic/
    |       (local no-metered analysis when quality clears eval)
    |
    +-- Learny: (when corpus is huge / event-scale) attend/analyze/synthesize
    |       -> long-form learnings export
    |
    v
Deepr expert make --local
    absorb Distill/Learny Markdown (trust-class secondary)
    optional: project stance as primary
    TKG edges + temporal "what changed"
    regenerate digest (wiki sections) + memory-card
    subscribe + sync for cadence
    quality scorecard + improve
    |
    v
Coding / research agents consult via MCP (local or plan synthesis)
```

Epistemic boundaries stay honest:

- Distill/Learny artifacts are **evidence packs**, not automatic belief writes.
- Deepr absorb/graph-commit remains the write boundary.
- TKG records what was believed when, contradictions, and revisions as sources
  update - that is the power of compounding research over time.

## Capacity reality (Deepr side)

| Capacity | Works for expert maintenance today | Notes |
|---|---|---|
| Local Ollama | Yes: absorb, sync, consult, improve structural | Preferred $0 |
| Plan CLI Claude Code | Yes after paid-overage-off proof | Only executable plan adapter |
| Codex / OpenCode / Kiro / Grok / Antigravity / Copilot | Visible, **execution-blocked** | Tool confinement / overage / metering not proven |
| Metered API | Preview/reconcile only; production dispatch frozen | Until account-control verifier |
| Distillr specialist on gap-execute | Routed as DEFERRED suggestion | Approval-gated, not auto-spend |
| Learny | Not a first-party Deepr instrument | Manual export absorb today |

So the membership-plan dream is **directionally right** and **partially true**:

- Deepr can already use **Claude plan** for some expert ops when safe.
- Distill can already use **local** analysis for $0 API on corpus builds.
- Full “any plan CLI anywhere free” is **not shipped** in either tool; claiming
  it would violate no-surprise-bills.

## Gaps vs end state (as of Step 3 done)

Authoritative build order: [../plans/living-expert-research-stack.md](../plans/living-expert-research-stack.md).

### Still open (ordered)

| Priority | Gap | Why it matters | Plan step |
|---|---|---|---|
| 1 | No batch absorb of Distill library trees | Deepen recipes exist; one-file absorb cannot scale multi-source | **4.1 next** |
| 2 | Distillr gap-execute still DEFERRED | Academic deepen not closed in improve loops | 5.1 |
| 3 | Learny not first-party | Event-scale long-form still manual export | 5.2 |
| 4 | No `expert spawn` | Council-plan requires manual make per role | 6.1 |
| 5 | No challenge consult mode | Dissent depends on prompt craft | 6.3 |
| 6 | **No insight layer.** Absorb only emits atomic facts, so no corpus can become stance, fail patterns, tensions, or open questions. The typed perspective state exists but is inert: zero production readers, zero populated across 39 experts, write-once, `evidence_refs` dropped on write. | This is the product, not a later polish. See [expert-insight-layer.md](expert-insight-layer.md) | decide **before** 4.1 |
| 7 | Plan-quota CLIs (most) blocked | Membership fleet incomplete by design until proofs | 7 |
| 8 | Calibration harness not published | Confidence meaning not measured | 8 |

### Closed or reduced (do not re-plan as if missing)

| Gap (was) | Status |
|---|---|
| Digest only a conf bullet list | Reduced: wiki partitions (stance/multi-source/secondary/tertiary/sources) |
| No Distill deepen recipe | Closed: `expert deepen-plan` |
| No quality/improve loop | Closed: structural `quality` + `improve` |
| No diverse council composition | Closed: `expert council-plan` |
| Trust always tertiary 0.60 on file absorb | Reduced: `--trust-class` with secondary default on `--file`. No reclassify command exists; re-absorbing with an explicit `--trust-class` is the only path, and `absorb-okf` still has no flag at all (lands tertiary). |
| Flat docs=0 false empty | Closed: claims inventory |

## Non-goals

- Pretend plan CLIs are free before proofs exist.
- Let Distill/Learny write Deepr beliefs without absorb gates.
- Replace Distill or Learny with a Deepr reimplementation.
- Autonomously burn membership quota without operator visibility.

## Success metrics

1. Domain pillar experts: majority of high-confidence claims cite Distill/official
   multi-origin packs, not project intent alone.
2. `expert quality` multi_source_share and circularity improve after Distill deepen.
3. One conference or large-topic Learny export absorbed into an expert produces
   wiki sections a human would actually study.
4. Coding agents can handoff-consult and get fail patterns + elite bar, not only
   atomic facts.
5. Operator can complete a deepen cycle with **$0 API** using Distill
   no-metered + Deepr local, when local models pass Distill eval for the workload.

## Implementation status (tracking)

Authoritative checkpoint: plan Steps 0-3 done; **next = Step 4.1 absorb-dir**.

- [x] Design + capacity research (this doc)
- [x] Implementation plan Steps 0-8 ([../plans/living-expert-research-stack.md](../plans/living-expert-research-stack.md))
- [x] ROADMAP unreleased pointers + runtime/build order
- [x] `deepr expert deepen-plan` (Distill/Learny recipe, $0 plan only)
- [x] Wiki-shaped `expert digest` partitions
- [x] Quality `distinct_origin_count` + improve points at deepen-plan
- [x] `deepr expert council-plan` (diverse multi-axis roster)
- [ ] **Next:** batch absorb-dir for Distill library trees (Step 4.1)
- [ ] Doctor probe for distill on PATH (4.2)
- [ ] Distillr gap-execute when no-metered proven (5.1)
- [ ] Learny export absorb first-class (5.2)
- [ ] `expert spawn` (6.1)
- [ ] Challenge consult mode (6.3)
- [ ] Plan-quota adapters (Step 7, proof-gated)
