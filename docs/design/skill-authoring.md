# Authoring Deepr skills well

Status: guidance, 2026-06-23. How to write skills that make Deepr (and the
agents that consult it) measurably better, not just more verbose. Grounded in
Anthropic's Agent Skills guidance and reconciled with Deepr's own
[AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) and evidence layer. Read this
before adding a built-in skill, scaffolding a custom one (`deepr skill create`),
or changing the SKILL.md exporters. User-facing skill mechanics live in
[EXPERTS.md](../EXPERTS.md#expert-skills); this is the *how to make them good*
companion.

## Two skill surfaces (do not conflate them)

Deepr touches skills from both sides, and the authoring rules differ:

1. **Internal expert-skills** - a `skill.yaml` + `prompt.md` + `tools/` folder an
   expert loads to gain a capability (`financial-data` computes ratios,
   `code-analysis` audits dependencies). Three-tier storage (built-in -> user ->
   expert-local), auto-activation on keyword/regex triggers, progressive
   disclosure (summary always in the system prompt, full prompt + tools load
   only on activation), cost-tiered tools, per-call budget. These run *inside*
   Deepr.

2. **Host-facing SKILL.md export** - `deepr expert export-skill` packages an
   expert as an agentskills.io `SKILL.md` so an outside host (Claude Code,
   Codex, Cursor, Copilot, OpenClaw) can consult it over MCP. This is a
   *pointer*, not a copy: the host calls Deepr's MCP tools at run time. The
   generated skill is the product's distribution surface.

Anthropic's practices apply to both, but "scripts" and "tools" mean the internal
`tools/` folder, while "description as a trigger" matters most on the export
frontmatter and the internal `triggers:` block.

## Where Deepr is already strong (do not regress these)

| Anthropic practice | Deepr already does it |
|---|---|
| Skills are folders, not prompts | `skill.yaml` + `prompt.md` + `tools/`; the exemplar `skills/deepr-research/` also ships `references/` and `scripts/` |
| Progressive disclosure | Skill summaries stay in context; full prompt + tools load only on activation. Keep `prompt.md` lean and push depth into `references/` |
| Scripts for deterministic work | `tools/` are Python with `cost_tier: free/low/...`; this is the AGENTIC_BALANCE workflow side (see below) |
| Measure usage | `SkillEfficacy` already records `times_activated`, `citations_added`, `gaps_closed`, `impact_score`, `cost_per_activation`. Use it to prune under-triggering or low-impact skills |
| Compose, don't over-orchestrate | Multi-expert work goes through the bounded `council.py`/crews and MCP bridging, never an unbounded mega-skill (the not-the-orchestrator non-goal) |

## The gaps to close (the actual refinement)

### 1. Verification is the highest-leverage skill type - and it is Deepr's home turf

Anthropic reports that *product-verification* skills had the most measurable
impact on output quality internally. Deepr has the strongest possible version of
this already built: the **evidence layer**. A skill that *checks whether work is
correct* beats one that merely produces more of it.

Lead skills with verification, drawing on tools that already exist:

- `deepr_expert_validate` -> PASS/WARN/FAIL with supporting/contradicting
  citations: the canonical "is this claim consistent with what we actually
  know?" check.
- `deepr expert reflect` (grounding/completeness/calibration) before delivery;
  `deepr eval calibrate` (does a stated confidence track real grounding?);
  `deepr eval continuity` (does the expert admit its own staleness?);
  `deepr eval red-team` ($0 boundary checks).

This is the same invariant AGENTIC_BALANCE states for loops - *a result is
complete only when an independent verifier passes, never when the model
self-declares done*. A verification skill is that invariant packaged for reuse.
When you can spend engineering time making one skill excellent, make it a
verifier.

### 2. Every skill carries a Gotchas section (the highest-signal content)

Anthropic calls Gotchas the single highest-signal part of a skill, and it must
come from *real* failure modes the agent hit, not theoretical warnings. Deepr
already lives this culture - the repo's root `SKILLS.md` and the inline
"dogfood-sourced" notes are a running gotchas log - but the skill *formats* did
not carry one. They now should:

- Internal skills: a `## Gotchas` section in `prompt.md`.
- Exported SKILL.md: a `## Gotchas` section in the body (the `export-skill`
  generator now emits one for consulting-an-expert; see
  `deepr/skills/expert_skill.py`).

Seed it from observed failures and append over time. Good Gotchas for a
*consult-a-Deepr-expert* skill, all grounded in real semantics:

- The expert can be **stale**; a confident answer is not necessarily current.
  Check `deepr_what_changed` / freshness for time-sensitive questions.
- A `PASS` from `deepr_expert_validate` means "consistent with what this expert
  currently believes," **not** ground truth - it is bounded by the expert's
  sources. Treat WARN/FAIL as a stop; do not treat PASS as proof.
- Confidence is **trust-floor-capped** (web-sourced claims cap at 0.60
  single-source / 0.80 with two independent sources), so a "0.8" is a capped
  ceiling, not a probability of truth.
- Low confidence or a flagged gap is a signal to **fill the gap** (offer
  research), not to guess - and to surface that to the user.
- The skill is a pointer: it needs a running Deepr MCP server with **this expert
  present**. `EXPERT_NOT_FOUND` means the host is pointed at the wrong instance.

### 3. Write the description as a trigger, not a summary

The host scans each skill's name + description to decide whether to invoke it,
so the description must name the *situations and user wording* that should fire
it, not summarize what the skill is. Internal skills already encode this in
`triggers: { keywords, patterns }`; carry the same intent into the exported
SKILL.md frontmatter `description` ("Use when the user asks about X / needs a
cited answer on Y / wants to validate a claim about Z"), not a noun phrase.

## Deterministic scripts vs model judgment (the AGENTIC_BALANCE line, in skills)

Use a `tools/` script for anything deterministic and repeatable: calculations,
extraction, schema validation, formatting, API/MCP calls, tests. That frees the
model to compose rather than rebuild boilerplate, and it puts the work on the
**workflow** side of the axis (form and side-effects, decidable from structure).

The one hard rule, straight from the STOP banner: a skill tool must **never
encode a meaning-verdict**. A `tools/` function may compute a ratio, parse a
table, or hash a file; it must not be a lexical/keyword rule that *concludes*
contradiction, grounding, similarity, dedup, or "good writing." Those are model
judgment, calibrated before trusted. A cheap tool may *route into* a model check
(high-recall prefilter) but never deliver the verdict. If a skill's value is a
quality judgment, its verifier is a calibrated model call, not a regex.

## Keep each skill narrowly scoped

Anthropic found the best skills fit cleanly into a single category; multi-purpose
skills confuse the agent. Deepr's built-ins are the model to copy:
`financial-data` computes ratios and nothing else; `code-analysis` does
dependency + complexity. One job per skill. If a skill is growing a second
unrelated job, split it - and let composition (council/crews, MCP bridging) join
small skills rather than one skill swallowing the workflow.

## Measure, then prune

`SkillEfficacy` already gives you `impact_score` (citations + closed gaps per
dollar), `cost_per_activation`, and `times_activated`. Treat a skill that
under-triggers or shows low impact as a candidate to retire or re-trigger - the
same discipline Anthropic applies by logging skill usage internally. A skill
nobody triggers, or that triggers and adds no citations/closed gaps, is cost
without value.

## Authoring checklist

Before shipping a skill (built-in, custom, or an exporter change):

- [ ] One job, one category. Split it if it is growing a second.
- [ ] Description is a trigger (situations + user wording), not a summary;
      `triggers.keywords`/`patterns` (internal) or frontmatter `description`
      (export) name real invocation moments.
- [ ] Deterministic work lives in `tools/`; no tool encodes a meaning-verdict
      (route to a calibrated model instead).
- [ ] If the skill asserts quality, it *verifies* (validate/reflect/eval), it
      does not just emit more output.
- [ ] A `## Gotchas` section exists, seeded from real failures, and you will
      append to it as new ones surface.
- [ ] `prompt.md`/SKILL.md is lean; depth is in `references/` (progressive
      disclosure).
- [ ] Cost tiers and budgets are set; paid tools are approval-gated, free tools
      can auto-run.
- [ ] You can name how you will measure it (`SkillEfficacy`) and when you would
      retire it.
