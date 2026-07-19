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

> **Note on workers:** AWS ships a complete worker implementation in
> `deploy/aws/src/worker/`. Azure (Container Apps) and GCP (Cloud Run)
> currently ship only the infrastructure templates - the worker
> container source is not yet included. Bring your own image or port
> the AWS worker as a starting point (it uses DynamoDB; rework the
> queue/state plumbing to Cosmos DB / Firestore for the other clouds).

### AWS v2.36 execution status

The AWS research API and worker are infrastructure previews in v2.36, not an
executable paid-research surface. Authenticated `POST /jobs` returns HTTP 503
with `error_code=aws_metered_research_accounting_unavailable` before request
parsing, job-id allocation, DynamoDB writes, or SQS writes. The worker applies
the same independent gate before importing or constructing a provider, so an
old or manually queued message cannot reach paid research. Existing read-only
job, result, cost, and health endpoints remain available. Restore submission
only after the hosted path uses one durable estimate, reservation, dispatch
mark, provider-usage settlement, and canonical cost-ledger transaction.

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
├── mcp-http/           # Hosted MCP HTTP container recipe
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── README.md
│   ├── aws-ecs-fargate/
│   │   ├── template.yaml
│   │   └── README.md
│   ├── azure-container-apps/
│   │   ├── main.bicep
│   │   └── README.md
│   ├── cloudflare-worker/
│   │   ├── worker.mjs
│   │   ├── wrangler.toml.example
│   │   └── README.md
│   └── gcp-cloud-run/
│       ├── main.tf
│       └── README.md
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

### Hosted MCP HTTP Endpoint

Remote agent hosts can call Deepr through the Streamable HTTP MCP endpoint.
Use the local service plus reverse-proxy recipe in [mcp-http.md](mcp-http.md),
or the containerized service in [mcp-http/](mcp-http/),
then verify the endpoint with:

```bash
deepr mcp smoke-http https://mcp.example.com/mcp --auth-token "$DEEPR_MCP_KEY"
```

For an Azure Container Apps variant, see
[mcp-http/azure-container-apps/](mcp-http/azure-container-apps/). It mounts a
persistent Azure Files share at `/data`, keeps scoped-key and audit state in
that share, exposes HTTPS-only ingress, and leaves provider API keys out of the
template until a scoped key mode and budget intentionally allow paid tools.

For an AWS variant, see [mcp-http/aws-ecs-fargate/](mcp-http/aws-ecs-fargate/).
It runs the same container on ECS Fargate behind an HTTPS Application Load
Balancer, mounts EFS at `/data`, keeps scoped-key and audit state durable, and
leaves provider API keys out of the template until paid tools are intentional.

For a GCP variant, see [mcp-http/gcp-cloud-run/](mcp-http/gcp-cloud-run/).
It runs the same container on Cloud Run, mounts a Cloud Storage bucket at
`/data`, keeps scoped-key and audit state durable with single-writer defaults,
and leaves provider API keys out of the template until paid tools are
intentional.

For an edge ingress variant, see
[mcp-http/cloudflare-worker/](mcp-http/cloudflare-worker/). It fronts an
existing HTTPS MCP origin, proxies only `/mcp` paths, caps request bodies at
1 MiB, forwards scoped-key auth headers, and leaves budgets, rate limits,
audit logs, and provider keys on the origin side.

### AWS

```bash
cd deploy/aws
cp .env.example .env        # Add a pre-created provider secret ARN

./deploy.sh                  # Build + deploy + auto-validate
./validate.sh                # Re-run validation anytime
./destroy.sh                 # Tear down all resources
```

### Azure

```bash
cd deploy/azure
cp .env.example .env        # Add secure template inputs

az login
./deploy.sh                  # Deploy + auto-validate
./validate.sh                # Re-run validation anytime
./destroy.sh                 # Tear down resource group
```

### GCP

```bash
cd deploy/gcp
cp .env.example .env        # Add project and pre-created secret ID

gcloud auth login
./deploy.sh                  # Deploy + auto-validate
./validate.sh                # Re-run validation anytime
./destroy.sh                 # Terraform destroy
```

### Deploy / Validate / Destroy Lifecycle

All three clouds follow the same lifecycle:

1. **Deploy** (`deploy.sh`) - Provisions infrastructure, deploys code, auto-runs validation
2. **Validate** (`validate.sh`) - Smoke tests the deployment's current supported boundary
3. **Destroy** (`destroy.sh`) - Tears down all resources with confirmation prompt (use `--yes` to skip)

Hosted v2.36 validation is provider-free:
- `GET /health` returns 200
- `POST /jobs` returns 503 with the cloud-specific
  `*_metered_research_accounting_unavailable` code
- `GET /jobs` returns 200 without creating a job
- `GET /costs` returns 200

AWS, Azure, and GCP independently block job submission before payload parsing,
durable job writes, queue writes, or provider work. Their validation scripts do
not establish the durable metered-accounting contract required to describe
hosted paid research as a supported v2.36 surface.

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

**Note:** AWS, Azure, and GCP v2.36 deployments can incur infrastructure costs
but block LLM research calls.
The provider-cost comparison applies only after a deployment implements the
required durable metered-accounting transaction. Security features add
approximately $50-100/month overhead.

## Environment Variables

The deployment scripts use cloud-specific secret inputs. A secret reference or
secure parameter does not enable the gated v2.36 research path:

```bash
# AWS: pre-created Secrets Manager ARN. Key values stay outside CloudFormation.
DEEPR_AWS_PROVIDER_SECRET_ARN=arn:aws:secretsmanager:REGION:ACCOUNT:secret:NAME

# GCP: pre-created Secret Manager ID. Key values stay outside Terraform state.
DEEPR_GCP_OPENAI_SECRET_ID=deepr-prod-openai-key

# Azure: secure Bicep input passed through a protected temporary parameter file.
OPENAI_API_KEY=sk-...

# Optional Azure stored credentials. They do not enable automatic fallback.
GOOGLE_API_KEY=
XAI_API_KEY=

# Optional: Deepr budget configuration
DEEPR_BUDGET_DAILY=10
DEEPR_BUDGET_MONTHLY=10

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

# Verify that AWS v2.36 blocks paid submission before writes
curl -X POST "$API_URL/jobs" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"prompt": "What are the best practices for PostgreSQL connection pooling?"}'
# Expected: HTTP 503 and
# {"error_code":"aws_metered_research_accounting_unavailable", ...}

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

### POST /jobs in v2.36

No model identifier is valid for AWS execution in v2.36 because the entire
metered submission path is gated before body parsing. Do not use the historical
deployment allowlist as a model catalog. Current model IDs and pricing live in
[`src/deepr/providers/registry.py`](../src/deepr/providers/registry.py), but a
registry entry alone never authorizes hosted dispatch. The AWS path must first
implement the durable accounting contract described above.

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
- AWS: `aws secretsmanager describe-secret --secret-id "$DEEPR_AWS_PROVIDER_SECRET_ARN"`
- Azure: `az keyvault secret show --vault-name deepr-prod-kv-xxx --name openai-api-key --query id -o tsv`
- GCP: `gcloud secrets describe "$DEEPR_GCP_OPENAI_SECRET_ID"`

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
