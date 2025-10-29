# Testing Strategy for Deepr

## Current Test Coverage

### Existing Tests (30 passing)

**Unit Tests:**
- ✅ Cost estimation and tracking (17 tests)
- ✅ Queue operations (local SQLite) (11 tests)
- ✅ OpenAI provider (mocked, 4 tests)
- ✅ Context chaining (3 tests)

**Integration Tests:**
- ⚠️ Anthropic provider (1 test, requires API key)
- ⚠️ Real OpenAI submission (1 test, failing - requires API key)

### Coverage Gaps (Need Testing)

**Priority 1 - Core Functionality (No API Calls):**
- ❌ Storage backend (LocalStorage)
  - save_report with metadata
  - get_report with legacy lookups
  - Human-readable directory naming
  - metadata.json generation
- ❌ Vector store management
- ❌ Prompt refinement logic
- ❌ Configuration validation
- ❌ Analytics calculations
- ❌ Template system

**Priority 2 - Integration (Mocked APIs):**
- ❌ Worker/poller job processing
- ❌ Batch executor (campaign execution)
- ❌ Research command end-to-end
- ❌ Queue sync operations
- ❌ File upload handling

**Priority 3 - Real API Tests (Cost-Limited):**
- ❌ Single research job submission (<$0.10)
- ❌ Job status polling
- ❌ Report retrieval
- ❌ Vector store with file upload (<$0.20)
- ❌ Prompt refinement with GPT-4o-mini (<$0.01)

## Test Architecture

### Three-Tier Testing Approach

```
┌─────────────────────────────────────────────────┐
│  1. UNIT TESTS (Fast, Free, Always Run)        │
│     - Pure logic, no I/O                       │
│     - Mock all external dependencies           │
│     - pytest -m unit                            │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  2. INTEGRATION TESTS (Fast, Free, Pre-Commit)  │
│     - Mock API responses                        │
│     - Real filesystem/database                  │
│     - pytest -m integration                     │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  3. E2E TESTS (Slow, $$, Manual/CI Only)        │
│     - Real API calls with cost limits          │
│     - Max $0.50 total per run                  │
│     - pytest -m e2e --allow-api                │
└─────────────────────────────────────────────────┘
```

### Pytest Markers

```python
@pytest.mark.unit          # Pure unit test, no I/O
@pytest.mark.integration   # Integration test with mocks
@pytest.mark.e2e           # End-to-end with real APIs
@pytest.mark.slow          # Takes >5 seconds
@pytest.mark.requires_api  # Needs API key, costs money
```

## Implementation Plan

### Phase 1: Unit Tests (This Week)

**Storage Tests** (`tests/unit/test_storage/test_local.py`)
```python
- test_save_report_creates_readable_dirname()
- test_save_report_generates_metadata()
- test_get_job_dir_finds_legacy_uuid()
- test_get_job_dir_finds_human_readable()
- test_campaign_uses_campaigns_subfolder()
- test_slug_generation_from_prompt()
- test_metadata_json_structure()
```

**Vector Store Tests** (`tests/unit/test_vector_store.py`)
```python
- test_create_vector_store()
- test_list_vector_stores()
- test_delete_vector_store()
- test_vector_store_lookup_by_name()
```

**Prompt Refinement Tests** (`tests/unit/test_prompt_refinement.py`)
```python
- test_refine_prompt_adds_date()
- test_refine_prompt_structures_output()
- test_dry_run_mode()
- test_auto_refine_config()
```

**Config Tests** (`tests/unit/test_config.py`)
```python
- test_validate_config()
- test_missing_required_fields()
- test_cost_limit_validation()
```

**Analytics Tests** (`tests/unit/test_analytics.py`)
```python
- test_success_rate_calculation()
- test_cost_trends_aggregation()
- test_failure_analysis()
```

**Template Tests** (`tests/unit/test_templates.py`)
```python
- test_save_template()
- test_load_template()
- test_template_variable_substitution()
```

### Phase 2: Integration Tests (Next Week)

**Worker Tests** (`tests/integration/test_worker.py`)
```python
- test_worker_polls_queue()
- test_worker_processes_job() # with mocked API
- test_worker_saves_report()
- test_worker_handles_failures()
```

**Batch Executor Tests** (`tests/integration/test_batch_executor.py`)
```python
- test_execute_campaign() # with mocked API
- test_phase_dependencies()
- test_context_chaining()
- test_campaign_results_saved()
```

**Research CLI Tests** (`tests/integration/test_research_cli.py`)
```python
- test_submit_research_command()
- test_get_result_command()
- test_cancel_command()
- test_queue_sync()
```

### Phase 3: E2E Tests (CI/Manual Only)

