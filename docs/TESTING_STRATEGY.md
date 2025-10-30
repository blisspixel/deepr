# Testing Strategy: Unit Tests vs Integration Tests

**Date:** October 30, 2025
**Status:** Active

---

## The Problem We Discovered

On October 30, 2025, we experienced 4 consecutive API failures when uploading files. The root cause: **unit tests passed but real API calls failed**.

### Why Unit Tests Weren't Enough

Our unit tests used mocks but didn't validate what parameters were being sent:

```python
# UNIT TEST (passed but didn't catch bug)
mock_api.assert_called_once()  # Just checked it was called

# REAL API CALL (failed 4 times)
# Error: Unknown parameter: 'tools[0].container'
```

**The issue:** Tests validated that code ran, not that it was correct.

---

## Testing Philosophy

> **Unit tests tell you if your code runs.
> Integration tests tell you if it works.**

We need BOTH:

1. **Unit Tests** - Fast, cheap, catch logic errors
2. **Integration Tests** - Slow, costly, catch API contract violations

---

## Three-Layer Testing Strategy

### Layer 1: Unit Tests (Fast, Free, Always Run)

**Purpose:** Validate internal logic without external dependencies

**Characteristics:**
- No real API calls (100% mocked)
- Run in <5 seconds
- Zero cost
- Run on every commit
- Test internal business logic

**What to validate:**
- Parameter formatting (CRITICAL)
- Data transformations
- Error handling logic
- State management
- Cost calculations

**Example - Parameter Validation:**
```python
def test_tool_parameters_formatted_correctly():
    """Unit test that validates ACTUAL parameters sent to mocked API."""
    provider = OpenAIProvider(api_key="test")
    mock_response = MagicMock()

    with patch.object(provider.client.responses, "create") as mock_create:
        mock_create.return_value = mock_response

        request = ResearchRequest(
            prompt="Test",
            tools=[
                ToolConfig(type="file_search", vector_store_ids=["vs_123"]),
                ToolConfig(type="web_search_preview"),
                ToolConfig(type="code_interpreter"),
            ]
        )

        await provider.submit_research(request)

        # KEY: Validate the actual parameters
        call_kwargs = mock_create.call_args.kwargs
        tools = call_kwargs["tools"]

        # These assertions would have caught the bug
        assert "container" not in tools[0], "file_search should NOT have container"
        assert "container" not in tools[1], "web_search should NOT have container"
        assert "container" in tools[2], "code_interpreter MUST have container"
```

**Files:**
- `tests/unit/test_providers/test_openai_tool_validation.py`
- `tests/unit/test_providers/test_gemini_provider.py`
- `tests/unit/test_costs.py`
- `tests/unit/test_queue/*.py`
- `tests/unit/test_storage/*.py`

### Layer 2: Integration Tests (Slow, Cheap, Run Periodically)

**Purpose:** Validate that code works with real APIs using minimal/cheap queries

**Characteristics:**
- Real API calls
- Cheap queries (<$0.10 per test)
- Run manually or in CI (not on every commit)
- Test API contract compliance

**What to validate:**
- API accepts our requests
- Response format matches expectations
- Error codes are handled correctly
- File uploads work end-to-end

**Example - Cheap API Validation:**
```python
@pytest.mark.integration
@pytest.mark.requires_api
async def test_openai_tool_parameters_real_api():
    """Integration test with REAL API - validates tool parameters work."""
    provider = OpenAIProvider()  # Real API key

    # Cheap query with web_search_preview (no container)
    request = ResearchRequest(
        prompt="What is 2+2?",
        model="o4-mini-deep-research",
        tools=[ToolConfig(type="web_search_preview")],
        background=True
    )

    # This will FAIL if tool parameters are wrong
    job_id = await provider.submit_research(request)
    assert job_id is not None  # Success means parameters are correct
```

**Files:**
- `tests/integration/test_file_upload_api.py`
- `tests/integration/test_all_providers.py`
- `tests/integration/test_cli_commands.py`

**Cost Control:**
- Use simplest queries ("What is 2+2?")
- Use cheap models when possible
- Limit research scope
- Budget: <$1 per test run, <$10 per month

### Layer 3: E2E Tests (Very Slow, Expensive, Run Rarely)

**Purpose:** Validate complete workflows in production-like scenarios

**Characteristics:**
- Full workflows (file upload → research → storage)
- Realistic queries
- High cost ($1-10 per test)
- Run before releases only
- Test user-facing functionality

**What to validate:**
- Complete user workflows
- Multi-phase campaigns
- Error recovery
- Performance under load

