#!/bin/bash
# Destroy Deepr GCP deployment

set -e

PROJECT_ID="${GCP_PROJECT_ID:-}"

if [ -z "$PROJECT_ID" ]; then
    echo "Error: GCP_PROJECT_ID is required"
    exit 1
fi

echo "WARNING: This will destroy all Deepr infrastructure in GCP project '$PROJECT_ID'."
echo "All resources (functions, storage, firestore, secrets) will be permanently deleted."
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
echo "Destroying Terraform-managed resources..."

# Set project
gcloud config set project "$PROJECT_ID"

# Destroy via Terraform
terraform destroy -auto-approve

echo ""
echo "Verifying teardown..."

# Check if any resources remain
REMAINING=$(terraform state list 2>/dev/null | wc -l || echo "0")

if [ "$REMAINING" -eq 0 ] || [ "$REMAINING" = "0" ]; then
    echo "All Terraform-managed resources successfully destroyed."
else
    echo "WARNING: $REMAINING resources still in Terraform state."
    echo "Run 'terraform state list' to inspect remaining resources."
fi

# Cleanup local files
rm -f terraform.tfvars
rm -f functions/function-source.zip

echo ""
echo "Teardown complete."
