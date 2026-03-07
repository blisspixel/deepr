# Archive Policy

Use this project-level archive policy when cleaning docs.

## What goes to archive
- superseded planning docs
- session notes and one-off analysis writeups
- completed implementation notes no longer needed for active onboarding

## Where archived files live
- local archive folder: `docs/archive/` (git-ignored)

Because `docs/archive/` is intentionally ignored, archived files are not part of the tracked docs set.
If a historical document must remain versioned, keep it in `docs/` and mark it clearly as archived.

## Recent archival actions
- Moved `docs/MCP_REFINEMENT_PLAN.md` to local archive at `docs/archive/analysis/MCP_REFINEMENT_PLAN.md`.
- Moved `docs/MIGRATION.md` -> `docs/archive/migration/MIGRATION.md` (legacy migration guidance).
- Moved `docs/mcp-client-architecture.md` -> `docs/archive/analysis/mcp-client-architecture.md` (historical design note).
- Moved `docs/PERFORMANCE.md` -> `docs/archive/analysis/PERFORMANCE.md` (superseded by active benchmark/model docs).
