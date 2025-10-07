# Testing Guide

## Overview

Deepr uses pytest for testing with a focus on local-only tests that avoid API costs. All tests run without making real API calls to OpenAI or Azure services.

## Running Tests

### Quick Test (Recommended)

**Windows (PowerShell):**
```powershell
.\scripts\test_all.ps1
```

**Linux/Mac (Bash):**
```bash
bash scripts/test_all.sh
```

**Cross-platform (Python):**
```bash
python -m pytest tests/unit/ -m "not integration"
```

### All Tests

```bash
# Run all unit tests
pytest tests/unit/

# Run with coverage
pytest tests/unit/ --cov=deepr

# Run specific test file
pytest tests/unit/test_costs.py -v

# Run specific test
pytest tests/unit/test_costs.py::TestCostEstimator::test_estimate_short_prompt -v
```

## Test Organization

```
tests/
├── unit/                           # Unit tests (no API calls)
│   ├── test_costs.py              # Cost estimation tests (14 tests)
│   ├── test_providers/
│   │   └── test_openai_provider.py # Provider tests (6 tests, mocked)
│   └── test_queue/
│       └── test_local_queue.py    # Queue tests (10 tests)
└── integration/                    # Integration tests (require API keys)
    └── (future)
```

## Test Categories

### Unit Tests (30 tests)

All unit tests run locally without API calls:

**Cost Estimation (14 tests)**
- Token estimation
- Cost calculation
- Budget enforcement (per-job, daily, monthly)
- Safe test prompts

**Queue System (10 tests)**
- Job enqueue/dequeue
- Priority handling
- Status updates
- Atomic operations
- Cleanup

**Provider Integration (6 tests)**
- Mock API calls
- Provider initialization
- Model mapping
- Job submission/status/cancellation

**Total: 30 passing tests, 0 API costs**

### Integration Tests (0 tests)

Integration tests are marked with `@pytest.mark.integration` and require:
- Valid API keys (OPENAI_API_KEY or Azure credentials)
- Budget for API calls (use cheap prompts)
- Skipped by default

To run integration tests:
```bash
pytest tests/ -m "integration"
```

## Test Configuration

### pytest.ini

```ini
[pytest]
testpaths = tests
asyncio_mode = auto

markers =
    integration: requires API keys, may cost money
    unit: no API calls, always free
    slow: may take >1 second
```

### Custom Markers

- `@pytest.mark.integration` - Requires API keys, may cost money
- `@pytest.mark.unit` - No API calls, always free
- `@pytest.mark.slow` - May take >1 second

## Writing Tests

### Unit Test Example

```python
import pytest
from deepr.core.costs import CostEstimator

class TestCostEstimator:
    """Test cost estimation (no API calls)."""

    def test_estimate_short_prompt(self):
        """Test estimation for short prompt."""
        estimate = CostEstimator.estimate_cost(
            prompt="What is 2+2?",
            model="o4-mini-deep-research",
            enable_web_search=False
        )

        assert estimate.expected_cost < 1.0
        assert estimate.input_tokens > 0
```

### Integration Test Example (Future)

```python
import pytest
import os
from deepr.providers import OpenAIProvider

@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
class TestOpenAIIntegration:
    """Integration tests with real API (costs money)."""

    @pytest.fixture
    def provider(self):
        return OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))

    async def test_cheap_research(self, provider):
        """Test with cheapest possible prompt."""
        # Use CHEAP_TEST_PROMPTS from deepr.core.costs
        request = ResearchRequest(
            prompt="What is 2+2? Answer in one word.",
            model="o4-mini-deep-research",
            tools=[]  # No web search to keep it cheap
        )

        job_id = await provider.submit_research(request)
        assert job_id.startswith("resp_")
```

## Mocking Strategy

### Provider Mocking

```python
from unittest.mock import AsyncMock, MagicMock, patch

async def test_submit_research(provider):
    """Test research submission (mocked)."""
    mock_response = MagicMock()
    mock_response.id = "resp_test123"

    with patch.object(
        provider.client.responses,
        "create",
        new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response

        job_id = await provider.submit_research(request)
        assert job_id == "resp_test123"
```

### Database Mocking

```python
@pytest.fixture
def queue(tmp_path):
    """Create test queue with temporary database."""
    db_path = tmp_path / "test_queue.db"
    return SQLiteQueue(str(db_path))
```

## Coverage

Current test coverage:

- **deepr/core/costs.py**: 100% (all cost estimation logic)
- **deepr/queue/local_queue.py**: 95% (SQLite queue operations)
- **deepr/providers/openai.py**: 60% (mocked interfaces only)
- **deepr/config.py**: 30% (basic validation)
- **deepr/storage/**: 0% (not yet tested)

Target coverage: 80% for v2.0 release

## Continuous Integration

### GitHub Actions (Future)

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: pytest tests/unit/ -m "not integration" --cov=deepr
```

## Best Practices

1. **Always mock external APIs** in unit tests
2. **Use tmp_path fixture** for file operations
3. **Mark integration tests** with `@pytest.mark.integration`
4. **Use cheap prompts** in integration tests
5. **Run tests before committing**
6. **Add tests for new features**
7. **Test error paths**, not just happy paths

## Troubleshooting

### Import Errors

```bash
# Make sure deepr is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/unit/
```

### Async Warnings

Remove `@pytest.mark.asyncio` from non-async test functions.

### Fixture Errors

Don't use `async def` for fixtures unless necessary:

```python
# WRONG
@pytest.fixture
async def queue(tmp_path):
    return SQLiteQueue(str(tmp_path / "test.db"))

# CORRECT
@pytest.fixture
def queue(tmp_path):
    return SQLiteQueue(str(tmp_path / "test.db"))
```

## Summary

- **30 passing unit tests** validate core functionality
- **0 API costs** for all unit tests
- **Cross-platform** test scripts (PowerShell + Bash)
- **Comprehensive mocking** avoids external dependencies
- **Fast execution** (< 3 seconds for full suite)

Run tests frequently to catch regressions early.
