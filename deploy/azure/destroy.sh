#!/bin/bash
# Destroy Deepr Azure deployment

set -e

RESOURCE_GROUP="${DEEPR_RESOURCE_GROUP:-deepr-rg}"

echo "WARNING: This will destroy the Azure resource group '$RESOURCE_GROUP'."
echo "All resources (functions, storage, cosmos DB, key vault) will be permanently deleted."
echo ""

# Confirm unless --yes flag is passed
if [ "$1" != "--yes" ]; then
    read -p "Are you sure? Type 'yes' to confirm: " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
fi

echo ""
echo "Destroying resource group: $RESOURCE_GROUP..."

az group delete \
    --name "$RESOURCE_GROUP" \
    --yes \
    --no-wait

echo ""
echo "Resource group deletion initiated (running in background)."
echo "Monitor progress: az group show --name $RESOURCE_GROUP --query properties.provisioningState"
echo ""

# Wait briefly and check status
sleep 5
RG_STATE=$(az group show --name "$RESOURCE_GROUP" --query "properties.provisioningState" --output tsv 2>/dev/null || echo "Deleted")

if [ "$RG_STATE" = "Deleting" ]; then
    echo "Resource group is being deleted. This may take several minutes."
elif [ "$RG_STATE" = "Deleted" ] || [ "$RG_STATE" = "" ]; then
    echo "Resource group '$RESOURCE_GROUP' successfully destroyed."
else
    echo "Resource group state: $RG_STATE"
fi
