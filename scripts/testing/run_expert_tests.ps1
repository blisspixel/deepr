# Expert Test Runner - PowerShell
# Runs expert chat tests to validate agentic workflow

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  EXPERT AGENTIC WORKFLOW TEST SUITE" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Midjourney Expert exists
Write-Host "Checking prerequisites..." -ForegroundColor Yellow
$expertExists = Test-Path "data/experts/midjourney_expert/profile.json"

if (-not $expertExists) {
    Write-Host ""
    Write-Host "❌ Midjourney Expert not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Create it first:" -ForegroundColor Yellow
    Write-Host '  deepr expert make "Midjourney Expert" --description "Midjourney AI art" --learn --docs 1 --yes' -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "✓ Midjourney Expert found" -ForegroundColor Green
Write-Host ""

# Menu
Write-Host "Select test to run:" -ForegroundColor Cyan
Write-Host "  1. Quick Test (1 simple question, ~30 seconds)" -ForegroundColor White
Write-Host "  2. Full Workflow Test (4 scenarios, ~2-3 minutes)" -ForegroundColor White
Write-Host "  3. Full + Expensive Test (includes deep research, ~20 minutes, costs $0.10-0.30)" -ForegroundColor White
Write-Host "  4. All Tests" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Enter choice (1-4)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Running Quick Test..." -ForegroundColor Cyan
        python tests/test_expert_quick.py
    }
    "2" {
        Write-Host ""
        Write-Host "Running Full Workflow Test..." -ForegroundColor Cyan
        python tests/test_expert_agentic_workflow.py
    }
    "3" {
        Write-Host ""
        Write-Host "⚠ WARNING: This will trigger deep research (costs $0.10-0.30, takes 5-20 min)" -ForegroundColor Yellow
        $confirm = Read-Host "Continue? (y/n)"
        if ($confirm -eq "y") {
            $env:RUN_EXPENSIVE_TESTS = "1"
            python tests/test_expert_agentic_workflow.py
            Remove-Item Env:\RUN_EXPENSIVE_TESTS
        } else {
            Write-Host "Cancelled" -ForegroundColor Yellow
        }
    }
    "4" {
        Write-Host ""
        Write-Host "Running All Tests..." -ForegroundColor Cyan
        Write-Host ""
        
        Write-Host "1/2: Quick Test" -ForegroundColor Cyan
        python tests/test_expert_quick.py
        $quickResult = $LASTEXITCODE
        
        Write-Host ""
        Write-Host "2/2: Full Workflow Test" -ForegroundColor Cyan
        python tests/test_expert_agentic_workflow.py
        $workflowResult = $LASTEXITCODE
        
        Write-Host ""
        Write-Host "======================================================================" -ForegroundColor Cyan
        Write-Host "  ALL TESTS COMPLETE" -ForegroundColor Cyan
        Write-Host "======================================================================" -ForegroundColor Cyan
        
        if ($quickResult -eq 0 -and $workflowResult -eq 0) {
            Write-Host "✓ All tests passed!" -ForegroundColor Green
            exit 0
        } else {
            Write-Host "❌ Some tests failed" -ForegroundColor Red
            exit 1
        }
    }
    default {
        Write-Host "Invalid choice" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Test completed successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Test failed" -ForegroundColor Red
}

exit $LASTEXITCODE
