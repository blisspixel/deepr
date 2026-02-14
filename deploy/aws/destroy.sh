#!/bin/bash
# Destroy Deepr AWS deployment

set -e

STACK_NAME="${DEEPR_STACK_NAME:-deepr-prod}"
REGION="${AWS_REGION:-us-east-1}"

echo "WARNING: This will destroy the Deepr AWS stack '$STACK_NAME' in region '$REGION'."
echo "All data (jobs, results, secrets) will be permanently deleted."
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
echo "Destroying stack: $STACK_NAME..."

# Empty S3 buckets first (CloudFormation can't delete non-empty buckets)
BUCKET=$(aws cloudformation describe-stack-resources \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" \
    --output text 2>/dev/null || echo "")

if [ -n "$BUCKET" ]; then
    echo "Emptying S3 bucket: $BUCKET"
    aws s3 rm "s3://$BUCKET" --recursive --region "$REGION" 2>/dev/null || true
fi

# Delete the stack
sam delete \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --no-prompts

echo ""
echo "Verifying teardown..."
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].StackStatus" \
    --output text 2>/dev/null || echo "DELETE_COMPLETE")

if [ "$STACK_STATUS" = "DELETE_COMPLETE" ] || [ "$STACK_STATUS" = "" ]; then
    echo "Stack '$STACK_NAME' successfully destroyed."
else
    echo "WARNING: Stack status is '$STACK_STATUS'. It may still be deleting."
    echo "Check AWS Console for details."
fi
