# Deepr Cloud Deployment

Deploy Deepr to AWS, Azure, or GCP with serverless triggers and container-based workers.

## Architecture

All three cloud deployments follow the same security-hardened pattern:

```
                              ┌─────────────────┐
                              │      WAF        │
                              │  Rate Limiting  │
                              └────────┬────────┘
                                       │
┌──────────┐    ┌──────────────────────▼──────────────────────┐
│  Client  │───▶│              API Gateway                    │
│          │    │  (API Key Auth + Request Validation)        │
└──────────┘    └──────────────────────┬──────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │   Serverless    │
                              │     Function    │ ◄─── VPC Integration
                              └────────┬────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
     ┌────────▼────────┐     ┌────────▼────────┐     ┌─────────▼────────┐
     │   Job Queue     │     │   Database      │     │     Secrets      │
     │ (Encrypted)     │     │ (DynamoDB/      │     │    Manager       │
     │                 │     │  Cosmos/Firestore)    │  (KMS Encrypted) │
     └────────┬────────┘     └─────────────────┘     └──────────────────┘
              │
     ┌────────▼────────┐     ┌─────────────────┐
     │     Worker      │────▶│   Results       │
     │   Container     │     │   Storage       │
     │ (Private Subnet)│     │ (KMS Encrypted) │
     └─────────────────┘     └─────────────────┘
```

**Components:**

| Component | AWS | Azure | GCP |
|-----------|-----|-------|-----|
| WAF | WAF v2 | Application Gateway WAF | Cloud Armor |
| API Gateway | API Gateway + Lambda | Azure Functions | Cloud Functions |
| Job Database | DynamoDB | Cosmos DB | Firestore |
| Job Queue | SQS | Azure Queue Storage | Pub/Sub |
| Worker | Fargate | Container Apps | Cloud Run |
| Results Storage | S3 | Blob Storage | Cloud Storage |
| Secrets | Secrets Manager | Key Vault | Secret Manager |
| Encryption | KMS | Azure Key Vault | Cloud KMS |
| Network | VPC + Private Subnets | VNet + Private Endpoints | VPC + Serverless Connector |

## Project Structure

```
deploy/
├── README.md           # This file
├── shared/             # Shared API library (cloud-agnostic utilities)
│   ├── setup.py
│   └── deepr_api_common/
│       ├── __init__.py
│       ├── validation.py   # Input validation (job ID, prompt, model, etc.)
│       ├── security.py     # API key validation, CORS/security headers
│       ├── models.py       # Job document creation, TTL, cost estimation
│       └── responses.py    # Response formatting utilities
├── aws/                # AWS SAM/CloudFormation deployment
│   ├── template.yaml   # SAM template
│   ├── deploy.sh       # Build + deploy + validate
│   ├── validate.sh     # Smoke test endpoints
│   ├── destroy.sh      # Tear down stack
│   └── src/api/handler.py
├── azure/              # Azure Bicep deployment
│   ├── main.bicep      # Bicep template
│   ├── deploy.sh       # Deploy + validate
│   ├── validate.sh     # Smoke test endpoints
│   ├── destroy.sh      # Delete resource group
│   └── functions/function_app.py
└── gcp/                # GCP Terraform deployment
    ├── main.tf         # Terraform config
    ├── deploy.sh       # Terraform apply + validate
    ├── validate.sh     # Smoke test endpoints
    ├── destroy.sh      # Terraform destroy
    └── functions/main.py
```

The shared library (`deploy/shared/deepr_api_common/`) provides reusable validation, security, and response utilities. Each cloud handler can import from it to reduce code duplication.

## Quick Start

Each cloud has three standardized scripts: `deploy.sh`, `validate.sh`, and `destroy.sh`.

### AWS

```bash
cd deploy/aws
cp .env.example .env        # Add your API keys

./deploy.sh                  # Build + deploy + auto-validate
./validate.sh                # Re-run validation anytime
./destroy.sh                 # Tear down all resources
```

### Azure

