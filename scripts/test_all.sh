#!/bin/bash
# Comprehensive test validation - all local tests without API calls

echo "============================================================"
echo "Deepr Local Test Validation"
echo "============================================================"
echo ""
echo "Running all unit tests without API calls..."
echo ""

python -m pytest tests/unit/ -v --tb=short -m "not integration"

echo ""
echo "============================================================"
echo "Test Summary"
echo "============================================================"
echo ""
echo "All tests run locally without API costs."
echo "Integration tests (marked with @pytest.mark.integration) are skipped."
echo ""
