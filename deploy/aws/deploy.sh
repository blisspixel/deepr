#!/bin/bash
# Deploy Deepr to AWS using SAM

set -e

# Configuration
STACK_NAME="${DEEPR_STACK_NAME:-deepr-prod}"
REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${DEEPR_ENVIRONMENT:-prod}"

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Validate required variables
if [ -z "$OPENAI_API_KEY" ] && [ -z "$GEMINI_API_KEY" ] && [ -z "$XAI_API_KEY" ]; then
    echo "Error: At least one provider API key is required (OPENAI_API_KEY, GEMINI_API_KEY, or XAI_API_KEY)"
    exit 1
fi

echo "Deploying Deepr to AWS..."
echo "  Stack Name: $STACK_NAME"
echo "  Region: $REGION"
echo "  Environment: $ENVIRONMENT"

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
        OpenAIApiKey="${OPENAI_API_KEY:-}" \
        GoogleApiKey="${GOOGLE_API_KEY:-}" \
        XaiApiKey="${XAI_API_KEY:-}" \
        DailyBudget="${DEEPR_BUDGET_DAILY:-50}" \
        MonthlyBudget="${DEEPR_BUDGET_MONTHLY:-500}" \
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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/validate.sh" ]; then
    echo "Running validation..."
    API_URL="$API_URL" bash "$SCRIPT_DIR/validate.sh"
fi
