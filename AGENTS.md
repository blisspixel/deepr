# Deepr - agent project guide

Multi-provider research automation: previews explicit local, plan-quota, and
bounded API capacity, dispatches only when capability and cost are proven, and
builds persistent domain experts (beliefs + confidence + gaps + citations).
Global cheapest-first and automatic metered fallback are not shipped.
Three layers: kernel (`core/`, `providers/`, `queue/`, `routing/`,
`observability/`), primitives (`experts/`, `services/`, `tools/`, `storage/`),
interfaces (`cli/`, `web/`, `mcp/`).

**Approach contract:** [docs/APPROACH.md](docs/APPROACH.md) freezes method-level
claims and refusals. **Executable surface:** [docs/SUPPORTED_SURFACE.md](docs/SUPPORTED_SURFACE.md)
wins for what currently runs. Do not treat roadmap or design notes as shipped
capability.

`ROADMAP.md` is the single source of truth for active work; completed items move to `docs/CHANGELOG.md` at release. Read its Planning Principles before adding features - especially "close the loop before widening it" and "self-improvement is a verification problem".

`CONTRIBUTING.md` is the operating manual: how work goes from idea to shipped (frame -> design note -> small reversible increments -> verify -> ship -> validate) and the **Definition of Done** checklist every change clears. Before a contract-spanning or hard-to-reverse change, write a design note (`docs/design/`) or a decision record (`docs/decisions/`, ADRs) first - the *why*, and the alternatives rejected.

## Working loop and canonical seams

Start with the relevant roadmap gate, current diff/history, contracts, and
callers/tests. Distinguish planned, implemented, tested, released, deployed,
and actually validated behavior; source, configuration, locks, and evidence
outrank stale status prose. Verify change-sensitive facts against current
primary sources before changing provider flags, protocols, or dependencies.
Preserve the Python/Click, React/TypeScript, and existing persistence stack.

Reuse the owning seam under `src/deepr/` before adding another implementation:

- `config.py`: configured data, expert, report, and queue roots.
- `experts/profile_store.py`, `experts/beliefs.py`: profile and belief authority;
  `utils/atomic_io.py`: atomic files and locked durable JSONL appends.
- `providers/registry.py`, `backends/`, `experts/cost_safety.py`: model metadata,
  capacity admission, and spend authority. Interfaces do not create bypasses.
- `mcp/protocol_compat.py`, `mcp/protocol_dispatch.py`: shared wire validation
  and dispatch across transports; `skills/agent_plugin.py`: package validation.

Implement the smallest sound change, reproduce the failure, verify, inspect
the diff adversarially, and prove the user-visible behavior. Update the owning
docs and roadmap/changelog. Repeated failures should strengthen the shared
boundary or regression tests, not add another warning. This file is the shared
agent guide; do not create duplicate tool-specific engineering manifests.

## Dev environment

- Install from `uv.lock`: `uv sync --frozen --extra dev --extra full`. Activate `.venv` before the commands below; on Windows, explicit `.venv/Scripts/python.exe` also avoids global-tool version drift. `[dev]` alone is NOT enough; the suite imports azure/flask/etc. and fails collection without `[full]`. The editable `uv pip install -e ".[dev,full]"` alternative does not itself enforce the lock.
- Tests: `python -m pytest tests/unit/ --ignore=tests/data -q --cov=deepr --cov-report=term`, then `python -m coverage report` to enforce the configured gate independently. The unit suite must pass with **no API keys and no .env**, keeping the socket guard enabled. Do NOT run bare `pytest`: `tests/integration/` hits real provider APIs, fails wholesale without keys, and at least one test polls forever on 401.
- Lint/format: `python -m ruff check src/deepr/` and `python -m ruff format --check src/deepr/`; omit `--check` to apply formatting. Pre-commit uses the pinned Ruff version.
- Code-health ratchets: `python scripts/check_file_sizes.py` and
  `python scripts/check_ratchets.py` (pre-commit and CI block on both). Run them
  before every commit so `main` is never knowingly left red.
- Also run `python scripts/check_paid_api_boundaries.py` and `python scripts/check_docs_consistency.py`.
- Types (blocking CI gate): `python -m mypy --strict --no-warn-unused-ignores --ignore-missing-imports src/deepr/core src/deepr/providers src/deepr/mcp src/deepr/security src/deepr/queue src/deepr/storage src/deepr/tools src/deepr/routing src/deepr/worker src/deepr/webhooks src/deepr/a2a src/deepr/skills`. The rest of the tree is a non-blocking baseline - don't add new errors.
- Coverage: 80% minimum with branch measurement enabled (`fail_under`), ratcheting toward 95. This is coverage.py's combined statement/branch score. New code ships with tests; every bug fix ships with a regression test.
- Do not lower gates, broaden ignores, weaken schemas, or change tests merely to accept incorrect behavior. Separate environment failures from assertion failures and retain their evidence. A focused run does not establish full coverage; an old green CI run does not validate a new diff.
- Plan-quota tests exercise dormant wiring through explicit synthetic adapters and real-registry refusal through unchanged production adapters. Verify refusal before probes, ledger writes, and process launch; never assume a provider stays execution-eligible.
- Frontend changes: use the Node/npm versions in CI and `package.json`; from `src/deepr/web/frontend`, run `npm ci`, `npm run lint`, `npm test`, and `npm run build`. Rendered workflow changes also need the existing browser checks and visual inspection. Protocol/package changes need conformance and clean-wheel stdio smoke evidence from the existing CI scripts, not just schema-shaped fixtures.
- Keep `uv.lock` and `package-lock.json` authoritative. Reuse standard-library/framework/existing dependencies before adding one; verify current stable compatibility, security, licensing, and Windows packaging when an addition or upgrade is justified.

