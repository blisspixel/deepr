# Deepr File Reorganization Plan

## Current State - Files Need Organizing

### Root Directory (Messy)
```
deepr/
├── deepr.py                        # DEPRECATED - Keep for now, mark clearly
├── manager.py                      # DEPRECATED - Keep for now
├── normalize.py                    # DUPLICATE - Already in deepr/formatting/
├── style.py                        # DUPLICATE - Already in deepr/formatting/
├── utility_convertr.py             # UTILITY - Should move to scripts/
├── Utility_Cancell_Active_Jobs.ps1 # UTILITY - Move to scripts/
├── set-env-paths.ps1               # UTILITY - Move to scripts/
├── queue.txt                       # EXAMPLE - Move to examples/
├── last_response.json              # TEMP FILE - Add to .gitignore
├── system.message.json             # CONFIG - Rename to system_message.json (fix typo)
├── requirements.txt                # OLD - Already have requirements/ folder
├── setup.py                        # OLD - Using pyproject.toml now
├── Documentation Using Docs.txt    # DOC - Move to docs/legacy/ or delete
├── to do.txt                       # TODO - Move to docs/legacy/ or delete
```

### What We've Built (Good)
```
deepr/
├── deepr/                          # NEW MODULAR CODE ✓
├── docs/                           # NEW DOCUMENTATION ✓
├── requirements/                   # NEW DEP MANAGEMENT ✓
├── tests/                          # NEW TEST SUITE ✓
├── deployment/                     # NEW DEPLOYMENT CONFIGS ✓
└── scripts/                        # NEW UTILITIES LOCATION ✓
```

---

## Reorganization Actions

### 1. Mark Deprecated Files (Don't Delete Yet)

Create warning headers in old files:

**deepr.py:**
```python
"""
⚠️  DEPRECATED - This file is preserved for backward compatibility only.

For new code, use the modular API:
    from deepr import AppConfig
    from deepr.providers import create_provider
    ...

This file will be removed in v3.0.
See: docs/migration-guide.md
"""
```

**manager.py:**
```python
"""
⚠️  DEPRECATED - This file is preserved for backward compatibility only.

For new code, use:
    from deepr.core import JobManager
    ...

This file will be removed in v3.0.
See: docs/migration-guide.md
"""
```

### 2. Move Utility Scripts

```bash
# PowerShell utilities
mv Utility_Cancell_Active_Jobs.ps1 scripts/cancel_all_jobs.ps1
mv set-env-paths.ps1 scripts/set_env_paths.ps1

# Python utilities
mv utility_convertr.py scripts/convert_legacy_report.py

# Add header to each explaining usage
```

### 3. Move Example Files

```bash
mkdir -p examples/batch_processing
mv queue.txt examples/batch_processing/sample_queue.txt

# Create examples README
```

### 4. Clean Up Config Files

```bash
# Fix typo in system message file
mv system.message.json system_message.json

# Mark old files
echo "# DEPRECATED - See requirements/ folder" > requirements.txt.deprecated
mv requirements.txt requirements.txt.deprecated

echo "# DEPRECATED - Using pyproject.toml" > setup.py.deprecated
mv setup.py setup.py.deprecated
```

### 5. Move Documentation

```bash
mkdir -p docs/legacy
mv "Documentation Using Docs.txt" docs/legacy/
mv "to do.txt" docs/legacy/

# Or delete if no longer relevant
```

### 6. Update .gitignore

```bash
# Add to .gitignore
last_response.json
*.deprecated
backups/
logs/*.jsonl
reports/*
!reports/.gitkeep
queue/
*.db
*.db-journal
.env
.env.local
__pycache__/
*.pyc
*.pyo
```

### 7. Remove Duplicate Files

```bash
# normalize.py and style.py are now in deepr/formatting/
# Can delete root copies AFTER verifying imports work

# Test imports first:
python -c "from deepr.formatting import normalize_markdown, apply_styles_to_doc"

# If successful, remove duplicates:
rm normalize.py
rm style.py
```

---

## Final Structure (Clean)