**Real API Tests** (`tests/e2e/test_cheap_api.py`)
```python
# Max cost: $0.10 per test
@pytest.mark.e2e
@pytest.mark.requires_api
def test_minimal_research_o4_mini():
    """Single research with o4-mini, minimal prompt (<$0.10)"""

@pytest.mark.e2e
@pytest.mark.requires_api
def test_file_upload_vector_search():
    """Upload small file, search with vector store (<$0.20)"""

@pytest.mark.e2e
@pytest.mark.requires_api
def test_prompt_refinement_real():
    """Test real prompt refinement with GPT-4o-mini (<$0.01)"""
```

**Cost Safety Wrapper:**
```python
@pytest.fixture
def api_cost_limiter():
    """Ensure test doesn't exceed cost limit"""
    max_cost = 0.50

    def _check_cost(actual_cost):
        if actual_cost > max_cost:
            pytest.fail(f"Test exceeded cost limit: ${actual_cost} > ${max_cost}")

    return _check_cost
```

## Test Execution Strategy

### Developer Workflow

```bash
# Fast feedback loop (< 5 seconds)
pytest -m unit

# Pre-commit checks (< 30 seconds)
pytest -m "unit or integration"

# Full test suite excluding API
pytest -m "not (e2e or requires_api)"

# Manual API testing (when needed)
pytest -m e2e --allow-api  # Requires flag to prevent accidental runs
```

### CI/CD Pipeline

```yaml
# GitHub Actions / CI
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest -m unit

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest -m integration

  e2e-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    steps:
      - run: pytest -m e2e --allow-api --maxfail=1
      # Stop immediately if any test fails to save money
```

## Mock Strategy

### Provider Mocking

```python
# tests/fixtures/mock_openai.py
@pytest.fixture
def mock_openai_response():
    """Mock successful OpenAI deep research response"""
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "text", "text": "Mock research report..."}]
            }
        ],
        "usage": {
            "total_tokens": 5000,
            "cost": 0.15
        }
    }

@pytest.fixture
def mock_openai_provider(mocker, mock_openai_response):
    """Mock OpenAI provider for integration tests"""
    mock = mocker.patch("deepr.providers.openai_provider.OpenAI")
    mock.return_value.chat.completions.create.return_value = mock_openai_response
    return mock
```

### Storage Mocking

```python
@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary storage for tests"""
    from deepr.storage import LocalStorage
    return LocalStorage(base_path=str(tmp_path / "reports"))
```

## Success Criteria

### Phase 1 Complete (Unit Tests)
- ✅ 50+ unit tests passing
- ✅ No external I/O (network, real files)
- ✅ Coverage > 70% for core modules
- ✅ All tests run in < 10 seconds

### Phase 2 Complete (Integration Tests)
- ✅ 30+ integration tests passing
- ✅ All API calls mocked
- ✅ Real filesystem/database operations
- ✅ All tests run in < 60 seconds

### Phase 3 Complete (E2E Tests)
- ✅ 10+ E2E tests passing
- ✅ Total cost per run < $0.50
- ✅ Tests validate real API behavior
- ✅ Manual approval required to run

### Documentation Complete
- ✅ Remove "needs testing" from README
- ✅ Update ROADMAP with test status
- ✅ Mark features as "production-ready" when tested

## Test Utilities

### Cost Tracking Decorator

```python
# tests/utils/cost_tracking.py
def track_api_cost(max_cost: float):
    """Decorator to track and limit API test costs"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_balance = get_api_balance()  # Implement if possible
            result = await func(*args, **kwargs)
            cost = start_balance - get_api_balance()

            if cost > max_cost:
                pytest.fail(f"Test cost ${cost:.4f} exceeded limit ${max_cost}")

            print(f"\n💰 Test cost: ${cost:.4f}")
            return result
        return wrapper
    return decorator
```

### Test Data Generators

```python
# tests/factories.py
class JobFactory:
    """Generate test job objects"""

    @staticmethod
    def create_simple_job(prompt="Test prompt"):
        return ResearchJob(
            id=str(uuid.uuid4()),
            prompt=prompt,
            model="o4-mini-deep-research",
            status=JobStatus.QUEUED
        )

    @staticmethod
    def create_campaign_jobs(task_count=3):
        """Generate campaign with N tasks"""
        # ...
```

## Next Steps

1. **Week 1:** Implement Phase 1 unit tests (storage, vector, config)
2. **Week 2:** Implement Phase 2 integration tests (worker, batch executor)
3. **Week 3:** Implement Phase 3 E2E tests with cost limits
4. **Week 4:** Update docs, remove "needs testing" flags

**Goal:** All v2.3 features fully tested and marked "production-ready" by end of month.
