# Test Coverage Improvement Plan

**Date:** October 30, 2025
**Current Coverage:** 14% overall
**Target Coverage:** 70%+ for critical paths

---

## Executive Summary

After experiencing 4 failed API submissions due to untested code, we've identified critical gaps in test coverage. This document outlines a prioritized plan to improve test coverage from 14% to 70%+ for critical code paths.

**Key Insight:** Our tests were **mocking without validation** - they checked that functions were called, but not that they were called correctly.

---

## Current State (October 30, 2025)

### Coverage by Module

| Module | Coverage | Critical? | Priority |
|--------|----------|-----------|----------|
| **Providers** | | | |
| `openai_provider.py` | 51% | ✅ Yes | **HIGH** |
| `gemini_provider.py` | 11% →  ~60% | ✅ Yes | **HIGH** ✅ IMPROVED |
| `grok_provider.py` | 21% | ⚠️ Used | **MEDIUM** |
| `anthropic_provider.py` | 0% | ❌ No | LOW |
| `azure_provider.py` | 16% | ⚠️ Enterprise | **MEDIUM** |
| **Queue** | | | |
| `local_queue.py` | 95% | ✅ Yes | ✅ GOOD |
| `base.py` | 87% | ✅ Yes | ✅ GOOD |
| **Storage** | | | |
| `local.py` | 61% | ✅ Yes | **MEDIUM** |
| `base.py` | 85% | ✅ Yes | ✅ GOOD |
| **Core** | | | |
| `costs.py` | 93% | ✅ Yes | ✅ GOOD |
| `research.py` | 22% | ✅ Yes | **HIGH** |
| `jobs.py` | 27% | ✅ Yes | **HIGH** |
| **CLI** | | | |
| All CLI commands | 0% | ✅ Yes | **HIGH** |
| **API/Worker** | | | |
| Web API | 0% | ❌ No | LOW |
| Background worker | 0% | ⚠️ Used | **MEDIUM** |

### What Works Well ✅

- **Queue operations**: 95% coverage with comprehensive tests
- **Cost calculations**: 93% coverage with edge cases
- **Storage**: 85%+ coverage for base functionality
- **Basic unit tests**: Good structure, just need expansion

### Critical Gaps 🚨

1. **Provider API integration** (51% OpenAI, 11% Gemini, 21% Grok)
   - **Issue**: Tests mock without validating parameters
   - **Impact**: Production failures not caught (4 failed submissions)
   - **Fix**: Validate actual API parameters in tests

2. **CLI commands** (0% coverage)
   - **Issue**: No tests for user-facing commands
   - **Impact**: Argument parsing bugs, validation failures
   - **Fix**: Add CLI integration tests

3. **Core research workflows** (22-27% coverage)
   - **Issue**: Main research logic untested
   - **Impact**: Workflow bugs, state management issues
   - **Fix**: Add workflow integration tests

---

## Lessons from Container Parameter Bug

### What Went Wrong

```python
# TEST CODE (insufficient)
mock_create.assert_called_once()  # Only checked it was called
```

**Problem:** Test passed even though parameters were wrong.

```python
# PRODUCTION CODE (buggy)
tools.append({"type": "web_search_preview", "container": {"type": "auto"}})
# ❌ web_search_preview doesn't take container parameter
```

**Result:** 4 failed API submissions, 45 minutes debugging

### What We Fixed

```python
# NEW TEST CODE (validates parameters)
call_kwargs = mock_create.call_args.kwargs
tools = call_kwargs["tools"]
assert "container" not in tools[0]  # ✅ Would have caught the bug!
```

**Result:** Bug prevented from happening again

### Key Principle

> **Don't just test that code runs - test that it runs CORRECTLY**

---

## Improvement Strategy

### Phase 1: Critical Path Coverage (Target: 2-3 days)

**Goal:** Bring critical paths to 70%+ coverage

#### 1.1 Provider API Parameter Validation ✅ STARTED

**Status:** OpenAI improved, Gemini improved
**Remaining:** Grok, Azure

**Tasks:**
- [x] Create `test_openai_tool_validation.py` with parameter validation
- [x] Create `test_gemini_provider.py` with 20 comprehensive tests
- [ ] Add Grok provider tests (similar pattern)
- [ ] Add Azure provider tests (similar pattern)

**Template for Provider Tests:**
```python
def test_tool_parameters_are_correct(self, provider):
    """Test that tools are formatted correctly for the provider API."""
    # Submit with mocked client
    await provider.submit_research(request)

    # Validate ACTUAL parameters sent to API
    call_kwargs = mock_api.call_args.kwargs
    assert call_kwargs["tools"][0] == expected_format
    assert "unexpected_param" not in call_kwargs["tools"][0]
```

#### 1.2 CLI Command Tests (0% → 50%)

