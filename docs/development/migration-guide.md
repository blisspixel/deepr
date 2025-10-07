# Deepr 2.0 Migration Guide

## Overview

Deepr 2.0 represents a complete architectural redesign focused on:
- **Modular design** with clear separation of concerns
- **Multi-cloud support** for both OpenAI and Azure
- **Storage abstraction** enabling local and cloud storage
- **Web application** in addition to CLI
- **Cloud deployment** ready for Azure App Services

## Architecture Changes

### Old Structure (v1.x)
```
deepr/
├── deepr.py (1083 lines - monolithic)
├── manager.py (491 lines)
├── normalize.py
├── style.py
└── utility_convertr.py
```

### New Structure (v2.0)
```
deepr/
├── deepr/
│   ├── __init__.py
│   ├── config.py                # Configuration management
│   │
│   ├── providers/               # AI provider abstraction
│   │   ├── base.py
│   │   ├── openai_provider.py
│   │   └── azure_provider.py
│   │
│   ├── storage/                 # Storage backend abstraction
│   │   ├── base.py
│   │   ├── local.py
│   │   └── blob.py
│   │
│   ├── core/                    # Business logic
│   │   ├── research.py
│   │   ├── jobs.py
│   │   ├── reports.py
│   │   └── documents.py
│   │
│   ├── webhooks/                # Webhook handling
│   │   ├── server.py
│   │   └── tunnel.py
│   │
│   ├── formatting/              # Output formatting
│   │   ├── normalize.py
│   │   ├── style.py
│   │   └── converters.py
│   │
│   ├── cli/                     # CLI interface
│   │   └── main.py
│   │
│   └── web/                     # Web application
│       ├── app.py
│       ├── routes/
│       └── templates/
│
├── requirements/
│   ├── base.txt
│   ├── cli.txt
│   ├── web.txt
│   └── dev.txt
│
└── deployment/
    └── azure/
```

## Migration Steps

### Step 1: Install New Dependencies

```bash
# For CLI only
pip install -r requirements/cli.txt

# For web application
pip install -r requirements/web.txt

# For development
pip install -r requirements/dev.txt
```

### Step 2: Update Configuration

**Old (v1.x):**
```bash
# .env file
OPENAI_API_KEY=sk-...
```

**New (v2.0):**
```bash
# .env file
DEEPR_PROVIDER=openai              # or azure
DEEPR_STORAGE=local                # or blob
DEEPR_ENVIRONMENT=local            # or cloud

# OpenAI Configuration
OPENAI_API_KEY=sk-...

# Azure Configuration (if using Azure)
AZURE_OPENAI_KEY=...
AZURE_OPENAI_ENDPOINT=https://...
AZURE_DEPLOYMENT_O3=...
AZURE_DEPLOYMENT_O4_MINI=...

# Azure Blob Storage (if using blob storage)
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_STORAGE_CONTAINER=reports
```

### Step 3: Update Code Usage

**Old CLI Usage (v1.x):**
```bash
python deepr.py --research "Your prompt here"
```

**New CLI Usage (v2.0):**
```bash
deepr --research "Your prompt here"

# Or with Python
python -m deepr.cli --research "Your prompt here"
```

**Programmatic Usage (v2.0):**
```python
import asyncio
from deepr import AppConfig
from deepr.providers import create_provider
from deepr.storage import create_storage
from deepr.core import ResearchOrchestrator, DocumentManager, ReportGenerator, JobManager

async def main():
    # Load configuration
    config = AppConfig.from_env()

    # Initialize components
    provider = create_provider(
        config.provider.type,
        api_key=config.provider.openai_api_key,  # or azure_api_key
        endpoint=config.provider.azure_endpoint  # for Azure
    )

    storage = create_storage(
        config.storage.type,
        base_path=config.storage.local_path  # or connection_string for blob
    )

    # Create orchestrator
    doc_manager = DocumentManager()
    report_gen = ReportGenerator()
    orchestrator = ResearchOrchestrator(provider, storage, doc_manager, report_gen)

    # Submit research
    job_id = await orchestrator.submit_research(
        prompt="Your research question",
        model="o3-deep-research"
    )

    print(f"Job submitted: {job_id}")

asyncio.run(main())
```

### Step 4: Migrate Custom Scripts

If you have custom scripts using the old `deepr.py`, update them to use the new modular API:

**Before:**
```python
from deepr import submit_research_query, download_report

job_id = submit_research_query(prompt, webhook_url)
download_report(job_id)
```

