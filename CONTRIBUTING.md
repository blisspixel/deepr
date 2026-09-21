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
uv sync --frozen --extra dev --extra full
```

Activate the environment before invoking its tools: `source .venv/bin/activate`
on POSIX bash/zsh, or `. .venv/Scripts/Activate.ps1` in Windows PowerShell.
Then install the local hooks:

```bash
pre-commit install
```

`[dev]` alone is not enough for the suite's azure/flask imports. Frozen sync
uses the committed lock; `uv pip install -e ".[dev,full]"` does not enforce it.
An explicit virtual-environment Python path selects that interpreter but does
not put subprocess entry points such as `deepr-mcp` on `PATH`. The unit tests
exercise those installed entry points. See the official
[environment activation](https://docs.python.org/3/library/venv.html#how-venvs-work)
and [lock/sync behavior](https://docs.astral.sh/uv/concepts/projects/sync/).

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
   increment lands green before the next starts. Do not extract new files
   only to clear C901 or the file-size ratchet - that creates confetti that
   is harder to read than a cohesive module. An extract is allowed only as a
   named seam with tests, and the parent must lose a whole story, not a
   helper. Prefer a short package map when a multi-file family is
   intentional. See
   [docs/design/module-shape-and-readability.md](docs/design/module-shape-and-readability.md).
5. **Verify as you go**, then **ship**, then **validate live** where it
   matters. Live runs have found real bugs every time (see the ROADMAP
   live-validation entries); a passing suite is necessary, not sufficient.

## Definition of Done

A change is done when all of these hold - not "the code works":

- [ ] Tests added/updated; a bug fix ships with a regression test that fails
      without the fix.
- [ ] `python -m pytest tests/unit/ --ignore=tests/data -q --cov=deepr --cov-report=term` is
      green (this is what CI runs). Do **not** run bare `pytest`:
      `tests/integration/` needs API keys and one test can hang without them.
      The unit gate blocks outbound sockets by default and only allows
      loopback hosts for local fixtures.
- [ ] `python -m coverage report` independently enforces the 80% combined
      statement/branch gate (`fail_under` in `pyproject.toml`; target 95).
- [ ] `ruff check src/deepr/` and `ruff format --check src/deepr/` clean.
- [ ] `python scripts/check_file_sizes.py` and
      `python scripts/check_ratchets.py` pass. These are local pre-commit hooks
      as well as blocking CI gates.
- [ ] `mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/core src/deepr/providers src/deepr/mcp src/deepr/security src/deepr/queue src/deepr/storage src/deepr/tools src/deepr/routing src/deepr/worker src/deepr/webhooks src/deepr/a2a src/deepr/skills src/deepr/backends src/deepr/agents src/deepr/evals src/deepr/observability src/deepr/services`
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
- **Dependencies.** Routine automation runs monthly and opens at most one
  grouped minor/patch PR per ecosystem. Major upgrades are deliberate roadmap
  work, not automatically opened branches. Merge green updates promptly and
  close incompatible updates in the same maintenance pass. Do not leave
  dependency branches or PRs sitting open.
- **Nothing merges red.** Require green checks on the current PR head and an
  up-to-date base before merging. Verify CI on the exact resulting `main`
  commit afterward; an earlier green run does not validate a later revision.
- **Hosted CI has a separate billing boundary.** Workflow jobs have explicit
  timeouts, but Deepr's `$5` application ledger cannot cap GitHub Actions.
  Keep the repository public on standard hosted runners, or disable paid
  Actions and remove payment authority at the GitHub account or organization.
  A GitHub budget alert alone is not a hard real-time stop.

## Version and release progression

The [active release plan](ROADMAP.md#active-release-plan) assigns one coherent
outcome and one evidence gate to each minor version. It is not a timeline. Do
not add day, sprint, week, quarter, or release-date estimates to active plans.

1. Keep incomplete work under `Unreleased`; do not bump versions to signal
   progress.
2. Use a patch for a compatible defect, security correction, dependency update,
   packaging fix, or documentation correction. A patch cannot add spend,
   mutation, or remote-control authority.
3. Use a minor version only after its named promotion gate passes. If the gate
   fails, preserve the evidence and keep the surface experimental or blocked.
4. When the candidate is complete, update the package, plugin, fixtures,
   lockfile, release docs, and changelog to one exact version. Regenerate
   `packages/deepr-agent-plugin/SHA256SUMS` after changing plugin content or
   versions, then run the plugin package tests before pushing. Run the full
   Definition of Done before merging.
5. Tag only the exact green `main` commit. Build and verify the release
   artifacts, publish the matching GitHub Release, validate the public
   installer, and confirm the installed CLI reports that version.
6. Record a failed live validation in the roadmap and fix it in the next patch.
   Never move or reuse a published tag to hide the finding.

## Code style

- **Formatter / linter**: ruff (line length 120). Pre-commit enforces it.
- **Types**: `core/`, `providers/`, `mcp/`, `security/`, `queue/`, `storage/`, `tools/`, `routing/`, `worker/`, `webhooks/`, `a2a/`, the importable `deepr.skills` package, `backends/`, `agents/`, `evals/`, `observability/`, and `services/` are `mypy --strict`-clean and
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
python -m pytest tests/unit/ --ignore=tests/data -q --cov=deepr --cov-report=term
python -m coverage report                                                 # independent coverage gate
python -m pytest tests/unit/test_config -v                                  # one area
```

Tests must pass with **no API keys and no .env** - a test that only passes
when a dev key happens to be set is a regression (it has happened twice).
The dev test environment disables outbound sockets by default; tests that need
network must live under `tests/integration/` and the live-test opt-in.

## Project structure

- `src/deepr/` - main package: `cli/` (Click commands), `core/` (orchestration,
  costs, context), `providers/` (model integrations), `experts/` (domain
  expert system), `mcp/` (MCP server), `services/`, `storage/`, `queue/`, `tools/`.
- `docs/` - guides; `docs/design/` (feature design docs); `docs/decisions/`
  (ADRs).
- `deploy/` - a supported local MCP container plus mechanically inert cloud
  reference markers. No cloud provisioning surface ships in v2.40.
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