**Priority:** HIGH - User-facing code with zero coverage

**Tasks:**
- [ ] Add `tests/cli/test_run_command.py` - Test research submission
- [ ] Add `tests/cli/test_jobs_command.py` - Test job management
- [ ] Add `tests/cli/test_budget_command.py` - Test budget controls
- [ ] Add parameter validation tests (required args, type checking)

**Example Test:**
```python
def test_run_focus_validates_required_args():
    """Test that run focus requires a query."""
    result = runner.invoke(cli, ["run", "focus"])
    assert result.exit_code != 0
    assert "query is required" in result.output.lower()
```

#### 1.3 Core Research Workflow Tests (22% → 60%)

**Priority:** HIGH - Main business logic

**Tasks:**
- [ ] Add `tests/integration/test_research_workflow.py`
- [ ] Test full research flow: submit → queue → process → store
- [ ] Test multi-phase campaigns with context chaining
- [ ] Test error handling and retry logic

**Example Test:**
```python
@pytest.mark.integration
async def test_full_research_workflow(tmp_path):
    """Test complete research workflow from submission to storage."""
    # Setup
    queue = SQLiteQueue(tmp_path / "queue.db")
    storage = LocalStorage(tmp_path / "research")
    provider = MockProvider()

    # Submit
    job_id = await submit_research("test query", queue, provider)
    assert job_id is not None

    # Process
    job = queue.dequeue()
    assert job.id == job_id

    result = await provider.get_status(job_id)
    assert result.status == "completed"

    # Store
    report_path = storage.save_report(job_id, result.output)
    assert report_path.exists()
```

### Phase 2: Medium Priority Coverage (Target: 1 week)

#### 2.1 Grok Provider (21% → 60%)

- [ ] Add comprehensive tests similar to Gemini
- [ ] Test X/Twitter search integration
- [ ] Test agentic tool calling

#### 2.2 Azure Provider (16% → 50%)

- [ ] Test enterprise deployment scenarios
- [ ] Test authentication (key-based, Entra ID)
- [ ] Test Azure-specific features

#### 2.3 Storage Module (61% → 80%)

- [ ] Test edge cases (disk full, permissions)
- [ ] Test migration from old to new format
- [ ] Test concurrent access

#### 2.4 Background Worker (0% → 50%)

- [ ] Test polling logic
- [ ] Test error handling and retries
- [ ] Test graceful shutdown

### Phase 3: Nice-to-Have Coverage (Target: Ongoing)

#### 3.1 Web API (0% → 40%)

- [ ] Test REST endpoints
- [ ] Test WebSocket events
- [ ] Test authentication/authorization

#### 3.2 Advanced Features (Various → 50%)

- [ ] Test vector store management
- [ ] Test prompt templates
- [ ] Test analytics and reporting
- [ ] Test configuration validation

---

## Testing Principles

### 1. Test Behavior, Not Implementation

**Bad:**
```python
def test_internal_method_called():
    provider._format_tools.assert_called_once()  # Testing implementation
```

**Good:**
```python
def test_tools_formatted_correctly():
    result = await provider.submit_research(request)
    actual_tools = mock_api.call_args.kwargs["tools"]
    assert actual_tools == expected_tools  # Testing behavior
```

### 2. Test Real-World Scenarios

**Bad:** Test single tool types in isolation

**Good:** Test combinations used in production
```python
def test_file_upload_with_multiple_tools():
    """Test the actual combination used when uploading files."""
    request = ResearchRequest(
        tools=[
            ToolConfig(type="file_search", vector_store_ids=["vs_123"]),
            ToolConfig(type="web_search_preview"),
            ToolConfig(type="code_interpreter"),
        ]
    )
    # This is what actually runs in production
```

### 3. Validate Parameters, Not Just Calls

**Bad:**
```python
mock_api.assert_called_once()  # Just checks it was called
```

**Good:**
```python
call_kwargs = mock_api.call_args.kwargs
assert call_kwargs["model"] == "o4-mini-deep-research"
assert "container" not in call_kwargs["tools"][0]
assert call_kwargs["tools"][1]["container"] == {"type": "auto"}
```

### 4. Document API Requirements in Tests

```python
def test_web_search_no_container():
    """Test web_search_preview does NOT include container parameter.

    Per OpenAI Responses API docs (line 36 in docs/openai_deep_research.txt):
    web_search_preview only requires {"type": "web_search_preview"}

    This prevents regression of the Oct 30, 2025 container parameter bug
    that caused 4 failed submissions.
    """
    # Test implementation
```

### 5. Create Regression Tests Immediately

