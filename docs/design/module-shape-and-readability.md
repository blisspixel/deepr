# Module Shape and Readability

Status: researched plan, 2026-07-14. Nothing here is shipped merely because it
is described. Companion to [code-health.md](code-health.md) and ROADMAP Phase Q
(deprioritized). Grounded in a fresh codegraph rebuild and a structural scan of
`src/deepr`.

## Goal

Make Deepr easier for humans and agents to *read and change correctly*, without
re-opening the Planning Principle 1b trap (tidiness refactors that break
adjacent behavior and deliver nothing a user feels).

The product still wins by calibrated experts and money-path integrity. This plan
only exists because navigability has become a *real* tax on that work.

## The dual failure mode of agentic coding

Agent-assisted development fails in **two opposite shapes**. Both show up here.

| Failure | Symptom | What agents optimize for | User / maintainer cost |
| --- | --- | --- | --- |
| **God files** | One module owns an entire surface | Keep editing the file you already have open | Hard to review, high merge conflict, C901 / file-size ratchet pressure |
| **Confetti / over-split** | Many tiny files, hop chains for one behavior | Clear a line-count or complexity ratchet; "one concern per file" cargo-cult | Hard to *find* the story; imports become the documentation; changes touch 5-12 files for one bug |

Industry context (same evidence base as code-health): GitClear-scale studies
show AI-era diffs increase copy-paste and collapse true refactoring. Agents also
prefer **extract-to-green** (split a function so C901/file-size pass) over
**reassemble-for-story** (put a cohesive workflow back in one readable unit).
Deepr's Q0 ratchets correctly stop god-files from growing, but they **incentivize
confetti** unless paired with a cohesion rule.

ROADMAP already bans one side of the trap:

> decomposing files for tidiness - work no user feels

This design bans the other side too:

> splitting files only to clear a ratchet, without a named cohesion boundary

## Codegraph (refreshed 2026-07-14)

Rebuilt with `.agent/codegraph/build_codegraph.py` at HEAD `ef555335`.

| Artifact | Use |
| --- | --- |
| `FRESHNESS.md` / `manifest.json` | Trust: medium; rebuild if HEAD or 7 days stale |
| `HOTSPOTS.md` / `impact.jsonl` | Blast radius before edits |
| `MAP.md` | Package map |
| `ENTRYPOINTS.md` | CLI / API / MCP entry surfaces |
| `RISK_ZONES.md` | Cost, security, provider, storage tags |
| `fragmentation_scan.py` | Size, tiny-module, prefix-family, cluster density |

Hotspots that matter for *reading* (not only blast radius):

- `experts/profile.py` fan-in 105 - almost everything touches expert identity
- `config.py` fan-in 84 - dual config systems still load-bearing
- `cli/commands/semantic/experts.py` fan-out 52, cycle_size 18 - CLI god-module
- `experts/chat.py` fan-out 24, cycle_size 7 - chat still central despite extracts
- `experts/beliefs.py` high churn + fan-in - belief store is a real core

## Measured shape (2026-07-14 scan)

Scope: `src/deepr/**/*.py` excluding node_modules (507 files, ~172k lines).

| Metric | Value | Read |
| --- | --- | --- |
| Median file | 230 lines | Healthy middle |
| p90 / p99 | 758 / 1328 | Long tail of large files |
| Files >1000 lines | 18 | Still the Q3 list, barely moved |
| Files >500 lines | 115 | Many "large but not ratcheted" modules |
| Tiny non-init (<=80 lines) | 57 | Real confetti population |
| One-top-level-symbol <100 lines | 26 | Often ratchet crumbs or thin gates |
| `experts/` package | **148 files**, ~56k lines | Largest cognitive surface |
| `cli/` | 89 files | Second |
| `mcp/` | 56 files | Third |

### Still-god files (extracts did not finish the story)

| File | Lines | Tops | Notes |
| --- | --- | --- | --- |
| `web/app.py` | 3929 | 94 | Blueprint split still planned, gated on characterization |
| `cli/.../experts.py` | 3336 | 28 | Fan-out 52; CLI dump |
| `experts/chat.py` | 2456 | **2** | Only 2 top-level defs - a class megamodule, not a package |
| `experts/lazy_graph_rag.py` | 2041 | 13 | Domain bulk |
| `mcp/server.py` | 1996 | 19 | Tool surface dump |

`chat.py` is the signature agentic-split failure: seven `chat_*` siblings
(~1508 lines total) were extracted for size/C901, but the parent remains 2456
lines with **two** top-level symbols. Readers still open the god file; the
siblings only help if you already know the names.

### Prefix families (cohesion candidates)