```
deepr/
├── .env                            # Local config (gitignored)
├── .gitignore                      # Updated
├── pyproject.toml                  # Main package config
├── system_message.json             # System message config
├── README.md                       # Main readme (update needed)
├── README_V2_PREVIEW.md            # New architecture preview
├── LICENSE                         # MIT license
│
├── deepr/                          # MAIN PACKAGE ✓
│   ├── __init__.py
│   ├── config.py
│   ├── providers/
│   ├── storage/
│   ├── queue/                      # NEW ✓
│   ├── core/
│   ├── webhooks/
│   ├── formatting/
│   ├── cli/
│   └── web/
│
├── docs/                           # DOCUMENTATION ✓
│   ├── architecture-vision.md      # NEW ✓
│   ├── azure-deep-research.md      # NEW ✓
│   ├── migration-guide.md          # NEW ✓
│   └── legacy/                     # Old docs archived
│
├── tests/                          # TEST SUITE ✓
│   ├── conftest.py                 # NEW ✓
│   ├── unit/
│   │   ├── test_providers/         # NEW ✓
│   │   ├── test_storage/
│   │   └── test_queue/             # NEW ✓
│   └── integration/
│
├── requirements/                   # DEPENDENCIES ✓
│   ├── base.txt
│   ├── cli.txt
│   ├── web.txt
│   └── dev.txt
│
├── scripts/                        # UTILITIES ✓
│   ├── cancel_all_jobs.ps1         # Moved
│   ├── set_env_paths.ps1           # Moved
│   └── convert_legacy_report.py    # Moved
│
├── examples/                       # EXAMPLES (NEW)
│   ├── README.md
│   ├── simple_research.py
│   ├── batch_processing/
│   │   └── sample_queue.txt
│   └── azure_deployment/
│
├── deployment/                     # DEPLOYMENT ✓
│   ├── azure/
│   │   ├── main.bicep
│   │   ├── app-service.bicep
│   │   └── storage.bicep
│   └── docker/
│       ├── Dockerfile
│       └── docker-compose.yml
│
├── logs/                           # Generated (gitignored)
├── reports/                        # Generated (gitignored)
├── queue/                          # Generated (gitignored)
├── backups/                        # Generated (gitignored)
│
└── DEPRECATED/                     # LEGACY CODE
    ├── deepr_v1.py                 # Renamed from deepr.py
    ├── manager_v1.py               # Renamed from manager.py
    └── README.md                   # Explains what's here
```

---

## Migration Commands

### Step 1: Backup Everything
```bash
mkdir -p backups/pre-reorganization
cp -r . backups/pre-reorganization/
```

### Step 2: Create New Directories
```bash
mkdir -p scripts examples/batch_processing docs/legacy DEPRECATED
```

### Step 3: Move Files
```bash
# Utilities
mv Utility_Cancell_Active_Jobs.ps1 scripts/cancel_all_jobs.ps1 2>/dev/null
mv set-env-paths.ps1 scripts/set_env_paths.ps1 2>/dev/null
mv utility_convertr.py scripts/convert_legacy_report.py 2>/dev/null

# Examples
mv queue.txt examples/batch_processing/sample_queue.txt 2>/dev/null

# Legacy docs
mv "Documentation Using Docs.txt" docs/legacy/ 2>/dev/null
mv "to do.txt" docs/legacy/ 2>/dev/null

# Fix config typo
if [ -f "system.message.json" ]; then
    mv system.message.json system_message.json
fi

# Deprecate old files (don't delete yet)
mkdir -p DEPRECATED
cp deepr.py DEPRECATED/deepr_v1.py
cp manager.py DEPRECATED/manager_v1.py
```

### Step 4: Update Imports
Check all imports and fix any that reference old locations:
```bash
# Find files that might need updating
grep -r "from normalize import" .
grep -r "from style import" .
grep -r "import normalize" .
grep -r "import style" .

# Should all be:
# from deepr.formatting import normalize_markdown, apply_styles_to_doc
```

### Step 5: Add Deprecation Notices
Add warning comments to deepr.py and manager.py at the top

### Step 6: Test Everything
```bash
# Run tests to ensure nothing broke
pytest tests/

# Try importing
python -c "from deepr import AppConfig; from deepr.providers import create_provider"

# Try old CLI (should still work)
python deepr.py --help
python manager.py --help
```

### Step 7: Remove Duplicates (After Testing)
```bash
# Only after confirming imports work
rm normalize.py 2>/dev/null
rm style.py 2>/dev/null
```

### Step 8: Clean Up Build Artifacts
```bash
rm -rf build/ dist/ *.egg-info/
rm -rf __pycache__/ deepr/__pycache__/
```

---

## Updated .gitignore

```gitignore
# Environment
.env
.env.local
.env.*.local

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Generated files
last_response.json
logs/
reports/
queue/
backups/
*.db
*.db-journal

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Deprecated
*.deprecated
```

---

## Communication Plan

### README.md Update
Add prominent notice at top:
```markdown
# Deepr 2.0

⚠️  **MAJOR ARCHITECTURE CHANGE** - If upgrading from v1.x, see [Migration Guide](docs/migration-guide.md)

## Quick Start (v2.0)
[New instructions here]

## Legacy Version (v1.x)
The old CLI is preserved in `DEPRECATED/` folder for reference.
See [Migration Guide](docs/migration-guide.md) for upgrading.
```

### Create DEPRECATED/README.md
```markdown
# Deprecated Files

These files are from Deepr v1.x and are preserved for reference only.

**Do not use these files for new development.**

For v2.0 architecture, see main README.md

## Files
- `deepr_v1.py` - Original monolithic implementation
- `manager_v1.py` - Original job manager

## Migration
See ../docs/migration-guide.md
```

---

## Testing Checklist

After reorganization, verify:

- [ ] `pytest tests/` passes
- [ ] `python -c "from deepr import AppConfig"` works
- [ ] `python -c "from deepr.providers import create_provider"` works
- [ ] `python -c "from deepr.queue import SQLiteQueue"` works
- [ ] Old CLI still runs: `python deepr.py --help`
- [ ] Scripts work: `python scripts/convert_legacy_report.py`
- [ ] Documentation links not broken
- [ ] .gitignore covers all generated files
- [ ] No import errors in any module

---

This reorganization will make the codebase much cleaner and clearer about what's legacy vs. new architecture.