```bash
cd deploy/azure
cp .env.example .env        # Add your API keys

az login
./deploy.sh                  # Deploy + auto-validate
./validate.sh                # Re-run validation anytime
./destroy.sh                 # Tear down resource group
```

### GCP

```bash
cd deploy/gcp
cp .env.example .env        # Add your API keys

gcloud auth login
./deploy.sh                  # Deploy + auto-validate
./validate.sh                # Re-run validation anytime
./destroy.sh                 # Terraform destroy
```

### Deploy / Validate / Destroy Lifecycle

All three clouds follow the same lifecycle:

1. **Deploy** (`deploy.sh`) — Provisions infrastructure, deploys code, auto-runs validation
2. **Validate** (`validate.sh`) — Smoke tests: health check, job submit, status check, costs endpoint
3. **Destroy** (`destroy.sh`) — Tears down all resources with confirmation prompt (use `--yes` to skip)

Validation checks (all clouds):
- `GET /health` returns 200
- `POST /jobs` returns a job_id
- `GET /jobs/{id}` returns 200
- `GET /costs` returns 200

Set `API_URL` and `API_KEY` environment variables to point validation at a specific deployment.

## Security Features

All deployments are hardened following cloud provider Well-Architected Framework guidelines:

### Authentication & Authorization

All API handlers support two authentication methods:
- **Authorization Header**: `Authorization: Bearer <api-key>`
- **X-Api-Key Header**: `X-Api-Key: <api-key>`

| Feature | AWS | Azure | GCP |
|---------|-----|-------|-----|
| API Authentication | Secrets Manager + handler validation | Key Vault + handler validation | Environment variable + handler validation |
| Rate Limiting | WAF + API Gateway throttling | App Gateway WAF | Cloud Armor |
| Request Validation | Handler input validation | Handler input validation | Handler input validation |

### Network Security

| Feature | AWS | Azure | GCP |
|---------|-----|-------|-----|
| VPC Isolation | Private subnets for workers | VNet integration | VPC with Serverless Connector |
| Private Endpoints | S3, DynamoDB, SQS, Secrets Manager, KMS | Storage, Key Vault, Cosmos DB | Private Google Access |
| NAT Gateway | For outbound LLM API calls | Azure NAT | Cloud NAT |
| Firewall Rules | Security Groups | Network Security Groups | VPC Firewall Rules |

### Data Protection

| Feature | AWS | Azure | GCP |
|---------|-----|-------|-----|
| Encryption at Rest | KMS (customer-managed keys) | Azure Key Vault keys | Cloud KMS |
| Encryption in Transit | TLS 1.2+ enforced | TLS 1.2+ enforced | TLS 1.2+ enforced |
| Secret Storage | Secrets Manager (KMS encrypted) | Key Vault | Secret Manager (KMS encrypted) |
| S3/Blob Policies | Deny HTTP, require encryption | Deny public access, HTTPS only | Uniform bucket-level access |

### IAM & Least Privilege

All deployments use least-privilege IAM policies:

- **API Service Account**: Write to queue, read/write job database, read secrets
- **Worker Service Account**: Read from queue, write results, update job status, read secrets
- **No wildcard permissions**: All policies scoped to specific resources and prefixes

### Monitoring & Alerting

| Alert | AWS | Azure | GCP |
|-------|-----|-------|-----|
| High Error Rate | CloudWatch Alarm | Azure Monitor Alert | Cloud Monitoring Alert |
| DLQ Messages | SQS DLQ depth alarm | - | Pub/Sub DLQ alert |
| Unauthorized Access | 4XX error threshold | WAF blocking logs | Cloud Armor metrics |
| Secrets Access Anomaly | SecretsManager access alarm | Key Vault diagnostics | Audit logs |

## Security Checklist

Before deploying to production, ensure:

- [ ] **API Keys**: Change default API keys, use strong random values
- [ ] **WAF Enabled**: Verify WAF is active (`enable_waf = true`)
- [ ] **IP Allowlisting**: Restrict API access to known IP ranges if possible
- [ ] **SSL Certificates**: Configure custom domain with valid SSL certificate
- [ ] **Audit Logging**: Verify audit logs are enabled and retained
- [ ] **Alerting**: Configure notification channels for security alerts
- [ ] **Secrets Rotation**: Set up automatic secrets rotation where supported
- [ ] **Budget Alerts**: Configure cost alerts to detect abuse