| Family | N files | Total lines | Internal import edges | Assessment |
| --- | --- | --- | --- | --- |
| `consult_*` | 12 | ~5921 | 12 | Large but *named* boundary (lifecycle, quality, traces). Keep as package; add a map |
| `chat_*` + `chat.py` | 8 | ~3964 | 15 | Split incomplete; god parent remains. Needs a real package boundary or reassembly of session core |
| `cost_*` / research cost | many | split across experts + observability + services | mixed | Money path *should* be multi-module; needs a single NAV map, not one file |
| `source_pack_*` | 7 | ~1616 | - | Reasonable compiler package; small leafs OK |
| `claim_*` | 2 | ~1282 | 0 | Healthy pair |

### Confetti concentrations

Tiny modules cluster in:

1. **`experts/`** - gates and helpers (`cost_admission`, `portrait_cost_gate`,
   `metered_mutation_gate`, `heartbeat`, ...) - some are correct *policy leaves*;
   some are extract-for-ratchet.
2. **`mcp/` + `cli/.../semantic/` + `web/`** - parallel thin wrappers for the same
   expert verbs (`expert_loop_status`, handoff, ...) - interface adapters, OK if
   they stay thin and share one implementation.
3. **`backends/plan_quota/`** - intentional process/OS split (Windows/Linux) -
   keep; cohesion is OS ownership, not line count.

## Pattern catalog (what to look for)

### P1 - Ratchet confetti

**Signal:** commit message "extract ... to clear C901/file-size"; new file under
~120 lines with one function; parent still huge.

**Examples in tree:** chat research-ops extract; repeated "keep under file-size
cap" commits on `web/app.py`.

**Fix policy:** allowed only when the extract has a **named seam** (e.g.
`execute_reserved_async_call`, not `helpers2.py`). Prefer reducing complexity
*inside* the function first. If extract is required, move a whole *story*
(admission + dispatch + settle), not a random helper.

### P2 - Incomplete god-file extract

**Signal:** parent still >1500 lines after N sibling extracts; parent has few
top-level symbols (one class / one facade).

**Example:** `experts/chat.py`.

**Fix policy:** either finish the package (`experts/chat/` package with
`session.py`, `dispatch.py`, public `__init__` re-exports) **after**
characterization tests, or stop extracting and treat the class as the unit
(document section map at top of file). Half-done splits are worse than either
extreme.

### P3 - Parallel surface wrappers

**Signal:** same verb in `cli/`, `mcp/`, `web/` as three thin files.

**Fix policy:** keep wrappers; force a **single primitive** in `experts/` or
`services/`. Do not invent a fourth copy. Document the primitive in the package
map.

### P4 - Import-as-architecture

**Signal:** understanding a feature requires chasing 8+ imports; no module
docstring lists the flow.

**Fix policy:** every multi-file family gets a 15-40 line map at the package or
facade top: ordered steps, which file owns which step, fail-closed points.

### P5 - Duplicate policy leaves

**Signal:** near-identical cost gates (`portrait_cost_gate` in experts and web
compat import, soft admission, metered gates).

**Fix policy:** one implementation; compat re-export only. Already partially
done for portrait; extend the rule.

### P6 - Docs and schemas sprawl (agent-readable but human-heavy)

**Signal:** 8 versions of graph-commit envelopes; huge ROADMAP/CHANGELOG.

**Fix policy:** schemas version; keep. ROADMAP stays SoT but "current work"
must stay skimmable. Do not merge schemas for tidiness.

## Principles (readability without churn)

1. **Cohesion over line count.** A 600-line file that tells one story beats six
   100-line files that scatter one story.
2. **Ratchets stay.** File-size and C901 ceilings remain un-regressable. They
   are not a license to confetti; they are a ceiling, not a target size.
3. **Characterize before reassembly or split.** Same Q2 gate as code-health.
4. **Navigation is a product for maintainers.** Package maps and codegraph are
   first-class, cheap, and reversible - prefer them before moving code.
5. **One public entry per verb.** CLI/MCP/Web may wrap; they must not reimplement.
6. **Money-path modules may stay multi-file.** Cost/ledger/reservation splits
   are intentional safety boundaries. Fix *maps*, not forced merges, unless
   two modules are true duplicates.
7. **Stop when adjacent tests break.** If a "readability" merge churns unrelated
   suites, revert - that is Principle 1b.

## Recommended target shapes

| Area | Target shape | Do not |
| --- | --- | --- |
| Expert chat | Package `experts/chat/` *or* documented section map inside `chat.py`; session core colocated | Endless `chat_foo.py` crumbs while `chat.py` stays 2k+ |
| Expert consult | Keep multi-file; add `experts/consult/README` map (or facade docstring) | Merge lifecycle + quality + traces into one god file |
| Cost / metered | Keep durable call, ledger, safety separate; one index doc `docs/design` already partial | Soft-admit helpers each in new files without using `cost_admission` |
| CLI semantic experts | Split by *command area* only after characterization (Q3.2) | Micro-files per flag |
| Web app | Blueprints by area after characterization (Q3.1) | Random helper extracts to stay under cap |
| MCP server | Tool groups modules after characterization | One file forever *or* one file per tool |

