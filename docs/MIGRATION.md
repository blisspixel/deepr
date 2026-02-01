# Migration Guide

This guide covers migrating from older versions of Deepr to the latest version.

---

## Expert Profile Migration

### Overview

Expert profiles have been refactored to use a cleaner architecture with separate `TemporalState` and `FreshnessChecker` classes. Existing profiles are automatically compatible, but running the migration script ensures optimal performance and adds new schema versioning.

### Running the Migration

```bash
# Preview changes (dry run)
python scripts/migrate_expert_profiles.py --dry-run

# Run migration
python scripts/migrate_expert_profiles.py

# Migrate specific expert
python scripts/migrate_expert_profiles.py --expert "AWS Expert"
```

### What the Migration Does

1. **Adds schema versioning**: Each profile gets a `schema_version` field for future compatibility
2. **Validates structure**: Ensures all required fields are present
3. **Preserves data**: No data is lost; only metadata is added
4. **Creates backups**: Original files are backed up before modification

### Troubleshooting

**"Expert not found" error:**
- Check the expert name matches exactly (case-sensitive)
- Run `deepr expert list` to see available experts

**"Invalid profile structure" error:**
- The profile may be corrupted
- Check `data/experts/{name}/profile.json` manually
- Restore from backup if available

**Migration fails silently:**
- Check `data/experts/{name}/migration.log` for details
- Ensure write permissions on the data directory

---

## Configuration Migration

### Overview

Configuration has been consolidated into `UnifiedConfig` which provides a single source of truth with clear precedence:

1. CLI flags (highest priority)
2. Environment variables
3. Config files
4. Defaults (lowest priority)

### Using UnifiedConfig

The new configuration system is backward compatible. Existing `.env` files and environment variables continue to work.

**View current configuration:**
```bash
deepr config show
```

**Validate configuration:**
```bash
deepr config validate
```

**Use unified config explicitly:**
```bash
deepr config show --unified
```

### Configuration Precedence

```
CLI flags > Environment variables > .env file > defaults
```

Example:
```bash
# This uses the CLI flag, ignoring env vars
deepr research "topic" --provider grok

# This uses DEEPR_PROVIDER env var if set
export DEEPR_PROVIDER=grok
deepr research "topic"
```

### New Configuration Options

The following new options are available:

| Option | Environment Variable | Default | Description |
|--------|---------------------|---------|-------------|
| `daily_budget` | `DEEPR_DAILY_BUDGET` | 25.0 | Daily spending limit |
| `monthly_budget` | `DEEPR_MONTHLY_BUDGET` | 200.0 | Monthly spending limit |
| `default_provider` | `DEEPR_PROVIDER` | openai | Default AI provider |
| `default_model` | `DEEPR_MODEL` | o4-mini | Default model |
| `trace_enabled` | `DEEPR_TRACE` | false | Enable trace logging |

### Troubleshooting

**"Configuration validation failed" error:**
- Run `deepr config validate` to see specific issues
- Check API keys are set correctly
- Ensure budget values are positive numbers

**API key not recognized:**
- Check for extra spaces or quotes in `.env` file
- Verify the key format matches the provider's format
- Try setting the key directly in environment

---

## New Features After Migration

After migrating, you'll have access to:

### Semantic Commands
```bash
deepr check "claim to verify"
deepr make docs --files "*.py"
deepr make strategy "business goal"
deepr agentic research "research goal" --rounds 3
deepr help verbs
```

### Cost Dashboard
```bash
deepr costs                    # View cost summary
deepr costs --breakdown        # By provider/operation
deepr costs --alerts           # Check budget alerts
```

### Provider Status
```bash
deepr providers status         # View provider health
deepr providers status --history  # View fallback history
```

### Enhanced Expert Features
```bash
deepr expert chat "Name" --verbose   # See reasoning
deepr expert chat "Name" --timeline  # See thought evolution
deepr expert info "Name" --beliefs   # View belief system
```

---

## Breaking Changes

### v2.0 Breaking Changes

1. **ExpertProfile internal structure**: The `temporal_state` and `freshness_checker` are now separate objects. This is handled automatically by the migration script.

2. **Configuration file location**: Config files should now be in `.deepr/` directory. Old locations still work but are deprecated.

3. **MCP tool names**: Some MCP tools have been renamed for consistency:
   - `query_expert` → `deepr_query_expert`
   - `list_experts` → `deepr_list_experts`
   - `get_expert_info` → `deepr_get_expert_info`

### Deprecation Warnings

The following are deprecated and will be removed in v3.0:

- `deepr config` without subcommand (use `deepr config show`)
- `--verbose` global flag (use command-specific `--verbose`)
- Direct access to `ExpertProfile.temporal_fields` (use `temporal_state` property)

---

## Getting Help

If you encounter issues during migration:

1. Check this guide for common solutions
2. Run `deepr doctor` to diagnose configuration issues
3. Check logs in `data/logs/` for detailed error messages
4. Open an issue on GitHub with:
   - Deepr version (`deepr --version`)
   - Error message
   - Steps to reproduce

---

## Rollback

If you need to rollback after migration:

### Expert Profiles
```bash
# Restore from backup
cp data/experts/{name}/profile.json.bak data/experts/{name}/profile.json
```

### Configuration
```bash
# Remove unified config
rm .deepr/config.json

# Deepr will fall back to environment variables and defaults
```

---

**Last Updated:** January 2026
