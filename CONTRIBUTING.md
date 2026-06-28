# Contributing to Deepr

Thanks for your interest. This document is the operating manual: how work
goes from idea to shipped, and the bar it clears on the way.

A note on weight: Deepr is a spare-time, solo-maintained project. The
practices below are borrowed from how strong teams work, kept deliberately
light. They exist to make quality repeatable instead of heroic - not to add
ceremony. Use judgment; most changes are small and need none of the heavier
steps.

## Setup

```bash
git clone https://github.com/blisspixel/deepr.git
cd deepr
uv pip install -e ".[dev,full]"   # [dev] alone is NOT enough - the suite imports
                                  # azure/flask/etc. and fails collection without [full]
pre-commit install
```

Requires Python 3.12+ (tested on 3.12 / 3.13 / 3.14). `uv` is the canonical
toolchain; plain `pip` works too.

## How we work

The loop, from smallest to largest change:

1. **Frame the goal.** State the decision or problem the change serves, not
   just the task. If you cannot say what "good" looks like, stop and figure
   that out first.
2. **Write a design note _before_ building** when the change touches a
   contract (a public/MCP/CLI output shape, an on-disk format, an error
   surface) or spans several modules. A page in `docs/design/` is enough.
   This is where you discover problems like "there are actually two error
   hierarchies" before you have written code against the wrong assumption.
3. **Record the decision** in `docs/decisions/` (an ADR) when a choice is
   cross-cutting or hard to reverse - the *why*, and the alternatives you
   rejected. See `docs/decisions/README.md`.
4. **Build in small, reversible increments.** Prefer additive,
   backward-compatible changes. One feature or fix per commit/PR. Each
   increment lands green before the next starts.
5. **Verify as you go**, then **ship**, then **validate live** where it
   matters. Live runs have found real bugs every time (see the ROADMAP
   live-validation entries); a passing suite is necessary, not sufficient.

## Definition of Done

A change is done when all of these hold - not "the code works":

- [ ] Tests added/updated; a bug fix ships with a regression test that fails
      without the fix.
- [ ] `python -m pytest tests/unit/ --ignore=tests/data -q --timeout=120` is
      green (this is what CI runs). Do **not** run bare `pytest`:
      `tests/integration/` needs API keys and one test can hang without them.
- [ ] Coverage stays at or above the gate (80% branch, `fail_under` in
      `pyproject.toml`; ratcheting toward 95).
- [ ] `ruff check src/deepr/` and `ruff format src/deepr/` clean.
- [ ] `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/core src/deepr/providers src/deepr/mcp`
      clean (the blocking strict islands; do not regress the wider baseline).
- [ ] `python scripts/check_docs_consistency.py` passes (doc counts match
      source).
- [ ] Docs updated: CHANGELOG entry; README/guides if behavior changed;
      ROADMAP item checked off or moved.
- [ ] Agentic or scheduled surfaces document their workflow/agent boundary,
      rollout stage, versioned contracts, verifier, state persistence, retry
      behavior, idempotency or compensation path, and human-approval threshold
      before widening autonomy.
- [ ] No em-dashes in docs/markdown (use ` - `). No AI attribution in commit
      messages.
- [ ] CI green after push.

## Branches, merges, and hygiene

The repository stays tidy by rule, not by cleanup:

- **One long-lived branch.** `main` is always releasable (GitHub Flow). Each
  change gets a short-lived branch, a PR against `main`, and is deleted on
  merge. Auto-delete is on, so no branches linger.
- **Squash-merge.** The merge commit is the PR title and nothing else - no
  body trailers. No machine attribution ever lands on `main`: no AI
  attribution, and no automated coauthor or signoff trailers. Repo settings
  enforce the clean squash message.
- **Dependencies.** Dependency update automation opens the PRs. Merge green minor/patch bumps
  promptly; close major bumps that fail CI until they are compatible. Do not
  leave dependency branches or PRs sitting open.
- **Nothing merges red.** A green CI run is the gate for every merge.

## Code style

- **Formatter / linter**: ruff (line length 120). Pre-commit enforces it.
- **Types**: `core/`, `providers/`, and `mcp/` are `mypy --strict`-clean and
  gated; new modules should aim for the same.
- **Logging**: `logging.getLogger(__name__)` in library code, never
  `print()`. Specific exception types, not bare `except Exception`.
- **Single sources of truth**: model pricing/capabilities in
  `src/deepr/providers/registry.py`; version in `src/deepr/__init__.py`; the reports
  root from `load_config()["results_dir"]` (never hardcode a path).
- **Parse, don't validate**: validate external data once at the boundary into
  rich types so core logic never sees raw, possibly-invalid input.

## Testing

```bash
python -m pytest tests/unit/ --ignore=tests/data -q --timeout=120          # the gate
python -m pytest tests/unit/ --ignore=tests/data --cov=deepr --cov-report=term-missing
python -m pytest tests/unit/test_config -v                                  # one area
```

Tests must pass with **no API keys and no .env** - a test that only passes
when a dev key happens to be set is a regression (it has happened twice).

## Project structure

- `src/deepr/` - main package: `cli/` (Click commands), `core/` (orchestration,
  costs, context), `providers/` (model integrations), `experts/` (domain
  expert system), `mcp/` (MCP server), `services/`, `storage/`, `queue/`.
- `docs/` - guides; `docs/design/` (feature design docs); `docs/decisions/`
  (ADRs).
- `deploy/` - cloud templates (AWS SAM, Azure Bicep, GCP Terraform) over a
  shared `deepr_api_common` library.
- `tests/unit/` - unit tests; `tests/integration/` - require API keys.

## Cloud deployment guidelines

When modifying `deploy/*/`: use native tooling (SAM / Bicep / Terraform);
validate input at the handler (prompt length, model, job-id format); include
security headers (HSTS, X-Frame-Options, X-Content-Type-Options); add CORS
OPTIONS handling; use `deploy/shared/deepr_api_common/`; verify syntax with
`python -m py_compile`; test both `Authorization: Bearer` and `X-Api-Key`.

## High-impact areas

Research quality (synthesis prompts, context chaining), provider
integrations, cost optimization, expert intelligence, and CLI/agent
usability. See [ROADMAP.md](ROADMAP.md) for the sequenced plan.

## Questions

[GitHub Issues](https://github.com/blisspixel/deepr/issues) or nick@pueo.io.