## Phased plan

### Phase R0 - Navigation only (cheap, no behavior change)

Done when a new contributor (or agent) can answer "where does X live?" without
opening 10 files at random.

1. Rebuild codegraph whenever HEAD moves on readability work (already done for
   this plan).
2. Keep `fragmentation_scan.py` next to the codegraph builder; run before any
   "tidy" PR and paste metrics into the PR body.
3. Add **family maps** (module docstring or short `MAP.md` in-package) for:
   - expert chat (`chat.py` + `chat_*`)
   - consult (`consult_*`)
   - research cost (`research_cost_*`, `metered_call`, `cost_safety`)
   - source pack (`source_pack_*`)
4. Extend `.agent/codegraph/QUERY_GUIDE.md` with "find fragmentation" and
   "find prefix family" recipes (point at the scan script).
5. ROADMAP: one line under Phase Q pointing here - **readability dual-mode**,
   not a new decomposition campaign.

### Phase R1 - Stop making confetti worse (policy)

Done when new extracts have a written seam name and a characterization note.

1. CONTRIBUTING / agent guide: **Extract rule**
   - Allowed: named seam, tested boundary, parent shrinks by a whole story.
   - Forbidden: extract only to clear C901/file-size; parent still owns the flow.
2. Prefer in-place simplification (early return, table-driven dispatch) over
   new files when complexity spikes.
3. CI optional later: warn (not fail) when a PR adds >N new files under 80 lines
   in `src/deepr` without deleting lines elsewhere - advisory only, never a
   ratchet war.

### Phase R2 - Reassemble wrong splits (behavior-preserving, gated)

Only with green characterization for the family. One family per PR.

| Priority | Family | Action | Risk |
| --- | --- | --- | --- |
| 1 | Chat session core | Either package `experts/chat/` with clear public API, *or* re-fold pure session helpers that have no independent callers into `chat.py` sections | Medium-high; many tests |
| 2 | Soft cost helpers | Ensure all soft-admit paths call `cost_admission`; delete duplicate gate copies | Medium (money path) |
| 3 | Portrait / metered web gates | Single implementation + re-export | Low |
| 4 | CLI/MCP/Web loop-status | Confirm one primitive; thin adapters only | Low |

Do **not** start R2 until R0 maps exist for that family.

### Phase R3 - Finish god-file decompositions (existing Q3, still gated)

Unchanged sequencing from code-health:

1. Characterization tests (Q2)
2. Then `web/app.py` blueprints, `experts.py` by command area, `mcp/server.py`
   tool groups

Difference from old Q3 wording: success is **readable areas with maps**, not
"every file under 800 lines." A 900-line blueprint that is one area is fine.

### Phase R4 - Agent ergonomics

1. Codegraph impact checks in PR template for critical fan-in files.
2. Optional: generate `docs/dev/PACKAGE_MAP.md` from codegraph MAP + scan
   (derived view, not hand-edited authority - same rule as expert digests).
3. When agents extract for C901, require the PR description to name the seam
   and show parent line delta.

## Success metrics (feelable)

| Metric | Baseline (2026-07-14) | Target |
| --- | --- | --- |
| God files >2000 lines | 5 | Down only via R3 with tests; no silent growth |
| Incomplete extracts (parent >1500 and sibling family exists) | chat, possibly others | 0 after R2 chat decision |
| Tiny non-init <=80 lines | 57 | Not a hard target; **net new tiny files in feature PRs trend flat** |
| Hops to implement a chat cost fix | open chat + 3-5 chat_* + cost modules | open map -> 1-2 modules |
| User-visible regressions from "tidy" PRs | historical config migration abort | zero; revert on break |

## Explicit non-goals

- Whole-tree "one file per class" or "max 200 lines"
- Config system migration re-open (Q1.1 abandoned)
- Merging money-path modules into one ledger megafile
- Coverage/mutation/file-size ratchets as primary goals
- Big-bang `experts/` re-tree

## Relationship to other docs

| Doc | Relationship |
| --- | --- |
| [code-health.md](code-health.md) | Ratchets, characterize-before-cut; this doc adds the confetti side |
| [AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) | Determinism vs meaning; module shape is a *human* determinism problem |
| ROADMAP Phase Q | Deprioritized churn track; R0-R1 are the only items that should compete with product work |
| `.agent/codegraph/*` | Navigation substrate; rebuild before structure PRs |

## First concrete steps (when prioritized)

1. R0 maps for chat, consult, research-cost (docstrings only).
2. Agent extract rule in CONTRIBUTING / Agents.md (short).
3. Chat family decision note: package vs section-map (design spike, no move).
4. Soft-cost call-site inventory -> force `admit_soft_cost_operation` (product
   + readability; aligns with money-path P1).

Until then, default when tempted to "clean structure": **update the map, not
the tree.**
