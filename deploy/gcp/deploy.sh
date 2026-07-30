#!/bin/bash
# Reference-only GCP deployment boundary.

set -e

echo "BLOCKED: Deepr cannot enforce the operator's total dollar ceiling over GCP infrastructure."
echo "The template remains available for local review, but this script will not package, initialize, or apply it."
echo "Use the GCP console with human approval for existing resources."
exit 2