**After:**
```python
from deepr import AppConfig
from deepr.providers import create_provider
from deepr.core import ResearchOrchestrator

config = AppConfig.from_env()
provider = create_provider(config.provider.type)
# ... initialize orchestrator
job_id = await orchestrator.submit_research(prompt)
await orchestrator.process_completion(job_id)
```

## Feature Comparison

| Feature | v1.x | v2.0 |
|---------|------|------|
| OpenAI Support | ✓ | ✓ |
| Azure OpenAI Support | ✗ | ✓ |
| Local Storage | ✓ | ✓ |
| Azure Blob Storage | ✗ | ✓ |
| CLI Interface | ✓ | ✓ |
| Web Interface | ✗ | ✓ |
| Batch Processing | ✓ | ✓ |
| Document Upload | ✓ | ✓ |
| Multi-format Output | ✓ | ✓ |
| Cost Tracking | Basic | Enhanced |
| Job Management | CLI only | CLI + Web |
| Cloud Deployment | ✗ | ✓ |

## Configuration Options

### Provider Configuration

**OpenAI:**
```python
config = AppConfig.from_env()
provider = create_provider(
    "openai",
    api_key="sk-...",
    base_url="https://api.openai.com/v1",  # optional
    organization="org-..."  # optional
)
```

**Azure OpenAI:**
```python
provider = create_provider(
    "azure",
    api_key="...",
    endpoint="https://your-resource.openai.azure.com/",
    api_version="2024-10-01-preview",
    deployment_mappings={
        "o3-deep-research": "my-o3-deployment",
        "o4-mini-deep-research": "my-o4-mini-deployment"
    }
)
```

**Azure with Managed Identity:**
```python
provider = create_provider(
    "azure",
    endpoint="https://your-resource.openai.azure.com/",
    use_managed_identity=True
)
```

### Storage Configuration

**Local Storage:**
```python
storage = create_storage("local", base_path="./reports")
```

**Azure Blob Storage:**
```python
storage = create_storage(
    "blob",
    connection_string="DefaultEndpointsProtocol=https;...",
    container_name="reports"
)
```

**Azure Blob with Managed Identity:**
```python
storage = create_storage(
    "blob",
    account_url="https://mystorageaccount.blob.core.windows.net",
    container_name="reports",
    use_managed_identity=True
)
```

## Breaking Changes

### 1. Module Imports
- `from deepr import ...` now imports from modular structure
- Direct imports from `deepr.py` no longer work

### 2. Function Signatures
- Most functions now `async` and require `await`
- Configuration passed via `AppConfig` instead of global variables

### 3. File Locations
- Reports organized by `job_id/{filename}` structure
- Job log format enhanced with provider and metadata fields

### 4. Environment Variables
- Prefixed with `DEEPR_` for namespacing
- More granular configuration options

## Backward Compatibility

### Legacy CLI Support

The old `deepr.py` and `manager.py` files are preserved in the root directory for backward compatibility. However, they are deprecated and will be removed in v3.0.

**To use legacy CLI:**
```bash
python deepr.py --research "Your prompt"
python manager.py --list
```

**Migration timeline:**
- v2.0-v2.9: Legacy files available but deprecated
- v3.0+: Legacy files removed, must use new architecture

### Configuration File Migration

A migration tool is provided to convert old `.env` files:

```bash
python -m deepr.cli migrate-config --input .env --output .env.new
```

## Testing Your Migration

### 1. Test Provider Connection
```bash
python -m deepr.cli test-provider
```

### 2. Test Storage Backend
```bash
python -m deepr.cli test-storage
```

### 3. Submit Test Job
```bash
deepr --research "Test prompt" --model o4-mini-deep-research
```

### 4. Verify Reports
```bash
# List jobs
deepr-manager --list

# View report
deepr-manager --view JOB_ID
```

## Troubleshooting

### Issue: "Module not found: deepr"
**Solution:** Reinstall package with `pip install -e .`

### Issue: "Provider configuration invalid"
**Solution:** Check environment variables match new format (DEEPR_PROVIDER, etc.)

### Issue: "Storage backend connection failed"
**Solution:** Verify credentials for Azure services if using blob storage

### Issue: "Async function not awaited"
**Solution:** Wrap calls in `asyncio.run()` or use within async context

## Getting Help

- **Documentation:** See `docs/` directory
- **Examples:** See `examples/` directory
- **Issues:** https://github.com/blisspixel/deepr/issues
- **Azure Setup:** See `docs/azure-deep-research.md`

## Next Steps

1. Review new architecture in `docs/architecture.md`
2. Explore web interface in `docs/web-application.md`
3. Set up Azure deployment with `docs/deployment.md`
4. Check out examples in `examples/`
