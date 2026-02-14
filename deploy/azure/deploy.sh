#!/bin/bash
# Deploy Deepr to Azure

set -e

# Configuration
RESOURCE_GROUP="${DEEPR_RESOURCE_GROUP:-deepr-rg}"
LOCATION="${DEEPR_LOCATION:-eastus}"
ENVIRONMENT="${DEEPR_ENVIRONMENT:-prod}"

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Validate required variables
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY is required"
    exit 1
fi

echo "Deploying Deepr to Azure..."
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Location: $LOCATION"
echo "  Environment: $ENVIRONMENT"

# Create resource group if it doesn't exist
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none 2>/dev/null || true

# Deploy infrastructure
echo "Deploying infrastructure..."
az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file main.bicep \
    --parameters \
        environment="$ENVIRONMENT" \
        openaiApiKey="$OPENAI_API_KEY" \
        googleApiKey="${GOOGLE_API_KEY:-}" \
        xaiApiKey="${XAI_API_KEY:-}" \
        dailyBudget="${DEEPR_BUDGET_DAILY:-50}" \
        monthlyBudget="${DEEPR_BUDGET_MONTHLY:-500}" \
    --output table

# Get outputs
FUNCTION_APP_URL=$(az deployment group show \
    --resource-group "$RESOURCE_GROUP" \
    --name main \
    --query "properties.outputs.functionAppUrl.value" \
    --output tsv)

echo ""
echo "Deployment complete!"
echo "  API URL: $FUNCTION_APP_URL"
echo ""
echo "Next steps:"
echo "  1. Deploy function app code: cd function_app && func azure functionapp publish deepr-${ENVIRONMENT}-api"
echo "  2. Build and push worker container to ACR"
echo "  3. Test the API: curl ${FUNCTION_APP_URL}/api/health"

# Run validation
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/validate.sh" ]; then
    echo ""
    echo "Running validation..."
    API_URL="$FUNCTION_APP_URL" bash "$SCRIPT_DIR/validate.sh"
fi
