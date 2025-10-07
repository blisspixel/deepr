# Azure Deep Research API Integration Guide

## Overview

This document provides comprehensive guidance on integrating Azure's Deep Research capabilities into Deepr, comparing Azure's implementation with OpenAI's approach, and outlining best practices for multi-cloud support.

## Architecture Comparison

### Azure Deep Research Sample (Azure-Samples/deepresearch)

**Core Components:**
- **AI Model**: DeepSeek R1 via Azure AI Inference API
- **Framework**: LangGraph for workflow orchestration
- **Backend**: FastAPI with WebSocket real-time communication
- **Research Tool**: Tavily API for web search
- **Deployment**: Azure Container Apps

**Research Workflow:**
1. Query Generation - Formulate research questions
2. Web Research - Tavily API searches
3. Summarization - Consolidate findings
4. Reflection - Identify knowledge gaps
5. Iterative Research - Multi-cycle refinement
6. Report Generation - Structured output

**Key Differentiators:**
- Transparent reasoning process (DeepSeek R1's chain-of-thought)
- Real-time progress via WebSockets
- Multi-stage iterative research cycles
- Automatic knowledge gap identification

### OpenAI Deep Research API

**Core Components:**
- **AI Model**: o3-deep-research, o4-mini-deep-research
- **Framework**: Native OpenAI Responses API
- **Backend**: Asynchronous job submission with webhooks
- **Research Tools**: web_search_preview, code_interpreter, file_search
- **Deployment**: Provider-agnostic (works anywhere)

**Research Workflow:**
1. Single prompt submission
2. Background job processing
3. Webhook notification on completion
4. Polling fallback mechanism

**Key Differentiators:**
- Native API integration (no orchestration framework needed)
- Built-in tool ecosystem
- Asynchronous by design
- Automatic citation handling

## Azure OpenAI Service Integration

### Authentication Methods

**1. API Key Authentication**
```python
from openai import AzureOpenAI

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-10-01-preview",
    azure_endpoint="https://YOUR-RESOURCE.openai.azure.com/"
)
```

**2. Managed Identity (Recommended for Production)**
```python
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

credential = DefaultAzureCredential()
token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

client = AzureOpenAI(
    azure_ad_token_provider=token_provider,
    api_version="2024-10-01-preview",
    azure_endpoint="https://YOUR-RESOURCE.openai.azure.com/"
)
```

### Deep Research Model Deployment

**Prerequisites:**
- Azure subscription with OpenAI access
- Deploy o3-deep-research or o4-mini-deep-research model
- Configure deployment in Azure Portal or via CLI

**Deployment Regions:**
Azure OpenAI model availability varies by region. Check current availability:
- East US
- West Europe
- Sweden Central (for DeepSeek models)

**Model Mapping:**
```python
# OpenAI model names → Azure deployment names
MODEL_MAPPINGS = {
    "o3-deep-research": "my-o3-deployment",
    "o4-mini-deep-research": "my-o4-mini-deployment",
    "deepseek-r1": "my-deepseek-deployment"
}
```

### API Differences

**Endpoint Structure:**
- OpenAI: `https://api.openai.com/v1/`
- Azure: `https://{resource-name}.openai.azure.com/openai/deployments/{deployment-name}/`

**Request Format:**
```python
# OpenAI
response = client.responses.create(
    model="o3-deep-research",
    input=[...],
    tools=[...]
)

# Azure
response = client.responses.create(
    model="my-o3-deployment",  # Deployment name, not model name
    input=[...],
    tools=[...]
)
```

**Tool Availability:**
- `web_search_preview`: Available on both (configuration differs)
- `code_interpreter`: Available on both
- `file_search`: Available on both
- `mcp`: OpenAI-specific (not available on Azure)

### Configuration Requirements

**Environment Variables:**
```bash
# Azure Configuration
DEEPR_PROVIDER=azure
AZURE_OPENAI_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_API_VERSION=2024-10-01-preview
AZURE_DEPLOYMENT_O3=your-o3-deployment-name
AZURE_DEPLOYMENT_O4_MINI=your-o4-mini-deployment-name

# Optional: Managed Identity
AZURE_CLIENT_ID=your-client-id
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_SECRET=your-client-secret
```

## Hybrid Architecture for Deepr

### Provider Selection Strategy

**Decision Tree:**
1. Check `DEEPR_PROVIDER` environment variable
2. If `azure`: Initialize AzureOpenAI client
3. If `openai`: Initialize OpenAI client
4. Default to `openai` if not specified

**Configuration Validation:**
```python
def validate_azure_config():
    required = ["AZURE_OPENAI_KEY", "AZURE_OPENAI_ENDPOINT"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise ConfigError(f"Missing Azure config: {missing}")
```

### Webhook Handling Differences

**OpenAI:**
- Uses `OpenAI-Hook-URL` header
- Sends POST to webhook URL on completion
- Includes full response payload

**Azure:**
- Same webhook mechanism
- Ensure endpoint is publicly accessible
- For local dev: ngrok tunnel
- For cloud: Azure App Service URL

**Cloud Deployment Considerations:**
```python
# Local environment: use ngrok
if environment == "local":
    webhook_url = get_ngrok_tunnel()

# Cloud environment: use App Service URL
elif environment == "cloud":
    webhook_url = f"https://{app_service_name}.azurewebsites.net/webhook"
```

## Azure Storage Integration

### Blob Storage for Reports

**Setup:**
```python
from azure.storage.blob.aio import BlobServiceClient

async def init_blob_storage():
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    client = BlobServiceClient.from_connection_string(connection_string)

    # Ensure container exists
    container_client = client.get_container_client("reports")
    if not await container_client.exists():
        await container_client.create_container()

    return client
```

**Report Storage Pattern:**
```
Container: reports
Structure:
  ├── {job_id}/
  │   ├── report.txt
  │   ├── report.md
  │   ├── report.docx
  │   ├── report.pdf
  │   └── report.json
```

**Access Control:**
- Use Shared Access Signatures (SAS) for time-limited access
- Enable blob versioning for audit trails
- Configure lifecycle management for automatic cleanup

### Cosmos DB for Job Metadata

**Schema Design:**
```json
{
  "id": "job-abc123",
  "partition_key": "user_id",
  "status": "completed",
  "created_at": "2025-01-15T10:30:00Z",
  "completed_at": "2025-01-15T10:45:00Z",
  "provider": "azure",
  "model": "o3-deep-research",
  "prompt": "Research prompt...",
  "usage": {
    "input_tokens": 1500,
    "output_tokens": 8500,
    "total_tokens": 10000
  },
  "cost": 0.25,
  "report_urls": {
    "txt": "https://...",
    "md": "https://...",
    "docx": "https://..."
  }
}
```

## Deployment Architecture

### Local Development
```
┌─────────────┐
│   CLI App   │
│  (deepr)    │
└──────┬──────┘
       │
       ├──→ OpenAI API (if DEEPR_PROVIDER=openai)
       ├──→ Azure OpenAI (if DEEPR_PROVIDER=azure)
       │
       ├──→ Local Storage (./reports/)
       └──→ Ngrok Tunnel (webhooks)
```

### Azure Cloud Deployment
```
┌─────────────────────────────────────────┐
│         Azure Front Door                 │
│   (CDN + WAF + Load Balancer)           │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│    Azure App Service (Linux + Python)   │
│  ┌────────────────────────────────────┐ │
│  │   Flask Web Application            │ │
│  │   - Research submission UI         │ │
│  │   - Job management dashboard       │ │
│  │   - REST API                       │ │
│  │   - Webhook endpoint               │ │
│  └─────────┬──────────────────────────┘ │
└────────────┼────────────────────────────┘
             │
    ┌────────┼────────┬────────────┐
    │        │        │            │
    ▼        ▼        ▼            ▼
┌────────┐ ┌────┐ ┌────────┐ ┌──────────┐
│ Azure  │ │Blob│ │ Cosmos │ │  Azure   │
│ OpenAI │ │Stor│ │   DB   │ │Key Vault │
│ Service│ │age │ │        │ │          │
└────────┘ └────┘ └────────┘ └──────────┘
```

### Infrastructure as Code (Bicep)

**Main Template:**
```bicep
// deployment/azure/main.bicep
param location string = resourceGroup().location
param appName string
param openAiResourceName string
param storageAccountName string

module appService './app-service.bicep' = {
  name: 'appServiceDeployment'
  params: {
    location: location
    appName: appName
  }
}

module openai './openai.bicep' = {
  name: 'openaiDeployment'
  params: {
    location: location
    resourceName: openAiResourceName
  }
}

module storage './storage.bicep' = {
  name: 'storageDeployment'
  params: {
    location: location
    accountName: storageAccountName
  }
}
```

## Cost Management

### Pricing Comparison

**OpenAI:**
- o3-deep-research: $2.00/M input tokens, $8.00/M output tokens
- o4-mini-deep-research: $1.10/M input tokens, $4.40/M output tokens

**Azure OpenAI:**
- Same model pricing as OpenAI
- Additional Azure infrastructure costs:
  - App Service: ~$50-200/month (B1-S1 tier)
  - Blob Storage: ~$0.02/GB/month
  - Cosmos DB: ~$25/month (serverless) or ~$200/month (provisioned)
  - Front Door: ~$35/month + data transfer

**Cost Optimization Strategies:**
1. Use `o4-mini-deep-research` for non-critical research
2. Implement request throttling and quotas
3. Enable blob storage lifecycle policies (delete after 90 days)
4. Use reserved capacity for predictable workloads
5. Monitor usage with Azure Cost Management

### Usage Tracking

**Implementation:**
```python
async def track_usage(job_id: str, usage: dict, provider: str):
    cost = calculate_cost(
        usage["input_tokens"],
        usage["output_tokens"],
        provider=provider
    )

    await cosmos_db.upsert_item({
        "id": job_id,
        "usage": usage,
        "cost": cost,
        "timestamp": datetime.utcnow().isoformat()
    })
```

## Security Best Practices

### API Key Management
- **Never** commit API keys to source control
- Use Azure Key Vault for production secrets
- Rotate keys every 90 days
- Enable Azure AD authentication when possible

### Network Security
- Use Azure Virtual Network for App Service
- Configure Private Endpoints for Azure OpenAI
- Enable Web Application Firewall (WAF)
- Implement rate limiting at Front Door

### Data Protection
- Enable blob encryption at rest
- Use HTTPS for all communication
- Implement data retention policies
- Enable audit logging with Azure Monitor

## Migration Strategy

### Phase 1: Provider Abstraction (Week 1)
1. Create provider interface
2. Implement OpenAI provider (port existing code)
3. Implement Azure provider (new)
4. Add provider factory

### Phase 2: Storage Abstraction (Week 1-2)
1. Create storage interface
2. Implement local storage (port existing)
3. Implement Azure Blob storage (new)
4. Migrate report generation

### Phase 3: Web Application (Week 2-3)
1. Build Flask app structure
2. Create REST API
3. Build frontend UI
4. Implement real-time updates

### Phase 4: Azure Deployment (Week 3-4)
1. Write Bicep templates
2. Configure CI/CD pipeline
3. Deploy to dev environment
4. Test end-to-end
5. Deploy to production

## Testing Strategy

### Unit Tests
```python
# tests/unit/test_azure_provider.py
@pytest.mark.asyncio
async def test_azure_provider_submit():
    provider = AzureProvider(
        api_key="test-key",
        endpoint="https://test.openai.azure.com"
    )

    request = ResearchRequest(
        prompt="Test prompt",
        model="o3-deep-research",
        tools=[{"type": "web_search_preview"}],
        metadata={},
        system_message="Test system message"
    )

    job_id = await provider.submit_research(request)
    assert job_id is not None
```

### Integration Tests
```python
# tests/integration/test_azure_e2e.py
@pytest.mark.azure
@pytest.mark.asyncio
async def test_full_research_flow():
    # Submit job
    orchestrator = ResearchOrchestrator(...)
    job_id = await orchestrator.submit_research("Test prompt")

    # Wait for completion
    await wait_for_completion(job_id, timeout=300)

    # Verify reports
    reports = await storage.list_reports(job_id)
    assert "report.md" in reports
```

### Load Tests
```bash
# Use Apache Bench or Locust
locust -f tests/load/locustfile.py --host https://deepr-app.azurewebsites.net
```

## Monitoring & Observability

### Application Insights
```python
from applicationinsights import TelemetryClient

telemetry = TelemetryClient(os.getenv("APPINSIGHTS_INSTRUMENTATION_KEY"))

@app.route("/api/research", methods=["POST"])
async def submit_research():
    telemetry.track_event("research_submitted", {
        "provider": config.provider.type,
        "model": request.json.get("model")
    })

    try:
        job_id = await orchestrator.submit_research(...)
        telemetry.track_metric("research_latency", elapsed_time)
        return jsonify({"job_id": job_id})
    except Exception as e:
        telemetry.track_exception()
        raise
```

### Key Metrics to Track
- Research job submission rate
- Job completion time (p50, p95, p99)
- Error rate by provider
- Token usage and cost per job
- Storage usage trends
- API response times

## References

- [Azure OpenAI Service Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
- [Azure Deep Research Sample](https://github.com/Azure-Samples/deepresearch)
- [OpenAI Deep Research API](https://platform.openai.com/docs/guides/deep-research)
- [Azure Bicep Documentation](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/)
- [Flask on Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/quickstart-python)
