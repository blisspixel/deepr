# Deepr GCP Deployment

Deploy Deepr to Google Cloud Platform using Terraform.

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

# 2. Copy and edit environment file
cp .env.example .env
# Edit .env with your API keys and project ID

# 3. Deploy
chmod +x deploy.sh
./deploy.sh
```

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
terraform apply \
  -var="project_id=your-project-id" \
  -var="openai_api_key=sk-..."
```

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

# Submit a job
curl -X POST "$API_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What are the best practices for PostgreSQL connection pooling?"}'

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
| openai_api_key | - | Required: OpenAI API key |
| google_api_key | - | Optional: Google API key |
| xai_api_key | - | Optional: xAI API key |
| daily_budget | 50 | Daily spending limit (USD) |
| monthly_budget | 500 | Monthly spending limit (USD) |

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
