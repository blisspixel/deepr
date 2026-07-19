#!/bin/bash
# Deploy Deepr to GCP

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/../shared/load-env.sh"
load_env_file "${DEEPR_ENV_FILE:-$SCRIPT_DIR/.env}"

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-us-central1}"
ENVIRONMENT="${DEEPR_ENVIRONMENT:-prod}"

# Validate required variables
if [ -z "$PROJECT_ID" ]; then
    echo "Error: GCP_PROJECT_ID is required"
    exit 1
fi

if [ -z "$DEEPR_GCP_OPENAI_SECRET_ID" ]; then
    echo "Error: DEEPR_GCP_OPENAI_SECRET_ID is required"
    exit 1
fi

echo "Deploying Deepr to GCP..."
echo "  Project: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Environment: $ENVIRONMENT"
cd "$SCRIPT_DIR"

# Set project
gcloud config set project "$PROJECT_ID"

# Create function source zip
echo "Packaging function source..."
cd functions
zip -r function-source.zip main.py requirements.txt
cd ..

# Initialize Terraform
echo "Initializing Terraform..."
terraform init

# Create a protected temporary variables file. Provider secret values never
# enter Terraform variables or state; only a pre-created secret ID is passed.
umask 077
TFVARS_FILE="$(mktemp "${TMPDIR:-/tmp}/deepr-gcp-tfvars.XXXXXX.json")"
trap 'rm -f "$TFVARS_FILE"' EXIT
export DEEPR_DEPLOY_PROJECT_ID="$PROJECT_ID"
export DEEPR_DEPLOY_REGION="$REGION"
export DEEPR_DEPLOY_ENVIRONMENT="$ENVIRONMENT"
python3 - <<'PY' > "$TFVARS_FILE"
import json
import os

print(json.dumps({
    "project_id": os.environ["DEEPR_DEPLOY_PROJECT_ID"],
    "region": os.environ["DEEPR_DEPLOY_REGION"],
    "environment": os.environ["DEEPR_DEPLOY_ENVIRONMENT"],
    "openai_secret_id": os.environ["DEEPR_GCP_OPENAI_SECRET_ID"],
    "daily_budget": int(os.environ.get("DEEPR_BUDGET_DAILY", "10")),
    "monthly_budget": int(os.environ.get("DEEPR_BUDGET_MONTHLY", "10")),
}))
PY

# Apply Terraform
echo "Deploying infrastructure..."
terraform apply -auto-approve -var-file="$TFVARS_FILE"

# Get outputs
API_URL=$(terraform output -raw api_url)

echo ""
echo "Deployment complete!"
echo "  API URL: $API_URL"
echo ""
echo "Next steps:"
echo "  1. Build and push worker container to Artifact Registry"
echo "  2. Test the API: curl $API_URL/health"

# Run validation
if [ -f "$SCRIPT_DIR/validate.sh" ]; then
    echo ""
    echo "Running validation..."
    API_URL="$API_URL" bash "$SCRIPT_DIR/validate.sh"
fi
