# Deepr Scripts

Utility scripts for managing Deepr environments.

## Local Environment

### Setup
```bash
python scripts/setup_local.py
```

Creates local directories, initializes SQLite database, and generates .env template.

### Cleanup
```bash
# Clean queue, results, and logs (with prompts)
python scripts/cleanup_local.py

# Clean specific items
python scripts/cleanup_local.py --queue
python scripts/cleanup_local.py --results
python scripts/cleanup_local.py --logs
python scripts/cleanup_local.py --uploads

# Clean everything without prompts
python scripts/cleanup_local.py --all -f

# Force cleanup without confirmation
python scripts/cleanup_local.py -f
```

## Azure Environment

### Setup
```bash
# Interactive setup
python scripts/setup_azure.py

# Custom configuration
python scripts/setup_azure.py \
  --resource-group my-deepr \
  --location westus \
  --storage-account mydeeprstorage \
  --servicebus-namespace my-deepr-bus
```

Creates Azure Storage, Service Bus, and generates .env.azure configuration.

**Prerequisites:**
- Azure CLI installed
- Logged in: `az login`
- Active subscription

### Teardown
```bash
# Delete individual resources (with prompts)
python scripts/destroy_azure.py

# Delete entire resource group
python scripts/destroy_azure.py --delete-resource-group

# Force delete without confirmation
python scripts/destroy_azure.py --delete-resource-group -f
```

## Job Management

### Cancel All Active Jobs
```bash
# PowerShell
.\scripts\cancel_all_jobs.ps1

# Python (coming soon)
python scripts/cancel_all_jobs.py
```

### Convert Legacy Reports
```bash
python scripts/convert_legacy_report.py input.txt output.md
```

## Environment Setup

### Setup Environment Paths
```powershell
.\scripts\setup_env.ps1
```

Configures environment variables for local development.
