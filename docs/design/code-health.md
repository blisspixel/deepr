# Code-Health Hardening Plan

> A sequenced plan to hold the whole codebase to a standard a human or an AI
> could admire, and to keep it there. Grounded in a hands-on audit of the
> repo (2026-06-12) and the engineering-standards track already in
> [ROADMAP.md](../../ROADMAP.md) Phase E. This is the detailed companion to
> the roadmap's **Phase Q** checklist.

## Why this exists

AI-assisted development is fast but has characteristic failure modes:
duplication ("five sloppy ways to do one thing"), inconsistent patterns,
over-large files, shallow abstractions, unenforced complexity, advisory-only
security, coverage numbers that exclude the hard parts, and a model's lack of
current-date / recent-change awareness. deepr already mitigates much of this
(see *Posture*), but an honest audit found specific, fixable gaps. The
governing principle, borrowed from the roadmap itself: **an unverified
improvement loop is a degradation loop** - so we make quality
*un-regressable* before we pay down the backlog, and we *characterize before
we refactor*.

## Posture (what already protects quality)

Recorded so the plan is proportional - this is not a rescue, it is a finish.

- **Types**: `mypy --strict` is a *blocking* gate on `core/` + `providers/` +
  `mcp/` (clean); whole-tree baseline is non-blocking.
- **Tests**: 5,300+ unit tests; **80% branch** coverage gate (stricter than
  line) on Python 3.12 / 3.13 / 3.14.
- **Lint**: ruff (E/F/W/I/B/UP/RUF) blocking + pre-commit.
- **Security / supply chain**: `pip-audit` blocking, Dependabot weekly, SBOM
  via `uv export`, hash-pinned `uv.lock`.
- **Invariants**: append-only cost ledger; single sources of truth (pricing
  in `providers/registry.py`, version in `__init__.py`, reports root from
  config); parse-don't-validate at boundaries; agent error envelope.
- **Process**: ROADMAP single-source-of-truth, ADRs (`docs/decisions/`),
  design docs (`docs/design/`), Definition of Done (`CONTRIBUTING.md`).

## Findings (the audit, with numbers)

| # | Finding | Evidence (2026-06-12) | Severity |
|---|---------|------------------------|----------|
| F1 | Over-large files | `web/app.py` 3,992 lines; `cli/commands/semantic/experts.py` 3,567; `experts/chat.py` 2,633; `experts/lazy_graph_rag.py` 2,036; `mcp/server.py` 1,937; 6 more over 1,000 | High |
| F2 | Two config systems | `load_config()` dict **53** call sites (formally "Deprecated: use get_settings()") vs typed `get_settings()` **14** sites - migration stalled | High |
| F3 | Complexity unenforced | **146** functions over the C901 cap (max-complexity 10); advisory only | Medium |
| F4 | Security lint advisory | ruff `S` rules find **97** issues; run advisory, not ratcheting | Medium |
| F5 | Coverage omits the hard parts | omit list excludes `web/*`, all `cli/commands/*`, `chat.py`, `curriculum.py`, `learner.py`, `lazy_graph_rag.py` - the largest, most complex files are unmeasured | Medium |
| F6 | Duplicate verbs / helpers | ~~top-level `cost` **and** `costs` commands~~ (Q1.2 done 2026-06-14: `cost` deprecated-hidden alias); ~~3 separate `run_async` definitions~~ (Q1.3 done 2026-06-14: one helper in `utils/async_runner.py`) | Low |
| F7 | Staleness defense | model-registry drift checks exist; no scheduled dependency-drift or standards-review cadence | Low |

(F-class context: the reports-root 3-way split and the learner infinite-poll
hang were the same families - both already fixed this session.)

## The plan, step by step

Sequenced so the cheap, risk-free, regression-proofing work lands first, and
the invasive refactors land last, behind tests. Each step states its
**approach**, **risk**, and **done** bar.

### Q0 - Make quality un-regressable (ratchets first)

The highest-leverage, lowest-risk work: stop the backlog from growing before
spending effort shrinking it. None of these change runtime behavior.