## Hard rules

- **Rules vs agentic: read [docs/plans/AGENTIC_BALANCE.md](docs/plans/AGENTIC_BALANCE.md) before adding a rule or making something agentic, and update it when a decision moves the boundary.** Brittle rules that encode *meaning* (lexical/word-overlap checks used as a verdict) are the most-repeated wrong turn here. Determinism guards form and side-effects (schema, types, ranges, spend, writes, flowchartable control flow); model judgment owns meaning (contradiction, grounding, atomicity, dedup), calibrated before trusted; a lexical check may *route* but never *conclude*.
- **Never make paid API calls** (research runs, evals, embeddings). Production metered dispatch is quarantined even when a caller supplies consent and budget flags. Use write-free previews and offline billing reconciliation only. Budgets are ceilings enforced in code - never weaken a gate to make a test pass. Active examples must keep the binding monthly ceiling at `$5` or less.
- Capacity sources must be described honestly:
  - Works now: local Ollama expert setup and maintenance via `expert make --local`, `expert sync --local`, `expert sync --local --fresh-context`, `expert sync --local --deep-context`, `expert absorb --local`, `eval local`, `eval local-context`, and scored `capacity admit`. Explicit plan-quota commands execute only for adapters whose stored plan auth, native-tool posture, and paid-overage posture pass the deterministic no-surprise-bills gate. No production plan adapter is currently execution-eligible. Claude Code is blocked because managed-policy hooks survive safe mode and cannot be confined by empty model tools or disabled paid overage. The dormant transport retains its auth, Sonnet, empty-tools/MCP, no-persistence, live-overage, quota, and `$0` ledger requirements. See [the containment decision](docs/design/claude-managed-policy-containment.md).
  - Visible/read-only or gated today: metered API requests can be priced, previewed, reserved, accounted, and reconciled from offline provider billing exports, but production paid dispatch remains blocked until a provider-specific authenticated account-control verifier and current credential-identity resolver are installed. `deepr capacity` shows every plan CLI and its reason. Codex, OpenCode, Kiro, Grok, and Antigravity are execution-blocked because native-tool confinement, stored provider provenance, prepaid overage state, or transcript side effects cannot be proven safe before dispatch. Copilot is blocked because it is metered at the margin. A CLI authenticated by an API key is refused as plan capacity. Automatic plan routing is limited to a safety-eligible adapter with a trusted remaining-quota observation; explicit `--plan` never bypasses the safety gate or the live paid-overage check. `DEEPR_SEARXNG_URL` and `DEEPR_HEARTBEAT_URL` remain configuration-visible, but SearXNG search and off-box heartbeat delivery are blocked because their upstream marginal cost cannot be proven before dispatch. `scripts/setup_azure.py` is reference-only and performs no cloud or credential operation.
  - Quarantined compatibility surfaces: local-eval CLI judges such as Grok remain blocked even with `--judge-cli ... --allow-cli-judge`; the legacy allow flag is not spend authority. Python and MCP expert skill execution, including `expert run-skill`, is also inventory-only until runtime network and credential confinement can be proven.
  - Roadmap language must distinguish `works now`, `visible/read-only`, and `planned adapter`. Do not market roadmap capacity as shipped UX.
- The cost ledger is **append-only** and every spend source writes it. No silent-money paths.
- Generated artifacts (expert digests, SKILL.md exports, reports) are **derived views**: regenerable from the structured belief store, never hand-edited as authoritative.
- The reports root is config-sourced: `load_config()["results_dir"]` (env `DEEPR_REPORTS_PATH`, default `data/reports`). Never hardcode a `reports/` path - divergent roots was a real shipped bug.
- `xfail` is disallowed in CI. Don't skip-to-green.
- Windows is a first-class dev platform: UTF-8 console handling, cross-platform paths, no POSIX-only assumptions.

## Conventions

- Conventional commits (`feat:`/`fix:`/`docs:`/`chore:`); single `main` branch.
- **No AI attribution anywhere.** No AI-tool authorship trailers or notes in commits, tags, PRs, releases, code comments, or docs. Commits and releases are authored as the human maintainer, full stop.
- **No emojis and no em/en dashes (`-` style only).** Do not use emoji or `-`/`-` in commit messages, tags, PRs, releases, code, or docs; use a plain hyphen `-` where a dash is needed.
- Live-validation findings get a ROADMAP backlog entry and are checked off with a dated note when fixed.
- Doc counts (test counts, tool counts) are checked by `scripts/check_docs_consistency.py` in CI - update docs when the numbers move.
- **Module shape (readability):** god-files and over-split confetti both hurt.
  Do not extract a file only to clear C901 or the file-size ratchet; extract
  only a named seam with tests. Prefer a package/section map over hop chains.
  Rebuild `.agent/codegraph` before structure work; run
  `python .agent/codegraph/fragmentation_scan.py`. Plan:
  [docs/design/module-shape-and-readability.md](docs/design/module-shape-and-readability.md).
- **Continuity:** keep scratch, logs, intermediate research, and derived indexes
  in the existing gitignored `.agent/`, never credentials. Check the codegraph
  manifest and file hashes before using its map/callers/test links; it is a
  navigation aid, not authority. Inspect source before editing. Preserve a
  bounded task's objective, changed files, decisions, commands/results, and next
  step there across sessions; promote durable conclusions into their existing
  docs, tests, or tracked issue. Do not create a second backlog or instruction tree.
