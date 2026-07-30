#!/bin/bash
# Reference-only Azure deployment boundary.

set -e

echo "BLOCKED: Deepr cannot enforce the operator's total dollar ceiling over Azure infrastructure."
echo "The template remains available for local review, but this script will not create a resource group or deployment."
echo "Use the Azure portal with human approval for existing resources."
exit 2
