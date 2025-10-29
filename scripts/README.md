# Deepr Scripts

Utility scripts for installation, environment management, and development workflows.

## Installation Scripts

### Linux/macOS Installation
```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

Installs Deepr with `pip install -e .` and provides PATH configuration guidance.

### Windows Installation
```batch
scripts\install.bat
```

Installs Deepr on Windows with proper PATH setup.

### Build Script (Windows)
```batch
scripts\build.bat
```

Creates a Windows distribution build.

### Makefile (Development)
```bash
# Install in development mode
make install

# Run tests
make test

# Clean build artifacts
make clean

# Format code
make format

# Type checking
make typecheck
```

Development automation for Linux/macOS.

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

## Azure Environment (Optional)

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
.\scripts\Utility_Cancell_Active_Jobs.ps1
```

Cancels all active research jobs in the queue.

### Monitor Research Jobs
```bash
python scripts/monitor_research_jobs.py
```

Real-time monitoring of research job status and progress.

### Submit Documentation Research
```bash
python scripts/submit_doc_research_jobs.py
```

Batch submission of documentation research jobs.

### Analyze Documentation Gaps
```bash
python scripts/analyze_doc_gaps.py
```

Identifies gaps in documentation coverage.

### Convert Legacy Reports
```bash
python scripts/convert_legacy_report.py input.txt output.md
```

Converts old report formats to current markdown format.

### Check Costs
```bash
python scripts/check_costs.py
```

Analyzes cost usage and spending patterns.

## Testing

### Run All Tests
```bash
# Linux/macOS
./scripts/test_all.sh

# Windows PowerShell
.\scripts\test_all.ps1

# Python
python scripts/test_all.py
```

Runs the complete test suite across all modules.

## Environment Setup

### Setup Environment Paths (Windows)
```powershell
.\scripts\setup_env.ps1
```

Configures environment variables for local development on Windows.
