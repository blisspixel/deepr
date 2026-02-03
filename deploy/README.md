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

## Quick Start

### AWS

```bash
cd deploy/aws
cp .env.example .env
# Edit .env with your API keys

# Deploy
sam build
sam deploy --guided
```

### Azure

```bash
cd deploy/azure
cp .env.example .env
# Edit .env with your API keys

# Deploy
az login
./deploy.sh
```

### GCP

```bash
cd deploy/gcp
cp .env.example .env
# Edit .env with your API keys

# Deploy
gcloud auth login
./deploy.sh
```

## Security Features

All deployments are hardened following cloud provider Well-Architected Framework guidelines:

### Authentication & Authorization

| Feature | AWS | Azure | GCP |
|---------|-----|-------|-----|
| API Authentication | API Gateway API Keys | Azure AD / Function Keys | IAP / API Keys |
| Rate Limiting | WAF + API Gateway throttling | App Gateway WAF | Cloud Armor |
| Request Validation | API Gateway validators | Function input validation | Cloud Endpoints |

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

## API Usage

All endpoints (except `/health`) require authentication:

```bash
# Get API endpoint URL from deployment output
API_URL="https://your-api-endpoint"
API_KEY="your-api-key"

# Submit a job
curl -X POST "$API_URL/jobs" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"prompt": "What are the best practices for PostgreSQL connection pooling?"}'

# Check job status
curl "$API_URL/jobs/{job_id}" \
  -H "X-Api-Key: $API_KEY"

# Get result
curl "$API_URL/results/{job_id}" \
  -H "X-Api-Key: $API_KEY"
```

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

### AWS
```bash
sam delete --stack-name deepr
# Note: KMS keys have deletion protection; disable manually if needed
```

### Azure
```bash
az group delete --name deepr-rg
```

### GCP
```bash
terraform destroy
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
