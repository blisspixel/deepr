# Deepr Azure Deployment

Deploy Deepr to Azure using Bicep templates.

## v2.36 status

This template is an infrastructure preview. Authenticated `POST /jobs` returns
HTTP 503 with `azure_metered_research_accounting_unavailable` before payload
parsing, Cosmos writes, queue writes, or provider work. Health and read-only
inspection remain available. Supplying provider credentials does not enable
dispatch. Azure resources can still incur infrastructure charges.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Azure      │────▶│   Azure      │────▶│    Azure     │
│  Functions   │     │   Queue      │     │   Storage    │
│   (API)      │     │  Storage     │     │   (Blob)     │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────▼───────┐
                     │  Container   │
                     │    Apps      │
                     │  (Worker)    │
                     └──────────────┘
```

## Prerequisites

- Azure CLI installed (`az --version`)
- Azure subscription
- (Optional) Azure Functions Core Tools (`func --version`)

## Quick Start

```bash
# 1. Login to Azure
az login

# 2. Copy and edit environment file
cp .env.example .env
# Add the required template credential and keep the file untracked.

# 3. Deploy
chmod +x deploy.sh
./deploy.sh
```

The script loads `deploy/azure/.env` before resolving configuration, writes
secure Bicep parameters to a mode-0600 temporary file, passes the file by
reference, and removes it on exit. Secret values do not appear in process argv.

## Manual Deployment

```bash
# Create resource group
az group create --name deepr-rg --location eastus

# Create a protected parameters file. Do not put key values on the command line.
umask 077
# Populate parameters.json using the shape produced by deploy.sh, then run:
az deployment group create \
  --resource-group deepr-rg \
  --template-file main.bicep \
  --parameters @parameters.json
rm -f parameters.json
```

## Deploy Function App Code

After infrastructure deployment:

```bash
cd functions
func azure functionapp publish deepr-prod-api
```

## Usage

```bash
# Get the function app URL from deployment output
FUNCTION_URL="https://deepr-prod-api.azurewebsites.net"

# Verify the fail-closed hosted submission boundary.
curl -X POST "$FUNCTION_URL/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What are the best practices for PostgreSQL connection pooling?"}'
# Expected: HTTP 503 with
# error_code=azure_metered_research_accounting_unavailable

# Check job status
curl "$FUNCTION_URL/api/jobs/{job_id}"

# Get result
curl "$FUNCTION_URL/api/results/{job_id}"
```

## Configuration

### Bicep Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| environment | prod | Deployment environment |
| location | (resource group) | Azure region |
| openaiApiKey | - | Required secure parameter; cannot enable hosted dispatch in v2.36 |
| googleApiKey | - | Optional secure parameter; does not enable automatic fallback |
| xaiApiKey | - | Optional secure parameter; does not enable automatic fallback |
| dailyBudget | 10 | Daily provider spending limit, effective only after hosted metered execution is deliberately enabled |
| monthlyBudget | 10 | Monthly provider spending limit, effective only after hosted metered execution is deliberately enabled |

### Scaling

Container Apps auto-scale based on queue depth:
- Min replicas: 0
- Max replicas: 10
- Scale trigger: 5 messages in queue

Adjust in `main.bicep` under `containerApp.properties.template.scale`.

## Monitoring

### Application Insights

The deployment creates an Application Insights instance for monitoring:
- Request metrics
- Dependency tracking
- Exception logging
- Custom events

Access via Azure Portal or:

```bash
az monitor app-insights query \
  --app deepr-prod-insights \
  --analytics-query "requests | take 10"
```

### Log Analytics

Container and function logs are sent to Log Analytics:

```bash
az monitor log-analytics query \
  --workspace deepr-prod-logs \
  --analytics-query "ContainerAppConsoleLogs_CL | take 10"
```

## Costs

Estimated monthly costs (varies by usage):

| Component | Estimated Cost |
|-----------|---------------|
| Functions (Consumption) | $5-20 |
| Container Apps | $20-100 |
| Queue Storage | $1-5 |
| Blob Storage | $1-10 |
| Key Vault | $1-5 |
| Log Analytics | $5-20 |
| **Total infrastructure** | **$35-160** |

Provider research is execution-gated, but deploying the infrastructure can
still incur the charges above. The provider budget fields do not cap Azure
resource charges. Configure Azure Cost Management budgets separately.

## Cleanup

```bash
# Delete entire resource group
az group delete --name deepr-rg --yes

# Or delete specific resources
az functionapp delete --name deepr-prod-api --resource-group deepr-rg
az containerapp delete --name deepr-prod-worker --resource-group deepr-rg
```

## Troubleshooting

### Function App errors

```bash
# Stream logs
func azure functionapp logstream deepr-prod-api

# Or via CLI
az webapp log tail --name deepr-prod-api --resource-group deepr-rg
```

### Container App errors

```bash
# View logs
az containerapp logs show \
  --name deepr-prod-worker \
  --resource-group deepr-rg
```

### Key Vault access issues

Verify managed identity has access:

```bash
az keyvault show --name deepr-prod-kv-xxx --query "properties.accessPolicies"
```