When you fix a bug, add a test:
```python
class TestToolParameterRegressions:
    """Regression tests for specific bugs we've encountered."""

    def test_regression_container_on_web_search():
        """Regression test: web_search_preview should NOT have container.

        Bug history:
        - Oct 30, 2025: 4 failed submissions due to incorrect container param
        - Fixed in commit abc123

        This test ensures we never reintroduce this bug.
        """
        # Test implementation
```

---

## Implementation Checklist

### Immediate (This Week)

- [x] Fix OpenAI provider tool parameter bug
- [x] Add `test_openai_tool_validation.py` (7 tests)
- [x] Add `test_gemini_provider.py` (20 tests)
- [ ] Add Grok provider tests
- [ ] Add basic CLI command tests
- [ ] Run full test suite and verify no regressions

### Short Term (Next 2 Weeks)

- [ ] Add Azure provider tests
- [ ] Add core research workflow integration tests
- [ ] Add background worker tests
- [ ] Achieve 50%+ overall coverage

### Medium Term (Next Month)

- [ ] Add Web API tests
- [ ] Add advanced feature tests
- [ ] Achieve 70%+ overall coverage for critical paths
- [ ] Set up CI/CD with coverage tracking

### Ongoing

- [ ] Add regression test for every bug fixed
- [ ] Review test coverage in every PR
- [ ] Maintain 70%+ coverage for new code

---

## Metrics & Tracking

### Coverage Goals

| Timeframe | Target | Current | Status |
|-----------|--------|---------|--------|
| Immediate | 25% | 14% → 20% | 🟡 In Progress |
| 1 Week | 35% | 14% | 🔴 Not Started |
| 2 Weeks | 50% | 14% | 🔴 Not Started |
| 1 Month | 70% | 14% | 🔴 Not Started |

### Test Count Goals

| Category | Current | Target | Progress |
|----------|---------|--------|----------|
| Provider Tests | 20 | 60 | 33% |
| CLI Tests | 0 | 30 | 0% |
| Integration Tests | 0 | 20 | 0% |
| Regression Tests | 1 | 10+ | 10% |
| **Total** | **75** | **200+** | **37%** |

### Quality Metrics

- **Bugs caught by tests before production:** 0 → 5+ per month
- **Time to fix bugs with tests:** ~45 min → <15 min
- **Confidence in refactoring:** Low → High
- **Production incidents:** Track decrease over time

---

## Tools & Infrastructure

### Current Setup ✅

- pytest with async support
- Coverage tracking with pytest-cov
- Mocking with unittest.mock
- Fixtures for common setups

### Recommended Additions

1. **Coverage tracking in CI/CD**
   ```yaml
   # .github/workflows/test.yml
   - name: Run tests with coverage
     run: pytest --cov=deepr --cov-report=xml --cov-fail-under=50
   ```

2. **Pre-commit hooks**
   ```yaml
   # .pre-commit-config.yaml
   - repo: local
     hooks:
       - id: pytest-coverage
         name: Check test coverage
         entry: pytest --cov=deepr --cov-fail-under=50
   ```

3. **Coverage badges in README**
   - Show current coverage percentage
   - Link to detailed coverage report

---

## Success Criteria

### Technical Metrics

- ✅ 70%+ coverage for critical paths (providers, core, CLI)
- ✅ 0 production bugs caught by tests before release per month
- ✅ All provider API parameters validated in tests
- ✅ Regression tests for all fixed bugs

### Process Metrics

- ✅ Test coverage reviewed in every PR
- ✅ Coverage trending upward month-over-month
- ✅ New features include tests from day 1
- ✅ Bug fixes include regression tests

### Team Metrics

- ✅ Increased confidence in refactoring
- ✅ Faster debugging (test pinpoints exact issue)
- ✅ Fewer "works on my machine" issues
- ✅ Documentation via tests (tests as specs)

---

## Conclusion

The container parameter bug taught us a valuable lesson: **tests that don't validate behavior provide false confidence**.

By improving test coverage from 14% to 70%+ with proper parameter validation, we can:
- Catch bugs before they reach production
- Refactor with confidence
- Document API requirements
- Reduce debugging time
- Ship faster with higher quality

**Next Steps:**
1. Complete Grok provider tests (this week)
2. Add basic CLI command tests (this week)
3. Set up coverage tracking in CI/CD (next week)
4. Review and update this plan monthly

---

## Related Documents

- [docs/BUGFIX_CONTAINER_PARAMETER.md](BUGFIX_CONTAINER_PARAMETER.md) - The bug that started this
- [tests/unit/test_providers/test_openai_tool_validation.py](../tests/unit/test_providers/test_openai_tool_validation.py) - Example of good testing
- [tests/unit/test_providers/test_gemini_provider.py](../tests/unit/test_providers/test_gemini_provider.py) - Comprehensive provider tests
- [tests/README.md](../tests/README.md) - Test organization and guidelines