- **Q0.1 File-size guard.** A CI check (`scripts/check_file_sizes.py`) fails
  if any `deepr/*.py` exceeds a line ceiling, with the current over-ceiling
  files grandfathered in an explicit, shrinking allowlist. *Risk:* none
  (additive CI). *Done:* a new 800-line file fails CI; the allowlist only
  ever shrinks.
- **Q0.2 Complexity ratchet.** Record the C901 count as a baseline; CI fails
  if it grows. *Approach:* a small count-and-compare step (ruff `--select
  C901`), baseline committed. *Done:* adding an 11-complexity function fails
  CI; baseline only decreases.
- **Q0.3 Security ratchet.** Same mechanism for ruff `S`: baseline the 97,
  fail on growth, drive toward flipping `S` into the blocking `select`.
  *Done:* a new `S`-flagged construct fails CI.

### Q1 - One way to do each thing (tidy duplication)

- **Q1.1 Finish the config migration (F2).** Migrate `load_config()` call
  sites to typed `get_settings()` **package by package** (cli, web, core,
  ...), each batch with the suite green, then delete `load_config()`.
  *Risk:* medium (53 sites; behavior must match). *Approach:* a thin compat
  shim first if needed; migrate + test per package; remove the shim last.
  *Done:* `load_config` gone; one config type; `get_settings` everywhere.
  *Hazard found 2026-06-14 (characterize before touching any site):* there are
  **two divergent `load_config()` dicts**, not one, and they disagree -
  `deepr/config.py` returns `api_key="***"` (redacted), includes an
  `experts_dir` key, and sources cost limits from `DEEPR_MAX_COST_*` env vars
  (defaults 5/25/200); `deepr/core/settings.py` returns the **real** `api_key`,
  has **no** `experts_dir`, and sources cost limits from `settings.budget`
  (different defaults). So each call site depends on which `load_config` it
  imports and which fields it reads. Step 0 is a characterization test pinning
  both shapes per call site (api-key expectation, `experts_dir` presence,
  cost-limit source) before any migration; reconcile the two dicts first, then
  migrate. A blind swap to `get_settings()` would flip a redacted key to a real
  one (or drop `experts_dir`) - the same silent-divergence family as the
  two-report-roots bug. (Third `load_config` in `core/constants.py` returns
  `None` and is unrelated - it loads env, not the config dict.)
- **Q1.2 Resolve `cost` vs `costs` (F6). DONE (2026-06-14).** `cost` is now a
  hidden, deprecated alias emitting a warning that names the replacement;
  `cost estimate` was ported to `costs estimate` (and its dead
  `deepr.services.cost_estimation` import fixed to `deepr.core.costs`). Kept
  working >= 2 releases (kubectl policy). *Done:* one cost namespace;
  deprecation warning + test (`test_cli/test_cost_deprecation.py`).
- **Q1.3 One `run_async` helper (F6). DONE (2026-06-14).** Canonical
  `run_async_command` moved to `deepr/utils/async_runner.py`;
  `deepr/cli/async_runner.py` re-exports it, and `web/app.py` + `api/app.py`
  dropped their private `def run_async` for `import ... as run_async`. *Done:*
  single definition, imported by cli + web + api (test harness helper left as-is).

### Q2 - Coverage honesty (F5)

- **Q2.1** Characterize the largest omitted files before touching them:
  add black-box tests that pin current behavior (`web/app.py` routes,
  `experts.py` commands). *Done:* each targeted file has a characterization
  suite.
- **Q2.2** Remove files from the coverage omit list as they gain real tests,
  ratcheting the *true* covered surface up. *Done:* omit list shrinks; the
  headline number reflects the hard parts too.

### Q3 - Decompose the giant files (F1) - only after Q2 characterization

- **Q3.1 `web/app.py` (3,992)** -> Flask blueprints by area (research,
  results, experts, costs, system), a thin `app factory`, shared helpers
  extracted. *Risk:* high (currently coverage-omitted) - **gated on Q2.1
  characterization tests**. *Done:* no file over the ceiling; blueprints;
  tests green.
