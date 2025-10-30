# Deepr Testing Guide

## Overview

Deepr has a comprehensive test suite organized into three layers:

1. **Unit Tests** - Fast, isolated tests with no external dependencies (free)
2. **Integration Tests** - Tests that validate provider APIs and CLI commands (small cost)
3. **End-to-End Tests** - Complete workflow validation (small cost)

## Test Structure

```
tests/
├── unit/                          # Unit tests (no API calls)
│   ├── test_costs.py             # Cost calculation and budget logic
│   ├── test_queue/               # Queue operations
│   └── test_storage/             # Storage operations
├── integration/                   # Integration tests (real API calls)
│   ├── test_cli_commands.py      # CLI command structure validation
│   ├── test_cli_e2e.py           # End-to-end CLI workflows
│   ├── test_all_providers.py     # All provider validation
│   ├── test_provider_validation.py # Gemini/Grok specific tests
│   └── test_real_api.py          # OpenAI integration tests
├── conftest.py                    # Shared fixtures
├── pytest.ini                     # Test configuration
└── README.md                      # Detailed test documentation
```

## Quick Start

**Run all tests that don't require API keys:**
```bash
pytest -m "not requires_api"
```

**Run only unit tests (fastest, free):**
```bash
pytest -m unit
```

**Run CLI command tests:**
```bash
pytest tests/integration/test_cli_commands.py -v
```

**Run with specific provider:**
```bash
# Requires GEMINI_API_KEY in .env
pytest tests/integration/test_provider_validation.py::test_gemini_provider_basic -v
```

## Test Results

### CLI Command Tests (test_cli_commands.py)

All tests passing:
- New command structure (focus, project, docs, jobs)
- Deprecated command warnings
- Help output validation
- Parameter validation
- Command consistency

**Status:** 14/14 tests passing

### Unit Tests (test_costs.py)

All tests passing:
- Cost estimation logic
- Budget management
- Token calculations
- Safe test prompts

**Status:** 14/14 tests passing

### Provider Integration Tests

Tests validate:
- Basic query execution
- Cost tracking
- Response format
- Error handling

**Providers Tested:**
- OpenAI (o4-mini-deep-research, o3-deep-research)
- Gemini (2.5-flash, 2.5-pro)
- Grok (grok-4-fast, grok-4)
- Azure OpenAI

## Testing New Features

### Testing New CLI Commands

1. Add tests to `tests/integration/test_cli_commands.py`
2. Test command help output
3. Test required parameters
4. Test deprecation warnings (if applicable)

Example:
```python
@pytest.mark.integration
def test_new_command_exists():
    result = subprocess.run(
        ["deepr", "new-command", "--help"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert "expected text" in result.stdout
```

### Testing New Providers

1. Add tests to `tests/integration/test_all_providers.py`
2. Test basic query
3. Test cost tracking
4. Test error handling

Example:
```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_new_provider_basic():
    if not os.getenv("NEW_PROVIDER_API_KEY"):
        pytest.skip("API key not set")

    provider = NewProvider()

    request = ResearchRequest(
        prompt="Simple test query",
        model="provider-model",
        tools=[],
        background=False
    )

    job_id = await provider.submit_research(request)
    response = await provider.get_status(job_id)

    validate_research_response(response, "NewProvider")
```

## Cost Optimization

Tests are designed to minimize API costs:

- Use simple queries ("What is 2+2?")
- Skip tests if API keys not available
- Limit test execution time
- Use fast models (gemini-2.5-flash, grok-4-fast)

**Estimated costs:**
- Unit tests: $0
- CLI tests: $0 (no API calls)
- Provider integration tests: $0.10-0.50 total
- E2E tests: $0.05-0.20 total

**Total cost to run full suite: $0.50-1.00**

## Continuous Integration

For CI/CD pipelines:

```bash
# Fast tests only
pytest -m "unit and not slow"

# Integration tests with timeout
pytest -m integration --timeout=300

# Generate coverage report
pytest --cov=deepr --cov-report=html --cov-report=term
```

## Test Markers

```python
@pytest.mark.unit              # No external dependencies
@pytest.mark.integration       # May require API keys
@pytest.mark.e2e              # Full workflow tests
@pytest.mark.requires_api      # Requires API keys, costs money
@pytest.mark.slow             # Takes >1 second
```

## Debugging Failed Tests

**Verbose output:**
```bash
pytest -vv -s
```

**Stop on first failure:**
```bash
pytest -x
```

**Run only failed tests:**
```bash
pytest --lf
```

**Debug with pdb:**
```bash
pytest --pdb
```

## Test Coverage

Current coverage targets:
- Core logic: 80%+
- Providers: 100% (all providers tested)
- CLI commands: 100% (all commands tested)
- Workflows: 90%+ (key user paths covered)

Check coverage:
```bash
pytest --cov=deepr --cov-report=term-missing
```

## Adding New Tests

1. Determine test type (unit/integration/e2e)
2. Add to appropriate directory
3. Use correct markers
4. Follow naming convention: `test_*.py` and `test_*()` functions
5. Add docstrings explaining what is tested
6. Skip tests gracefully if dependencies missing

## Common Issues

**Tests hanging:**
- Check timeout settings
- Verify API keys are valid
- Check network connectivity

**API key errors:**
- Verify .env file exists and has correct keys
- Check key format (no extra spaces/quotes)

**Tests skipped:**
- Normal if API keys not configured
- Tests skip gracefully with reason

**Unexpected costs:**
- Review test execution plan
- Run unit tests only for development

## Reporting Issues

When reporting test failures, include:
1. Test name and full path
2. Pytest output (`-vv`)
3. Provider name (if applicable)
4. Error message and stack trace
5. Environment (OS, Python version)

## Further Reading

- [tests/README.md](../tests/README.md) - Detailed test documentation
- [pytest.ini](../tests/pytest.ini) - Test configuration
- [conftest.py](../tests/conftest.py) - Shared fixtures