## Cost Considerations

Serverless deployments have different cost profiles than local execution:

| Component | Approximate Cost |
|-----------|-----------------|
| API calls | ~$0.001 per request |
| WAF | ~$5/month + $0.60/million requests |
| Queue operations | ~$0.0001 per message |
| Worker compute | ~$0.05/hour (container running) |
| Database | ~$1-10/month (on-demand) |
| Storage | ~$0.02/GB/month |
| VPC Endpoints | ~$7/endpoint/month (AWS) |
| NAT Gateway | ~$30/month + data transfer |

**Note:** The actual research costs (OpenAI, Gemini, etc.) remain the same regardless of deployment method. Security features add ~$50-100/month overhead.

## Environment Variables

All deployments require these environment variables:

```bash
# Required: At least one provider
OPENAI_API_KEY=sk-...
# or
GOOGLE_API_KEY=...
# or
XAI_API_KEY=xai-...

# Optional: Additional providers for fallback
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://....openai.azure.com

# Optional: Deepr configuration
DEEPR_DEFAULT_MODEL=o4-mini-deep-research
DEEPR_BUDGET_DAILY=50
DEEPR_BUDGET_MONTHLY=500

# Security (auto-generated if not provided)
API_KEY=your-secure-api-key
```

## API Features

All handlers include:

| Feature | Description |
|---------|-------------|
| **Authentication** | API key via `Authorization: Bearer` or `X-Api-Key` header |
| **CORS** | Preflight OPTIONS handling for browser clients |
| **Input Validation** | Prompt length (10,000 chars), model validation, UUID format |
| **Security Headers** | HSTS, X-Frame-Options, X-Content-Type-Options, Cache-Control |
| **Document TTL** | 90-day automatic cleanup of job records |
| **Error Handling** | Structured JSON error responses with appropriate HTTP codes |

## API Usage

All endpoints (except `/health`) require authentication. Use either header format:

```bash
# Get API endpoint URL from deployment output
API_URL="https://your-api-endpoint"
API_KEY="your-api-key"

# Health check (no auth required)
curl "$API_URL/health"

# Submit a job (using X-Api-Key header)
curl -X POST "$API_URL/jobs" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"prompt": "What are the best practices for PostgreSQL connection pooling?"}'

# Submit a job (using Authorization Bearer header)
curl -X POST "$API_URL/jobs" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"prompt": "What are the best practices for PostgreSQL connection pooling?", "model": "o4-mini-deep-research"}'

# List jobs
curl "$API_URL/jobs" -H "X-Api-Key: $API_KEY"

# List jobs filtered by status
curl "$API_URL/jobs?status=completed&limit=10" -H "X-Api-Key: $API_KEY"

# Check job status
curl "$API_URL/jobs/{job_id}" -H "X-Api-Key: $API_KEY"

# Cancel a job
curl -X POST "$API_URL/jobs/{job_id}/cancel" -H "X-Api-Key: $API_KEY"

# Get result (markdown report)
curl "$API_URL/results/{job_id}" -H "X-Api-Key: $API_KEY"

# Get cost summary
curl "$API_URL/costs" -H "X-Api-Key: $API_KEY"
```

### Request Body (POST /jobs)

