# Deepr 2.0 Quick Start Guide

**Version:** 2.0.0-alpha
**Status:** Core Infrastructure Ready

## Installation

```bash
# Clone the repository
cd deepr

# Install for CLI usage
pip install -r requirements/cli.txt

# Or install for web application development
pip install -r requirements/web.txt

# Or install for development
pip install -r requirements/dev.txt
```

## Configuration

### 1. Create `.env` file

**For OpenAI:**
```bash
# Provider Configuration
DEEPR_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here

# Storage Configuration
DEEPR_STORAGE=local
DEEPR_REPORTS_PATH=./reports

# Optional
DEEPR_ENVIRONMENT=local
DEEPR_DEBUG=false
```

**For Azure:**
```bash
# Provider Configuration
DEEPR_PROVIDER=azure
AZURE_OPENAI_KEY=your-azure-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_DEPLOYMENT_O3=your-o3-deployment-name
AZURE_DEPLOYMENT_O4_MINI=your-o4-mini-deployment-name

# Storage Configuration (Blob)
DEEPR_STORAGE=blob
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_STORAGE_CONTAINER=reports

# Optional
DEEPR_ENVIRONMENT=local
DEEPR_DEBUG=false
```

## Basic Usage

### Python API

```python
import asyncio
from deepr import AppConfig
from deepr.providers import create_provider
from deepr.storage import create_storage
from deepr.core import (
    ResearchOrchestrator,
    DocumentManager,
    ReportGenerator,
    JobManager
)

async def main():
    # Load configuration from environment
    config = AppConfig.from_env()

    # Initialize provider (OpenAI or Azure)
    if config.provider.type == "openai":
        provider = create_provider(
            "openai",
            api_key=config.provider.openai_api_key
        )
    else:  # azure
        provider = create_provider(
            "azure",
            api_key=config.provider.azure_api_key,
            endpoint=config.provider.azure_endpoint,
            deployment_mappings=config.provider.model_mappings
        )

    # Initialize storage (local or blob)
    if config.storage.type == "local":
        storage = create_storage(
            "local",
            base_path=config.storage.local_path
        )
    else:  # blob
        storage = create_storage(
            "blob",
            connection_string=config.storage.azure_connection_string,
            container_name=config.storage.azure_container
        )

    # Initialize core components
    doc_manager = DocumentManager()
    report_gen = ReportGenerator(
        generate_pdf=config.research.generate_pdf,
        strip_citations=config.research.strip_inline_citations
    )
    job_manager = JobManager(
        backend_type=config.database.type,
        log_path=config.database.jsonl_path
    )

    # Create orchestrator
    orchestrator = ResearchOrchestrator(
        provider=provider,
        storage=storage,
        document_manager=doc_manager,
        report_generator=report_gen
    )

    # Submit research
    job_id = await orchestrator.submit_research(
        prompt="Analyze the impact of quantum computing on cybersecurity",
        model="o3-deep-research",
        enable_web_search=True
    )

    print(f"✅ Job submitted: {job_id}")

    # Log the submission
    await job_manager.log_submission(
        response_id=job_id,
        original_prompt="Analyze the impact of quantum computing on cybersecurity",
        model="o3-deep-research",
        provider=config.provider.type
    )

    # Poll for completion (simplified - production should use webhooks)
    import time
    while True:
        status = await orchestrator.get_job_status(job_id)
        print(f"Status: {status.status}")

        if status.status == "completed":
            # Process completion
            await orchestrator.process_completion(
                job_id=job_id,
                append_references=config.research.append_references
            )
            print(f"✅ Reports generated and saved")
            break
        elif status.status in ["failed", "cancelled", "expired"]:
            print(f"❌ Job {status.status}")
            break

        time.sleep(10)

    # List reports
    reports = await storage.list_reports(job_id=job_id)
    for report in reports:
        print(f"📄 {report.filename} ({report.size_bytes} bytes)")
        print(f"   {report.url}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Examples

### Example 1: Simple Research Query

```python
import asyncio
from deepr import AppConfig
from deepr.providers import create_provider
from deepr.storage import create_storage
from deepr.core import ResearchOrchestrator, DocumentManager, ReportGenerator

async def simple_research():
    config = AppConfig.from_env()

    provider = create_provider(config.provider.type, api_key=config.provider.openai_api_key)
    storage = create_storage(config.storage.type, base_path="./reports")

    orchestrator = ResearchOrchestrator(
        provider, storage, DocumentManager(), ReportGenerator()
    )

    job_id = await orchestrator.submit_research(
        "What are the latest advancements in renewable energy?"
    )

    return job_id

asyncio.run(simple_research())
```

### Example 2: Research with Documents

```python
async def research_with_docs():
    # ... initialize components ...

    job_id = await orchestrator.submit_research(
        prompt="Summarize the key findings from these research papers",
        documents=[
            "./papers/paper1.pdf",
            "./papers/paper2.pdf"
        ],
        model="o4-mini-deep-research",  # Cost-sensitive
        enable_web_search=False  # Only use provided documents
    )

    return job_id
```

### Example 3: Provider Switching

```python
# OpenAI
openai_provider = create_provider("openai", api_key="sk-...")
job1 = await orchestrator_openai.submit_research("Query 1")

# Azure
azure_provider = create_provider(
    "azure",
    api_key="azure-key",
    endpoint="https://resource.openai.azure.com/",
    deployment_mappings={
        "o3-deep-research": "my-o3-deployment"
    }
)
job2 = await orchestrator_azure.submit_research("Query 2")

# Same interface, different provider!
```

### Example 4: Storage Switching

```python
# Local storage
local_storage = create_storage("local", base_path="./reports")

