#!/bin/bash
# Expert Test Runner - Bash
# Runs expert chat tests to validate agentic workflow

echo ""
echo "======================================================================"
echo "  EXPERT AGENTIC WORKFLOW TEST SUITE"
echo "======================================================================"
echo ""

# Check if Midjourney Expert exists
echo "Checking prerequisites..."
if [ ! -f "data/experts/midjourney_expert/profile.json" ]; then
    echo ""
    echo "❌ Midjourney Expert not found"
    echo ""
    echo "Create it first:"
    echo '  deepr expert make "Midjourney Expert" --description "Midjourney AI art" --learn --docs 1 --yes'
    echo ""
    exit 1
fi

echo "✓ Midjourney Expert found"
echo ""

# Menu
echo "Select test to run:"
echo "  1. Quick Test (1 simple question, ~30 seconds)"
echo "  2. Full Workflow Test (4 scenarios, ~2-3 minutes)"
echo "  3. Full + Expensive Test (includes deep research, ~20 minutes, costs \$0.10-0.30)"
echo "  4. All Tests"
echo ""

read -p "Enter choice (1-4): " choice

case $choice in
    1)
        echo ""
        echo "Running Quick Test..."
        python tests/test_expert_quick.py
        ;;
    2)
        echo ""
        echo "Running Full Workflow Test..."
        python tests/test_expert_agentic_workflow.py
        ;;
    3)
        echo ""
        echo "⚠ WARNING: This will trigger deep research (costs \$0.10-0.30, takes 5-20 min)"
        read -p "Continue? (y/n): " confirm
        if [ "$confirm" = "y" ]; then
            export RUN_EXPENSIVE_TESTS=1
            python tests/test_expert_agentic_workflow.py
            unset RUN_EXPENSIVE_TESTS
        else
            echo "Cancelled"
        fi
        ;;
    4)
        echo ""
        echo "Running All Tests..."
        echo ""
        
        echo "1/2: Quick Test"
        python tests/test_expert_quick.py
        quick_result=$?
        
        echo ""
        echo "2/2: Full Workflow Test"
        python tests/test_expert_agentic_workflow.py
        workflow_result=$?
        
        echo ""
        echo "======================================================================"
        echo "  ALL TESTS COMPLETE"
        echo "======================================================================"
        
        if [ $quick_result -eq 0 ] && [ $workflow_result -eq 0 ]; then
            echo "✓ All tests passed!"
            exit 0
        else
            echo "❌ Some tests failed"
            exit 1
        fi
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
if [ $? -eq 0 ]; then
    echo "✓ Test completed successfully"
else
    echo "❌ Test failed"
fi

exit $?
