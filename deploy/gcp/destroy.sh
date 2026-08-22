#!/bin/bash
echo "BLOCKED: legacy GCP cloud operations are reference-only in the current release."
echo "This script cannot enforce the operator's total dollar ceiling."
echo "Use the GCP console with human approval for existing resources."
exit 2
