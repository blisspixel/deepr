# Storage and Naming Improvements

## Overview

The report storage system has been upgraded to use human-readable directory names with timestamps, making it much easier to find and organize research reports.

## New Naming Scheme

### Single Research Jobs

**Format:** `YYYY-MM-DD_HHMM_topic-slug_shortid/`

**Example:** `2025-10-29_0825_ai-code-editor-market-analysis_ac2d48e1/`

Structure:
```
data/reports/
  └── 2025-10-29_0825_ai-code-editor-market_ac2d48e1/
      ├── report.md           # Main research report
      └── metadata.json       # Job metadata (prompt, model, cost, etc.)
```

### Multi-Phase Campaigns

**Format:** `campaigns/YYYY-MM-DD_HHMM_campaign-name_shortid/`

**Example:** `campaigns/2025-10-08_1200_ford-ev-strategy_campaign-1759970251/`

Structure:
```
data/reports/campaigns/
  └── 2025-10-08_1200_ford-ev-strategy_1759970251/
      ├── campaign_summary.md
      ├── campaign_results.json
      ├── metadata.json
      └── task-1_market-research/
          ├── report.md
          └── metadata.json
```

## Benefits

1. **Chronological sorting** - Date prefix enables natural time-based browsing
2. **Human-readable** - Topic visible at a glance without opening files
3. **Unique** - Short ID suffix prevents naming collisions
4. **Organized** - Campaigns separated into dedicated subfolder
5. **Searchable** - metadata.json enables programmatic search and filtering

## Metadata File

Each report directory contains a `metadata.json` with:

```json
{
  "job_id": "ac2d48e1-51c7-4344-b556-143a358c0132",
  "created_at": "2025-10-29T08:25:00.000Z",
  "filename": "report.md",
  "content_type": "text/markdown",
  "size_bytes": 15420,
  "prompt": "Analyze AI code editor market as of October 2025",
  "model": "o3-deep-research",
  "status": "completed",
  "provider_job_id": "chatcmpl-xyz123",
  "cost": 2.45,
  "tokens_used": 18500
}
```

## Migration Utility

### Check Current Status

```bash
deepr migrate stats
```

Output:
```
Report Organization Statistics

Organized reports:      0 (timestamped, readable names)
Legacy directories:    30 (UUID-only)
Legacy flat files:     11 (*.md in root)
Campaigns:              0 (multi-phase research)

Organization: 0.0% of reports use new format

[!] Run 'deepr migrate organize' to clean up legacy reports
```

### Organize Legacy Reports

```bash
# Dry run (preview changes)
deepr migrate organize --dry-run

# Execute migration
deepr migrate organize
```

This moves legacy reports to `data/reports/_legacy_archive/` to keep your reports directory clean.

## Implementation Details

### Backwards Compatibility

The storage system maintains full backwards compatibility with legacy formats:

- **UUID-only directories** - System searches for existing directories
- **Flat files** - Legacy *.md files are still accessible
- **Campaign IDs** - Old campaign-* naming is supported

### Slug Generation

Topic slugs are generated from the research prompt:

1. Take first 50 characters of prompt
2. Convert to lowercase
3. Remove special characters (keep alphanumeric and spaces)
4. Replace spaces with hyphens
5. Trim to 40 characters maximum

**Examples:**
- "Analyze AI code editors" → `analyze-ai-code-editors`
- "What should Ford do in EVs for 2026?" → `what-should-ford-do-in-evs-for-2026`
- "Context injection best practices (Python)" → `context-injection-best-practices-python`

### Short ID Extraction

- **UUIDs:** Last 8 characters (e.g., `ac2d48e1` from full UUID)
- **Campaign IDs:** First 12 characters after "campaign-" prefix

## Future Enhancements

Potential future additions:

- **Search by metadata** - `deepr research search --prompt "AI editors" --cost "<$3"`
- **Export knowledge packages** - `deepr research export <job-id> --format zip`
- **Auto-tagging** - Automatically extract tags/topics from reports
- **Batch renaming** - Update legacy reports to new naming scheme (optional)

## Technical Notes

### Storage Backend Changes

Modified files:
- `deepr/storage/local.py` - Added readable naming logic
- `deepr/cli/commands/research.py` - Pass metadata on save
- `deepr/worker/poller.py` - Include metadata in worker saves
- `deepr/services/batch_executor.py` - Campaign metadata handling

### Key Methods

- `_create_readable_dirname()` - Generates human-readable directory names
- `_get_job_dir()` - Resolves job IDs to directories (supports legacy + new)
- `save_report()` - Enhanced to create metadata.json automatically

## Migration Path

For new installations:
- All reports use new naming automatically
- No action required

For existing installations:
1. Run `deepr migrate stats` to assess current state
2. Run `deepr migrate organize --dry-run` to preview
3. Run `deepr migrate organize` to archive legacy reports
4. New reports will use readable names going forward

Legacy reports remain accessible in `_legacy_archive/` if needed.
