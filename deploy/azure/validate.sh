#!/bin/bash
# Validate Deepr Azure deployment
# Usage: API_URL=https://... API_KEY=... ./validate.sh

set -e

# Configuration
API_URL="${API_URL:-}"
API_KEY="${API_KEY:-}"
RESOURCE_GROUP="${DEEPR_RESOURCE_GROUP:-deepr-rg}"

# Auto-detect API URL from deployment if not provided
if [ -z "$API_URL" ]; then
    API_URL=$(az deployment group show \
        --resource-group "$RESOURCE_GROUP" \
        --name main \
        --query "properties.outputs.functionAppUrl.value" \
        --output tsv 2>/dev/null || echo "")
fi

if [ -z "$API_URL" ]; then
    echo "Error: API_URL not set and could not be auto-detected from resource group '$RESOURCE_GROUP'"
    exit 1
fi

echo "Validating Deepr deployment at: $API_URL"
echo "============================================"

PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo "  [PASS] $name"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name"
        FAIL=$((FAIL + 1))
    fi
}

# 1. Health check
echo ""
echo "1. Health Check"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/health" 2>/dev/null || echo "000")
check "GET /api/health returns 200" $([ "$HTTP_CODE" = "200" ] && echo 0 || echo 1)

# 2. Submit a test job
echo ""
echo "2. Submit Test Job"
if [ -n "$API_KEY" ]; then
    SUBMIT_RESPONSE=$(curl -s -X POST "$API_URL/api/jobs" \
        -H "Content-Type: application/json" \
        -H "X-Api-Key: $API_KEY" \
        -d '{"prompt": "What is 2+2? Answer in one word.", "model": "grok-4-fast"}' 2>/dev/null || echo "{}")
else
    SUBMIT_RESPONSE=$(curl -s -X POST "$API_URL/api/jobs" \
        -H "Content-Type: application/json" \
        -d '{"prompt": "What is 2+2? Answer in one word.", "model": "grok-4-fast"}' 2>/dev/null || echo "{}")
fi

JOB_ID=$(echo "$SUBMIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null || echo "")
check "POST /api/jobs returns job_id" $([ -n "$JOB_ID" ] && echo 0 || echo 1)

# 3. Check job status
echo ""
echo "3. Check Job Status"
if [ -n "$JOB_ID" ] && [ -n "$API_KEY" ]; then
    STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/jobs/$JOB_ID" \
        -H "X-Api-Key: $API_KEY" 2>/dev/null || echo "000")
elif [ -n "$JOB_ID" ]; then
    STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/jobs/$JOB_ID" 2>/dev/null || echo "000")
else
    STATUS_CODE="000"
fi
check "GET /api/jobs/{id} returns 200" $([ "$STATUS_CODE" = "200" ] && echo 0 || echo 1)

# 4. Check costs endpoint
echo ""
echo "4. Cost Endpoint"
if [ -n "$API_KEY" ]; then
    COST_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/costs" \
        -H "X-Api-Key: $API_KEY" 2>/dev/null || echo "000")
else
    COST_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/costs" 2>/dev/null || echo "000")
fi
check "GET /api/costs returns 200" $([ "$COST_CODE" = "200" ] && echo 0 || echo 1)

# Summary
echo ""
echo "============================================"
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    echo "VALIDATION FAILED"
    exit 1
else
    echo "VALIDATION PASSED"
    exit 0
fi
