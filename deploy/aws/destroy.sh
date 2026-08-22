#!/bin/bash
echo "BLOCKED: legacy AWS cloud operations are reference-only in the current release."
echo "This script cannot enforce the operator's total dollar ceiling."
echo "Use the AWS account console with human approval for existing resources."
exit 2
