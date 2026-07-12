# Deepr AWS Deployment

Deploy Deepr to AWS using SAM (Serverless Application Model).

## v2.36 status

This template is an infrastructure preview. Paid research execution is gated
in v2.36. Authenticated `POST /jobs` returns HTTP 503 with
`aws_metered_research_accounting_unavailable` before DynamoDB or SQS writes.
The Fargate worker independently rejects old or manually queued work before it
imports or constructs a provider. Health and read-only job, result, and cost
inspection remain available. Supplying provider keys does not enable dispatch.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ API Gateway  │────▶│    Lambda    │────▶│     SQS      │
│              │     │  (deepr-api) │     │ (job queue)  │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                     ┌──────────────┐     ┌──────▼───────┐
                     │      S3      │◀────│   Fargate    │
                     │  (results)   │     │  (worker)    │
                     └──────────────┘     └──────────────┘
```

## Prerequisites

- AWS CLI configured (`aws configure`)
- SAM CLI installed (`pip install aws-sam-cli`)
- Docker (for building Lambda packages)

## Quick Start

```bash
# 1. Copy and edit environment file
cp .env.example .env
# Edit .env with your API keys

# 2. Build the application
sam build

# 3. Deploy (first time - guided)
sam deploy --guided

# Or deploy with defaults
sam deploy \
  --stack-name deepr \
  --parameter-overrides \
    OpenAIApiKey=$OPENAI_API_KEY \
    GoogleApiKey=$GOOGLE_API_KEY \
    XaiApiKey=$XAI_API_KEY \
  --capabilities CAPABILITY_IAM
```

## Build Worker Container

The Fargate worker requires a Docker image in ECR:

```bash
# Create ECR repository (one time)
aws ecr create-repository --repository-name deepr-worker

# Login to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(aws configure get region).amazonaws.com

# Build and push (from repo root)
docker build -f deploy/aws/src/worker/Dockerfile -t deepr-worker .
docker tag deepr-worker:latest \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(aws configure get region).amazonaws.com/deepr-worker:latest
docker push \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(aws configure get region).amazonaws.com/deepr-worker:latest
```

## Usage

After deployment, SAM outputs the API endpoint:

```bash
# Verify the fail-closed submission boundary
curl -X POST https://xxxxx.execute-api.us-east-1.amazonaws.com/Prod/jobs \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What are the best practices for PostgreSQL connection pooling?"}'
# Expected: HTTP 503 with
# error_code=aws_metered_research_accounting_unavailable

# Check job status
curl https://xxxxx.execute-api.us-east-1.amazonaws.com/Prod/jobs/{job_id}

# Get result
curl https://xxxxx.execute-api.us-east-1.amazonaws.com/Prod/results/{job_id}
```

## Configuration

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Environment | prod | Deployment environment (dev/staging/prod) |
| OpenAIApiKey | - | Accepted by the template but cannot enable v2.36 dispatch |
| GoogleApiKey | - | Accepted by the template but cannot enable v2.36 dispatch |
| XaiApiKey | - | Accepted by the template but cannot enable v2.36 dispatch |
| DailyBudget | 50 | Daily spending limit (USD) |
| MonthlyBudget | 500 | Monthly spending limit (USD) |

### Scaling

Workers auto-scale based on:
- CPU utilization (target: 70%)
- Queue depth (scale up when > 5 messages)

Adjust in `template.yaml`:
- `WorkerScalingTarget.MaxCapacity`: Max workers (default: 10)
- `QueueDepthAlarm.Threshold`: Queue depth trigger (default: 5)

## Monitoring

### CloudWatch Logs

- API: `/aws/lambda/deepr-api-{env}`
- Worker: `/aws/fargate/deepr-worker-{env}`

### CloudWatch Metrics

- SQS: `ApproximateNumberOfMessagesVisible`
- Lambda: `Invocations`, `Duration`, `Errors`
- ECS: `CPUUtilization`, `MemoryUtilization`

### Alarms

The stack creates a `deepr-queue-depth-{env}` alarm that triggers when the queue backs up.

## Costs

Estimated monthly costs (varies by usage):

| Component | Estimated Cost |
|-----------|---------------|
| Lambda (API) | $5-20 |
| Fargate (worker) | $20-100 |
| SQS | $1-5 |
| S3 | $1-10 |
| **Total infrastructure** | **$30-150** |

The v2.36 gate prevents LLM API research costs. Infrastructure resources can
still incur the costs above.

## Cleanup

```bash
# Delete stack (keeps S3 bucket by default)
sam delete --stack-name deepr

# To delete S3 bucket too
aws s3 rm s3://deepr-results-prod-{account-id} --recursive
aws s3 rb s3://deepr-results-prod-{account-id}
```

## Troubleshooting

### Jobs stuck in queue

Check worker logs:
```bash
aws logs tail /aws/fargate/deepr-worker-prod --follow
```

### API errors

Check Lambda logs:
```bash
aws logs tail /aws/lambda/deepr-api-prod --follow
```

### Authentication issues

Verify secrets:
```bash
aws secretsmanager get-secret-value --secret-id deepr/prod/api-keys
```