- **Q3.2 `cli/commands/semantic/experts.py` (3,567)** -> split by command
  area (chat, knowledge, lifecycle, perspective-queries, skills). *Done:*
  each module focused; CLI behavior unchanged (tested).
- **Q3.3 `experts/chat.py` (2,633) and `mcp/server.py` (1,937)** -> extract
  cohesive units (chat modes / dispatch; tool groups). *Done:* under
  ceiling; strict-clean (mcp stays in the strict gate).

### Q4 - Pay down the backlog (F3, F4)

- **Q4.1** Refactor the worst C901 offenders (top 10 by score first); ratchet
  the cap down as they fall. *Done:* cap reaches 10 blocking.
- **Q4.2** Resolve or explicitly justify each ruff `S` finding; flip `S` into
  the blocking `select`. *Done:* `S` blocking, zero unjustified findings.

### Q5 - Defend against staleness (F7)

- **Q5.1** Scheduled CI job: dependency drift (`uv lock --upgrade` behind
  review), model-registry drift (extend the existing check), and a quarterly
  "standards review" reminder issue. *Done:* drift surfaces automatically,
  not by luck.

## Evidence base (2026 research)

A deep, source-verified review (2026-06-13) backs the approach. Highlights,
with the "why it matters" each implies:

- **The slopware signature is measurable.** Copy-pasted code rose 8.3% ->
  12.3% of changed lines (2021-2024) while refactoring collapsed 25% ->
  under 10% (GitClear 2025, 211M changed lines). *Implication:* audit for
  duplication and reward consolidation - Q1, and the file-size/clone
  discipline.
- **Models hallucinate dependencies** at 4.62-6.10% on 2026 frontier models,
  model-agnostically (arXiv:2605.17062). *Implication:* never auto-install
  AI-suggested packages; pin with hashes - deepr's hash-pinned `uv.lock`
  already does this; keep it.
- **Model staleness is real and doc-grounding is the fix.** With no docs,
  only ~42.6% of LLM code against changed APIs is executable; treating docs
  as first-class input raises it to ~66% and adoption to ~93%
  (arXiv:2604.09515). *Implication:* Q5, and the standing "research/search
  before claiming, don't trust memory" habit (this plan was written that
  way).
- **Ruff is the single-tool gate** (900+ rules: C901 complexity, S/bandit
  70+ SAST rules, comprehensions, pyupgrade, F401 dead-imports) - Astral
  docs. *Implication:* Q0.2/Q0.3/Q4 build on exactly this.
- **Function size**: Google's standard - when a function exceeds ~40 lines,
  consider splitting (soft trigger, paired with C901). *Implication:* the
  file-size guard's natural companion; fold a function-length signal into Q4.
- **Supply chain at publish time**: PyPI Trusted Publishing (OIDC, 15-min
  tokens) + PEP 740 attestations are the 2026 standard (OpenSSF, PyPI docs).
  *Implication:* if/when deepr publishes to PyPI, no static `PYPI_TOKEN` -
  already the roadmap Phase E position.
- **Coverage is a floor, not the goal**: mutation testing verifies tests
  actually catch faults (Meta Eng., FSE 2025). *Implication:* Q4 sets a
  mutation-score target on kernel modules (mutmut is already wired), not just
  a coverage %.

Full cited report retained in the research run; re-verify the time-sensitive
items (model cohort, hallucination rates, Ruff rule count) periodically -
this doc is meant to resist the very staleness it warns about.

## Principles carried through

- **Ratchet before refactor** - never let the backlog grow; shrink baselines
  monotonically.
- **Characterize before you cut** - no refactor of an under-tested file
  without pinning its behavior first.
- **Additive, reversible increments** - one concern per commit; green before
  the next.
- **No silent scope** - if a step grandfathers debt (an allowlist, a
  baseline), it is explicit and shrinking, never hidden.
- **Verify, don't assert** - each ratchet is proven by a test that fails when
  the rule is violated.
