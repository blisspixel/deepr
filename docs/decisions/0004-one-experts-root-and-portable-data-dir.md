# 4. One experts root, and a portable data directory

Date: 2026-06-13
Status: accepted

Amended: 2026-07-10. Portability through a synced folder is supported for
sequential device use only. Generic file sync does not provide safe concurrent
writers. See
[multi-device-expert-continuity.md](../design/multi-device-expert-continuity.md).

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
   else `~/.deepr/experts`. Every expert component derives its location from
   it; no module computes an experts path any other way. Exposed as
   `load_config()["experts_dir"]`.
2. **Guided setup coordinates three roots.** `deepr init --data-dir PATH`
   writes `DEEPR_DATA_DIR=PATH`, `DEEPR_EXPERTS_PATH=PATH/experts`, and
   `DEEPR_REPORTS_PATH=PATH/reports`. Setting `DEEPR_DATA_DIR` manually
   relocates experts and operational runtime artifacts but not reports, which
   retain their explicit `DEEPR_REPORTS_PATH` contract. `deepr doctor` shows
   the resolved expert and report roots. Synced roots support sequential use
   only: stop services, use one writer, and wait for sync before switching.
3. **Backward compatible defaults.** Without overrides, experts resolve under
   `~/.deepr/experts`, while reports and operational runtime artifacts retain
   their established `data/reports` and `data` defaults. No migration is
   forced.
4. **A guard test enforces completeness:** no production module may hardcode
   `data/experts`; it must call `experts_root()`. This is the safety net
   against the split-store failure mode.

### What syncs, and what stays machine-local

Portable when their configured roots are inside the synced folder: **experts**
(profiles, beliefs, knowledge, memory, graph, conversations, documents),
**reports**, and every runtime artifact resolved through `DEEPR_DATA_DIR`.
The runtime group currently includes queues, traces, observability artifacts,
benchmark caches, security state, and several MCP state databases. They are
not machine-local when the entire data root is synced, so the one-writer and
completed-sync rule applies to Deepr services as well as expert commands.

The **cost ledger** and **capacity ledger** have dedicated root overrides and
should remain machine-specific because concurrent writes would corrupt spend
or capability evidence. Future configuration should separate portable expert
knowledge from operational runtime state by default.

## Consequences

- Experts become relocatable through their canonical resolver. Guided setup
  coordinates expert, report, and runtime roots under one selected folder for
  sequential cross-machine use.
- Concurrent offline mutation remains unsupported until canonical expert
  writes use device-partitioned, mergeable event journals.
- A large but mechanical centralization (every hardcoded `data/experts` ->
  `experts_root()`), gated by the guard test so no reader is missed.
- The cost ledger's separateness is now a documented invariant, not an
  accident - syncing it is explicitly wrong.
- Future expert storage must use `experts_root()`; the guard test fails the
  build otherwise.

## Alternatives rejected

- **Partial wiring (only BeliefStore/ExpertStore):** rejected - leaves other
  components writing to the old root, splitting the store (the ADR 0001 bug).
- **Treat a whole shared root as concurrently safe:** rejected - operational
  databases and mutable files do not gain cross-device transaction semantics
  from file synchronization.
- **Force report resolution to derive from `DEEPR_DATA_DIR`:** rejected for
  backward compatibility. Guided setup coordinates the explicit report root,
  while existing standalone report configurations remain stable.