# Azure Blob storage
blob_storage = create_storage(
    "blob",
    connection_string="DefaultEndpointsProtocol=https;...",
    container_name="deepr-reports"
)

# Same interface, different backend!
await local_storage.save_report(job_id, "report.md", content, "text/markdown")
await blob_storage.save_report(job_id, "report.md", content, "text/markdown")
```

## Job Management

```python
from deepr.core import JobManager

async def manage_jobs():
    job_manager = JobManager()

    # List all jobs
    jobs = await job_manager.list_jobs()
    for job in jobs:
        print(f"{job.response_id}: {job.status}")

    # List completed jobs
    completed = await job_manager.list_jobs(status="completed")

    # Get specific job
    job = await job_manager.get_job("resp_abc123")

    # Update status
    await job_manager.update_status("resp_abc123", "completed")

    # Cleanup old jobs
    cleaned = await job_manager.cleanup_old_jobs(days=30)
    print(f"Cleaned up {cleaned} old jobs")

asyncio.run(manage_jobs())
```

## Report Generation

```python
from deepr.core import ReportGenerator

async def generate_reports():
    generator = ReportGenerator(
        generate_pdf=True,
        strip_citations=True
    )

    # Extract text from provider response
    text = generator.extract_text_from_response(response)

    # Generate all formats
    reports = await generator.generate_reports(
        text=text,
        title="Research Report",
        formats=["txt", "md", "json", "docx", "pdf"]
    )

    # Save with storage backend
    for format_name, content in reports.items():
        await storage.save_report(
            job_id=job_id,
            filename=f"report.{format_name}",
            content=content,
            content_type=storage.get_content_type(f"report.{format_name}")
        )

asyncio.run(generate_reports())
```

## Webhook Setup (Local Development)

```python
from deepr.webhooks import create_webhook_server, NgrokTunnel
from flask import Flask
import asyncio
from threading import Thread

async def on_completion(job_id: str, data: dict):
    """Handle webhook completion"""
    print(f"Job {job_id} completed!")

    # Process the completion
    await orchestrator.process_completion(job_id)

def run_webhook_server():
    app = create_webhook_server(on_completion, port=5000)
    app.run(host="0.0.0.0", port=5000)

# Start webhook server in background thread
server_thread = Thread(target=run_webhook_server, daemon=True)
server_thread.start()

# Start ngrok tunnel
tunnel = NgrokTunnel(port=5000)
webhook_url = tunnel.start()
print(f"Webhook URL: {webhook_url}")

# Now submit research with webhook
job_id = await orchestrator.submit_research(
    prompt="Your query",
    webhook_url=webhook_url
)

# Webhook will receive completion notification automatically
```

## Cost-Sensitive Mode

```python
# Use lighter model and fewer tools
job_id = await orchestrator.submit_research(
    prompt="Quick research task",
    cost_sensitive=True,  # Uses o4-mini-deep-research
    enable_code_interpreter=False  # Disable code interpreter
)
```

## Testing Provider Connection

```python
async def test_provider():
    config = AppConfig.from_env()

    try:
        provider = create_provider(
            config.provider.type,
            api_key=config.provider.openai_api_key or config.provider.azure_api_key,
            endpoint=config.provider.azure_endpoint
        )

        print(f"✅ Provider initialized: {config.provider.type}")

        # Test with a simple query (optional)
        # job_id = await provider.submit_research(...)
        # print(f"✅ Test submission successful: {job_id}")

    except Exception as e:
        print(f"❌ Provider initialization failed: {e}")

asyncio.run(test_provider())
```

## Testing Storage Connection

```python
async def test_storage():
    config = AppConfig.from_env()

    try:
        storage = create_storage(
            config.storage.type,
            base_path=config.storage.local_path,
            connection_string=config.storage.azure_connection_string,
            container_name=config.storage.azure_container
        )

        print(f"✅ Storage initialized: {config.storage.type}")

        # Test with a dummy report
        test_content = b"Test report content"
        metadata = await storage.save_report(
            job_id="test-job",
            filename="test.txt",
            content=test_content,
            content_type="text/plain"
        )

        print(f"✅ Test write successful: {metadata.url}")

        # Clean up
        await storage.delete_report("test-job")
        print(f"✅ Test cleanup successful")

    except Exception as e:
        print(f"❌ Storage test failed: {e}")

asyncio.run(test_storage())
```

## Troubleshooting

### Issue: "No module named 'deepr'"
**Solution:**
```bash
pip install -e .
```

### Issue: "Provider initialization failed"
**Solution:**
Check your `.env` file has the correct keys:
- `OPENAI_API_KEY` for OpenAI
- `AZURE_OPENAI_KEY` and `AZURE_OPENAI_ENDPOINT` for Azure

### Issue: "Storage connection failed"
**Solution:**
For blob storage, verify:
- `AZURE_STORAGE_CONNECTION_STRING` is correct
- Container exists or will be created
- Credentials have proper permissions

### Issue: "Async function not awaited"
**Solution:**
Make sure to use `asyncio.run()`:
```python
# Wrong
result = some_async_function()

# Right
result = asyncio.run(some_async_function())

# Or inside async function
result = await some_async_function()
```

## Next Steps

1. **Read the Migration Guide**: `docs/migration-guide.md`
2. **Review Implementation Status**: `IMPLEMENTATION_STATUS.md`
3. **Check Azure Integration**: `docs/azure-deep-research.md`
4. **Explore Examples**: Try the examples above
5. **Join Development**: Check `CONTRIBUTING.md` (coming soon)

## Resources

- **Documentation**: `docs/` directory
- **Examples**: This file and `examples/` (coming soon)
- **Issues**: GitHub issues page
- **License**: MIT

---

**Happy Researching! 🚀**
