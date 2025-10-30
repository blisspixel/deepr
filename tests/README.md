## Deepr Test Suite

Comprehensive test suite for Deepr covering unit tests, integration tests, and end-to-end workflows.

### Test Organization

```
tests/
├── unit/                          # Unit tests (no API calls, fast, free)
│   ├── test_costs.py             # Cost calculation logic
│   ├── test_queue/               # SQLite queue operations
│   └── test_storage/             # Local storage operations
├── integration/                   # Integration tests (real API calls, costs money)
│   ├── test_cli_commands.py      # New CLI command structure tests
│   ├── test_cli_e2e.py           # End-to-end CLI workflows
│   ├── test_all_providers.py     # Comprehensive provider validation
│   ├── test_provider_validation.py # Gemini and Grok validation
│   └── test_real_api.py          # OpenAI API integration tests
├── conftest.py                    # Pytest fixtures and configuration
└── pytest.ini                     # Pytest settings and markers
```

### Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests (no external dependencies, always free)
- `@pytest.mark.integration` - Integration tests (may require API keys)
- `@pytest.mark.e2e` - End-to-end tests (full workflow validation)
- `@pytest.mark.requires_api` - Tests that require API keys and will cost money
- `@pytest.mark.slow` - Tests that take more than 1 second

### Running Tests

**Run all unit tests (fast, free):**
```bash
pytest -m unit
```

**Run integration tests (requires API keys, costs money):**
```bash
pytest -m integration
```

**Run end-to-end tests (full workflows, costs money):**
```bash
pytest -m e2e
```

**Run CLI command tests only:**
```bash
pytest tests/integration/test_cli_commands.py -v
```

**Run all provider validation tests:**
```bash
pytest tests/integration/test_all_providers.py -v
```

**Run specific test:**
```bash
pytest tests/integration/test_cli_commands.py::test_focus_command_has_correct_options -v
```

**Skip expensive tests:**
```bash
pytest -m "not requires_api"
```

**Run everything (including expensive API tests):**
```bash
pytest
```

### API Keys Required

For integration and e2e tests, you need at least one provider API key configured in `.env`:

```bash
# Required for OpenAI tests
OPENAI_API_KEY=sk-...

# Required for Gemini tests
GEMINI_API_KEY=...

# Required for Grok tests
XAI_API_KEY=...

# Required for Azure tests
AZURE_OPENAI_KEY=...
AZURE_OPENAI_ENDPOINT=https://....openai.azure.com/
AZURE_DEPLOYMENT_O3=...
AZURE_DEPLOYMENT_O4_MINI=...
```

Tests automatically skip if the required API key is not set.

### Cost Estimates

Integration and e2e tests use simple queries to minimize costs:

- **Unit tests**: $0 (no API calls)
- **Integration tests (all providers)**: ~$0.10-0.50
  - OpenAI: ~$0.02-0.10 per test
  - Gemini: ~$0.001-0.01 per test (very cheap)
  - Grok: ~$0.01-0.05 per test
- **End-to-end tests**: ~$0.05-0.20 per test

**Estimated total cost to run full suite**: $1-3

### What Tests Cover

**CLI Command Structure (test_cli_commands.py)**
- New command structure (focus, project, docs, jobs)
- Deprecated command warnings
- Command help output
- Parameter validation
- Quick aliases

**Provider Validation (test_all_providers.py)**
- All providers (OpenAI, Gemini, Grok, Azure)
- Basic query execution
- Cost tracking accuracy
- Response format consistency
- Error handling

**End-to-End Workflows (test_cli_e2e.py)**
- Complete job lifecycle: submit -> status -> get results
- Provider switching
- Budget limits
- Job cancellation
- Deprecated command compatibility

**Unit Tests**
- Cost calculation logic
- Queue operations (CRUD)
- Storage operations
- Context chaining logic

### Test Results Location

Test results and artifacts are saved to:
```
tests/test_results/
├── <timestamp>/
│   ├── test_name_report.md
│   ├── test_name_report.json
│   └── test_name_report.txt
```

### Continuous Integration

For CI/CD pipelines:

```bash
# Fast tests only (no API calls)
pytest -m "unit and not slow"

# Integration tests with timeout
pytest -m integration --timeout=300

# Generate coverage report
pytest --cov=deepr --cov-report=html
```

### Writing New Tests

**Unit Test Template:**
```python
@pytest.mark.unit
def test_my_feature():
    """Test description."""
    # Test implementation (no external calls)
    assert result == expected
```

**Integration Test Template:**
```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_provider_feature():
    """Test description."""
    if not os.getenv("PROVIDER_API_KEY"):
        pytest.skip("API key not set")

    # Test implementation with real API calls
```

**CLI Test Template:**
```python
@pytest.mark.integration
@pytest.mark.e2e
def test_cli_command():
    """Test description."""
    result = subprocess.run(
        ["deepr", "command", "args"],
        capture_output=True,
        text=True,
        timeout=30
    )

    assert result.returncode == 0
    assert "expected" in result.stdout
```

### Debugging Tests

**Run with verbose output:**
```bash
pytest -vv
```

**Show print statements:**
```bash
pytest -s
```

**Stop on first failure:**
```bash
pytest -x
```

**Run last failed tests:**
```bash
pytest --lf
```

**Debug with pdb:**
```bash
pytest --pdb
```

### Test Coverage Goals

- **Unit tests**: 80%+ coverage of core logic
- **Integration tests**: All providers validated
- **E2E tests**: All user workflows covered
- **CLI tests**: All commands and options tested

### Common Issues

**Issue: Tests hanging**
- Solution: Check timeouts, ensure API keys are valid

**Issue: API key errors**
- Solution: Verify `.env` file has correct keys

**Issue: Tests skipped**
- Solution: Normal if API keys not configured, tests skip gracefully

**Issue: Costs higher than expected**
- Solution: Run unit tests only (`pytest -m unit`)

### Reporting Issues

When reporting test failures, include:
1. Test name and marker
2. Full pytest output (`-vv`)
3. API provider (if applicable)
4. Error message and traceback
5. Test results from `tests/test_results/`

### Test Maintenance

- Update tests when CLI commands change
- Add tests for new features
- Keep integration tests cheap (simple queries)
- Document any breaking changes
- Review test coverage regularly
