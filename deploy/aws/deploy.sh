#!/bin/bash
# Reference-only AWS deployment boundary.

set -e

echo "BLOCKED: Deepr cannot enforce the operator's total dollar ceiling over AWS infrastructure."
echo "The template remains available for local review, but this script will not build or deploy it."
echo "Use the AWS account console with human approval for existing resources."
exit 2