**Example - Full Workflow:**
```python
@pytest.mark.e2e
@pytest.mark.expensive
async def test_complete_file_upload_research_workflow():
    """E2E test of full file upload + research workflow."""
    # 1. Upload files
    # 2. Create vector store
    # 3. Submit research
    # 4. Poll for completion
    # 5. Retrieve and validate results
    # 6. Verify storage
    # Cost: ~$0.50-$2.00
```

**Files:**
- `tests/test_e2e_cheap.py`
- `tests/integration/test_cli_e2e.py`

**Cost Control:**
- Run only before releases
- Manual execution only
- Budget: <$10 per release

---

## Test Markers

We use pytest markers to categorize tests:

```python
@pytest.mark.unit              # Fast, free, always run
@pytest.mark.integration       # Slow, cheap, run periodically
@pytest.mark.e2e               # Very slow, expensive, run rarely
@pytest.mark.requires_api      # Requires API key (integration or e2e)
@pytest.mark.file_upload       # Tests file upload (costs money)
@pytest.mark.expensive         # High-cost test (>$1)
```

### Running Tests

```bash
# Run only unit tests (fast, free)
pytest -m unit

# Run unit + integration (requires API key, costs <$5)
pytest -m "unit or integration"

# Run everything including E2E (costs $10+)
pytest

# Run only file upload tests (costs money)
pytest -m file_upload

# Skip expensive tests
pytest -m "not expensive"
```

---

## What Each Layer Catches

| Issue Type | Unit | Integration | E2E |
|------------|------|-------------|-----|
| Logic errors | YES | YES | YES |
| Type errors | YES | YES | YES |
| Parameter formatting | YES | YES | YES |
| API contract violations | NO | YES | YES |
| Network issues | NO | YES | YES |
| Performance problems | NO | SOME | YES |
| User workflow issues | NO | NO | YES |
| Cost estimation accuracy | SOME | YES | YES |

---

## The Container Parameter Bug Case Study

Let's trace how each layer would have caught (or missed) the bug:

### What Happened
- Bug: `web_search_preview` received `container` parameter (should not have)
- Result: 4 failed API submissions, 45 min debugging

### Layer 1: Unit Tests (BEFORE our fix)

**Original unit test:**
```python
def test_submit_research(self, provider):
    mock_create.return_value = mock_response
    job_id = await provider.submit_research(request)
    assert job_id == "resp_test123"
    mock_create.assert_called_once()  # INSUFFICIENT
```

**Result:** PASSED (bug not caught)
**Why:** Didn't validate parameters

### Layer 1: Unit Tests (AFTER our fix)

**Improved unit test:**
```python
def test_web_search_no_container(self, provider):
    """Test web_search_preview does NOT have container parameter."""
    mock_create.return_value = mock_response
    await provider.submit_research(request)

    # Validate actual parameters
    tools = mock_create.call_args.kwargs["tools"]
    assert "container" not in tools[0]  # WOULD CATCH BUG
```

**Result:** WOULD FAIL (bug caught)
**Cost:** $0, runs in milliseconds

### Layer 2: Integration Tests

**Integration test:**
```python
@pytest.mark.integration
async def test_file_upload_real_api():
    """Test file upload with real API."""
    provider = OpenAIProvider()  # Real API

    request = ResearchRequest(
        prompt="Test query",
        tools=[
            ToolConfig(type="file_search", vector_store_ids=["vs_123"]),
            ToolConfig(type="web_search_preview"),  # Bug here
        ]
    )

    job_id = await provider.submit_research(request)  # FAILS HERE
```

**Result:** WOULD FAIL (bug caught)
**Cost:** $0.10-0.50 per test run
**Time:** 5-30 seconds

### Layer 3: E2E Tests

**E2E test:**
```python
@pytest.mark.e2e
async def test_full_research_with_files():
    """Test complete file upload research workflow."""
    # This would fail at submission stage
```

**Result:** WOULD FAIL (bug caught)
**Cost:** $1-5 per test run
**Time:** 2-10 minutes

### Conclusion

**Best approach:** Layer 1 (improved unit tests) + Layer 2 (integration tests)

- Unit tests catch 90% of bugs at $0 cost
- Integration tests catch the remaining 10% at low cost
- E2E tests validate user experience but too expensive for frequent use

---

## CI/CD Integration

### Pre-Commit Hook (Local)

```bash
# Run unit tests only (fast, free)
pytest -m unit --tb=short
```

### Pull Request CI (GitHub Actions)

