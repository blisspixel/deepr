#!/bin/bash
# Reference-only cloud validation stub.

echo "BLOCKED: hosted cloud validation is reference-only in the current release."
echo "This script cannot enforce the operator's total dollar ceiling."
echo "This script cannot contact Azure, an HTTP endpoint, or a provider."
echo "Use the supported local container and local-only validation instead."
exit 2
