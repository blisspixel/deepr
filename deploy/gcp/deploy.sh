#!/bin/bash
# Deploy Deepr to GCP

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-us-central1}"
ENVIRONMENT="${DEEPR_ENVIRONMENT:-prod}"

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Validate required variables
if [ -z "$PROJECT_ID" ]; then
    echo "Error: GCP_PROJECT_ID is required"
    exit 1
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY is required"
    exit 1
fi

echo "Deploying Deepr to GCP..."
echo "  Project: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Environment: $ENVIRONMENT"

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

# Create terraform.tfvars
cat > terraform.tfvars <<EOF
project_id     = "$PROJECT_ID"
region         = "$REGION"
environment    = "$ENVIRONMENT"
openai_api_key = "$OPENAI_API_KEY"
google_api_key = "${GOOGLE_API_KEY:-}"
xai_api_key    = "${XAI_API_KEY:-}"
daily_budget   = ${DEEPR_BUDGET_DAILY:-50}
monthly_budget = ${DEEPR_BUDGET_MONTHLY:-500}
EOF

# Apply Terraform
echo "Deploying infrastructure..."
terraform apply -auto-approve

# Get outputs
API_URL=$(terraform output -raw api_url)

echo ""
echo "Deployment complete!"
echo "  API URL: $API_URL"
echo ""
echo "Next steps:"
echo "  1. Build and push worker container to Artifact Registry"
echo "  2. Test the API: curl $API_URL/health"

# Cleanup sensitive file
rm -f terraform.tfvars