```yaml
# .github/workflows/pr-tests.yml
- name: Run unit tests
  run: pytest -m unit --cov=deepr --cov-fail-under=70

# Optional: Run cheap integration tests on main branch only
- name: Run integration tests
  if: github.ref == 'refs/heads/main'
  run: pytest -m "integration and not expensive"
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### Release CI (Before Deploy)

```yaml
# .github/workflows/release.yml
- name: Run all tests including E2E
  run: pytest --maxfail=3
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

---

## Test Coverage Goals

| Module | Unit | Integration | E2E |
|--------|------|-------------|-----|
| Providers | 70%+ | Required | Optional |
| Queue | 90%+ | Optional | Required |
| Storage | 80%+ | Optional | Required |
| CLI | 50%+ | Required | Required |
| Core Research | 60%+ | Required | Required |
| Web API | 40%+ | Required | Optional |

### Current Status (Oct 30, 2025)

- Overall coverage: 14% → Target: 70%
- Provider unit tests: Improved (OpenAI 51%, Gemini 60%)
- Provider integration tests: Need expansion
- CLI tests: 0% → Target: 50%

---

## Best Practices

### 1. Write Unit Tests That Validate Parameters

**Bad:**
```python
mock_api.assert_called_once()  # Just checks it was called
```

**Good:**
```python
call_kwargs = mock_api.call_args.kwargs
assert call_kwargs["tools"][0] == expected_format
```

### 2. Use Integration Tests for API Contracts

Test that your requests are accepted by the real API, not just that your code runs.

### 3. Keep Integration Tests Cheap

```python
# BAD: Expensive query
prompt = "Write a comprehensive 50-page analysis..."

# GOOD: Cheap query
prompt = "What is 2+2? One sentence only."
```

### 4. Document Cost in Test Docstrings

```python
@pytest.mark.integration
async def test_file_upload():
    """Test file upload with real API.

    Cost: ~$0.10 per run
    Duration: ~10 seconds
    """
```

### 5. Create Regression Tests for Every Bug

When you fix a bug, add a test that would have caught it:

```python
class TestToolParameterRegressions:
    """Regression tests for specific bugs."""

    def test_regression_oct_30_2025_container_bug():
        """Regression: web_search_preview should NOT have container.

        Bug history: Oct 30, 2025 - 4 failed submissions
        Fixed in: commit abc123
        """
        # Test that prevents re-introduction
```

---

## Cost Management

### Monthly Testing Budget

- Unit tests: $0/month (no API calls)
- Integration tests (CI): ~$5/month (50 runs × $0.10)
- Integration tests (manual): ~$5/month (ad-hoc testing)
- E2E tests (releases): ~$10/month (1 release × $10)
- **Total: ~$20/month**

### Cost Tracking

```python
# Track actual vs estimated cost in tests
@pytest.fixture(autouse=True)
def track_test_cost():
    """Track cost of API tests."""
    start = datetime.now()
    yield
    duration = (datetime.now() - start).total_seconds()

    if cost_tracker.get_cost() > EXPECTED_COST * 2:
        pytest.fail(f"Test cost too high: ${cost_tracker.get_cost()}")
```

---

## Summary

The container parameter bug taught us:

1. **Unit tests must validate parameters**, not just calls
2. **Integration tests are essential** for API contract validation
3. **Both layers are needed** - unit tests for speed, integration for confidence
4. **Cost can be managed** - most tests should be unit tests (<$0), integration tests for critical paths (<$0.10 each)

### Quick Reference

| When to use... | Unit Tests | Integration Tests | E2E Tests |
|----------------|-----------|-------------------|-----------|
| Every commit | YES | NO | NO |
| Every PR | YES | Optional | NO |
| Before release | YES | YES | YES |
| Bug reproduction | YES | If API-related | Rarely |
| Cost per run | $0 | $0.10-1.00 | $1-10 |
| Run time | <1 min | 1-5 min | 5-30 min |

---

## Related Documents

- [docs/BUGFIX_CONTAINER_PARAMETER.md](BUGFIX_CONTAINER_PARAMETER.md) - The bug that motivated this
- [docs/TEST_COVERAGE_IMPROVEMENT_PLAN.md](TEST_COVERAGE_IMPROVEMENT_PLAN.md) - Coverage roadmap
- [tests/integration/test_file_upload_api.py](../tests/integration/test_file_upload_api.py) - Integration test examples
- [tests/unit/test_providers/test_openai_tool_validation.py](../tests/unit/test_providers/test_openai_tool_validation.py) - Unit test examples
