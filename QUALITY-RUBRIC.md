# Quality Rubric

The bar every change clears before it ships. Score each category 1-5; a change
merges only at 5/5 across the board. 5 is not "no obvious problems" - it is "a
ruthless senior principal engineer would proudly merge this." Anchored to the
project's bible: [AGENTS.md](AGENTS.md), [ROADMAP.md](ROADMAP.md) (STOP banner +
Planning Principles), and [docs/plans/AGENTIC_BALANCE.md](docs/plans/AGENTIC_BALANCE.md).

## The six categories

1. **Correctness** - Does exactly what it should, including edge cases and
   failure paths. Has tests that would fail without the change (test-first).
   Validated locally (pytest, the change actually exercised), not asserted.
   - 5: behavior proven by tests that pin the contract and the failure modes;
     the maker-checker found nothing real.
   - 3: works on the happy path; an edge case or failure path is untested.
   - 1: unverified, or a test was written to pass rather than to catch.

2. **Security** - Money-path integrity (no surprise bills, append-only cost
   ledger), prompt-injection boundaries on untrusted spans, secret hygiene
   (never logged, stripped from child envs), SSRF/input validation at the edge.
   - 5: side-effects gated deterministically; untrusted input parsed at the
     boundary; no secret can leak; spend cannot exceed its contract.
   - 3: safe on the main path but a boundary is implicit or unverified.
   - 1: a path can overspend, leak a secret, or trust untrusted input.

3. **Performance** - Appropriate for an I/O-bound research system: bounded loops,
   no needless re-reads or N+1 calls, $0/owned capacity preferred over metered,
   cheap-first routing. Not premature micro-optimization.
   - 5: the cheapest correct path; bounded; no wasted calls or spend.
   - 3: acceptable but does redundant work or misses a cheaper rung.
   - 1: unbounded, or burns metered spend where owned/prepaid would do.

4. **Readability** - Reads like the surrounding code: same idioms, naming, and
   comment density. Comments explain *why*, never *what*. A new reader follows it
   without the author.
   - 5: self-evident; the one or two comments capture the non-obvious reason.
   - 3: correct but needs a second read, or over/under-commented.
   - 1: cleverness for its own sake, or noise comments.

5. **Maintainability** - Small functions, narrow scope, parse-don't-validate
   domain types, generated artifacts regenerable from canonical state. Respects
   the file-size, complexity, and security ratchets (never grows a grandfathered
   file). Determinism on form/side-effects; model judgment on meaning - never a
   brittle lexical verdict on contradiction, grounding, dedup, or quality.
   - 5: the boundary is right (workflow vs agent), nothing brittle, ratchets green.
   - 3: works but adds a small rule that encodes meaning, or nudges a ratchet.
   - 1: a lexical/keyword verdict on meaning, or churn no user feels.

6. **Simplicity (long-term)** - The simplest design that is still correct. No
   speculative generality, no over-engineering, no new dependency or abstraction
   that does not pay for itself now. Deleting code counts.
   - 5: a CS professor would call it elegant; nothing left to remove.
   - 3: fine, but carries an unused seam or an extra layer.
   - 1: framework-building for a problem we do not have.

## Hard gates (a single failure blocks merge, regardless of scores)

- Tests green locally on `.venv/Scripts/python.exe -m pytest` for the touched area.
- `ruff check` + `ruff format --check` clean; `mypy --strict` clean on the
  `core`/`providers`/`mcp` islands when touched.
- `scripts/check_file_sizes.py` and `scripts/check_ratchets.py` at or below
  baseline (never grow a grandfathered file or the C901/S counts).
- `scripts/check_docs_consistency.py` consistent (tool/skill counts match source).
- No AI attribution, emojis, or em/en dashes in any output or artifact.
- Lifetime external spend <= $5; owned/prepaid/$0 paths preferred by default.

## Current Cycle Alignment - 2026-06-26

Active task: add reviewed monitor proposal promotion for gap/eval candidates,
with dry-run default, explicit `--apply`, and no model calls.

Target score before merge:

| Category | Required score | Evidence |
|---|---:|---|
| Correctness | 5/5 | Promotion tests prove preview is non-mutating, gap apply is idempotent, eval apply writes a bounded artifact, CLI JSON works, and the published schema validates runtime payloads. |
| Security | 5/5 | `--apply` is required for writes; trace paths are not exposed; outputs stay `$0`; only sanitized candidate fields are promoted. |
| Performance | 5/5 | Work is bounded to recent local loop/trace records; no provider calls, embeddings, or paid validation. |
| Readability | 5/5 | Promotion is a small service over existing monitor and metacognition primitives. |
| Maintainability | 5/5 | Published v1 schema, registry entry, CLI surface, and docs keep the promotion artifact consumable by agents. |
| Simplicity | 5/5 | No new dependency, no broad state store, no prompt mutation, no self-model writer. |

Cycle 7 adds reviewed promotion for gap/eval proposals only. Self-model,
prompt, tool, and skill changes remain gated future work.

## How to score (maker-checker)

Maker implements test-first. Then two independent checker passes: one for
security + performance, one for maintainability + simplicity. Each names the
weakest category and one concrete improvement. Iterate until all six are 5/5 and
every hard gate passes. A "5" earned by lowering the bar is a 1.
