# Deepr - agent project guide

Multi-provider research automation: routes each research question to the cheapest capable model and builds persistent domain experts (beliefs + confidence + gaps + citations). Three layers: kernel (`core/`, `providers/`, `queue/`, `routing/`, `observability/`), primitives (`experts/`, `services/`, `tools/`, `storage/`), interfaces (`cli/`, `web/`, `mcp/`).

`ROADMAP.md` is the single source of truth for active work; completed items move to `docs/CHANGELOG.md` at release. Read its Planning Principles before adding features - especially "close the loop before widening it" and "self-improvement is a verification problem".

`CONTRIBUTING.md` is the operating manual: how work goes from idea to shipped (frame -> design note -> small reversible increments -> verify -> ship -> validate) and the **Definition of Done** checklist every change clears. Before a contract-spanning or hard-to-reverse change, write a design note (`docs/design/`) or a decision record (`docs/decisions/`, ADRs) first - the *why*, and the alternatives rejected.

## Dev environment

- Install: `uv pip install -e ".[dev,full]"` - `[dev]` alone is NOT enough; the suite imports azure/flask/etc. and fails collection without `[full]`.
- Tests: `pytest tests/unit/ -q` - this is what CI runs (5700+ tests, several minutes). The unit suite must pass with **no API keys and no .env** - tests that only pass when a dev key happens to be set are a known regression class (fixed twice). Do NOT run bare `pytest`: `tests/integration/` hits real provider APIs, fails wholesale without keys, and at least one test polls forever on 401.
- Lint/format: `ruff check src/deepr/ && ruff format src/deepr/` (pre-commit runs these).
- Types (blocking CI gate): `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/core src/deepr/providers src/deepr/mcp`. The rest of the tree is a non-blocking baseline - don't add new errors.
- Coverage: 80% branch minimum (`fail_under`), ratcheting toward 95. New code ships with tests; every bug fix ships with a regression test.

## Hard rules

- **Rules vs agentic: read [docs/plans/AGENTIC_BALANCE.md](docs/plans/AGENTIC_BALANCE.md) before adding a rule or making something agentic, and update it when a decision moves the boundary.** Brittle rules that encode *meaning* (lexical/word-overlap checks used as a verdict) are the most-repeated wrong turn here. Determinism guards form and side-effects (schema, types, ranges, spend, writes, flowchartable control flow); model judgment owns meaning (contradiction, grounding, atomicity, dedup), calibrated before trusted; a lexical check may *route* but never *conclude*.
- **Never make paid API calls** (research runs, evals, embeddings) unless explicitly asked. Estimate cost first. Budgets are ceilings enforced in code - never weaken a gate to make a test pass.
- Capacity sources must be described honestly:
  - Works now: API-backed research with user keys and budget gates; local Ollama expert setup and maintenance via `expert make --local`, `expert sync --local`, `expert absorb --local`, `eval local`, and scored `capacity admit`.
  - Visible/read-only today: plan CLIs and quota sources shown by `deepr capacity`. Claude Code, Codex, Antigravity, Grok Build, GitHub Copilot CLI, Kiro, and similar plan CLIs are not Deepr execution backends until their adapters, quota probes, no-surprise-bills guards, and tests ship.
  - Explicit opt-in only: CLI judges such as Grok for `deepr eval local --judge-cli ... --allow-cli-judge`. Do not imply Deepr can prove whether a vendor CLI used subscription quota, credits, or metered credentials.
  - Roadmap language must distinguish `works now`, `visible/read-only`, and `planned adapter`. Do not market roadmap capacity as shipped UX.
- The cost ledger is **append-only** and every spend source writes it. No silent-money paths.
- Generated artifacts (expert digests, SKILL.md exports, reports) are **derived views**: regenerable from the structured belief store, never hand-edited as authoritative.
- The reports root is config-sourced: `load_config()["results_dir"]` (env `DEEPR_REPORTS_PATH`, default `data/reports`). Never hardcode a `reports/` path - divergent roots was a real shipped bug.
- `xfail` is disallowed in CI. Don't skip-to-green.
- Windows is a first-class dev platform: UTF-8 console handling, cross-platform paths, no POSIX-only assumptions.

## Conventions

- Conventional commits (`feat:`/`fix:`/`docs:`/`chore:`); single `main` branch; no bot-authored commits.
- Live-validation findings get a ROADMAP backlog entry and are checked off with a dated note when fixed.
- Doc counts (test counts, tool counts) are checked by `scripts/check_docs_consistency.py` in CI - update docs when the numbers move.
