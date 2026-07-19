#!/bin/bash
# Deploy Deepr to Azure

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/../shared/load-env.sh"
load_env_file "${DEEPR_ENV_FILE:-$SCRIPT_DIR/.env}"

# Configuration
RESOURCE_GROUP="${DEEPR_RESOURCE_GROUP:-deepr-rg}"
LOCATION="${DEEPR_LOCATION:-eastus}"
ENVIRONMENT="${DEEPR_ENVIRONMENT:-prod}"

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
umask 077
PARAMETERS_FILE="$(mktemp "${TMPDIR:-/tmp}/deepr-azure-parameters.XXXXXX.json")"
trap 'rm -f "$PARAMETERS_FILE"' EXIT
export DEEPR_DEPLOY_ENVIRONMENT="$ENVIRONMENT"
python3 - <<'PY' > "$PARAMETERS_FILE"
import json
import os

parameters = {
    "environment": {"value": os.environ["DEEPR_DEPLOY_ENVIRONMENT"]},
    "openaiApiKey": {"value": os.environ["OPENAI_API_KEY"]},
    "googleApiKey": {"value": os.environ.get("GOOGLE_API_KEY", "")},
    "xaiApiKey": {"value": os.environ.get("XAI_API_KEY", "")},
    "dailyBudget": {"value": int(os.environ.get("DEEPR_BUDGET_DAILY", "10"))},
    "monthlyBudget": {"value": int(os.environ.get("DEEPR_BUDGET_MONTHLY", "10"))},
}
print(json.dumps({"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#", "contentVersion": "1.0.0.0", "parameters": parameters}))
PY
az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file "$SCRIPT_DIR/main.bicep" \
    --parameters "@$PARAMETERS_FILE" \
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
echo "  1. Deploy function app code: cd functions && func azure functionapp publish deepr-${ENVIRONMENT}-api"
echo "  2. Build and push worker container to ACR"
echo "  3. Test the API: curl ${FUNCTION_APP_URL}/api/health"

# Run validation
if [ -f "$SCRIPT_DIR/validate.sh" ]; then
    echo ""
    echo "Running validation..."
    API_URL="$FUNCTION_APP_URL" bash "$SCRIPT_DIR/validate.sh"
fi
