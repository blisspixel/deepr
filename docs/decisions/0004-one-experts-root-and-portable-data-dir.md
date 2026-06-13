# 4. One experts root, and a portable data directory

Date: 2026-06-13
Status: accepted

## Context

Experts and reports are the artifacts users own and want to keep across
machines - the natural ask is to point deepr at a synced folder (OneDrive,
Dropbox, iCloud Drive) so experts and research follow you. Two gaps blocked
that:

1. **Reports** were already unified to one config root (ADR 0001,
   `load_config()["results_dir"]`, env `DEEPR_REPORTS_PATH`).
2. **Experts** were not: ~19 components (`BeliefStore`, `ExpertStore`,
   `HierarchicalMemory`, `LazyGraphRAG`, `KnowledgeConsolidation`,
   `thought_stream`, `dspy_pipeline`, `health_check`, `profile`,
   `metacognition`, `temporal_knowledge`, `skills/manager`, the CLI, ...) each
   hardcoded `Path("data/experts")`. `settings.data_dir` (`DEEPR_DATA_DIR`,
   default `data`) existed but nothing consumed it.

Hardcoding the root in many places is the exact failure mode ADR 0001 fixed
for reports: if one reader uses a different root, the store splits and data
silently goes missing (this shipped as a real bug once). So making experts
portable requires *complete* centralization, not a partial wiring.

## Decision

1. **One experts root, one source of truth:** `deepr.config.experts_root()`
   resolves `DEEPR_EXPERTS_PATH` if set, else `<DEEPR_DATA_DIR>/experts`,
   default `data/experts`. Every expert component derives its location from
   it; no module computes an experts path any other way. Exposed as
   `load_config()["experts_dir"]`.
2. **`DEEPR_DATA_DIR` is the single knob.** Experts derive from it; reports
   already honor `DEEPR_REPORTS_PATH` (which `deepr init` sets to
   `<data_dir>/reports`). Point `DEEPR_DATA_DIR` at a synced folder and both
   move; `deepr init` writes the env, `deepr doctor` shows the resolved roots,
   `deepr migrate` relocates existing data.
3. **Backward compatible.** Default `DEEPR_DATA_DIR=data` -> `data/experts`,
   identical to today. Data only moves when a path is set, so existing installs
   are untouched and no migration is forced.
4. **A guard test enforces completeness:** no production module may hardcode
   `data/experts`; it must call `experts_root()`. This is the safety net
   against the split-store failure mode.

### What syncs, and what stays machine-local

Portable (synced folder): **experts** (profiles, beliefs, knowledge, memory,
graph, conversations, documents) and **reports**. These are the artifacts a
user owns and consults across machines.

Deliberately NOT synced (machine-local): the **cost ledger** (append-only;
concurrent writes from two machines into one synced file corrupt it and break
anomaly detection - it must stay per-machine and has its own
`DEEPR_COST_DATA_DIR`), the **research queue** (in-flight, machine-bound jobs),
**traces / observability / benchmark caches**, and **MCP state DBs**. These are
operational, not the user's portable knowledge.

## Consequences

- Experts become portable with one env var; experts + reports can live in a
  synced folder and work across machines.
- A large but mechanical centralization (every hardcoded `data/experts` ->
  `experts_root()`), gated by the guard test so no reader is missed.
- The cost ledger's separateness is now a documented invariant, not an
  accident - syncing it is explicitly wrong.
- Future expert storage must use `experts_root()`; the guard test fails the
  build otherwise.

## Alternatives rejected

- **Partial wiring (only BeliefStore/ExpertStore):** rejected - leaves other
  components writing to the old root, splitting the store (the ADR 0001 bug).
- **Sync everything under `data/`:** rejected - corrupts the append-only cost
  ledger and syncs machine-bound queue/trace state.
- **Per-component env vars:** rejected - too many knobs; one `DEEPR_DATA_DIR`
  with `experts_root()` as the single resolver is simpler and safer.
