#!/bin/bash
# Deploy Deepr to AWS using SAM

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/../shared/load-env.sh"
load_env_file "${DEEPR_ENV_FILE:-$SCRIPT_DIR/.env}"

# Configuration
STACK_NAME="${DEEPR_STACK_NAME:-deepr-prod}"
REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${DEEPR_ENVIRONMENT:-prod}"

# Validate required variables
if [ -z "$DEEPR_AWS_PROVIDER_SECRET_ARN" ]; then
    echo "Error: DEEPR_AWS_PROVIDER_SECRET_ARN is required"
    exit 1
fi

echo "Deploying Deepr to AWS..."
echo "  Stack Name: $STACK_NAME"
echo "  Region: $REGION"
echo "  Environment: $ENVIRONMENT"
cd "$SCRIPT_DIR"

# Build
echo "Building SAM application..."
sam build

# Deploy
echo "Deploying infrastructure..."
sam deploy \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --resolve-s3 \
    --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
    --parameter-overrides \
        Environment="$ENVIRONMENT" \
        ProviderSecretArn="$DEEPR_AWS_PROVIDER_SECRET_ARN" \
        DailyBudget="${DEEPR_BUDGET_DAILY:-10}" \
        MonthlyBudget="${DEEPR_BUDGET_MONTHLY:-10}" \
    --no-confirm-changeset

# Get outputs
API_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
    --output text)

echo ""
echo "Deployment complete!"
echo "  API URL: $API_URL"
echo ""

# Run validation
if [ -f "$SCRIPT_DIR/validate.sh" ]; then
    echo "Running validation..."
    API_URL="$API_URL" bash "$SCRIPT_DIR/validate.sh"
fi
