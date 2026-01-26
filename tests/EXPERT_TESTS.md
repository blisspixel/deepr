# Expert Agentic Workflow Tests

Comprehensive test suite to validate the expert's natural thinking workflow.

## Overview

These tests validate that experts think like real experts:

1. **Simple questions** - Answer directly (no tools needed)
2. **Domain questions** - Search knowledge base, synthesize
3. **Current info** - Web search when knowledge base is empty
4. **Complex questions** - Trigger deep research for analysis

## Prerequisites

Create the Midjourney Expert first:

```bash
deepr expert make "Midjourney Expert" --description "Midjourney AI art" --learn --docs 1 --yes
```

This takes ~2 minutes and costs ~$0.002.

## Running Tests

### Quick Test (Recommended)

Fast smoke test to verify basic functionality:

```bash
python tests/test_expert_quick.py
```

**Time:** ~30 seconds  
**Cost:** ~$0.01  
**Tests:** 1 simple question

### Full Workflow Test

Tests all 4 scenarios (except expensive deep research):

```bash
python tests/test_expert_agentic_workflow.py
```

**Time:** ~2-3 minutes  
**Cost:** ~$0.05  
**Tests:** 4 scenarios

### Full + Expensive Test

Includes deep research test (optional):

```bash
# Set environment variable to enable expensive tests
export RUN_EXPENSIVE_TESTS=1  # Linux/Mac
$env:RUN_EXPENSIVE_TESTS = "1"  # PowerShell

python tests/test_expert_agentic_workflow.py
```

**Time:** ~20 minutes  
**Cost:** ~$0.15-0.35  
**Tests:** 4 scenarios including deep research

### Interactive Test Runner

Use the test runner script for an interactive menu:

**PowerShell (Windows):**
```powershell
.\tests\run_expert_tests.ps1
```

**Bash (Linux/Mac):**
```bash
./tests/run_expert_tests.sh
```

## Test Scenarios

### Scenario 1: Simple Question

**Query:** "What does the --ar parameter do?"

**Expected Behavior:**
- Expert recognizes this as basic knowledge
- Answers directly OR searches knowledge base
- No web search needed
- Fast response (<5 seconds)

**Validates:**
- Expert can answer from knowledge
- No unnecessary tool calls
- Natural, confident response

### Scenario 2: Domain Question

**Query:** "Explain all the key parameters for controlling Midjourney image generation, organized by category"

**Expected Behavior:**
- Expert searches knowledge base
- Finds relevant documents
- Synthesizes comprehensive answer
- Cites sources when appropriate

**Validates:**
- Knowledge base search works
- Expert synthesizes information
- Comprehensive, organized response

### Scenario 3: Current Information

**Query:** "What are the latest Midjourney features announced in January 2026?"

**Expected Behavior:**
- Expert searches knowledge base (empty/outdated)
- Recognizes need for current info
- Triggers web search (Grok)
- Integrates web results into answer

**Validates:**
- Expert recognizes knowledge gaps
- Web search triggers correctly
- Current information retrieved
- Results integrated naturally

### Scenario 4: Complex Question (Optional)

**Query:** "Design a comprehensive workflow for a creative agency using Midjourney, including prompt templates, style management, version control, and team collaboration strategies"

**Expected Behavior:**
- Expert recognizes complexity
- Triggers deep research
- Waits for analysis (5-20 min)
- Provides comprehensive strategic answer

**Validates:**
- Expert recognizes complex questions
- Deep research triggers correctly
- Comprehensive analysis provided

**Note:** This test is OPTIONAL because it costs $0.10-0.30 and takes 5-20 minutes.

## Understanding Test Results

### Success Indicators

- **Response received** - Expert generated a response  
- **Cost tracked** - Token usage calculated correctly  
- **Tool calls logged** - Reasoning trace captured  
- **Appropriate tools used** - Right tool for the question  

### What to Look For

**Good Signs:**
- Expert answers simple questions quickly
- Knowledge base searched for domain questions
- Web search used for current info
- Responses are natural and synthesized
- Cost is reasonable for complexity

**Red Flags:**
- Expert always searches even for simple questions
- No tool calls when they're clearly needed
- Web search for info that's in knowledge base
- Responses are just document dumps
- Excessive costs

## Debugging Failed Tests

### Expert Not Found

```
ERROR: Midjourney Expert not found
```

**Solution:** Create the expert first:
```bash
deepr expert make "Midjourney Expert" --description "Midjourney AI art" --learn --docs 1 --yes
```

### API Key Issues

```
FAIL: XAI_API_KEY not set
```

**Solution:** Set API keys in `.env`:
```bash
OPENAI_API_KEY=sk-...
XAI_API_KEY=xai-...
```

### Timeout Errors

```
FAIL: Request timed out
```

**Solution:** 
- Check internet connection
- Verify API keys are valid
- Try again (web search can be slow)

### Tool Not Called

```
WARNING: Expected web search, but expert answered directly
```

**This is OK!** The expert might have:
- Recent documents with the info
- Sufficient knowledge to answer
- Made a judgment call

The test will still pass - we trust expert intelligence.

## Test Philosophy

These tests validate **intelligent behavior**, not rigid rules.

**We DON'T require:**
- Exact tool call sequences
- Specific number of searches
- Predetermined responses

**We DO validate:**
- Expert can answer questions
- Tools are available and work
- Responses are substantive
- Costs are reasonable

The expert is an **intelligent agent**, not a state machine. We trust its judgment about when to search, when to research, and when to just answer.

## Continuous Testing

Run tests after:
- Changing expert system prompts
- Updating tool descriptions
- Modifying agentic logic
- Adding new research tools
- Updating model configurations

## Cost Tracking

Typical costs per test run:

| Test | Time | Cost | Notes |
|------|------|------|-------|
| Quick Test | 30s | $0.01 | 1 question |
| Full Workflow | 2-3 min | $0.05 | 3 scenarios |
| Full + Expensive | 20 min | $0.15-0.35 | Includes deep research |

**Budget recommendation:** Set aside $1-2 for testing.

## Contributing

When adding new test scenarios:

1. Follow the existing pattern
2. Document expected behavior
3. Make tests resilient (trust expert judgment)
4. Track costs and time
5. Update this README

## Questions?

See the main test documentation:
- `tests/README.md` - General testing guide
- `tests/TESTING_SUMMARY.md` - Test results and coverage
- `EXPERT_AGENTIC_REDESIGN.md` - Design philosophy

Or run the tests and see what happens! The expert will show you how it thinks.
