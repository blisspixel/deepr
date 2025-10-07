# Comprehensive test validation - all local tests without API calls

Write-Host "============================================================"
Write-Host "Deepr Local Test Validation"
Write-Host "============================================================"
Write-Host ""
Write-Host "Running all unit tests without API calls..."
Write-Host ""

python -m pytest tests/unit/ -v --tb=short -m "not integration"

Write-Host ""
Write-Host "============================================================"
Write-Host "Test Summary"
Write-Host "============================================================"
Write-Host ""
Write-Host "All tests run locally without API costs."
Write-Host "Integration tests (marked with @pytest.mark.integration) are skipped."
Write-Host ""
