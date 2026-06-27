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

## Current Cycle Alignment - 2026-06-27

Active task: harden the MCP expert consult contract for external agents and
lock the legacy expert-chat spend boundary without widening brittle agentic
rules.

Target score before merge:

| Category | Required score | Evidence |
|---|---:|---|
| Correctness | 5/5 | Focused tests prove zero-budget non-streaming and streaming expert chat block before provider dispatch; MCP capability, registry, and agent-guide tests pin the consult-vs-query boundary. Full unit suite is green. |
| Security | 5/5 | Legacy chat now denies before direct model paths when budget is insufficient; no-metered external-agent docs require local or explicit plan consult with no live metered fallback; Gitleaks git history scan found no tracked leaks. |
| Performance | 5/5 | The no-metered path stays on existing local or plan consult synthesis. No new model calls, polling, pre-warm, or auto-fan-out behavior was added. |
| Readability | 5/5 | Reusable chat-turn budget and routing helpers live in a small module; docs name works-now surfaces plainly and do not market planned chat backends as shipped. |
| Maintainability | 5/5 | The `experts/chat.py` grandfathered file-size ratchet stays green; deterministic code owns budgets, backend choice, schemas, and no-fallback, while model judgment still owns synthesis meaning. |
| Simplicity | 5/5 | One small helper module plus precise docs and tests close the safety gap without inventing a new expert-chat backend before the design contract is ready. |

Cycle 12 keeps the MCP expert collaboration boundary intact: deterministic
workflow code owns spend, backend choice, scoped-tool guidance, schema language,
and no-fallback behavior; expert and synthesis models own perspective,
disagreement, uncertainty, and novel ideas.

## How to score (maker-checker)

Maker implements test-first. Then two independent checker passes: one for
security + performance, one for maintainability + simplicity. Each names the
weakest category and one concrete improvement. Iterate until all six are 5/5 and
every hard gate passes. A "5" earned by lowering the bar is a 1.
