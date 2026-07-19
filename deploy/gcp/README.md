# Deepr GCP Deployment

Deploy Deepr to Google Cloud Platform using Terraform.

## v2.36 status

This template is an infrastructure preview. Authenticated `POST /jobs` returns
HTTP 503 with `gcp_metered_research_accounting_unavailable` before payload
parsing, Firestore writes, Pub/Sub writes, or provider work. Health and read-only
inspection remain available. Supplying a provider-secret reference does not
enable dispatch. GCP resources can still incur infrastructure charges.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Cloud     │────▶│   Pub/Sub    │────▶│    Cloud     │
│  Functions   │     │   (Topic)    │     │   Storage    │
│   (API)      │     │              │     │  (Results)   │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────▼───────┐
                     │   Cloud      │
                     │    Run       │
                     │  (Worker)    │
                     └──────────────┘
```

## Prerequisites

- Google Cloud SDK installed (`gcloud --version`)
- Terraform installed (`terraform --version`)
- GCP project with billing enabled

## Quick Start

```bash
# 1. Login to GCP
gcloud auth login
gcloud auth application-default login

# 2. Pre-create the provider secret. Prefer stdin or a protected file so the key
# value does not enter shell history.
gcloud secrets create deepr-prod-openai-key --replication-policy=automatic
gcloud secrets versions add deepr-prod-openai-key --data-file=-

# 3. Copy and edit environment file. Store the secret ID, never the key value.
cp .env.example .env
# Set GCP_PROJECT_ID and DEEPR_GCP_OPENAI_SECRET_ID.

# 4. Deploy
chmod +x deploy.sh
./deploy.sh
```

Terraform receives only the pre-created secret ID. Provider key values do not
enter Terraform variables, plan output, or state. The script loads `.env`
before resolving configuration and uses a mode-0600 temporary JSON variables
file that is removed on exit.

## Manual Deployment

```bash
# Enable required APIs
gcloud services enable \
  cloudfunctions.googleapis.com \
  run.googleapis.com \
  pubsub.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

# Package function source
cd functions && zip -r function-source.zip main.py requirements.txt && cd ..

# Initialize and apply Terraform
terraform init
terraform apply -var-file=deployment.tfvars.json
```

The variables file should contain `project_id`, `region`, `environment`,
`openai_secret_id`, and budget numbers only. It must never contain a provider
key value. Protect and remove it after apply, or use `deploy.sh` to manage an
ephemeral file automatically.

## Build Worker Container

```bash
# Get repository info
REPO=$(terraform output -raw results_bucket | sed 's/-results.*//')
REGION=$(gcloud config get-value compute/region)
PROJECT=$(gcloud config get-value project)

# Build and push (from repo root)
docker build -f Dockerfile -t deepr-worker .
docker tag deepr-worker:latest \
  ${REGION}-docker.pkg.dev/${PROJECT}/${REPO}-repo/deepr-worker:latest
docker push \
  ${REGION}-docker.pkg.dev/${PROJECT}/${REPO}-repo/deepr-worker:latest

# Update Cloud Run service
gcloud run services update deepr-prod-worker \
  --image ${REGION}-docker.pkg.dev/${PROJECT}/${REPO}-repo/deepr-worker:latest
```

## Usage

```bash
# Get the API URL from Terraform output
API_URL=$(terraform output -raw api_url)

# Verify the fail-closed hosted submission boundary.
curl -X POST "$API_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What are the best practices for PostgreSQL connection pooling?"}'
# Expected: HTTP 503 with
# error_code=gcp_metered_research_accounting_unavailable

# Check job status
curl "$API_URL/jobs/{job_id}"

# Get result
curl "$API_URL/results/{job_id}"
```

## Configuration

### Terraform Variables

| Variable | Default | Description |
|----------|---------|-------------|
| project_id | - | Required: GCP project ID |
| region | us-central1 | GCP region |
| environment | prod | Deployment environment |
| openai_secret_id | - | Required ID of a pre-created Secret Manager secret; provider key values never enter Terraform state |
| daily_budget | 10 | Daily provider spending limit, effective only after hosted metered execution is deliberately enabled |
| monthly_budget | 10 | Monthly provider spending limit, effective only after hosted metered execution is deliberately enabled |

### Scaling

Cloud Run auto-scales based on CPU/request metrics:
- Min instances: 0
- Max instances: 10

Adjust in `main.tf` under `google_cloud_run_v2_service.worker.template.scaling`.

## Monitoring

### Cloud Logging

```bash
# Function logs
gcloud functions logs read deepr-prod-api --limit 50

# Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=deepr-prod-worker" --limit 50
```

### Cloud Monitoring

The deployment creates metrics for:
- Function invocations and latency
- Pub/Sub message throughput
- Cloud Run CPU/memory utilization

Access via Cloud Console: Monitoring > Dashboards

## Costs

Estimated monthly costs (varies by usage):

| Component | Estimated Cost |
|-----------|---------------|
| Cloud Functions | $5-20 |
| Cloud Run | $20-100 |
| Pub/Sub | $1-5 |
| Cloud Storage | $1-10 |
| Secret Manager | $1-5 |
| **Total infrastructure** | **$30-140** |

Provider research is execution-gated, but deploying the infrastructure can
still incur the charges above. The provider budget fields do not cap GCP
resource charges. Configure Cloud Billing budgets separately.

## Cleanup

```bash
# Destroy all resources
terraform destroy

# Or delete specific resources
gcloud functions delete deepr-prod-api
gcloud run services delete deepr-prod-worker
gcloud pubsub topics delete deepr-prod-jobs
gsutil rm -r gs://deepr-prod-results-*
```

## Troubleshooting

### Function errors

```bash
gcloud functions logs read deepr-prod-api --limit 100
```

### Cloud Run errors

```bash
gcloud logging read "resource.type=cloud_run_revision" --limit 100 --format json
```

### Pub/Sub issues

```bash
# Check subscription
gcloud pubsub subscriptions describe deepr-prod-jobs-sub

# Check dead letter queue
gcloud pubsub subscriptions pull deepr-prod-jobs-dlq --auto-ack --limit 10
```

### Secret Manager access

```bash
# Verify secret exists
gcloud secrets versions access latest --secret=deepr-prod-openai-key

# Check IAM bindings
gcloud secrets get-iam-policy deepr-prod-openai-key
```