```json
{
  "prompt": "Your research question (required, max 10,000 chars)",
  "model": "o4-mini-deep-research",
  "priority": 3,
  "enable_web_search": true,
  "metadata": {"project": "example"}
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | Yes | - | Research question (max 10,000 characters) |
| `model` | string | No | `o4-mini-deep-research` | Model to use (see valid models below) |
| `priority` | integer | No | 3 | Priority 1-5 (1 = highest) |
| `enable_web_search` | boolean | No | true | Enable web search for research |
| `metadata` | object | No | {} | Custom metadata (max 4KB) |

**Valid Models:**
- `o4-mini-deep-research` (default, lower cost)
- `o3-deep-research` (higher quality)
- `gemini-2.0-flash-thinking-exp`
- `gemini-2.5-pro-exp-03-25`
- `grok-3-mini-fast`
- `grok-3-fast`

## Customization

### Scaling

Workers scale based on queue depth. Adjust these settings per cloud:

- **AWS**: `WorkerScalingTarget` in `template.yaml` (default: 0-10 instances)
- **Azure**: `minReplicas`/`maxReplicas` in `main.bicep` (default: 0-10)
- **GCP**: `min_instance_count`/`max_instance_count` in `main.tf` (default: 0-10)

### Timeout

Deep research jobs can run 1-60+ minutes. Worker timeouts are set to 60-90 minutes by default:

- **AWS**: `timeout` in Fargate task definition (3600s)
- **Azure**: Container Apps timeout (3600s)
- **GCP**: `timeout` in Cloud Run service (3600s)

### WAF Rules

Customize WAF rules for your use case:

- **AWS**: Modify `WAFWebACL` rules in `template.yaml`
- **Azure**: Modify `wafPolicy` rules in `main.bicep`
- **GCP**: Modify `google_compute_security_policy` rules in `main.tf`

### IP Allowlisting

Restrict API access to specific IP ranges:

- **AWS**: Set `AllowedIPRanges` parameter
- **Azure**: Set `allowedIpRanges` parameter
- **GCP**: Set `allowed_ip_ranges` variable

## Cleanup

Use the standardized destroy scripts (with confirmation prompts):

### AWS
```bash
cd deploy/aws
./destroy.sh                 # Interactive confirmation
./destroy.sh --yes           # Skip confirmation
# Note: KMS keys have deletion protection; disable manually if needed
```

### Azure
```bash
cd deploy/azure
./destroy.sh                 # Interactive confirmation
./destroy.sh --yes           # Skip confirmation
```

### GCP
```bash
cd deploy/gcp
./destroy.sh                 # Interactive confirmation
./destroy.sh --yes           # Skip confirmation
# Note: KMS keys have deletion protection; disable manually if needed
```

## Troubleshooting

### Jobs stuck in queue

Check worker logs:
- AWS: CloudWatch Logs `/aws/fargate/deepr-worker`
- Azure: Container Apps logs in Azure Portal
- GCP: Cloud Run logs in Cloud Console

### API returns 401

Verify API key is correct:
```bash
# Include API key in request
curl -H "X-Api-Key: your-key" $API_URL/health
```

### API returns 403

Check WAF logs for blocked requests:
- AWS: CloudWatch Logs for WAF
- Azure: Application Gateway WAF logs
- GCP: Cloud Armor logs in Cloud Console

### API returns 429

Rate limit exceeded. Wait and retry, or adjust rate limits:
- AWS: Modify `RateLimitRule` in WAF
- Azure: Modify `rateLimitThreshold` in WAF policy
- GCP: Modify `rate_limit_threshold` in Cloud Armor

### API returns 500

Check API logs:
- AWS: CloudWatch Logs `/aws/lambda/deepr-api`
- Azure: Function App logs
- GCP: Cloud Functions logs

### Authentication errors

Verify secrets are set correctly:
- AWS: `aws secretsmanager get-secret-value --secret-id deepr/prod/api-keys`
- Azure: `az keyvault secret show --vault-name deepr-prod-kv-xxx --name openai-api-key`
- GCP: `gcloud secrets versions access latest --secret=deepr-prod-openai-key`

## Security Incident Response

If you suspect a security incident:

1. **Rotate API keys immediately**
   - AWS: Update secrets in Secrets Manager
   - Azure: Update secrets in Key Vault
   - GCP: Update secrets in Secret Manager

2. **Review audit logs**
   - AWS: CloudTrail + CloudWatch Logs
   - Azure: Activity Log + Diagnostic logs
   - GCP: Cloud Audit Logs

3. **Check WAF logs** for attack patterns

4. **Review IAM** for unauthorized changes

5. **Enable IP blocking** if attack source is identified
